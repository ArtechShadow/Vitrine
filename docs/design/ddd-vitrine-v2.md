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

Reuse today's Flask app + `viewer.html`; add:

- **Ingest**: `POST /api/ingest/upload` (chunked multipart, drag-dropped DNG/stills → `INPUT_DIR/<job>_images/` → existing `image_decoder.decode_directory` → `queue_job`). Primary pane = dropzone. Drive pull (`/ingest/url`) demoted to a collapsed "or pull a link".
- **Run browser**: `GET /api/runs` (list `output/*` + capture.json summary), `GET /api/runs/<id>/tree` (path-jailed file tree), `GET /api/runs/<id>/file?path=…` (range-served preview: images inline, text/log inline, `.ply/.ksplat` → `viewer.html`, `.glb/.obj` → model viewer).
- **Zip**: `GET /api/runs/<id>/zip?include=all|assets` → `zipstream` (streamed, never buffered); default excludes regenerable intermediates (COLMAP db, undistorted images, raw frames) unless `include=all`.
- **Inspection endpoints** (replace tab6 `docker exec`): `GET /api/diskusage` (per-mount + per-run + image-layer sizes), `GET /api/health/processes` (each service's user+venv+GPU), `GET /api/tools/lichtfeld/version`.
- Security: all `path=` params resolved and asserted to stay under `output/` (jail); no write endpoints on the browser.

## 5. Domain model — `Run` (read model for the browser)

```
Run{ id, created_at, kind: images|video, source: dropzone|gdrive,
     state, stages[], capture{decode manifest, image_count},
     artifacts{ colmap?, splat_ply?, ksplat?, objects[glb], scene_fbx?, previews[] },
     size_bytes, metrics{} }
```
Built by scanning `output/<id>/` + `capture.json` + job JSON. No new store — the filesystem *is* the store.

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
