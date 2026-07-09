# Video-to-Scene Pipeline -- Claude Code Orchestration

**Vitrine** is a standalone capture-adaptive video → structured-3D-scene → Unreal Engine 5.8 game-asset pipeline. LichtFeld Studio is a **vendored tool** (pinned at `vendor/lichtfeld-studio` @ v0.5.3) that Vitrine calls for native 3DGS training/rendering. Never modify the vendored tool; update it only by bumping the submodule to a new tag.

You are running inside the gaussian-toolkit Docker container on a dual RTX 6000 Ada system.
**You are the orchestrator.** There is no state machine. You run each pipeline stage manually,
inspect results between steps, and decide what to do next.

**CRITICAL: You MUST complete ALL stages through to the textured UE scene and validation.
Do NOT stop after training. The full pipeline is:
decode/ingest -> select_frames -> reconstruct -> train -> render_previews -> segment -> extract_objects -> mesh_objects
  -> mesh_env -> clean_mesh(smooth=0) -> bake_textures(xatlas) -> export_fbx -> ue_import -> validate**

For **still-image captures** (DNG/HEIC/JPEG folders) the first stage is `decode`
(`image_decoder.decode_directory`), not `ingest` (which is video-only ffmpeg extraction).
Both converge at `select_frames`.

> **End-state = textured polygonal scene in UE 5.8 (game assets), NOT USD.** USD assembly is
> demoted to an OPTIONAL/archival side-step — UE cannot import LichtFeld's native USD
> `ParticleField`, and UE drops vertex colours (so colour MUST be baked to a UV texture before
> the FBX import). See `docs/ANTIPATTERNS.md`, `research/decisions/adr-019-*`, and the
> `docs/engineering-log.md` 2026-06-22 entry. Objects use Hunyuan3D-2.1 with **restart-ComfyUI-per-object**.

## Standing Directives (READ FIRST — apply to every job and every change)

These supersede convenience shortcuts elsewhere in this file.

### Internal-Claude enablement (ADR-024)

The in-container Claude intelligence — this terminal, and the pipeline's
auto-launch of Claude Code — runs **only** when `VITRINE_CLAUDE_ENABLED=1`.
With it unset, the web panel on `:7860` is the only operator I/O; there is no
in-container Claude orchestration to fall back on.

1. **Vitrine is the product; LichtFeld is a vendored tool.** For 3DGS training,
   pose-opt, densification, scene export, and rendering, call the vendored
   LichtFeld tool via its MCP surface (`AGENTS.md`; bridge at
   `http://localhost:45677/mcp`) rather than reimplementing those capabilities in
   `src/pipeline`. Fall back to custom Python only when the vendored tool lacks a
   required feature (e.g. per-object USD hierarchy + `v2g:*` metadata).
   **Never modify files inside `vendor/lichtfeld-studio/`.** Update the tool by
   bumping the submodule pin to a new tag.
