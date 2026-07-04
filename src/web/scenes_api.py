# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scene/run alias facade for the ArchiveSpace SPA contract.

This Flask *blueprint* maps the community SPA's scene-centric REST surface
(``/api/scenes*``, ``/api/runs*``, ``/api/system/stats``, ``/api/tools``,
``/api/import/google-drive``) onto Vitrine's existing job store — **without a new
state machine**. A "scene" is exactly a job: ``scene_id == job_id`` 1:1. Every
write path aliases the primitives the legacy job-centric routes already use
(:func:`web.job_manager.create_job`, :func:`web.pipeline_runner.start_pipeline`,
:func:`web.job_manager.delete_job`, :func:`web.pipeline_runner.cancel_pipeline`,
and the Drive ``gdown`` workers in :mod:`web.app`), so scenes and the legacy
``/jobs`` view stay perfectly consistent.

Security posture (ADR-022 / PRD IMPL-5): this blueprint **adds no listener of its
own** — it inherits the host app's socket bind, which is loopback-only
(``127.0.0.1``) and reached over an SSH tunnel. No route echoes secret values or
dotfiles: file serving is path-jailed to a job's output directory and rejects any
``.``-prefixed path component. The Google-Drive import is a thin wrapper over the
existing public-link ``gdown`` flow — it introduces **no new credential surface**.

The read-model mappers (:func:`scene_metadata_from_job`,
:func:`progress_info_from_job`, :func:`run_summary_from_job`) are pure functions
over a :class:`web.job_manager.Job` (or an equivalent mapping) and are unit-tested
directly.

Registered by the app factory via :func:`register` (additive — it never replaces
the job-centric routes the legacy templates and orchestrator callbacks depend on).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    send_file,
)
from werkzeug.utils import secure_filename

from web.job_manager import (
    INPUT_DIR,
    OUTPUT_BASE,
    PIPELINE_STAGES,
    JobState,
    append_log,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    update_job,
)
from web.pipeline_runner import cancel_pipeline, start_pipeline

logger = logging.getLogger(__name__)

bp = Blueprint("scenes_api", __name__)

# ---------------------------------------------------------------------------
# Limits / capture-format classification (mirrors web.app so the blueprint is
# self-contained and never imports it at module load — avoiding import cycles).
# ---------------------------------------------------------------------------

