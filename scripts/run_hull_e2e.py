#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Slice-A hull end-to-end: a single per-object Gaussian PLY -> a 360 PBR GLB.

Exercises the NEW object-reconstruction path on real reconstructed data
(skipping the multi-hour COLMAP + 3DGS front-end): orbit-render the splat (6
panels) -> coverage-gated FLUX.2 view completion for unobserved panels ->
TRELLIS.2 multiview -> PBR-textured GLB, with serial /free VRAM management.

Run inside the gaussian-toolkit container (has the pipeline deps + reaches
vitrine-comfyui):

    docker run --rm --runtime nvidia --network v2g-net \
        -e PYTHONPATH=/repo/src -v <repo>:/repo -w /repo \
        gaussian-toolkit:latest \
        python3 scripts/run_hull_e2e.py output/e2e_run1/objects/sculptures.ply sculptures

Args: <ply_path> [label] [--no-view-completion]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hull_e2e")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    ply = Path(argv[0])
    label = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ply.stem
    use_completion = "--no-view-completion" not in argv
    if not ply.exists():
        log.error("PLY not found: %s", ply)
        return 1

    from pipeline.config import Trellis2Config, ViewCompletionConfig
    from pipeline.trellis2_client import Trellis2Client

    t2cfg = Trellis2Config()
    client = Trellis2Client.from_config(t2cfg)
    log.info("ComfyUI: %s | resolution=%s texture_size=%s",
             client.comfyui_url, client.resolution, client.texture_size)
    if not client.health_check():
        log.error("ComfyUI not reachable at %s — is vitrine-comfyui up + on this network?",
                  client.comfyui_url)
        return 1

    if use_completion:
        try:
            from pipeline.view_completer import ViewCompleter
            client.view_completer = ViewCompleter.from_config(ViewCompletionConfig())
            log.info("FLUX.2 view completion ENABLED (coverage-gated)")
        except Exception as e:  # noqa: BLE001
            log.warning("view completer unavailable: %s", e)

    out_dir = Path("output/hull_e2e")
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / f"{label}_work"

    log.info("=== Slice-A hull e2e: %s (label=%s) ===", ply, label)
    t0 = time.monotonic()
    result = client.reconstruct_from_gaussians(
        ply, label=label, work_dir=work_dir, object_desc={"label": label},
    )
    elapsed = time.monotonic() - t0

    print("\n================ HULL E2E REPORT ================")
    print(f"  object        : {label}")
    print(f"  backend       : {result.backend}")
    print(f"  views rendered: {result.views_rendered}")
    print(f"  prompt_id     : {result.prompt_id}")
    print(f"  wall time     : {elapsed:.1f}s")
    if result.mesh is not None:
        glb_path = out_dir / f"{label}_hull.glb"
        result.mesh.export(str(glb_path))
        print(f"  RESULT        : OK")
        print(f"  vertices      : {result.vertex_count}")
        print(f"  faces         : {result.face_count}")
        print(f"  glb           : {glb_path} ({glb_path.stat().st_size/1e6:.1f} MB)")
        print("================================================")
        return 0
    print(f"  RESULT        : FAILED — {result.error}")
    print("================================================")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
