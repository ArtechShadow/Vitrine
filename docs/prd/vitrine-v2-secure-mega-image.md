# PRD — Vitrine v2: Secure Single-Image Appliance + Raw-First Web UI

Status: **Draft for implementation** · Owner: Vitrine · Date: 2026-07-02
Companion docs: [ADR-022](../../research/decisions/adr-022-secure-single-image-architecture.md) · [DDD](../design/ddd-vitrine-v2.md)

## 1. Problem & motivation

Vitrine today is a multi-container stack (`gaussian-toolkit` + `vitrine-comfyui` +
`milo`/`come` + `unreal` overlay) that binds source code and a host-compiled
LichtFeld binary from the host filesystem, publishes ~8 unauthenticated services
on `0.0.0.0`, and is driven partly through an error-prone host shell (tmux
"tab 6"). This is hard to hand to IT for sign-off, fragile (the LichtFeld binary
went missing when its host bind-mount source was deleted — see the master audit),
and awkward for a non-expert curator to operate.

**Goal:** a **single, self-contained, IT-signable Docker appliance** that a
curator drives **entirely through a hardened web UI reached over an SSH bridge** —
drop raw photos in, watch the pipeline run, browse/preview/zip the outputs — with
no host bind-mounts of code or binaries and no unauthenticated LAN surface.

## 2. Users & top jobs-to-be-done

| User | Job |
|---|---|
| Curator / operator | Drop a folder of **raw (DNG) stills** → get a textured UE-ready scene; browse and download the results. No terminal, no Docker knowledge. |
| Researcher | Inspect any run's intermediate artifacts (COLMAP, splat PLY, object GLBs, logs); re-run stages; optionally invoke ArtiFixer. |
| IT / security | Approve one image with a documented, minimal, authenticated attack surface; audit what it exposes and what it can reach. |
| Maintainer | Update one component (ArtiFixer weights, LichtFeld tag, a pipeline module) without dependency conflicts breaking the others. |

## 3. Requirements

### R1 — Single self-contained image (must)
- One `docker build` produces one runnable image; `docker run` (or one short compose) brings up the whole pipeline. LichtFeld-Studio v0.5.3 is **built into the image** (multi-stage), not bind-mounted. Pipeline + web code is **baked in**, not mounted.
- **Data stays external** as named volumes (the ~216 GB model tree and `output/` cannot be baked) — this is the *only* sanctioned external state. Removal of all bind-mounts (incl. code/build) is achieved; further collapsing model/output into the image is **explicitly deferred** pending the R8 disk study.

### R2 — Internal separation of concerns (must)
- Three isolated Python environments so heavy/conflicting deps never collide: `pipeline` (Vitrine + web), `artifixer` (Wan2.1 diffusion stack), `comfyui`. Shared native tools (CUDA, COLMAP, LichtFeld) live once, on PATH.
- **Least-privilege users**: `vitrine` (web/orchestrator/terminal), `comfyui`, `artifixer`. Secrets (HF token, Anthropic key, Claude OAuth) are readable **only by `vitrine`**. ArtiFixer runs as `artifixer` with no secret access. Supervisord (root, PID 1) launches each program under its user+venv.

### R3 — Hardened, loopback-only exposure (must)
- The container publishes **no `0.0.0.0` ports**. All UIs bind to the host's `127.0.0.1` only (or are reachable solely on the internal docker network for the agent).
- Access is via an **SSH `LocalForward` bridge**; the PRD ships copy-paste instructions (§6). VNC gets a password or is dropped. ComfyUI/MCP/UE-RC are not directly reachable from the LAN.
- Acceptance: from another LAN host, `curl http://<rig-ip>:7860` **fails**; `ssh -L 7860:localhost:7860 user@rig` then `curl localhost:7860` **succeeds**.

### R4 — Raw-first ingest (must)
- **Primary pane: drag-and-drop** of a folder / multiple **raw (DNG) + still** files directly in the browser (chunked upload). This is the preferred capture path (sharper than video frames).
- **Secondary (retained, de-emphasised): Google Drive URL pull** (the current gdown path) — collapsed under "or pull from a link", flagged best-effort (anonymous rate-limits).
- Decode (DNG/HEIC/WebP → COLMAP-native) and the existing image→pipeline handoff are reused; the stills-ingest case-sensitivity blocker (fixed 2026-07-02) is a prerequisite.

