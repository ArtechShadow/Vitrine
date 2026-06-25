# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.view_completer.

All HTTP calls and PIL reads are mocked so these tests run without GPU,
network, or ComfyUI.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure pipeline package is importable via src/.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import numpy as np

from pipeline.view_completer import (
    ViewCompleter,
    ViewCompletionResult,
    CompletedView,
    _VIEW_GEOMETRY,
)

# ---------------------------------------------------------------------------
# Helpers for synthetic PIL images
# ---------------------------------------------------------------------------

try:
    from PIL import Image as _PIL_Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _make_rgba_png(tmp_path: Path, name: str, *, alpha_value: int) -> Path:
    """Write a solid RGBA PNG where the alpha channel is uniformly alpha_value."""
    if not _HAS_PIL:
        pytest.skip("Pillow not available")
    arr = np.zeros((64, 64, 4), dtype=np.uint8)
    arr[..., :3] = 128  # grey RGB
    arr[..., 3] = alpha_value
    img = _PIL_Image.fromarray(arr, mode="RGBA")
    p = tmp_path / name
    img.save(str(p))
    return p


def _make_rgb_png(tmp_path: Path, name: str, *, bg: tuple = (0, 0, 0)) -> Path:
    """Write a solid RGB PNG (no alpha) with the given background colour."""
    if not _HAS_PIL:
        pytest.skip("Pillow not available")
    arr = np.full((64, 64, 3), bg, dtype=np.uint8)
    img = _PIL_Image.fromarray(arr, mode="RGB")
    p = tmp_path / name
    img.save(str(p))
    return p


# ---------------------------------------------------------------------------
# coverage() tests
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_high_alpha_returns_high_fraction(self, tmp_path):
        p = _make_rgba_png(tmp_path, "opaque.png", alpha_value=255)
        c = ViewCompleter.coverage(p)
        assert c > 0.9, f"expected >0.9, got {c}"

    def test_transparent_returns_near_zero(self, tmp_path):
        p = _make_rgba_png(tmp_path, "transparent.png", alpha_value=0)
        c = ViewCompleter.coverage(p)
        assert c < 0.05, f"expected ~0.0, got {c}"

    def test_partial_alpha_midrange(self, tmp_path):
        """Half the pixels have alpha > 8 => coverage ~0.5."""
        arr = np.zeros((64, 64, 4), dtype=np.uint8)
        arr[:32, :, 3] = 255   # top half fully opaque
        arr[32:, :, 3] = 0     # bottom half transparent
        img = _PIL_Image.fromarray(arr, mode="RGBA")
        p = tmp_path / "half.png"
        img.save(str(p))
        c = ViewCompleter.coverage(p)
        assert 0.45 < c < 0.55, f"expected ~0.5, got {c}"

    def test_missing_file_returns_zero(self):
        c = ViewCompleter.coverage(Path("/nonexistent/image.png"))
        assert c == 0.0

    def test_rgb_uniform_bg_returns_near_zero(self, tmp_path):
        """RGB image that is entirely the background colour -> ~0 object coverage."""
        p = _make_rgb_png(tmp_path, "bg.png", bg=(0, 0, 0))
        c = ViewCompleter.coverage(p)
        assert c < 0.05, f"expected ~0 for blank background, got {c}"

    def test_rgb_object_present(self, tmp_path):
        """RGB image with object pixels (different from corner) -> nonzero coverage."""
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        # Place a bright object in the centre; corners are black.
        arr[16:48, 16:48] = [200, 200, 200]
        img = _PIL_Image.fromarray(arr, mode="RGB")
        p = tmp_path / "obj.png"
        img.save(str(p))
        c = ViewCompleter.coverage(p)
        # Centre region is 32x32 = 1024 / 4096 total = 0.25 of pixels
        assert c > 0.1, f"expected >0.1, got {c}"