# Batch stills / zip decompressed caps. The whole app already enforces a 2 GB
# request-body cap (app.config["MAX_CONTENT_LENGTH"]); these are defence-in-depth
# for the *decompressed* footprint of an uploaded archive and the cumulative size
# of a multipart image batch.
MAX_IMAGE_BATCH_BYTES = int(os.environ.get("LFS_MAX_IMAGE_BATCH_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_UNZIP_BYTES = int(os.environ.get("LFS_MAX_UNZIP_BYTES", str(10 * 1024 * 1024 * 1024)))
MAX_UNZIP_FILES = int(os.environ.get("LFS_MAX_UNZIP_FILES", "200000"))

VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm"}
# Stills + camera-raw formats accepted as an "images" capture.
IMAGE_EXTS = {
    # camera raw
    "dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf",
    "rw2", "pef", "srw", "x3f", "erf", "kdc", "dcr", "raw", "3fr", "fff", "iiq",
    "mos", "mef", "gpr", "k25",
    # stills
    "jpg", "jpeg", "png", "tif", "tiff", "heic", "heif", "webp", "bmp",
}

# Human-readable labels for the fixed pipeline-stage vocabulary.
_STAGE_LABELS = {
    "ingest": "Frame extraction",
    "remove_people": "Person removal",
    "select_frames": "Frame selection",
    "reconstruct": "COLMAP reconstruction",
    "train": "Splat training",
    "segment": "Segmentation",
    "extract_objects": "Object extraction",
    "mesh_objects": "Object meshing",
    "texture_bake": "Texture bake",
    "assemble_usd": "Scene assembly",
    "validate": "Validation",
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _err(detail: str, code: int, error: str | None = None) -> tuple[Response, int]:
    """Uniform error envelope: ``{"detail", "error"}`` with an HTTP status."""
    return jsonify({"detail": detail, "error": error or detail}), code


def _G(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dataclass ``Job`` or a plain mapping (test-friendly)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _classify(name: str) -> str:
    """Return ``'image' | 'video' | 'other'`` for a filename."""
    e = _ext(name)
    if e in IMAGE_EXTS:
        return "image"
    if e in VIDEO_EXTS:
        return "video"
    return "other"


def _iso(ts: Any) -> str:
    """UTC ISO-8601 string for an epoch timestamp; ``""`` when falsy/invalid."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return ""


def _stage_label(stage: str) -> str:
    if not stage:
        return ""
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def _map_status(job: Any) -> str:
    """Map Vitrine's internal job state onto the SPA's status vocabulary.

    Our states are ``queued|running|completed|failed|cancelled`` plus dynamic
    ``stage_<name>``; the SPA understands ``created|extracting_frames|
    colmap_running|training|processing|ready|error|cancelled``.
    """
    state = str(_G(job, "state", "") or "")
    stage = str(_G(job, "current_stage", "") or "").lower()

    if state == JobState.COMPLETED:
        return "ready"
    if state == JobState.FAILED:
        return "error"
    if state == JobState.CANCELLED:
        return "cancelled"
    if state == JobState.QUEUED:
        return "created"

    # running / stage_* — surface the coarse phase the SPA can badge.
    if stage in ("ingest", "select_frames"):
        return "extracting_frames"
    if stage == "reconstruct":
        return "colmap_running"
    if stage == "train":
        return "training"
    if state == JobState.RUNNING or state.startswith("stage_"):
        return "processing"
    return state or "created"


def _output_dir(job: Any) -> Path | None:
    """Return the job's output directory as a :class:`Path`, if it exists."""
    out = _G(job, "output_dir", "") or ""
    if not out:
        job_id = _G(job, "job_id", "")
        if not job_id:
            return None
        out = str(OUTPUT_BASE / job_id)
    p = Path(out)
    return p if p.exists() else None


def _safe_under(base: Path, candidate: Path) -> bool:
    """True iff ``candidate`` resolves to ``base`` or a descendant of it."""
    try:
        base_r = base.resolve()
        cand_r = candidate.resolve()
    except OSError:
        return False
    if cand_r == base_r:
        return True
    return str(cand_r).startswith(str(base_r) + os.sep)


def _first_match(output_dir: Path, patterns: tuple[str, ...]) -> Path | None:
    """First existing, non-empty file matching any of ``patterns`` (glob order)."""
    for pat in patterns:
        try:
            hits = sorted(output_dir.glob(pat))
        except OSError:
            continue
        for h in hits:
            if h.is_file() and h.stat().st_size > 0:
                return h
    return None


def _find_thumbnail(job: Any) -> Path | None:
    """Locate the best preview image for a scene (path-jailed to its output dir).

    Preference order: an explicit stage preview recorded on the job, then a
    contact sheet / sparse preview, then any preview render.
    """
    output_dir = _output_dir(job)
    if output_dir is None:
        return None

    # 1) Explicit stage previews recorded on the job (absolute paths).
    previews = _G(job, "previews", {}) or {}
    if isinstance(previews, dict):
        for val in previews.values():
            if not val:
                continue
            p = Path(val)
            if p.is_file() and p.stat().st_size > 0 and _safe_under(output_dir, p):
                return p

    # 2) Well-known derivative names, then any preview render.
    return _first_match(
        output_dir,
        (
            "**/contact_sheet.jpg",
            "**/sparse_preview.jpg",
            "previews/*.png",
            "previews/*.jpg",
            "**/preview*.png",
            "**/preview*.jpg",
        ),
    )


def _find_ksplat(output_dir: Path) -> Path | None:
    """Find the web splat derivative (.ksplat preferred, then .splat, then .ply)."""
    for suffix in (".ksplat", ".splat", ".ply"):
        hit = _first_match(
            output_dir,
            (f"web/*{suffix}", f"*{suffix}", f"model/*{suffix}", f"**/*{suffix}"),
        )
        if hit is not None:
            return hit
    return None


def _discover_outputs(output_dir: Path | None) -> dict[str, str]:
    """Map of well-known deliverables → output-dir-relative path (best effort)."""
    outputs: dict[str, str] = {}
    if output_dir is None:
        return outputs

    def _rel(p: Path | None) -> str | None:
        if p is None:
            return None
        try:
            return str(p.relative_to(output_dir))
        except ValueError:
            return None

    for key, patterns in (
        ("contact_sheet", ("**/contact_sheet.jpg",)),
        ("sparse_preview", ("**/sparse_preview.jpg",)),
        ("glb", ("usd/scene.glb", "**/scene.glb", "**/*.glb")),
        ("ksplat", ("web/*.ksplat", "*.ksplat", "**/*.ksplat")),
        ("splat", ("web/*.splat", "*.splat", "**/*.splat")),
        ("ply", ("model/*.ply", "*.ply", "**/*.ply")),
    ):
        rel = _rel(_first_match(output_dir, patterns))
        if rel:
            outputs[key] = rel
    return outputs


# ---------------------------------------------------------------------------
# Pure read-model mappers (unit-tested directly)
# ---------------------------------------------------------------------------


def scene_metadata_from_job(job: Any) -> dict[str, Any]:
    """Project a :class:`Job` onto the SPA's ``SceneMetadata`` shape.

    Pure w.r.t. the job's fields; only *reads* the filesystem (thumbnail/output
    discovery) which is side-effect free.
    """
    job_id = str(_G(job, "job_id", ""))
    filename = _G(job, "filename", "") or job_id
    input_kind = _G(job, "input_kind", "video") or "video"
    output_dir = _output_dir(job)

    stages = _G(job, "stages", {}) or {}
    processing_pipeline = {
        name: (info.get("status", "pending") if isinstance(info, dict) else "pending")
        for name, info in stages.items()
    }

    outputs = _discover_outputs(output_dir)
    thumb = _find_thumbnail(job)
    thumbnail_url = f"/api/scenes/{job_id}/thumbnail" if thumb is not None else None

    created = _G(job, "created_at", 0)
    finished = _G(job, "finished_at", None)
    started = _G(job, "started_at", None)
    updated = finished or started or created

    meta: dict[str, Any] = {
        "scene_id": job_id,
        "title": filename,
        "description": "",
        "creator": "",
        "location": "",
        "capture_date": _iso(created),
        "capture_device": "",
        "source_type": "photos" if input_kind == "images" else "video",
        "source_filename": filename,
        "status": _map_status(job),
        "processing_pipeline": processing_pipeline,
        "outputs": outputs,
        "notes": "",
        "rights": "",
        "created_at": _iso(created),
        "updated_at": _iso(updated),
        "last_error": _G(job, "error", None),
        # Vitrine extensions (harmless to the SPA, load-bearing for our viewer):
        "thumbnail_url": thumbnail_url,
        "input_kind": input_kind,
        "file_size_bytes": _G(job, "file_size_bytes", 0),
    }

    frame_count = _G(job, "image_count", 0) or 0
    if frame_count or input_kind == "images":
        meta["extraction"] = {"fps": 0, "frame_count": int(frame_count)}

    if output_dir is not None:
        splat = _find_ksplat(output_dir)
        if splat is not None:
            try:
                rel = str(splat.relative_to(output_dir))
                size = splat.stat().st_size
            except (ValueError, OSError):
                rel, size = splat.name, 0
            meta["splat"] = {"path": rel, "iterations": 0, "size_bytes": size}

    return meta


def progress_info_from_job(job: Any, job_type: str = "pipeline") -> dict[str, Any]:
    """Synthesize the SPA's ``ProgressInfo`` from a job's coarse progress fields.

    Derived from ``progress`` / ``current_stage`` / ``PIPELINE_STAGES`` / the log
    tail — Vitrine has one state machine, so all ``job=`` variants resolve to it.
    """
    stage = str(_G(job, "current_stage", "") or "")
    try:
        stage_index = PIPELINE_STAGES.index(stage)
    except ValueError:
        stage_index = -1

    logs = _G(job, "logs", []) or []
    log_tail = "\n".join(logs[-40:]) if logs else ""
    message = logs[-1] if logs else ""

    progress = _G(job, "progress", 0.0) or 0.0
    try:
        percent = max(0, min(100, round(float(progress) * 100)))
    except (TypeError, ValueError):
        percent = 0

    finished = _G(job, "finished_at", None)
    started = _G(job, "started_at", None)
    created = _G(job, "created_at", 0)

    return {
        "job_type": job_type,
        "status": _map_status(job),
        "stage": stage,
        "stage_label": _stage_label(stage),
        "stage_index": stage_index,
        "stage_count": len(PIPELINE_STAGES),
        "percent": percent,
        "message": message,
        "log_tail": log_tail,
        "eta_seconds": None,
        "preview": None,
        "metrics": {},
        "updated_at": _iso(finished or started or created),
        "error": _G(job, "error", None),
    }


def run_summary_from_job(job: Any) -> dict[str, Any]:
    """DDD-canonical *run* summary (``/api/runs`` list item)."""
    job_id = str(_G(job, "job_id", ""))
    output_dir = _output_dir(job)
    created = _G(job, "created_at", 0)
    finished = _G(job, "finished_at", None)
    started = _G(job, "started_at", None)
    return {
        "id": job_id,
        "scene_id": job_id,
        "filename": _G(job, "filename", "") or job_id,
        "title": _G(job, "filename", "") or job_id,
        "state": _G(job, "state", ""),
        "status": _map_status(job),
        "current_stage": _G(job, "current_stage", ""),
        "progress": _G(job, "progress", 0.0),
        "input_kind": _G(job, "input_kind", "video"),
        "file_size_bytes": _G(job, "file_size_bytes", 0),
        "created_at": _iso(created),
        "updated_at": _iso(finished or started or created),
        "outputs": _discover_outputs(output_dir),
        "has_output": output_dir is not None,
    }


def scene_detail_from_job(job: Any) -> dict[str, Any]:
    """Project a :class:`Job` onto the SPA's ``SceneDetail`` shape."""
    meta = scene_metadata_from_job(job)
    progress = progress_info_from_job(job, job_type="pipeline")

    output_dir = _output_dir(job)
    ksplat_path: str | None = None
    ksplat_url: str | None = None
    if output_dir is not None:
        splat = _find_ksplat(output_dir)
        if splat is not None:
            try:
                ksplat_path = str(splat.relative_to(output_dir))
            except ValueError:
                ksplat_path = splat.name
            # Served by the splat_api sibling blueprint; a URL string only.
            ksplat_url = f"/api/scenes/{meta['scene_id']}/splat/{ksplat_path}"

    state = str(_G(job, "state", "") or "")
    job_info = {
        "status": _map_status(job),
        "type": "pipeline",
        "error": _G(job, "error", None),
        "progress": progress,
    }

    stage = str(_G(job, "current_stage", "") or "")
    detail: dict[str, Any] = {
        "metadata": meta,
        "splat_readiness": {
            "ready": state == JobState.COMPLETED and ksplat_path is not None,
            "registered_images": 0,
            "total_images": int(_G(job, "image_count", 0) or 0),
            "registration_ratio": 0.0,
            "blockers": [] if state == JobState.COMPLETED else ["pipeline_incomplete"],
        },
        "qa_report": None,
        "qa_progress": None,
        "colmap_report": None,
        "recovery_report": None,
        "progress": progress,
        "progress_extract": progress if stage in ("ingest", "select_frames") else None,
        "progress_colmap": progress if stage == "reconstruct" else None,
        "progress_recovery": None,
        "progress_lingbot": None,
        "progress_ppisp": None,
        "progress_artifixer": None,
        "progress_train": progress if stage == "train" else None,
        "energy": None,
        "job": job_info,
        "jobs": {"pipeline": job_info},
        # Vitrine extensions for the splat viewer:
        "ksplat_path": ksplat_path,
        "ksplat_url": ksplat_url,
    }
    return detail


# ---------------------------------------------------------------------------
# Read model — scenes / runs
# ---------------------------------------------------------------------------


def _all_jobs() -> list[Any]:
    """Load every job as a full :class:`Job` (newest first)."""
    jobs: list[Any] = []
    for summ in list_jobs():
        jid = summ.get("job_id")
        if not jid:
            continue
        job = get_job(jid)
        if job is not None:
            jobs.append(job)
    return jobs


@bp.route("/api/scenes", methods=["GET"])
def list_scenes() -> tuple[Response, int]:
    """``SceneMetadata[]`` for every job (the ArchiveLibrary grid)."""
    return jsonify([scene_metadata_from_job(j) for j in _all_jobs()]), 200


@bp.route("/api/scenes/<sid>", methods=["GET"])
def get_scene(sid: str) -> tuple[Response, int]:
    """``SceneDetail`` for one scene; 404 ``{detail: 'Scene not found'}``."""
    job = get_job(sid)
    if job is None:
        return _err("Scene not found", 404, "not_found")
    return jsonify(scene_detail_from_job(job)), 200


@bp.route("/api/scenes/<sid>/progress", methods=["GET"])
def scene_progress(sid: str) -> tuple[Response, int]:
    """Synthesized ``ProgressInfo`` polling fallback (SSE ``/stream`` is canonical)."""
    job = get_job(sid)
    if job is None:
        return _err("Scene not found", 404, "not_found")
    job_type = request.args.get("job", "pipeline") or "pipeline"
    return jsonify(progress_info_from_job(job, job_type=job_type)), 200


@bp.route("/api/scenes/<sid>/thumbnail", methods=["GET"])
def scene_thumbnail(sid: str) -> Response | tuple[Response, int]:
    """Serve a scene's best preview image (path-jailed; never a dotfile)."""
    job = get_job(sid)
    if job is None:
        return _err("Scene not found", 404, "not_found")
    thumb = _find_thumbnail(job)
    output_dir = _output_dir(job)
    if thumb is None or output_dir is None:
        return _err("No thumbnail available", 404, "not_found")
    # Defence in depth: re-jail and refuse any dotfile component.
    if not _safe_under(output_dir, thumb) or any(
        part.startswith(".") for part in thumb.relative_to(output_dir).parts
    ):
        return _err("Forbidden", 403, "forbidden")
    mime, _ = mimetypes.guess_type(str(thumb))
    return send_file(str(thumb), mimetype=mime or "application/octet-stream")


@bp.route("/api/runs", methods=["GET"])
def list_runs() -> tuple[Response, int]:
    """DDD-canonical run list; scenes delegate to the same job builders."""
    return jsonify([run_summary_from_job(j) for j in _all_jobs()]), 200


@bp.route("/api/runs/<rid>", methods=["GET"])
def get_run(rid: str) -> tuple[Response, int]:
    """DDD-canonical run detail; 404 ``{detail: 'Run not found'}``."""
    job = get_job(rid)
    if job is None:
        return _err("Run not found", 404, "not_found")
    detail = run_summary_from_job(job)
    detail["progress"] = progress_info_from_job(job, job_type="pipeline")
    detail["stages"] = _G(job, "stages", {}) or {}
    detail["scene"] = scene_metadata_from_job(job)
    return jsonify(detail), 200


# ---------------------------------------------------------------------------
# System stats / tool availability
# ---------------------------------------------------------------------------


@bp.route("/api/system/stats", methods=["GET"])
def system_stats() -> tuple[Response, int]:
    """Best-effort host stats (psutil/pynvml); zeros when the libs are absent."""
    stats: dict[str, Any] = {
        "updated_at": _iso(time.time()),
        "cpu_percent": 0.0,
        "ram_used_gb": 0.0,
        "ram_total_gb": 0.0,
        "ram_percent": 0.0,
        "gpu_available": False,
        "gpu_name": "",
        "gpu_percent": 0.0,
        "vram_used_mb": 0.0,
        "vram_total_mb": 0.0,
        "vram_percent": 0.0,
        "gpu_power_w": None,
        "cpu_power_est_w": 0.0,
        "total_power_w": 0.0,
        "power_note": "estimate",
    }

    try:
        import psutil  # type: ignore

        stats["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        vm = psutil.virtual_memory()
        stats["ram_used_gb"] = round(vm.used / 1e9, 2)
        stats["ram_total_gb"] = round(vm.total / 1e9, 2)
        stats["ram_percent"] = float(vm.percent)
    except Exception:  # noqa: BLE001 — best-effort; zeros are a valid answer.
        pass

    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            stats["gpu_available"] = True
            stats["gpu_name"] = name.decode() if isinstance(name, bytes) else str(name)
            stats["gpu_percent"] = float(util.gpu)
            stats["vram_used_mb"] = round(mem.used / 1e6, 1)
            stats["vram_total_mb"] = round(mem.total / 1e6, 1)
            stats["vram_percent"] = round(mem.used / mem.total * 100, 1) if mem.total else 0.0
            try:
                stats["gpu_power_w"] = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 1)
                stats["total_power_w"] = stats["gpu_power_w"]
            except Exception:  # noqa: BLE001
                pass
        finally:
            pynvml.nvmlShutdown()
    except Exception:  # noqa: BLE001 — no NVML / no GPU: gpu_available stays False.
        pass

    return jsonify(stats), 200


@bp.route("/api/tools", methods=["GET"])
def tools() -> tuple[Response, int]:
    """Tool availability flags. Advanced branches (lingbot/ppisp/artifixer) off."""
    ffmpeg = shutil.which("ffmpeg")
    colmap = shutil.which("colmap")
    py = shutil.which("python3") or shutil.which("python") or ""
    return jsonify({
        "ffmpeg": {"available": bool(ffmpeg), "path": ffmpeg or ""},
        "colmap": {"available": bool(colmap), "path": colmap or ""},
        "lingbot_map": {"available": False},
        "ppisp": {"available": False, "doc": ""},
        "nvidia_artifixer": {"available": False, "doc": ""},
        "splat_training": {"available": True, "python": py, "doc": "LichtFeld Studio (vendored)"},
    }), 200


# ---------------------------------------------------------------------------
# Write / ingest
# ---------------------------------------------------------------------------


def _uploaded_file():
    """Return the primary uploaded file part (SPA sends ``file``; legacy ``video``)."""
    for key in ("file", "video"):
        if key in request.files:
            f = request.files[key]
            if f and f.filename:
                return f
    return None


@bp.route("/api/scenes/upload", methods=["POST"])
def upload_scene() -> tuple[Response, int]:
    """Video upload → ``create_job`` + ``start_pipeline`` (aliases legacy ``/upload``)."""
    file = _uploaded_file()
    if file is None:
        return _err("No file in request", 400, "no_file")
    if _classify(file.filename) != "video":
        return _err(
            f"Invalid file type. Allowed: {', '.join(sorted(VIDEO_EXTS))}", 400, "bad_type"
        )

    filename = secure_filename(file.filename)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = INPUT_DIR / f"{int(time.time() * 1000)}_{filename}"
    try:
        file.save(str(save_path))
    except Exception as exc:  # noqa: BLE001
        logger.error("upload save failed: %s", exc)
        return _err("Failed to save file", 500, "save_failed")

    job = create_job(
        filename=filename,
        input_video_path=str(save_path),
        file_size_bytes=save_path.stat().st_size,
    )
    if not start_pipeline(job.job_id):
        return _err("Failed to start pipeline", 500, "start_failed")

    fresh = get_job(job.job_id) or job
    return jsonify({"scene_id": job.job_id, "metadata": scene_metadata_from_job(fresh)}), 201


@bp.route("/api/scenes/upload-images", methods=["POST"])
def upload_images() -> tuple[Response, int]:
    """Batch stills → staged images capture (decoded + enqueued by ``queue_job``)."""
    files = request.files.getlist("files") + request.files.getlist("file")
    if not files:
        files = [f for f in request.files.values() if f and f.filename]
    files = [f for f in files if f and f.filename]
    if not files:
        return _err("Choose at least one photo.", 400, "no_files")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    job = create_job(filename="images capture", input_video_path="", file_size_bytes=0)
    img_dir = INPUT_DIR / f"{job.job_id}_images"
    img_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    total_bytes = 0
    skipped: list[str] = []
    for f in files:
        if _classify(f.filename) != "image":
            skipped.append(f.filename)
            continue
        safe = secure_filename(f.filename) or f"img_{saved:05d}.{_ext(f.filename) or 'img'}"
        dest = img_dir / safe
        try:
            f.save(str(dest))
        except Exception as exc:  # noqa: BLE001
            logger.warning("image save failed for %s: %s", f.filename, exc)
            skipped.append(f.filename)
            continue
        total_bytes += dest.stat().st_size
        if total_bytes > MAX_IMAGE_BATCH_BYTES:
            shutil.rmtree(img_dir, ignore_errors=True)
            delete_job(job.job_id)
            return _err("Total image upload exceeds the 2 GB cap.", 413, "too_large")
        saved += 1

    if saved == 0:
        shutil.rmtree(img_dir, ignore_errors=True)
        delete_job(job.job_id)
        return _err("No usable images in the upload.", 400, "no_images")

    update_job(
        job.job_id,
        input_kind="images",
        input_dir=str(img_dir),
        image_count=saved,
        input_video_path="",
        filename=f"{saved} images",
        file_size_bytes=total_bytes,
        current_stage="",
    )
    if skipped:
        append_log(job.job_id, f"WARN: skipped {len(skipped)} non-image file(s): {skipped[:8]}")
    if not start_pipeline(job.job_id):
        return _err("Failed to start pipeline", 500, "start_failed")

    fresh = get_job(job.job_id)
    return jsonify({"scene_id": job.job_id, "metadata": scene_metadata_from_job(fresh)}), 201


@bp.route("/api/scenes/upload-zip", methods=["POST"])
def upload_zip() -> tuple[Response, int]:
    """ZIP import with a zip-slip guard and a decompressed-size cap.

    Every member is resolved under the per-job staging directory and rejected if
    it escapes (``../…`` or an absolute path). Extracted content is classified:
    images become an image capture; a lone video becomes a video capture.
    """
    file = _uploaded_file()
    if file is None:
        return _err("No file in request", 400, "no_file")
    if _ext(file.filename) != "zip":
        return _err("Upload must be a .zip archive.", 400, "bad_type")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    job = create_job(filename=secure_filename(file.filename) or "archive.zip",
                     input_video_path="", file_size_bytes=0)
    zip_path = INPUT_DIR / f"{job.job_id}.zip"
    stage_dir = INPUT_DIR / f"{job.job_id}_images"
    stage_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup() -> None:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(stage_dir, ignore_errors=True)
        delete_job(job.job_id)

    try:
        file.save(str(zip_path))
    except Exception as exc:  # noqa: BLE001
        _cleanup()
        logger.error("zip save failed: %s", exc)
        return _err("Failed to save archive", 500, "save_failed")

    base = stage_dir.resolve()
    total = 0
    extracted = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.infolist()
            if len(members) > MAX_UNZIP_FILES:
                _cleanup()
                return _err("Archive contains too many entries.", 400, "too_many_files")
            for m in members:
                name = m.filename
                if not name or name.endswith("/"):
                    continue  # directory entry
                if os.path.isabs(name) or name.startswith(("/", "\\")):
                    _cleanup()
                    return _err(f"Unsafe absolute path in archive: {name}", 400, "zip_slip")
                dest = (stage_dir / name).resolve()
                # Zip-slip: the resolved destination MUST stay under the jail.
                if dest != base and not str(dest).startswith(str(base) + os.sep):
                    _cleanup()
                    return _err(f"Unsafe path in archive (zip slip): {name}", 400, "zip_slip")
                total += int(m.file_size)
                if total > MAX_UNZIP_BYTES:
                    _cleanup()
                    return _err("Archive is too large when decompressed.", 400, "too_large")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1
    except zipfile.BadZipFile:
        _cleanup()
        return _err("Not a valid ZIP archive.", 400, "bad_zip")
    except Exception as exc:  # noqa: BLE001
        _cleanup()
        logger.error("zip extract failed: %s", exc)
        return _err("Failed to extract archive", 500, "extract_failed")
    finally:
        zip_path.unlink(missing_ok=True)

    if extracted == 0:
        _cleanup()
        return _err("Archive is empty.", 400, "empty")

    # Classify extracted content: prefer images, fall back to a single video.
    images = [p for p in stage_dir.rglob("*") if p.is_file() and _classify(p.name) == "image"]
    videos = [p for p in stage_dir.rglob("*") if p.is_file() and _classify(p.name) == "video"]

    if images:
        size = sum(p.stat().st_size for p in images)
        update_job(
            job.job_id, input_kind="images", input_dir=str(stage_dir),
            image_count=len(images), input_video_path="",
            filename=f"{len(images)} images (zip)", file_size_bytes=size, current_stage="",
        )
        append_log(job.job_id, f"ZIP import: {len(images)} image(s) staged; ignoring "
                               f"{len(videos)} video(s).")
    elif videos:
        vid = videos[0]
        update_job(
            job.job_id, input_kind="video", input_video_path=str(vid),
            filename=vid.name, file_size_bytes=vid.stat().st_size, current_stage="",
        )
        append_log(job.job_id, f"ZIP import: no images — using video {vid.name}.")
    else:
        _cleanup()
        return _err("Archive has no images or videos.", 400, "no_media")

    if not start_pipeline(job.job_id):
        return _err("Failed to start pipeline", 500, "start_failed")

    fresh = get_job(job.job_id)
    return jsonify({"scene_id": job.job_id, "metadata": scene_metadata_from_job(fresh)}), 201


@bp.route("/api/import/google-drive", methods=["POST"])
def import_google_drive() -> tuple[Response, int]:
    """Public Drive-link import — a thin wrapper over the existing ``gdown`` flow.

    Reuses :mod:`web.app`'s parser and background workers (no new download logic,
    no new credential surface). ``gdown`` handles *public* links only, so there is
    no secret to leak here.
    """
    data = request.get_json(silent=True) or request.form
    url = (data.get("url") or "").strip()
    if not url:
        return _err("Paste a shared Google Drive link.", 400, "no_url")

    # Lazy import to avoid an import cycle at blueprint load time.
    from web import app as web_app  # type: ignore

    drive_id, kind = web_app._parse_drive_url(url)
    if not drive_id:
        return _err(
            "Could not find a Google Drive id in that link. Paste a file link "
            "(…/file/d/<ID>/view) or a folder link (…/folders/<ID>).",
            400, "bad_url",
        )

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    job = create_job(filename=f"gdrive_{drive_id}", input_video_path="", file_size_bytes=0)
    update_job(job.job_id, current_stage="downloading")

    if kind == "folder":
        append_log(job.job_id, f"Scanning Google Drive folder (images preferred): {url}")
        worker = threading.Thread(
            target=web_app._folder_ingest_worker, args=(job.job_id, url), daemon=True
        )
    else:
        append_log(job.job_id, f"Downloading Google Drive file: {url}")
        worker = threading.Thread(
            target=web_app._file_ingest_worker, args=(job.job_id, drive_id), daemon=True
        )
    worker.start()

    logger.info("Drive import queued: scene=%s id=%s kind=%s", job.job_id, drive_id, kind)
    fresh = get_job(job.job_id) or job
    return jsonify({
        "scene_id": job.job_id,
        "status": "downloading",
        "inputSource": "google_drive",
        "kind": kind,
        "drive_id": drive_id,
        "metadata": scene_metadata_from_job(fresh),
    }), 202


@bp.route("/api/scenes/<sid>", methods=["DELETE"])
def delete_scene(sid: str) -> tuple[Response, int]:
    """Cancel (if running) and delete a scene — aliases the legacy job delete."""
    job = get_job(sid)
    if job is None:
        return _err("Scene not found", 404, "not_found")

    state = str(_G(job, "state", "") or "")
    if state in (JobState.RUNNING, JobState.QUEUED) or state.startswith("stage_"):
        cancel_pipeline(sid)

    if delete_job(sid):
        return jsonify({"status": "deleted", "scene_id": sid}), 200
    return _err("Delete failed", 500, "delete_failed")


@bp.route("/api/scenes/<sid>/export", methods=["POST"])
def export_scene(sid: str) -> tuple[Response, int]:
    """Return a download URL for the scene's result archive (replaces the mock).

    Prefers the DDD-canonical streamed ``/api/runs/<id>/zip`` (served by the
    ``zip_api`` sibling) when it is registered, and otherwise falls back to the
    always-available legacy ``/download/<id>`` streamer. Either way the URL
    streams a valid zip.
    """
    job = get_job(sid)
    if job is None:
        return _err("Scene not found", 404, "not_found")
    return jsonify({"downloadUrl": _zip_url(sid)}), 200


def _zip_url(sid: str) -> str:
    """Canonical ``/api/runs/<id>/zip`` when routable, else legacy ``/download``."""
    target = f"/api/runs/{sid}/zip"
    try:
        adapter = current_app.url_map.bind("127.0.0.1")
        adapter.match(target, method="GET")
        return target
    except Exception:  # noqa: BLE001 — route not present: use the legacy streamer.
        return f"/download/{sid}"


# ---------------------------------------------------------------------------
# Per-stage / job control — not implemented by the Vitrine web service.
#
# Vitrine's orchestrator (Claude Code + the pipeline) drives stages; the SPA's
# granular "run this stage" buttons have no server-side counterpart here, so we
# answer 501 with the standard error envelope rather than pretend. Job cancel is
# the one control we *can* honour (aliases cancel_pipeline).
# ---------------------------------------------------------------------------

_STAGE_CONTROL_ROUTES: tuple[tuple[str, str], ...] = (
    ("/api/scenes/<sid>/extract-frames", "POST"),
    ("/api/scenes/<sid>/run-colmap", "POST"),
    ("/api/scenes/<sid>/recover-colmap", "POST"),
    ("/api/scenes/<sid>/quality-reconstruction", "POST"),
    ("/api/scenes/<sid>/train-splat", "POST"),
    ("/api/scenes/<sid>/run-lingbot", "POST"),
    ("/api/scenes/<sid>/run-ppisp", "POST"),
    ("/api/scenes/<sid>/run-artifixer", "POST"),
    ("/api/scenes/<sid>/regenerate-preview", "POST"),
    ("/api/scenes/<sid>/import-splat", "POST"),
    ("/api/scenes/<sid>/active-splat", "POST"),
    ("/api/scenes/<sid>/metadata", "PATCH"),
    ("/api/scenes/<sid>/jobs/pause", "POST"),
    ("/api/scenes/<sid>/jobs/resume", "POST"),
)


def _stage_not_implemented(sid: str) -> tuple[Response, int]:
    if get_job(sid) is None:
        return _err("Scene not found", 404, "not_found")
    return _err(
        "Per-stage control is managed by the Vitrine orchestrator and is not "
        "exposed as an on-demand endpoint in this web service.",
        501, "not_implemented",
    )


for _i, (_rule, _method) in enumerate(_STAGE_CONTROL_ROUTES):
    bp.add_url_rule(
        _rule,
        endpoint=f"stage_control_{_i}",
        view_func=_stage_not_implemented,
        methods=[_method],
    )


@bp.route("/api/scenes/<sid>/jobs/cancel", methods=["POST"])
def cancel_scene_job(sid: str) -> tuple[Response, int]:
    """Cancel the scene's running pipeline — aliases ``cancel_pipeline``."""
    if get_job(sid) is None:
        return _err("Scene not found", 404, "not_found")
    cancel_pipeline(sid)
    return jsonify({"status": "cancelled", "scene_id": sid}), 200


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(app) -> None:
    """Register this blueprint on ``app`` (additive; adds no listener/bind).

    The blueprint inherits the host app's loopback (``127.0.0.1``) socket bind —
    it never opens a socket of its own (ADR-022 IMPL-5).
    """
    app.register_blueprint(bp)
