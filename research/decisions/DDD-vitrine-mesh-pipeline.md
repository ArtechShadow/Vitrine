# DDD: Vitrine Video → Mesh → Unreal Engine Pipeline

Status: living document · Author: domain modelling pass · Date: 2026-06-22

**Scope of this model.** This document models the *delivered* Vitrine domain: turning
capture video into a **textured polygonal scene** — a room mesh plus per-object textured
meshes — imported into **Unreal Engine 5.8** as game-style assets (FBX). It is the
authoritative DDD for the mesh/UE delivery path.

**Explicitly out of the delivered contract:**

- **No USD.** USD is *not* the delivery artifact for the UE path. The legacy
  `usd_assembler.py` / `assemble_usd` stage and the `DDD: Domain Model for Video-to-Scene
  Pipeline` doc (`ddd-domain-model.md`) describe the older USD-scenegraph contract; they
  are superseded for UE delivery by this document. USD may still be emitted as an interop
  by-product, but it is not what crosses into UE.
- **Gaussian-in-UE is optional** (a splat can ride alongside the meshes for scenes where a
  bake collapses, but it is not the primary asset).
- **Interactivity / lighting** in UE are *stretch* goals, not part of the core contract.

---

## 1. Ubiquitous Language

These terms are the shared vocabulary. Code, ADRs, and conversation must use them with
exactly these meanings.

| Term | Definition | Where it lives |
|---|---|---|
| **Capture / Video** | A single source video clip from a capture session. The lineage root. | ingest stage; `drive_ingestor.py` |
| **Frame** | A still RGB image extracted from a Video at a chosen FPS. Carries a back-pointer to its source Video + PTS timestamp. | `ingest`, frame sidecars |
| **FrameQuality** | A no-reference quality verdict for a Frame, headed by the **MUSIQ** NR-IQA metric (pyiqa, koniq weights), with classical fallbacks (Laplacian blur variance, gradient coverage). Drives the **keep / marginal / drop** gate. | `frame_quality.py` |
| **MUSIQ gate** | The per-video drop-and-flag admission rule: frames below the MUSIQ/blur/coverage thresholds are dropped; a whole Video can be flagged as unusable (Drive footage scored ~19 → rejected). | `frame_quality.py`, `quality_gates.py` |
| **SfM / COLMAP model** | A sparse Structure-from-Motion reconstruction: camera intrinsics + per-frame extrinsics (poses) + a sparse point cloud, in COLMAP's coordinate frame. The *spatial truth* every downstream context shares. | `reconstruct`; `colmap_parser.py`, `coordinate_transform.py` |
| **GaussianSplat** | A trained 3D Gaussian Splatting model (`.ply` of Gaussians) of the whole scene, in the COLMAP frame. The dense radiance source from which meshes and renders are derived. | `train`; `gsplat_trainer.py`, `splat_optimizer.py` |
| **Object Concept** | A semantic concept proposal in the scene ("chair", "ladder") produced by open-vocabulary segmentation (SAM3). Identifies *what* objects exist and *where* in image/3D space. | `segment`; `sam3_segmentor.py` |
| **Object Crop** | A tight **RGBA** image cutout of one Object Concept (SAM mask applied to the best source Frame → transparent background). The input contract for object-mesh generation. | `extract_objects`; `sam3_segmentor.py`, `multiview_renderer.py` |
| **ObjectHull / ObjectMesh** | A single reconstructed, textured object mesh (initially a GLB) generated from its Object Crop. "Hull" = the reconstructed solid; "ObjectMesh" = the cleaned, game-ready form. | `mesh_objects`; `hunyuan3d_client.py`, `trellis2_client.py` |
| **EnvMesh / RoomMesh** | The textured polygonal mesh of the *environment* (the room/background), extracted from the GaussianSplat or COLMAP model. | `train`/mesh backend; `come_extractor.py`, `mesh_extractor.py`, `milo_extractor.py` |
| **BakedTexture (albedo / PBR)** | A UV-mapped raster texture (PNG) onto which the captured per-vertex colour (and, where available, PBR channels) has been rasterised. The thing that survives the FBX boundary. | `texture_bake`; `texture_baker.py`, `scripts/scene_texture.py` |
| **GameAsset (FBX)** | The delivered, engine-native asset: a polygonal mesh + UV + embedded BakedTexture in **FBX**, pre-transformed into UE's coordinate/unit frame. | `scripts/blender_obj_to_fbx.py` |
| **UE Scene** | The assembled Unreal Engine 5.8 level: GameAssets placed at their reconstructed poses, optionally with a companion GaussianSplat. The delivered experience. | UE overlay (`unreal/`), UE MCP bridge |
| **Lineage (`v2g:*`)** | The durable provenance chain Video → Frame → Object → Mesh → Asset, carried as `v2g:*` metadata (e.g. `v2g:hull_glb`, `v2g:hull_backend`, `v2g:hull_vertices`, `v2g:confidence`, `v2g:pipeline_version`). | `stages.py`, `manifest.py`, mirrored to UE tags |

