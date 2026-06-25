# Proposed Pipeline: Agentic Video-to-Scene

## Architecture Overview

```mermaid
graph TB
    subgraph "STAGE 1: INGEST"
        V[Video File] --> FE[Frame Extraction<br/>SplatReady/PyAV]
        FE --> QA1[SOTA Frame-QA Gate<br/>MUSIQ NR-IQA + windowed best-of]
        QA1 -->|enough good frames| FR[Selected Frames]
        QA1 -->|too_low_quality| DROP[Drop video + flag<br/>try next / re-capture]
    end

    subgraph "STAGE 2: RECONSTRUCT"
        FR --> COL[COLMAP SfM]
        COL --> GG[Gaussian Grouping Training<br/>Joint 3DGS + Segmentation<br/>+ppisp +bilateral · UNPRUNED]
        GG --> QA2[Quality Gate<br/>Loss/PSNR/SSIM]
        QA2 --> TS[Trained Scene<br/>+ Per-Gaussian Object Labels]
    end

    subgraph "STAGE 3: DECOMPOSE"
        TS --> OE[Object Extraction<br/>Per-Label Gaussian Groups<br/>remap vertex colors thru kept-index map]
        OE --> ME[Mesh Extraction GPU<br/>SuGaR / MILo radegs per Object]
        OE --> BI[Background Inpainting<br/>FLUX via ComfyUI]
        BI --> BR[Background Retrain<br/>Clean Environment Gaussian]
        ME --> BK{Clean watertight hull?}
        BK -->|yes| TM[Textured Meshes<br/>Smart-UV + Cycles GPU bake<br/>OBJ + baked diffuse texture]
        BK -->|no: room-scale| SR[Direct Gaussian-Splat Render<br/>gsplat — captured color]
    end

    subgraph "STAGE 4: ASSEMBLE"
        TM --> UA[USD Assembly<br/>OpenUSD Python API]
        SR --> UA
        BR --> UA
        UA --> VS[Variant Sets<br/>Gaussian + Mesh per Object]
        VS --> VAL[Validation<br/>Render Comparison + UE ingest]
        VAL --> OUT[Final USD Scene<br/>baked-texture or VertexColor material]
        OUT --> UEN[UE 5.8 Scene<br/>full-res mesh as Nanite · auto-LOD]
        OUT --> WEB[Web delivery<br/>decimated GLB / .ksplat]
    end

    style V fill:#4a9eff
    style OUT fill:#4aff4a
    style GG fill:#ff4a4a
    style ME fill:#ff4a4a
    style BI fill:#ff4a4a
    style UA fill:#ffaa4a
    style DROP fill:#ff6a6a
    style UEN fill:#4aff4a
    style BK fill:#ffaa4a
    style SR fill:#4a9eff
```

Red = new development, Yellow = extend existing, Blue/Green = input/output.

## Agentic Orchestration

```mermaid
stateDiagram-v2
    [*] --> INGEST
    INGEST --> RECONSTRUCT: Frames ready
    RECONSTRUCT --> QUALITY_GATE_1: Training complete
    QUALITY_GATE_1 --> RECONSTRUCT: PSNR < 25
    QUALITY_GATE_1 --> DECOMPOSE: PSNR >= 25
    DECOMPOSE --> EXTRACT_OBJECTS: Labels assigned
    EXTRACT_OBJECTS --> MESH_OBJECTS: Gaussians extracted
    MESH_OBJECTS --> QUALITY_GATE_2: Meshes generated
    QUALITY_GATE_2 --> MESH_OBJECTS: Mesh quality low
    QUALITY_GATE_2 --> INPAINT_BG: Mesh quality OK
    INPAINT_BG --> RETRAIN_BG: Images inpainted
    RETRAIN_BG --> USD_ASSEMBLE: Background ready
    USD_ASSEMBLE --> VALIDATE: Scene composed
    VALIDATE --> USD_ASSEMBLE: Validation failed
    VALIDATE --> [*]: Scene valid
```

Each state transition is an agent decision point. The orchestrator agent evaluates quality metrics and decides whether to proceed, retry with adjusted parameters, or abort with partial results.

## Stage Detail

### Stage 1: Ingest

**Agent**: Ingest Agent

**Tools**: SplatReady (`extract_frames`), OpenCV (blur detection), LichtFeld MCP

**Process**:
1. Extract frames from video at initial FPS (adaptive: 0.5-2.0 based on motion)
2. Compute per-frame quality: Laplacian variance (blur), histogram spread (exposure)
3. Drop frames below blur threshold
4. Flag sequence for PPISP if exposure variance > 1.5 EV
5. Detect duplicate frames via perceptual hashing
6. Output: quality-filtered frame set

**Decision Points**:
- Frame count < 50 → warn insufficient coverage
- Frame count > 500 → subsample
- All frames blurry → suggest different video or enable deblurring

### Stage 2: Reconstruct

**Agent**: Reconstruction Agent

