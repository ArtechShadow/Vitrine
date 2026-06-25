# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene masking for robust reconstruction of imperfect captures.

Builds a per-frame *ignore mask* (moving people + blown-out highlights) and writes it in BOTH the
COLMAP and LichtFeld conventions, so masked pixels are excluded from **SfM feature extraction** AND
from the **3DGS training loss** — absorbing a transient person and clipped highlights without
ghosting/floaters.

Mandated-video reality (2026-06-23): the dreamlab capture is dense-but-blurry, locked-exposure
(some blowout), with a moving person in places. LichtFeld natively supports masks
(`--mask-mode ignore`, per-camera mask) + PPISP/bilateral appearance modelling — this module just
generates the masks and points both consumers at them.

Polarity (both consumers): **255 = keep, 0 = ignore**.
  * COLMAP: `colmap feature_extractor --ImageReader.mask_path <dir>`; the mask for `images/foo.png`
    is read from `<dir>/foo.png.png` (COLMAP appends `.png`); pixel value 0 => ignored.
  * LichtFeld: `--mask-mode ignore` (+ `--invert-masks` if polarity is reversed); per-camera mask
    discovered under `<data_path>/masks/<image_name>`; 0 => excluded from the loss.

Person source is pluggable: pass a `person_mask_fn(bgr) -> bool[H,W]` (e.g. wrapping
`person_remover.PersonRemover` / SAM3); if None, only highlight masking runs (always available,
numpy-only). The same canonical keep-mask is emitted to both layouts so they never diverge.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

PersonMaskFn = Callable[[np.ndarray], np.ndarray]  # BGR uint8 HxWx3 -> bool HxW (True = person)


def highlight_mask(img: np.ndarray, thresh: int = 250, min_frac: float = 0.0) -> np.ndarray:
    """True where a pixel is blown out (all channels >= thresh => clipped, no recoverable detail)."""
    clipped = (img >= thresh).all(axis=2)
    if min_frac and clipped.mean() < min_frac:
        return np.zeros(img.shape[:2], dtype=bool)
    return clipped


def _dilate(mask: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return mask
    try:
        import cv2
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
        return cv2.dilate(mask.astype(np.uint8), k).astype(bool)
    except Exception:
        from scipy import ndimage
        return ndimage.binary_dilation(mask, iterations=px)


def build_keep_mask(img: np.ndarray, *, mask_highlights: bool = True, highlight_thresh: int = 250,
                    person_mask_fn: Optional[PersonMaskFn] = None, dilate_px: int = 8) -> tuple[np.ndarray, dict]:
    """Return (keep_mask uint8 [255=keep,0=ignore], stats). Ignore = person ∪ highlight, dilated."""
    h, w = img.shape[:2]
    ignore = np.zeros((h, w), dtype=bool)
    stats = {"person_frac": 0.0, "highlight_frac": 0.0}
    if person_mask_fn is not None:
        try:
            pm = person_mask_fn(img).astype(bool)
            stats["person_frac"] = float(pm.mean())
            ignore |= pm
        except Exception as e:  # never let a detector failure abort the ingest
            logger.warning("person_mask_fn failed on a frame: %s", e)
    if mask_highlights:
        hm = highlight_mask(img, highlight_thresh)
        stats["highlight_frac"] = float(hm.mean())
        ignore |= hm
    if ignore.any():
        ignore = _dilate(ignore, dilate_px)
    keep = np.where(ignore, 0, 255).astype(np.uint8)
    stats["ignore_frac"] = float((keep == 0).mean())
    return keep, stats


def generate(frames_dir: str | Path, data_path: str | Path, colmap_mask_dir: str | Path, *,
             mask_highlights: bool = True, highlight_thresh: int = 250,
             person_mask_fn: Optional[PersonMaskFn] = None, dilate_px: int = 8,
             exts: tuple[str, ...] = (".png", ".jpg", ".jpeg")) -> dict:
    """Generate keep-masks for every frame and write both conventions.

    Writes:
      * LichtFeld:  <data_path>/masks/<image_name>          (same stem+ext as the image)
      * COLMAP:     <colmap_mask_dir>/<image_name>.png      (COLMAP appends .png)
    Returns a manifest dict (also written to <data_path>/masks/mask_manifest.json).
    """
    import cv2
    frames_dir = Path(frames_dir)
    lfs_masks = Path(data_path) / "masks"; lfs_masks.mkdir(parents=True, exist_ok=True)
    colmap_mask_dir = Path(colmap_mask_dir); colmap_mask_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in exts)
    man = {"n_frames": len(frames), "mask_highlights": mask_highlights, "highlight_thresh": highlight_thresh,
           "person_masking": person_mask_fn is not None, "dilate_px": dilate_px,
           "polarity": "255=keep,0=ignore", "frames": []}
    for fp in frames:
        img = cv2.imread(str(fp))  # BGR
        if img is None:
            logger.warning("unreadable frame %s", fp); continue
        keep, stats = build_keep_mask(img, mask_highlights=mask_highlights, highlight_thresh=highlight_thresh,
                                      person_mask_fn=person_mask_fn, dilate_px=dilate_px)
        cv2.imwrite(str(lfs_masks / fp.name), keep)               # LichtFeld convention
        cv2.imwrite(str(colmap_mask_dir / (fp.name + ".png")), keep)  # COLMAP convention
        man["frames"].append({"name": fp.name, **{k: round(v, 5) for k, v in stats.items()}})
    if man["frames"]:
        ig = np.array([f["ignore_frac"] for f in man["frames"]])
        man["mean_ignore_frac"] = round(float(ig.mean()), 5)
        man["max_ignore_frac"] = round(float(ig.max()), 5)
    (lfs_masks / "mask_manifest.json").write_text(json.dumps(man, indent=1))
    logger.info("scene_masking: %d masks; mean ignore %.1f%% (max %.1f%%) -> %s + %s",
                len(man["frames"]), 100 * man.get("mean_ignore_frac", 0),
                100 * man.get("max_ignore_frac", 0), lfs_masks, colmap_mask_dir)
    return man


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Generate person+highlight ignore-masks (COLMAP + LichtFeld).")
    ap.add_argument("frames_dir"); ap.add_argument("data_path")
    ap.add_argument("--colmap-mask-dir", default=None)
    ap.add_argument("--no-highlights", action="store_true")
    ap.add_argument("--highlight-thresh", type=int, default=250)
    ap.add_argument("--dilate", type=int, default=8)
    ap.add_argument("--people", action="store_true", help="enable person masking via person_remover/SAM3")
    a = ap.parse_args()
    pfn = None
    if a.people:
        try:
            from pipeline.person_remover import PersonRemover
            pr = PersonRemover()
            def pfn(bgr):  # noqa: E306
                dets, _ = pr.detect(bgr)
                m = np.zeros(bgr.shape[:2], bool)
                for d in dets:
                    m |= (d.mask > 127)
                return m
        except Exception as e:
            logger.warning("person masking unavailable (%s); highlights only", e)
    out = generate(a.frames_dir, a.data_path, a.colmap_mask_dir or (Path(a.data_path) / "colmap_masks"),
                   mask_highlights=not a.no_highlights, highlight_thresh=a.highlight_thresh,
                   person_mask_fn=pfn, dilate_px=a.dilate)
    print(json.dumps({k: v for k, v in out.items() if k != "frames"}, indent=1))


if __name__ == "__main__":
    _cli()