2. **Always run clean SOTA.** Use the newest stable models/tools, never a stale
   default. SOTA weights are **pre-staged** in the single **unified models tree**
   `data/comfyui/models/` (ComfyUI's native store, ~216 GB), bind-mounted into
   this container at `/models-staging` and as ComfyUI's native `/comfyui/models`.
   **Prefer the staged weights** and don't redundantly re-download what is already
   present — but this is a preference, **not a prohibition**. If a model you need
   is **not staged** — a fresh setup without the pre-staged tree, or a new
   checkpoint you have version-checked — **download it from HuggingFace** (use
   `HF_TOKEN` for gated repos) into the models tree / HF cache, then pin the exact
   revision. If `/models-staging` is empty, check the bind mount /
   `MODELS_STAGING_DIR` first; when there is no staged copy to point at,
   downloading the missing weights is the correct action, not an error.
3. **Always version-check before use, then pin.** For every model/tool, verify
   the current latest (MCP catalog, ComfyUI `/object_info`, HF, upstream repo),
   update if behind, then pin the exact tag/commit/checkpoint. No HEAD clones,
   no floating `latest`.

**Mesh backend = CoMe (project pivot, 2026-06-04).** The config default is now
`come` (~3x faster than MILo at comparable F1). To honour the pivot the image
MUST be built with `INSTALL_COME=1`, the `come` sidecar MUST be running, and you
MUST **verify `come_extractor.py`'s CLI flags against the released CoMe repo**
(they were inferred). Otherwise every run silently degrades to the TSDF fallback.
(master-audit #17 confirms `mesh_method='come'` silently degrades to TSDF when
the come sidecar/flags aren't validated — verify before relying on CoMe output.)

## SOTA Modernization Mandate (research → implement → validate → pin → report)

You own these upgrades. Work one item at a time on a real test job; gate each
behind a capability probe so an upgrade never hard-breaks a run. Canonical
detail + traceability: `research/decisions/work-order-sota-modernisation.md`
(ADR-012 SOTA tooling + the v3 closure PRD).

| # | Upgrade | Current (file:line) | Target | Notes |
|---|---------|---------------------|--------|-------|
| 1 | Inpaint model | `comfyui_inpainter.py:88` flux1-fill-dev | **FLUX.2-dev** | staged `flux2_dev_fp8mixed.safetensors` (+ `flux2-vae`, `mistral_3_small_flux2_fp8`, Turbo LoRAs); add `workflows/flux2_inpaint.json`; probe→fallback FLUX.1-Fill |
| 2 | Image-to-3D hull | `hunyuan3d_client.py:61,77` Hunyuan3D-2.0 | **Hunyuan3D-2.1** | local `comfy/ldm/hunyuan3dv2_1` + `comfyui-sam3dobjects`; probe→fallback 2.0 |
| 3 | SAM3D fallback | `sam3d_client.py` orphaned (unimported) | **wire as Hunyuan fallback** | `config.hunyuan3d.fallback_sam3d` already True; node + weights present |
| 4 | COLMAP features | SIFT + exhaustive matcher | **ALIKED+LightGlue** | prefer the LichtFeld COLMAP plugin if present; SIFT fallback |
| 5 | USD assembly | subprocess `scripts/assemble_usd_scene.py` | **native LichtFeld USD export** (MCP `scene.export`) | keep custom path only if native lacks per-object hierarchy + `v2g:*` metadata |
| 6 | Plugins | `splat_ready` referenced (`stages.py`) but not installed | **install + enable** splat_ready, PPISP, bilateral-grid, 3DGUT, pose-opt, ImprovedGS+ | wire native flags in `train` |
| 7 | Version pins | Dockerfiles clone ComfyUI/Hunyuan/COLMAP/MILo/CoMe/GW/SAM3/gsplat at HEAD | **pin all** to tag/commit | write a lock manifest |
| 8 | Endpoints | hardcoded `localhost:8189/:3001` (~11 sites) + in-container :8188 | **single source via config/manifest** | reconcile Salad(:3001) vs local ComfyUI(:8188) |

For each item: (a) RESEARCH the current latest + whether LichtFeld-native/plugin
already covers it; (b) IMPLEMENT against the staged weights / local ComfyUI,
behind a capability probe; (c) VALIDATE on a test job against the Quality
Targets below; (d) PIN the exact version; (e) REPORT via the REST API.

## Available Tools

- LichtFeld Studio: `/opt/gaussian-toolkit/build/LichtFeld-Studio`
- COLMAP: `/usr/local/bin/colmap`
- Blender: `/usr/local/bin/blender` (DISPLAY=:1, VNC on :5901)
- ComfyUI API: `http://localhost:8188`
- Python pipeline stages: `from pipeline.stages import PipelineStages`
- Web API: `http://localhost:7860`

## When a job arrives

Check for new jobs:

```bash
curl -s http://localhost:7860/jobs | python3 -m json.tool
```

For each queued job, run the pipeline stage by stage.

---

## Step 1: Decode / Ingest

### 1a: Still-image captures (DNG / HEIC / JPEG folders) — **rawcapdev-validated path**

Camera-raw (DNG/ARW/CR2) and HEIC files must be decoded before COLMAP or
frame-QA can read them. `image_decoder._decode_rawpy` uses `use_camera_wb=True`
so the camera's as-shot white balance is honoured — without it, libraw falls back
to daylight WB and indoor DNGs carry a heavy orange cast that propagates into the
splat and every SAM crop.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.image_decoder import decode_directory
manifest = decode_directory('/data/input/JOB_ID', '/data/output/JOB_ID/frames')
print(manifest)
"
```

Alternatively, invoke the module directly:

```bash
docker exec gaussian-toolkit python3 -m pipeline.image_decoder \
    /data/input/JOB_ID /data/output/JOB_ID/frames
```

**Inspect**: verify `manifest['decoded']` matches the source file count; check
`manifest['failures']` is empty.

### 1b: Video captures — ffmpeg frame extraction

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.ingest('/data/output/JOB_ID/input.mp4', fps=4.0)
print(result)
"
```

Update the web UI:
```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "ingest", "progress": 0.05, "message": "Extracting frames at 4fps"}'
```

**Inspect**: `ls /data/output/JOB_ID/frames/ | wc -l`

---

## Step 2: Remove people (if needed)

Look at the frames. If people are visible:

```bash
python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.remove_people('/data/output/JOB_ID/frames/')
print(result)
"
```

If no people, skip to step 3 using the frames directory directly.

---

## Step 3: Select best frames (IMPORTANT for COLMAP registration)

Select 60-80 diverse, high-quality frames from the oversampled set.
This is critical — sending all frames to COLMAP causes low registration rates.
The selector scores sharpness at full resolution via the Laplacian variance (downscaled
blurdetect scores have ~105× less range and can select blurry frames), keeps the
sharpest frame per time window (FIFO), and gates on MUSIQ NR-IQA.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.select_frames('/data/output/JOB_ID/frames/', target=80)
print(result)
"
```

**Check**: The selected frame count should be 60-80. If less than 40, re-run with lower blur_threshold.

```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "select_frames", "progress": 0.1, "message": "Selected N frames from M extracted"}'
```

---

## Step 4: COLMAP reconstruction

`reconstruct()` defaults to the **direct COLMAP path** (feature extraction →
matcher → mapper → `image_undistorter`). The bundled SplatReady plugin is
bypassed by default: it had a config-name collision that silently clobbered its
own config and exited 0 on failure. Set `config.reconstruct.use_splatready=True`
only for the video fast-path where you have explicitly confirmed the plugin works.

`image_undistorter` is called with `--max_image_size 2000`
(`config.ingest.max_image_size`). Without this cap, full-resolution DNGs undistort
to ~36 MP and LichtFeld CPU-downscales every image on each load (~5 s/img,
uncached), which starves the GPU. With the cap, igs+ 30 k iterations train
GPU-bound at ~99% utilisation (~15 min on an RTX 6000 Ada).

Use the **sequential** matcher for video input; for unordered stills use `exhaustive`.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.reconstruct('/data/output/JOB_ID/frames_selected/')
print(result)
"
```

**Check**: Look for `sparse/0/cameras.bin` and `images/` in the colmap dir.
**CRITICAL**: Check the registration rate. At least 70% of input frames should register.
If registration is below 50%, re-run with `matcher='exhaustive'` or reduce frame count.

```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "reconstruct", "progress": 0.25, "message": "COLMAP: N/M frames registered"}'
```

---

## Step 5: Train gaussian splatting

`train()` calls the LichtFeld binary with `--log-level info` but uses
`subprocess.run(capture_output=True)`, so all output is buffered until the
process exits (~15 min for 30 k iters). **You cannot watch per-iteration loss via
`train()`.** If you need live progress, run the binary directly and tee to a log:

```bash
# Watch training progress in real time (run in a separate shell or background)
docker exec gaussian-toolkit bash -c '
    /opt/gaussian-toolkit/build/LichtFeld-Studio --headless \
        --data-path /data/output/JOB_ID/colmap/undistorted \
        --output-path /data/output/JOB_ID/model \
        --iter 30000 \
        --strategy igs+ \
        --sh-degree 3 \
        --log-level info \
    2>&1 | tee /data/output/JOB_ID/train.log
'

# Poll for the binary while it runs (name is >15 chars — use -f, not -x)
pgrep -f LichtFeld-Studio
```

For the standard orchestrated path (fires and returns on completion):

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.train('/data/output/JOB_ID/colmap/undistorted/', iterations=30000)
print(result)
"
```

Update progress during training:
```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "train", "progress": 0.5, "message": "30k iter, loss 0.02"}'
```

**Quality check**: The PLY should be > 10 MB for a good scene.
If training fails or quality is poor, adjust `iterations` or try `strategy="mcmc"`.

**DO NOT STOP HERE. Continue to render_previews, then segmentation.**

---

## Step 5a: Render preview images from the splat

`render_previews` orbits gsplat cameras around the trained PLY and saves PNG
depth + colour previews to `output/JOB_ID/previews/`. The web carousel discovers
them automatically.

**Important:** `cameras.bin` stores width/height as `uint64`, not `int32`. The
correct struct format is `'<iiQQ'` (camera_id int32, model_id int32, width uint64,
height uint64). The old `'<iiii'` format would read `render_h=0` → SIGFPE in the
rasterizer tile grid; this is fixed in commit b1fb6c4a.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.render_previews(
    '/data/output/JOB_ID/model/splat_30000.ply',
    '/data/output/JOB_ID/colmap/undistorted',
    num_views=8,
)
print(result)
"
```

