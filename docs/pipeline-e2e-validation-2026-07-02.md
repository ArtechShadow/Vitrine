# Pipeline E2E Validation — rawcapdev (2026-07-02)

Durable record of the first LichtFeld-native end-to-end run on real raw capture.
Dataset: `rawsForDev/` — 55 Pixel DNG stills of a gallery still-life (brass patina
vessel with an inverted Heinz ketchup bottle on top), shot handheld, indoor
available light.

---

## Stage results

| Stage | Result | Notes |
|---|---|---|
| **Decode** | 55 / 55 (rawpy) | `use_camera_wb=True` applied; see Bug 4 below |
| **Select** | 50 sharpest retained | Full-res Laplacian sharpness gate; 5 frames dropped |
| **COLMAP** | 50/50 registered, 10.4k sparse pts | 100% registration rate; ALIKED+LightGlue features |
| **LichtFeld igs+ training** | 4 M-gaussian splat, 30k iters | GPU-bound at ~99% util, ~15 min, avg 32.8 it/s; output `splat_30000.ply` (992 MB) |
| **Render previews** | 3 views + depth (gsplat, COLMAP poses) | Requires `cameras.bin` fix; see Bug 3 below |
| **SAM3 concept segmentation** | Runs; returns coarse bounding boxes | Not silhouettes — see open items |
| **extract\_objects** | Returns full scene (not per-object PLYs) | Downstream of SAM3 box-mask failure |
| **Object meshing (TRELLIS.2)** | Not started for this dataset | ComfyUI/TRELLIS.2 up; hero crop committed; gated on SAM3 mask quality |

**Neutral-WB retrain** (follow-up same day, commit `e4d0dd17`): with
`use_camera_wb=True` frames all 55 registered (COLMAP 55/55), 30k iters; heavy
orange cast is gone — walls render neutral white; residual floater haze is
capture-limited (handheld). Keeper renders under `docs/renders/rawcapdev-2026-07-02/neutral/`.

---

## Bugs fixed en route (4)

### Bug 1 — SplatReady config-name collision (commit `77c64b4c`)

`reconstruct()` previously called the bundled SplatReady plugin by default. The
plugin derives its status-file path by replacing `"_run_config.json"` in the
config filename, but our config was named `"splatready_config.json"` (no matching
substring), so the status path collided with the config file and the runner
clobbered its own config mid-run (`JSONDecodeError` on reuse). The runner also
exits 0 on failure, so the error was swallowed silently. Fixed: `reconstruct()`
now defaults to the transparent `_run_colmap_direct` path; SplatReady is opt-in
behind `config.reconstruct.use_splatready` (video fast-path) with the naming bug
fixed and stdout captured in the error message.

### Bug 2 — Missing `--max_image_size` on undistortion (commit `77c64b4c`)

`_run_colmap_direct()` called `image_undistorter` without `--max_image_size`, so
undistorted training images were full 36 MP. LichtFeld CPU-downscales anything
wider than its internal `--max-width` threshold on **every load** without disk
caching (~5 s/image). For 30k iterations this projected to hours at 0% GPU
utilisation. Fixed: `image_undistorter` now passes
`--max_image_size config.ingest.max_image_size` (default 2000 px); correctly-scaled
intrinsics are baked into `cameras.bin` at undistort time. Training is GPU-bound at
~99% (~15 min for 30k igs+ iters).

### Bug 3 — `cameras.bin` uint64 parse → SIGFPE in preview render (commit `b1fb6c4a`)

`stages.render_previews` read the COLMAP `cameras.bin` camera record with struct
format `'<iiii'` (four `int32`). The COLMAP binary format stores `width` and
`height` as `uint64`; the old format split the `width uint64` into `(w, h=high32=0)`.
A zero `render_h` caused a divide-by-zero (SIGFPE / core dump) in the gsplat
rasterizer. Fixed to `'<iiQQ'` (`uint32 camera_id`, `int32 model_id`, `uint64 w`,
`uint64 h`); preview render now succeeds from real COLMAP camera poses.

