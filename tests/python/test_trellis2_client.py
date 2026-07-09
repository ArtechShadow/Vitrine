# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for pipeline.trellis2_client (single-image, ADR-025).

All HTTP and GPU calls are mocked: no live ComfyUI/native service, no GPU.
The tests pin the ADR-025 contract: single-crop conditioning, runtime
parameters landing on the right workflow nodes, and GLB bytes returned
verbatim (PRD v4 R6).
"""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Minimal trimesh stub when the real one is absent (keeps CI slim).
try:
    import trimesh as _trimesh_real  # noqa: F401
except ImportError:
    _stub = types.ModuleType("trimesh")
    _stub.Trimesh = MagicMock
    _stub.Scene = MagicMock
    _stub.load = MagicMock(return_value=MagicMock())
    _util = types.ModuleType("trimesh.util")
    _util.concatenate = MagicMock(return_value=MagicMock())
    _stub.util = _util
    sys.modules["trimesh"] = _stub
    sys.modules["trimesh.util"] = _util

from pipeline.trellis2_client import (  # noqa: E402
    Trellis2Client,
    Trellis2Result,
    TRELLIS2_SI_WORKFLOW,
)

GLB_BYTES = b"glTF-FAKE-BINARY-PAYLOAD" * 10


@pytest.fixture()
def crop(tmp_path) -> Path:
    p = tmp_path / "0001_vase.png"
    p.write_bytes(b"\x89PNG-fake")
    return p


def _client(**kw) -> Trellis2Client:
    c = Trellis2Client(comfyui_url="http://comfy:8188", **kw)
    c._load_glb = MagicMock(return_value=None)   # no real GLB parsing in unit tests
    return c


# ---------------------------------------------------------------------------
# Workflow template + prompt construction
# ---------------------------------------------------------------------------

def test_shipped_workflow_is_single_image():
    prompt = json.loads(TRELLIS2_SI_WORKFLOW.read_text())
    nodes = {n["class_type"] for k, n in prompt.items() if not k.startswith("_")}
    assert "Trellis2ImageToShape" in nodes
    assert "Trellis2MultiViewImageToShape" not in nodes      # ADR-025 compliance
    # Exactly ONE image input feeds the graph.
    loads = [n for k, n in prompt.items()
             if not k.startswith("_") and n["class_type"] == "LoadImage"]
    assert len(loads) == 1
    # LoadImage MASK is 1-alpha; conditioning wants white=object -> InvertMask.
    assert "InvertMask" in nodes


def test_build_prompt_substitutes_crop_and_parameters():
    client = _client(resolution="1024_cascade", seed=7, texture_size=2048,
                     ss_steps=9, shape_steps=10, tex_steps=11,
                     face_count_high=123_456)
    prompt = client._build_prompt("uploaded_vase.png", seed=7, label="vase")

    assert prompt["10"]["inputs"]["image"] == "uploaded_vase.png"
    assert prompt["1"]["inputs"]["resolution"] == "1024_cascade"
    assert prompt["40"]["inputs"]["seed"] == 7
    assert prompt["40"]["inputs"]["ss_sampling_steps"] == 9
    assert prompt["40"]["inputs"]["shape_sampling_steps"] == 10
    assert prompt["45"]["inputs"]["target_face_count"] == 123_456
    assert prompt["50"]["inputs"]["tex_sampling_steps"] == 11
    assert prompt["60"]["inputs"]["texture_size"] == 2048
    assert prompt["70"]["inputs"]["filename_prefix"] == "vitrine_object_vase"
    # Comment keys never reach the ComfyUI API.
    assert not any(k.startswith("_") for k in prompt)


# ---------------------------------------------------------------------------
# ComfyUI executor
# ---------------------------------------------------------------------------

def _mock_comfy_session(history_outputs: dict) -> MagicMock:
    session = MagicMock()

    def post(url, **kw):
        resp = MagicMock(status_code=200)
        if url.endswith("/upload/image"):
            resp.json.return_value = {"name": "uploaded_vase.png"}
        elif url.endswith("/prompt"):
            resp.json.return_value = {"prompt_id": "p123"}
        else:  # /free
            resp.json.return_value = {}
        return resp

    def get(url, **kw):
        resp = MagicMock(status_code=200)
        if "/history/" in url:
            resp.json.return_value = {
                "p123": {"status": {"status_str": "success"},
                         "outputs": history_outputs},
            }
        elif url.endswith("/view") or "/view" in url:
            resp.content = GLB_BYTES
        return resp

    session.post.side_effect = post
    session.get.side_effect = get
    return session


def test_reconstruct_from_image_returns_glb_bytes_verbatim(crop):
    client = _client(poll_interval=0.001)
    client.session = _mock_comfy_session({
        "80": {"result": [{"filename": "vitrine_object_vase.glb", "subfolder": ""}]},
    })
    result = client.reconstruct_from_image(crop, label="vase",
                                           provenance={"source_frame": "f1.jpg"})
    assert result.glb_data == GLB_BYTES              # byte-identical (R6)
    assert result.glb_sha256                          # hash recorded
    assert result.backend == "trellis2-comfyui-single-image"
    assert result.lineage["conditioning"] == "single-image"
    assert result.lineage["source"]["source_frame"] == "f1.jpg"
    # Only ONE image was uploaded — single-crop conditioning.
    uploads = [c for c in client.session.post.call_args_list
               if c.args and c.args[0].endswith("/upload/image")]
    assert len(uploads) == 1


def test_reconstruct_from_image_missing_crop_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _client().reconstruct_from_image(tmp_path / "nope.png")


def test_reconstruct_reports_missing_glb(crop):
    client = _client(poll_interval=0.001)
    client.session = _mock_comfy_session({})          # no outputs at all
    result = client.reconstruct_from_image(crop, label="vase")
    assert result.glb_data is None
    assert result.error


# ---------------------------------------------------------------------------
# Native-service executor (PRD v4 R5 contract)
# ---------------------------------------------------------------------------

def test_native_executor_decodes_high_low_pair(crop):
    client = _client(native_url="http://native:8402")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "glb_high_b64": base64.b64encode(GLB_BYTES).decode(),
        "glb_low_b64": base64.b64encode(b"low-poly").decode(),
        "lineage": {"timings": {"run_s": 30.0}},
    }
    client.session.post = MagicMock(return_value=resp)

    result = client.reconstruct_from_image(crop, label="vase")
    assert result.glb_data == GLB_BYTES
    assert result.glb_low_data == b"low-poly"
    assert result.backend == "trellis2-native-single-image"
    assert result.lineage["timings"] == {"run_s": 30.0}
    url = client.session.post.call_args.args[0]
    assert url == "http://native:8402/generate"


def test_from_config_reads_new_fields():
    cfg = types.SimpleNamespace(
        comfyui_url="http://c:8188", native_url="http://n:8402", timeout=99,
        resolution="512", texture_size=1024, seed=1, ss_steps=2, shape_steps=3,
        tex_steps=4, face_count_high=5, face_count_low=6,
    )
    client = Trellis2Client.from_config(cfg)
    assert client.native_url == "http://n:8402"
    assert (client.ss_steps, client.shape_steps, client.tex_steps) == (2, 3, 4)
    assert (client.face_count_high, client.face_count_low) == (5, 6)


def test_result_sha_empty_without_glb():
    assert Trellis2Result().glb_sha256 == ""
