# DDD — Vitrine v2 design & bounded contexts

Companion: [PRD](../prd/vitrine-v2-secure-mega-image.md) · [ADR-022](../../research/decisions/adr-022-secure-single-image-architecture.md) · Date 2026-07-02

## 1. Bounded contexts

| Context | Responsibility | Runs as | Venv | Trust |
|---|---|---|---|---|
| **Operator UI** | Web control plane: ingest, monitor, browse, preview, zip, disk/health | `vitrine` | `pipeline` | holds secrets |
| **Ingest** | Raw drag-drop upload + Drive pull → decode → stage frames → enqueue job | `vitrine` | `pipeline` | holds secrets |
| **Orchestration** | Drive the capture→scene pipeline (Claude Code + stages) | `vitrine` | `pipeline` | holds secrets/OAuth |
| **Reconstruction** | COLMAP SfM, LichtFeld/gsplat 3DGS, mesh/texture | `vitrine` | `pipeline` + native `/opt/lichtfeld/bin` | — |
| **Object gen (ComfyUI)** | TRELLIS.2 / Hunyuan / SAM3 / FLUX on ComfyUI | `comfyui` | `comfyui` | no secrets |
| **Refinement (ArtiFixer)** | Optional diffusion enhance/distill of a recon | `artifixer` | `artifixer` | no secrets |
| **Artifact store** | `output/<run>/…` read model for the browser | `vitrine` | `pipeline` | read-only, path-jailed |

Boundary rule: cross-context calls are **HTTP on the internal loopback/docker net** (ComfyUI `:8188`, LichtFeld MCP `:45677`, agent LLM), never shared Python imports across venvs. Secrets never cross into `comfyui`/`artifixer`.

## 2. Image build (multi-stage) — `Dockerfile.appliance`

```
Stage 0  base            = nvidia/cuda:12.8.0-devel-ubuntu24.04
Stage 1  lichtfeld-builder  (from lf_build2.sh, verbatim upstream ubuntu.yml)
           → /out/{LichtFeld-Studio, liblfs_*.so, vcpkg_installed/.../lib/*.so}
Stage 2  comfyui-builder    venv /opt/venvs/comfyui + ComfyUI + pinned custom nodes
Stage 3  artifixer-builder  venv /opt/venvs/artifixer + Wan2.1 stack (pinned)
Stage 4  runtime (final):
           - system: colmap, xvfb/x11vnc, ttyd, gtk3/usd/nvimgcodec runtime libs, gosu
           - COPY --from=1 → /opt/lichtfeld/{bin,lib}  (patchelf RUNPATH=$ORIGIN/../lib)
           - venv /opt/venvs/pipeline + requirements (torch/gsplat/pyiqa/rawpy/gdown/flask)
           - COPY --from=2,3 the comfyui/artifixer venvs + apps
           - COPY src/pipeline src/web  (BAKED, not mounted)
           - useradd vitrine(1000) comfyui(1001) artifixer(1002); mkdir /run/vitrine-secrets 0700 vitrine
           - supervisord.conf, entrypoint.sh
```
Caching: stages 1–3 rebuild only when their inputs change; editing a pipeline module only re-runs the cheap COPY in stage 4.

## 3. Process model — `supervisord.conf` (v2)

| program | command | user |
|---|---|---|
| comfyui | `/opt/venvs/comfyui/bin/python /opt/comfyui/main.py --listen 127.0.0.1 --port 8188 --cuda-device 0` | comfyui |
| web | `/opt/venvs/pipeline/bin/python /opt/web-interface/app.py` (binds `127.0.0.1:7860` inside; publish maps host loopback) | vitrine |
| lichtfeld-mcp | `scripts/lichtfeld_mcp_bridge.py` → `/opt/lichtfeld/bin/LichtFeld-Studio` (loopback :45677) | vitrine |
| terminal | ttyd `--credential` (token) or **omit** | vitrine |
| artifixer-runner | on-demand (spawned by orchestrator via a small queue), `/opt/venvs/artifixer/bin/python …` | artifixer |

ArtiFixer is **not** a permanent process — it's launched per-job as `artifixer` (gosu) with only `output/<run>` and model paths mounted-in via the shared volume, never the secrets dir.

## 4. Operator UI — component design (extends `src/web`)