**Tools**: COLMAP 4.1.0, LichtFeld MCP (70+ tools)

> **COLMAP 4.1.0 note**: the option namespace changed to `--FeatureExtraction.*` /
> `--FeatureMatching.*` (NOT `--SiftExtraction.use_gpu`). `FeatureExtraction.type SIFT`
> is the working enum — the `ALIKED` enum is invalid in this build, and
> `ALIKED_LIGHTGLUE` needs `libcudnn.so.9` which is missing, so the **GPU-SIFT path is
> the fallback** (gave 100% registration on the e2e run). Use
> `--ImageReader.single_camera_per_folder` for mixed cameras, and `mkdir` the colmap dir
> before `feature_extractor` (it checks `database_parent_path`).

**Process**:
1. Run COLMAP via SplatReady pipeline (GPU SIFT)
2. Load dataset: `lfs-mcp call scene.load_dataset`
3. Train with Gaussian Grouping (joint segmentation):
   - Strategy: MCMC
   - Iterations: 30,000
   - Enable PPISP if flagged
   - Enable pose optimisation if loss > 0.1 at iteration 5000
4. Monitor via `lfs-mcp call training.get_state` every 30s
5. Quality gate: render from training views, compute PSNR/SSIM

**Decision Points**:
- COLMAP fails → fallback to InstantSplat
- Loss plateau before 15k iterations → increase learning rate
- Loss oscillates → decrease learning rate
- PSNR < 25 → retrain with adjusted parameters

**Output**: Trained 3DGS scene with per-Gaussian object identity labels

### Stage 3: Decompose

**Agent**: Decomposition Agent (3 sub-tasks)

#### 3a. Object Extraction

**Tools**: Gaussian Grouping labels, LichtFeld selection tools, SAGA (refinement)

**Process**:
1. Read Gaussian identity labels from training
2. For each unique label > threshold size:
   - Create selection mask
   - `lfs-mcp call history.begin_transaction`
   - Duplicate node for object
   - Store mask for inpainting
3. Optionally refine boundaries with SAGA interactive segmentation
4. Validate: render each object in isolation, check completeness

> **Color-preservation pitfall**: when filtering mesh components (dropping small/
> disconnected parts), vertex colors MUST be remapped through the kept-vertex index map.
> Rebuilding a `Trimesh` without explicitly carrying colors yields trimesh's default gray
> `[102,102,102]` — which read as a spurious "white/gray in UE" red herring on the e2e
> run. Also: `trimesh.split()` + `concatenate()` HANGS at ~1.8M verts → use
> `trimesh.graph.connected_components` plus an explicit index remap instead.

#### 3b. Mesh Extraction (Per Object)

**Tools**: SuGaR or SOF/GOF, MILo radegs (GPU), Blender Cycles GPU bake

> **GPU-always**: every extraction/bake step here is GPU (MILo radegs, Cycles GPU bake).
> A CPU path (numpy TSDF, PIL per-face baker, Python projection loops) is a defect to
> replace — the proven baker is `blender_assembler.bake_vertex_colors_to_texture()`
> (Cycles GPU, ~0.5 s / 100k faces); grep `src/pipeline` + `scripts` for it before
> writing any new baking code.

**Primary Path (SuGaR)**:
1. Export per-object Gaussians
2. Run SuGaR: produces OBJ with UV-mapped diffuse texture
3. Clean mesh: remove disconnected components, smooth
4. Decimate to target polygon count

**Alternative Path (SOF + Texture Baking)**:
1. Extract mesh via Marching Tetrahedra on opacity field (vertex-coloured)
2. Generate UV atlas with xatlas (or Blender Smart UV Project)
3. Bake diffuse texture from Gaussian colour renders projected onto UV (Cycles GPU)

> **Captured-color baking caveat (L2)**: a baked-texture material is *mandatory* for UE
> (see Stage 4) but the Smart-UV-Project + Cycles bake only succeeds on **clean,
> watertight HULLS**. On room-scale MILo meshes (many thin/disconnected components — 876
> removed on scene02) Smart UV Project COLLAPSES into degenerate near-zero-area UV islands
> → a near-black atlas. For room/scene-scale captured color the highest-fidelity output is
> a **direct Gaussian-splat render (gsplat)**, not a baked mesh texture.

**Decision**: SuGaR for quality, SOF for speed — benchmark both on the first object and
pick the winner for remaining objects. Per-object close-orbit captures (e.g. a dedicated
turnaround) give clean hulls that bake cleanly; route the messy room mesh to the gsplat
render path instead.

#### 3c. Background Recovery

**Tools**: ComfyUI + FLUX + Gaussian Splats Repair LoRA

**Process**:
1. For each training image:
   - Generate binary mask of all extracted objects
   - Send to ComfyUI FLUX inpainting workflow
   - Denoise strength: 0.65-0.85
2. Replace training images with inpainted versions
3. Retrain background-only Gaussian from inpainted dataset

