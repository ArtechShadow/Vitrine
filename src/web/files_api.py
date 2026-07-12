# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only artifact-browser blueprint for the Vitrine web service.

Implements the "browse surface" from DDD §4 and the ArchiveSpace (PR #6)
frames/derivatives contract, consolidated into OUR security-constrained Flask
app instead of adopting the SPA's implied raw-path backend verbatim.

Endpoints (all GET, all read-only, all path-jailed to ``output/<id>/``)::

    GET /api/runs/<id>/tree                    recursive [{path,size,kind}]
    GET /api/runs/<id>/file?path=<rel>         range-served preview (allow-list)
    GET /api/scenes/<id>/frames?limit&offset   {total,offset,limit,frames[]}
    GET /api/scenes/<id>/frames/<name>         a single frame image
    GET /api/scenes/<id>/derivatives/<path>    contact_sheet.jpg / sparse_preview.jpg / …

Security posture (ADR-022 secure single-image):
  * This blueprint binds nothing — it is registered onto the app that already
    binds 127.0.0.1 loopback and is reached only via an SSH tunnel. It never
    introduces a socket, never listens on 0.0.0.0.
  * Every path parameter is run through ``werkzeug.security.safe_join`` (rejects
    ``..`` / absolute / encoded traversal) *and* ``Path.resolve()`` (canonicalises
    symlinks) *and* a strict ``relative_to`` + ``startswith`` jail against the
    per-run output root — hardening the ``app.py`` ``serve_job_file`` pattern so a
    sibling prefix (``/out/ab`` vs ``/out/abcdef``) can never leak.
  * A symlink whose canonical target escapes the jail resolves outside the root
    and is rejected with 403; the tree walk skips symlinks entirely.
  * Dotfiles and secret-shaped names (``.env``, ``*.key``, ``*credential*``,
    ``.anthropic_key`` …) are excluded from the tree and refused by the file
    reader, so nothing here can read ``/data/.anthropic_key`` or any path outside
    ``output/<id>/``.
  * There are no write endpoints.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file
from werkzeug.security import safe_join
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# Same output root the job manager / app.py use (env-overridable). Resolved once
# so the jail compares canonical paths (symlink-free) on every request.
OUTPUT_DIR = Path(os.environ.get("LFS_OUTPUT_DIR", "/data/output")).resolve()

# Directories that may hold the per-frame stills a scene's QA review renders,
# in preference order. A finished run may have pruned the heavy raw dirs
# (drive_ingestor prunes frames/frames_cleaned/frames_selected/colmap), so we
# probe several and fall back to an empty list rather than 404.
_FRAME_DIR_CANDIDATES = ("frames", "frames_selected", "frames_cleaned", "input")

# Image extensions treated as frames / thumbnails.
_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif",
}

