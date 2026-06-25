# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Agentic open-vocabulary object discovery + ``v2g.object.1`` metadata (FR-27).

This module revives the *discovery -> extract -> rich-metadata* loop that the
fixed-concept Stage 6 path lost. Instead of segmenting against a hard-coded
``sam3_concepts`` list, the segment stage can first sample a spread of
representative frames and ask a **pluggable vision overseer** to enumerate the
distinct physical OBJECTS actually present (open vocabulary). The discovered
labels then drive SAM3.

Why a *pluggable* overseer? The project's local reasoner, DiffusionGemma
(:mod:`pipeline.agent_llm`), is **TEXT-ONLY** in its current GGUF build — it
cannot read pixels (see ``agent_llm.py`` module docstring + ADR-013). Visual
triage therefore falls back to the vision-capable ``claude_code`` oversight
backend, mirroring :class:`pipeline.config.OversightConfig`. This module makes
that an explicit seam (:class:`DiscoveryOverseer`) rather than an implicit
fallback:

* ``static``       — no vision; returns the configured ``sam3_concepts`` as-is.
                     Safe default when no overseer is wired (never blocks a run).
* ``claude_code``  — vision-capable agent enumerates objects from frame images.
                     Wired as a *callback* the orchestrator (this very agent, or
                     the web/MCP layer) supplies; there is no autonomous local
                     vision model to call, so absent a callback it WARNs and
                     degrades to ``static``.

The second half of the module is the ``v2g.object.1`` metadata schema and a
writer (:func:`write_objects_v2g`) that MERGES whatever artifacts a run already
produced — size JSON, SAM crops, masks, reconstructed meshes — with the
discovery labels/confidence/description into one record per object.

CLI::

    python -m pipeline.object_discovery dreamlab \
        --root output/dreamlab --out output/dreamlab/objects_v2g.json
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol

logger = logging.getLogger("pipeline.object_discovery")

#: Schema tag stamped on every emitted record (versioned so consumers — UE
#: import, usd_assembler, the web UI — can branch on shape).
V2G_OBJECT_SCHEMA = "v2g.object.1"

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


# ---------------------------------------------------------------------------
# Discovery data model
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredObject:
    """One open-vocabulary object proposal from a vision overseer.

    ``label`` is the canonical concept fed to SAM3; ``aliases`` are alternate
    phrasings (brand names, synonyms) kept for metadata + future re-matching.
    """
    label: str
    confidence: float = 1.0
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    source_frames: list[str] = field(default_factory=list)

    def normalized_label(self) -> str:
        return canonical_key(self.label)


class DiscoveryOverseer(Protocol):
    """Pluggable vision overseer contract.

    Implementations receive absolute paths to representative frames and return
    open-vocabulary :class:`DiscoveredObject` proposals. Implementations MUST
    NOT raise on an empty/unsupported input — return ``[]`` instead, so the
    caller can degrade to the static concept list without crashing the run.
    """

    name: str

    def discover(self, frame_paths: list[str], *,
                 hint_concepts: Optional[list[str]] = None,
                 max_objects: int = 24) -> list[DiscoveredObject]:
        ...


class StaticOverseer:
    """No-vision overseer: echoes the configured concept list.

    This is the always-available fallback. It performs zero image analysis; it
    simply turns the static ``sam3_concepts`` into :class:`DiscoveredObject`
    records (confidence 1.0) so the rest of the pipeline is shape-compatible
    whether or not a real vision model ran.
    """

    name = "static"

    def discover(self, frame_paths: list[str], *,
                 hint_concepts: Optional[list[str]] = None,
                 max_objects: int = 24) -> list[DiscoveredObject]:
        concepts = hint_concepts or []
        return [DiscoveredObject(label=c, confidence=1.0, description="",
                                 source_frames=[])
                for c in concepts[:max_objects]]


class CallbackOverseer:
    """Vision overseer backed by a host-supplied callback.

    The orchestrator (the ``claude_code`` agent driving the run, the web UI, or
    an MCP tool) passes a callable that actually looks at the frames and returns
    proposals. We deliberately do NOT call a local model here: DiffusionGemma is
    text-only, so the only vision-capable overseer in this environment is the
    agent itself. The callback signature is ``(frame_paths) -> list[dict|DiscoveredObject]``.
    """

    name = "callback"

    def __init__(self, callback: Callable[[list[str]], Iterable[Any]],
                 *, label: str = "claude_code") -> None:
        self._callback = callback
        self.name = label

    def discover(self, frame_paths: list[str], *,
                 hint_concepts: Optional[list[str]] = None,
                 max_objects: int = 24) -> list[DiscoveredObject]:
        try:
            raw = self._callback(frame_paths)
        except Exception as exc:  # never crash the run on overseer failure
            logger.warning("discovery callback failed (%s) — degrading to static", exc)
            return []
        out = list(coerce_discoveries(raw))
        return out[:max_objects]


