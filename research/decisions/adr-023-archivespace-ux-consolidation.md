# ADR-023 — ArchiveSpace (PR #6) UX consolidation into the Flask control surface

Status: **Accepted** (2026-07-02) · Companion: [ADR-022](adr-022-secure-single-image-architecture.md)
(secure single-image appliance), [PRD](../../docs/prd/vitrine-v2-secure-mega-image.md),
[DDD](../../docs/design/ddd-vitrine-v2.md) · Related: [ADR-006](adr-006-splat-transform-web-delivery.md)
(`.ksplat` web delivery), [ADR-015 (web onboarding)](adr-015-vitrine-web-onboarding.md) ·
Audit input: [master-audit-2026-07-02 finding #13](../../docs/audit/master-audit-2026-07-02.md)

## Context

Community PR #6 ("ArchiveSpace") landed a standalone **Vite + React 19 + TypeScript
SPA** under `web-interface/` (routes `/`, `/library`, `/create`, `/scenes/:sceneId`,
`/pipeline`, `/viewer`, `/upload`). It is a genuinely good curator UX — a source-picker
Home, a URL-state Create wizard, a filterable library grid, a scene workspace, a QA-swipe
frame review, and a **three.js + `@mkkellogg/gaussian-splats-3d` splat viewer** — and it
implies a clean backend contract (`/api/scenes/*`, `/api/import/google-drive`,
`/api/scenes/upload-images`, `/api/scenes/upload-zip`, `/api/frames`, `/api/system/stats`).

We are **not adopting PR #6 verbatim.** Three constraints make a straight merge unacceptable:

1. **Security (ADR-022 D3/D4, PRD R3).** ADR-022 makes the appliance loopback-only,
   reached over an SSH `LocalForward` bridge, with the Flask web app as the single operator
   plane. The master-audit finding #13 records ~8 unauthenticated services on `0.0.0.0`;
   our own `src/web/app.py` still calls `app.run(host="0.0.0.0", …)` (app.py:1066). A second
   long-running Node/Vite server (PR #6's `vite`, `vite preview`) would be a *new* network
   surface and a *new* runtime dependency, directly contradicting the single-image,
   loopback-only, IT-signable goal.
2. **Ownership (CLAUDE.md §7, BOUNDARIES).** Vitrine's backend is the existing Flask app
   (`src/web/app.py` + `job_manager.py` + `pipeline_runner.py`), running as user `vitrine`
   in venv `/opt/venvs/pipeline`. The PR's SPA is built against a *different, partly
   fictional* backend: five of its service functions are **mocks** (`uploadImages`,
   `uploadZip`, `importGoogleDriveLink`, `exportArchive`, `exportForGameEngine`/`exportForUnreal`
   in `web-interface/src/api/archiveService.ts`) and it ships a `previewApi`/`previewData`
   demo-mode plus a `netlify.toml` deploy target that has no place in an offline appliance.
3. **Duplication risk.** The SPA's per-stage control surface (`extract-frames`, `run-colmap`,
   `recover-colmap`, `quality-reconstruction`, `train-splat`, `import-splat`, `active-splat`,
   `run-lingbot`, `run-ppisp`, `run-artifixer`, `metadata` PATCH, `jobs/pause|resume|cancel`)
   assumes a scene-centric, stage-granular state machine that **we do not have** — our
   orchestrator is job-centric (Claude Code + `stages.py`), with SSE `/stream/<job>` as the
   canonical progress channel. Reproducing that surface would fork the pipeline's control model.

The mandate is: **take the UX and the *implied* contract, consolidate them into our
security-constrained Flask service — ideas, not slavish code.** Land three features now:
(1) a file browser with previews, (2) a per-run zip downloader, (3) a 3D splat viewer.

## Decision

### D1. Absorb PR #6 into the Flask control surface — no standalone SPA server, no Rust rewrite, no runtime Node

The ArchiveSpace UX is re-homed **inside the existing Flask app** (`src/web`, served by
the `web` supervisord program as user `vitrine`). There is **no second web server**: no
Node/Vite process at runtime, no Rust rewrite of the backend. The Rust/Axum onboarding
wizard (`onboarding/`, :8088) stays a separate, minimal `exhibit.toml` tool and is **out of
scope here** except that it too must rebind to `127.0.0.1` (its `0.0.0.0:8088` bind is the
same finding-#13 class); folding its `/api/manifest` into Flask is a deferred follow-up
(open question, not decided here).

New capability lands as four small **additive Flask blueprints** registered by `app.py`
— `scenes_api`, `files_api`, `zip_api`, `splat_api` — that **alias/delegate to the existing
handlers** rather than duplicating logic. The job-centric routes that `index.html`,
`viewer.html`, and the orchestrator callbacks depend on (`/upload`, `/status/<job>`,
`/stream/<job>`, `/download/<job>`, `/viewer/<job>`, `/preview/<job>/<stage>`,
`/api/job/<job>/…`, `/api/ingest/drive`) are **never replaced.**

Two front-end tracks, both **same-origin on `127.0.0.1:7860`**, both **zero runtime CDN
fetches** (offline / IT-signable):

- **Track 1 (ships the three mandated features immediately, no build toolchain):** vendor
  pinned `three` + `@mkkellogg/gaussian-splats-3d` into `src/web/static/vendor/`, port the
  ~150-line `SplatViewer.tsx` logic into a Jinja template `viewer_splat.html`, and extend
  the existing `viewer.html` with a splat/mesh tab (stripping its CDN loads).
- **Track 2 (the richer ArchiveSpace UX):** a **new Vitrine-owned** minimal Vite+React app
  at `src/web/frontend/`, harvesting PR #6 patterns with its API client rewritten against
  **our** contract (D2). It is compiled by a `node:20` builder stage in
  `Dockerfile.consolidated` **at image-build time only** (`npm ci && vite build`); the static
  `dist/` is baked into `src/web/static/spa/` and served by a Flask SPA catch-all that
  **never shadows `/api/*` or real files**. No Node ships in the runtime image.

### D2. `scene_id == job_id` alias facade — `/api/scenes/*` over DDD-canonical `/api/runs/*`

The DDD (§5) canonicalises the read model as `Run{id, …}` over `/api/runs/*`. PR #6 speaks
`/api/scenes/*` with a `scene_id`. **We treat `scene_id` as an alias of `job_id`/`run id`**
(one identifier, three names). `scenes_api` implements the `/api/scenes/*` surface as a thin
facade over the canonical `/api/runs/*` read model and the existing job handlers — the SPA is
satisfied without inventing a parallel store (the filesystem `output/<id>/` remains the store,
DDD §5).

**Error-shape rule.** Every JSON error from the new blueprints returns
`{"detail": "<human message>", "error": "<stable_code>"}` with the appropriate HTTP status.
`detail` is what PR #6's client already reads (`err.detail ?? …` throughout `client.ts`);
`error` is a stable machine code for our own tooling. This is uniform across `scenes_api`,
`files_api`, `zip_api`, `splat_api`.

**Consolidated endpoint table** (SPA call → new alias → delegated existing handler):

| SPA call (`web-interface`) | Facade endpoint (new) | Canonical / delegate (existing) | Notes |
|---|---|---|---|
| `listScenes()` | `GET /api/scenes` | `GET /api/runs` → scans `output/*` / `/jobs` | list + `capture.json` summary |
| `getScene(id)` | `GET /api/scenes/<id>` | `GET /api/runs/<id>` (built from `/status/<id>` + job scan) | `SceneDetail` read model |
| `getProgress(id, job)` | `GET /api/scenes/<id>/progress?job=` | **synthesized** from `/status/<id>` | SSE `/stream/<id>` stays canonical; this poll is a *fallback* for the SPA's 1.5–2.5 s contract |
| `getSystemStats()` | `GET /api/system/stats` | **new** (`pynvml` optional; degrades if absent) | CPU/RAM/GPU/VRAM/power |
| `uploadVideo()` | `POST /api/scenes/upload` | `POST /upload` | video ingest (already real) |
| `uploadImages()` **(was mock)** | `POST /api/scenes/upload-images` | `POST /upload` (multi-file) → `image_decoder.decode_directory` → `queue_job` | **real** (D6) |
| `uploadZip()` **(was mock)** | `POST /api/scenes/upload-zip` | new: extract to `INPUT_DIR/<job>_images/` → decode → `queue_job` | **real** (D6) |
| `importGoogleDriveLink()` **(was mock)** | `POST /api/import/google-drive` | `POST /api/ingest/drive` | **real** alias (D6) |
| `listFrames()` / `cullFrames()` | `GET /api/frames?scene=<id>` | `GET /api/job/<id>/previews` + path-jailed file serve | QA-swipe read model |
| `derivativeUrl(id, path)` | `GET /api/scenes/<id>/derivatives/<path>` | `GET /preview/<id>/<stage>` + `GET /api/job/<id>/file/<path>` | path-jailed to `output/<id>/` |
| `splatUrl(id, file)` | `GET /api/scenes/<id>/splat/<filename>` | new `splat_api`, path-jailed serve of run splat | feeds the D3 viewer; default `scene.ply` |
| `exportArchive()` **(was mock)** | `POST /api/scenes/<id>/export` → `GET /api/runs/<id>/zip` | `GET /download/<id>` (streamed zip) | **real** per-run zip (D6) |
| `exportForGameEngine()`/`exportForUnreal()` **(mock)** | `POST /api/scenes/<id>/export/unreal` | — | **deferred** (D6): `501`/`{detail:"…deferred"}` |
| `deleteScene(id)` | `DELETE /api/scenes/<id>` | `DELETE /job/<id>` | |
| `getTools()` | `GET /api/tools` | `GET /health` + `GET /api/config` | capability probe |
| per-stage: `extractFrames`, `runColmap`, `recoverColmap`, `runQualityReconstruction`, `trainSplat`, `importExternalSplat`, `setActiveSplat`, `runLingbot`, `runPpisp`, `runArtifixer`, `updateMetadata`, `pause/resume/cancelJob`, `regenerateSparsePreview`, `getBranches` | **not reproduced** (D6) | orchestrator owns the pipeline; expose only start (`/upload*`) + cancel (`DELETE`) | scene-granular stage machine is not our model |

`GET /api/runs/<id>/zip` (DDD §5 canonical) is the primary zip route; `/api/scenes/<id>/zip`
and `POST /api/scenes/<id>/export` are aliases of it. All three delegate to the streamed
implementation (`zip_api`, `zipstream-ng`), which itself supersedes the buffered
`/download/<id>`.

This table delivers the three mandated features against real backends: the **file browser +
previews** (PRD R5, DDD §4/§5 — `GET /api/scenes/<id>`, `.../derivatives/<path>`,
`GET /api/frames`), the **per-run zip downloader** (PRD R6 — `GET /api/runs/<id>/zip` and its
`/export` alias), and the **3D splat viewer** (`GET /api/scenes/<id>/splat/<filename>`, D3).

### D3. Splat viewer — `@mkkellogg/gaussian-splats-3d`, `sharedMemoryForWorkers:false` / `gpuAcceleratedSort:false` → no COOP/COEP on the loopback service

We adopt PR #6's viewer engine, **`@mkkellogg/gaussian-splats-3d`** (three.js-based),
constructed exactly as `SplatViewer.tsx` already does:

```
new GaussianSplats3D.Viewer({ …, sharedMemoryForWorkers: false, gpuAcceleratedSort: false })
```

**Rationale — the security-critical part:** `sharedMemoryForWorkers: true` requires
`SharedArrayBuffer`, which browsers gate behind **cross-origin isolation** — i.e. the server
must send `Cross-Origin-Opener-Policy: same-origin` **and** `Cross-Origin-Embedder-Policy:
require-corp`. Those headers would force *every* sub-resource (previews, GLBs, fonts, the
splat itself) to be CORP/CORS-clean and would break the simple same-origin Flask static
serving on the loopback appliance. By keeping `sharedMemoryForWorkers:false` and
`gpuAcceleratedSort:false` we get a CPU-sorted, non-SAB viewer that runs **without any
COOP/COEP headers** — no header surgery on Flask, no cross-origin-isolation coupling, fully
compatible with the loopback SSH-tunnel model. The modest sort-performance cost is acceptable
for a curator preview and is the correct trade for the appliance's simplicity/security.

Both tracks use the same viewer: Track 1 in `viewer_splat.html` (vendored, `<script>`),
Track 2 in `src/web/frontend/` (bundled). The splat source is served same-origin by
`splat_api` (D2), path-jailed to `output/<id>/`.

### D4. `.ksplat` format-compatibility verdict + chosen web-derivative path (from IMPL-7)

**Verdict: the two `.ksplat` extensions are a name collision, not a shared format.** Our
pipeline's `.ksplat` (ADR-006, `src/pipeline/splat_optimizer.py`) is the **PlayCanvas
`@playcanvas/splat-transform`** compressed format. The PR #6 viewer,
`@mkkellogg/gaussian-splats-3d`, reads its **own** `.ksplat` (its internal `SplatBuffer`
layout, generated by *its* `.ply`/`.splat` loaders) — a **different, incompatible binary
layout** that happens to share the file extension. Handing our splat-transform `.ksplat`
straight to the mkkellogg loader **does not work.** The mkkellogg viewer *does* natively
read standard **`.ply`** (INRIA 3DGS) and the antimatter15 **`.splat`** format.

**Chosen web-derivative path:** the viewer is fed the **uncompressed / source `.ply`**
(`splatUrl()` already defaults to `scene.ply`), which the mkkellogg loader consumes natively
and which ADR-006 already keeps as the source-of-truth (the `.ksplat` there is a *delivery*
artefact, not the master). Concretely:

- **Now:** `splat_api` serves the run's trained `scene.ply` to the viewer. No conversion,
  works today, honours ADR-006's "always retain the source `.ply`".
- **Web-size optimisation (opt-in):** where a *smaller* delivery is wanted, produce an
  **mkkellogg-native `.ksplat`** (or `.splat`) — i.e. run the mkkellogg converter on the
  `.ply`, **not** the PlayCanvas `.ksplat` — and serve that. The PlayCanvas `.ksplat` remains
  a valid artefact for PlayCanvas/SuperSplat consumers (ADR-006) but is **not** the viewer
  feed. We deliberately do **not** try to make one `.ksplat` serve both ecosystems.

This keeps ADR-006 intact (PLY-first, `.ksplat` as an external-delivery derivative) and
removes the trap of assuming the two `.ksplat`s interoperate.

### D5. Loopback bind default + `LFS_WEB_HOST` opt-in for the docker-net topology

Per ADR-022 D3 and PRD R3, the Flask app **binds `127.0.0.1:7860` by default**, fixing the
current `app.run(host="0.0.0.0", …)` (app.py:1066 — master-audit finding #13). The bind host
is read from an env var:

```
host = os.environ.get("LFS_WEB_HOST", "127.0.0.1")   # default loopback; NEVER 0.0.0.0 implicitly
```

- **Default (unset):** loopback only — external access is *only* via `ssh -N -L
  7860:localhost:7860 user@rig` (PRD §6). Nothing on the LAN.
- **Opt-in (`LFS_WEB_HOST=0.0.0.0`):** explicitly required *only* for **container-to-container**
  reachability on the shared docker networks (`v2g-net` / `visionclaw_network`), where the
  agentbox and VisionFlow reach the pipeline by service DNS (`gaussian-toolkit:7860`). This is
  an in-cluster surface behind the docker network, **not** a host LAN publish — the host
  publish stays `127.0.0.1:7860:7860` regardless (ADR-022 D3). The opt-in is a conscious,
  logged decision, never the default, and is documented as the *only* sanctioned way to widen
  the bind.

The four new blueprints inherit this — none of them opens its own socket; they are Flask
routes on the single loopback app.

### D6. Five PR mocks → real implementations (one deferred); per-stage control surface not reproduced

The five `archiveService.ts` mocks are resolved as:

| Mock | Disposition |
|---|---|
| `uploadImages` → `POST /api/scenes/upload-images` | **real** — multi-file drag-drop → `image_decoder.decode_directory` → `queue_job` (PRD R4, DDD §4 ingest) |
| `uploadZip` → `POST /api/scenes/upload-zip` | **real** — server-side unzip (path-jailed) → decode → `queue_job` |
| `importGoogleDriveLink` → `POST /api/import/google-drive` | **real** — alias of the existing `POST /api/ingest/drive` (gdown path) |
| `exportArchive` → `POST /api/scenes/<id>/export` | **real** — per-run streamed zip (D2/D4), aliases `GET /api/runs/<id>/zip` |
| `exportForGameEngine`/`exportForUnreal` → `POST /api/scenes/<id>/export/unreal` | **deferred** — returns a `{detail, error}` "not yet available" (`501`); the UE/FBX path (ADR-019) is not wired to the web surface this iteration |

The **per-stage control surface is deliberately NOT reproduced** (see the table in D2): our
pipeline is job-centric with SSE progress, not a scene-granular stage machine. The SPA gets
**start** (the `upload*`/`import` ingest endpoints) and **cancel** (`DELETE /api/scenes/<id>`),
plus read-only progress; individual `run-colmap`/`train-splat`/`recover-*`/`active-splat`/
`run-artifixer`/stage-PATCH operations are left to the orchestrator and are not exposed as web
mutations.

### D7. Preview-mode / Netlify stripped

`VITE_PREVIEW_MODE`, `previewApi.ts`, `previewData.ts`, `src/lib/previewMode.ts`, the
`build:preview`/`preview:ui` scripts, and `netlify.toml` are **removed** from the Track-2 app.
The appliance is offline and same-origin — the SPA only ever talks to the real loopback
backend; there is no demo/offline deploy target. `VITE_DEMO_SPLAT_URL` may *optionally* point
at a small committed sample `.ksplat`/`.ply` for a first-run empty state, but nothing else
from the preview stack survives. Track 2's dev `vite.config.ts` proxy target is repointed to
the real Flask origin (`http://127.0.0.1:7860`) for local dev only; production is the baked
`dist/` served by Flask.

### D8. `web-interface/` retained as an un-built reference bank

The PR #6 tree at `web-interface/` is **kept in-repo as a read-only reference bank** (source
of the UX patterns and the `SplatViewer` logic we port), but it is **not built, not served,
and not on any runtime path** — no Dockerfile stage compiles it, no supervisord program runs
it. It is design provenance for Track 1/Track 2, nothing more. (If it is ever removed, this
ADR and the ported templates/components remain the record.)

### D9. Exact dependency pins (no floating ranges)

Per CLAUDE.md directive §3 (pin exact, no floating `latest`) and PRD R9, PR #6's caret ranges
are pinned to **exact** versions; the lockfile is committed; **zero runtime CDN fetches**.

**Track 2 SPA (`src/web/frontend/package.json`, `npm ci` at image-build):**

| Package | Pin |
|---|---|
| `@mkkellogg/gaussian-splats-3d` | `0.4.6` |
| `three` | `0.175.0` |
| `react` / `react-dom` | `19.0.0` |
| `react-router-dom` | `7.1.0` |
| `@types/react` / `@types/react-dom` | `19.0.0` |
| `@types/three` | `0.185.0` |
| `@vitejs/plugin-react` | `4.3.4` |
| `typescript` | `5.7.2` |
| `vite` | `6.0.5` |
| builder image | `node:20` (build-time only; no runtime Node) |

**Track 1 vendored (`src/web/static/vendor/`):** the pinned, self-hosted UMD/ES builds of
`three@0.175.0` and `@mkkellogg/gaussian-splats-3d@0.4.6` (committed, no CDN). The pipeline's
existing `@playcanvas/splat-transform@2.3.2` (ADR-006) is **unchanged** — it remains the
external-delivery `.ksplat` producer, distinct from the viewer's mkkellogg format (D4).

## Consequences

**Positive**
- One operator surface, one server, one bind — the ArchiveSpace UX ships without adding a
  network surface, a runtime language, or a second auth boundary. Loopback-only is preserved
  (ADR-022 D3, PRD R3); finding #13's `0.0.0.0` bind is fixed at the default.
- The three mandated features land against real backends by *aliasing* existing handlers
  (no logic duplication): file browser (D2 derivatives + frames), per-run zip (D2/D4 streamed),
  splat viewer (D3 mkkellogg on native `.ply`).
- No COOP/COEP header coupling on the loopback app (D3) — simplest possible static serving.
- The `.ksplat` name-collision trap is documented and avoided (D4); ADR-006 stays coherent.
- Offline / IT-signable: pins exact, lockfile committed, no CDN, no Netlify, no preview mode
  (D7/D9).

**Negative / accepted**
- Two front-end tracks to maintain (vendored Jinja viewer *and* a compiled SPA). Accepted:
  Track 1 de-risks the three features immediately with zero toolchain; Track 2 is the richer,
  optional UX and is build-time-only.
- CPU-sorted splat viewer (no `gpuAcceleratedSort`, no SAB) is slower on very large scenes.
  Accepted trade for no COOP/COEP and loopback simplicity (D3).
- We ship an mkkellogg-native derivative path *in addition to* the PlayCanvas `.ksplat`
  (D4) — a second web splat artefact. Accepted: they serve different ecosystems and the `.ply`
  master covers both.
- The scene-granular per-stage control surface PR #6 assumes is intentionally absent (D6);
  power users still drive stages via the orchestrator/MCP, not the web UI.
- `LFS_WEB_HOST=0.0.0.0` remains a footgun if misused on a host publish; mitigated by making
  it opt-in, docker-net-only, and never the host-publish target (D5).

## Alternatives rejected
- **Adopt PR #6 verbatim as a standalone SPA server (+ Netlify/preview mode).** Rejected — a
  second runtime server + network surface + demo-deploy target, straight against ADR-022's
  single-image loopback-only sign-off.
- **Rewrite the backend in Rust/Axum (extend `onboarding/`).** Rejected — throws away the
  working Flask orchestrator/job model for no security or capability gain; the wizard stays a
  minimal separate tool (only its bind is fixed).
- **Feed the pipeline's PlayCanvas `.ksplat` directly to the mkkellogg viewer.** Rejected —
  incompatible formats (D4); it would silently fail to load.
- **Enable `sharedMemoryForWorkers`/`gpuAcceleratedSort` for viewer performance.** Rejected —
  forces cross-origin isolation (COOP/COEP) on the whole app, breaking simple same-origin
  static serving on the loopback appliance (D3).
- **Reproduce PR #6's full per-stage `/api/scenes/<id>/…` mutation surface.** Rejected —
  forks the job-centric pipeline control model (D6); SSE `/stream/<job>` + start/cancel is the
  contract.
