# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for PipelineStages._export_native_splat_formats.

All MCP/network calls are mocked: no live endpoint, no GPU, no real PLY.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Ensure pipeline package is importable via src/
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Stub out heavy optional imports that stages.py pulls in at import time
# so that we never need torch/trimesh/GPU in this test.
# ---------------------------------------------------------------------------

def _ensure_stub(name: str, **attrs: object) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


_ensure_stub("torch")
_ensure_stub("trimesh")
_ensure_stub("plyfile")
_ensure_stub("open3d")
_ensure_stub("cv2")
_ensure_stub("numpy", array=MagicMock(), isfinite=MagicMock(return_value=MagicMock()))

# Stub pipeline.colmap_parser with the names that pipeline/__init__.py imports.
_colmap_parser_stub = _ensure_stub(
    "pipeline.colmap_parser",
    ColmapCamera=MagicMock,
    ColmapImage=MagicMock,
    ColmapPoint3D=MagicMock,
    parse_cameras_txt=MagicMock(return_value=[]),
    parse_images_txt=MagicMock(return_value=[]),
    parse_points3d_txt=MagicMock(return_value=[]),
)

# Stub pipeline.coordinate_transform with the names pipeline/__init__.py needs.
_coord_stub = _ensure_stub(
    "pipeline.coordinate_transform",
    CoordinateTransformer=MagicMock,
    colmap_to_usd_position=MagicMock(return_value=(0, 0, 0)),
    colmap_to_usd_rotation=MagicMock(return_value=(1, 0, 0, 0)),
)

# Stub remaining pipeline sub-modules that stages.py imports at the method level.
for _sub in (
    "pipeline.preflight",
    "pipeline.splat_optimizer",
    "pipeline.milo_extractor",
    "pipeline.come_extractor",
    "pipeline.gaussianwrapping_extractor",
    "pipeline.frame_selector",
    "pipeline.person_remover",
    "pipeline.mesh_extractor",
    "pipeline.multiview_renderer",
):
    _ensure_stub(_sub, check_all=MagicMock(return_value={}))

# Make preflight.check_all return a dict (used in __init__)
sys.modules["pipeline.preflight"].check_all = MagicMock(return_value={})  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Import the module under test
# (bypass pipeline/__init__.py eager imports by importing submodules directly)
# ---------------------------------------------------------------------------
from pipeline.stages import PipelineStages, StageResult  # noqa: E402
from pipeline.config import PipelineConfig, DeliveryConfig  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stages(job_dir: Path, extra_formats: list[str] | None = None) -> PipelineStages:
    """Return a PipelineStages instance with a clean config and no real preflight."""
    cfg = PipelineConfig()
    cfg.delivery.lichtfeld_extra_formats = extra_formats or []
    with patch("pipeline.stages.PipelineStages.__init__", autospec=True) as mock_init:
        mock_init.return_value = None
        stages = PipelineStages.__new__(PipelineStages)
    # Manually set the attributes __init__ would set.
    stages.job_dir = job_dir
    stages.config = cfg
    stages._preflight = {}
    return stages


