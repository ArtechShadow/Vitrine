# Performance Statistics -- Video-to-USD Pipeline

## Test Environments

### Primary: Consolidated Docker on Dual RTX 6000 Ada
- **GPUs**: 2x NVIDIA RTX 6000 Ada (48 GB each, 96 GB total)
- **CPU**: AMD Threadripper PRO 48-core
- **RAM**: 251 GB
- **Host**: reachable by service DNS on `visionclaw_network` (`gaussian-toolkit` / `vitrine`)
- **Test asset**: Gallery tour video, 121 frames, ~1M Gaussians after 7k training iterations

### Legacy: Agentic Workstation Container
- **GPU**: RTX A6000 48 GB
- **CPU**: 32 cores
- **RAM**: 376 GB
- **Test asset**: 15-second video, 15 extracted frames, ~50k Gaussians

## Infrastructure Diagram

```mermaid
graph TB
    subgraph "gaussian-toolkit (v2g-net + visionclaw_network)"
        direction TB
        WEB[Web UI :7860<br/>Upload + Job Manager]
        LFS[LichtFeld Studio<br/>MCP :45677, 70+ tools]
        COL[COLMAP 4.1.0<br/>--FeatureExtraction.* ns<br/>GPU SIFT fallback, 100% reg]
        PIP[Pipeline Code<br/>41 modules]
        SAM3[SAM3 Segmentor<br/>SAM2 fallback]
        MESH[Mesh Extractor<br/>TSDF + MC fallback]
        USD_A[USD Assembler<br/>v2g:* lineage, 59 prims<br/>baked-texture / VertexColor mat for UE]
    end

    subgraph "vitrine-comfyui (owner ComfyUI)"
        CUI[ComfyUI :8188 (host :8200)<br/>orchestrator]
        TRE[TRELLIS.2-4B<br/>hull PRIMARY ~24GB]
        HUN[Hunyuan3D-2.1<br/>hull fallback ~29GB]
        FLX[FLUX.2-dev<br/>view recovery ~44.6GB]
        S3D[SAM3D]
    end

    subgraph "Sidecars (docker exec / overlay)"
        MILO[milo<br/>MILo / GaussianWrapping]
        COME[come<br/>CoMe env mesh, gated]
        UE[unreal<br/>UE 5.8 USD export, optional<br/>drops displayColor primvar / ignores COLOR_0]
    end

    subgraph "GPU Allocation (96GB)"
        GPU0[GPU0: RTX 6000 Ada 48GB<br/>ComfyUI workloads, serialised]
        GPU1[GPU1: RTX 6000 Ada 48GB<br/>sidecars: milo / come / unreal]
    end

    subgraph "Unified Model Tree (data/comfyui/models, ~216GB)"
        MODELS[FLUX.2 / TRELLIS.2 / Hunyuan3D-2.1<br/>SAM3D, LoRAs]
    end

    PIP --> LFS
    PIP --> COL
    PIP --> SAM3
    PIP --> MESH
    PIP --> USD_A
    PIP -->|http://vitrine-comfyui:8188| CUI
    CUI --> TRE
    CUI --> HUN
    CUI --> FLX
    CUI --> S3D
    PIP -->|docker exec| MILO
    PIP -->|docker exec| COME
    USD_A -.->|optional overlay; textured-USD for captured color| UE
    LFS --> GPU0
    SAM3 --> GPU0
    CUI --> GPU0
    MILO --> GPU1
    COME --> GPU1
    UE --> GPU1
    MODELS -.->|symlink from staging| CUI
```

## Museum Tour Run (2026-03-29) -- Pre-Fix Baseline

| Metric | Value |
|--------|-------|
| Input | 90s museum tour, handheld |
| Extraction | 180 frames at ~2fps (no frame selection) |
| COLMAP registration | 21/180 (11.7%) -- **failure** |
| SAM3 | Fell back to SAM2 (BPE vocab missing) |
| Pipeline | Stopped after training (no mesh/USD) |

**Issues**: No frame selection, exhaustive matcher, missing SAM3 BPE, incomplete pipeline prompt.

All fixed in this commit. Rerun expected to achieve 70%+ registration with 80 selected frames + sequential matcher.

## Pipeline Timing Breakdown

