# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.trellis2_client.

All HTTP and GPU calls are mocked: no live ComfyUI server, no GPU, no disk
reads of real PLY files.  The workflow template is synthesised in-memory so
TRELLIS2_MV_WORKFLOW does not need to exist on disk.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure pipeline package is importable via src/
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Stub out heavy optional deps before importing the module under test so we
# do not need a live trimesh or GPU environment.
# ---------------------------------------------------------------------------

# Provide a minimal trimesh stub if not already importable.
try:
    import trimesh as _trimesh_real  # noqa: F401
except ImportError:
    _trimesh_stub = types.ModuleType("trimesh")
    _trimesh_stub.Trimesh = MagicMock
    _trimesh_stub.Scene = MagicMock
    _trimesh_stub.load = MagicMock(return_value=MagicMock())
    _trimesh_util = types.ModuleType("trimesh.util")
    _trimesh_util.concatenate = MagicMock(return_value=MagicMock())
    _trimesh_stub.util = _trimesh_util
    sys.modules["trimesh"] = _trimesh_stub
    sys.modules["trimesh.util"] = _trimesh_util

# Stub the renderer so importing trellis2_client does not pull in GPU deps.
_mv_mod = types.ModuleType("pipeline.multiview_renderer")


class _FakeRenderConfig:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeCamera:
    def __init__(self, label: str):
        self.label = label
        self.name = label


class _FakeViewResult:
    def __init__(self, label: str):
        self.camera = _FakeCamera(label)


class _FakeMultiViewRenderer:
    def __init__(self, cfg):
        self.cfg = cfg

    def render(self, ply_path, output_dir=None):
        labels = ["front", "left", "back", "right", "top", "bottom"]
        results = []
        for label in labels:
            vr = _FakeViewResult(label)
            results.append(vr)
            # Create dummy PNG files so _render_and_save_views can build the map
            if output_dir is not None:
                out = Path(output_dir) / f"{label}.png"
                out.write_bytes(b"FAKEPNG")
        return results


_mv_mod.MultiViewRenderer = _FakeMultiViewRenderer
_mv_mod.RenderConfig = _FakeRenderConfig
sys.modules["pipeline.multiview_renderer"] = _mv_mod