Reuse today's Flask app + `viewer.html`; add four small Flask blueprints (`scenes_api`, `files_api`, `zip_api`, `splat_api`) registered by `app.py` — additive, never replacing the existing job-centric routes that `index.html`/`viewer.html` and the orchestrator callbacks depend on.

**Endpoint summary**

- **Ingest**:
  - `POST /api/scenes/upload` — chunked multipart (field `file` + optional `title`/`fps`/`qa_preset`); aliases the existing `/upload` path; returns `{scene_id, metadata:SceneMetadata}`. Legacy `POST /upload` (field `video`) kept unchanged.
  - `POST /api/scenes/upload-images` — multipart batch stills (jpg/png/DNG/HEIC → `INPUT_DIR/<job>_images/` → `image_decoder.decode_directory` → enqueue); 2 GB total cap, `secure_filename`, per-file extension allow-list; returns `{scene_id, metadata}`.
  - `POST /api/scenes/upload-zip` — multipart zip capture bundle; extracted with a zip-slip path guard and decompressed-size cap into a new job input dir; returns `{scene_id, metadata}`.
  - `POST /api/import/google-drive` — JSON `{url, contentType?, title?}`; reuses existing Drive/gdown ingest logic; returns `{scene_id, state:'downloading'}`. No new credential surface.
  - Legacy `POST /ingest/url` kept as-is.
- **Scenes alias facade** (`scenes_api.py`): `scene_id` == `job_id` 1:1; all `/api/scenes/*` routes delegate to `job_manager`. Error shape is always `{detail, error}` (never bare strings) so the SPA can render them uniformly. Key aliases:
  - `GET /api/scenes` — list; synthesized from `job_manager.list_jobs()` + on-disk outputs (thumbnail via derivatives URL).
  - `GET /api/scenes/<id>` — detail; synthesized from `Job.to_dict()` + `ksplat_path` discovery.
  - `GET /api/scenes/<id>/progress?job=` — polling fallback only (SSE `GET /stream/<id>` is canonical); returns `ProgressInfo{status,stage,stage_label,stage_index,stage_count,percent,message,log_tail}`.
  - `DELETE /api/scenes/<id>` — delegates to existing `delete_job` (cancels if running).
  - `POST /api/scenes/<id>/export` — returns `{downloadUrl:'/api/runs/<id>/zip'}`.
- **Run browser** (`files_api.py`): `GET /api/runs` (list `output/*` + capture.json summary), `GET /api/runs/<id>/tree` (path-jailed recursive `[{path,size,kind}]`, dotfiles + `.secrets` excluded), `GET /api/runs/<id>/file?path=…` (range-served preview: images/text inline, `.glb` → mesh viewer, `.ply/.ksplat` → splat viewer).
  - `GET /api/scenes/<id>/frames?limit=&offset=` — paginated frame list from `output/<id>/frames/` or input-images dir; returns `{total,offset,limit,frames:string[]}`.
  - `GET /api/scenes/<id>/frames/<name>` — image bytes; `safe_join` + extension allow-list, path-jailed to `output/<id>/`.
  - `GET /api/scenes/<id>/derivatives/<path>` — `contact_sheet.jpg`, `sparse_preview.jpg`, etc.; path-jailed, dotfiles excluded.
- **Zip** (`zip_api.py`): `GET /api/runs/<id>/zip?include=all|assets` → `zipstream-ng` (streamed, constant memory); default excludes regenerable intermediates (COLMAP db, undistorted images, raw frames) unless `include=all`. Legacy `GET /download/<job_id>` kept for the current Jinja UI.
- **Splat serve** (`splat_api.py`):
  - `GET /api/scenes/<id>/splat/<filename>` — Range- and ETag-served splat bytes consumed by `@mkkellogg/gaussian-splats-3d` `addSplatScene()`. Discovery order: `output/<id>/web/scene.ksplat` → `model/*.ply` → `*.splat`; `Content-Type: application/octet-stream`. Path-traversal-guarded; mirrors the existing `/mesh/<id>` pattern. **This is the route absent today that unlocks in-browser 3DGS viewing.**
  - `GET /splat/<job_id>` — convenience 302/serve to the best available splat for the job (for `viewer_splat.html`).
