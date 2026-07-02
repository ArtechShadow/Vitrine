# ⚠ REFERENCE ONLY — not built, installed, or served

This directory is the **community PR #6 "ArchiveSpace" React SPA**, kept in-repo as a
read-only **reference bank** for its UX patterns and its implied backend contract.

**It is NOT the Vitrine web frontend.** Do not build, `npm install`, deploy, or wire it
into the running service. Its Netlify/preview config and mocked backend (`delay()`
stubs against a Windows FastAPI on `:8000` that never existed here) are inert.

The Vitrine-owned consolidation lives elsewhere and is the real deliverable:

- **Backend** — additive Flask blueprints in `src/web/` (`scenes_api.py`, `files_api.py`,
  `zip_api.py`, `splat_api.py`), loopback-only (`127.0.0.1:7860`), reached via SSH tunnel.
- **Frontend** — a Vitrine-owned Vite+React app at `src/web/frontend/` that harvests these
  patterns against our real API, built at image-build time and served same-origin by Flask.
- **Viewer** — vendored `@mkkellogg/gaussian-splats-3d` + three.js in `src/web/static/vendor/`,
  wired via `templates/viewer_splat.html` (no CDN, offline-capable).

Rationale and the full decision: `research/decisions/adr-023-archivespace-ux-consolidation.md`.
