#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Object e2e smoke test: ONE matted crop -> a PBR-textured GLB (ADR-025).

Exercises the single-image object-generation path on a real object_crops
output (skipping the multi-hour COLMAP + 3DGS + segment front-end):
crop -> TRELLIS.2 single-image (ComfyUI executor or native service, per
config) -> PBR GLB persisted byte-identical, graded by the R9 mesh stats.

The predecessor of this script drove the RETIRED splat-render multiview
path (orbit panels + FLUX view completion); see ADR-025 / audit 2026-07-09.

Run inside the gaussian-toolkit container (has the pipeline deps + reaches
vitrine-comfyui):

    python3 scripts/run_hull_e2e.py \
        /data/output/rawcapdev/object_crops/0001_metal_container.png [label] [seed]
"""
from __future__ import annotations

import hashlib
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("object_e2e")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    crop = Path(argv[0])
    label = argv[1] if len(argv) > 1 else crop.stem
    seed = int(argv[2]) if len(argv) > 2 else 42
    if not crop.exists():
        log.error("Crop not found: %s", crop)
        return 1

    from pipeline.config import Trellis2Config
    from pipeline.trellis2_client import Trellis2Client

    client = Trellis2Client.from_config(Trellis2Config())
    executor = client.native_url or client.comfyui_url
    log.info("executor: %s | resolution=%s texture_size=%s seed=%d",
             executor, client.resolution, client.texture_size, seed)
    if not client.health_check():
        log.error("Executor not reachable at %s — is vitrine-comfyui up + on "
                  "this network?", executor)
        return 1

    out_dir = Path("/data/output/object_e2e")
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== object e2e (single-image): %s (label=%s) ===", crop, label)
    t0 = time.monotonic()
    result = client.reconstruct_from_image(crop, seed=seed, label=label)
    elapsed = time.monotonic() - t0

    print("\n================ OBJECT E2E REPORT ================")
    print(f"  object     : {label}")
    print(f"  crop       : {crop}")
    print(f"  backend    : {result.backend}")
    print(f"  prompt_id  : {result.prompt_id}")
    print(f"  wall time  : {elapsed:.1f}s")
    if result.glb_data:
        glb_path = out_dir / f"{label}.glb"
        glb_path.write_bytes(result.glb_data)          # verbatim (PRD v4 R6)
        sha = hashlib.sha256(result.glb_data).hexdigest()
        print(f"  RESULT     : OK")
        print(f"  vertices   : {result.vertex_count}")
        print(f"  faces      : {result.face_count}")
        print(f"  glb        : {glb_path} ({len(result.glb_data)/1e6:.1f} MB)")
        print(f"  sha256     : {sha[:16]}…")
        print(f"  lineage    : {result.lineage}")
        print("===================================================")
        return 0
    print(f"  RESULT     : FAILED — {result.error}")
    print("===================================================")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
