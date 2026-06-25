# Gaussian-to-Mesh Extraction Methods

## Taxonomy

```mermaid
graph TD
    A[Mesh Extraction from Gaussians] --> B[Post-Hoc<br/>Any trained model]
    A --> C[Integrated<br/>Requires training modification]

    B --> B1[Poisson Reconstruction<br/>SuGaR]
    B --> B2[Marching Tetrahedra<br/>GOF / SOF]
    B --> B3[TSDF Fusion<br/>Depth render → MC]
    B --> B4[Stereo Depth Fusion<br/>GS2Mesh]

    C --> C1[Differentiable Mesh-in-Loop<br/>MILo, MeshSplatting]
    C --> C2[2D Gaussian Surfaces<br/>2DGS, PGSR]

    B1 --> T{Textured / USD color}
    B2 --> T
    B3 --> T
    C1 --> T
    T -->|clean watertight HULL| H[UV atlas + Cycles GPU bake<br/>→ textured GLB/USD]
    T -->|room/scene-scale mesh| S[UV-atlas bake COLLAPSES<br/>→ direct gsplat splat render]
```

> **Caveat (L2, 2026-06-21 e2e run):** the "UV-atlas → bake Gaussian color"
> route to a textured, USD-ready mesh only holds for **clean watertight hulls**.
> On **room-scale MILo meshes** Smart UV Project collapses (many
> thin/disconnected components — 876 removed on scene02 — yield degenerate
> near-zero-area UV islands → a near-black 2048² atlas), so the bake is
> **hull-only**. The highest-fidelity captured scene color is a **direct gsplat
> splat render**, not a baked mesh texture.

## Method Comparison

| Method | Type | Texture | UV Maps | Quality | Speed | Post-hoc | C++ Portable |
|--------|------|---------|---------|---------|-------|----------|--------------|
| **SuGaR** | Poisson | Diffuse | Yes | Good | 30 min | Yes | Yes (libs) |
| **SOF** | March.Tet. | Vertex | No | Excellent | 10 min | Yes | Yes |
| **GOF** | March.Tet. | Vertex | No | Very Good | 20 min | Yes | Yes |
| **TSDF** | Depth fusion | Vertex | No | Good | 5 min | Yes | Yes |
| **GS2Mesh** | Stereo | Vertex | No | Good | 15 min | Yes | Partial |
| **MILo** | Differentiable | Joint | Yes | Excellent | Training | No | No |
| **MeshSplatting** | Direct | Vertex | No | Very Good | Training | No | No |
| **2DGS** | TSDF | Vertex | No | Very Good | Training | No | No |

## Recommended Methods

### Primary: SuGaR (UV-Mapped Textured Meshes)

**Why**: Only method producing OBJ with UV-mapped diffuse textures from Gaussians. Direct compatibility with USD `UsdPreviewSurface` materials and standard rendering pipelines.

**Process**:
1. Surface alignment: regularise Gaussians to lie on surfaces
2. Poisson reconstruction: extract watertight mesh
3. Gaussian binding: re-bind Gaussians to mesh faces
4. UV mapping: auto-parameterise via Nvdiffrast
5. Texture baking: project SH colours onto UV atlas

**Quality**: Good geometry, excellent textures. Tends to over-smooth fine details (trade-off of Poisson reconstruction).

**Output**: `.obj` with `.mtl` and diffuse texture `.png`

> **Scale caveat (L2):** the UV-map → texture-bake step (steps 4–5) only
> survives on **clean watertight meshes (hulls)**. On room/scene-scale meshes
> with many thin/disconnected components the UV unwrap (Smart UV Project /
> xatlas-equivalent) produces degenerate near-zero-area islands and the baked
> atlas comes out near-black — see the Texture-baking caveat below. For
> scene-scale captured color, render the Gaussians directly rather than baking.

### Alternative: SOF/GOF (Best Geometric Accuracy)

