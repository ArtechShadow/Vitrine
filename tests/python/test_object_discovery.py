# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.object_discovery — open-vocab discovery + the
``v2g.object.1`` metadata writer.

No network, no GPU, no SAM3: the discovery overseer is exercised via the static
backend and a fake vision callback, and the metadata writer is exercised against
a synthetic run directory laid out like a real Vitrine run (object_meta.json,
obj_crops/, sam3_masks/, output/hull_e2e/, objects_fbx_scaled/).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pipeline import object_discovery as od  # noqa: E402


# ---------------------------------------------------------------------------
# canonical_key
# ---------------------------------------------------------------------------

def test_canonical_key_normalises_to_artifact_filenames():
    assert od.canonical_key("Vacuum Cleaner") == "vacuum_cleaner"
    assert od.canonical_key("wet and dry vacuum") == "wet_and_dry_vacuum"
    assert od.canonical_key("  Mitre-Saw!! ") == "mitre_saw"
    assert od.canonical_key("") == ""


# ---------------------------------------------------------------------------
# coerce_discoveries
# ---------------------------------------------------------------------------

def test_coerce_discoveries_accepts_dicts_strings_and_objects():
    raw = [
        "chair",
        {"label": "ladder", "confidence": 0.9, "description": "step ladder",
         "aliases": ["step ladder"]},
        {"name": "toolbox", "confidence": 0.8},   # 'name' alias key
        od.DiscoveredObject(label="vacuum", confidence=0.7),
        {"no_label_here": 1},                      # skipped
    ]
    out = od.coerce_discoveries(raw)
    labels = [d.label for d in out]
    assert labels == ["chair", "ladder", "toolbox", "vacuum"]
    assert out[1].aliases == ["step ladder"]
    assert out[2].confidence == 0.8


# ---------------------------------------------------------------------------
# frame sampling
# ---------------------------------------------------------------------------