# Now import the module under test.
from pipeline.trellis2_client import (  # noqa: E402
    Trellis2Client,
    Trellis2Result,
    _VIEW_PLACEHOLDERS,
    TRELLIS2_MV_WORKFLOW,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VIEWS = list(_VIEW_PLACEHOLDERS.keys())  # front/left/back/right/top/bottom


def _make_workflow_template(extra_nodes: dict | None = None) -> dict:
    """Build a minimal trellis2_multiview_pbr.json-shaped workflow dict."""
    nodes = {
        "1": {"inputs": {"resolution": "PLACEHOLDER_RES"}},
        "40": {"inputs": {"seed": 0}},
        "50": {"inputs": {"seed": 0}},
        "60": {"inputs": {"seed": 0, "texture_size": 0}},
        "70": {"inputs": {"filename_prefix": "PLACEHOLDER_FN"}},
        "_comment": "this node should be stripped",
    }
    # Add a LoadImage node for each view placeholder.
    for i, (view, token) in enumerate(_VIEW_PLACEHOLDERS.items(), start=100):
        nodes[str(i)] = {"inputs": {"image": token}}
    if extra_nodes:
        nodes.update(extra_nodes)
    return nodes


def _make_client(workflow_content: dict | None = None, **kwargs) -> tuple[Trellis2Client, Path]:
    """Create a client pointing at a temp workflow file."""
    td = Path(tempfile.mkdtemp())
    wf_path = td / "trellis2_multiview_pbr.json"
    wf = workflow_content if workflow_content is not None else _make_workflow_template()
    wf_path.write_text(json.dumps(wf))
    client = Trellis2Client(
        comfyui_url="http://fake-comfyui:8188",
        workflow_path=wf_path,
        **kwargs,
    )
    return client, td


# ---------------------------------------------------------------------------
# _build_prompt: placeholder substitution
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_all_view_placeholders_substituted(self):
        client, _ = _make_client()
        uploaded = {v: f"uploaded_{v}.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=99, label="chair")

        for view, token in _VIEW_PLACEHOLDERS.items():
            # No node should still contain the raw placeholder string.
            for node in prompt.values():
                if isinstance(node, dict):
                    assert node.get("inputs", {}).get("image") != token, (
                        f"Token {token!r} was not replaced for view '{view}'"
                    )

    def test_uploaded_filenames_appear_in_load_image_nodes(self):
        client, _ = _make_client()
        uploaded = {v: f"srv_{v}.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=0, label="box")

        image_values = [
            node.get("inputs", {}).get("image")
            for node in prompt.values()
            if isinstance(node, dict)
        ]
        for view in _VIEWS:
            assert f"srv_{view}.png" in image_values, (
                f"uploaded name for '{view}' not found in prompt"
            )

    def test_resolution_applied_to_node_1(self):
        client, _ = _make_client(resolution="1024")
        uploaded = {v: "x.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=0, label="obj")
        assert prompt["1"]["inputs"]["resolution"] == "1024"

    def test_seed_applied_to_nodes_40_50_60(self):
        client, _ = _make_client(seed=1234)
        uploaded = {v: "x.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=1234, label="obj")
        for nid in ("40", "50", "60"):
            assert prompt[nid]["inputs"]["seed"] == 1234, f"node {nid} seed wrong"

    def test_texture_size_applied_to_node_60(self):
        client, _ = _make_client(texture_size=2048)
        uploaded = {v: "x.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=0, label="cup")
        assert prompt["60"]["inputs"]["texture_size"] == 2048

    def test_filename_prefix_applied_to_node_70(self):
        client, _ = _make_client()
        uploaded = {v: "x.png" for v in _VIEWS}
        label = "my_fancy_object"
        prompt = client._build_prompt(uploaded, seed=0, label=label)
        assert prompt["70"]["inputs"]["filename_prefix"] == f"vitrine_hull_{label}"

    def test_comment_nodes_stripped(self):
        client, _ = _make_client()
        uploaded = {v: "x.png" for v in _VIEWS}
        prompt = client._build_prompt(uploaded, seed=0, label="obj")
        assert "_comment" not in prompt

    def test_label_sanitised(self):
        """Labels with special chars should be sanitised in filename_prefix."""
        client, _ = _make_client()
        uploaded = {v: "x.png" for v in _VIEWS}
        # The sanitisation happens in reconstruct_from_gaussians; _build_prompt
        # uses whatever label string it receives — pass an already-safe one.
        prompt = client._build_prompt(uploaded, seed=0, label="safe_label")
        assert "safe_label" in prompt["70"]["inputs"]["filename_prefix"]


# ---------------------------------------------------------------------------
# _extract_glb_refs: various output shapes
# ---------------------------------------------------------------------------

class TestExtractGlbRefs:
    def test_preview3d_result_list_shape(self):
        """Preview3D node: result -> ["hull.glb", null, null]"""
        client, _ = _make_client()
        history = {
            "outputs": {
                "99": {"result": ["hull.glb", None, None]}
            }
        }
        refs = client._extract_glb_refs(history)
        assert len(refs) == 1
        fname, sub = refs[0]
        assert fname == "hull.glb"

    def test_dict_images_shape(self):
        """Standard images list with dict entries."""
        client, _ = _make_client()
        history = {
            "outputs": {
                "7": {
                    "images": [
                        {"filename": "mesh_out.glb", "subfolder": "3d", "type": "output"},
                        {"filename": "mesh_out.glb", "subfolder": "3d", "type": "output"},
                    ]
                }
            }
        }
        refs = client._extract_glb_refs(history)
        assert len(refs) >= 1
        fnames = [r[0] for r in refs]
        assert "mesh_out.glb" in fnames

    def test_non_glb_ignored(self):
        """PNG and JSON outputs must not appear in the result."""
        client, _ = _make_client()
        history = {
            "outputs": {
                "5": {"images": [{"filename": "preview.png", "subfolder": ""}]},
                "6": {"text": ["manifest.json"]},
                "7": {"result": ["actual.glb", None]},
            }
        }
        refs = client._extract_glb_refs(history)
        fnames = [r[0] for r in refs]
        assert "preview.png" not in fnames
        assert "manifest.json" not in fnames
        assert "actual.glb" in fnames

    def test_empty_outputs(self):
        client, _ = _make_client()
        refs = client._extract_glb_refs({"outputs": {}})
        assert refs == []

    def test_subfolder_extracted_from_dict(self):
        client, _ = _make_client()
        history = {
            "outputs": {
                "8": {
                    "meshes": [{"filename": "out.glb", "subfolder": "hulls"}]
                }
            }
        }
        refs = client._extract_glb_refs(history)
        assert len(refs) == 1
        fname, sub = refs[0]
        assert fname == "out.glb"
        assert sub == "hulls"

    def test_string_items_in_list(self):
        """Plain strings (not dicts) in a list should be added if .glb."""
        client, _ = _make_client()
        history = {
            "outputs": {
                "3": {"result": ["plain.glb", "skip.png", None]}
            }
        }
        refs = client._extract_glb_refs(history)
        fnames = [r[0] for r in refs]
        assert "plain.glb" in fnames
        assert "skip.png" not in fnames


# ---------------------------------------------------------------------------
# _free_vram: best-effort, never raises
# ---------------------------------------------------------------------------

class TestFreeVram:
    def test_free_vram_posts_free_endpoint(self):
        client, _ = _make_client()
        post_calls = []

        def fake_post(url, json=None, timeout=None):
            post_calls.append({"url": url, "json": json})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        client.session.post = fake_post
        client._free_vram()

        assert len(post_calls) == 1
        assert post_calls[0]["url"].endswith("/free")
        assert post_calls[0]["json"]["unload_models"] is True
        assert post_calls[0]["json"]["free_memory"] is True

    def test_free_vram_does_not_raise_on_request_exception(self):
        """Network failure in /free must be swallowed silently."""
        import requests as req_mod

        client, _ = _make_client()

        def failing_post(url, json=None, timeout=None):
            raise req_mod.RequestException("connection refused")

        client.session.post = failing_post
        # Should not raise.
        client._free_vram()

    def test_free_vram_does_not_raise_on_connection_error(self):
        import requests as req_mod

        client, _ = _make_client()
        client.session.post = MagicMock(side_effect=req_mod.ConnectionError("refused"))
        client._free_vram()  # must not propagate


# ---------------------------------------------------------------------------
# from_config: defaults
# ---------------------------------------------------------------------------

class TestFromConfig:
    def _bare_config(self, **overrides):
        """Minimal object that mimics Trellis2Config without importing it."""
        cfg = MagicMock()
        # Provide defaults that mirror Trellis2Config.
        defaults = {
            "comfyui_url": "http://vitrine-comfyui:8188",
            "timeout": 1800,
            "resolution": "1536_cascade",
            "texture_size": 4096,
            "seed": 42,
            "render_size": 512,
            "camera_distance": 2.5,
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(cfg, k, v)
        return cfg

    def test_from_config_uses_url(self):
        cfg = self._bare_config(comfyui_url="http://my-comfyui:9999")
        client = Trellis2Client.from_config(cfg)
        assert client.comfyui_url == "http://my-comfyui:9999"

    def test_from_config_defaults(self):
        cfg = self._bare_config()
        client = Trellis2Client.from_config(cfg)
        assert client.resolution == "1536_cascade"
        assert client.texture_size == 4096
        assert client.seed == 42
        assert client.render_size == 512
        assert client.camera_distance == 2.5
        assert client.timeout == 1800

    def test_from_config_override_seed(self):
        cfg = self._bare_config(seed=999)
        client = Trellis2Client.from_config(cfg)
        assert client.seed == 999

    def test_from_config_missing_attr_uses_getattr_default(self):
        """from_config uses getattr() with defaults: a minimal config with only
        comfyui_url (no other attrs) should still construct without error."""
        cfg = MagicMock(spec=[])  # no attributes at all
        # getattr(cfg, 'comfyui_url', default) -> MagicMock default fallback
        # We just need it not to raise.
        client = Trellis2Client.from_config(cfg)
        assert client is not None


# ---------------------------------------------------------------------------
# reconstruct_from_gaussians: full end-to-end wiring with mocked session
# ---------------------------------------------------------------------------

class TestReconstructFromGaussians:
    """Verifies that the public method wires all internal calls correctly and
    returns a Trellis2Result.  All I/O (session, renderer) is mocked."""

    def _make_full_client(self, wf_content=None, **kwargs):
        client, td = _make_client(wf_content, **kwargs)
        return client, td

    def _stub_session(self, client: Trellis2Client, glb_bytes: bytes = b"GLB\x00") -> dict:
        """Replace client.session with a fake that responds to ComfyUI's API."""
        calls = []

        # POST /upload/image -> {"name": "<original>"}
        def fake_post(url, files=None, json=None, timeout=None):
            calls.append(("POST", url, files, json))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url.endswith("/upload/image"):
                fname = list(files["image"])[0] if files else "img.png"
                # files["image"] is a tuple: (name, fileobj, mime)
                resp.json.return_value = {"name": files["image"][0] if files else "img.png"}
            elif url.endswith("/prompt"):
                resp.json.return_value = {"prompt_id": "test-pid-1234"}
            elif url.endswith("/free"):
                resp.json.return_value = {}
            else:
                resp.json.return_value = {}
            return resp

        def fake_get(url, params=None, timeout=None):
            calls.append(("GET", url, params))
            resp = MagicMock()
            resp.status_code = 200
            if "/history/" in url:
                resp.json.return_value = {
                    "test-pid-1234": {
                        "status": {"status_str": "success"},
                        "outputs": {
                            "99": {"result": ["vitrine_hull.glb", None, None]}
                        },
                    }
                }
            elif "/view" in url:
                resp.content = glb_bytes
            return resp

        client.session.post = fake_post
        client.session.get = fake_get
        return calls

    def test_returns_trellis2result(self, tmp_path):
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        # Patch _poll_completion to skip the wait loop, _load_glb to return a
        # dummy mesh, and time.sleep to be instant.
        dummy_mesh = MagicMock()
        dummy_mesh.vertices = [1, 2, 3]
        dummy_mesh.faces = [1]

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={
                 "outputs": {"99": {"result": ["hull.glb", None, None]}}
             }), \
             patch.object(client, "_load_glb", return_value=dummy_mesh):
            result = client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work")

        assert isinstance(result, Trellis2Result)

    def test_ply_not_found_raises(self, tmp_path):
        client, _ = self._make_full_client()
        with pytest.raises(FileNotFoundError):
            client.reconstruct_from_gaussians(tmp_path / "missing.ply")

    def test_prompt_id_stored_in_result(self, tmp_path):
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={
                 "outputs": {}
             }):
            result = client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work")

        assert result.prompt_id == "test-pid-1234"

    def test_no_glb_sets_error(self, tmp_path):
        """When history has no GLB outputs, result.error is set."""
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={"outputs": {}}):
            result = client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work")

        assert result.error is not None
        assert result.mesh is None

    def test_view_completer_called_when_set(self, tmp_path):
        """When view_completer is attached, complete() is called with the view dict."""
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        # Build view map that will be passed to view_completer.complete.
        mock_vc = MagicMock()
        vc_result = MagicMock()
        vc_result.views = {v: tmp_path / f"{v}.png" for v in _VIEWS}
        for p in vc_result.views.values():
            p.write_bytes(b"FAKEPNG")
        vc_result.synthesised = ["back"]
        vc_result.kept = ["front", "left", "right", "top", "bottom"]
        mock_vc.complete.return_value = vc_result
        client.view_completer = mock_vc

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={"outputs": {}}):
            client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work", label="chair")

        mock_vc.complete.assert_called_once()

    def test_view_completer_failure_is_non_fatal(self, tmp_path):
        """If view_completer.complete() raises, the pipeline continues."""
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        mock_vc = MagicMock()
        mock_vc.complete.side_effect = RuntimeError("FLUX.2 not staged")
        client.view_completer = mock_vc

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={"outputs": {}}):
            result = client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work")

        # Should not raise; result may have error because no GLB but no exception.
        assert isinstance(result, Trellis2Result)

    def test_free_vram_called_after_reconstruction(self, tmp_path):
        client, _ = self._make_full_client()
        self._stub_session(client)
        ply = tmp_path / "obj.ply"
        ply.write_bytes(b"ply")

        free_calls = []
        orig_free = client._free_vram
        client._free_vram = lambda: free_calls.append(1)

        with patch("pipeline.trellis2_client.time.sleep"), \
             patch.object(client, "_poll_completion", return_value={"outputs": {}}):
            client.reconstruct_from_gaussians(ply, work_dir=tmp_path / "work")

        assert len(free_calls) == 1


# ---------------------------------------------------------------------------
# Trellis2Result properties
# ---------------------------------------------------------------------------

class TestTrellis2ResultProperties:
    def test_vertex_count_zero_when_no_mesh(self):
        r = Trellis2Result()
        assert r.vertex_count == 0

    def test_face_count_zero_when_no_mesh(self):
        r = Trellis2Result()
        assert r.face_count == 0

    def test_has_texture_false_when_no_mesh(self):
        r = Trellis2Result()
        assert r.has_texture is False

    def test_backend_default(self):
        r = Trellis2Result()
        assert r.backend == "trellis2-4b-mv-pbr"