**Why**: Highest geometric fidelity via Marching Tetrahedra on opacity fields. SOF is 10x faster than GOF with better detail preservation.

**Process**:
1. Evaluate Gaussian opacity field on adaptive tetrahedral grid
2. Extract isosurface via Marching Tetrahedra
3. Output vertex-coloured mesh

**Quality**: Excellent geometry, especially on unbounded scenes. No UV maps — requires separate texture baking.

**Texture baking** (post-SOF/GOF):
1. Generate UV atlas with xatlas
2. Render Gaussian SH colours from multiple viewpoints
3. Project rendered colours onto UV coordinates
4. Composite into diffuse texture atlas

> **Room-scale failure mode (L2, 2026-06-21):** steps 1–4 assume the input is a
> clean, mostly-connected surface. On room-scale MILo meshes the UV unwrap
> (Smart UV Project / xatlas) **collapses** — many thin/disconnected components
> (876 removed on scene02) map to degenerate near-zero-area UV islands, so the
> 2048² atlas bakes near-black. This bake is reliable on **watertight object
> hulls only**. For the room/scene itself, the highest-fidelity captured color
> is a **direct gsplat splat render**, not a baked mesh texture.
>
> **GPU-preferred (L8):** the bake itself must run on GPU — Blender **Cycles
> DIFFUSE GPU bake** (`blender_assembler.py` `bake_vertex_colors_to_texture()`,
> ~0.5 s / 100k faces), never a CPU PIL/`numpy` per-face loop. Any CPU baking
> path is a defect to replace.

### Fallback: TSDF Fusion (Simplest)

**Why**: Minimal implementation complexity. Uses existing Gaussian rasteriser.

**Process**:
1. Render depth maps from 32-64 viewpoints using LichtFeld
2. Fuse into TSDF volume (Open3D `ScalableTSDFVolume`)
3. Extract mesh via Marching Cubes
4. Clean: remove disconnected components, smooth, decimate

**Quality**: Lower than SuGaR/SOF but reliable. Good enough for background environment meshes.

> **GPU-preferred (L8):** the Open3D `ScalableTSDFVolume` path above is
> **CPU/`numpy`** and should be treated as a last-resort fallback. Prefer GPU
> extraction — **MILo `radegs` (GPU)** — over a CPU numpy TSDF; a CPU path here
> is a defect to replace. (Step 1 depth render is already GPU via LichtFeld;
> keep video decode on GPU upstream too.)

## Integration with LichtFeld Studio

### Current State
- **mesh2splat** (EA, BSD-3): Integrated in `src/rendering/mesh2splat.cpp`. Converts mesh → Gaussians.
- **Mesh import**: Assimp loader for OBJ/FBX/glTF/GLB/STL/DAE
- **Mesh processing**: OpenMesh half-edge operations, decimation
- **Scene graph**: `NodeType::SPLAT` and `NodeType::MESH` node types
- **USD export**: `ParticleField3DGaussianSplat` prims (no mesh prims yet)

### Missing
- Splat → Mesh conversion (the inverse of mesh2splat)
- Mesh USD export (`UsdGeomMesh` prims)
- Per-object mesh extraction workflow

### Recommended Integration Path

**Phase 1**: TSDF fallback (use existing depth rendering + Open3D)
**Phase 2**: SuGaR integration (Python, callable from MCP)
**Phase 3**: SOF port to C++/CUDA (native LichtFeld integration)
**Phase 4**: MILo/MeshSplatting-style joint training (long-term)

## Round-Trip Validation

Use EA's mesh2splat to validate mesh quality:

```
Gaussians → SuGaR → Mesh → mesh2splat → Gaussians'
Compare render(Gaussians) vs render(Gaussians')
If PSNR(Gaussians, Gaussians') > 30: mesh is faithful
```

This closed-loop validation confirms the mesh preserves the visual appearance of the original Gaussian representation.