def test_sample_representative_frames_spreads_across_sequence(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    for i in range(1, 101):
        (imgs / f"frame_{i:05d}.png").write_bytes(b"x")
    got = od.sample_representative_frames(imgs, n=5)
    names = [Path(p).name for p in got]
    # Endpoints included; evenly spread.
    assert names[0] == "frame_00001.png"
    assert names[-1] == "frame_00100.png"
    assert len(names) == 5


def test_sample_representative_frames_handles_missing_dir(tmp_path):
    assert od.sample_representative_frames(tmp_path / "nope", n=8) == []


# ---------------------------------------------------------------------------
# overseer selection + discovery
# ---------------------------------------------------------------------------

def test_static_overseer_echoes_hint_concepts(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    (imgs / "frame_00001.png").write_bytes(b"x")
    concepts, discoveries = od.discover_objects(
        imgs, overseer=od.StaticOverseer(),
        hint_concepts=["chair", "ladder"])
    assert concepts == ["chair", "ladder"]
    assert {d.label for d in discoveries} == {"chair", "ladder"}


def test_select_overseer_degrades_to_static_without_callback():
    ov = od.select_overseer("claude_code", callback=None)
    assert isinstance(ov, od.StaticOverseer)


def test_select_overseer_uses_callback_when_supplied():
    ov = od.select_overseer("claude_code", callback=lambda paths: [])
    assert isinstance(ov, od.CallbackOverseer)
    assert ov.name == "claude_code"


def test_discover_objects_with_vision_callback_filters_and_dedups(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    for i in range(1, 9):
        (imgs / f"frame_{i:05d}.png").write_bytes(b"x")

    def fake_vision(frame_paths):
        # high-confidence, a dup, and a below-threshold proposal
        return [
            {"label": "Workbench", "confidence": 0.95, "description": "bench"},
            {"label": "workbench", "confidence": 0.6},   # dup -> dropped
            {"label": "fan", "confidence": 0.1},          # below threshold -> dropped
            {"label": "ladder", "confidence": 0.8},
        ]

    ov = od.select_overseer("claude_code", callback=fake_vision)
    concepts, discoveries = od.discover_objects(
        imgs, overseer=ov, hint_concepts=["x"], min_confidence=0.3)
    assert concepts == ["Workbench", "ladder"]
    assert len(discoveries) == 2


def test_discover_objects_falls_back_to_hints_on_empty(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    (imgs / "frame_00001.png").write_bytes(b"x")
    ov = od.select_overseer("claude_code", callback=lambda p: [])
    concepts, discoveries = od.discover_objects(
        imgs, overseer=ov, hint_concepts=["fallback"])
    assert concepts == ["fallback"]
    assert discoveries == []


def test_callback_overseer_never_raises_on_bad_callback(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    (imgs / "frame_00001.png").write_bytes(b"x")

    def boom(paths):
        raise RuntimeError("vision model exploded")

    ov = od.CallbackOverseer(boom, label="claude_code")
    concepts, discoveries = od.discover_objects(
        imgs, overseer=ov, hint_concepts=["safe"])
    assert concepts == ["safe"]
    assert discoveries == []


# ---------------------------------------------------------------------------
# v2g.object.1 metadata writer (the core deliverable)
# ---------------------------------------------------------------------------

def _make_run(tmp_path) -> Path:
    """Lay out a synthetic run dir mirroring a real dreamlab run."""
    root = tmp_path / "run"
    (root / "objects_fbx_scaled").mkdir(parents=True)
    (root / "obj_crops").mkdir(parents=True)
    (root / "sam3_masks").mkdir(parents=True)
    (root / "output" / "hull_e2e").mkdir(parents=True)

    meta = {
        "chair": {"height_cm": 59.6, "footprint_cm": [82.7, 95.0]},
        "vacuum_cleaner": {"height_cm": 28.0, "footprint_cm": [115.0, 98.6]},
    }
    (root / "objects_fbx_scaled" / "object_meta.json").write_text(
        json.dumps(meta), encoding="utf-8")

    (root / "obj_crops" / "chair.png").write_bytes(b"png")
    (root / "obj_crops" / "vacuum_cleaner.png").write_bytes(b"png")

    (root / "objects_fbx_scaled" / "chair.fbx").write_bytes(b"fbx")
    (root / "output" / "hull_e2e" / "chair_hull.glb").write_bytes(b"glb")
    (root / "output" / "hull_e2e" / "vacuum_cleaner_hull.glb").write_bytes(b"glb")

    (root / "sam3_masks" / "mask_0001.npy").write_bytes(b"npy")
    (root / "sam3_masks" / "mask_0002.npy").write_bytes(b"npy")
    return root


def test_discover_run_artifacts_finds_sizes_crops_recons(tmp_path):
    root = _make_run(tmp_path)
    arts = od.discover_run_artifacts(root)
    assert set(arts["sizes"]) == {"chair", "vacuum_cleaner"}
    assert "chair" in arts["crops"]
    # FBX preferred over hull GLB for the recon path.
    assert arts["recons"]["chair"].suffix == ".fbx"
    # vacuum has only a hull GLB.
    assert arts["recons"]["vacuum_cleaner"].suffix == ".glb"
    assert arts["masks_dir"].endswith("sam3_masks")


def test_build_object_records_merges_all_sources(tmp_path):
    root = _make_run(tmp_path)
    arts = od.discover_run_artifacts(root)
    discoveries = [
        od.DiscoveredObject(label="chair", confidence=0.86,
                            description="wooden dining chair",
                            aliases=["dining chair"],
                            source_frames=["frame_01440.png"]),
        od.DiscoveredObject(label="vacuum cleaner", confidence=0.94,
                            description="wet/dry shop vac"),
        od.DiscoveredObject(label="dartboard", confidence=0.92),  # no artifacts
    ]
    records = od.build_object_records(
        discoveries, sizes=arts["sizes"], crops=arts["crops"],
        recons=arts["recons"])

    by_label = {r.label: r for r in records}
    chair = by_label["chair"]
    assert chair.id == "obj_001"
    assert chair.schema == od.V2G_OBJECT_SCHEMA
    assert chair.size_cm == [82.7, 95.0, 59.6]      # [w, d, h]
    assert chair.footprint_cm == [82.7, 95.0]
    assert chair.crop_path.endswith("chair.png")
    assert chair.recon_path.endswith("chair.fbx")
    assert chair.aliases == ["dining chair"]
    assert chair.confidence == 0.86

    # vacuum cleaner: label normalises to vacuum_cleaner to hit artifacts.
    vac = by_label["vacuum cleaner"]
    assert vac.size_cm == [115.0, 98.6, 28.0]
    assert vac.recon_path.endswith("vacuum_cleaner_hull.glb")

    # dartboard: discovered but no merged artifacts -> honest None fields.
    dart = by_label["dartboard"]
    assert dart.size_cm is None
    assert dart.crop_path is None
    assert dart.recon_path is None


def test_build_object_records_bridges_openvocab_label_to_legacy_filenames(tmp_path):
    """Open-vocab phrasing ('wet and dry vacuum') must still hit legacy
    'vacuum_cleaner.*' artifacts via its aliases."""
    root = _make_run(tmp_path)
    arts = od.discover_run_artifacts(root)
    discoveries = [
        od.DiscoveredObject(
            label="wet and dry vacuum", confidence=0.94,
            aliases=["vacuum cleaner", "shop vac"]),  # alias -> vacuum_cleaner
    ]
    records = od.build_object_records(
        discoveries, sizes=arts["sizes"], crops=arts["crops"],
        recons=arts["recons"])
    rec = records[0]
    assert rec.label == "wet and dry vacuum"        # discovery label preserved
    assert rec.size_cm == [115.0, 98.6, 28.0]        # matched via alias
    assert rec.crop_path.endswith("vacuum_cleaner.png")
    assert rec.recon_path.endswith("vacuum_cleaner_hull.glb")


def test_write_objects_v2g_emits_versioned_envelope(tmp_path):
    root = _make_run(tmp_path)
    arts = od.discover_run_artifacts(root)
    discoveries = [
        od.DiscoveredObject(label="chair", confidence=0.86,
                            source_frames=["frame_01440.png"]),
    ]
    records = od.build_object_records(
        discoveries, sizes=arts["sizes"], crops=arts["crops"],
        recons=arts["recons"])
    out = root / "objects_v2g.json"
    od.write_objects_v2g(records, out, source_frames=["frame_01440.png"],
                         overseer="claude_code")

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == "v2g.object.1"
    assert doc["overseer"] == "claude_code"
    assert doc["object_count"] == 1
    assert doc["source_frames"] == ["frame_01440.png"]
    assert doc["objects"][0]["label"] == "chair"
    assert doc["objects"][0]["schema"] == "v2g.object.1"


def test_writer_roundtrips_record_fields(tmp_path):
    """Every documented v2g.object.1 field survives to JSON."""
    rec = od.ObjectRecord(
        id="obj_001", label="ladder", aliases=["step ladder"], confidence=0.95,
        description="aluminium step ladder", size_cm=[117.5, 96.8, 210.0],
        footprint_cm=[117.5, 96.8], floor_position_cm=[1.2, 0.0, 3.4],
        source_frames=["frame_00480.png"], mask_path="m.npy",
        crop_path="c.png", recon_path="r.fbx")
    out = tmp_path / "one.json"
    od.write_objects_v2g([rec], out)
    obj = json.loads(out.read_text(encoding="utf-8"))["objects"][0]
    for fld in ("id", "label", "aliases", "confidence", "description",
                "size_cm", "footprint_cm", "floor_position_cm", "source_frames",
                "mask_path", "crop_path", "recon_path", "schema"):
        assert fld in obj, f"missing field {fld}"
