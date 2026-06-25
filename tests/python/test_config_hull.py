# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for hull-related config dataclasses in pipeline.config.

Covers:
- PipelineConfig has trellis2 and view_completion sub-configs.
- Trellis2Config and ViewCompletionConfig carry the correct defaults.
- PipelineConfig._from_dict round-trips overrides for both sub-configs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pipeline.config import (
    PipelineConfig,
    Trellis2Config,
    ViewCompletionConfig,
)


# ---------------------------------------------------------------------------
# PipelineConfig sub-config presence
# ---------------------------------------------------------------------------

class TestPipelineConfigHasHullFields:
    def setup_method(self):
        self.cfg = PipelineConfig()

    def test_has_trellis2_attribute(self):
        assert hasattr(self.cfg, "trellis2")

    def test_trellis2_is_trellis2config(self):
        assert isinstance(self.cfg.trellis2, Trellis2Config)

    def test_has_view_completion_attribute(self):
        assert hasattr(self.cfg, "view_completion")

    def test_view_completion_is_view_completion_config(self):
        assert isinstance(self.cfg.view_completion, ViewCompletionConfig)


# ---------------------------------------------------------------------------
# Trellis2Config defaults
# ---------------------------------------------------------------------------

class TestTrellis2ConfigDefaults:
    def setup_method(self):
        self.cfg = Trellis2Config()

    def test_enabled_default_true(self):
        assert self.cfg.enabled is True

    def test_comfyui_url_default(self):
        assert self.cfg.comfyui_url == "http://vitrine-comfyui:8188"

    def test_resolution_default(self):
        assert self.cfg.resolution == "1536_cascade"

    def test_texture_size_default(self):
        assert self.cfg.texture_size == 4096

    def test_timeout_default(self):
        assert self.cfg.timeout == 1800

    def test_seed_default(self):
        assert self.cfg.seed == 42

    def test_render_size_default(self):
        assert self.cfg.render_size == 512

    def test_camera_distance_default(self):
        assert self.cfg.camera_distance == 2.5


# ---------------------------------------------------------------------------
# ViewCompletionConfig defaults
# ---------------------------------------------------------------------------

class TestViewCompletionConfigDefaults:
    def setup_method(self):
        self.cfg = ViewCompletionConfig()

    def test_enabled_default_true(self):
        assert self.cfg.enabled is True

    def test_comfyui_url_default(self):
        assert self.cfg.comfyui_url == "http://vitrine-comfyui:8188"

    def test_generator_default(self):
        assert self.cfg.generator == "flux2"

    def test_gap_threshold_default(self):
        assert self.cfg.gap_threshold == pytest.approx(0.02)

    def test_keep_threshold_default(self):
        assert self.cfg.keep_threshold == pytest.approx(0.10)

    def test_steps_default(self):
        assert self.cfg.steps == 28

    def test_guidance_default(self):
        assert self.cfg.guidance == pytest.approx(4.0)

    def test_seed_default(self):
        assert self.cfg.seed == 42

    def test_max_references_default(self):
        assert self.cfg.max_references == 2

    def test_timeout_default(self):
        assert self.cfg.timeout == 600


# ---------------------------------------------------------------------------
# PipelineConfig._from_dict round-trips for trellis2
# ---------------------------------------------------------------------------

class TestFromDictTrellis2:
    def _round_trip(self, overrides: dict) -> PipelineConfig:
        data = PipelineConfig().to_dict()
        data["trellis2"].update(overrides)
        return PipelineConfig._from_dict(data)

    def test_round_trips_enabled_false(self):
        cfg = self._round_trip({"enabled": False})
        assert cfg.trellis2.enabled is False

    def test_round_trips_resolution_override(self):
        cfg = self._round_trip({"resolution": "1024_cascade"})
        assert cfg.trellis2.resolution == "1024_cascade"

    def test_round_trips_texture_size_override(self):
        cfg = self._round_trip({"texture_size": 2048})
        assert cfg.trellis2.texture_size == 2048

    def test_round_trips_seed_override(self):
        cfg = self._round_trip({"seed": 77})
        assert cfg.trellis2.seed == 77

    def test_round_trips_comfyui_url_override(self):
        cfg = self._round_trip({"comfyui_url": "http://custom:9999"})
        assert cfg.trellis2.comfyui_url == "http://custom:9999"

    def test_round_trips_timeout_override(self):
        cfg = self._round_trip({"timeout": 3600})
        assert cfg.trellis2.timeout == 3600

    def test_round_trips_render_size_override(self):
        cfg = self._round_trip({"render_size": 256})
        assert cfg.trellis2.render_size == 256

    def test_round_trips_camera_distance_override(self):
        cfg = self._round_trip({"camera_distance": 3.0})
        assert cfg.trellis2.camera_distance == pytest.approx(3.0)

    def test_unrecognised_field_ignored(self):
        """Unknown fields in the dict must not raise."""
        data = PipelineConfig().to_dict()
        data["trellis2"]["completely_unknown_key"] = "bogus"
        cfg = PipelineConfig._from_dict(data)
        assert isinstance(cfg.trellis2, Trellis2Config)