# ---------------------------------------------------------------------------
# _build_prompt: structure and content
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def setup_method(self):
        self.vc = ViewCompleter()

    def _parse(self, text: str) -> dict:
        """Strip the preamble and parse the JSON body."""
        parts = text.split("\n", 1)
        return json.loads(parts[1])

    def test_returns_string_with_valid_json_body(self):
        text = self.vc._build_prompt("front", {"label": "vase"}, ["left"])
        spec = self._parse(text)
        assert isinstance(spec, dict)

    def test_object_field_comes_from_label(self):
        text = self.vc._build_prompt("back", {"label": "ceramic_pot"}, [])
        spec = self._parse(text)
        assert spec["object"] == "ceramic_pot"

    def test_object_field_falls_back_to_concept(self):
        text = self.vc._build_prompt("top", {"concept": "bronze_statue"}, [])
        spec = self._parse(text)
        assert spec["object"] == "bronze_statue"

    def test_target_view_field(self):
        text = self.vc._build_prompt("left", {"label": "obj"}, [])
        spec = self._parse(text)
        assert spec["target_view"] == "left"

    def test_azimuth_matches_view_geometry(self):
        for view_label, (az, el) in _VIEW_GEOMETRY.items():
            text = self.vc._build_prompt(view_label, {"label": "x"}, [])
            spec = self._parse(text)
            assert spec["azimuth_deg"] == az, f"{view_label}: azimuth mismatch"
            assert spec["elevation_deg"] == el, f"{view_label}: elevation mismatch"

    def test_constraints_list_present(self):
        text = self.vc._build_prompt("right", {"label": "chair"}, ["front"])
        spec = self._parse(text)
        assert isinstance(spec["constraints"], list)
        assert len(spec["constraints"]) >= 3

    def test_reference_views_recorded(self):
        text = self.vc._build_prompt("back", {"label": "box"}, ["front", "left"])
        spec = self._parse(text)
        assert "front" in spec["reference_views_provided"]

    def test_unknown_view_defaults_to_zero_azimuth(self):
        text = self.vc._build_prompt("mystery_view", {"label": "x"}, [])
        spec = self._parse(text)
        assert spec["azimuth_deg"] == 0
        assert spec["elevation_deg"] == 0


# ---------------------------------------------------------------------------
# complete(): coverage-gating + generation routing
# ---------------------------------------------------------------------------

def _make_completer(**kwargs) -> ViewCompleter:
    vc = ViewCompleter(
        comfyui_url="http://fake:8188",
        gap_threshold=0.02,
        keep_threshold=0.10,
        **kwargs,
    )
    return vc


