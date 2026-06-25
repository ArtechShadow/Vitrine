# Splat-hero (Opt-4) — NanoGS in UE 5.8 handoff

The splat half of the dreamlab Opt-4 deliverable: render the **LichtFeld-native 4M-gaussian splat** as
real Gaussians in UE 5.8 via the **NanoGS** plugin (MIT), replacing the blocky LiDAR-point-cloud hack.
This is also *campaign step 3* (lean-on-LichtFeld) — the room ships from LichtFeld's own trainer output.

## What's staged (done, agent side)
- **Splat source:** `output/dreamlab/model/splat_30000.ply` — LichtFeld-native, standard 3DGS .ply
  (4,000,000 verts; x/y/z, f_dc, f_rest SH, opacity, scale, rot). 992 MB.
- **Plugin:** `unreal/runtime/Plugins/NanoGS/NanoGS.uplugin` (flattened to UE-project layout).
  Modules: `NanoGS` (Runtime, PostConfigInit) + `NanoGSEditor` (Editor). Source/Shaders/Resources present.
  Reference docs in `Plugins/NanoGS/_ref/` (Achitecture.txt, README, a TestPLYFile).

## UE 5.8 recompile — DONE (2026-06-25)
NanoGS advertised UE 5.6/5.7 only; **recompiled for UE 5.8 successfully** in the `vitrine-unreal` container
(installed engine `/opt/ue`, bundled clang-20). Result: `Result: Succeeded`, both modules linked.
- **One source fix:** `Source/NanoGS/Public/GaussianClusterBuilder.h` — removed an in-class default arg
  `= FBuildSettings()` (clang-20 rejects it; the struct has default member initializers) and added a 2-arg
  overload whose inline body supplies it (member-function context is allowed). Resolved all 10 errors.
- **No real UE 5.8 API breaks** — the view-matrix deprecations (GetViewProjectionMatrix→GetWorldToClip,
  GetProjectionMatrix→GetViewToClip) compiled as non-fatal warnings (module doesn't set warnings-as-errors).
- **Binaries delivered to the repo:** `unreal/runtime/Plugins/NanoGS/Binaries/Linux/`
  (`libUnrealEditor-NanoGS.so` 785KB + `libUnrealEditor-NanoGSEditor.so` 157KB + sidecars). Plugin enabled
  in `Vitrine.uproject`. **Build a writable copy** (`/vitrine/unreal` is read-only in the container; build at
  `/tmp/nanogs-build`).
- Known runtime caveat to watch at render time: **TSR ghosting on near-transparent splats → switch AA to FXAA**.

### Remaining: validate the render (needs an editor relaunch)
The live editor (PID 1) runs from a `/tmp/vitrine-proj` copy made *before* NanoGS existed, so it can't load the
plugin yet. To validate: **restart the `vitrine-unreal` container** (entrypoint re-copies the repo project —
now with NanoGS + binaries — to `/tmp/vitrine-proj` and relaunches the editor), then smoke-test with the
bundled `Plugins/NanoGS/_ref/TestPLYFile/Llama.ply`, then NanoGS-import `room_clean.ply` and render.

## Pre-clean the splat — DONE (agent side)
`scripts/splat_clean.py` (scripted SuperSplat substitute: opacity>0.10 + spatial statistical-outlier
removal, all gaussian attributes preserved) produced the import-ready file:
- **`output/dreamlab/locked/splat_hero/room_clean.ply`** — **2,475,366 gaussians** (62% of 4.0M kept;
  dropped low-opacity haze + isolated floaters). This is the file to NanoGS-import.
- Optional further polish: **SuperSplat** (https://superspl.at/editor) for manual box-crop of ceiling/edge
  junk, or **SplatTransform** (`npx @playcanvas/splat-transform`) for decimation / `.ply`↔`.spz`/`.sog`.

## In-editor workflow (after recompile)
1. NanoGS **Import** button → pick the cleaned `.ply` → creates a *Gaussian Splat Asset*.
2. Drag the asset into the level. Toggle Nanite via asset action. Tune SH Order / Opacity Scale / Splat Scale.
3. Embed the **TRELLIS.2 object FBXs** (chair / vacuum / toolbox) in the same level — those are the polygonal
   meshes that satisfy the design mandate. Add a hidden low-poly room proxy for collision (Opt-2 idiom).

## Why this over the LiDAR point cloud
NanoGS renders the actual Gaussians (Nanite-style LOD + GPU radix sort, scales to millions), not sparse
colored points — directly answers "a point cloud render is certainly not correct." Fallback if NanoGS
chokes on 5.8 or splat count: **MLSLabs Renderer** (Apache-2.0, custom DX12, 5M+ splats @50fps).