# Extension allow-list for the generic file reader → canonical Content-Type.
# Anything not in this map is refused (403); we never serve arbitrary bytes.
# Text/log/json/markdown are given text mimetypes so browsers render them inline.
_MIME_OVERRIDES: dict[str, str] = {
    # text / logs / structured (inline-rendered)
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".csv": "text/csv; charset=utf-8",
    ".tsv": "text/tab-separated-values; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
    ".yml": "text/plain; charset=utf-8",
    ".toml": "text/plain; charset=utf-8",
    ".ini": "text/plain; charset=utf-8",
    ".mtl": "text/plain; charset=utf-8",
    ".usda": "text/plain; charset=utf-8",
    ".obj": "text/plain; charset=utf-8",  # Wavefront OBJ is ASCII
    # images (inline)
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    # 3D / splat assets (binary; the viewer route consumes these)
    ".ply": "application/octet-stream",
    ".splat": "application/octet-stream",
    ".ksplat": "application/octet-stream",
    ".spz": "application/octet-stream",
    ".sog": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".usdc": "application/octet-stream",
    ".usdz": "model/vnd.usdz+zip",
    ".exr": "application/octet-stream",
    # short preview clips
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_ALLOWED_EXTENSIONS = frozenset(_MIME_OVERRIDES)

# Bare (non-dot) names that must never be listed or served even though they lack
# a leading dot. Dotfiles are already excluded structurally.
_SENSITIVE_NAMES = frozenset({
    "env", "credentials", "credentials.json", "secrets", "secrets.json",
    "anthropic_key", "id_rsa", "id_ed25519", ".htpasswd",
})

# Soft cap so a pathological run (tens of thousands of frames) cannot make the
# tree endpoint allocate an unbounded response.
_MAX_TREE_ENTRIES = 50_000

files_api = Blueprint("files_api", __name__)


# ---------------------------------------------------------------------------
# Jail helpers — the load-bearing security boundary
# ---------------------------------------------------------------------------


def _is_hidden_or_sensitive(name: str) -> bool:
    """True if a single path component is a dotfile or secret-shaped."""
    if not name or name.startswith("."):
        return True
    low = name.lower()
    if low in _SENSITIVE_NAMES:
        return True
    if low.endswith((".key", ".pem", ".env", ".secret")):
        return True
    return "secret" in low or "credential" in low or "password" in low


def _run_root(run_id: str) -> Path:
    """Resolve the jail root for a run/scene id, or abort.

    ``<id>`` never contains a slash (Flask's default converter), but we still
    ``secure_filename`` it so a crafted id cannot introduce path separators or
    escape ``output/``.
    """
    safe_id = secure_filename(run_id or "")
    if not safe_id:
        abort(400, description="invalid run id")
    root = (OUTPUT_DIR / safe_id).resolve()
    # Belt-and-suspenders: the resolved root must itself live under OUTPUT_DIR.
    if root != OUTPUT_DIR and not str(root).startswith(str(OUTPUT_DIR) + os.sep):
        abort(403)
    if not root.is_dir():
        abort(404, description="run not found")
    return root


def _jailed(root: Path, rel: str) -> Path:
    """Return the canonical path for ``rel`` under ``root``, or abort.

    Layers: ``safe_join`` (lexical traversal / absolute rejection) →
    ``resolve`` (symlink canonicalisation) → strict ``relative_to`` +
    ``startswith`` containment → per-component dotfile/secret rejection. A
    symlink whose target escapes the root resolves outside it and is refused.
    """
    if rel is None or rel == "":
        abort(400, description="path is required")
    # NUL / control bytes explode deep inside pathlib/send_file as a 500;
    # reject them at the boundary (found by live probe 2026-07-09).
    if any(ord(c) < 0x20 for c in rel):
        abort(400, description="invalid path")

    joined = safe_join(str(root), rel)
    if joined is None:  # '..', absolute, or otherwise traversing
        abort(403)

    resolved = Path(joined).resolve()

    # Strict containment: equal to root or a genuine descendant (the trailing
    # os.sep stops '/out/abcdef' from matching a jail rooted at '/out/abc').
    root_str = str(root)
    if resolved != root and not str(resolved).startswith(root_str + os.sep):
        abort(403)

    # Refuse hidden / secret-shaped components anywhere in the relative path.
    try:
        rel_parts = resolved.relative_to(root).parts
    except ValueError:
        abort(403)
    if any(_is_hidden_or_sensitive(part) for part in rel_parts):
        abort(403)

    return resolved


def _mime_for(path: Path) -> str | None:
    """Allow-listed Content-Type for a file, or None if the extension is denied."""
    return _MIME_OVERRIDES.get(path.suffix.lower())


def _serve_file(path: Path, mimetype: str | None) -> Response:
    """Range/ETag-aware inline send of an existing, jailed, allow-listed file."""
    if not path.is_file():
        abort(404, description="file not found")
    resolved_mime = mimetype or _mime_for(path) or mimetypes.guess_type(path.name)[0]
    if resolved_mime is None:
        abort(403, description="file type not permitted")
    # conditional=True → honours Range + If-None-Match/If-Modified-Since and
    # sets ETag/Last-Modified/Accept-Ranges. as_attachment=False → inline.
    return send_file(
        str(path),
        mimetype=resolved_mime,
        as_attachment=False,
        conditional=True,
        etag=True,
        max_age=0,
    )


def _find_frames_dir(root: Path) -> Path | None:
    """First existing, non-empty frame directory for a run (or None)."""
    for name in _FRAME_DIR_CANDIDATES:
        candidate = root / name
        if candidate.is_dir() and not candidate.is_symlink():
            for entry in candidate.iterdir():
                if entry.is_file() and entry.suffix.lower() in _IMAGE_EXTENSIONS:
                    return candidate
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@files_api.route("/api/runs/<run_id>/tree")
def run_tree(run_id: str) -> Response:
    """Recursive artifact listing rooted at ``output/<id>/``.

    Returns ``{"run_id", "entries": [{path, size, kind}]}`` where ``kind`` is
    ``"file"`` or ``"dir"`` and ``path`` is POSIX-relative to the run root.
    Dotfiles, secret-shaped names, and symlinks are excluded; the walk is
    capped to keep the response bounded.
    """
    root = _run_root(run_id)

    entries: list[dict[str, object]] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune hidden/secret/symlinked subdirectories in place so os.walk
        # never descends into them.
        kept_dirs = []
        for d in sorted(dirnames):
            full = Path(dirpath) / d
            if _is_hidden_or_sensitive(d) or full.is_symlink():
                continue
            kept_dirs.append(d)
            rel = full.relative_to(root).as_posix()
            entries.append({"path": rel, "size": 0, "kind": "dir"})
        dirnames[:] = kept_dirs

        for f in sorted(filenames):
            full = Path(dirpath) / f
            if _is_hidden_or_sensitive(f) or full.is_symlink():
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            rel = full.relative_to(root).as_posix()
            entries.append({"path": rel, "size": size, "kind": "file"})

        if len(entries) >= _MAX_TREE_ENTRIES:
            truncated = True
            break

    entries.sort(key=lambda e: e["path"])
    if truncated:
        entries = entries[:_MAX_TREE_ENTRIES]

    return jsonify({
        "run_id": secure_filename(run_id),
        "count": len(entries),
        "truncated": truncated,
        "entries": entries,
    })


@files_api.route("/api/runs/<run_id>/file")
def run_file(run_id: str) -> Response:
    """Range-served, allow-listed preview of one file under a run root.

    Query param ``path`` is the run-relative path. Images/text/logs/json render
    inline; disallowed extensions and any traversal attempt return 403.
    """
    root = _run_root(run_id)
    rel = request.args.get("path", "")
    target = _jailed(root, rel)
    mime = _mime_for(target)
    if mime is None:
        abort(403, description="file type not permitted")
    return _serve_file(target, mime)


@files_api.route("/api/scenes/<scene_id>/frames")
def scene_frames(scene_id: str) -> Response:
    """Paginated, stably-ordered list of a scene's frame filenames.

    Response: ``{total, offset, limit, frames: [name, …]}`` — ``frames`` are
    bare filenames the SPA turns into ``/api/scenes/<id>/frames/<name>`` URLs.
    """
    root = _run_root(scene_id)

    try:
        limit = int(request.args.get("limit", 120))
    except (TypeError, ValueError):
        limit = 120
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(0, min(limit, 1000))  # clamp to a sane page size
    offset = max(0, offset)

    frames_dir = _find_frames_dir(root)
    if frames_dir is None:
        return jsonify({"total": 0, "offset": offset, "limit": limit, "frames": []})

    # Stable ordering: lexicographic by filename (frame_00001.jpg …).
    names = sorted(
        p.name
        for p in frames_dir.iterdir()
        if p.is_file()
        and not p.is_symlink()
        and p.suffix.lower() in _IMAGE_EXTENSIONS
        and not _is_hidden_or_sensitive(p.name)
    )
    total = len(names)
    page = names[offset:offset + limit] if limit else []

    return jsonify({
        "total": total,
        "offset": offset,
        "limit": limit,
        "frames": page,
    })


@files_api.route("/api/scenes/<scene_id>/frames/<path:name>")
def scene_frame(scene_id: str, name: str) -> Response:
    """Serve a single frame image (Range/ETag-aware, jailed to the frame dir)."""
    root = _run_root(scene_id)
    frames_dir = _find_frames_dir(root)
    if frames_dir is None:
        abort(404, description="no frames for scene")

    # Tolerate a leading 'frames/' the SPA may not strip.
    rel = name[len("frames/"):] if name.startswith("frames/") else name
    target = _jailed(frames_dir, rel)
    if target.suffix.lower() not in _IMAGE_EXTENSIONS:
        abort(403, description="not an image")
    return _serve_file(target, _mime_for(target) or "image/jpeg")


@files_api.route("/api/scenes/<scene_id>/derivatives/<path:deriv_path>")
def scene_derivative(scene_id: str, deriv_path: str) -> Response:
    """Serve a derivative artifact (contact_sheet.jpg, sparse_preview.jpg, …).

    Jailed to ``output/<id>/derivatives/``; allow-listed by extension.
    """
    root = _run_root(scene_id)
    deriv_dir = root / "derivatives"
    if not deriv_dir.is_dir():
        abort(404, description="no derivatives for scene")
    target = _jailed(deriv_dir, deriv_path)
    mime = _mime_for(target)
    if mime is None:
        abort(403, description="file type not permitted")
    return _serve_file(target, mime)


# ---------------------------------------------------------------------------
# Mesh viewer — a standalone <model-viewer> page for an object GLB. Output-dir
# based (no registered job needed), consistent with the rest of files_api, so it
# works for runs materialised directly on disk. Serves the vendored, offline
# model-viewer component; loopback + SSH-tunnel posture is unchanged.
# ---------------------------------------------------------------------------


def _best_glb(root: Path) -> Path | None:
    """Best GLB under a run: prefer the textured TRELLIS.2 export, then the largest."""
    cands = [c for c in (list(root.glob("objects/*.glb")) + list(root.glob("**/*.glb")))
             if c.is_file() and c.stat().st_size > 0]
    if not cands:
        return None
    cands.sort(key=lambda p: (0 if "trellis2" in p.name.lower() else 1, -p.stat().st_size))
    return cands[0]


@files_api.route("/mesh-view/<scene_id>")
def mesh_view(scene_id: str):
    """Standalone model-viewer page for the best object GLB under a run."""
    root = _run_root(scene_id)
    glb = _best_glb(root)
    if glb is None:
        abort(404, description="no GLB mesh found for this run")
    sid = secure_filename(scene_id)
    return render_template(
        "viewer_mesh.html", scene_id=sid,
        glb_url=f"/mesh-view/{sid}/glb", glb_name=glb.name,
    )


@files_api.route("/mesh-view/<scene_id>/glb")
def mesh_view_glb(scene_id: str) -> Response:
    """Serve the best object GLB under a run (jailed to output/<id>/)."""
    root = _run_root(scene_id)
    glb = _best_glb(root)
    if glb is None:
        abort(404, description="no GLB mesh found for this run")
    target = _jailed(root, glb.relative_to(root).as_posix())  # defensive re-jail
    return _serve_file(target, "model/gltf-binary")


# ---------------------------------------------------------------------------
# Blueprint-scoped JSON error responses (match app.py's JSON error contract)
# ---------------------------------------------------------------------------


@files_api.errorhandler(400)
def _bad_request(exc) -> tuple[Response, int]:
    return jsonify({"error": getattr(exc, "description", "bad request")}), 400


@files_api.errorhandler(403)
def _forbidden(exc) -> tuple[Response, int]:
    return jsonify({"error": "forbidden"}), 403


@files_api.errorhandler(404)
def _not_found(exc) -> tuple[Response, int]:
    return jsonify({"error": getattr(exc, "description", "not found")}), 404


def register(app) -> Blueprint:
    """Register this blueprint on the given Flask app. Called from app.py.

    Additive only: it introduces read-only ``/api/runs`` and
    ``/api/scenes/<id>/{frames,derivatives}`` routes and never shadows the
    existing job-centric routes. Introduces no network bind (the host app owns
    the 127.0.0.1 loopback bind mandated by ADR-022).
    """
    app.register_blueprint(files_api)
    logger.info("Registered files_api blueprint (read-only artifact browser)")
    return files_api
