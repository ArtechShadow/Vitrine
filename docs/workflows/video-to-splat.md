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
    ▼ [Stage 6: Per-Object Hull Creation]
    │   Primary: TRELLIS.2 multiview shape+texture diffusion → PBR-textured GLB
    │           (FLUX.2 view completion upstream)
    │   Fallback: Hunyuan3D-2.1 multi-view → textured mesh
    │   Fallback: TSDF fusion → watertight mesh (22K verts, 49K faces)
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

Upload videos directly via the web interface:

```
http://localhost:7860
```

The web UI provides:
- Drag-and-drop video upload
- Pipeline job management
- Progress monitoring
- Result download

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

### 6. Per-Object Hull Creation

```bash
# Primary: TRELLIS.2 (orbit render → FLUX.2 view completion → multiview shape+texture
#          diffusion → PBR-textured GLB)
python3 scripts/run_hull_e2e.py \
    --object-ply /output/my_scene/objects/object_001.ply \
    --output /output/my_scene/hulls/object_001/

# Fallback: Hunyuan3D-2.1 (multi-view to textured mesh)
python3 -m src.pipeline.hunyuan3d_client \
    --object-ply /output/my_scene/objects/object_001.ply \
    --output /output/my_scene/meshes/object_001/

# Fallback: TSDF mesh (watertight)
python3 scripts/run_tsdf_mesh.py \
    --input /output/my_scene/objects/ \
    --output /output/my_scene/meshes/
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

- **Per-object hulls** — TRELLIS.2 is the primary path (PBR-textured GLB via FLUX.2 view
  completion → multiview shape+texture diffusion); Hunyuan3D-2.1 is the textured-mesh
  fallback; TSDF fusion is the watertight last-resort fallback.
- **Environment mesh** — CoMe is the default (gated) backend, with MILo, GaussianWrapping,
  and TSDF as fallbacks.