def coerce_discoveries(raw: Iterable[Any]) -> list[DiscoveredObject]:
    """Coerce loose overseer output (dicts / objects) into DiscoveredObject."""
    result: list[DiscoveredObject] = []
    for item in raw or []:
        if isinstance(item, DiscoveredObject):
            result.append(item)
            continue
        if isinstance(item, str):
            result.append(DiscoveredObject(label=item))
            continue
        if isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("concept")
            if not label:
                continue
            result.append(DiscoveredObject(
                label=str(label),
                confidence=float(item.get("confidence", 1.0)),
                description=str(item.get("description", "")),
                aliases=[str(a) for a in (item.get("aliases") or [])],
                source_frames=[str(s) for s in (item.get("source_frames") or [])],
            ))
    return result


# ---------------------------------------------------------------------------
# Frame sampling
# ---------------------------------------------------------------------------

def sample_representative_frames(frames_dir: str | Path, n: int = 8) -> list[str]:
    """Return ``n`` frame paths spread evenly across the (sorted) sequence.

    Evenly-spaced sampling (not just first/last) gives a vision overseer
    coverage of the whole walkthrough so transient / partially-occluded objects
    are still seen. Returns absolute string paths.
    """
    frames_path = Path(frames_dir)
    if not frames_path.is_dir():
        return []
    frames = sorted(
        p for p in frames_path.iterdir()
        if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not frames:
        return []
    if n >= len(frames):
        return [str(p.resolve()) for p in frames]
    # Even spread including both endpoints.
    step = (len(frames) - 1) / (n - 1) if n > 1 else 0
    idxs = sorted({int(round(i * step)) for i in range(n)})
    return [str(frames[i].resolve()) for i in idxs]


# ---------------------------------------------------------------------------
# Discovery orchestration
# ---------------------------------------------------------------------------

def select_overseer(backend: str,
                    callback: Optional[Callable[[list[str]], Iterable[Any]]] = None
                    ) -> DiscoveryOverseer:
    """Resolve a backend name + optional callback into an overseer instance.

    ``static`` -> :class:`StaticOverseer`. Any vision backend (``claude_code``,
    ``diffusiongemma``, …) requires a host-supplied vision callback; without one
    we cannot see pixels in-process (DiffusionGemma is text-only), so we WARN and
    return the static overseer.
    """
    backend = (backend or "static").strip().lower()
    if backend == "static":
        return StaticOverseer()
    if callback is not None:
        return CallbackOverseer(callback, label=backend)
    if backend == "diffusiongemma":
        logger.warning(
            "discovery overseer 'diffusiongemma' requested but it is TEXT-ONLY "
            "(agent_llm.py) — cannot read frames; degrading to static.")
    else:
        logger.warning(
            "discovery overseer %r requested but no vision callback was supplied "
            "— degrading to static (the local reasoner cannot see pixels).",
            backend)
    return StaticOverseer()


def discover_objects(frames_dir: str | Path, *,
                     overseer: Optional[DiscoveryOverseer] = None,
                     hint_concepts: Optional[list[str]] = None,
                     num_frames: int = 8,
                     min_confidence: float = 0.3,
                     max_objects: int = 24) -> tuple[list[str], list[DiscoveredObject]]:
    """Run open-vocab discovery and return ``(concepts, discoveries)``.

    ``concepts`` is the de-duplicated, confidence-filtered list of labels to
    hand to SAM3 (replacing the static list). ``discoveries`` are the full
    proposal records for downstream metadata. Falls back to ``hint_concepts``
    when discovery yields nothing.
    """
    overseer = overseer or StaticOverseer()
    frame_paths = sample_representative_frames(frames_dir, n=num_frames)
    if not frame_paths:
        logger.warning("no frames in %s — using hint concepts", frames_dir)
        return list(hint_concepts or []), []

    discoveries = overseer.discover(
        frame_paths, hint_concepts=hint_concepts, max_objects=max_objects)

    kept: list[DiscoveredObject] = []
    seen: set[str] = set()
    for d in discoveries:
        if d.confidence < min_confidence:
            continue
        key = d.normalized_label()
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(d)

    if not kept:
        logger.warning(
            "discovery (overseer=%s) yielded no objects — falling back to %d "
            "hint concepts", getattr(overseer, "name", "?"),
            len(hint_concepts or []))
        return list(hint_concepts or []), []

    concepts = [d.label for d in kept[:max_objects]]
    logger.info("discovery (overseer=%s) -> %d concepts: %s",
                getattr(overseer, "name", "?"), len(concepts), concepts)
    return concepts, kept


# ---------------------------------------------------------------------------
# v2g.object.1 metadata schema + merge writer
# ---------------------------------------------------------------------------

@dataclass
class ObjectRecord:
    """One ``v2g.object.1`` record.

    A single object's full provenance: what it is (label/aliases/confidence/
    description from discovery), how big it is (size + footprint + floor
    position, in centimetres), and where every artifact lives (the frames it was
    seen in, its SAM mask, its image crop, and its reconstructed mesh).
    """
    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    confidence: float = 1.0
    description: str = ""
    size_cm: Optional[list[float]] = None          # [w, d, h] bbox in cm
    footprint_cm: Optional[list[float]] = None      # [w, d] floor footprint in cm
    floor_position_cm: Optional[list[float]] = None  # [x, y, z] of base centre in cm
    source_frames: list[str] = field(default_factory=list)
    mask_path: Optional[str] = None
    crop_path: Optional[str] = None
    recon_path: Optional[str] = None
    schema: str = V2G_OBJECT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_key(label: str) -> str:
    """Normalise a label to an artifact-filename key.

    'vacuum cleaner' / 'Vacuum-Cleaner' -> 'vacuum_cleaner', matching how
    obj_crops / objects_fbx files are named.
    """
    s = (label or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _index_by_key(paths: Iterable[Path]) -> dict[str, Path]:
    """Map ``canonical_key(stem)`` -> path for a set of artifact files."""
    out: dict[str, Path] = {}
    for p in paths:
        out.setdefault(canonical_key(p.stem), p)
    return out


def build_object_records(
    discoveries: list[DiscoveredObject],
    *,
    sizes: Optional[dict[str, dict[str, Any]]] = None,
    crops: Optional[dict[str, Path]] = None,
    masks: Optional[dict[str, Path]] = None,
    recons: Optional[dict[str, Path]] = None,
    floor_positions: Optional[dict[str, list[float]]] = None,
) -> list[ObjectRecord]:
    """Merge discovery proposals with per-key artifact maps into records.

    Each map is keyed by :func:`canonical_key`. To bridge open-vocab discovery
    phrasing ('wet and dry vacuum') and the legacy fixed-pipeline artifact
    filenames ('vacuum_cleaner.png'), each object is matched against its primary
    label key first and then its alias keys — the first map containing a key
    wins. Missing artifacts leave the corresponding field ``None`` (honest about
    what a run actually produced).
    """
    sizes = sizes or {}
    crops = crops or {}
    masks = masks or {}
    recons = recons or {}
    floor_positions = floor_positions or {}

    def _lookup(mapping: dict, keys: list[str]):
        for k in keys:
            if k in mapping:
                return mapping[k], k
        return None, None

    records: list[ObjectRecord] = []
    for i, d in enumerate(discoveries, start=1):
        # Candidate keys: primary label, then each alias (legacy filenames).
        keys = [d.normalized_label()] + [canonical_key(a) for a in d.aliases]
        keys = [k for k in dict.fromkeys(keys) if k]  # dedup, drop empties

        sz, _ = _lookup(sizes, keys)
        sz = sz or {}
        height = sz.get("height_cm")
        footprint = sz.get("footprint_cm")
        size_cm = None
        if footprint and height is not None:
            size_cm = [float(footprint[0]), float(footprint[1]), float(height)]

        mask, _ = _lookup(masks, keys)
        crop, _ = _lookup(crops, keys)
        recon, _ = _lookup(recons, keys)
        floor, _ = _lookup(floor_positions, keys)

        records.append(ObjectRecord(
            id=f"obj_{i:03d}",
            label=d.label,
            aliases=list(d.aliases),
            confidence=round(float(d.confidence), 3),
            description=d.description,
            size_cm=size_cm,
            footprint_cm=[float(x) for x in footprint] if footprint else None,
            floor_position_cm=floor,
            source_frames=list(d.source_frames),
            mask_path=str(mask) if mask is not None else None,
            crop_path=str(crop) if crop is not None else None,
            recon_path=str(recon) if recon is not None else None,
        ))
    return records


def discover_run_artifacts(root: str | Path) -> dict[str, Any]:
    """Scan a pipeline run directory for the artifacts the writer merges.

    Looks in the conventional locations a Vitrine run produces:
      * ``objects_fbx_scaled/object_meta.json``  -> sizes
      * ``obj_crops/<key>.png``                  -> crops
      * ``sam3_masks/mask_*.npy``                -> masks (by index, see below)
      * ``output/hull_e2e/<key>_hull.glb`` and
        ``objects_fbx_scaled/<key>.fbx``         -> recon paths (fbx preferred)

    Returns a dict of per-key maps suitable for :func:`build_object_records`.
    SAM masks are stored by numeric index (``mask_0001.npy``) with no label in
    the filename, so they are returned separately under ``masks_dir`` for the
    caller to associate by discovery order if desired.
    """
    root = Path(root)
    out: dict[str, Any] = {"sizes": {}, "crops": {}, "recons": {},
                           "masks_dir": None}

    meta_path = root / "objects_fbx_scaled" / "object_meta.json"
    if meta_path.is_file():
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            out["sizes"] = {canonical_key(k): v for k, v in raw.items()}
        except (ValueError, OSError) as exc:
            logger.warning("failed to read %s: %s", meta_path, exc)

    crops_dir = root / "obj_crops"
    if crops_dir.is_dir():
        out["crops"] = _index_by_key(
            p for p in crops_dir.iterdir()
            if p.suffix.lower() in IMAGE_SUFFIXES)

    # Recon: prefer scaled FBX (the UE deliverable), else hull GLB.
    recons: dict[str, Path] = {}
    hull_dir = root / "output" / "hull_e2e"
    if hull_dir.is_dir():
        for p in hull_dir.glob("*_hull.glb"):
            recons[canonical_key(p.stem.replace("_hull", ""))] = p
    fbx_dir = root / "objects_fbx_scaled"
    if fbx_dir.is_dir():
        for p in fbx_dir.glob("*.fbx"):
            recons[canonical_key(p.stem)] = p  # fbx wins over hull
    out["recons"] = recons

    masks_dir = root / "sam3_masks"
    if masks_dir.is_dir():
        out["masks_dir"] = str(masks_dir)
    return out


def write_objects_v2g(records: list[ObjectRecord], out_path: str | Path,
                      *, source_frames: Optional[list[str]] = None,
                      overseer: str = "static") -> Path:
    """Write merged ``v2g.object.1`` records to a JSON document.

    The envelope carries the schema tag, the overseer that produced the labels,
    and the representative frames used, so the artifact is self-describing.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": V2G_OBJECT_SCHEMA,
        "overseer": overseer,
        "object_count": len(records),
        "source_frames": list(source_frames or []),
        "objects": [r.to_dict() for r in records],
    }
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    logger.info("wrote %d %s records -> %s", len(records),
                V2G_OBJECT_SCHEMA, out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI (build objects_v2g.json from an existing run, e.g. dreamlab)
# ---------------------------------------------------------------------------

#: Legacy fixed-concept order the dreamlab SAM3 masks were saved in
#: (mask_0001..0008), per ``output/dreamlab/objects.log``. Used to associate the
#: index-named masks with concept keys; live runs instead pass an explicit
#: label->mask map from the segment stage.
DREAMLAB_MASK_ORDER = [
    "vacuum_cleaner", "ladder", "workbench", "table",
    "mitre_saw", "toolbox", "chair", "dartboard",
]


def _build_from_run(root: str | Path, discoveries: list[DiscoveredObject],
                    *, overseer: str = "static",
                    mask_order: Optional[list[str]] = None) -> list[ObjectRecord]:
    arts = discover_run_artifacts(root)
    # Associate index-named SAM masks with their KNOWN concept order (not the
    # discovery order — those differ). Keyed by concept so build_object_records
    # can join via label/alias. Skips silently if the order is unknown.
    masks: dict[str, Path] = {}
    masks_dir = arts.get("masks_dir")
    if masks_dir and mask_order:
        mask_files = sorted(Path(masks_dir).glob("mask_*.npy"))
        for concept_key, mp in zip(mask_order, mask_files):
            masks[canonical_key(concept_key)] = mp
    return build_object_records(
        discoveries,
        sizes=arts["sizes"], crops=arts["crops"],
        masks=masks, recons=arts["recons"],
    )


def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="object_discovery CLI")
    parser.add_argument("preset", nargs="?", default="dreamlab")
    parser.add_argument("--root", default="output/dreamlab")
    parser.add_argument("--discoveries", default="",
                        help="JSON file of discovery records (label/confidence/"
                             "description); omit to use the built-in dreamlab list.")
    parser.add_argument("--out", default="output/dreamlab/objects_v2g.json")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    mask_order = None
    source_frames: list[str] = []
    if args.discoveries:
        raw = json.loads(Path(args.discoveries).read_text(encoding="utf-8"))
        discoveries = coerce_discoveries(raw)
    else:
        from pipeline._dreamlab_discovery import (
            DREAMLAB_DISCOVERIES, DREAMLAB_FRAMES,
        )
        discoveries = coerce_discoveries(DREAMLAB_DISCOVERIES)
        mask_order = DREAMLAB_MASK_ORDER
        source_frames = list(DREAMLAB_FRAMES)

    records = _build_from_run(args.root, discoveries, overseer="claude_code",
                              mask_order=mask_order)
    write_objects_v2g(records, args.out, source_frames=source_frames,
                      overseer="claude_code")
    print(json.dumps({"object_count": len(records), "out": args.out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