**Inspect**: open a preview PNG to verify the splat has no obvious colour cast or
missing regions before continuing to segmentation.

---

## Step 5b: MILo Training (preferred -- produces mesh directly)

If MILo conda environment is available, use it instead of LichtFeld + TSDF:

```bash
# Check if MILo is installed
conda run -n milo python -c "import torch; print('MILo OK')" 2>/dev/null

# If available, run MILo training + mesh extraction
python3 -c "
import sys; sys.path.insert(0, 'src')
from pipeline.milo_extractor import run_milo, is_milo_available, MiloConfig
if is_milo_available():
    result = run_milo(
        colmap_dir='/data/output/JOB_ID/colmap/undistorted',
        output_dir='/data/output/JOB_ID/model_milo',
        config=MiloConfig(imp_metric='indoor', mesh_config='default'),
    )
    print(result)
    if result['success']:
        print(f'MILo mesh: {result[\"mesh_path\"]}')
        # Skip to Step 9 (Blender assembly) -- no separate TSDF needed
else:
    print('MILo not available, using LichtFeld + TSDF pipeline')
"
```

MILo trains for 18K iterations with mesh-in-the-loop regularization.
The output mesh is via learned SDF extraction -- much higher quality than TSDF.
If MILo produced a mesh, **skip Steps 6-8** and go directly to Step 9 (Blender assembly).

