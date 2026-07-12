# Workflow: Video to Structured 3D Scene

## One-Command Pipeline

```bash
video2splat /path/to/drone_footage.mp4 /output/my_scene 0.5 30000 mcmc
```

Parameters: `<video> <output_dir> [fps] [max_iterations] [strategy]`

Strategies: `mcmc` (default, best quality), `mrnf`, `igs+`

## Full Pipeline Stages

The complete pipeline now includes 8 stages from video input to assembled USD scene:

```
Video File (.mp4/.mov)
    │
    ▼ [Stage 1: Frame Extraction]
    │   SplatReady / PyAV, quality filtering
    │
    ▼ [Stage 2: COLMAP SfM]
    │   Feature extraction → matching → sparse recon → undistortion
    │   ~20 min on 48 cores
    │
    ▼ [Stage 3: 3DGS Training]
    │   LichtFeld MCP (vendored tool), 7k iter in 2m15s, 1M gaussians, 8.4GB VRAM
    │
    ▼ [Stage 4: SAM3 Concept Segmentation]
    │   Text+visual prompts, 4M concepts (upgrading from SAM2)
    │   Fallback: SAM2 grid-point prompts, 46s-5min
    │
    ▼ [Stage 5: Mask Projection to 3D]
    │   2D masks → 3D Gaussian labels via batched voting
    │   98.3% coverage, 33 objects, 7.3 min
    │
    ▼ [Stage 5b: Object Crops]  (ADR-025)
    │   Best-frame selection → SAM-matte crop ≥1024² + provenance
    │   The ONLY generator conditioning — splat contributes pose/scale, never pixels
    │
    ▼ [Stage 6: Per-Object Generation]
    │   Primary: TRELLIS.2 SINGLE-image shape+texture diffusion → PBR GLB
    │            (bytes persisted verbatim, sha256 + lineage sidecar)
    │   Fallback: Hunyuan3D-2.1 single-image (proven Hy3D21 graph)
    │   Environment (full_scene) only: gsplat-TSDF geometry chain
    │
    ▼ [Stage 7: Background Recovery]
    │   FLUX inpainting via ComfyUI (:8188)
    │   Remove objects from training views, retrain clean background
    │
    ▼ [Stage 8: USD Scene Assembly]
    │   59 prims, variant sets (Gaussian + Mesh per object)
    │   Camera prims from COLMAP extrinsics
    │
    ▼
USD Scene + Per-Object PLY + HTML Viewer
```

## Web Upload Interface

Access the web UI via SSH tunnel:

```bash
ssh -N -L 7860:localhost:7860 <user>@<rig>
```

Then open `http://localhost:7860` in your browser. The service binds
`127.0.0.1:7860` only (never `0.0.0.0`); the SSH tunnel is the sole
external access path. Container-to-container access on `v2g-net` /
`visionclaw_network` uses the `LFS_WEB_HOST` env opt-in.

The ingest panel accepts four input modes in a wizard-style multi-step flow:

1. **Video upload** — drag-drop or file-pick an `.mp4`/`.mov`; set title,
   target FPS, and QA preset (fast / balanced / quality).
2. **Raw stills drag-drop** — batch JPEG, PNG, DNG, or HEIC files; the
   pipeline decodes and decompresses them via `image_decoder` before enqueue
   (2 GB cap per batch, secure filename + extension allow-list enforced).
3. **Zip bundle** — upload a capture bundle `.zip`; extracted server-side
   with zip-slip guard and decompressed-size cap into a new job input directory.
4. **Google Drive URL** — paste a Drive share link; the backend reuses the
   existing `gdown`-based ingest path (images preferred over video).

After submission the ingest panel switches to a live progress view driven by
the SSE channel (`/stream/<job_id>`). Stages and percent-complete are updated
in real time; polling fallback (`/api/scenes/<id>/progress`) is available for
clients that cannot consume SSE.

### Post-run flow

Once the pipeline completes:

- **Runs library** (`/library`) — lists every run with status badge,
  thumbnail derived from the contact sheet, and one-click actions.
- **File browser** — expand a run card to browse the output tree with
  inline previews; images and text open in-page, `.glb` files open in the
  mesh viewer, and `.ply`/`.ksplat` files open in the 3D splat viewer.
- **3D splat viewer** — the hybridised viewer (`/splat/<job_id>`) serves
  the best available splat asset for the run (discovery order:
  `output/<id>/web/scene.ksplat` → `model/*.ply` → `*.splat`) and renders
  it with `@mkkellogg/gaussian-splats-3d`; the LichtFeld native visualizer
  can be launched separately for full editing capability.
- **Streamed zip download** — the "Download run" button hits
  `/api/runs/<id>/zip` (streamed via `zipstream-ng`, constant memory);
  `include=all` query param includes the full output tree; the default
  excludes COLMAP database, undistorted frames, and raw frame cache.
  The legacy `/download/<job_id>` route is preserved for the existing Jinja UI.

## Step-by-Step Manual Pipeline

### 1. Extract Frames

```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.lichtfeld/plugins/splat_ready')
from core.frame_extractor import extract_frames
extract_frames('/path/to/video.mp4', '/output/my_scene', 0.5, print)
"
```

