# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Streamed, constant-memory per-run zip downloads (``zip_api`` blueprint).

Exposes ``GET /api/runs/<id>/zip`` for the Vitrine web SPA export flow. Unlike the
legacy ``/download/<job_id>`` route in ``app.py`` — which buffers the whole archive
in an ``io.BytesIO`` (a PRD-R6 "constant-memory" violation) — this route streams the
archive on the fly with ``zipstream-ng`` so a multi-GB run downloads with the Flask
process RSS staying flat. The legacy route is intentionally left untouched for its
current UI callers; the SPA export flow points at this route instead.

Registration is additive: ``app.py`` does ``from web.zip_api import zip_api`` then
``app.register_blueprint(zip_api)`` (or ``zip_api``'s ``register(app)`` helper). It
never shadows the job-centric routes the existing UI / orchestrator callbacks depend
on.

Security (ADR-022 secure single-image architecture): this blueprint opens **no**
network socket of its own — it inherits the application's loopback bind
(127.0.0.1, reachable externally only over an SSH tunnel). Every member path is
resolved and confined to the ``output/<id>/`` jail before it is added to the
archive, and dotfiles / hidden dirs are always excluded, so a request can never
escape the run directory or leak host files.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from flask import Blueprint, Response, jsonify, request
from werkzeug.utils import secure_filename

# Canonical output base — the same location create_job() writes run dirs under, so
# the zip jail matches exactly where runs actually live.
from web.job_manager import OUTPUT_BASE

logger = logging.getLogger(__name__)

zip_api = Blueprint("zip_api", __name__)


# ---------------------------------------------------------------------------
# Asset-mode filter — mirrors the legacy app.py:/download filter semantics.
# ---------------------------------------------------------------------------

# Top-level dirs whose contents are always part of the deliverable bundle.
_ASSET_INCLUDE_DIRS = {"objects", "usd", "previews", "model"}

# File extensions that are part of the deliverable regardless of directory.
_ASSET_INCLUDE_EXTENSIONS = {
    ".glb", ".obj", ".ply", ".usda", ".usdc", ".usdz",
    ".jpg", ".png", ".json", ".mtl",
}

# Bulky intermediates that never belong in an "assets" bundle.
_EXCLUDE_TOP_DIRS = {"frames", "frames_selected", "input", "colmap"}


def _is_asset_member(rel: Path) -> bool:
    """Return True if ``rel`` (relative to the run dir) belongs in an assets zip.

    Matches ``app.py:/download``: an excluded top-level dir is dropped first; an
    included top-level dir wins outright; otherwise the file must carry a
    deliverable extension (``.usd*`` covers usd/usda/usdc/usdz).
    """
    top = rel.parts[0] if rel.parts else ""
    if top in _EXCLUDE_TOP_DIRS:
        return False
    if top in _ASSET_INCLUDE_DIRS:
        return True
    suffix = rel.suffix.lower()
    return suffix in _ASSET_INCLUDE_EXTENSIONS or suffix.startswith(".usd")


def _resolve_run_dir(run_id: str) -> Path | None:
    """Resolve ``run_id`` to its ``output/<id>/`` directory inside the jail.

    Returns None if the id is malformed, escapes the output base, or does not
    exist as a real directory (the caller turns that into a 404).
    """
    safe_id = secure_filename(run_id)
    if not safe_id:
        return None
    base = OUTPUT_BASE.resolve()
    run_dir = (base / safe_id).resolve()
    # Jail: the run must be an immediate child of the output base (no traversal,
    # no symlinked escape) and must exist as a real directory.
    if run_dir.parent != base or not run_dir.is_dir():
        return None
    return run_dir


def _iter_members(run_dir: Path, mode: str):
    """Yield ``(absolute_path, arcname)`` tuples for the files to archive.

    ``mode`` is ``"all"`` (the whole tree, dotfiles excluded) or ``"assets"`` (the
    deliverable subset). Only file paths + arcnames are produced here — no bytes —
    so the walk stays cheap. Hidden paths and any symlink target that escapes the
    jail are filtered so the archive can never leak anything outside ``run_dir``.
    """
    jail = run_dir.resolve()
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(run_dir)
        except ValueError:
            continue
        # Never archive dotfiles / hidden dirs, in any mode.
        if any(part.startswith(".") for part in rel.parts):
            continue
        if mode == "assets" and not _is_asset_member(rel):
            continue
        # Confine to the jail even through symlinks (rglob can surface links).
        resolved = path.resolve()
        if resolved != jail and jail not in resolved.parents:
            continue
        yield str(path), str(rel)


@zip_api.route("/api/runs/<run_id>/zip")
def download_run_zip(run_id: str) -> Response:
    """Stream a per-run zip archive with constant memory.

    Query param ``include``:
      * ``assets`` (default) — the deliverable subset: ``objects/usd/previews/model``
        dirs plus ``.glb/.obj/.ply/.usd*/.jpg/.png/.json/.mtl`` files, excluding
        ``frames/frames_selected/input/colmap``.
      * ``all`` — the full run tree (dotfiles still excluded).

    Returns ``application/zip`` as a chunked, generator-backed streaming response
    (``Content-Disposition: attachment; filename="<id>.zip"``). A 404 ``{detail}``
    is returned for an unknown run; a 503 ``{detail}`` if ``zipstream-ng`` is not
    installed in the image.
    """
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        return jsonify({"detail": f"Run '{run_id}' not found"}), 404

    mode = "all" if request.args.get("include", "assets").lower() == "all" else "assets"

    # Lazy import (matches the app's defensive-import style for optional runtime
    # deps): keeps the blueprint importable even before the image bakes in the dep.
    try:
        from zipstream import ZipStream  # zipstream-ng: streamed, ZIP64-aware
    except ImportError:
        logger.error("zipstream-ng not installed — cannot stream run %s", run_dir.name)
        return jsonify({"detail": "Streaming zip support (zipstream-ng) unavailable"}), 503

    # ZIP_STORED: constant-memory streaming at maximum throughput. A run is
    # dominated by already-compressed binary assets (png/jpg/glb/ply/usd), so
    # deflate would burn CPU on multi-GB downloads for negligible size gain.
    zs = ZipStream(compress_type=zipfile.ZIP_STORED)
    for abspath, arcname in _iter_members(run_dir, mode):
        # add_path records path + arcname only; file bytes are read lazily during
        # iteration of the response, so the archive is never buffered in memory.
        zs.add_path(abspath, arcname)

    safe_name = run_dir.name
    logger.info("Streaming zip for run %s (include=%s)", safe_name, mode)
    return Response(
        zs,
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.zip"',
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # never let a proxy buffer the stream
        },
    )


def register(app) -> None:
    """Register this blueprint on a Flask ``app`` (convenience for ``app.py``)."""
    app.register_blueprint(zip_api)


__all__ = ["zip_api", "register"]
