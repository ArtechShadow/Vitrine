# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Best-frame object crop extraction (ADR-025 D1 / PRD v4 R3).

For each SAM3-segmented object, select the best observing source frame, crop
it with padding, matte it, and square-pad it to the generator's native input
size. The resulting crop — never a splat render — is the ONLY conditioning
input the 3D generator receives (ADR-025 supersedes the ADR-015/017 panel
path). This module commits the proven manual dreamlab path (hand-picked SAM
crop -> single-image generator) as a first-class, provenance-tracked stage.

Best-frame score = silhouette_area x sharpness x centrality x edge_clearance.
Centrality + edge clearance are practical stand-ins for frontality until the
R10 pose-solve gives the object a 3D position; the chosen frame's COLMAP pose
is recorded in the provenance either way so the pose-solve can consume it.

Matting policy (``ObjectCropsConfig.matting``):
  auto   — SAM silhouette as alpha; rembg fallback when the mask is box-shaped
           (the R1 boxes-not-silhouettes defect signature).
  mask   — always the SAM mask, even when box-shaped (flagged in lineage).
  rembg  — always rembg on the padded crop.
  none   — opaque crop, ``matting: "none"`` in lineage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

_FRAME_EXTS = (".jpg", ".jpeg", ".png")


@dataclass
class CropCandidate:
    """One frame's observation of an object, with its selection scores."""
    frame_stem: str
    frame_path: Path
    mask: np.ndarray                  # (H, W) bool, frame-resolution silhouette
    bbox: tuple[int, int, int, int]   # x0, y0, x1, y1 (exclusive)
    area_px: int
    fill_ratio: float                 # mask area / bbox area (~1.0 => box, not silhouette)
    sharpness: float = 0.0
    centrality: float = 0.0
    edge_clearance: float = 0.0
    score: float = 0.0


@dataclass
class CropResult:
    """A generator-ready object crop plus full provenance."""
    label: str
    object_id: int
    crop_path: Path
    mask_path: Optional[Path]
    provenance: dict[str, Any] = field(default_factory=dict)