Quality targets for MILo:
- Mesh should have 50K-500K vertices depending on mesh_config
- Vertex colors from gaussian splatting
- Clean surface topology (no TSDF lumpiness)

---

## Step 6: SAM3 Object Identification

SAM3 identifies freestanding objects using text prompts. HF_TOKEN is set for
model download. First run downloads ~2.4 GB checkpoint (cached in /opt/hf-cache
afterward).

**Known issue (as of rawcapdev 2026-07-02):** SAM3 currently returns coarse
axis-aligned bounding boxes rather than per-object silhouette masks.
`extract_objects` therefore returns the full-scene gaussian rather than isolated
per-object sub-clouds. The working object path is a **clean SAM image crop →
TRELLIS.2 image-to-3D** (ComfyUI on `vitrine-comfyui:8188`); see Step 7d.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.segment(
    '/data/output/JOB_ID/model/splat_30000.ply',
    '/data/output/JOB_ID/frames_selected/'
)
print(result)
"
```

**INSPECT THE RESULTS.** Check: how many objects? What labels? Gaussian counts
per object? If SAM3 fell back to full_scene only, check HF_TOKEN, model download,
and that `SAM3_BPE_PATH=/opt/sam3-repo/sam3/assets/bpe_simple_vocab_16e6.txt.gz`
is set in the container environment.

```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "segment", "progress": 0.55, "message": "SAM3: N objects identified"}'
```

---

## Step 7: Per-Object Processing Loop

**For EACH identified object, run this sub-pipeline. You are iterating.**

### 7a: Extract per-object gaussian PLY

Due to the SAM3 bounding-box limitation (Step 6), this currently returns the
full-scene gaussian for each label. It is still worth running to produce the
per-object directory structure and metadata used by later steps.

```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.extract_objects('/data/output/JOB_ID/model/splat_30000.ply', OBJECTS_FROM_STEP6)
print(result)
"
```

### 7b: Render object views with gsplat (orbit cameras -- correct for isolated objects)
```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from pipeline.mesh_extractor import load_3dgs_ply, render_gsplat, generate_orbit_cameras_gsplat
import numpy as np
from PIL import Image

