# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Thin job-queue layer for the web pipeline.

Claude Code is the orchestrator. This module only:
1. Saves uploaded videos to the job directory
2. Sets job state to "queued"
3. Provides an API for Claude Code to update job progress

The old PipelineRunner that drove the state machine is removed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Persistent API key location (same as app.py)
_API_KEY_PATH = Path(os.environ.get("LFS_API_KEY_PATH", "/data/.anthropic_key"))


def queue_job(job_id: str) -> bool:
    """Mark a job as queued for Claude Code to pick up.

    Copies the input video into the job output directory so
    Claude Code can find it at a known location.

    Returns False if the job doesn't exist.
    """
    from web.job_manager import get_job, update_job, append_log, JobState

    job = get_job(job_id)
    if job is None:
        logger.error("Job %s not found", job_id)
        return False

    # Ensure output directory exists
    output_dir = Path(job.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage the capture into the job directory so Claude Code can find it.
    input_kind = getattr(job, "input_kind", "video")
    if input_kind == "images" and job.input_dir and Path(job.input_dir).exists():
        # PREFERRED capture: raw/still images serve as frames — no frame
        # extraction needed. DECODE them to COLMAP-native images (DNG/CR2/HEIC/…
        # can't be read by COLMAP or the IQA gate) as they are staged under
        # input/images/, so the downstream flow has no format blockers.
        images_src = Path(job.input_dir)
        images_dst = output_dir / "input" / "images"
        images_dst.mkdir(parents=True, exist_ok=True)

        manifest = None
        try:
            from pipeline.image_decoder import decode_directory
            manifest = decode_directory(
                images_src, images_dst, log=lambda m: append_log(job_id, m)
            )
        except Exception as exc:  # decode module/deps unavailable — never block
            logger.error("decode stage unavailable, copying images as-is: %s", exc)
            append_log(job_id, f"WARN: decode stage unavailable ({exc}); copying images as-is")
            for f in sorted(images_src.iterdir()):
                if f.is_file():
                    t = images_dst / f.name
                    if not t.exists():
                        shutil.copy2(str(f), str(t))

        ready = (
            manifest["native"] + manifest["decoded"]
            if manifest else sum(1 for p in images_dst.iterdir() if p.is_file())
        )
        if ready == 0:
            append_log(job_id, "ERROR: no usable images after decode — nothing to reconstruct")
            update_job(job_id, state=JobState.FAILED, error="No usable images after decode")
            return False
        capture = {"kind": "images", "images_dir": str(images_dst), "ready_images": ready}
        if manifest:
            capture["decode"] = manifest
        (output_dir / "capture.json").write_text(json.dumps(capture, indent=2))
        append_log(
            job_id,
            f"Image capture ready: {ready} COLMAP-native image(s) at {images_dst} "
            f"— frame extraction not required",
        )
        if manifest and manifest.get("failed"):
            append_log(
                job_id,
                f"WARN: {manifest['failed']} image(s) could not be decoded: "
                f"{manifest['failures'][:8]}",
            )
    else:
        # VIDEO capture: copy the file in and provide an input.mp4 convenience link.
        input_path = Path(job.input_video_path) if job.input_video_path else None
        if input_path and input_path.exists() and input_path.is_file():
            target = output_dir / "input" / input_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(str(input_path), str(target))

            link = output_dir / "input.mp4"
            if not link.exists():
                try:
                    link.symlink_to(target)
                except OSError:
                    shutil.copy2(str(target), str(link))
        (output_dir / "capture.json").write_text(json.dumps(
            {"kind": "video", "filename": job.filename}, indent=2,
        ))

    update_job(job_id, state=JobState.QUEUED)
    append_log(job_id, f"Job queued for Claude Code: {job.filename}")
    append_log(job_id, f"Job directory: {job.output_dir}")

    # Attempt to auto-launch Claude Code if an API key is available
    launched = _launch_claude_code(
        job_id, job.output_dir, input_kind=input_kind,
        image_count=getattr(job, "image_count", 0),
    )
    if launched:
        append_log(job_id, "Claude Code launched automatically (API key or Claude subscription session)")
    else:
        append_log(
            job_id,
            "No Claude auth yet. Open the Terminal tab and run: "
            "claude --dangerously-skip-permissions  then  /login  "
            "(log in with your Claude subscription — no API key needed). "
            "This job is queued and will be picked up.",
        )

    return True


def _has_oauth_session() -> bool:
    """True if a Claude Code subscription (OAuth) session exists on disk.

    Provisioned by logging in from the web terminal
    (``claude --dangerously-skip-permissions`` then ``/login``). Persists in the
    ``claude-session`` volume mounted at ``/home/ubuntu/.claude``.
    """
    for p in (
        Path("/home/ubuntu/.claude/.credentials.json"),
        Path.home() / ".claude" / ".credentials.json",
    ):
        try:
            if p.exists() and p.stat().st_size > 10:
                return True
        except OSError:
            pass
    return False


def _launch_claude_code(
    job_id: str, output_dir: str, input_kind: str = "video", image_count: int = 0
) -> bool:
    """Launch Claude Code as a background subprocess to process the job.

    Reads the API key from the persistent volume. If no key is stored,
    returns False (the user must run Claude Code manually via the terminal).
    """
    # Internal-Claude enablement gate (ADR-024). Unless the operator opted in at
    # setup (VITRINE_CLAUDE_ENABLED=1), the in-container Claude intelligence is
    # OFF: never auto-launch Claude Code. The job stays queued and the only
    # operator surface is the web upload + runtime-feedback panel.
    _enabled = str(os.environ.get("VITRINE_CLAUDE_ENABLED", "0")).strip().lower()
    if _enabled not in ("1", "true", "yes", "on"):
        logger.info(
            "VITRINE_CLAUDE_ENABLED is not set — internal Claude disabled; "
            "skipping auto-launch (job queued, web panel remains the only I/O)."
        )
        return False

    # Check for API key or OAuth session. Either is sufficient — a Claude
    # subscription login (OAuth, provisioned via the web terminal) overrides
    # the need for an Anthropic API key. Don't auto-launch with no auth at all;
    # the job stays queued for manual pickup in the terminal instead.
    api_key = None
    if _API_KEY_PATH.exists():
        api_key = _API_KEY_PATH.read_text().strip() or None

    if not api_key and not _has_oauth_session():
        logger.info("No Claude auth (API key or subscription session) — skipping auto-launch")
        return False

    if input_kind == "images":
        capture_line = (
            f"This is an IMAGE capture: {image_count} photos have already been decoded "
            f"to COLMAP-native images at {output_dir}/input/images and serve as the "
            f"capture frames (raw/DNG/HEIC were converted by the decode stage — see "
            f"capture.json). SKIP the ingest (frame-extraction) stage entirely; use that "
            f"directory as the frames directory. Then run: select_frames → reconstruct → "
        )
    else:
        capture_line = (
            f"This is a VIDEO capture at {output_dir}/input.mp4. "
            f"Run ALL stages: ingest → select_frames → reconstruct → "
        )

    prompt = (
        f"Process the pipeline job at {output_dir}. "
        f"Job ID is {job_id}. "
        f"Follow the instructions in CLAUDE.md step by step. "
        f"{capture_line}"
        f"train → segment → extract_objects → mesh_objects → assemble_usd → validate. "
        f"Do NOT stop after training. Continue through segmentation, mesh extraction, "
        f"and USD assembly. "
        f"Report progress to the web API at http://localhost:7860/api/job/{job_id}/stage "
        f"and mark completion at http://localhost:7860/api/job/{job_id}/complete"
    )

    # Build environment — web interface runs as ubuntu user so
    # Claude Code has direct access to OAuth session in ~/.claude/
    env = {**os.environ, "TERM": "xterm-256color"}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    # If no API key, Claude Code uses the OAuth session from ~/.claude/

    claude_bin = "/usr/local/bin/claude"
    cmd = [
        claude_bin,
        "--dangerously-skip-permissions",
        "-p", prompt,
        "--allowedTools", "Bash,Read,Write,Edit",
    ]

    logger.info("Launching Claude Code: %s", " ".join(cmd[:4]) + " ...")

    try:
        log_path = Path(output_dir) / "claude_launch.log"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            cmd,
            cwd="/opt/gaussian-toolkit",
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        logger.info("Launched Claude Code (pid=%d) for job %s, log: %s", proc.pid, job_id, log_path)
        return True
    except FileNotFoundError:
        logger.warning("Claude Code binary not found at %s — cannot auto-launch", claude_bin)
        return False
    except Exception as exc:
        logger.error("Failed to launch Claude Code for job %s: %s", job_id, exc)
        return False


def update_stage(job_id: str, stage: str, progress: float = 0.0, message: str = "") -> bool:
    """Called by Claude Code (via REST API) to report stage progress.

    Args:
        job_id: The job identifier.
        stage: Current stage name (e.g. "train", "segment").
        progress: Overall progress 0.0-1.0.
        message: Optional status message (e.g. "30k iter, loss 0.02").

    Returns False if the job doesn't exist.
    """
    from web.job_manager import get_job, update_job, append_log, set_stage_status, JobState

    job = get_job(job_id)
    if job is None:
        return False

    update_job(job_id, state=JobState.RUNNING, progress=progress, current_stage=stage)
    set_stage_status(job_id, stage, "running")

    if message:
        append_log(job_id, f"[{stage}] {message}")

    return True


def complete_stage(job_id: str, stage: str, success: bool = True, error: str = "") -> bool:
    """Mark a stage as completed or failed.

    Args:
        job_id: The job identifier.
        stage: Stage name that just finished.
        success: Whether the stage succeeded.
        error: Error message if failed.
    """
    from web.job_manager import get_job, append_log, set_stage_status

    job = get_job(job_id)
    if job is None:
        return False

    status = "completed" if success else "failed"
    set_stage_status(job_id, stage, status, error=error if not success else None)

    if success:
        append_log(job_id, f"Stage {stage} completed")
    else:
        append_log(job_id, f"Stage {stage} FAILED: {error}")

    return True


# ---------------------------------------------------------------------------
# Web splat derivative (mkkellogg .ksplat) -- additive, post-training stage.
# ---------------------------------------------------------------------------
#
# Emits output/<id>/web/scene.ksplat for the embedded @mkkellogg/gaussian-splats-3d
# viewer.  Gated on the converter being available in-image (see
# pipeline.splat_optimizer for the compatibility verdict: splat-transform cannot
# produce this bitstream).  When the converter is unavailable the stage skips
# cleanly and the viewer falls back to progressive-loading the trained .ply.
#
# INVARIANT: the source trained .ply is only ever read here -- never mutated,
# moved, or renamed (it is the source-of-truth for the NanoGS/UE + mesh handoff).

# Web derivative filename the splat route discovers first (output/<id>/web/…).
_WEB_KSPLAT_NAME = "scene.ksplat"

# Directories that never hold the trained *scene* PLY (objects, derivatives).
_NON_SCENE_PLY_TOPS = {"objects", "web", "delivery", "usd"}


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, streamed in 1 MiB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iteration_number(name: str) -> int:
    """Parse the trailing integer from an ``iteration_<N>`` directory name."""
    try:
        return int(name.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return -1


def _find_trained_scene_ply(output_dir: Path) -> Path | None:
    """Locate the trained *scene* Gaussian PLY (source-of-truth).

    Never returns a per-object reconstruction or an already-optimised
    derivative.  Discovery order mirrors the pipeline's own layout
    (CLAUDE_CONTAINER.md): ``model/splat_30000.ply`` -> ``splat/scene.ply`` ->
    highest-iteration ``model/point_cloud/iteration_*/point_cloud.ply`` ->
    largest ``model/*.ply`` -> largest PLY elsewhere (objects/derivatives
    excluded).
    """
    named = [
        output_dir / "model" / "splat_30000.ply",
        output_dir / "splat" / "scene.ply",
    ]
    for p in named:
        if p.is_file() and p.stat().st_size > 0:
            return p

    model_dir = output_dir / "model"
    if model_dir.is_dir():
        iter_plys = sorted(
            model_dir.glob("point_cloud/iteration_*/point_cloud.ply"),
            key=lambda q: _iteration_number(q.parent.name),
        )
        iter_plys = [q for q in iter_plys if q.stat().st_size > 0]
        if iter_plys:
            return iter_plys[-1]

        splat_plys = [
            q for q in model_dir.glob("splat_*.ply") if q.stat().st_size > 0
        ]
        if splat_plys:
            return max(splat_plys, key=lambda q: q.stat().st_size)

        model_plys = [q for q in model_dir.glob("*.ply") if q.stat().st_size > 0]
        if model_plys:
            return max(model_plys, key=lambda q: q.stat().st_size)

    candidates = [
        p
        for p in output_dir.rglob("*.ply")
        if p.is_file()
        and p.stat().st_size > 0
        and (p.relative_to(output_dir).parts[:1] or [""])[0]
        not in _NON_SCENE_PLY_TOPS
    ]
    if candidates:
        return max(candidates, key=lambda q: q.stat().st_size)
    return None


def _record_web_derivative_stage(job_id: str, status: str, **extra: Any) -> None:
    """Durably record the web-derivative outcome in the job's ``stages`` dict.

    Uses a load-merge-save through the job_manager public API so the entry
    survives later ``asdict``-based saves (a bare undeclared attribute would
    not).  ``web_splat_path`` is also mirrored to the top level via
    ``update_job`` for forward compatibility with a ``Job.web_splat_path``
    field (surfaces as ``ksplat_path`` in the scenes API); that call is a
    harmless no-op until the field is declared.
    """
    from web.job_manager import get_job, update_job

    job = get_job(job_id)
    if job is None:
        return

    stages = dict(job.stages)
    entry = dict(stages.get("web_derivative", {"name": "web_derivative"}))
    entry["status"] = status
    entry["finished_at"] = time.time()
    entry.update(extra)
    stages["web_derivative"] = entry

    fields: dict[str, Any] = {"stages": stages}
    web_splat_path = extra.get("web_splat_path")
    if web_splat_path:
        fields["web_splat_path"] = web_splat_path
    update_job(job_id, **fields)


def generate_web_derivative(job_id: str, config: Any = None) -> dict[str, Any]:
    """Produce the mkkellogg ``.ksplat`` web derivative for a completed job.

    Additive and non-fatal: any failure is logged and recorded but never fails
    the job.  Writes ``output/<id>/web/scene.ksplat`` plus a
    ``output/<id>/web/manifest.json`` sidecar, and records the outcome in the
    job record.  The trained source ``.ply`` is only ever read.

    Args:
        job_id: The job identifier.
        config: Optional ``pipeline.splat_optimizer.WebKsplatConfig``.

    Returns:
        A dict with ``status`` (``"ready"`` | ``"skipped"`` | ``"failed"``),
        ``web_splat_path`` (or ``None``), ``fallback_ply``, ``reason``, and the
        source PLY sha256 (identical before and after -- the invariant).
    """
    from web.job_manager import get_job, append_log

    outcome: dict[str, Any] = {
        "status": "skipped",
        "web_splat_path": None,
        "fallback_ply": None,
        "reason": None,
        "source_sha256": None,
        "source_sha256_stable": True,
    }

    job = get_job(job_id)
    if job is None:
        outcome["reason"] = "job not found"
        return outcome

    output_dir = Path(job.output_dir)
    if not output_dir.is_dir():
        outcome["reason"] = f"output dir missing: {output_dir}"
        return outcome

    source_ply = _find_trained_scene_ply(output_dir)
    if source_ply is None:
        outcome["reason"] = "no trained scene .ply found; nothing to convert"
        append_log(job_id, "web derivative: no trained scene .ply found — skipped")
        _record_web_derivative_stage(job_id, "skipped", reason=outcome["reason"])
        return outcome

    try:
        rel_source = str(source_ply.relative_to(output_dir))
    except ValueError:
        rel_source = str(source_ply)
    outcome["fallback_ply"] = rel_source

    # Invariant guard: capture the source hash before conversion.
    sha_before = _sha256_file(source_ply)
    outcome["source_sha256"] = sha_before

    web_dir = output_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pipeline.splat_optimizer import make_web_ksplat, WebKsplatConfig
    except ImportError as exc:
        outcome["reason"] = f"splat_optimizer not importable: {exc}"
        append_log(job_id, f"web derivative: splat_optimizer unavailable ({exc}) — skipped")
        _record_web_derivative_stage(
            job_id, "skipped", reason=outcome["reason"], fallback_ply=rel_source
        )
        _write_web_manifest(web_dir, output_dir, job_id, outcome, None)
        return outcome

    cfg = config or WebKsplatConfig()
    result = make_web_ksplat(str(source_ply), str(web_dir), cfg, output_name=_WEB_KSPLAT_NAME)

    # Re-verify the source PLY was not touched (belt-and-braces on the invariant).
    sha_after = _sha256_file(source_ply)
    outcome["source_sha256_stable"] = sha_before == sha_after
    if not outcome["source_sha256_stable"]:
        logger.error(
            "INVARIANT VIOLATION: trained PLY sha256 changed during web "
            "derivative for job %s (%s != %s)",
            job_id, sha_before, sha_after,
        )
        append_log(job_id, "web derivative: WARNING source .ply hash changed (invariant)")

    if result["success"]:
        ksplat_path = Path(result["output_path"])
        outcome["status"] = "ready"
        outcome["web_splat_path"] = str(ksplat_path)
        append_log(
            job_id,
            f"web derivative ready: web/{_WEB_KSPLAT_NAME} "
            f"({result['splat_count']} splats, {result['output_size_mb']:.1f} MB, "
            f"{result['compression_ratio']:.1f}x)",
        )
        _record_web_derivative_stage(
            job_id,
            "completed",
            web_splat_path=str(ksplat_path),
            ksplat_path=f"web/{_WEB_KSPLAT_NAME}",
            splat_count=result["splat_count"],
            output_size_mb=round(result["output_size_mb"], 2),
            compression_ratio=round(result["compression_ratio"], 2),
            source_ply=rel_source,
        )
    elif result["skipped"]:
        outcome["status"] = "skipped"
        outcome["reason"] = result["reason"]
        append_log(
            job_id,
            f"web derivative skipped ({result['reason']}); "
            f"viewer falls back to {rel_source}",
        )
        _record_web_derivative_stage(
            job_id, "skipped", reason=result["reason"], fallback_ply=rel_source
        )
    else:
        outcome["status"] = "failed"
        outcome["reason"] = result["error"]
        logger.warning("web derivative failed (non-fatal): %s", result["error"])
        append_log(
            job_id,
            f"web derivative failed (non-fatal): {result['error']}; "
            f"viewer falls back to {rel_source}",
        )
        _record_web_derivative_stage(
            job_id, "failed", reason=result["error"], fallback_ply=rel_source
        )

    _write_web_manifest(web_dir, output_dir, job_id, outcome, result)
    return outcome


def _write_web_manifest(
    web_dir: Path,
    output_dir: Path,
    job_id: str,
    outcome: dict[str, Any],
    result: dict[str, Any] | None,
) -> None:
    """Write ``web/manifest.json`` -- the authoritative, durable record of the
    web derivative that the scenes/splat API can read directly (independent of
    the job JSON)."""
    web_splat_rel = None
    if outcome.get("web_splat_path"):
        try:
            web_splat_rel = str(Path(outcome["web_splat_path"]).relative_to(output_dir))
        except ValueError:
            web_splat_rel = outcome["web_splat_path"]

    manifest = {
        "schema": "vitrine.web_derivative/1",
        "generated_at": time.time(),
        "job_id": job_id,
        "status": outcome["status"],
        "reason": outcome.get("reason"),
        "source_ply": outcome.get("fallback_ply"),
        "source_sha256": outcome.get("source_sha256"),
        "source_sha256_stable": outcome.get("source_sha256_stable"),
        # The viewer discovers the .ksplat here; when absent it loads the .ply.
        "ksplat_path": f"web/{_WEB_KSPLAT_NAME}" if outcome["status"] == "ready" else None,
        "web_splat_path": web_splat_rel,
        "fallback_ply": outcome.get("fallback_ply"),
        "viewer": {
            "library": "@mkkellogg/gaussian-splats-3d",
            "min_version": "0.4.6",
            "accepts": [".ksplat", ".ply", ".splat"],
        },
    }
    if result:
        manifest["splat_count"] = result.get("splat_count")
        manifest["output_size_mb"] = round(result.get("output_size_mb", 0.0), 2)
        manifest["input_size_mb"] = round(result.get("input_size_mb", 0.0), 2)
        manifest["compression_ratio"] = round(result.get("compression_ratio", 1.0), 2)
        manifest["duration_seconds"] = round(result.get("duration", 0.0), 2)

    try:
        (web_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    except OSError as exc:
        logger.warning("Failed to write web derivative manifest: %s", exc)


def complete_job(job_id: str, success: bool = True, error: str = "") -> bool:
    """Mark the entire job as completed or failed.

    If successful, generates the web splat derivative (non-fatal) then creates a
    downloadable ZIP archive.
    """
    from web.job_manager import get_job, update_job, append_log, JobState

    job = get_job(job_id)
    if job is None:
        return False

    if success:
        # Additive, non-fatal: emit output/<id>/web/scene.ksplat before archiving
        # so the web derivative is included in the result zip.  Never fails the job.
        try:
            generate_web_derivative(job_id)
        except Exception as exc:  # noqa: BLE001 - derivative must never fail the job
            logger.warning("web derivative stage errored (non-fatal): %s", exc)
            append_log(job_id, f"web derivative stage errored (non-fatal): {exc}")

        archive_path = _create_result_archive(job_id, job.output_dir)
        update_job(
            job_id,
            state=JobState.COMPLETED,
            progress=1.0,
            finished_at=time.time(),
            result_archive=archive_path,
        )
        append_log(job_id, "Pipeline completed successfully")
    else:
        update_job(
            job_id,
            state=JobState.FAILED,
            finished_at=time.time(),
            error=error,
        )
        append_log(job_id, f"Pipeline failed: {error}")

    return True


def cancel_pipeline(job_id: str) -> bool:
    """Cancel a job. Since Claude Code is the orchestrator, this just
    updates the state. Claude Code checks the state and stops."""
    from web.job_manager import get_job, update_job, append_log, JobState

    job = get_job(job_id)
    if job is None:
        return False

    update_job(
        job_id,
        state=JobState.CANCELLED,
        finished_at=time.time(),
        error="Cancelled by user",
    )
    append_log(job_id, "Job cancelled by user")
    return True


def is_running(job_id: str) -> bool:
    """Check if a job is in an active state."""
    from web.job_manager import get_job, JobState

    job = get_job(job_id)
    if job is None:
        return False
    return job.state in (JobState.RUNNING, JobState.QUEUED) or job.state.startswith("stage_")


# ---- Backward compat alias ----
# The old upload handler calls start_pipeline(). Now it just queues.
start_pipeline = queue_job


def _create_result_archive(job_id: str, output_dir: str) -> str | None:
    """Zip USD + meshes + textures into a downloadable archive."""
    output = Path(output_dir)
    if not output.exists():
        return None

    archive_path = output / f"{job_id}_result.zip"
    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(output):
                for fname in files:
                    fpath = Path(root) / fname
                    if fpath == archive_path:
                        continue
                    arcname = fpath.relative_to(output)
                    zf.write(fpath, arcname)
        return str(archive_path)
    except Exception as exc:
        logger.error("Failed to create result archive: %s", exc)
        return None
