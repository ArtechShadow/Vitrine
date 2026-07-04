# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flask blueprint: 3D Gaussian-splat serving + vanilla-JS viewer page.

Consolidates the ArchiveSpace SPA's splat contract into our loopback-only
Flask service. Additive to the job-centric routes in ``app.py`` — it never
replaces them. Registered by ``app.py`` via::

    from web.splat_api import splat_api
    app.register_blueprint(splat_api)

Routes
------
GET /api/scenes/<scene_id>/splat
    JSON manifest of the best splat derivative for a job (SPA + viewer.html
    tab selection).
GET /api/scenes/<scene_id>/splat/<filename>
    Serve one named splat file, sanitized and jailed to ``output/<id>/``.
    ``send_file(conditional=True)`` gives Range (206) + ETag for progressive
    load and caching over the SSH tunnel. (SPA contract: ``splatUrl()``.)
GET /splat/<job_id>
    Serve the best-discovered splat bytes for a job (no filename needed) —
    the default source loaded by the vanilla-JS viewer.
GET /viewer_splat/<job_id>
    Render the vendored gaussian-splats-3d viewer page (``viewer_splat.html``),
    embeddable as an iframe from ``viewer.html``.

Security: this blueprint opens NO network listener of its own; it inherits the
app's ``127.0.0.1`` loopback bind. All file access is jailed to the job's
output directory (traversal attempts return 403), mirroring the ``/mesh/<id>``
and ``serve_job_file`` patterns in ``app.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    render_template,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

# Ensure src/ is importable when this module is loaded standalone (mirrors app.py).
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from web.job_manager import OUTPUT_BASE, get_job

splat_api = Blueprint("splat_api", __name__)

# Splat container formats we recognise, mapped to the gaussian-splats-3d
# ``SceneFormat`` token the viewer passes to ``addSplatScene``.
SPLAT_EXTENSIONS: dict[str, str] = {
    ".ksplat": "ksplat",  # gaussian-splats-3d compressed web deliverable
    ".splat": "splat",    # antimatter15 uncompressed splat
    ".ply": "ply",        # INRIA 3DGS point PLY (trained model output)
    ".spz": "spz",        # Niantic compressed splat
}


# ---------------------------------------------------------------------------
# Discovery + jailing helpers
# ---------------------------------------------------------------------------


def _job_output_dir(job_id: str) -> tuple[object | None, Path | None]:
    """Return ``(job, output_dir)`` for a job id, or ``(None, None)`` if absent.

    ``output_dir`` is ``None`` when the job exists but its directory does not
    (e.g. deleted on disk) so callers can render a graceful "still exporting"
    state instead of 404-ing the whole page.
    """
    job = get_job(job_id)
    if job is None:
        return None, None
    raw = getattr(job, "output_dir", "") or ""
    out = Path(raw) if raw else (OUTPUT_BASE / secure_filename(job_id))
    if not out.exists() or not out.is_dir():
        return job, None
    return job, out


def _first_nonempty(paths) -> Path | None:
    for p in paths:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def _discover_splat(out: Path) -> tuple[Path | None, str | None]:
    """Return ``(path, format_token)`` for the best splat derivative under ``out``.

    Priority (matches the pipeline's web-derivative layout):
      1. ``web/scene.ksplat``          -- canonical compressed web deliverable
      2. any ``web/*.ksplat`` then ``*.ksplat`` anywhere
      3. ``model/*.ply``               -- trained 3DGS point PLYs
      4. any ``*.splat``               -- uncompressed splat
      5. any ``*.spz``                 -- compressed splat fallback

    ``.ply`` discovery is deliberately restricted to ``model/`` so a meshing
    stage's surface PLY is never mistaken for a splat point cloud.
    """
    canonical = out / "web" / "scene.ksplat"
    hit = _first_nonempty([canonical])
    if hit is not None:
        return hit, "ksplat"

    web = out / "web"
    ksplats = (sorted(web.glob("*.ksplat")) if web.is_dir() else []) + sorted(out.glob("*.ksplat"))
    hit = _first_nonempty(ksplats)
    if hit is not None:
        return hit, "ksplat"

    model = out / "model"
    if model.is_dir():
        hit = _first_nonempty(sorted(model.glob("*.ply")))
        if hit is not None:
            return hit, "ply"

    hit = _first_nonempty(sorted(out.rglob("*.splat")))
    if hit is not None:
        return hit, "splat"

    hit = _first_nonempty(sorted(out.rglob("*.spz")))
    if hit is not None:
        return hit, "spz"

    return None, None