gs = load_3dgs_ply('/data/output/JOB_ID/objects/OBJECT_LABEL.ply')
cameras = generate_orbit_cameras_gsplat(gs['means'], 4, 1024)
for i, (vm, K) in enumerate(cameras):
    depth, rgb, alpha = render_gsplat(gs, vm, K, 1024, 1024)
    Image.fromarray((np.clip(rgb,0,1)*255).astype(np.uint8)).save(
        f'/data/output/JOB_ID/objects/OBJECT_LABEL_view{i}.png')
print('Saved 4 orbit views')
"
```

### 7c: (Optional) Hunyuan Multi-View enhancement via ComfyUI
Submit the best render to ComfyUI Hunyuan MV workflow for consistent multi-view generation:
```bash
curl -s http://localhost:8188/prompt -X POST \
  -H 'Content-Type: application/json' \
  -d @/data/output/JOB_ID/workflows/hunyuan_mv_OBJECT.json
```

### 7d: Create mesh per object — TRELLIS.2 primary path

`mesh_objects()` routes each per-object PLY to **TRELLIS.2** first (ADR-015,
commit d2ab4641). TRELLIS.2 runs in the `vitrine-comfyui` container
(`http://vitrine-comfyui:8188`). Hunyuan3D-2.1 is the automatic fallback if
TRELLIS.2 fails or is unconfigured. Both routes require the ComfyUI sidecar to
be running and reachable on the `v2g-net` / `visionclaw_network` before calling
this stage.

Verify the sidecar is up before proceeding:
```bash
curl -s http://vitrine-comfyui:8188/system_stats | python3 -m json.tool
```

Then run mesh extraction:
```bash
docker exec gaussian-toolkit python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.mesh_objects(['/data/output/JOB_ID/objects/OBJECT_LABEL.ply'])
print(result)
"
```

The validated object path for the rawcapdev run was a **clean SAM image crop
(not an orbit render)** fed into TRELLIS.2 image→3D. Use the best-lit frame
crop of the isolated object as the input image; TRELLIS.2 generates the
multi-view turnaround sheet and textured GLB internally.