# ---------------------------------------------------------------------------
# PipelineConfig._from_dict round-trips for view_completion
# ---------------------------------------------------------------------------

class TestFromDictViewCompletion:
    def _round_trip(self, overrides: dict) -> PipelineConfig:
        data = PipelineConfig().to_dict()
        data["view_completion"].update(overrides)
        return PipelineConfig._from_dict(data)

    def test_round_trips_enabled_false(self):
        cfg = self._round_trip({"enabled": False})
        assert cfg.view_completion.enabled is False

    def test_round_trips_gap_threshold(self):
        cfg = self._round_trip({"gap_threshold": 0.05})
        assert cfg.view_completion.gap_threshold == pytest.approx(0.05)

    def test_round_trips_keep_threshold(self):
        cfg = self._round_trip({"keep_threshold": 0.20})
        assert cfg.view_completion.keep_threshold == pytest.approx(0.20)

    def test_round_trips_steps(self):
        cfg = self._round_trip({"steps": 50})
        assert cfg.view_completion.steps == 50

    def test_round_trips_guidance(self):
        cfg = self._round_trip({"guidance": 7.5})
        assert cfg.view_completion.guidance == pytest.approx(7.5)

    def test_round_trips_seed(self):
        cfg = self._round_trip({"seed": 123})
        assert cfg.view_completion.seed == 123

    def test_round_trips_max_references(self):
        cfg = self._round_trip({"max_references": 4})
        assert cfg.view_completion.max_references == 4

    def test_round_trips_timeout(self):
        cfg = self._round_trip({"timeout": 1200})
        assert cfg.view_completion.timeout == 1200

    def test_round_trips_comfyui_url(self):
        cfg = self._round_trip({"comfyui_url": "http://alt-comfyui:8200"})
        assert cfg.view_completion.comfyui_url == "http://alt-comfyui:8200"

    def test_round_trips_generator(self):
        cfg = self._round_trip({"generator": "qwen-image-edit"})
        assert cfg.view_completion.generator == "qwen-image-edit"

    def test_unrecognised_field_ignored(self):
        data = PipelineConfig().to_dict()
        data["view_completion"]["mystery_field"] = "ignored"
        cfg = PipelineConfig._from_dict(data)
        assert isinstance(cfg.view_completion, ViewCompletionConfig)


# ---------------------------------------------------------------------------
# Both configs survive to_dict() -> _from_dict() unchanged at defaults
# ---------------------------------------------------------------------------

class TestDefaultRoundTrip:
    def test_trellis2_defaults_survive_round_trip(self):
        original = PipelineConfig()
        restored = PipelineConfig._from_dict(original.to_dict())
        assert restored.trellis2.enabled == original.trellis2.enabled
        assert restored.trellis2.resolution == original.trellis2.resolution
        assert restored.trellis2.texture_size == original.trellis2.texture_size
        assert restored.trellis2.seed == original.trellis2.seed
        assert restored.trellis2.timeout == original.trellis2.timeout
        assert restored.trellis2.render_size == original.trellis2.render_size

    def test_view_completion_defaults_survive_round_trip(self):
        original = PipelineConfig()
        restored = PipelineConfig._from_dict(original.to_dict())
        assert restored.view_completion.enabled == original.view_completion.enabled
        assert restored.view_completion.generator == original.view_completion.generator
        assert restored.view_completion.gap_threshold == pytest.approx(
            original.view_completion.gap_threshold
        )
        assert restored.view_completion.keep_threshold == pytest.approx(
            original.view_completion.keep_threshold
        )
        assert restored.view_completion.steps == original.view_completion.steps
        assert restored.view_completion.seed == original.view_completion.seed
        assert restored.view_completion.max_references == original.view_completion.max_references

    def test_other_config_keys_unaffected_by_trellis2_override(self):
        """Overriding trellis2 must not bleed into other sub-configs."""
        data = PipelineConfig().to_dict()
        data["trellis2"]["texture_size"] = 1024
        cfg = PipelineConfig._from_dict(data)
        # Hunyuan3D should be untouched.
        assert cfg.hunyuan3d.seed == 42
        assert cfg.ingest.fps == pytest.approx(2.0)
