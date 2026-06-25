#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end downstream re-validation after the DiffusionGemma LLM rewire.

Runs preflight (which now includes the DiffusionGemma agent-LLM connectivity
probe) followed by the decompose -> mesh -> dual-USD path into output/e2e_run3,
REUSING the validated output/e2e_run2 trained splat + COLMAP (no 30k retrain).
The rewire does not touch the decompose/mesh/USD logic, so this confirms (a) the
new config/registry/preflight wiring runs clean in the real container env, and
(b) the object-resolved, dual-USD output still reproduces.

Each stage is captured (not asserted) so a single failure still yields a full
report. Run inside the gaussian-toolkit image. CLI: python scripts/e2e_downstream_validate.py
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline import preflight  # noqa: E402
from pipeline.config import PipelineConfig  # noqa: E402
from pipeline.stages import PipelineStages  # noqa: E402

SRC = ROOT / "output" / "e2e_run2"
RUN = ROOT / "output" / "e2e_run3"
PLY = SRC / "model" / "splat_30000.ply"
FRAMES = ROOT / "output" / "milo_run" / "images"


def banner(t: str) -> None:
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72, flush=True)


def main() -> int:
    banner("PREFLIGHT (deps + SOTA idiot-check + DiffusionGemma agent-LLM probe)")
    try:
        preflight.print_report()
    except Exception as e:  # noqa: BLE001
        print(f"  preflight raised (continuing): {e}")

    if not PLY.exists():
        print(f"FATAL: reused splat missing: {PLY}")
        return 1
    if not FRAMES.exists():
        print(f"FATAL: source frames missing: {FRAMES}")
        return 1

    RUN.mkdir(parents=True, exist_ok=True)
    if not (RUN / "colmap").exists():
        print(f"reusing COLMAP: {SRC/'colmap'} -> {RUN/'colmap'}", flush=True)
        shutil.copytree(SRC / "colmap", RUN / "colmap")

    cfg = PipelineConfig()
    errs = cfg.validate()
    print(f"config.validate(): {errs or 'OK'}", flush=True)
    print(f"agent LLM endpoint: {cfg.endpoints.agent_llm_url} "
          f"({cfg.endpoints.agent_llm_model})", flush=True)

    p = PipelineStages(str(RUN), config=cfg)
    t0 = time.monotonic()

    banner("SEGMENT (SAM3 concept seg + per-frame masks)")
    r = p.segment(str(PLY), str(FRAMES))
    print(f"  segment: {'OK' if r.success else 'FAIL'} {r.metrics} {r.error or ''}", flush=True)
    objs = r.artifacts.get("objects", "[]") if r.success else "[]"

    banner("EXTRACT OBJECTS (ADR-010 D10 depth-aware multi-view projection)")
    r = p.extract_objects(str(PLY), labels=objs)
    print(f"  extract_objects: {'OK' if r.success else 'FAIL'} {r.metrics} {r.error or ''}", flush=True)
    plys = r.artifacts.get("object_plys", "[]") if r.success else "[]"

    banner("MESH OBJECTS (gsplat-TSDF)")
    r = p.mesh_objects(plys)
    print(f"  mesh_objects: {'OK' if r.success else 'FAIL'} {r.metrics} {r.error or ''}", flush=True)
    meshes = r.artifacts.get("meshes", "[]") if r.success else "[]"

    banner("TEXTURE BAKE")
    try:
        r = p.texture_bake(meshes)
        print(f"  texture_bake: {'OK' if r.success else 'FAIL'} {r.metrics} {r.error or ''}", flush=True)
        meshes = r.artifacts.get("textured_meshes", meshes)
    except Exception as e:  # noqa: BLE001
        print(f"  texture_bake raised (continuing): {e}", flush=True)

    banner("ASSEMBLE USD (native LichtFeld convert + composed Blender USD)")
    r = p.assemble_usd(meshes)
    print(f"  assemble_usd: {'OK' if r.success else 'FAIL'} {r.metrics} {r.error or ''}", flush=True)

    banner(f"ARTIFACTS  (elapsed {time.monotonic()-t0:.0f}s)")
    objdir = RUN / "objects"
    for f in sorted(objdir.glob("*.ply")):
        print(f"  PLY  {f.name:18} {f.stat().st_size/1e6:8.2f} MB", flush=True)
    for f in sorted(RUN.rglob("*.usd*")):
        print(f"  USD  {f.relative_to(RUN)}  {f.stat().st_size/1e6:8.2f} MB", flush=True)
    for f in sorted((RUN / "previews").glob("*.png")) if (RUN/"previews").exists() else []:
        print(f"  PNG  {f.name}", flush=True)
    print("E2E_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
