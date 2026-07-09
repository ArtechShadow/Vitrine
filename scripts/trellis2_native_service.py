#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Thin HTTP service wrapping the NATIVE TRELLIS.2 pipeline (PRD v4 R5).

ADR-025 D2: the 3D half of object generation moves off ComfyUI onto the
upstream microsoft/TRELLIS.2 pipeline behind this small, stable HTTP
contract. One matted object crop in; a high-poly + decimated low-poly PBR
GLB pair out, plus lineage. The Vitrine client (pipeline.trellis2_client,
``native_url`` config) already speaks this contract — flipping the config
from ComfyUI to this service requires no pipeline change.

Contract
--------
GET  /health
    -> 200 {"status": "ok", "pipeline_loaded": bool, "device": str}

POST /generate   (multipart/form-data)
    image: PNG/JPEG file — RGBA preferred (alpha = object matte)
    seed, resolution, texture_size, ss_steps, shape_steps, tex_steps,
    face_count_high, face_count_low, label: form fields (all optional)
    -> 200 {"glb_high_b64": str, "glb_low_b64": str, "lineage": {...}}
    -> 4xx/5xx {"error": str}

Environment
-----------
Runs in its OWN pinned env (ADR-021 vendoring discipline), NOT ComfyUI's:
the upstream TRELLIS.2 checkout + its CUDA extensions (nvdiffrast, CuMesh,
flash-attn, o_voxel). VRAM >= 24 GB for 1024_cascade; 1536_cascade is the
hero setting. Model dir defaults to the staged tree; override with
TRELLIS2_MODEL_PATH. Serve with:

    python3 scripts/trellis2_native_service.py --host 127.0.0.1 --port 8402

NOTE (scaffold status): the HTTP surface and client contract are final; the
two functions marked VERIFY-ON-ENV-BUILD wrap the upstream API exactly as
documented (``pipeline.run(image)`` -> ``to_glb`` twice) and must be smoke-
tested against the pinned upstream checkout when the env is stood up
(PRD v4 R5 acceptance; see also the R9 eval harness).
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
import os
import time

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger("trellis2-native")

MODEL_PATH = os.environ.get("TRELLIS2_MODEL_PATH", "microsoft/TRELLIS.2-4B")

app = Flask(__name__)
_pipeline = None  # loaded lazily on first /generate


def _load_pipeline():
    """Load the upstream TRELLIS.2 image-to-3D pipeline once.

    VERIFY-ON-ENV-BUILD: import path + class name per the pinned upstream
    checkout (microsoft/TRELLIS.2). The documented API is
    ``Trellis2ImageTo3DPipeline.from_pretrained(...)`` with ``.run(image)``.
    """
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    t0 = time.monotonic()
    from trellis2.pipelines import Trellis2ImageTo3DPipeline  # upstream repo
    _pipeline = Trellis2ImageTo3DPipeline.from_pretrained(MODEL_PATH)
    _pipeline.cuda()
    logger.info("TRELLIS.2 pipeline loaded from %s in %.1fs",
                MODEL_PATH, time.monotonic() - t0)
    return _pipeline


def _generate(image, params: dict):
    """Run single-image generation + the high/low to_glb pair.

    VERIFY-ON-ENV-BUILD: ``run()`` kwargs and the o-voxel ``to_glb``
    signature (decimation target, texture_size, remesh/UV options) per the
    pinned checkout. Returns (glb_high_bytes, glb_low_bytes, timings).
    """
    pipeline = _load_pipeline()
    t0 = time.monotonic()
    outputs = pipeline.run(
        image,
        seed=params["seed"],
        sparse_structure_sampler_params={"steps": params["ss_steps"]},
        slat_sampler_params={"steps": params["shape_steps"]},
    )
    t_run = time.monotonic() - t0

    # One supported call per artifact: high-poly hero + decimated game-res
    # low-poly, both with the PBR bake (ADR-025 D2 — never re-export).
    def _to_glb(face_count: int) -> bytes:
        glb = outputs.to_glb(
            decimation_target=face_count,
            texture_size=params["texture_size"],
        )
        buf = io.BytesIO()
        glb.export(buf, file_type="glb")
        return buf.getvalue()

    t1 = time.monotonic()
    glb_high = _to_glb(params["face_count_high"])
    glb_low = _to_glb(params["face_count_low"])
    t_glb = time.monotonic() - t1
    return glb_high, glb_low, {"run_s": round(t_run, 1), "to_glb_s": round(t_glb, 1)}


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "pipeline_loaded": _pipeline is not None,
        "model_path": MODEL_PATH,
    })


@app.post("/generate")
def generate():
    if "image" not in request.files:
        return jsonify({"error": "multipart field 'image' is required"}), 400

    def _int(name: str, default: int) -> int:
        try:
            return int(request.form.get(name, default))
        except (TypeError, ValueError):
            return default

    params = {
        "seed": _int("seed", 42),
        "resolution": request.form.get("resolution", "1536_cascade"),
        "texture_size": _int("texture_size", 4096),
        "ss_steps": _int("ss_steps", 12),
        "shape_steps": _int("shape_steps", 12),
        "tex_steps": _int("tex_steps", 12),
        "face_count_high": _int("face_count_high", 500_000),
        "face_count_low": _int("face_count_low", 20_000),
        "label": request.form.get("label", "object"),
    }

    try:
        from PIL import Image
        image = Image.open(request.files["image"].stream).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"could not decode image: {exc}"}), 400

    logger.info("generate '%s': %dx%d seed=%d res=%s",
                params["label"], image.width, image.height,
                params["seed"], params["resolution"])
    try:
        glb_high, glb_low, timings = _generate(image, params)
    except ImportError as exc:
        return jsonify({"error": (
            "native TRELLIS.2 env not available in this interpreter: "
            f"{exc}. Stand up the pinned env per PRD v4 R5 / ADR-021, or "
            "leave trellis2.native_url empty to use the ComfyUI executor."
        )}), 503
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the service
        logger.exception("generation failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "glb_high_b64": base64.b64encode(glb_high).decode("ascii"),
        "glb_low_b64": base64.b64encode(glb_low).decode("ascii"),
        "lineage": {
            "generator": "TRELLIS.2-4B",
            "executor": "native-service",
            "model_path": MODEL_PATH,
            **params,
            "timings": timings,
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (loopback by default, ADR-022)")
    parser.add_argument("--port", type=int, default=8402)
    parser.add_argument("--preload", action="store_true",
                        help="Load the pipeline at startup instead of first request")
    args = parser.parse_args()
    if args.preload:
        _load_pipeline()
    app.run(host=args.host, port=args.port, threaded=False)


if __name__ == "__main__":
    main()
