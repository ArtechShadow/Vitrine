# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Directional (motion-blur-aware) sharpness for the frame-ingest quality gate.

Validates the structure-tensor sharpness added per the blur-gate research fan-in:
isotropic variance-of-Laplacian is blind to motion-blur *direction*, so the gate
gains a structure-tensor smaller-eigenvalue (lambda2) signal that (a) drops under
directional motion blur, (b) ranks a sharp frame above a blurred one, (c) is more
discriminating than VoL on a one-axis-degenerate frame, and (d) recovers the blur
axis. Pure-CPU/OpenCV; no GPU or weights required.
"""
import cv2
import numpy as np

from pipeline.frame_quality import FrameQualityAssessor


def _textured(seed: int = 0, size: int = 256) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (size, size), dtype=np.uint8)


def _motion_blur(img: np.ndarray, length: int = 21, angle_deg: float = 0.0) -> np.ndarray:
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1.0
    M = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle_deg, 1.0)
    k = cv2.warpAffine(k, M, (length, length))
    k /= max(k.sum(), 1e-6)
    return cv2.filter2D(img, -1, k)


def test_directional_sharpness_drops_under_motion_blur():
    sharp = _textured()
    blurred = _motion_blur(sharp, length=21, angle_deg=0.0)
    s_sharp, _ = FrameQualityAssessor.compute_directional_sharpness(sharp)
    s_blur, _ = FrameQualityAssessor.compute_directional_sharpness(blurred)
    assert s_sharp > s_blur, (s_sharp, s_blur)
    assert s_blur < 0.7 * s_sharp, (s_sharp, s_blur)


def test_directional_beats_isotropic_on_one_axis_texture():
    """Vertical stripes have strong horizontal gradient but ZERO vertical gradient
    — sharp to VoL, yet directionally degenerate. The directional metric must rank
    isotropic texture above it; VoL cannot make that distinction."""
    size = 256
    stripes = np.zeros((size, size), np.uint8)
    stripes[:, ::4] = 255
    iso = _textured(seed=1)
    s_stripes, _ = FrameQualityAssessor.compute_directional_sharpness(stripes)
    s_iso, _ = FrameQualityAssessor.compute_directional_sharpness(iso)
    assert FrameQualityAssessor.compute_blur_score(stripes) > 0  # VoL sees stripes as "sharp"
    assert s_iso > s_stripes, (s_iso, s_stripes)


def test_blur_direction_is_recovered():
    horiz = _motion_blur(_textured(seed=2), length=21, angle_deg=0.0)  # horizontal smear
    _, dir_deg = FrameQualityAssessor.compute_directional_sharpness(horiz)
    assert dir_deg >= 0.0
    assert min(dir_deg, 180.0 - dir_deg) < 25.0, dir_deg  # ~horizontal axis


def test_assess_frame_populates_directional_fields(tmp_path):
    p = tmp_path / "f.png"
    cv2.imwrite(str(p), cv2.cvtColor(_textured(seed=3), cv2.COLOR_GRAY2BGR))
    fq = FrameQualityAssessor().assess_frame(p)
    assert fq.dir_sharpness > 0.0
    assert 0.0 <= fq.blur_direction_deg < 180.0 or fq.blur_direction_deg == -1.0
