# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Candidate scoring for best-of-N object generation (ADR-025 D4 / PRD v4 R7).

When ``trellis2.best_of_n > 1`` the pipeline generates several seed re-rolls of
an object and keeps the best. "Best" here is a deliberately MODEST, honest
signal — a front-silhouette proxy, not a full 3D quality metric:

1. **Proportion agreement** — the generated mesh's front-face aspect ratio
   (width/height) versus the crop's observed silhouette aspect ratio. A good
   reconstruction should have the proportions the camera actually saw; a seed
   that hallucinates a squashed or stretched body scores lower. Scale-invariant
   and symmetric (2× too wide is penalised like 2× too narrow).
2. **Mesh sanity** — degenerate meshes (too few faces) are penalised; a mild
   bonus for watertightness.

This does NOT directly detect backside hallucination (that needs true
multi-view scoring — future work). It selects, among N seeds, the one most
consistent with the single observation we have, and records every candidate's
score in the winner's lineage so a human / the R9 eval can review the field.

Pure: no I/O, no numpy, no pxr. Unit-tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

# Face-count sanity band (a TRELLIS.2 object is ~100k–600k faces after remesh;
# well below the floor means the shape stage collapsed).
_FACE_FLOOR = 5_000
_FACE_HEALTHY = 50_000


@dataclass
class CandidateScore:
    """Score breakdown for one generated candidate (all in [0, 1] except total)."""
    seed: int
    proportion: float
    sanity: float
    total: float
    mesh_aspect: float
    crop_aspect: float


def aspect_ratio(extent_xy: Sequence[float] | None) -> float | None:
    """width/height from a 2-or-3 component extent, or None if unusable."""
    if not extent_xy or len(extent_xy) < 2:
        return None
    w, h = float(extent_xy[0]), float(extent_xy[1])
    if w <= 0.0 or h <= 0.0:
        return None
    return w / h


def proportion_score(mesh_aspect: float | None, crop_aspect: float | None) -> float:
    """1.0 when the mesh's front aspect matches the crop's, decaying symmetrically.

    Uses |log(ratio)| so the penalty is scale-invariant and symmetric. When
    either aspect is unknown the score is a neutral 0.5 (no evidence either way)
    so scoring degrades to mesh sanity rather than guessing.
    """
    if mesh_aspect is None or crop_aspect is None:
        return 0.5
    disagreement = abs(math.log(mesh_aspect / crop_aspect))
    return 1.0 / (1.0 + disagreement)


def sanity_score(face_count: int, watertight: bool) -> float:
    """Mesh-health score: ramps 0→1 across the face-count floor, +watertight bonus.

    A degenerate mesh (at/below the floor) scores 0 regardless of watertightness
    — a broken shape is broken even if it happens to be closed.
    """
    if face_count <= _FACE_FLOOR:
        return 0.0
    base = min(1.0, (face_count - _FACE_FLOOR) / (_FACE_HEALTHY - _FACE_FLOOR))
    base = max(base, 0.1)                       # non-degenerate floor
    return min(1.0, base + (0.1 if watertight else 0.0))


def score_candidate(
    seed: int,
    mesh_extent: Sequence[float] | None,
    crop_aspect: float | None,
    face_count: int,
    watertight: bool = False,
) -> CandidateScore:
    """Combine proportion agreement and mesh sanity into one score.

    ``mesh_extent`` is the generated mesh's bbox size (x=width, y=height in the
    Y-up export front view). ``crop_aspect`` is width/height of the observed
    silhouette. A degenerate mesh (sanity 0) scores 0 regardless of proportion.
    """
    m_aspect = aspect_ratio(mesh_extent)
    prop = proportion_score(m_aspect, crop_aspect)
    san = sanity_score(face_count, watertight)
    # Sanity gates the result (a broken mesh with lucky proportions is still
    # broken); proportion then ranks the healthy candidates.
    total = san * (0.5 + 0.5 * prop)
    return CandidateScore(
        seed=seed, proportion=round(prop, 4), sanity=round(san, 4),
        total=round(total, 4),
        mesh_aspect=round(m_aspect, 4) if m_aspect else 0.0,
        crop_aspect=round(crop_aspect, 4) if crop_aspect else 0.0,
    )


def crop_aspect_from_provenance(provenance: dict | None) -> float | None:
    """width/height of the observed silhouette from an object_crops provenance.

    Prefers the tight ``bbox`` (the object's real proportions); falls back to
    the padded bbox. Returns None when neither is present.
    """
    if not provenance:
        return None
    for key in ("bbox", "padded_bbox"):
        box = provenance.get(key)
        if box and len(box) == 4:
            w = float(box[2]) - float(box[0])
            h = float(box[3]) - float(box[1])
            if w > 0 and h > 0:
                return w / h
    return None


def derive_seeds(base_seed: int, n: int, explicit: Sequence[int] | None) -> list[int]:
    """The seed list for a best-of-N run: explicit if given, else base + offsets."""
    if explicit:
        return list(explicit)[:max(1, n)]
    return [base_seed + i for i in range(max(1, n))]