### R5 — Integrated run browser + preview (must)
- A **runs list** (each `output/<run>`), a **file tree** per run, and a **preview pane**: images (thumbnails + lightbox), splats (`.ply`/`.ksplat` in-browser 3D viewer — see below), meshes (`.glb`/`.obj`), text/logs, `capture.json`, metrics. Read-only, path-jailed to `output/`.
- **Splat viewer:** `.ply`/`.ksplat` files are rendered in-browser via [`@mkkellogg/gaussian-splats-3d`](https://github.com/mkkellogg/GaussianSplats3D), bundled into `static/vendor/` (ships in-image, no CDN dependency). The library is fed via `GET /api/scenes/<id>/splat/<filename>` (Range- and ETag-supported; discovery order: `output/<id>/web/scene.ksplat` → `model/*.ply` → `*.splat`). The generic per-run file path `GET /api/runs/<id>/file?path=` also resolves splat assets for the file-browser preview pane. See ADR-023.

### R6 — Per-run asset zip download (must)
- One click downloads **all assets for a run as a `.zip`** (streamed, so a multi-GB run doesn't buffer in RAM), with a sane manifest and exclusion of huge regenerable intermediates by default (toggle to include).
- **Endpoint:** `GET /api/runs/<id>/zip?include=all|assets` — `assets` (default) excludes COLMAP databases, undistorted frame dumps, and raw frame caches; `all` includes the full run tree. Streamed via **zipstream-ng** (constant memory, no buffering). The legacy `GET /download/<job_id>` route is kept unchanged for the existing Jinja UI. See ADR-023.

### R7 — Operate via web + tab6-rebuild-only workflow (must)
- All routine operation (ingest, monitor, browse, download, disk usage, health) is in the web UI, reachable **over the docker network / SSH bridge**. The host shell (tab 6) is used **only to rebuild** the image. Inspection never requires `docker exec`.

### R8 — Disk-usage visibility (must) → informs bind-mount deprecation (deferred)
- A **`/api/diskusage`** endpoint (network-inspectable) reports per-mount and per-run sizes and image-layer footprint, so we can decide *later* whether model/output can move into the image. **Do not remove the model/output volumes until this study is done.**

### R9 — Maintainability (should)
- Component upgrades (LichtFeld tag, ArtiFixer, a venv's deps) are localized to one build stage / one venv. Pins are honoured (no floating HEAD). CI (the new `vitrine-ci.yml`) gates code changes.

## 4. Non-goals / out of scope (this iteration)
- Baking the 216 GB model tree or `output/` into the image (deferred to R8 study).
- Multi-tenant auth / user accounts in the web UI (SSH bridge is the auth boundary).
- Removing the `milo`/`come`/`unreal` sidecars (they can remain optional overlays; the mega image is the *core* appliance). ArtiFixer is **in-image** (own venv/user) since we can prove it runs.
- Actioning full bind-mount removal beyond code/build (noted, not done).

## 5. ArtiFixer decision (research complete, 2026-07-02)

Verdict (paper numbers + code + LichtFeld v0.5.3 source; see [memory/research note]):
- **Low-noise / floaters is a LichtFeld-native job, not ArtiFixer.** v0.5.3 has *no*
  diffusion refinement, but its training does: igs+ (`prune_opacity 0.005`,
  `prune_scale`), MCMC densification, MRNF (SSIM+edge error-map refine), depth-loss,
  bilateral grid, a sparsity optimizer (**`prune_ratio 0.6`**) and post-hoc
  **`SplatSimplify` (`opacity_prune_threshold 0.1`)**. Together these produce a much
  lower-floater splat than the gsplat fallback — **repairing LichtFeld is the noise fix.**
- **ArtiFixer's only *unique* capability is generative fill of under-observed regions.**
  It is opacity-gated: dense/well-covered captures → no-op (upstream issue #10). Raw-still
  ingest makes its rare win *sharper* (hole-fill is cross-attended on the sharp captured
  references, not blurry video frames) but also *rarer* (a deliberate stills shoot leaves
  fewer holes). Best-case ~20 dB PSNR / big FID drops **only on sparse-but-sharp/holey**
  benchmarks; never a deblurrer; `ds4` (validated 48 GB config) softens output at ¼ res.

**Decision:** ArtiFixer ships **wired-but-opt-in, off by default**, own venv+user, gated
behind a coverage/hole detector so it runs only on genuinely holey raw captures. Default
noise path = LichtFeld-native (igs+ + `--use-depth-loss` + `simplify_splats`). Rare
observed-region cleanup → **Difix3D+** (single-step, tiny vs 14 B ArtiFixer) before the
opacity-attenuation hack. Cheapest validation: one *holey raw* scene, A/B LichtFeld-native
vs ArtiFixer3D on the identical hole regions.

## 6. SSH bridge — operator instructions (ships in-app + README)
```
# One tunnel exposes the web UI locally without opening any LAN port:
ssh -N -L 7860:localhost:7860 <user>@<rig-host>
# then open http://localhost:7860 in your browser.
# (The rig publishes 7860 only on its own 127.0.0.1; nothing is on the LAN.)
```
The file browser, per-run zip download, and 3D splat viewer are all reachable through this single tunnel.

## 7. Acceptance criteria (verifiable over the docker network / SSH bridge)
1. `docker build` → single image; `up` → `curl http://gaussian-toolkit:7860/health` ok on the docker net; LAN `curl` to the rig IP fails.
2. LichtFeld: `GET /api/tools/lichtfeld/version` returns `0.5.3` (binary in-image, no bind-mount).
3. Drop 40 DNGs in the browser → run completes → run browser shows COLMAP + splat + previews.
4. `GET /api/runs/<id>/zip` streams a valid archive of the run.
5. `GET /api/diskusage` returns per-mount + per-run sizes.
6. `ps`-equivalent (via a `/api/health/processes` endpoint): web as `vitrine`, comfyui as `comfyui`, artifixer as `artifixer`; each on its own venv.
7. Rebuild is the only step performed on tab 6.