**Decision Points**:
- Inpainting quality per-view: compare inpainted region texture to surrounding context
- If FLUX LoRA is NC-licensed → use standard SDXL inpainting instead
- Large occluded areas → multiple inpainting passes with varying seeds

### Stage 4: Assemble

**Agent**: USD Assembly Agent

**Tools**: OpenUSD Python API (`pxr`), LichtFeld `scene.export_usd`

**Process**:
1. Export each object as individual USD file via LichtFeld
2. Export background as USD file
3. Compose master scene:
   ```
   /World (Xform, Y-up, meters)
     /World/Environment/Background (ParticleField3DGaussianSplat)
     /World/Objects/Object_001 (Xform + reference to object_001.usd)
       variant_set "representation": gaussian | mesh
     /World/Objects/Object_002 ...
     /World/Cameras/cam_0000 (Camera from COLMAP)
   ```
4. Apply coordinate transforms (COLMAP Y-down → USD Y-up)
5. Create variant sets per object (Gaussian + Mesh representations)
6. Assign materials to mesh variants — **a baked-texture or explicit VertexColor material
   is mandatory** (UsdPreviewSurface + UsdUVTexture). Do NOT rely on vertex colors or the
   `displayColor` primvar: UE 5.8 Interchange GLB import IGNORES vertex colors (`COLOR_0`)
   — "Mesh has primitives with no materials assigned" — and UE USD import DROPS the
   `displayColor` primvar (renders flat white). Only (a) a baked-texture material
   (`UsdUVTexture` / textured GLB) or (b) an explicit VertexColor material survives the UE
   boundary. For mesh objects, prefer the textured GLB from the clean-hull Cycles bake; for
   room/scene-scale captured color, carry the direct gsplat render rather than a baked mesh.
7. Write metadata: source video, COLMAP params, training config

**Validation**:
- Render USD scene from training viewpoints
- Compare against original training images
- PSNR/SSIM should be within 3dB of original Gaussian render

## Technology Stack

| Stage | Primary | Fallback | Interface | Status |
|-------|---------|----------|-----------|--------|
| Frame extraction | SplatReady (PyAV) | FFmpeg CLI | CLI/MCP | Exists |
| SfM | COLMAP 4.1.0 (GPU SIFT; new `--FeatureExtraction.*` namespace) | InstantSplat/DUSt3R | CLI | Exists |
| 3DGS + Segmentation | Gaussian Grouping | LichtFeld + SAGA | MCP | **New** |
| Pose optimisation | LichtFeld --pose-opt | — | MCP | Exists |
| PPISP correction | LichtFeld native | — | MCP | Exists |
| Object extraction | Label-based selection | SAGA interactive | MCP | **New** |
| Mesh extraction | SuGaR / MILo radegs (GPU) | SOF (GPU TSDF only) | Python | **New** |
| Background inpaint | FLUX via ComfyUI | SDXL, LaMa | ComfyUI API | **New** |
| Texture baking | Blender Smart-UV + Cycles GPU bake (clean hulls) | direct gsplat render (room-scale) | Python | **New** |
| USD export (single) | LichtFeld export_usd | — | MCP | Exists |
| USD composition | OpenUSD Python | — | Python | **New** |
| Quality assessment | PSNR/SSIM + LLM vision | — | MCP render | Partial |

## Edge Cases and Left-Field Ideas

### Edge Cases
- **Transparent objects** (glass, water): Gaussians handle transparency well but mesh extraction fails. Keep as Gaussian-only in USD.
- **Reflective surfaces**: SH coefficients capture view-dependent reflection. Mesh PBR materials need environment probes.
- **Thin structures** (fences, wires): Gaussians excel but SuGaR over-smooths. SOF's Marching Tetrahedra preserves thin features better.
- **Repeating patterns** (tiled floors, brick walls): COLMAP feature matching may fail. Use InstantSplat fallback.
- **Moving objects in video**: Detect via optical flow residual after camera motion compensation. Mask out for static scene reconstruction, or use 4D Gaussians (future extension).

### Left-Field Ideas
- **DreamGaussian for hole filling**: When an object is partially occluded, generate the unseen portion using DreamGaussian from the best visible view.
- **RL3DEdit for automated cleanup**: Text-driven scene editing ("remove all shadows", "brighten the ceiling") before decomposition.
- **mesh2splat round-trip validation**: Convert extracted mesh back to Gaussians via EA's mesh2splat. Compare render quality. If degradation < threshold, mesh is faithful.
- **Blender procedural materials**: For background elements (walls, floors), detect material type and assign Blender procedural shaders rather than baked textures. Higher quality, resolution-independent.
- **LLM scene understanding**: Before segmentation, render panoramic view and ask LLM to describe the scene. Use description to guide Gaussian Grouping label assignment and naming.
- **ConceptGraphs-style scene graph**: Build semantic relationships between objects ("chair is-on floor", "painting is-on wall") for richer USD metadata.