def _resolve_named(out: Path, filename: str) -> Path | None:
    """Resolve a single splat file by name, jailed to ``out``.

    Returns the path if it is a real, non-empty splat file inside ``out``.
    Raises ``werkzeug`` 403 on a traversal attempt, 400 on a non-splat
    extension, and returns ``None`` when simply not found (caller 404s).
    """
    # Explicit traversal rejection (before sanitising) so probes get 403.
    if ".." in filename or filename.startswith(("/", "\\")) or "\x00" in filename:
        abort(403)
    if "/" in filename or "\\" in filename or os.sep in filename:
        abort(403)

    safe = secure_filename(os.path.basename(filename))
    if not safe:
        abort(403)

    ext = os.path.splitext(safe)[1].lower()
    if ext not in SPLAT_EXTENSIONS:
        abort(400, description="Unsupported splat extension")

    jail = out.resolve()
    for base in (out, out / "web", out / "model"):
        cand = base / safe
        try:
            rp = cand.resolve()
        except OSError:
            continue
        # Jail check mirrors serve_job_file() in app.py.
        if rp != jail and not str(rp).startswith(str(jail) + os.sep):
            continue
        if cand.is_file() and cand.stat().st_size > 0:
            return cand
    return None


def _serve_splat_file(path: Path, download_name: str | None = None) -> Response:
    """Send splat bytes with Range/ETag support for progressive load + caching."""
    return send_file(
        str(path),
        mimetype="application/octet-stream",
        conditional=True,  # enables 206 Range + ETag/Last-Modified revalidation
        download_name=download_name or path.name,
        max_age=3600,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@splat_api.route("/api/scenes/<scene_id>/splat")
def splat_manifest(scene_id: str) -> tuple[Response, int]:
    """Return a JSON manifest of the best splat derivative for a scene/job."""
    job, out = _job_output_dir(scene_id)
    if job is None:
        abort(404)

    info: dict = {
        "scene_id": scene_id,
        "available": False,
        "url": None,
        "download_url": url_for("splat_api.serve_best_splat", job_id=scene_id),
        "viewer_url": url_for("splat_api.viewer_splat_page", job_id=scene_id),
        "format": None,
        "filename": None,
        "size_bytes": 0,
    }
    if out is not None:
        path, fmt = _discover_splat(out)
        if path is not None:
            info.update(
                available=True,
                format=fmt,
                filename=path.name,
                size_bytes=path.stat().st_size,
                url=url_for("splat_api.serve_named_splat", scene_id=scene_id, filename=path.name),
            )
    return jsonify(info), 200


@splat_api.route("/api/scenes/<scene_id>/splat/<path:filename>")
def serve_named_splat(scene_id: str, filename: str) -> Response:
    """Serve one named splat file (SPA contract), jailed to ``output/<id>/``."""
    job, out = _job_output_dir(scene_id)
    if job is None:
        abort(404)
    if out is None:
        abort(404, description="Splat not available (still exporting)")

    path = _resolve_named(out, filename)  # aborts 403/400 on bad input
    if path is None:
        abort(404, description="Splat file not found")
    return _serve_splat_file(path)


@splat_api.route("/splat/<job_id>")
def serve_best_splat(job_id: str) -> Response:
    """Serve the best-discovered splat bytes for a job (viewer default source)."""
    job, out = _job_output_dir(job_id)
    if job is None:
        abort(404)
    if out is None:
        abort(404, description="Splat not available (still exporting)")

    path, _fmt = _discover_splat(out)
    if path is None:
        abort(404, description="No splat derivative found for this job")
    return _serve_splat_file(path)


@splat_api.route("/viewer_splat/<job_id>")
def viewer_splat_page(job_id: str) -> str:
    """Render the vendored gaussian-splats-3d viewer page for a job."""
    job, out = _job_output_dir(job_id)
    if job is None:
        abort(404)

    splat_url: str | None = None
    splat_format: str | None = None
    splat_name: str | None = None
    if out is not None:
        path, fmt = _discover_splat(out)
        if path is not None:
            splat_format = fmt
            splat_name = path.name
            splat_url = url_for("splat_api.serve_named_splat", scene_id=job_id, filename=path.name)

    return render_template(
        "viewer_splat.html",
        job_id=job_id,
        filename=getattr(job, "filename", "") or job_id,
        splat_url=splat_url,
        splat_format=splat_format,
        splat_name=splat_name,
        download_url=url_for("splat_api.serve_best_splat", job_id=job_id),
    )
