#!/usr/bin/env python3
"""Generate a Vitrine exhibit scene.usda from an e2e pipeline run.

Reads the hull GLB, splat PLY, and view completion metadata from a pipeline
output directory and writes a properly-structured scene.usda with v2g:*
lineage metadata (ADR-011/016).

Usage:
    python3 scripts/generate_exhibit_usd.py \
        --job-dir output/e2e_run1 \
        --hull output/hull_e2e/sculptures_hull.glb \
        --label sculptures \
        --hull-backend trellis2-4b-mv-pbr \
        --hull-vertices 280799 \
        --hull-faces 461352 \
        --view-synth front,back \
        -o output/exhibit/scene.usda
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline.usd_assembler import ObjectDescriptor, UsdSceneAssembler


def main() -> None:
    p = argparse.ArgumentParser(description="Generate exhibit scene.usda")
    p.add_argument("--job-dir", required=True, help="Pipeline job output dir")
    p.add_argument("--hull", required=True, help="Path to hull GLB")
    p.add_argument("--label", required=True, help="Object label")
    p.add_argument("--hull-backend", default="trellis2-4b-mv-pbr")
    p.add_argument("--hull-vertices", type=int, default=0)
    p.add_argument("--hull-faces", type=int, default=0)
    p.add_argument("--view-synth", default="", help="Comma-separated synthesised view names")
    p.add_argument("--splat", default=None, help="Path to gaussian PLY")
    p.add_argument("--confidence", type=float, default=1.0)
    p.add_argument("-o", "--output", required=True, help="Output scene.usda path")
    args = p.parse_args()

    job_dir = Path(args.job_dir)
    hull_path = Path(args.hull)
    output_path = Path(args.output)

    splat_path = args.splat
    if splat_path is None:
        candidates = list(job_dir.glob("objects/*.ply"))
        if candidates:
            splat_path = str(candidates[0])

    view_synth = [v.strip() for v in args.view_synth.split(",") if v.strip()]

    assembler = UsdSceneAssembler(up_axis="Y", meters_per_unit=1.0)

    obj = ObjectDescriptor(
        name=args.label,
        hull_glb_path=str(hull_path),
        hull_backend=args.hull_backend,
        hull_vertices=args.hull_vertices,
        hull_faces=args.hull_faces,
        view_synth_views=view_synth,
        confidence=args.confidence,
        metadata={
            "v2g:source_job": str(job_dir),
            "v2g:source_splat": splat_path or "",
        },
    )

    if splat_path:
        obj.metadata["v2g:gaussian_ply"] = splat_path

    assembler.add_object(obj)
    assembler.set_metadata("job_dir", str(job_dir))
    if splat_path:
        assembler.set_metadata("gaussian_ply", splat_path)

    stage = assembler.write(output_path)
    print(f"Wrote {output_path}")

    for prim in stage.Traverse():
        cd = prim.GetCustomData() or {}
        v2g = {k: v for k, v in cd.items() if str(k).startswith("v2g:")}
        if v2g:
            print(f"  {prim.GetPath()}: {v2g}")


if __name__ == "__main__":
    main()