### Bug 4 — DNG white balance (commit `b1fb6c4a`)

`image_decoder._decode_rawpy` did not set `use_camera_wb`. libraw's default
daylight white balance left a heavy warm/orange cast on the indoor Pixel DNG frames;
this propagated into the splat and every downstream SAM crop and object texture.
Fixed: `use_camera_wb=True` in `_decode_rawpy`. The before/after is documented in
`docs/renders/rawcapdev-2026-07-02/01_wb_before_default.jpg` vs
`02_wb_after_camera.jpg`.

---

## Additional work committed this session

| Commit | Change |
|---|---|
| `309e8964` | LichtFeld Studio v0.5.3 baked into the `gaussian-toolkit` mega-image (ADR-022); `ldconfig` indexes the full build lib tree so the binary resolves all `.so` dependencies (`libusd_*`, `libOpenMeshCore`, `libnvimgcodec`) without a host bind-mount. |
| `d2ab4641` | Object recon (`_mesh_single`) now routes isolated per-object PLYs to TRELLIS.2 first (ADR-015 primary, gap #8) rather than orbit-TSDF; `Hunyuan3DConfig` and `Trellis2Config` default `comfyui_url` = `http://vitrine-comfyui:8188` (was dead `localhost:8189`/`3001`, gap #5). |
| `25c6ab78` | Dockerfile: `zipstream-ng` + `pynvml` added (web zip download + system stats); numpy/scipy reconciliation — SAM3 pins `numpy<2`, which left the image with numpy 1.26 + a modern scipy whose wheel references `np.long` (removed in numpy >= 1.24), causing `scipy.spatial` import crash in `select_frames` and `reconstruct`; fixed by upgrading scipy (pulls numpy >= 2) and adding `matplotlib` for `render_previews` depth colormaps after the SAM3 install step. |
| `25c6ab78` | Web: Flask service consolidated to loopback-only (`127.0.0.1`, ADR-023); four additive blueprints (`scenes_api`, `files_api`, `zip_api`, `splat_api`); vendored offline gaussian-splats-3d viewer; Vitrine-owned Vite+React frontend (`src/web/frontend/`). |

---

## Keeper renders

All under `docs/renders/rawcapdev-2026-07-02/` (committed, not gitignored):

| Path | What it shows |
|---|---|
| `01_wb_before_default.jpg` | Source DNG with libraw daylight WB — heavy orange cast |
| `02_wb_after_camera.jpg` | Same frame, `use_camera_wb=True` — neutral gallery walls |
| `03_splat_render_view00.jpg` | igs+ splat, gsplat render from COLMAP pose (front) |
| `03_splat_render_view18.jpg` | Splat render, oblique — window blinds, skirting, carpet, vessel |
| `03_splat_render_view36.jpg` | Splat render, top-down over the vessel |
| `04_splat_depth_view18.jpg` | Depth preview for view 18 |
| `neutral/neutral_splat_view{00,18,36}.jpg` | Neutral-WB retrain renders — orange cast resolved |
| `objects/hero_object_brass_vessel_ketchup.jpg` | Manual TRELLIS.2-ready crop of the hero still-life |
| `objects/sam3_segmentation_overlay.jpg` | SAM3 concept-segmentation output (coarse bounding boxes) |

---

## Open items

- **SAM3 box-mask output**: SAM3 concept segmentation currently returns coarse
  axis-aligned bounding boxes, not silhouette masks. `extract_objects` therefore
  falls back to the full scene. Per-object isolation (and onward TRELLIS.2 mesh
  generation) is blocked on SAM3 mask quality or a manual-crop workaround.
- **`.ksplat` production inert**: the `.ksplat` conversion step runs without error
  but the web viewer falls back to `.ply` (runtime issue, not tracked here).
- **Object meshing not started**: TRELLIS.2 and ComfyUI are up and the hero crop
  is committed; the image→3D call has not been executed for this dataset.
- **Rust onboarding wizard**: still binds `0.0.0.0`; loopback hardening is pending
  (tracked separately from the Flask fix above).