**Note on the word "hull".** Historically "hull" meant a convex/approximate object solid.
In the current contract it denotes the *full reconstructed object mesh* from Hunyuan3D-2.1
(textured GLB), not a convex hull. Treat ObjectHull ≡ ObjectMesh.

---

## 2. Bounded Contexts

Seven bounded contexts, each owning a phase of the lineage. The orchestrator
(`stages.py`) is the *integrating host* that threads them together; it is not itself a
domain context but the application service layer that sequences them.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Vitrine mesh-pipeline context map  (one-way lineage flow, left → right)        │
│                                                                                │
│  ┌────────────┐   ┌─────────────────┐   ┌──────────────┐                        │
│  │ Ingest&QA  │──▶│ Reconstruction  │──▶│ Segmentation │─────────┐             │
│  │ (CORE)     │   │ SfM + 3DGS CORE │   │ (CORE)       │         │ crops       │
│  └────────────┘   └───────┬─────────┘   └──────────────┘         ▼             │
│       frames               │ splat                       ┌────────────────────┐│
│                            │                             │ Object-Mesh-Gen    ││
│                            │ splat/colmap                │ (Hunyuan3D) CORE   ││
│                            ▼                             └─────────┬──────────┘│
│                   ┌──────────────────┐                            │ obj meshes │
│                   │ Env-Mesh-Extract │                            │            │
│                   │ (CoMe/TSDF) SUPP │── room mesh ──┐            │            │
│                   └──────────────────┘               ▼            ▼            │
│                                              ┌─────────────────────────┐       │
│                                              │ Texturing (xatlas bake) │       │
│                                              │ (SUPPORTING)            │       │
│                                              └────────────┬────────────┘       │
│                                                 textured OBJ + albedo PNG       │
│                                                           ▼                     │
│                                              ┌─────────────────────────┐       │
│                                              │ UE-Assembly (GENERIC)   │       │
│                                              │ FBX export → UE 5.8     │       │
│                                              └─────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────────┘
```

| # | Bounded Context | Type | Responsibility | Code home (`src/pipeline/` unless noted) |
|---|---|---|---|---|
| 1 | **Ingest & QA** | Core | Decode Video → Frames; score FrameQuality; apply the MUSIQ gate; emit clean frame set + lineage roots. | `stages.py::ingest/remove_people/select_frames`, `frame_quality.py`, `quality_gates.py`, `frame_selector.py`, `drive_ingestor.py` |
| 2 | **Reconstruction (SfM + 3DGS)** | Core | Frames → COLMAP model → GaussianSplat. Owns the canonical spatial frame. | `stages.py::reconstruct/train`, `colmap_parser.py`, `coordinate_transform.py`, `gsplat_trainer.py`, `splat_optimizer.py` |
| 3 | **Segmentation** | Core | Splat/Frames → Object Concepts → RGBA Object Crops. Decides *what* objects to reconstruct. | `stages.py::segment/extract_objects`, `sam3_segmentor.py`, `mask_projector.py`, `multiview_renderer.py` |
| 4 | **Object-Mesh-Generation** | Core | Object Crop → textured ObjectMesh (GLB). SOTA generative reconstruction (Hunyuan3D-2.1 primary; TRELLIS.2 alt). | `stages.py::mesh_objects`, `hunyuan3d_client.py`, `trellis2_client.py`, `scripts/hy3d_one.py`, `scripts/hy3d_turnaround.py`, `scripts/hy3d_batch.sh` |
| 5 | **Env-Mesh-Extraction** | Supporting | Splat/COLMAP → textured RoomMesh. Pluggable backends (CoMe → MILo → GaussianWrapping → TSDF fallback). | `come_extractor.py`, `mesh_extractor.py` (TSDF), `milo_extractor.py`, `gaussianwrapping_extractor.py`, `mesh_cleaner.py` |
| 6 | **Texturing** | Supporting | Mesh + captured vertex colour → UV atlas + BakedTexture (albedo PNG) → textured OBJ. **Enforces the bake invariant.** | `texture_baker.py`, `mesh_cleaner.py`, `scripts/scene_texture.py`, `material_assigner.py` |
| 7 | **UE-Assembly** | Generic | Textured OBJ → coordinate-baked **FBX GameAsset** → placed in UE 5.8 Scene. | `scripts/blender_obj_to_fbx.py`, `unreal/runtime/*`, UE MCP bridge (`:9100`) |

**Why these splits.** Each boundary is where the *language* and the *artifact contract*
change: Ingest speaks Frames/quality; Reconstruction speaks poses/Gaussians; Segmentation
speaks concepts/masks; the two mesh contexts speak geometry; Texturing speaks UV/raster;
UE-Assembly speaks engine assets. Crossing a boundary always means a model translation
(see §5 ACLs).

---

## 3. Aggregates, Entities & Value Objects (per context)

Convention: **AR** = aggregate root, **E** = entity (identity matters), **VO** = value
object (immutable, equality by value).

### 3.1 Ingest & QA

- **Capture / Video** (AR) — root of a lineage tree; owns its Frames and the QA verdict for
  the whole clip.
  - **Frame** (E) — identity = `(video_id, pts)`. Holds path + source back-pointer.
  - **FrameQuality** (VO) — `{musiq, blur_variance, coverage, recommendation∈{keep,marginal,drop}}`.
  - **CaptureSession** (VO) — capture-time context (`source_video`, `capture_session`, `source_timestamp_pts`).
  - *Invariant:* a Frame may only advance to Reconstruction if its FrameQuality ≥ gate, and
    its Video is not flagged unusable.

### 3.2 Reconstruction (SfM + 3DGS)

- **ColmapModel** (AR) — the sparse SfM solution; owns cameras, poses, sparse points.
  - **CameraPose** (E) — per-frame extrinsic; identity = frame_id.
  - **CameraIntrinsics** (VO) — `width,height,fx,fy,cx,cy` (`mesh_extractor.CameraIntrinsics`).
  - **CoordinateFrame** (VO) — up-axis, metres-per-unit, COLMAP→world transform (`coordinate_transform.py`).
- **GaussianSplat** (AR) — the trained `.ply` of Gaussians; owns the dense scene appearance.
  - *Invariant:* GaussianSplat and every derived mesh share the **one** COLMAP CoordinateFrame; no
    context re-solves poses.

### 3.3 Segmentation

- **SceneSegmentation** (AR) — the set of Object Concepts found in one scene.
  - **ObjectConcept** (E) — identity = stable `label`; carries class + per-frame masks + a 3D footprint.
  - **ObjectCrop** (VO) — an RGBA cutout `{label, source_frame, rgba_png, bbox}`; the *only* output that
    leaves this context toward Object-Mesh-Generation.
  - *Invariant:* a Crop's alpha matte isolates exactly one Concept; background is transparent (so the
    generator never reconstructs the room into the object).

### 3.4 Object-Mesh-Generation

- **ObjectMesh** (AR) — one reconstructed, textured object (GLB → cleaned OBJ).
  - **MeshGeometry** (VO) — `{vertices, faces, normals}`.
  - **HullProvenance** (VO) — `{hull_backend, hull_vertices, hull_faces, view_synth, confidence}`
    (the `v2g:hull_*` set).
  - *Invariant:* an ObjectMesh is always traceable to exactly one ObjectConcept/Crop (1 Concept → 1 Mesh).

### 3.5 Env-Mesh-Extraction

- **EnvMesh / RoomMesh** (AR) — the environment mesh + the backend that produced it.
  - **MeshGeometry** (VO) — shared shape with §3.4.
  - **VertexColour** (VO) — per-vertex captured colour carried out of TSDF/CoMe (the colour that *must*
    later be baked).
  - **MeshBackend** (VO) — `{come|milo|gaussianwrapping|tsdf}` with selection precedence.
  - *Invariant:* RoomMesh stays in the COLMAP CoordinateFrame until UE-Assembly bakes the transform.

### 3.6 Texturing

- **TexturedMesh** (AR) — a mesh that now owns a UV atlas + a BakedTexture.
  - **UVAtlas** (VO) — xatlas-generated UV layout (`_generate_uv_atlas_xatlas`).
  - **BakedTexture** (VO) — the albedo (and optional PBR) PNG raster `{path, size, padding}` (`BakeConfig`).
  - *Invariant (the central one):* a TexturedMesh exists **iff** its captured vertex colour has been
    rasterised into a UV-mapped BakedTexture. See §6.

### 3.7 UE-Assembly

- **GameAsset** (AR) — the FBX delivered to UE; owns geometry + embedded texture + the baked transform.
  - **WorldTransform** (VO) — COLMAP→UE matrix with the m→cm scale folded in (`×0.01` in
    `blender_obj_to_fbx.py`, so FBX's m→cm export lands in UE centimetres).
  - **AssetLineage** (VO) — `v2g:*` provenance mirrored onto UE tags.
- **UEScene** (AR) — the assembled level: placed GameAssets (+ optional companion GaussianSplat).
  - *Invariant:* a GameAsset carries an *embedded* texture (FBX `embed_textures=True`, `path_mode='COPY'`);
    UE must never have to resolve vertex colours (it can't — §6).

---

## 4. Domain Events / Pipeline Flow

The pipeline is an event-ordered lineage. Each event is the published fact that lets the
next context begin. Stage names below match `stages.py::STAGE_NAMES`.

```
VideoIngested                 (ingest)            Video → Frames + lineage root
PeopleRemoved                 (remove_people)     Frames cleaned of transient humans
FramesAdmitted                (select_frames)     MUSIQ gate applied → keep-set  ◀ GATE
SfmSolved                     (reconstruct)       Frames → ColmapModel (poses + sparse pts)
SplatTrained                  (train)             ColmapModel → GaussianSplat (+ RoomMesh side-product)
PreviewsRendered              (render_previews)   orbit renders for QA/inspection
SceneSegmented                (segment)           Splat/Frames → ObjectConcepts
ObjectsCropped                (extract_objects)   Concepts → RGBA ObjectCrops
   ├─ ObjectMeshGenerated     (mesh_objects)      Crop → textured ObjectMesh (GLB)   [Hunyuan3D]
   └─ EnvMeshExtracted        (train/backend)     Splat/COLMAP → RoomMesh            [CoMe/TSDF]
TexturesBaked                 (texture_bake)      Mesh + vertex colour → UV + albedo PNG  ◀ BAKE INVARIANT
GameAssetsExported            (—, FBX script)     textured OBJ → FBX (transform baked)
UESceneAssembled              (—, UE overlay)     FBX placed in UE 5.8 (+ optional splat)
```

The two mesh tracks (`ObjectMeshGenerated`, `EnvMeshExtracted`) run in parallel and **rejoin
at `TexturesBaked`**. Both tracks must pass the bake invariant before any FBX export.

**Lineage carried through every event:** each artifact keeps `v2g:*` provenance so the final
GameAsset can be traced back to its Video/Frame/Concept (`v2g:hull_glb`, `v2g:hull_backend`,
`v2g:hull_vertices`, `v2g:hull_faces`, `v2g:confidence`, `v2g:view_synth`, `v2g:pipeline_version`,
`v2g:up_axis`, `v2g:meters_per_unit`, `v2g:object_count`).

---

## 5. Anti-Corruption Layers (external-tool boundaries)

Every heavy external tool gets an ACL: a thin adapter that translates the tool's wire/file
model into our domain model, so the tool's quirks never leak inward. These are the four
real seams.

| External system | ACL adapter | Translation it performs | Quirks it absorbs |
|---|---|---|---|
| **ComfyUI** (Hunyuan3D-2.1 / TRELLIS.2 / FLUX.2 / SAM) | `hunyuan3d_client.py`, `trellis2_client.py`, `comfyui_control.py`, `scripts/hy3d_one.py` | ObjectCrop → upload → graph prompt → poll history → download GLB → `ObjectMesh`. | HTTP prompt/poll lifecycle; output paths (`output/dreamlab/*_hull_*.glb`); crash vs. busy disambiguation (exit codes `3`=down/retry, `4`=reject/timeout); serial VRAM `/free` (FLUX.2 cannot co-reside with TRELLIS.2 on 48 GB). |
| **COLMAP** | `colmap_parser.py`, `coordinate_transform.py`, `stages.py::_run_colmap_direct` | COLMAP binary DB/text model → `ColmapModel` (CameraPose + CameraIntrinsics + CoordinateFrame). | COLMAP's coordinate convention; sparse-dir discovery; SIFT-vs-ALIKED feature path. |
| **Blender** | `scripts/blender_obj_to_fbx.py`, `blender_assembler.py` | textured OBJ (+ mtl + `map_Kd`) → coordinate-baked, texture-embedded **FBX** GameAsset; Cycles GPU colour bake where vertex colours must be re-projected. | `bpy` import API drift (`wm.obj_import` vs `import_scene.obj`); FBX m→cm scaling; `transform_apply`; `embed_textures`/`path_mode='COPY'`. |
| **UE MCP** (UE 5.8) | `mcp_client.py`, `unreal/runtime/mcp_bridge.py` (`:9100`), Web Remote Control `:30010` | FBX GameAsset + pose → imported UE asset + placed actor; `v2g:*` → UE tags. | UE control transports (Remote Control unicast primary, first-party MCP `:8000` experimental); UE dropping vertex colours / `customData` on import (§6). |

Secondary external seams handled by their own clients but not on the core mesh→UE path:
SAM3 (`sam3_segmentor.py`), Drive/rclone (`drive_ingestor.py`), pyiqa/MUSIQ (`frame_quality.py`),
CoMe/MILo/GaussianWrapping sidecars (`come_extractor.py`, `milo_extractor.py`,
`gaussianwrapping_extractor.py`) — each is its own ACL into the sidecar's CLI/file contract.

---

## 6. The bake invariant (the load-bearing rule)

> **Captured colour MUST be baked into a UV-mapped raster texture before a mesh crosses into
> Unreal Engine. UE drops per-vertex colours (and the baked-USD importer drops `customData`),
> so any colour that lives only on vertices is lost at the FBX/UE boundary.**

Consequences enforced across contexts:

- **Texturing is mandatory, not optional.** No mesh — RoomMesh or ObjectMesh — may reach
  UE-Assembly with colour stored only as `vertex_colors`. `scripts/scene_texture.py` is the
  canonical realisation: `MeshCleaner.clean()` (decimate so xatlas behaves;
  **smoothing disabled** because smoothed degenerate tris crash xatlas) → re-attach vertex
  colours by nearest-neighbour if cleaning dropped them →
  `TextureBaker.bake_from_vertex_colors()` (xatlas UV atlas + rasterise into a 2048² albedo PNG
  with padding/dilation) → export `room_textured.obj` + `room_albedo.png`.
- **FBX must embed the texture.** `blender_obj_to_fbx.py` exports with `embed_textures=True`
  and `path_mode='COPY'`; UE never resolves an external/vertex colour source.
- **Where the bake collapses, fall back to splat.** On large/thin room meshes (e.g. MILo room
  geometry) the bake can collapse; for those scenes ship the companion **GaussianSplat** render
  instead of (or alongside) a baked RoomMesh — the "gaussian-in-UE optional" escape hatch.

This invariant is the reason Texturing is its own bounded context rather than a step folded
into Env/Object mesh extraction: it is the single guard that protects the UE boundary.

---

## 7. Context-mapping patterns

| Relationship | Pattern | Rationale |
|---|---|---|
| Ingest&QA → Reconstruction | Customer–Supplier | Reconstruction's needs (sharp, well-distributed frames) define the QA gate. |
| Reconstruction → (Segmentation, Env-Mesh, Object-Mesh) | Shared Kernel (CoordinateFrame) | All consumers share the one COLMAP frame; nobody re-solves poses. |
| Segmentation → Object-Mesh-Generation | Customer–Supplier (ObjectCrop = published contract) | The RGBA Crop is the agreed interface; the generator knows nothing of SAM internals. |
| {Object-Mesh, Env-Mesh} → Texturing | Conformist (both conform to TexturedMesh) | Texturing imposes one UV/bake contract on both mesh sources. |
| Texturing → UE-Assembly | Open Host Service (FBX) | FBX + embedded albedo is the published, engine-native language. |
| Pipeline ↔ ComfyUI / COLMAP / Blender / UE | Anti-Corruption Layer | §5 — external tools never leak their model inward. |

---

## 8. Mapping summary: context → code home

```
Ingest & QA               → stages.py (ingest, remove_people, select_frames)
                            frame_quality.py, quality_gates.py, frame_selector.py, drive_ingestor.py
Reconstruction (SfM+3DGS) → stages.py (reconstruct, train)
                            colmap_parser.py, coordinate_transform.py, gsplat_trainer.py, splat_optimizer.py
Segmentation              → stages.py (segment, extract_objects)
                            sam3_segmentor.py, mask_projector.py, multiview_renderer.py
Object-Mesh-Generation    → stages.py (mesh_objects)
                            hunyuan3d_client.py, trellis2_client.py
                            scripts/hy3d_one.py, scripts/hy3d_turnaround.py, scripts/hy3d_batch.sh
Env-Mesh-Extraction       → come_extractor.py, mesh_extractor.py (TSDF), milo_extractor.py,
                            gaussianwrapping_extractor.py, mesh_cleaner.py
Texturing (xatlas bake)   → texture_baker.py, mesh_cleaner.py, material_assigner.py
                            scripts/scene_texture.py
UE-Assembly               → scripts/blender_obj_to_fbx.py, mcp_client.py
                            unreal/runtime/* (mcp_bridge.py, import_*.py)
Orchestrator (host)       → stages.py::PipelineStages (sequences all of the above)
```

---

## 9. Relationship to prior docs

- Supersedes (for UE delivery) `research/decisions/ddd-domain-model.md`, whose Assembly
  context targeted a USD scenegraph. This document drops USD from the delivered contract and
  adds the Texturing and UE-Assembly contexts plus the bake invariant.
- Aligns with: ADR-003 (pluggable mesh backends), ADR-015 (object-reconstruction SOTA refresh
  → Hunyuan3D-2.1), ADR-016 (Unreal scenegraph export — now FBX-asset-oriented for the mesh
  path), ADR-018 (Unreal exhibit builder).
