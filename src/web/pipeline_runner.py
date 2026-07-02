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


def complete_job(job_id: str, success: bool = True, error: str = "") -> bool:
    """Mark the entire job as completed or failed.

    If successful, creates a downloadable ZIP archive.
    """
    from web.job_manager import get_job, update_job, append_log, JobState

    job = get_job(job_id)
    if job is None:
        return False

    if success:
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