### 7e: Save object metadata (position, bbox, label, mesh path)
```bash
python3 -c "
import json, numpy as np
from plyfile import PlyData
ply = PlyData.read('/data/output/JOB_ID/objects/OBJECT_LABEL.ply')
v = ply['vertex']
meta = {
    'label': 'OBJECT_LABEL',
    'position': [float(np.mean(v['x'])), float(np.mean(v['y'])), float(np.mean(v['z']))],
    'bbox_min': [float(np.min(v['x'])), float(np.min(v['y'])), float(np.min(v['z']))],
    'bbox_max': [float(np.max(v['x'])), float(np.max(v['y'])), float(np.max(v['z']))],
    'gaussian_count': len(v),
    'mesh': '/data/output/JOB_ID/objects/meshes/OBJECT_LABEL/OBJECT_LABEL.glb',
}
json.dump(meta, open('/data/output/JOB_ID/objects/OBJECT_LABEL_meta.json', 'w'), indent=2)
print(json.dumps(meta, indent=2))
"
```

Report per-object progress:
```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "mesh_objects", "progress": 0.7, "message": "Object N/M: LABEL"}'
```

---

## Step 8: Build Empty Room

Remove identified objects from frames using inpainting, reconstruct clean room.

### 8a: Inpaint objects out of frames
Use SAM3 object masks + ComfyUI FLUX inpainting to remove objects from frames.
The inpainted frames go to `frames_inpainted/`.

### 8b: Reconstruct empty room
Re-run COLMAP + 3DGS training on inpainted frames. Reuse camera poses from step 4.

### 8c: Extract room mesh
Room mesh uses **COLMAP cameras** (interior scene), not orbit cameras.

---

## Step 9: Assemble Scene in Blender

The Blender assembler combines room mesh + object meshes at their original positions.
It bakes vertex colors to UV textures in 0.5s using Cycles GPU.

```bash
blender --background --python src/pipeline/blender_assembler.py -- \
    --input /data/output/JOB_ID/objects/meshes/full_scene/full_scene.glb \
    --output-usd /data/output/JOB_ID/usd/scene.usda \
    --output-renders /data/output/JOB_ID/previews/ \
    --render-size 1920x1080
```

For multi-object scenes, write a custom Blender script to import each object at position:
```python
import bpy, json
from pathlib import Path
JOB = '/data/output/JOB_ID'
for meta_file in sorted(Path(f'{JOB}/objects').glob('*_meta.json')):
    meta = json.load(open(meta_file))
    bpy.ops.import_scene.gltf(filepath=meta['mesh'])
    obj = bpy.context.selected_objects[0]
    obj.location = meta['position']
    obj.name = meta['label']
```

```bash
curl -X POST http://localhost:7860/api/job/JOB_ID/stage \
  -H 'Content-Type: application/json' \
  -d '{"stage": "assemble_usd", "progress": 0.95, "message": "Scene: room + N objects"}'
```

---

## Step 10: Validate and Complete

```bash
python3 -c "
from pipeline.stages import PipelineStages
p = PipelineStages('/data/output/JOB_ID')
result = p.validate()
print(result)
"
curl -X POST http://localhost:7860/api/job/JOB_ID/complete \
  -H 'Content-Type: application/json' \
  -d '{"success": true}'
```

---

## Orchestration Rules

### YOU ARE THE ORCHESTRATOR. Not a script runner.

1. **Inspect results between every step.** Check vertex counts, image quality, file sizes.
2. **If SAM3 finds objects**: Run the per-object loop (7a-7e) for EACH object.
3. **If SAM3 falls back to full_scene only**: Mesh the full scene, skip object loop.
4. **If quality is poor**: Re-run the stage with different parameters.
5. **Orbit cameras for isolated objects**, COLMAP cameras for full scenes/rooms.
6. **Save preview images at every stage** for the web carousel.
7. **Report progress via REST API** at each stage transition.
8. **Blender assembler bakes textures in 0.5s** via Cycles GPU -- always use it for final output.

### Quality Targets

| Stage | Target | Fail if |
|-------|--------|---------|
| COLMAP | >70% registration | <30% |
| Training | >10MB PLY, loss <0.02 | <1MB PLY |
| SAM3 | 2+ objects identified | (fallback to full_scene is OK) |
| Per-object mesh | >5K verts per object | <500 verts |
| Room mesh | >30K verts | <5K verts |
| MILo mesh | 50K-500K verts, vertex colors, clean topology | <10K verts or no mesh produced |
| Final USD | Room + objects with materials | Empty scene |

