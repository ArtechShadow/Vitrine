# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Frame quality assessment for video-to-Gaussian pipelines.

Evaluates blur, exposure, duplicate detection, and spatial coverage to
filter out low-quality frames before reconstruction.

Typical usage::

    assessor = FrameQualityAssessor()
    report = assessor.assess_directory("/path/to/frames")
    good_frames = [r.path for r in report if r.recommendation == "keep"]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class Recommendation(str, Enum):
    """Frame filtering recommendation."""
    KEEP = "keep"
    MARGINAL = "marginal"
    DROP = "drop"


# ----------------------------------------------------------------------------
#  SOTA no-reference image-quality scorer (GPU, local)
# ----------------------------------------------------------------------------
#  Laplacian variance is a brittle, content-dependent sharpness proxy. Handheld
#  video motion blur is common, so we add a SOTA *neural* no-reference IQA score
#  (perceptual, MOS-calibrated) that captures blur + noise + exposure jointly.
#  Local + GPU via `pyiqa` (pinned). MUSIQ (multi-scale transformer, koniq) is
#  the default: timm-only, no exotic deps, ~0-100 with higher=better. The whole
#  thing degrades gracefully to the classical metrics when pyiqa/GPU is absent,
#  so this module never hard-requires the heavy dependency.
class NeuralIQA:
    """Thin wrapper over a pyiqa no-reference metric (lazy, GPU-first).

    This is a *callable capability* — the production overseer agent decides
    when/how to run it and how to act on the scores; the pipeline only exposes
    a clean scorer. ``score(path)`` returns a float where higher is better
    (sign-normalised regardless of the metric's native polarity), or ``None``
    if the backend is unavailable.
    """

    def __init__(self, model_name: str = "musiq", device: Optional[str] = None) -> None:
        self.model_name = model_name
        self._device = device
        self._metric = None
        self._higher_better = True
        self._unavailable = False

    def _ensure(self) -> bool:
        if self._metric is not None:
            return True
        if self._unavailable:
            return False
        try:
            import torch
            import pyiqa
            dev = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            self._metric = pyiqa.create_metric(self.model_name, device=dev)
            # pyiqa exposes lower_better; normalise so callers always maximise.
            self._higher_better = not bool(getattr(self._metric, "lower_better", False))
            self._device = dev
            logger.info("NeuralIQA: %s on %s (higher_better=%s)",
                        self.model_name, dev, self._higher_better)
            return True
        except Exception as exc:  # pyiqa missing, no GPU, weight-download failure…
            logger.warning("NeuralIQA unavailable (%s); falling back to classical metrics", exc)
            self._unavailable = True
            return False

    @property
    def available(self) -> bool:
        return self._ensure()

    def score(self, image_path: str | Path) -> Optional[float]:
        if not self._ensure():
            return None
        try:
            val = float(self._metric(str(image_path)).item())
        except Exception as exc:
            logger.warning("NeuralIQA scoring failed for %s: %s", image_path, exc)
            return None
        return val if self._higher_better else -val


@dataclass(slots=True)
class FrameQuality:
    """Quality assessment for a single frame.

    Attributes:
        path: Absolute path to the image file.
        blur_score: Laplacian variance (higher = sharper). Typical threshold ~100.
        exposure_mean: Mean normalised brightness in ``[0, 1]``.
        exposure_std: Standard deviation of brightness histogram.
        is_underexposed: True if the frame is too dark.
        is_overexposed: True if the frame is too bright.
        phash: 64-bit perceptual hash for duplicate detection.
        is_duplicate: True if this frame is a near-duplicate of an earlier one.
        duplicate_of: Path of the earlier frame this duplicates, if any.
        coverage_score: Fraction of image area with non-trivial gradient energy.
        recommendation: Aggregate keep/marginal/drop recommendation.
    """
    path: Path
    blur_score: float = 0.0
    exposure_mean: float = 0.0
    exposure_std: float = 0.0
    is_underexposed: bool = False
    is_overexposed: bool = False
    phash: int = 0
    is_duplicate: bool = False
    duplicate_of: Optional[Path] = None
    coverage_score: float = 0.0
    dir_sharpness: float = 0.0  # motion-blur-aware sharpness (structure-tensor lambda2); higher=sharper
    blur_direction_deg: float = -1.0  # estimated motion-blur axis [0,180); -1 = N/A
    neural_score: float = -1.0  # SOTA NR-IQA (higher=better); -1 = not computed
    recommendation: Recommendation = Recommendation.KEEP


