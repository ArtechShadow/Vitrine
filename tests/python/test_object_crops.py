# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.object_crops (ADR-025 D1 / PRD v4 R3).

Synthetic frames + masks only — no GPU, no network, no model weights.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

cv2 = pytest.importorskip("cv2", reason="object_crops needs OpenCV")

from pipeline import object_crops as oc  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic scene helpers
# ---------------------------------------------------------------------------

H, W = 240, 320


def _disk_mask(cy: int, cx: int, r: int, shape=(H, W)) -> np.ndarray:
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def _box_mask(y0: int, x0: int, y1: int, x1: int, shape=(H, W)) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def _textured_frame(sharp: bool = True) -> np.ndarray:
    """A frame with high-frequency texture (sharp) or its blurred twin."""
    rng = np.random.default_rng(0)
    img = (rng.random((H, W, 3)) * 255).astype(np.uint8)
    if not sharp:
        img = cv2.GaussianBlur(img, (31, 31), 12)
    return img


# ---------------------------------------------------------------------------
# Geometry scores
# ---------------------------------------------------------------------------

def test_mask_bbox_and_empty():
    m = _box_mask(10, 20, 60, 100)
    assert oc.mask_bbox(m) == (20, 10, 100, 60)
    assert oc.mask_bbox(np.zeros((H, W), dtype=bool)) is None


def test_fill_ratio_separates_boxes_from_silhouettes():
    box = _box_mask(10, 10, 110, 110)
    disk = _disk_mask(60, 60, 50)
    assert oc.fill_ratio(box, oc.mask_bbox(box)) == pytest.approx(1.0)
    # A disk fills pi/4 of its bbox — well under the boxlike threshold.
    assert oc.fill_ratio(disk, oc.mask_bbox(disk)) == pytest.approx(np.pi / 4, abs=0.05)


