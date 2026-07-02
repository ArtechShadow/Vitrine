# Vitrine web frontend

A Vitrine-owned, minimal **Vite + React 19 + TypeScript** SPA for the
capture-adaptive video/photo → 3DGS pipeline. It harvests the UX of the
community "ArchiveSpace" PR (#6) — source-picker home, URL-state create wizard,
library grid with filters, tabbed scene workspace, read-only frame/QA review,
and a Gaussian-splat viewer — but is a clean rewrite against **our** backend
contract. There is **no mock/preview layer**: the app only ever talks to the
real, same-origin Flask backend.

## Security posture

The app is served same-origin by the loopback Flask app (`src/web/app.py`) on
`127.0.0.1:7860` and reached externally only over an SSH tunnel
(`ssh -N -L 7860:localhost:7860`). All API traffic is relative (`/api/...`,
`/stream/...`); there are **zero cross-origin or CDN fetches**, so the built
bundle is offline-signable. The splat viewer runs with
`sharedMemoryForWorkers: false` and `gpuAcceleratedSort: false`, so **no
SharedArrayBuffer** and therefore **no COOP/COEP headers** are needed on the
loopback server.

## Build

```bash
npm ci            # exact, pinned install from the committed lockfile
npm run build     # tsc -b && vite build → dist/
```

`dist/` is **not** committed here; the `node:20` builder stage in
`Dockerfile.consolidated` runs `npm ci && npm run build` at image-build time and
bakes the output into `src/web/static/spa/`, which Flask serves under
`/static/spa/` with an SPA catch-all. Client assets use the `/static/spa/` base
(`vite.config.ts`), while client routes (`/`, `/library`, `/create`,
`/scenes/:id`, `/viewer`, `/pipeline`) are handled by the router.

## Develop

```bash
npm run dev       # http://127.0.0.1:5173, proxies /api + /stream to :7860
```

The dev server binds loopback and proxies to the Flask backend. Override the
backend with `VITE_DEV_BACKEND` if it runs elsewhere on localhost.

## Backend contract

Same-origin endpoints this app consumes (served by the `scenes_api`,
`files_api`, `zip_api`, and `splat_api` blueprints plus the existing SSE route):

| Purpose            | Endpoint                                   |
| ------------------ | ------------------------------------------ |
| List / get / delete| `GET|DELETE /api/scenes[/:id]`             |
| Upload video       | `POST /api/scenes/upload`                  |
| Upload photos      | `POST /api/scenes/upload-images`           |
| Upload folder/ZIP  | `POST /api/scenes/upload-zip`              |
| Google Drive import| `POST /api/import/google-drive`            |
| Frames (read-only) | `GET /api/scenes/:id/frames[/:name]`       |
| Derivatives/preview| `GET /api/scenes/:id/derivatives/:path`    |
| Splat asset        | `GET /api/scenes/:id/splat/:file`          |
| Live progress      | `GET /stream/:id` (SSE, canonical)         |
| Progress fallback  | `GET /api/scenes/:id/progress`             |
| Run archive (zip)  | `GET /api/scenes/:id/export`               |
| Capability flags   | `GET /api/tools`                           |

SSE is the primary progress channel; polling is only a fallback. Panels whose
endpoints Vitrine deliberately does not build are gated on `/api/tools`.

## Configuration

All env vars are optional (see `.env.example`). There is intentionally no
`VITE_PREVIEW_MODE` / preview API. `VITE_DEMO_SPLAT_URL` may point at a small
committed sample `.ksplat` for the viewer empty-state.
