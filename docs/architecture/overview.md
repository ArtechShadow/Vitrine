# Vitrine Architecture

**Vitrine** is a standalone capture-adaptive video → structured-3D-scene → Unreal Engine 5.8
game-asset pipeline. Code identifiers still say `video2splat` / `gaussian-toolkit`; a full
code rename is a separate scheduled follow-up (ADR-015).

> **Vendored tool:** [LichtFeld Studio](https://github.com/MrNeRF/LichtFeld-Studio) is pinned
> as a git submodule at `vendor/lichtfeld-studio` (tag v0.5.3). It supplies native 3DGS training,
> visualisation, editing, export, and a local MCP server. Vitrine never modifies it; updates are a
> submodule bump. Vitrine's own code — the pipeline, web UI, Docker stack, onboarding wizard, and
> Unreal overlay — lives outside the submodule directory.

## System Overview (v2 — current)

> See also: [docs/architecture.md](../architecture.md) for the multi-container deployment architecture and the **v3 End-to-End Architecture** section (the v3 service-DNS topology is now the live state, not merely proposed).
>
> For the v3 pipeline design reference, see [architecture/v3-pipeline.md](v3-pipeline.md).

Gaussian Toolkit integrates multiple components into a unified 3D Gaussian Splatting pipeline running across Docker containers on dual RTX 6000 Ada GPUs (96GB total VRAM). GPU 0 runs the ComfyUI workloads (FLUX.2, TRELLIS.2, training, segmentation — serialised, ADR-013); GPU 1 runs the mesh/render sidecars (milo / come / unreal).

```
┌───────────────────────────────────────────────────────┐
│  gaussian-toolkit container (GPU 0)                    │
│  Ubuntu 24.04 / CUDA 12.8 / Python 3.12               │
├───────────────────────────────────────────────────────┤
│  COLMAP SfM → LichtFeld 3DGS → SAM3 Segmentation     │
│  → TRELLIS.2 hull / CoMe env mesh → USD Export        │
│                                                        │
│  Web UI :7860 (file browser, splat viewer,            │
│    zip, ingest) | MCP :45677 | ttyd :7681            │
│  VNC :5901 (host :5902)                               │
│  Claude Code (agentic orchestrator)                    │
└────────────────┬──────────────────────────────────────┘
                 │ v2g-net (service DNS) / shared /data/output
┌────────────────▼──────────────────────────────────────┐
│  vitrine-comfyui container (GPU 0, reuses image)       │
│  Owner ComfyUI :8188 (host :8200)                     │
│  FLUX.2 / TRELLIS.2 / Hunyuan3D-2.1 / SAM3D           │
└────────────────┬──────────────────────────────────────┘
                 │ docker exec / shared /data/output
┌────────────────▼──────────────────────────────────────┐
│  milo (GPU 1)  | come (GPU 1, gated, off by default)   │
│  Ubuntu 22.04 / CUDA 11.8 / Python 3.10               │
│  MILo (+ optional GaussianWrapping) / CoMe mesh        │
└────────────────┬──────────────────────────────────────┘
                 │ unreal/docker-compose.unreal.yml overlay
┌────────────────▼──────────────────────────────────────┐
│  unreal (GPU 1, optional overlay, not started yet)    │
│  vitrine-unreal:5.8 USD scenegraph export + render     │
│  + unreal-mcp-bridge :9100                             │
└───────────────────────────────────────────────────────┘
                 ▲
                 │ lfs-mcp CLI / MCP bridge / Web UI
                 ▼
         Claude Code / Agents
```

## Component Stack

| Component | Version | License | Purpose |
|-----------|---------|---------|---------|
| LichtFeld Studio (vendored) | v0.5.3 | GPL-3.0 | 3DGS training, visualisation, editing, export (via `vendor/lichtfeld-studio`) |
| COLMAP | 4.1.0 | BSD | Structure-from-Motion reconstruction |
| SplatReady | 1.0.0 | Plugin | Video-to-COLMAP pipeline automation |
| SAM3 | latest | Apache-2.0 | Concept segmentation (4M concepts, text+visual prompts) |
| SAM2 | hiera-large | Apache-2.0 | Video segmentation (fallback, validated) |
| TRELLIS.2-4B | 4B | MIT | **Primary** per-object hull (multiview shape+texture diffusion → PBR GLB) |
| Hunyuan3D-2.1 | 2.1 | Tencent-community | Per-object hull **fallback** (multi-view to textured mesh) |
| ComfyUI | latest | GPL-3.0 | Node-based workflow engine (FLUX.2 / TRELLIS.2 / Hunyuan3D-2.1 / SAM3D) |
| FLUX.2-dev | dev | Non-commercial | View completion + inpaint/background recovery (Qwen-Image-Edit = commercial-safe alt) |
| CoMe | latest | gated | **Default** environment mesh (MILo / GaussianWrapping / TSDF fallbacks) |
| MILo | SIGGRAPH Asia 2025 | research | Differentiable mesh-in-the-loop env mesh (fallback) |
| Open3D | 0.18+ | MIT | TSDF fusion, mesh processing (env-mesh floor fallback) |
| OpenUSD | 25.02+ | Modified Apache 2.0 | USD scene composition |
| METIS | 5.2.1 | Apache-2.0 | Graph partitioning (COLMAP dependency) |
| Flask | 3.x | BSD | Operator UI: ingest (video/stills/zip/Drive), run browser + file tree, 3D splat viewer (gaussian-splats-3d, bundled), streamed zip download, disk/health/system stats. Loopback-only per ADR-022; ADR-023 records the ArchiveSpace UX consolidation. |
| vcpkg | latest | MIT | C++ dependency management (91 packages) |

## Data Flow

### Full Pipeline (video2splat -> scene assembly)

```
Video File (.mp4/.mov) or Web Upload (:7860)
    │
    ▼ [Stage 1: SplatReady - PyAV frame extraction]
JPEG Frames + GPS EXIF
    │
    ▼ [Stage 2: COLMAP - 6-step SfM pipeline]
    │   feature_extractor → exhaustive_matcher → mapper
    │   → model_aligner → image_undistorter → model_converter
    │
    ▼
COLMAP Undistorted Dataset
    │   images/ + sparse/0/{cameras,images,points3D}.txt
    │
    ▼ [Stage 3: LichtFeld (vendored) - CUDA-accelerated training]
Trained 3D Gaussian Splat Model (1M gaussians)
    │
    ▼ [Stage 4: SAM3 Concept Segmentation]
    │   text+visual prompts, 4M concepts
    │   (fallback: SAM2 grid-point prompts)
    │
    ▼ [Stage 5: Mask Projection to 3D]
    │   2D masks → 3D Gaussian labels (98.3% coverage)
    │   33 per-object PLY files extracted
    │
    ▼ [Stage 6: Per-Object Hull Creation]
    │   orbit render → coverage gate → FLUX.2 view completion
    │   → TRELLIS.2-4B multiview shape+texture diffusion → PBR GLB (primary)
    │   Hunyuan3D-2.1 fallback; TSDF floor fallback: Open3D fusion
    │
    ▼ [Stage 7: Environment Mesh + Background Recovery]
    │   CoMe env mesh (MILo / GaussianWrapping / TSDF fallbacks)
    │   FLUX.2 inpaint/recovery via ComfyUI (vitrine-comfyui:8188)
    │
    ▼ [Stage 8: USD Scene Assembly]
USD Scene (59 prims, variant sets: Gaussian + Mesh per object)
    + PLY / SOG / SPZ / HTML exports
```

### MCP-Controlled Pipeline

```
Claude Agent
    │
    ├─► lfs-mcp call scene.load_dataset {"path": "..."}
    ├─► lfs-mcp call training.start
    ├─► lfs-mcp call training.get_state  (poll loop)
    ├─► lfs-mcp call render.capture {"width": 1920}
    ├─► lfs-mcp call selection.by_description {"description": "floaters"}
    ├─► lfs-mcp call gaussians.write {"delete_selected": true}
    └─► lfs-mcp call scene.export_spz {"path": "output.spz"}
```

## Multi-Container Docker Architecture

The pipeline runs as a multi-container stack: the main container, a dedicated owner-ComfyUI container, mesh sidecars (MILo / CoMe), and an optional Unreal 5.8 overlay. The canonical stack is `docker-compose.consolidated.yml` (+ `Dockerfile.consolidated`) at the repo root; sidecar Dockerfiles and the entrypoint live under `docker/`, and the UE 5.8 overlay is self-contained under the top-level `unreal/`.

```
┌─────────────────────────────────────────────────────────┐
│  gaussian-toolkit (GPU 0)                                │
│  Ubuntu 24.04 / CUDA 12.8 / Python 3.12                 │
├─────────────────────────────────────────────────────────┤
│  Services (supervisord):                                  │
│    Web UI (:7860)        - Flask upload + job manager     │
│    LichtFeld MCP (:45677) - 70+ tools (vendored)         │
│    ttyd (:7681)          - Web terminal (Claude Code)    │
│    VNC (:5901, host :5902) - Remote desktop (Blender)    │
├─────────────────────────────────────────────────────────┤
│  Pipeline (41 modules in src/pipeline/):                  │
│    stages, orchestrator, cli, config, preflight,          │
│    sam2_segmentor, sam3_segmentor, sam3d_client,          │
│    mask_projector, mesh_extractor, milo_extractor,       │
│    come_extractor, mesh_cleaner, blender_assembler,      │
│    usd_assembler (v2g:* lineage), texture_baker,         │
│    material_assigner, mcp_client, multiview_renderer,    │
│    trellis_client, hunyuan3d_client, comfyui_inpainter,  │
│    quality_gates, frame_quality, frame_selector,         │
│    colmap_parser, coordinate_transform, person_remover,  │
│    agent_llm, sota_registry, … (+ __init__, __main__)    │
└────────────────┬────────────────────────────────────────┘
                 │ v2g-net (http://vitrine-comfyui:8188)
┌────────────────▼────────────────────────────────────────┐
│  vitrine-comfyui (GPU 0) — owner ComfyUI, reuses image   │
│  scripts/run_comfyui.sh → scripts/comfyui_entrypoint.sh  │
│  ComfyUI :8188 (host :8200)                              │
│  FLUX.2 / TRELLIS.2 / Hunyuan3D-2.1 / SAM3D             │
│  Serial VRAM lifecycle via POST /free (ADR-013)         │
└────────────────┬────────────────────────────────────────┘
                 │ docker exec milo … / shared /data/output
┌────────────────▼────────────────────────────────────────┐
│  milo (GPU 1) — sidecar, called via docker exec          │
│  Ubuntu 22.04 / CUDA 11.8 / Python 3.10                 │
│  MILo (SIGGRAPH Asia 2025) (+ optional GaussianWrapping) │
│  Differentiable mesh-in-the-loop gaussian splatting      │
└────────────────┬────────────────────────────────────────┘
                 │ optional, gated (INSTALL_COME=1)
┌────────────────▼────────────────────────────────────────┐
│  come (GPU 1) — env-mesh sidecar, off by default         │
│  CoMe mesh extraction (licensing-gated, no prebuilt img) │
└────────────────┬────────────────────────────────────────┘
                 │ unreal/docker-compose.unreal.yml overlay
┌────────────────▼────────────────────────────────────────┐
│  unreal (GPU 1) — vitrine-unreal:5.8, optional overlay   │
│  UE 5.8 USD scenegraph export + render (image built;     │
│  overlay not started yet). + unreal-mcp-bridge :9100     │
│  Web Remote Control :30010 (primary), UE MCP :8000 (exp) │
└─────────────────────────────────────────────────────────┘
```

> Networks: **v2g-net** is the internal bus (containers resolve each other by service name — the pipeline reaches ComfyUI as `http://vitrine-comfyui:8188`). **visionclaw_network** is the shared external network joined by `gaussian-toolkit` (aliases `gaussian-toolkit`, `vitrine`), `vitrine-comfyui`, `milo`, and `agentbox`, letting the VisionFlow app and the Claude Code environment reach the pipeline by service name. Service-DNS / localhost replace the old hardcoded `localhost:PORT` scheme.

## GPU Architecture

- **CUDA Toolkit**: 13.1
- **Target architectures**: sm_89 (RTX 6000 Ada), sm_86 (RTX A6000/3090), sm_75 (RTX 6000/2080)
- **C++ Standard**: C++23
- **CUDA Standard**: C++20
- **Build system**: CMake + Ninja + vcpkg

## MCP Server Architecture

```
scripts/lichtfeld_mcp_bridge.py                      <-- stdio MCP client (Claude Desktop/Codex)
        │
        │ HTTP POST to http://127.0.0.1:45677/mcp
        ▼
vendor/lichtfeld-studio/src/mcp/mcp_http_server.cpp  <-- cpp-httplib HTTP listener (vendored)
        │
        ▼
vendor/lichtfeld-studio/src/mcp/mcp_server.cpp       <-- JSON-RPC 2.0 dispatcher (vendored)
        │
        ├──► ToolRegistry (singleton)       70+ tools
        └──► ResourceRegistry (singleton)   8+ resources
```

### Tool Runtime Model

Tools are registered in two backends depending on the application mode:

- **Headless**: `TrainingContext` singleton manages scene/trainer directly
- **GUI**: `Visualizer` provides the backend with live viewport interaction

Each tool carries metadata:
- `category` (training, scene, render, selection, etc.)
- `kind` (command vs query)
- `runtime` (shared, headless, gui)
- `thread_affinity` (any, training_context, main_thread)
- `destructive`, `long_running`, `user_visible` flags

## Directory Layout

Summary:

```
vitrine/                   (repo root)
├── src/
│   ├── pipeline/          # Vitrine — 41 Python pipeline modules
│   └── web/               # Vitrine — Flask web interface (:7860)
├── vendor/
│   └── lichtfeld-studio/  # VENDORED — LichtFeld Studio @ v0.5.3 (git submodule, never modified)
├── onboarding/            # Vitrine — Rust/Axum exhibit-manifest wizard (:8088)
├── unreal/                # Vitrine — self-contained UE 5.8 overlay
│   │                      #           (engine/, runtime/, Dockerfile.unreal,
│   │                      #            docker-compose.unreal.yml)
├── research/              # Vitrine — research documents + ADRs (not product)
├── docker/                # Vitrine — sidecar Dockerfiles + entrypoint + configs
├── scripts/               # Vitrine — run_comfyui.sh, bridges, e2e/test harnesses
├── Dockerfile.consolidated         # Vitrine — Consolidated container (repo root)
├── docker-compose.consolidated.yml # Vitrine — Single-command deployment (repo root)
├── docs/                  # Vitrine — project documentation (this site)
└── build/                 # Build output (not committed)
```