class FrameQualityAssessor:
    """Assess and filter video frames by quality metrics.

    Parameters:
        blur_threshold: Laplacian variance below which a frame is considered blurry.
        exposure_low: Mean brightness below this is underexposed.
        exposure_high: Mean brightness above this is overexposed.
        duplicate_hash_distance: Maximum Hamming distance to flag as duplicate.
        coverage_threshold: Minimum fraction of active gradient area.
        coverage_block_size: Block size for coverage grid estimation.
    """

    def __init__(
        self,
        blur_threshold: float = 100.0,
        exposure_low: float = 0.10,
        exposure_high: float = 0.90,
        duplicate_hash_distance: int = 8,
        coverage_threshold: float = 0.20,
        coverage_block_size: int = 64,
        neural_scorer: Optional["NeuralIQA"] = None,
        min_neural_score: float = 40.0,
    ) -> None:
        self.blur_threshold = blur_threshold
        self.exposure_low = exposure_low
        self.exposure_high = exposure_high
        self.duplicate_hash_distance = duplicate_hash_distance
        self.coverage_threshold = coverage_threshold
        self.coverage_block_size = coverage_block_size
        # SOTA NR-IQA (optional). When present, a low perceptual score counts as
        # a quality issue alongside the classical cues. Default min is tuned to
        # MUSIQ/koniq (~0-100); a *good* photo scores 50-75, so 40 is a lenient
        # "usable" floor. Left absolute here; the overseer agent may override or
        # switch to relative/windowed selection per dataset.
        self.neural_scorer = neural_scorer
        self.min_neural_score = min_neural_score

    # ------------------------------------------------------------------
    #  Individual metrics
    # ------------------------------------------------------------------
    @staticmethod
    def compute_blur_score(gray: np.ndarray) -> float:
        """Compute Laplacian variance as a sharpness metric.

        A higher score indicates a sharper image.

        Args:
            gray: ``(H, W)`` uint8 grayscale image.

        Returns:
            Laplacian variance (float).
        """
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        return float(laplacian.var())

    @staticmethod
    def compute_directional_sharpness(gray: np.ndarray) -> Tuple[float, float]:
        """Motion-blur-aware sharpness via the gradient structure tensor.

        Variance-of-Laplacian is *isotropic*: a frame smeared horizontally still
        has sharp vertical edges, so it reads as "sharp" despite being motion-
        blurred. The structure tensor's *smaller* eigenvalue (lambda2) is large
        only when gradient energy exists in BOTH directions, so it collapses under
        directional motion blur — a far better motion-blur discriminator than VoL
        (see the blur-gate research fan-in: nodes A+C converge on this). Cheap,
        full-res, CPU; also yields the blur direction.

        Args:
            gray: ``(H, W)`` uint8 grayscale image.

        Returns:
            ``(sharpness, direction_deg)`` — ``sharpness`` is the mean smaller
            structure-tensor eigenvalue (higher = sharp in all directions);
            ``direction_deg`` is the estimated motion-blur axis in ``[0, 180)``
            degrees (perpendicular to the dominant edges), or ``-1`` if undefined.
        """
        g = gray.astype(np.float32)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        # Structure-tensor components, locally averaged over a Gaussian window.
        jxx = cv2.GaussianBlur(gx * gx, (7, 7), 0)
        jyy = cv2.GaussianBlur(gy * gy, (7, 7), 0)
        jxy = cv2.GaussianBlur(gx * gy, (7, 7), 0)
        disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
        lambda2 = 0.5 * (jxx + jyy - disc)  # per-pixel smaller eigenvalue
        sharpness = float(np.mean(lambda2))
        # Global blur direction via the structure-tensor double-angle estimate:
        # the dominant-edge orientation; motion blur runs perpendicular to it.
        sxx, syy, sxy = float(jxx.sum()), float(jyy.sum()), float(jxy.sum())
        if abs(sxx - syy) < 1e-6 and abs(sxy) < 1e-6:
            direction = -1.0
        else:
            edge_axis = 0.5 * np.degrees(np.arctan2(2.0 * sxy, sxx - syy))
            direction = float((edge_axis + 90.0) % 180.0)
        return sharpness, direction

    @staticmethod
    def compute_exposure(gray: np.ndarray) -> Tuple[float, float]:
        """Compute mean and standard deviation of normalised brightness.

        Args:
            gray: ``(H, W)`` uint8 grayscale image.

        Returns:
            ``(mean, std)`` in ``[0, 1]``.
        """
        normed = gray.astype(np.float32) / 255.0
        return float(normed.mean()), float(normed.std())

    @staticmethod
    def compute_phash(gray: np.ndarray, hash_size: int = 8) -> int:
        """Compute a 64-bit perceptual hash (pHash) of a grayscale image.

        Uses DCT-based hashing: resize to ``(hash_size*4, hash_size*4)``,
        compute DCT, keep top-left ``hash_size x hash_size`` coefficients,
        threshold at the median.

        Args:
            gray: ``(H, W)`` uint8 grayscale image.
            hash_size: Side length of the hash grid (hash is ``hash_size^2`` bits).

        Returns:
            Integer perceptual hash.
        """
        resized = cv2.resize(gray, (hash_size * 4, hash_size * 4), interpolation=cv2.INTER_AREA)
        dct_full = cv2.dct(resized.astype(np.float32))
        dct_low = dct_full[:hash_size, :hash_size]
        median = float(np.median(dct_low))
        bits = (dct_low > median).flatten()
        h = 0
        for b in bits:
            h = (h << 1) | int(b)
        return h

    @staticmethod
    def hamming_distance(a: int, b: int) -> int:
        """Count differing bits between two integers."""
        return bin(a ^ b).count("1")

    def compute_coverage(self, gray: np.ndarray) -> float:
        """Estimate spatial coverage as the fraction of image blocks with
        significant gradient energy.

        This filters out frames that are mostly uniform (e.g., blank walls,
        sky-only shots) which provide little value for reconstruction.

        Args:
            gray: ``(H, W)`` uint8 grayscale image.

        Returns:
            Coverage fraction in ``[0, 1]``.
        """
        bs = self.coverage_block_size
        h, w = gray.shape
        if h < bs or w < bs:
            # Image too small for block analysis; assume full coverage
            return 1.0

        # Compute gradient magnitude
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.sqrt(gx * gx + gy * gy)

        # Block-wise mean gradient
        n_rows = h // bs
        n_cols = w // bs
        active_blocks = 0
        total_blocks = n_rows * n_cols

        # Threshold: block is "active" if mean gradient > 10
        gradient_threshold = 10.0
        for r in range(n_rows):
            for c in range(n_cols):
                block = mag[r*bs:(r+1)*bs, c*bs:(c+1)*bs]
                if block.mean() > gradient_threshold:
                    active_blocks += 1

        return active_blocks / max(total_blocks, 1)

    # ------------------------------------------------------------------
    #  Single-frame assessment
    # ------------------------------------------------------------------
    def assess_frame(self, image_path: str | Path) -> FrameQuality:
        """Run all quality checks on a single frame.

        Args:
            image_path: Path to the image file.

        Returns:
            Populated ``FrameQuality`` instance.
        """
        path = Path(image_path)
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        blur = self.compute_blur_score(gray)
        exp_mean, exp_std = self.compute_exposure(gray)
        phash = self.compute_phash(gray)
        coverage = self.compute_coverage(gray)
        dir_sharp, blur_dir = self.compute_directional_sharpness(gray)

        is_under = exp_mean < self.exposure_low
        is_over = exp_mean > self.exposure_high
        is_blurry = blur < self.blur_threshold
        is_low_coverage = coverage < self.coverage_threshold

        # SOTA NR-IQA (optional, GPU). A low perceptual score is the strongest
        # single motion-blur signal we have — weight it as two classical issues.
        neural = -1.0
        neural_issue = 0
        if self.neural_scorer is not None:
            s = self.neural_scorer.score(path)
            if s is not None:
                neural = s
                if s < self.min_neural_score:
                    neural_issue = 2

        # Aggregate recommendation
        issues = sum([is_blurry, is_under, is_over, is_low_coverage]) + neural_issue
        if issues >= 2:
            rec = Recommendation.DROP
        elif issues == 1:
            rec = Recommendation.MARGINAL
        else:
            rec = Recommendation.KEEP

        return FrameQuality(
            path=path,
            blur_score=blur,
            exposure_mean=exp_mean,
            exposure_std=exp_std,
            is_underexposed=is_under,
            is_overexposed=is_over,
            phash=phash,
            coverage_score=coverage,
            dir_sharpness=dir_sharp,
            blur_direction_deg=blur_dir,
            neural_score=neural,
            recommendation=rec,
        )

    # ------------------------------------------------------------------
    #  Batch assessment with duplicate detection
    # ------------------------------------------------------------------
    def assess_directory(
        self,
        frame_dir: str | Path,
        *,
        extensions: Sequence[str] = (
            ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp",
        ),
    ) -> List[FrameQuality]:
        """Assess all frames in a directory, including cross-frame duplicate
        detection.

        Args:
            frame_dir: Directory containing video frames.
            extensions: Accepted image file extensions.

        Returns:
            List of ``FrameQuality`` in filename-sorted order.
        """
        frame_dir = Path(frame_dir)
        paths = sorted(
            p for p in frame_dir.iterdir()
            if p.suffix.lower() in extensions
        )
        if not paths:
            raise FileNotFoundError(f"No image files in {frame_dir}")

        logger.info("Assessing %d frames in %s", len(paths), frame_dir)
        results: List[FrameQuality] = []
        seen_hashes: List[Tuple[int, Path]] = []  # (phash, path)

        for p in paths:
            try:
                fq = self.assess_frame(p)
            except FileNotFoundError:
                logger.warning("Skipping unreadable: %s", p)
                continue

            # Check for duplicates against all prior frames
            for prev_hash, prev_path in seen_hashes:
                dist = self.hamming_distance(fq.phash, prev_hash)
                if dist <= self.duplicate_hash_distance:
                    fq.is_duplicate = True
                    fq.duplicate_of = prev_path
                    if fq.recommendation == Recommendation.KEEP:
                        fq.recommendation = Recommendation.MARGINAL
                    break

            seen_hashes.append((fq.phash, fq.path))
            results.append(fq)

        n_keep = sum(1 for r in results if r.recommendation == Recommendation.KEEP)
        n_marg = sum(1 for r in results if r.recommendation == Recommendation.MARGINAL)
        n_drop = sum(1 for r in results if r.recommendation == Recommendation.DROP)
        logger.info("Quality assessment: %d keep, %d marginal, %d drop",
                     n_keep, n_marg, n_drop)
        return results

    def filter_frames(
        self,
        results: List[FrameQuality],
        *,
        include_marginal: bool = True,
    ) -> List[Path]:
        """Return paths of frames that pass the quality filter.

        Args:
            results: Output of ``assess_directory``.
            include_marginal: Whether to include marginal frames.

        Returns:
            Sorted list of file paths.
        """
        allowed = {Recommendation.KEEP}
        if include_marginal:
            allowed.add(Recommendation.MARGINAL)
        return sorted(r.path for r in results if r.recommendation in allowed)

    # ------------------------------------------------------------------
    #  Per-video quality gate (drop-and-flag)
    # ------------------------------------------------------------------
    def assess_video(
        self,
        frame_dir: str | Path,
        *,
        min_good_frames: int = 60,
        target_frames: Optional[int] = None,
        extensions: Sequence[str] = (
            ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp",
        ),
    ) -> "VideoQualityVerdict":
        """Quality-gate one video's extracted frames; drop the whole video if
        it can't supply enough good frames.

        Policy (per the capture playbook): a handheld video that cannot yield
        ``min_good_frames`` usable (sharp, well-exposed, non-duplicate) frames
        is marked ``too_low_quality`` and rejected so the orchestrator moves on
        to the next video instead of feeding soft footage into SfM/3DGS. This is
        a *callable capability* — the production overseer agent owns the decision
        of what ``min_good_frames`` to require and what to do on rejection
        (skip, re-extract a denser sample, or demand a fresh capture).

        Args:
            frame_dir: Directory of frames extracted from a SINGLE video.
            min_good_frames: Minimum acceptable frames below which the video is
                rejected as too low quality.
            target_frames: If set and the video is accepted, return at most this
                many frames chosen for quality + temporal spread (windowed
                best-of); otherwise return all good frames.
            extensions: Accepted image extensions.

        Returns:
            A populated :class:`VideoQualityVerdict`.
        """
        results = self.assess_directory(frame_dir, extensions=extensions)
        good = [r for r in results
                if r.recommendation == Recommendation.KEEP and not r.is_duplicate]
        good.sort(key=lambda r: r.path.name)  # temporal order by filename

        neural_vals = [r.neural_score for r in results if r.neural_score >= 0]
        median_neural = float(np.median(neural_vals)) if neural_vals else -1.0

        accepted = len(good) >= min_good_frames
        if not accepted:
            return VideoQualityVerdict(
                source=Path(frame_dir),
                accepted=False,
                verdict=VideoVerdict.TOO_LOW_QUALITY,
                n_total=len(results),
                n_good=len(good),
                median_neural=median_neural,
                selected=[],
                reason=(f"only {len(good)} good frames < required {min_good_frames}"
                        f" (median NR-IQA={median_neural:.1f})"),
                recapture_recommended=True,
            )

        # Accepted: optionally thin to target_frames by windowed best-of so the
        # kept frames are both high-quality AND temporally spread (the advantage
        # of video — pick the sharpest frame within each local window).
        selected = good
        if target_frames and target_frames < len(good):
            selected = self._windowed_best(good, target_frames)

        return VideoQualityVerdict(
            source=Path(frame_dir),
            accepted=True,
            verdict=VideoVerdict.ACCEPTED,
            n_total=len(results),
            n_good=len(good),
            median_neural=median_neural,
            selected=[r.path for r in selected],
            reason=f"{len(good)} good frames >= {min_good_frames}; selected {len(selected)}",
            recapture_recommended=(median_neural >= 0 and median_neural < self.min_neural_score),
        )

    @staticmethod
    def _windowed_best(frames: List[FrameQuality], target: int) -> List[FrameQuality]:
        """Pick the single best frame in each of ``target`` consecutive temporal
        windows — quality + even coverage. Ranks by motion-blur-aware directional
        sharpness (structure-tensor lambda2) — the strongest per-frame motion-blur
        signal — with neural NR-IQA then VoL as tiebreaks (blur-gate research)."""
        n = len(frames)
        if target >= n:
            return frames
        edges = np.linspace(0, n, target + 1).round().astype(int)

        def key(fq: FrameQuality) -> Tuple[float, float, float]:
            return (fq.dir_sharpness, fq.neural_score, fq.blur_score)

        out: List[FrameQuality] = []
        for a, b in zip(edges[:-1], edges[1:]):
            window = frames[a:max(a + 1, b)]
            out.append(max(window, key=key))
        return out


class VideoVerdict(str, Enum):
    """Per-video quality-gate outcome."""
    ACCEPTED = "accepted"
    TOO_LOW_QUALITY = "too_low_quality"


@dataclass(slots=True)
class VideoQualityVerdict:
    """Outcome of gating a single video's extracted frames.

    Attributes:
        source: The frame directory (one video's frames) that was assessed.
        accepted: True if the video yielded enough good frames to use.
        verdict: ``accepted`` or ``too_low_quality``.
        n_total: Frames assessed.
        n_good: Frames passing the quality filter (KEEP, non-duplicate).
        median_neural: Median SOTA NR-IQA over the video (-1 if not computed).
        selected: Chosen frame paths (empty when rejected).
        reason: Human-readable explanation, suitable for logging / a flag.
        recapture_recommended: True when the footage is too soft to trust — the
            video was rejected, or its median NR-IQA sits below the usable floor
            even though it passed. The honest "this capture needs a reshoot" flag;
            no gate recovers detail the sensor never recorded.
    """
    source: Path
    accepted: bool
    verdict: VideoVerdict
    n_total: int
    n_good: int
    median_neural: float
    selected: List[Path]
    reason: str
    recapture_recommended: bool = False