| Stage | Duration | Notes |
|-------|----------|-------|
| Frame Extraction (PyAV) | ~5 s | CPU-only, 4 fps default (oversample) |
| Frame Selection | ~10 s | Quality scoring + diversity, target 80 frames |
| COLMAP Feature Extraction | ~30 s | GPU SIFT via `--FeatureExtraction.type SIFT` (4.1.0 namespace; ALIKED enum invalid in this build, ALIKED_LIGHTGLUE needs missing libcudnn.so.9) |
| COLMAP Sequential Matching | ~1 min | Sequential matcher (video), faster than exhaustive |
| COLMAP Sparse Reconstruction | ~20 min | CPU-bound, 32-48 cores |
| COLMAP Image Undistortion | ~10 s | CPU + disk I/O |
| 3DGS Training (7k iterations) | 2 min 15 s | 1M gaussians, CUDA kernels, 99% GPU util |
| SAM2 Segmentation (13 frames) | ~46 s | Transformer inference |
| SAM2 Segmentation (121 frames) | ~5 min | Full gallery tour |
| Mask Projection to 3D | 7.3 min | CPU, per-Gaussian voting, 200K batches |
| Object Separation | variable | 33 objects extracted, 98.3% coverage |
| TSDF Mesh Extraction | 12 min | Open3D fusion, 22K verts / 49K faces |
| Mesh Cleaning (Trimesh) | ~10 s | CPU |
| USD Assembly | < 1 s | 59 prims, variant sets |
| **Total (end-to-end, gallery)** | **~50 min** | Including TSDF + full segmentation |
| **Total (end-to-end, minimal)** | **~22-25 min** | 15 frames, basic MC mesh |

## GPU VRAM Usage per Stage

| Stage | Allocated VRAM | Peak VRAM | GPU Power |
|-------|---------------|-----------|-----------|
| Frame Extraction | 0 MB | 0 MB | idle |
| COLMAP Feature Extraction (GPU SIFT, `--FeatureExtraction.*`) | ~1.5 GB | ~1.5 GB | 80% util |
| COLMAP Matching | ~1.5 GB | ~1.5 GB | 60% util |
| COLMAP Sparse Recon | ~1.5 GB | ~1.5 GB | CPU-bound |
| COLMAP Undistortion | 0 MB | 0 MB | idle |
| 3DGS Training (7k iter, 1M gaussians) | 8.4 GB | 8.4 GB | 99% util @ 299 W |
| SAM2 Segmentation | 9.5 GB | 9.5 GB | 92% util @ 246 W |
| Mask Projection | 0 MB | 0 MB | CPU only |
| TSDF Mesh Extraction | 0 MB | ~3 GB RAM | CPU only |
| USD Assembly | 0 MB | 0 MB | idle |

**Peak GPU VRAM**: 9.5 GB (SAM2 segmentation stage)

## Object Separation Results

| Metric | Value |
|--------|-------|
| Total Gaussians (after outlier filter) | 950,000 |
| Labeled Gaussians | 933,837 (98.3%) |
| Unlabeled Gaussians | 16,163 |
| Objects extracted (>= 10 Gaussians) | 33 |
| Dominant object (room/walls) | 661,548 Gaussians (69.6%) |
| Second largest | 107,438 Gaussians (11.3%) |
| Third largest | 57,291 Gaussians (6.0%) |

## TSDF Mesh Results

| Metric | Value |
|--------|-------|
| Vertices | 22,000 |
| Faces | 49,000 |
| Extraction time | 12 min |
| RAM usage | ~3 GB |
| Method | Open3D TSDF fusion |

## USD Scene Results

| Metric | Value |
|--------|-------|
| Total prims | 59 |
| Variant sets | Gaussian + Mesh per object |
| Assembly time | < 1 s |
| UE captured color | requires baked-texture (UsdUVTexture) or explicit VertexColor material -- UE 5.8 USD import drops the `displayColor` primvar (flat white) and Interchange GLB import ignores `COLOR_0` vertex colors |

> **UE captured-color note (L2)**: Blender Cycles GPU bake (`blender_assembler.py bake_vertex_colors_to_texture`, Smart UV Project) works on clean watertight hulls but collapses on room-scale MILo meshes (thin/disconnected components yield degenerate near-zero-area UV islands -> near-black atlas). For room/scene-scale captured color the highest-fidelity output is a direct gsplat splat render, not a baked mesh texture.

