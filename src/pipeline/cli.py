# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""CLI entry point: python -m pipeline.cli video2scene <video> <output> [options]

Runs the pipeline stages sequentially. For interactive use with Claude Code,
import PipelineStages directly and call stages individually.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from pipeline.config import PipelineConfig
from pipeline.stages import PipelineStages, STAGE_NAMES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Gaussian Toolkit video-to-scene pipeline (stage-based)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- video2scene ---
    v2s = sub.add_parser("video2scene", help="Run the full video-to-scene pipeline")
    v2s.add_argument("video", help="Path to input video file")
    v2s.add_argument("output", help="Output directory")
    v2s.add_argument("--config", "-c", help="Path to pipeline config JSON")
    v2s.add_argument("--fps", type=float, help="Frame extraction FPS")
    v2s.add_argument("--max-iter", type=int, help="Max training iterations")
    v2s.add_argument("--strategy", choices=["mcmc", "mrnf", "default"], help="Training strategy")
    v2s.add_argument("--objects", nargs="*", help="Object descriptions for decomposition")
    v2s.add_argument("--target-psnr", type=float, help="Target PSNR threshold")
    v2s.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    v2s.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    # --- objects (ADR-025 object arc on an existing run) ---
    obj = sub.add_parser(
        "objects",
        help="Run the object arc (segment → crops → isolate → generate) on an "
             "existing trained run directory",
    )
    obj.add_argument("job_dir", help="Existing run directory (contains model/ + frames)")
    obj.add_argument("--config", "-c", help="Path to pipeline config JSON")
    obj.add_argument("--concepts", nargs="*",
                     help="SAM3 concepts to segment (default: config list)")
    obj.add_argument("--frames-dir", help="Frames directory (default: auto-detect)")
    obj.add_argument("--ply", help="Trained PLY (default: newest under model/)")
    obj.add_argument("--skip-segment", action="store_true",
                     help="Reuse existing sam3_masks/ instead of re-running SAM3")
    obj.add_argument("--verbose", "-v", action="store_true")
    obj.add_argument("--quiet", "-q", action="store_true")

    # --- config ---
    cfg_cmd = sub.add_parser("config", help="Manage pipeline configuration")
    cfg_sub = cfg_cmd.add_subparsers(dest="config_action", required=True)

    cfg_show = cfg_sub.add_parser("show", help="Show default config")
    cfg_show.add_argument("--output", "-o", help="Write to file instead of stdout")

    cfg_validate = cfg_sub.add_parser("validate", help="Validate a config file")
    cfg_validate.add_argument("file", help="Config file to validate")

    # --- status ---
    st = sub.add_parser("status", help="Show pipeline status for a job directory")
    st.add_argument("job_dir", help="Path to the job output directory")

    return parser


def _apply_overrides(config: PipelineConfig, args: argparse.Namespace) -> None:
    if getattr(args, "fps", None) is not None:
        config.ingest.fps = args.fps
    if getattr(args, "max_iter", None) is not None:
        config.training.max_iterations = args.max_iter
        config.training.iterations = args.max_iter
    if getattr(args, "strategy", None) is not None:
        config.training.strategy = args.strategy
    if getattr(args, "objects", None) is not None:
        config.decompose.descriptions = args.objects
    if getattr(args, "target_psnr", None) is not None:
        config.training.target_psnr = args.target_psnr
        config.quality.gate1_min_psnr = args.target_psnr * 0.8