def test_centrality_prefers_centered_objects():
    centered = (W // 2 - 20, H // 2 - 20, W // 2 + 20, H // 2 + 20)
    corner = (0, 0, 40, 40)
    assert oc.centrality_score(centered, (H, W)) > oc.centrality_score(corner, (H, W))
    assert oc.centrality_score(centered, (H, W)) == pytest.approx(1.0, abs=0.01)


def test_edge_clearance_penalises_clipped_objects():
    inside = (50, 50, 100, 100)
    touching = (0, 50, 100, 100)   # clipped at the left frame edge
    assert oc.edge_clearance_score(inside, (H, W)) == 1.0
    assert oc.edge_clearance_score(touching, (H, W)) == 0.0


# ---------------------------------------------------------------------------
# Best-frame selection
# ---------------------------------------------------------------------------

def _write_scene(tmp_path: Path, specs: list[tuple[str, np.ndarray, bool]]):
    """specs: (frame_stem, mask, sharp). Returns (frames_dir, perframe_dir)."""
    frames = tmp_path / "frames"
    perframe = tmp_path / "perframe"
    frames.mkdir()
    perframe.mkdir()
    for stem, mask, sharp in specs:
        cv2.imwrite(str(frames / f"{stem}.jpg"), _textured_frame(sharp))
        np.save(str(perframe / f"{stem}.npy"), mask)
    return frames, perframe


def test_select_best_prefers_sharp_centered_complete(tmp_path):
    good = _disk_mask(H // 2, W // 2, 40)
    clipped = _box_mask(0, 0, 80, 60)          # corner + touching edges
    frames, perframe = _write_scene(tmp_path, [
        ("frame_good", good, True),
        ("frame_blurry", good, False),          # same mask, blurred frame
        ("frame_clipped", clipped, True),
    ])
    best = oc.select_best_candidate(perframe, frames)
    assert best is not None
    assert best.frame_stem == "frame_good"
    assert best.sharpness > 0


def test_select_best_ignores_tiny_masks(tmp_path):
    tiny = _disk_mask(H // 2, W // 2, 3)        # ~28 px < min_mask_area_px
    frames, perframe = _write_scene(tmp_path, [("f0", tiny, True)])
    assert oc.select_best_candidate(perframe, frames, min_mask_area_px=400) is None


# ---------------------------------------------------------------------------
# Crop + matte
# ---------------------------------------------------------------------------

def _candidate_for(mask: np.ndarray) -> oc.CropCandidate:
    bbox = oc.mask_bbox(mask)
    return oc.CropCandidate(
        frame_stem="f", frame_path=Path("f.jpg"), mask=mask, bbox=bbox,
        area_px=int(mask.sum()), fill_ratio=oc.fill_ratio(mask, bbox),
    )


def test_crop_and_matte_uses_sam_silhouette_as_alpha():
    mask = _disk_mask(H // 2, W // 2, 40)
    rgba, info = oc.crop_and_matte(_textured_frame(), _candidate_for(mask),
                                   out_size=256, matting="auto")
    assert rgba.shape == (256, 256, 4)
    assert info["matting"] == "mask"
    assert not info["boxlike_mask"]
    # Alpha must partition into object (255) and background (0) regions.
    assert (rgba[..., 3] == 255).any() and (rgba[..., 3] == 0).any()
    # Canvas corners (square padding region) are fully transparent.
    assert rgba[0, 0, 3] == 0


def test_crop_and_matte_flags_boxlike_masks():
    box = _box_mask(60, 80, 180, 240)           # fill_ratio 1.0 — the R1 defect
    rgba, info = oc.crop_and_matte(_textured_frame(), _candidate_for(box),
                                   out_size=128, matting="auto")
    assert info["boxlike_mask"] is True
    # Without rembg installed the crop stays opaque and lineage says so;
    # with rembg it records the fallback matting backend.
    assert info["matting"] in ("rembg", "none-boxlike")


def test_crop_and_matte_upscales_to_out_size():
    mask = _disk_mask(H // 2, W // 2, 20)       # small object -> small native crop
    rgba, info = oc.crop_and_matte(_textured_frame(), _candidate_for(mask),
                                   out_size=1024, matting="mask")
    assert rgba.shape[:2] == (1024, 1024)
    assert info["native_side_px"] < 1024        # genuinely upscaled, recorded


def test_crop_and_matte_rejects_unknown_mode():
    mask = _disk_mask(H // 2, W // 2, 30)
    with pytest.raises(ValueError):
        oc.crop_and_matte(_textured_frame(), _candidate_for(mask), matting="wat")


# ---------------------------------------------------------------------------
# End-to-end single object + manifest
# ---------------------------------------------------------------------------

def test_extract_object_crop_end_to_end(tmp_path):
    mask = _disk_mask(H // 2, W // 2, 40)
    frames, perframe = _write_scene(tmp_path, [("frame_0001", mask, True)])
    out_dir = tmp_path / "crops"

    res = oc.extract_object_crop("brass vessel", 3, perframe, frames, out_dir,
                                 out_size=256)
    assert res is not None
    assert res.crop_path.exists()
    assert res.mask_path.exists()
    prov = res.provenance
    assert prov["source_frame"] == "frame_0001.jpg"
    assert prov["object_id"] == 3
    assert prov["matting"] == "mask"
    assert prov["selection"]["score"] > 0
    # RGBA PNG round-trip keeps the matte.
    rgba = cv2.imread(str(res.crop_path), cv2.IMREAD_UNCHANGED)
    assert rgba.shape[2] == 4

    manifest = oc.write_crops_manifest([res], [], tmp_path / "crops.json")
    data = json.loads(manifest.read_text())
    assert data["version"] == "object_crops.1"
    assert data["crops"][0]["label"] == "brass vessel"
    assert data["crops"][0]["crop"].endswith("0003_brass_vessel.png")


def test_extract_object_crop_returns_none_without_observation(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    cv2.imwrite(str(frames / "f0.jpg"), _textured_frame())
    perframe = tmp_path / "perframe"
    perframe.mkdir()                              # no masks at all
    assert oc.extract_object_crop("ghost", 1, perframe, frames,
                                  tmp_path / "crops") is None