## System RAM Usage per Stage

| Stage | Peak RAM | Notes |
|-------|----------|-------|
| Frame Extraction | ~200 MB | PyAV decoder |
| COLMAP (all phases) | ~4 GB | Feature DB + matching |
| 3DGS Training | ~30 GB | Point cloud + SH coefficients |
| SAM2 Segmentation | ~31 GB | Model weights + frame buffers |
| Mask Projection | ~4 GB | Batch voting arrays |
| TSDF Mesh Extraction | ~3 GB | Voxel grid + fusion |
| Mesh Extraction (MC) | ~8 GB | Voxel grid + marching cubes |
| USD Assembly | ~100 MB | Scene graph serialization |

**Peak system RAM**: ~31 GB (SAM2 segmentation, co-resident with training data)

## Disk Usage for Intermediate Artifacts

| Artifact | Size | Path |
|----------|------|------|
| Extracted frames (15 frames) | ~45 MB | `<project>/frames/` |
| Extracted frames (121 frames) | ~360 MB | `<project>/frames/` |
| COLMAP sparse model | ~5 MB | `<project>/colmap/sparse/` |
| COLMAP undistorted images | ~90 MB | `<project>/colmap/undistorted/` |
| 3DGS checkpoint (7k iter) | ~50 MB | `<project>/output/point_cloud/` |
| SAM2 masks (per frame) | ~2-20 MB | `<project>/masks/` |
| Per-object PLY files (33 objects) | ~200 MB | `<project>/objects/` |
| TSDF mesh | ~5 MB | `<project>/meshes/` |
| Final USD scene | ~20-100 MB | `<project>/scene.usda` |
| **Total per project (gallery)** | **~800 MB** | |
| **Total per project (minimal)** | **~220-440 MB** | |

## Minimum / Recommended Hardware Specifications

Based on measured peak usage with 20% headroom.

| Component | Minimum | Recommended | Consolidated Docker |
|-----------|---------|-------------|---------------------|
| GPU VRAM | 12 GB | 24 GB | 96 GB (2x RTX 6000 Ada) |
| System RAM | 36 GB | 64 GB | 251 GB |
| CPU Cores | 8 | 16 | 48 (Threadripper PRO) |
| Disk (SSD) | 50 GB free | 200 GB free | 128 GB models + workspace |
| GPU Compute | SM 7.5+ (Turing) | SM 8.6+ (Ampere) | SM 8.9 (Ada Lovelace) |
| CUDA | 11.8+ | 12.1+ | 12.4 |

### GPU Compatibility Notes

- **12 GB VRAM**: Can run the pipeline if SAM2 and training do not overlap. Use `CUDA_VISIBLE_DEVICES` to serialize.
- **24 GB VRAM**: Comfortable for single-object scenes. Multi-object with ComfyUI inpainting requires a second GPU or remote endpoint.
- **48 GB+ VRAM**: Practical floor for the full SOTA stack. FLUX.2 (~44.6 GB) and TRELLIS.2 (~24 GB) cannot co-reside on 48 GB, so models load/unload serially via ComfyUI `POST /free` (peak VRAM = max stage, not the sum).
- **96 GB (dual GPU)**: GPU0 runs the serialised ComfyUI workloads (training, segmentation, FLUX.2, TRELLIS.2 / Hunyuan3D-2.1); GPU1 runs the mesh/export sidecars (milo / come / unreal).

### Dual RTX 6000 Ada Target Specs

| Feature | Value |
|---------|-------|
| Architecture | Ada Lovelace (SM 8.9) |
| VRAM per GPU | 48 GB GDDR6 ECC |
| Memory bandwidth | 960 GB/s per GPU |
| CUDA cores | 18,176 per GPU |
| RT cores | 142 per GPU |
| TDP | 300W per GPU |
| Total VRAM | 96 GB |
| NVLink | Not available (PCIe only) |

### Multi-GPU Configuration

| GPU | Role | VRAM Required |
|-----|------|---------------|
| GPU 0 | ComfyUI workloads: training + SAM2/SAM3 + FLUX.2 + TRELLIS.2 / Hunyuan3D-2.1 (serialised) | 12 GB min (TSDF-only), 48 GB recommended (full SOTA stack) |
| GPU 1 | Sidecars: milo / come / unreal mesh + USD export | 12 GB min |