def _make_result() -> StageResult:
    return StageResult(success=True, stage="train")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestExportNativeSplatFormats:
    """Unit tests for PipelineStages._export_native_splat_formats."""

    # ------------------------------------------------------------------
    # (a) empty lichtfeld_extra_formats → no export calls
    # ------------------------------------------------------------------

    def test_empty_formats_no_export_calls(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=[])
        result = _make_result()

        with patch("pipeline.mcp_client.McpClient") as MockClient:
            stages._export_native_splat_formats(result)
            MockClient.assert_not_called()

        assert not any(k.startswith("delivery_splat_") for k in result.artifacts)

    # ------------------------------------------------------------------
    # (b) ["spz", "html"] → export_spz / export_html called with delivery paths
    # ------------------------------------------------------------------

    def test_spz_and_html_exports_called(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz", "html"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)

        # Each exporter must have been called once with a path under delivery/
        mock_client.export_spz.assert_called_once()
        spz_arg = mock_client.export_spz.call_args[0][0]
        assert spz_arg.endswith("scene.spz")
        assert "delivery" in spz_arg

        mock_client.export_html.assert_called_once()
        html_arg = mock_client.export_html.call_args[0][0]
        assert html_arg.endswith("scene.html")
        assert "delivery" in html_arg

    def test_artifacts_populated_on_success(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz", "html"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)

        assert "delivery_splat_spz" in result.artifacts
        assert "delivery_splat_html" in result.artifacts
        assert result.artifacts["delivery_splat_spz"].endswith("scene.spz")
        assert result.artifacts["delivery_splat_html"].endswith("scene.html")

    # ------------------------------------------------------------------
    # (c) unknown format → skipped, no raise
    # ------------------------------------------------------------------

    def test_unknown_format_skipped_no_raise(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz", "totally_made_up"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)  # must not raise

        # spz exported; the unknown format should NOT produce an artifact key
        assert "delivery_splat_spz" in result.artifacts
        assert "delivery_splat_totally_made_up" not in result.artifacts
        # MagicMock auto-creates attributes, so we verify via call_count instead:
        # the auto-created attribute was never *called* as an exporter.
        assert mock_client.export_totally_made_up.call_count == 0

    def test_only_unknown_format_does_not_raise(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["fantasy_format"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)  # must not raise

        assert not any(k.startswith("delivery_splat_") for k in result.artifacts)

    # ------------------------------------------------------------------
    # (d) exporter raising → non-fatal, method returns normally
    # ------------------------------------------------------------------

    def test_exporter_exception_is_non_fatal(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz", "sog"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.export_spz.side_effect = RuntimeError("MCP connection dropped")

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)  # must not raise

        # spz failed → no artifact; sog succeeded → artifact present
        assert "delivery_splat_spz" not in result.artifacts
        assert "delivery_splat_sog" in result.artifacts

    def test_all_exporters_fail_no_raise(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz", "sog", "html"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.export_spz.side_effect = OSError("disk full")
        mock_client.export_sog.side_effect = OSError("disk full")
        mock_client.export_html.side_effect = OSError("disk full")

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)  # must not raise

        assert not any(k.startswith("delivery_splat_") for k in result.artifacts)

    # ------------------------------------------------------------------
    # MCP unreachable → skip-with-warning, non-fatal
    # ------------------------------------------------------------------

    def test_mcp_unreachable_skips_non_fatal(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = False  # endpoint unreachable

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)  # must not raise

        mock_client.export_spz.assert_not_called()
        assert "delivery_splat_spz" not in result.artifacts

    # ------------------------------------------------------------------
    # load_checkpoint called when ply_path supplied
    # ------------------------------------------------------------------

    def test_load_checkpoint_called_when_ply_supplied(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["rad"])
        result = _make_result()

        ply = tmp_path / "scene.ply"
        ply.write_bytes(b"ply")

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result, ply_path=ply)

        mock_client.load_checkpoint.assert_called_once_with(str(ply))

    def test_load_checkpoint_not_called_when_no_ply(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["rad"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result, ply_path=None)

        mock_client.load_checkpoint.assert_not_called()

    def test_load_checkpoint_failure_is_non_fatal(self, tmp_path: Path) -> None:
        """load_checkpoint raising must not prevent the exports from being attempted."""
        stages = _make_stages(tmp_path, extra_formats=["sog"])
        result = _make_result()

        ply = tmp_path / "scene.ply"
        ply.write_bytes(b"ply")

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.load_checkpoint.side_effect = RuntimeError("checkpoint not found")

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result, ply_path=ply)  # must not raise

        # Export was still attempted after the checkpoint failure
        mock_client.export_sog.assert_called_once()

    # ------------------------------------------------------------------
    # usdz_nurec writes a .usdz container (not .usdz_nurec) — licence-sensitive
    # ------------------------------------------------------------------

    def test_usdz_nurec_uses_usdz_extension(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["usdz_nurec"])
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)

        mock_client.export_usdz_nurec.assert_called_once()
        out_arg = mock_client.export_usdz_nurec.call_args[0][0]
        assert out_arg.endswith("scene.usdz")
        assert not out_arg.endswith("scene.usdz_nurec")
        assert result.artifacts["delivery_splat_usdz_nurec"].endswith("scene.usdz")

    # ------------------------------------------------------------------
    # sh_degree from config is forwarded to the exporter
    # ------------------------------------------------------------------

    def test_sh_degree_forwarded_to_exporter(self, tmp_path: Path) -> None:
        stages = _make_stages(tmp_path, extra_formats=["spz"])
        stages.config.delivery.lichtfeld_extra_formats_sh_degree = 2
        result = _make_result()

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pipeline.mcp_client.McpClient", return_value=mock_client):
            stages._export_native_splat_formats(result)

        mock_client.export_spz.assert_called_once()
        assert mock_client.export_spz.call_args.kwargs.get("sh_degree") == 2