def _setup_logging(verbose: bool, quiet: bool) -> None:
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_video2scene(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose, args.quiet)

    if args.config:
        config = PipelineConfig.load(args.config)
    else:
        config = PipelineConfig()

    _apply_overrides(config, args)

    errors = config.validate()
    if errors:
        for err in errors:
            print(f"Config error: {err}", file=sys.stderr)
        return 1

    video = Path(args.video)
    if not video.exists():
        print(f"Error: video not found: {video}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fps = args.fps or config.ingest.fps
    iterations = args.max_iter or config.training.iterations

    p = PipelineStages(str(output), config=config)

    print(f"Pipeline: {video} -> {output}")
    print(f"Strategy: {config.training.strategy}, iterations: {iterations}")

    start = time.monotonic()
    all_artifacts: dict[str, str] = {}

    # Stage 1: Ingest
    print("\n--- Ingest ---")
    result = p.ingest(str(video), fps=fps)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    frames_dir = result.artifacts["frames_dir"]

    # Stage 2: Remove people (auto-skip if disabled)
    print("\n--- Remove People ---")
    result = p.remove_people(frames_dir)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    frames_dir = result.artifacts.get("cleaned_frames_dir", frames_dir)

    # Stage 3: Select frames
    print("\n--- Select Frames ---")
    result = p.select_frames(frames_dir)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    frames_dir = result.artifacts.get("selected_frames_dir", frames_dir)

    # Stage 4: Reconstruct
    print("\n--- Reconstruct ---")
    result = p.reconstruct(frames_dir)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    colmap_dir = result.artifacts["colmap_dir"]

    # Stage 5: Train
    print("\n--- Train ---")
    result = p.train(colmap_dir, iterations=iterations)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    ply_path = result.artifacts["ply_path"]

    # Stage 6: Segment
    print("\n--- Segment ---")
    result = p.segment(ply_path, frames_dir)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    objects_json = result.artifacts.get("objects", "[]")

    # Stage 6b: Object crops (ADR-025 — generator conditioning input)
    print("\n--- Object Crops ---")
    result = p.object_crops(frames_dir, objects=objects_json)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    crops_json = result.artifacts.get("object_crops", "[]")

    # Stage 7: Extract objects (pose/scale only — never generator pixels)
    print("\n--- Extract Objects ---")
    result = p.extract_objects(ply_path, labels=objects_json)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    object_plys = result.artifacts.get("object_plys", "[]")

    # Stage 8: Mesh objects
    print("\n--- Mesh Objects ---")
    result = p.mesh_objects(object_plys, crops=crops_json)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    if not result.success:
        print(f"  Error: {result.error}", file=sys.stderr)
        return 1
    all_artifacts.update(result.artifacts)
    meshes_json = result.artifacts.get("meshes", "[]")

    # Stage 9: Texture bake
    print("\n--- Texture Bake ---")
    result = p.texture_bake(meshes_json)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    meshes_json = result.artifacts.get("textured_meshes", meshes_json)

    # Stage 10: Assemble USD
    print("\n--- Assemble USD ---")
    result = p.assemble_usd(meshes_json)
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
    all_artifacts.update(result.artifacts)

    # Stage 11: Validate
    print("\n--- Validate ---")
    result = p.validate()
    print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")

    elapsed = time.monotonic() - start
    if result.success:
        print(f"\nPipeline completed in {elapsed:.1f}s")
        for name, path in all_artifacts.items():
            if path and not name.startswith("ply:") and not name.startswith("mesh:"):
                print(f"  {name}: {path}")
        return 0
    else:
        print(f"\nPipeline finished with validation errors after {elapsed:.1f}s")
        return 1


def cmd_objects(args: argparse.Namespace) -> int:
    """ADR-025 object arc on an existing trained run.

    Runs segment → object_crops → extract_objects → mesh_objects →
    texture_bake against a run that already has frames + a trained splat, so
    object generation can be iterated without repeating the multi-hour
    COLMAP/training front-end. This is the committed form of the flow that
    produced the first validated automated objects (rawcapdev, 2026-07-09).
    """
    _setup_logging(args.verbose, args.quiet)

    config = PipelineConfig.load(args.config) if args.config else PipelineConfig()
    if args.concepts:
        config.decompose.sam3_concepts = args.concepts

    job_dir = Path(args.job_dir)
    if not job_dir.is_dir():
        print(f"Error: job dir not found: {job_dir}", file=sys.stderr)
        return 1

    # Trained PLY: explicit flag, else the newest model checkpoint.
    if args.ply:
        ply_path = Path(args.ply)
    else:
        candidates = sorted(job_dir.glob("model/**/*.ply")) or sorted(
            job_dir.glob("model/*.ply"))
        if not candidates:
            print(f"Error: no trained PLY under {job_dir}/model — pass --ply",
                  file=sys.stderr)
            return 1
        ply_path = candidates[-1]

    # Frames: explicit flag, else the standard candidates in preference order.
    if args.frames_dir:
        frames_dir = Path(args.frames_dir)
    else:
        frames_dir = next(
            (d for n in ("frames_selected", "frames_cleaned", "frames", "input")
             if (d := job_dir / n).is_dir()), None)
        if frames_dir is None:
            print(f"Error: no frames directory under {job_dir} — pass --frames-dir",
                  file=sys.stderr)
            return 1

    p = PipelineStages(str(job_dir), config=config)
    print(f"Object arc: {job_dir}\n  ply    = {ply_path}\n  frames = {frames_dir}")

    def _run(name: str, fn, *fargs, fatal: bool = True, **kw):
        print(f"\n--- {name} ---")
        result = fn(*fargs, **kw)
        print(f"  {result.stage}: {'OK' if result.success else 'FAIL'} {result.metrics}")
        if not result.success:
            print(f"  Error: {result.error}", file=sys.stderr)
            if fatal:
                raise SystemExit(1)
        return result

    if args.skip_segment:
        masks_dir = job_dir / "sam3_masks"
        objects_json = "[]"
        # Rebuild the object list from the persisted masks + crops manifest if
        # present; otherwise segment metadata must be re-derived.
        manifest = job_dir / "object_crops" / "crops.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            objects_json = json.dumps([
                {"label": c["label"], "object_id": c["object_id"], "mask_pixels": 1}
                for c in data.get("crops", [])
            ])
        elif not masks_dir.exists():
            print("Error: --skip-segment but no sam3_masks/ to reuse", file=sys.stderr)
            return 1
        print("\n--- Segment (skipped — reusing existing masks) ---")
    else:
        result = _run("Segment", p.segment, str(ply_path), str(frames_dir))
        objects_json = result.artifacts.get("objects", "[]")

    result = _run("Object Crops", p.object_crops, str(frames_dir),
                  objects=objects_json)
    crops_json = result.artifacts.get("object_crops", "[]")

    result = _run("Extract Objects", p.extract_objects, str(ply_path),
                  labels=objects_json)
    object_plys = result.artifacts.get("object_plys", "[]")

    result = _run("Mesh Objects", p.mesh_objects, object_plys, crops=crops_json)
    meshes_json = result.artifacts.get("meshes", "[]")

    _run("Texture Bake", p.texture_bake, meshes_json, fatal=False)

    meshes = json.loads(meshes_json)
    print(f"\nObject arc complete: {len(meshes)} asset(s)")
    for m in meshes:
        tag = " [generator, PBR verbatim]" if m.get("generator") else ""
        print(f"  {m.get('label')}: {m.get('mesh')}{tag}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if args.config_action == "show":
        config = PipelineConfig()
        text = json.dumps(config.to_dict(), indent=2, default=str)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"Config written to {args.output}")
        else:
            print(text)
        return 0

    elif args.config_action == "validate":
        try:
            config = PipelineConfig.load(args.file)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error loading config: {exc}", file=sys.stderr)
            return 1

        errors = config.validate()
        if errors:
            for err in errors:
                print(f"  FAIL: {err}", file=sys.stderr)
            return 1
        print("Config is valid.")
        return 0

    return 1


def cmd_status(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_dir)
    if not job_dir.exists():
        print(f"Job directory not found: {job_dir}", file=sys.stderr)
        return 1

    config = PipelineConfig()
    p = PipelineStages(str(job_dir), config=config)
    status = p.status()
    print(json.dumps(status, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "video2scene": cmd_video2scene,
        "objects": cmd_objects,
        "config": cmd_config,
        "status": cmd_status,
    }
    handler = dispatch.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
