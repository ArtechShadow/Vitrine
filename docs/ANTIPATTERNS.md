# ANTIPATTERNS — proven dead-ends (do not retry)

Warning breadcrumbs for the Vitrine video→mesh→UE pipeline. Each entry is a path that
was **tried and failed**; the one-liner is the reason + the thing to do instead. Keep
this list when you delete dead code so nobody walks the same wall twice.
Last updated 2026-06-22 (mesh-into-UE end-state; USD dropped from the critical path).

## Getting captured colour into Unreal Engine
- **Vertex colours into UE (FBX *or* OBJ *or* GLB `COLOR_0`) → flat white.** UE's
  importers drop vertex colours. **Bake captured colour to a UV texture** and import an
  FBX/OBJ with a baked-texture material. *(Removed `unreal/runtime/build_room_ue.py`,
  which assigned a `M_VColor` VertexColor material → white room. Use a baked-texture FBX
  + `import_materials=True` instead.)*
- **LichtFeld native USD → UE.** Native export emits a `ParticleField`/gaussian prim UE
  **cannot import as a mesh**; UE USD import also drops `displayColor` + `customData`.
  USD is optional/archival only — import meshes (FBX) directly. *(ADR-019)*
- **UE `import_file` on `.glb` → rejected** ("FbxFactory does not support .glb. Allowed:
  fbx, obj"). Convert GLB/OBJ → **FBX** (`scripts/blender_obj_to_fbx.py`, embeds texture).

## Meshing & texturing
- **`open3d compute_uvatlas` / `xatlas` on a raw TSDF (non-manifold) mesh → crash.** They
  need a manifold mesh. The working path: `texture_baker.bake_from_vertex_colors` (xatlas)
  on a **decimated** mesh.
- **`MeshCleaner.clean(smooth_iterations>0)` before an xatlas bake → segfault.** Laplacian
  smoothing makes degenerate tris that crash xatlas. **Pass `smooth_iterations=0`** (the
  default is 3). *(scripts/scene_texture.py pins it to 0.)*
- **Blender Smart-UV-Project on a room-scale marching-cubes mesh → near-black atlas.** Many
  thin/disconnected components collapse to sub-texel UV islands. Use the xatlas
  `texture_baker` path for the room; bake clean **watertight hulls** only with Blender.
- **`trimesh.split()` + `concatenate()` for large meshes → hangs at ~1.8M verts.** Use
  `trimesh.graph.connected_components` + an explicit vertex-colour index remap.

## Object reconstruction (Hunyuan3D / ComfyUI)
- **Orbit-render isolated per-object gaussians as hull input.** Partial captures give ~1
  non-empty view → the model hallucinates the rest. **Feed the SAM image crop (RGBA).**
- **Naive ComfyUI-direct heavy calls / no restart between objects.** The Hy3D extension
  crashes the server after ~1-2 objects (VRAM) and the dinov2 image-processor load fails on
  stale state. **Restart ComfyUI per object** (`scripts/hy3d_batch.sh` does this) + poll on
  a long deadline (big-mesh bakes take hours; the GLB file is the completion signal, not a
  short `/history` timeout).
- **Stock `ImageOnlyCheckpointLoader` for Hy3D.** Reads empty `checkpoints/`. Symlink the
  DiT/VAE into the scanned folder; old Hunyuan3D-2.0 8-node workflows are shape-only.

## Quality / perf
- **Pruning gaussians (`--enable-sparsity`) for a perf target.** Spiked loss, over-thinned
  4M→1.6M, didn't fix haze. Keep gaussians **unpruned**; solve poly budget on the mesh via
  **UE Nanite**. (`--resume` is config-sticky — needs a fresh run to change strategy.)
- **Reimplementing in CPU Python what has a GPU path** (per-texel PIL rasteriser, numpy
  TSDF). Grep `src/pipeline/` + `scripts/` first — bake/TSDF/render all have GPU paths.

## Unreal / infra
- **`-run=pythonscript` / `-ExecutePythonScript` for UE GPU render → NullDrv (no GPU).** Use
  a persistent `UnrealEditor` on Xvfb + `-ExecCmds="py ..."`.
- **Agent-side `docker build` → read-only `~/.docker`, wrong daemon.** Build on the host via
  `tmux agentbox:host` (fish shell). *(see memory `host-access-and-build-topology`)*
- **`comfyui-sam3dobjects/vendor/cv2` shim → SIGSEGV on 4096px PBR inpaint.** Disable it
  before ComfyUI starts (entrypoint step 1d).
- **rclone build failure misread as network.** It's the `RCLONE_VERSION`→`--version` flag
  collision; egress is fine. Use `env -u RCLONE_VERSION`.
