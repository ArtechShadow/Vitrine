# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.object_candidate_score (ADR-025 D4 / PRD v4 R7).

Pure math — no deps, no I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pipeline import object_candidate_score as ocs  # noqa: E402


def test_aspect_ratio_and_guards():
    assert ocs.aspect_ratio([2.0, 1.0, 0.5]) == pytest.approx(2.0)
    assert ocs.aspect_ratio([1.0]) is None
    assert ocs.aspect_ratio([0.0, 1.0]) is None
    assert ocs.aspect_ratio(None) is None


def test_proportion_score_peaks_on_match_and_is_symmetric():
    assert ocs.proportion_score(1.0, 1.0) == pytest.approx(1.0)
    # 2x too wide and 2x too narrow score identically (log-symmetric).
    wide = ocs.proportion_score(2.0, 1.0)
    narrow = ocs.proportion_score(0.5, 1.0)
    assert wide == pytest.approx(narrow)
    assert wide < 1.0
    # Bigger mismatch -> lower score.
    assert ocs.proportion_score(4.0, 1.0) < wide


def test_proportion_score_neutral_when_unknown():
    assert ocs.proportion_score(None, 1.0) == 0.5
    assert ocs.proportion_score(1.0, None) == 0.5


def test_sanity_score_ramp_and_watertight_bonus():
    assert ocs.sanity_score(0, False) == 0.0
    assert ocs.sanity_score(1000, False) == 0.0        # below floor
    assert ocs.sanity_score(50_000, False) == pytest.approx(1.0)
    assert ocs.sanity_score(500_000, False) == pytest.approx(1.0)  # clamped
    # Watertight adds a bonus but never exceeds 1.0.
    assert ocs.sanity_score(50_000, True) == pytest.approx(1.0)
    assert ocs.sanity_score(20_000, True) > ocs.sanity_score(20_000, False)


def test_score_candidate_prefers_matching_proportions():
    # crop is 1.5 wide:tall; two healthy meshes, one matching, one squashed.
    match = ocs.score_candidate(1, [1.5, 1.0, 1.0], 1.5, 200_000, True)
    squashed = ocs.score_candidate(2, [0.5, 1.0, 1.0], 1.5, 200_000, True)
    assert match.total > squashed.total


def test_score_candidate_degenerate_mesh_scores_zero():
    # Lucky proportions cannot rescue a collapsed mesh.
    cs = ocs.score_candidate(1, [1.5, 1.0, 1.0], 1.5, 10, True)
    assert cs.sanity == 0.0
    assert cs.total == 0.0


def test_crop_aspect_from_provenance():
    prov = {"bbox": [10, 20, 40, 80]}          # w=30 h=60 -> 0.5
    assert ocs.crop_aspect_from_provenance(prov) == pytest.approx(0.5)
    # Falls back to padded_bbox.
    assert ocs.crop_aspect_from_provenance(
        {"padded_bbox": [0, 0, 100, 50]}) == pytest.approx(2.0)
    assert ocs.crop_aspect_from_provenance(None) is None
    assert ocs.crop_aspect_from_provenance({"bbox": [0, 0, 0, 5]}) is None


def test_derive_seeds():
    assert ocs.derive_seeds(42, 3, None) == [42, 43, 44]
    assert ocs.derive_seeds(42, 1, None) == [42]
    assert ocs.derive_seeds(42, 3, [7, 8]) == [7, 8]      # explicit wins
    assert ocs.derive_seeds(42, 0, None) == [42]          # clamps to >=1