### Known issues (as of 2026-07-02)

| Area | Issue | Status |
|------|-------|--------|
| SAM3 masks | Returns coarse bounding boxes, not per-object silhouettes; `extract_objects` therefore returns the full scene | Open; working path is SAM image crop → TRELLIS.2 |
| .ksplat production | `make_web_ksplat()` requires Node / npx at runtime; when absent the web viewer falls back to progressive-loading the trained `.ply` directly | Open; Node not pre-installed in the image |
| Rust onboarding wizard | `vitrine-onboarding` (:8088) still binds `0.0.0.0` (not loopback-restricted) | **Resolved** — now defaults to `127.0.0.1:8088` (ADR-024) |

### Process management

The LichtFeld binary name is **`LichtFeld-Studio`** — 16 characters, which exceeds
the 15-character limit of `pgrep -x`. Always use `pgrep -f` when polling for it:

```bash
pgrep -f LichtFeld-Studio          # correct
pgrep -x LichtFeld-Studio          # WRONG — never matches, silently returns nothing
```

### Key Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `SAM3_BPE_PATH` | `/opt/sam3-repo/sam3/assets/bpe_simple_vocab_16e6.txt.gz` | SAM3 text tokenizer |
| `HF_TOKEN` | (from .env) | HuggingFace model downloads |
| `HF_HOME` | `/opt/hf-cache` | Shared HF cache directory |

### REST API

The web UI at :7860 now includes a file browser, per-run zip download, and 3D splat viewer (PR #6 UX consolidation, ADR-023); it binds 127.0.0.1 by default — set LFS_WEB_HOST only for container-bus access.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/job/<id>/stage` | Report stage progress |
| POST | `/api/job/<id>/stage/complete` | Mark stage done |
| POST | `/api/job/<id>/complete` | Mark job done |
| GET | `/status/<id>` | Job detail |
| GET | `/api/job/<id>/previews` | List preview images |
| GET | `/api/runs` | Richer run list synthesized from job_manager + on-disk outputs (thumbnail via derivatives URL) |
| GET | `/api/runs/<id>/tree` | Recursive file tree for output/<id>/; dotfiles + .secrets excluded; [{path,size,kind}] |
| GET | `/api/runs/<id>/zip` | Streamed zip (zipstream-ng, constant memory); default excludes colmap db/raw frames; `?include=all` for full tree |
| GET | `/api/runs/<id>/file?path=` | Range-served file preview path-jailed to output/<id>/; images/text inline, .glb→mesh viewer, .ply/.ksplat→splat viewer |
| GET | `/api/scenes/*` | SPA alias facade (scene_id == job_id 1:1): list scenes, get scene detail, progress polling, frames list, derivatives, delete, export; SSE /stream/<id> remains canonical progress channel |
| GET | `/api/scenes/<id>/splat/<filename>` | Range/ETag-served .ksplat/.ply for gaussian-splats-3d viewer; discovery order: output/<id>/web/scene.ksplat → model/*.ply → *.splat; traversal-guarded |
| GET | `/api/system/stats` | System stats via pynvml/psutil best-effort; returns zeros + gpu_available:false when unavailable |
| POST | `/api/scenes/upload-images` | Batch stills (jpg/png/DNG/HEIC) multipart → image_decoder.decode_directory → enqueue; 2 GB cap, secure_filename, ext allow-list |
| POST | `/api/scenes/upload-zip` | Zip capture bundle multipart; extracted with zip-slip guard + decompressed-size cap into new job input dir |
| POST | `/api/import/google-drive` | Drive URL ingest via existing gdown logic (images-preferred); returns {scene_id, state:'downloading'}; no new secret surface |

### MANDATORY: Save preview images

The web UI carousel auto-detects PNG/JPG in the job output directory.
Save previews at: frame selection, training renders, depth maps, mesh renders, final scene.