### 2. Run COLMAP Reconstruction

```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.lichtfeld/plugins/splat_ready')
from core.colmap_processor import process_colmap
process_colmap('/output/my_scene/frames/video', '/output/my_scene',
               '/usr/local/bin/colmap', {'max_image_size': 2000}, print)
"
```

### 3. Train with LichtFeld (vendored)

```bash
# lichtfeld-studio binary is provided by vendor/lichtfeld-studio (pinned @ v0.5.3)
lichtfeld-studio --headless \
    --data-path /output/my_scene/colmap/undistorted \
    --output-path /output/my_scene/model \
    --iter 30000 \
    --strategy mcmc
```

### 4. SAM3 Concept Segmentation (New)

```bash
# SAM3 text+visual prompt segmentation (upgrading)
python3 -m src.pipeline.sam3d_client \
    --frames /output/my_scene/frames/ \
    --output /output/my_scene/masks/ \
    --prompt "all objects"

# SAM2 fallback (validated)
python3 -m src.pipeline.sam2_segmentor \
    --frames /output/my_scene/frames/ \
    --output /output/my_scene/masks/ \
    --points-per-side 32
```

### 5. Mask Projection to 3D

```bash
python3 -m src.pipeline.mask_projector \
    --gaussians /output/my_scene/model/point_cloud.ply \
    --masks /output/my_scene/masks/ \
    --cameras /output/my_scene/colmap/sparse/0/ \
    --output /output/my_scene/objects/
```

### 6. Per-Object Generation (ADR-025: single-image)

```bash
# Primary: TRELLIS.2 single-image (object_crops matte → shape+texture diffusion
#          → PBR GLB persisted verbatim)
python3 scripts/run_hull_e2e.py \
    /output/my_scene/object_crops/0001_label.png label

# Fallback: Hunyuan3D-2.1 single-image (Hy3D21 graph) — invoked automatically by
# mesh_objects when TRELLIS.2 fails; or grade any GLB with the eval harness:
python3 eval/objects/run_eval.py --stats-only /output/my_scene/objects/meshes/label/label.glb
```

### 7. Background Inpainting via FLUX

```bash
python3 -m src.pipeline.comfyui_inpainter \
    --frames /output/my_scene/frames/ \
    --masks /output/my_scene/masks/ \
    --object-id 1 \
    --output /output/my_scene/inpainted/ \
    --comfyui-url http://localhost:8188
```

### 8. USD Scene Assembly

```bash
python3 scripts/assemble_gallery_usd.py \
    --objects /output/my_scene/objects/ \
    --meshes /output/my_scene/meshes/ \
    --cameras /output/my_scene/colmap/sparse/0/ \
    --output /output/my_scene/scene.usda
```

### 9. Export (via LichtFeld vendored tool)

```bash
lichtfeld-studio convert /output/my_scene/model/point_cloud.ply /output/my_scene/model.spz
lichtfeld-studio convert /output/my_scene/model/point_cloud.ply /output/my_scene/viewer.html
```

## Agent-Controlled Training (MCP)

LichtFeld Studio's local MCP server (vendored at `vendor/lichtfeld-studio`) exposes 70+ tools
for training and scene control. The MCP bridge (`scripts/lichtfeld_mcp_bridge.py`) proxies
stdio MCP to its HTTP endpoint at `:45677`.

```bash
# Start GUI mode (uses vendored lichtfeld-studio binary)
lichtfeld-studio &

# Load dataset
lfs-mcp call scene.load_dataset '{"path":"/output/my_scene/colmap/undistorted"}'

# Start training
lfs-mcp call training.start

# Monitor (poll until done)
lfs-mcp call training.get_state

# Capture renders
lfs-mcp call render.capture '{"width":1920,"height":1080}'

# Export
lfs-mcp call scene.export_spz '{"path":"/output/model.spz"}'
lfs-mcp call scene.export_html '{"path":"/output/viewer.html"}'
```

## Quality Tips

| Parameter | Low Quality / Fast | Balanced | High Quality |
|-----------|-------------------|----------|--------------|
| FPS | 0.2 | 0.5 | 1.0-2.0 |
| Frames | 50-100 | 150-300 | 500+ |
| COLMAP max_image_size | 1000 | 2000 | 4000 |
| Training iterations | 10000 | 30000 | 60000+ |
| Strategy | mcmc | mcmc | mcmc |
| SAM points_per_side | 16 | 32 | 64 |
| Env mesh method | TSDF (fallback) | MILo | CoMe (default) |
| Per-object hull method | TSDF (fallback) | Hunyuan3D-2.1 (fallback) | TRELLIS.2 (primary) |

Mesh backends in detail:

- **Per-object generation** — TRELLIS.2 single-image is the primary path (one matted
  best-frame crop from the `object_crops` stage → shape+texture diffusion → PBR GLB,
  bytes persisted verbatim); Hunyuan3D-2.1 single-image (the proven Hy3D21 graph) is the
  fallback. There is NO geometry-from-partial-splat fallback for objects (ADR-025 —
  failures are reported, not faked); the TSDF chain applies to the environment only.
- **Environment mesh** — CoMe is the default (gated) backend, with MILo, GaussianWrapping,
  and TSDF as fallbacks.