class TestComplete:
    """Test complete() with fully mocked HTTP + PIL coverage."""

    def _setup_views(self, tmp_path: Path) -> tuple[ViewCompleter, dict]:
        """Create a ViewCompleter and a synthetic view dict with:
        - 'front': high-coverage (observed)
        - 'back': near-empty (gap)
        """
        vc = _make_completer()
        front_img = _make_rgba_png(tmp_path, "front.png", alpha_value=200)
        back_img = _make_rgba_png(tmp_path, "back.png", alpha_value=0)
        views = {"front": front_img, "back": back_img}
        return vc, views

    def test_observed_panels_kept(self, tmp_path):
        vc, views = self._setup_views(tmp_path)
        # Mock away all HTTP calls.
        with patch.object(vc, "_upload_image", return_value="srv_front.png"), \
             patch.object(vc, "_submit", return_value="pid-abc"), \
             patch.object(vc, "_poll", return_value={"outputs": {}}), \
             patch.object(vc, "_download_image", return_value=None), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "chair"},
                                 work_dir=tmp_path / "out")

        assert "front" in result.kept

    def test_gap_panels_routed_to_generation(self, tmp_path):
        vc, views = self._setup_views(tmp_path)
        generate_calls = []

        def fake_submit(wf):
            generate_calls.append(wf)
            return "pid-xyz"

        with patch.object(vc, "_upload_image", return_value="srv.png"), \
             patch.object(vc, "_submit", side_effect=fake_submit), \
             patch.object(vc, "_poll", return_value={"outputs": {}}), \
             patch.object(vc, "_download_image", return_value=None), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "table"},
                                 work_dir=tmp_path / "out")

        # 'back' is a gap panel: generation must have been attempted.
        assert len(generate_calls) >= 1

    def test_synthesised_image_updates_views(self, tmp_path):
        vc, views = self._setup_views(tmp_path)
        synth_path = tmp_path / "out" / "back.png"

        def fake_download(history, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"SYNTH")
            return out_path

        with patch.object(vc, "_upload_image", return_value="srv.png"), \
             patch.object(vc, "_submit", return_value="pid-1"), \
             patch.object(vc, "_poll", return_value={"outputs": {}}), \
             patch.object(vc, "_download_image", side_effect=fake_download), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "cup"},
                                 work_dir=tmp_path / "out")

        assert "back" in result.synthesised
        # The views dict must be updated to point at the synthesised file.
        assert result.views["back"].read_bytes() == b"SYNTH"

    def test_all_observed_returns_early_no_generation(self, tmp_path):
        """If all panels have good coverage, no generation should be triggered."""
        vc = _make_completer()
        front = _make_rgba_png(tmp_path, "front.png", alpha_value=200)
        back = _make_rgba_png(tmp_path, "back.png", alpha_value=200)
        views = {"front": front, "back": back}

        submit_calls = []
        with patch.object(vc, "_upload_image"), \
             patch.object(vc, "_submit", side_effect=lambda wf: submit_calls.append(wf) or "pid"), \
             patch.object(vc, "_poll"), \
             patch.object(vc, "_download_image"), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "pot"},
                                 work_dir=tmp_path / "out")

        # No generation should have been submitted.
        assert submit_calls == []
        assert result.synthesised == []
        assert sorted(result.kept) == sorted(views.keys())

    def test_no_observed_panel_returns_error(self, tmp_path):
        """When every panel is empty (no observed), complete() returns error immediately."""
        vc = _make_completer()
        empty1 = _make_rgba_png(tmp_path, "front.png", alpha_value=0)
        empty2 = _make_rgba_png(tmp_path, "back.png", alpha_value=0)
        views = {"front": empty1, "back": empty2}

        with patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "obj"},
                                 work_dir=tmp_path / "out")

        assert result.error is not None
        assert "no observed panel" in result.error.lower()

    def test_free_vram_called_when_gaps_processed(self, tmp_path):
        vc, views = self._setup_views(tmp_path)
        free_calls = []

        with patch.object(vc, "_upload_image", return_value="srv.png"), \
             patch.object(vc, "_submit", return_value="pid-1"), \
             patch.object(vc, "_poll", return_value={"outputs": {}}), \
             patch.object(vc, "_download_image", return_value=None), \
             patch.object(vc, "_free_vram", side_effect=lambda: free_calls.append(1)):
            vc.complete(views, object_desc={"label": "lamp"}, work_dir=tmp_path / "out")

        assert len(free_calls) == 1

    def test_generation_failure_leaves_original_view(self, tmp_path):
        """If FLUX.2 raises for a gap panel, the original panel path is preserved."""
        vc, views = self._setup_views(tmp_path)
        original_back = views["back"]

        with patch.object(vc, "_upload_image", return_value="srv.png"), \
             patch.object(vc, "_submit", side_effect=RuntimeError("FLUX.2 offline")), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "box"},
                                 work_dir=tmp_path / "out")

        # Generation failed -> back not in synthesised; original path kept.
        assert "back" not in result.synthesised
        assert result.views["back"] == original_back

    def test_reference_upload_failure_returns_error(self, tmp_path):
        """If reference image upload fails, complete() returns an error result."""
        import requests as req_mod

        vc, views = self._setup_views(tmp_path)

        with patch.object(vc, "_upload_image",
                          side_effect=req_mod.RequestException("upload refused")), \
             patch.object(vc, "_free_vram"):
            result = vc.complete(views, object_desc={"label": "jug"},
                                 work_dir=tmp_path / "out")

        assert result.error is not None
        assert "upload" in result.error.lower()

    def test_single_reference_duplicated_for_workflow(self, tmp_path):
        """When only one observed panel exists, it is duplicated into both ref slots."""
        vc = ViewCompleter(
            comfyui_url="http://fake:8188",
            gap_threshold=0.02,
            keep_threshold=0.10,
            max_references=2,
        )
        front = _make_rgba_png(tmp_path, "front.png", alpha_value=200)
        back = _make_rgba_png(tmp_path, "back.png", alpha_value=0)
        views = {"front": front, "back": back}

        upload_calls = []

        def counting_upload(path):
            upload_calls.append(path)
            return f"srv_{path.name}"

        with patch.object(vc, "_upload_image", side_effect=counting_upload), \
             patch.object(vc, "_submit", return_value="pid-dup"), \
             patch.object(vc, "_poll", return_value={"outputs": {}}), \
             patch.object(vc, "_download_image", return_value=None), \
             patch.object(vc, "_free_vram"):
            vc.complete(views, object_desc={"label": "sphere"}, work_dir=tmp_path / "out")

        # front uploaded twice (duplicated ref list) + possibly again for gap iteration.
        front_uploads = [c for c in upload_calls if "front" in str(c)]
        assert len(front_uploads) >= 2


# ---------------------------------------------------------------------------
# _free_vram: best-effort
# ---------------------------------------------------------------------------

class TestViewCompleterFreeVram:
    def test_free_vram_posts_to_free_endpoint(self):
        vc = _make_completer()
        post_calls = []

        def fake_post(url, json=None, timeout=None):
            post_calls.append(url)
            return MagicMock()

        vc.session.post = fake_post
        vc._free_vram()
        assert any("/free" in u for u in post_calls)

    def test_free_vram_does_not_raise_on_request_exception(self):
        import requests as req_mod

        vc = _make_completer()
        vc.session.post = MagicMock(side_effect=req_mod.RequestException("offline"))
        vc._free_vram()  # must not raise