def mask_bbox(mask: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Tight bbox (x0, y0, x1, y1; exclusive) of a boolean mask, or None."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def fill_ratio(mask: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    """Mask area over bbox area. ~1.0 means the 'silhouette' is a filled box."""
    x0, y0, x1, y1 = bbox
    box_area = max(1, (x1 - x0) * (y1 - y0))
    return float(mask[y0:y1, x0:x1].sum()) / box_area


def sharpness_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian — the standard cheap focus measure."""
    import cv2
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def centrality_score(bbox: tuple[int, int, int, int], shape: tuple[int, int]) -> float:
    """1.0 when the bbox centre sits on the image centre, falling to ~0 at a corner."""
    h, w = shape
    cx = (bbox[0] + bbox[2]) / 2.0 / max(1, w)
    cy = (bbox[1] + bbox[3]) / 2.0 / max(1, h)
    # Normalised distance from centre; max possible is sqrt(0.5).
    d = ((cx - 0.5) ** 2 + (cy - 0.5) ** 2) ** 0.5
    return max(0.0, 1.0 - d / (0.5 ** 0.5))


def edge_clearance_score(bbox: tuple[int, int, int, int], shape: tuple[int, int]) -> float:
    """Penalise objects clipped by the frame border (truncated observations).

    1.0 when the bbox is fully inside with margin; 0.0 when it touches an edge.
    """
    h, w = shape
    margin = 0.01 * max(h, w)
    clear = min(bbox[0], bbox[1], w - bbox[2], h - bbox[3])
    return float(np.clip(clear / max(1.0, margin), 0.0, 1.0))


def select_best_candidate(
    perframe_dir: Path,
    frames_dir: Path,
    *,
    candidates: int = 12,
    min_mask_area_px: int = 400,
) -> Optional[CropCandidate]:
    """Pick the best observing frame for one object.

    Two passes: rank every per-frame mask by silhouette area (cheap — masks
    only), then decode just the top ``candidates`` frames to score sharpness /
    centrality / edge clearance.
    """
    import cv2

    frame_by_stem: dict[str, Path] = {}
    for p in frames_dir.iterdir():
        if p.suffix.lower() in _FRAME_EXTS:
            frame_by_stem[p.stem] = p

    ranked: list[CropCandidate] = []
    for mfile in perframe_dir.glob("*.npy"):
        frame_path = frame_by_stem.get(mfile.stem)
        if frame_path is None:
            continue
        mask = np.load(str(mfile))
        mask = (mask[0] if mask.ndim == 3 else mask).astype(bool)
        bbox = mask_bbox(mask)
        if bbox is None:
            continue
        area = int(mask.sum())
        if area < min_mask_area_px:
            continue
        ranked.append(CropCandidate(
            frame_stem=mfile.stem, frame_path=frame_path, mask=mask,
            bbox=bbox, area_px=area, fill_ratio=fill_ratio(mask, bbox),
        ))

    if not ranked:
        return None
    ranked.sort(key=lambda c: c.area_px, reverse=True)

    best: Optional[CropCandidate] = None
    for cand in ranked[:max(1, candidates)]:
        image = cv2.imread(str(cand.frame_path))
        if image is None:
            continue
        h, w = image.shape[:2]
        if cand.mask.shape != (h, w):
            cand.mask = cv2.resize(
                cand.mask.astype(np.uint8), (w, h),
                interpolation=cv2.INTER_NEAREST).astype(bool)
            bbox = mask_bbox(cand.mask)
            if bbox is None:
                continue
            cand.bbox = bbox
        x0, y0, x1, y1 = cand.bbox
        gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        cand.sharpness = sharpness_score(gray)
        cand.centrality = centrality_score(cand.bbox, (h, w))
        cand.edge_clearance = edge_clearance_score(cand.bbox, (h, w))
        area_frac = cand.area_px / float(h * w)
        # Sharpness spans orders of magnitude; log-compress so one razor-sharp
        # sliver cannot outrank a large, centred, complete observation.
        cand.score = (area_frac
                      * float(np.log1p(cand.sharpness))
                      * (0.25 + 0.75 * cand.centrality)
                      * (0.25 + 0.75 * cand.edge_clearance))
        if best is None or cand.score > best.score:
            best = cand
    return best


def _rembg_alpha(crop_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Alpha matte from rembg, or None when rembg is unavailable/fails."""
    try:
        import cv2
        from rembg import remove
        rgba = remove(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
        rgba = np.asarray(rgba)
        if rgba.ndim == 3 and rgba.shape[2] == 4:
            return rgba[:, :, 3]
    except Exception as exc:  # noqa: BLE001 — any failure means "no matte"
        logger.warning("rembg matting unavailable/failed: %s", exc)
    return None


def crop_and_matte(
    image_bgr: np.ndarray,
    cand: CropCandidate,
    *,
    pad_frac: float = 0.12,
    out_size: int = 1024,
    matting: str = "auto",
    boxlike_fill_threshold: float = 0.95,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Cut the padded square RGBA crop for a chosen candidate.

    Returns (rgba, info) where info records the matting method actually used
    and the crop geometry for lineage.
    """
    import cv2

    h, w = image_bgr.shape[:2]
    x0, y0, x1, y1 = cand.bbox
    pad = int(round(pad_frac * max(x1 - x0, y1 - y0)))
    px0, py0 = max(0, x0 - pad), max(0, y0 - pad)
    px1, py1 = min(w, x1 + pad), min(h, y1 + pad)

    crop = image_bgr[py0:py1, px0:px1]
    mask_crop = cand.mask[py0:py1, px0:px1]

    boxlike = cand.fill_ratio >= boxlike_fill_threshold
    method = matting
    alpha: Optional[np.ndarray] = None
    if matting == "auto":
        if boxlike:
            alpha = _rembg_alpha(crop)
            method = "rembg" if alpha is not None else "none-boxlike"
        else:
            alpha = (mask_crop.astype(np.uint8)) * 255
            method = "mask"
    elif matting == "mask":
        alpha = (mask_crop.astype(np.uint8)) * 255
    elif matting == "rembg":
        alpha = _rembg_alpha(crop)
        if alpha is None:
            method = "none-rembg-failed"
    elif matting != "none":
        raise ValueError(f"Unknown matting mode: {matting!r}")

    if alpha is None:
        alpha = np.full(crop.shape[:2], 255, dtype=np.uint8)

    rgba = np.dstack([cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), alpha])

    # Square-pad on a transparent canvas, then upscale to >= out_size if needed
    # (never downscale — native resolution is the whole point of the crop path).
    ch, cw = rgba.shape[:2]
    side = max(ch, cw)
    canvas = np.zeros((side, side, 4), dtype=np.uint8)
    oy, ox = (side - ch) // 2, (side - cw) // 2
    canvas[oy:oy + ch, ox:ox + cw] = rgba
    if side < out_size:
        canvas = cv2.resize(canvas, (out_size, out_size),
                            interpolation=cv2.INTER_LANCZOS4)

    info = {
        "matting": method,
        "boxlike_mask": bool(boxlike),
        "mask_fill_ratio": round(cand.fill_ratio, 4),
        "bbox": [x0, y0, x1, y1],
        "padded_bbox": [px0, py0, px1, py1],
        "native_side_px": int(side),
        "output_side_px": int(max(side, out_size)),
    }
    return canvas, info


def colmap_pose_for_frame(colmap_dir: Optional[Path], frame_stem: str) -> Optional[dict[str, Any]]:
    """Camera pose provenance (COLMAP world-to-camera) for the chosen frame."""
    if colmap_dir is None:
        return None
    try:
        from pipeline.colmap_parser import load_images
        for im in load_images(colmap_dir):
            if Path(im.name).stem == frame_stem:
                return {
                    "image_name": im.name,
                    "camera_id": int(im.camera_id),
                    "quaternion_wxyz": [float(q) for q in im.quaternion],
                    "translation": [float(t) for t in im.translation],
                }
    except Exception as exc:  # noqa: BLE001 — provenance is best-effort
        logger.warning("COLMAP pose lookup failed for '%s': %s", frame_stem, exc)
    return None


def extract_object_crop(
    label: str,
    object_id: int,
    perframe_dir: Path,
    frames_dir: Path,
    out_dir: Path,
    *,
    colmap_dir: Optional[Path] = None,
    pad_frac: float = 0.12,
    out_size: int = 1024,
    candidates: int = 12,
    min_mask_area_px: int = 400,
    matting: str = "auto",
    boxlike_fill_threshold: float = 0.95,
) -> Optional[CropResult]:
    """Full crop path for one object: select best frame -> matte -> persist.

    Returns None when no frame observes the object well enough (the caller
    reports that as a per-object failure — no silent fallback, ADR-025).
    """
    import cv2

    best = select_best_candidate(
        perframe_dir, frames_dir,
        candidates=candidates, min_mask_area_px=min_mask_area_px,
    )
    if best is None:
        return None

    image = cv2.imread(str(best.frame_path))
    if image is None:
        return None

    rgba, info = crop_and_matte(
        image, best, pad_frac=pad_frac, out_size=out_size,
        matting=matting, boxlike_fill_threshold=boxlike_fill_threshold,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    safe = label.replace(" ", "_").replace("/", "_")[:50]
    crop_path = out_dir / f"{object_id:04d}_{safe}.png"
    cv2.imwrite(str(crop_path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    mask_path = out_dir / f"{object_id:04d}_{safe}_mask.npy"
    np.save(str(mask_path), best.mask)

    provenance = {
        "label": label,
        "object_id": int(object_id),
        "source_frame": best.frame_path.name,
        "frame_stem": best.frame_stem,
        "camera_pose": colmap_pose_for_frame(colmap_dir, best.frame_stem),
        "selection": {
            "area_px": best.area_px,
            "sharpness": round(best.sharpness, 2),
            "centrality": round(best.centrality, 4),
            "edge_clearance": round(best.edge_clearance, 4),
            "score": round(best.score, 6),
        },
        **info,
    }
    return CropResult(
        label=label, object_id=int(object_id),
        crop_path=crop_path, mask_path=mask_path, provenance=provenance,
    )


def write_crops_manifest(results: list[CropResult],
                         failures: list[dict[str, Any]],
                         out_path: Path) -> Path:
    """Persist the stage manifest: every crop's provenance + every failure."""
    payload = {
        "version": "object_crops.1",
        "crops": [
            {"crop": str(r.crop_path),
             "mask": str(r.mask_path) if r.mask_path else None,
             **r.provenance}
            for r in results
        ],
        "failures": failures,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