- **System and tooling stats**:
  - `GET /api/system/stats` — `SystemStats{gpu_available,gpu_name,vram_total_mb,vram_used_mb,cpu_percent,ram_used_mb,ram_total_mb}` via `pynvml`/`psutil` best-effort; all numeric fields zero and `gpu_available:false` when unavailable. Optional dep: `pynvml`.
  - `GET /api/tools` — availability flags; `nvidia_artifixer`/`lingbot_map`/`ppisp` always report `available:false` so SPA panels degrade gracefully.
- **Inspection endpoints** (replace tab6 `docker exec`): `GET /api/diskusage` (per-mount + per-run + image-layer sizes), `GET /api/health/processes` (each service's user+venv+GPU), `GET /api/tools/lichtfeld/version`.
- Security: all `path=` params resolved and asserted to stay under `output/` (jail); dotfiles and `.secrets` entries never served. No write endpoints on the run-browser paths.

**File browser UX**

The runs list (`/api/runs`) renders as a searchable card grid following the ArchiveLibrary pattern from community PR #6. Client-side search and filter (title, status, date) operate over the full `/api/runs` response — no server-side search endpoint needed. Each card shows a thumbnail (from `derivatives/contact_sheet.jpg` if present), run status badge, stage progress, and quick-action buttons (preview, download zip, open viewer). The card grid delegates to `/api/runs/<id>/tree` for per-run file browsing and to `/api/scenes/<id>/splat/<filename>` for in-browser 3DGS preview via `gaussian-splats-3d`. The 3D viewer (`viewer_splat.html`) embeds `@mkkellogg/gaussian-splats-3d` and Three.js from `src/web/static/vendor/` (no CDN; `sharedMemoryForWorkers:false` so no COOP/COEP headers are required on the Flask server).

## 5. Domain model — `Run` (read model for the browser)

```
Run{ id, created_at, kind: images|video, source: dropzone|gdrive,
     state, stages[], capture{decode manifest, image_count},
     artifacts{ colmap?, splat_ply?, ksplat?, ksplat_path?: string,
                objects[glb], scene_fbx?, previews[] },
     size_bytes, metrics{} }
```
Built by scanning `output/<id>/` + `capture.json` + job JSON. No new store — the filesystem *is* the store.

`ksplat_path` is the relative path (under `output/<id>/`) to the best available web-format splat, resolved in the same discovery order as the splat endpoint: `web/scene.ksplat` → `model/*.ply` → `*.splat`. Present only once at least one splat artifact exists; consumed by the `/api/scenes/<id>` detail response and the card-grid thumbnail logic.

**Client-side 3D viewer deps**: `@mkkellogg/gaussian-splats-3d` and `three` are bundled at `src/web/static/vendor/` — no CDN dependency. The viewer is initialised with `sharedMemoryForWorkers: false` so no `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` headers are required on the Flask server.

## 6. Migration / phasing (each phase independently shippable, tab6-rebuild + network-verify)

1. **P0 — Tidy & truth**: purge experiment litter (output/build scratch); land the audit blocker fixes (done); doc-truth pass + module header notes. *(no image change)*
2. **P1 — LichtFeld in-image**: `Dockerfile.appliance` stage 1+4 bakes v0.5.3; drop the `./build` bind-mount. Verify `/api/tools/lichtfeld/version`=0.5.3 over the net.
3. **P2 — Isolation**: three venvs + three users + supervisord v2 + secret containment. Verify `/api/health/processes`.
4. **P3 — Lockdown**: loopback-only publishes, ttyd token, VNC password; ship SSH-bridge instructions.
5. **P4 — Web UX**: drag-drop raw ingest; run browser + preview + zip; `/api/diskusage`.
6. **P5 — ArtiFixer wired** (own venv/user, off by default, coverage-gated) — pending research verdict.
7. **P6 (deferred, needs disk study)**: evaluate collapsing model/output volumes into the image.

## 7. Non-obvious risks
- Image size: baked venvs + LichtFeld libs are multi-GB; keep the 216 GB models a volume (do **not** bake). Multi-stage must discard vcpkg buildtrees (`rm -rf` in-stage).
- ArtiFixer torch pin may fight the pipeline's — the separate venv is precisely the mitigation; never `pip install` across venvs.
- Loopback publish + the agentbox on the docker net: the agent reaches services by service-DNS on the internal net (unchanged); only the *host* publish becomes 127.0.0.1.
- LichtFeld headless: still needs Xvfb (GUI libs linked); keep the Xvfb start in entrypoint.
