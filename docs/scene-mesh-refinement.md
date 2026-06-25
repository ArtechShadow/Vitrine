# Scene-mesh refinement & the ArtiFixer recon-enhancement trial

This session pushed two parallel levers on the **dreamlab/locked** scene mesh: (A) a
finer-voxel CoMe TSDF refinement campaign — many backend attempts, one stable success,
and an honest verdict that geometry resolution is *not* the binding constraint; and (B)
standing up the gated **ArtiFixer** recon-enhancement branch (ADR-020), whose **prepare
stage is currently running** with no enhanced result yet. Both are written here as a
consolidated, accurate engineering record — in-progress work is marked as such.

> Cross-links: [`docs/engineering-log.md`](./engineering-log.md) ·
> [`research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md`](../research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md) ·
> [`docs/artifixer-recon-enhancement.md`](./artifixer-recon-enhancement.md)

---

## Goal

The campaign goal (set 2026-06-24): **keep experimenting** — across source data, the
pipeline, component technology, settings, and in-flight evaluations — **until we have a
FAIR textured room in Unreal plus at least TWO good interactive objects (one EXCELLENT)**;
then attempt to reach the same quality leaning on the capabilities exposed by LichtFeld
Studio (the vendored 3DGS tool at `vendor/lichtfeld-studio`).

This document covers the **room/scene-mesh** half of that goal. The objects path
(SAM crop → Hunyuan3D-2.1) is tracked separately. The scene is the **dreamlab/locked**
capture: 750 frames, **motion-blur-limited** (MUSIQ ~31), with partial coverage. The
scene mesh is produced by **CoMe** (which trains its own 3DGS, then a TSDF mesh).
Hardware: 2× RTX 6000 Ada (48 GB, sm_89, 200 W-capped), 251 GB host RAM.

---

## Part A — CoMe finer-voxel scene mesh: approaches, issues, results

### Why touch the baseline at all

The shipped baseline scene mesh was extracted at **voxel 0.015** with Open3D's tensor
`VoxelBlockGrid` on CUDA → ~3.2M faces. **0.015 was itself an OOM-forced compromise**: a
prior **voxel 0.002** attempt OOM'd at frame 7/750 because the upstream
`extract_mesh_tsdf.py` hardcodes `VoxelBlockGrid` on `cuda:0` with `block_count=50000`, so
a fine voxel rehashes past 48 GB VRAM. The work in this session aimed to get **finer
geometry**, **use both GPUs**, and **get around the OOM**.

### Approaches, in order

| # | Backend + config | Outcome | Root cause |
|---|---|---|---|
| 1 | Open3D tensor `VoxelBlockGrid`, **CPU volume**, `block_resolution=16`. voxel **0.005** / `block_count` 250k; then voxel **0.0035** / cap 600k | SEGFAULT mid-`integrate` — frame **648/750**, then frame **203/750** | Open3D `block_count` is a **hard pre-allocated cap** (not grow-on-demand); overflow corrupts the hash backend. **Not OOM** — 165 GB RAM free at crash. |
| 2 | Same tensor API, CPU volume, **`block_resolution=8`** (8× cheaper blocks) + big caps. voxel **0.004** / cap 8M; then voxel **0.006** / cap 4M | SEGFAULT mid-`integrate` (frame 618); then `integrate` reached `active_blocks=735,967` of 4M cap (**18.4 %**) and SEGFAULT **inside `extract_triangle_mesh()`** | **Not capacity** — crash at 18.4 % cap utilisation, in the extract step. |
| 3 | **CUDA** + res8 + sized caps (back to the tested backend). voxel **0.005** / cap 1.5M; then voxel **0.006** / cap 1.0M | `integrate` succeeded both times (`active_blocks=1,074,138` = 71.6 %; `active_blocks=735,967` = 73.6 %), then **ABORT inside `extract_triangle_mesh()`** both times | Both abort at extract at the **same block count** as the CPU crash → an **Open3D 0.19 `VoxelBlockGrid.extract_triangle_mesh()` size/overflow bug** (~180k+ res16-equivalent blocks). The 0.015 baseline (~29k res16 blocks) extracts fine. |
| 4 | **Legacy Open3D `ScalableTSDFVolume`** (CPU, years-hardened). voxel **0.005**; then voxel **0.007** | **SUCCESS** — no OOM, no crash (see below) | Render on GPU; fusion + extract on CPU in 251 GB host RAM; hashes 16³ voxel blocks (memory ~ surface area). This is the stable path. |

The arc is the key finding: the new tensor `VoxelBlockGrid` API is the wrong tool for a
large fine grid. The crash migrated from `integrate` (a real pre-allocated-cap overflow)
to `extract_triangle_mesh()` (a size/overflow bug that fires at the **same** block count
on **both** CUDA and CPU) — proving it is **not** a memory limit and **not** a capacity
limit, but a defect in the Open3D 0.19 tensor extract path at scale.

### The legacy-TSDF success

Switching to the legacy `pipelines.integration.ScalableTSDFVolume` (rendering still on
`cuda:0`, only fusion + extraction on CPU) cleared every failure:

| Voxel | Verts | Faces (raw) | PLY | Integrate time | Rate |
|---|---|---|---|---|---|
| **0.005** | 33.3M | **51.5M** | 2.37 GB | ~71 s | 10.5 it/s |
| **0.007** | 16.5M | **25.7M** | 1.17 GB | ~50 s | 14.8 it/s |

### Cleaning (connected-component floater removal)

`come_mesh_clean.py` / `come_clean_qa.py` use Open3D `cluster_connected_triangles`,
keeping every component **≥ 2 % of the biggest cluster's triangle count** (drops detached
floaters/islands, preserves the main body plus any substantial fragment; vertex colour
preserved).

| Voxel | Backend | Blocks at extract | Raw faces | Cleaned faces | Floaters removed | Clusters | Biggest cluster |
|---|---|---|---|---|---|---|---|
| 0.005 (new API) | CUDA res8 | 1,074,138 (71.6 %) | — | ABORT in extract | — | — | — |
| 0.006 (new API) | CUDA res8 | 735,967 (73.6 %) | — | ABORT in extract | — | — | — |
| **0.005** | **legacy** | n/a | **51.5M** | **30.4M** | **21.1M (41 %)** | 1,382,549 | 29.0M |
| **0.007** | **legacy** | n/a | **25.7M** | **15.9M** | **9.7M (38 %)** | 663,042 | 15.1M |

(For reference, the shipped **baseline** scene mesh is `room_come_clean.ply` at **2.74M
faces**, extracted at voxel 0.015.)

### QA renders (Blender Cycles, vertex colour)

Two render families were produced. The **3q** comparison decimates each candidate to
~630–665k faces so the three voxels render at comparable face budget. The **tight
main-body** render keeps only the largest connected component to frame on the room core:
baseline largest component **2.57M faces**, 0.005 largest component **557k faces**.

**Three-quarter comparison — baseline (0.015) → 0.007 → 0.005:**

| Baseline (voxel 0.015) | Finer (voxel 0.007) | Finest (voxel 0.005) |
|---|---|---|
| ![baseline 3q](/img/scene-mesh-refinement/mesh-qa-baseline-3q.png) | ![v0070 3q](/img/scene-mesh-refinement/mesh-qa-v0070-3q.png) | ![v0050 3q](/img/scene-mesh-refinement/mesh-qa-v0050-3q.png) |

**Tight main-body (largest component only) — baseline vs 0.005:**

| Baseline main body (2.57M f) | Voxel-0.005 main body (557k f) |
|---|---|
| ![baseline main](/img/scene-mesh-refinement/mesh-qa-baseline-main.png) | ![v0050 main](/img/scene-mesh-refinement/mesh-qa-v0050-main.png) |

For context, the textured baseline room delivered as a UE game asset (CoMe scene →
texture bake → FBX, UE-cm, embedded albedo):

| Room FBX 3q | Room FBX top | Room FBX 3q (alt) |
|---|---|---|
| ![fbx room 3q](/img/scene-mesh-refinement/fbx-room-3q.png) | ![fbx room top](/img/scene-mesh-refinement/fbx-room-top.png) | ![fbx room 3q2](/img/scene-mesh-refinement/fbx-room-3q2.png) |

### Verdict

**Finer voxel sharpens the observed surface but does NOT beat the capture.** All three
voxels (0.015, 0.007, 0.005) yield the **same partial, lumpy mass**. The white TSDF
"wings" — under-observed / motion-blurred silhouette noise — resolve **more sharply** at
finer voxel, **not cleaner**: finer resolution renders the noise in higher fidelity rather
than removing it. The binding constraint is the **capture** (motion blur + partial
coverage), **not** mesh resolution. The legacy `ScalableTSDFVolume` path is the right,
stable extractor; voxel choice trades face count and floater fraction but does not change
the conclusion.

---

## Part B — ArtiFixer recon-enhancement trial (ADR-020, IN PROGRESS)

> **Status: IN PROGRESS.** The prepare stage is **running now**; the enhance, distill,
> and mesh stages — and the per-scene gate verdict — are **PENDING**. No enhanced result
> has been produced yet. Nothing below should be read as a result.

### What ArtiFixer is

**ArtiFixer** (NVIDIA Spatial Intelligence Lab, SIGGRAPH 2026; arXiv 2603.00492) is an
**auto-regressive video-diffusion 3DGS refiner**. Its opacity-mixing trick keeps
**observed** pixels faithful (opacity ≈ 1) while **regenerating unobserved** regions
(opacity ≈ 0) from a strong generative prior → it removes floaters/ghosts and fills holes.
The **ArtiFixer3D** variant distills the enhanced views back into a clean **3DGRUT**
Gaussian recon. Code is Apache-2.0; weights are NVIDIA OneWay Noncommercial (fine for this
non-commercial university research).

### The critical no-deblur caveat

ArtiFixer **does not deblur.** In observed regions opacity ≈ 1, so it stays **faithful to
the blurry observed pixels**. It targets the project's **secondary** problem — noisy/holey
**under-observed** regions — **not** dreamlab's **dominant** motion-blur limit. This is
exactly why ADR-020 makes it a **per-scene GATED trial**, not a blanket pipeline change:
if a scene is blur-dominated rather than coverage-limited, the enhancement may show **no
measurable downstream gain**.

### The Ada sm_89 fork

ArtiFixer's published stack mandates FlashAttention-3/FA4 on Hopper/Blackwell
(sm_90/sm_100). A **9-agent QE source audit ruled that requirement ARTIFICIAL** —
packaging/perf-default only, not a math/kernel dependency. The fork
(`Dockerfile.cuda12.ada-sm89`) **strips the FlashAttention-3/4 build block + the CI
asserts**, with **zero application-code changes** (the model falls through to cuDNN SDPA on
Ada). The 14B model runs **bf16 (~28 GB) on one 48 GB card**. Delivery is a sidecar
`artifixer` (image `gaussian-toolkit-artifixer:ada-sm89`) on `v2g-net`, GPU 1, `ipc=host`;
the 63 GB `artifixer-14b.pt` weight is staged (out of git, bind-mounted); the overlay is
`docker-compose.artifixer.yml`.

### The 3-stage pipeline (after COLMAP → BIN prep)

| Stage | Command | What it does |
|---|---|---|
| **1. Prepare** | `prepare_colmap_artifixer_inputs` | Trains its **own** 3DGRUT recon + MoGe metric scale; **720 train / 30 val**; 10k steps. |
| **2. Enhance** | `run_inference` | 14B diffusion enhance over `all_frames`. |
| **3. Distill** | `run_artifixer3d` | Distills enhanced frames → a clean **3DGRUT** recon. |
| → Mesh | (route TBD) | Adapter → CoMe/TSDF mesh; routing not yet decided. |

### Issues fixed so far

- **(a) Empty-val crash.** With no selected-images file, all 750 frames went to train,
  leaving val empty → 3DGRUT `compute_spatial_extents` `IndexError`. **Fixed** by a
  `selected_train_images.txt` that holds out **every 25th frame** → **720 train / 30 val**.
- **(b) sm_89 absent from the torch 2.11+cu128 `arch_list`** (`sm_75/80/86/90/100/120`).
  **Non-fatal:** sm_86 cubins are forward-compatible to sm_89, and the 3DGRUT JIT compiles
  **explicitly for 8.9**.

### Current status

The **prepare stage is RUNNING** — 3DGRUT JIT compiling for sm_89, then the 10k recon +
render + MoGe scale. **Enhance / distill / mesh and the gate verdict are PENDING. No
enhanced result yet.** The first run *is* the gate's validation: per ADR-020, the exit
criterion is **PROCEED** only on a measurable de-holing/de-noising gain at acceptable
wall-clock under the 200 W cap; **FALL BACK to Difix3D+** if it helps but is too costly;
**ABANDON** if the scene proves blur-dominated.

---

## Standing vs the goal / next levers

Honest read against the campaign goal (a fair textured room + two good objects):

- **Room geometry/texture is delivered as a UE game asset** (CoMe baseline scene →
  texture bake → FBX), but it is **partial and lumpy** — bounded by capture quality, not
  by anything we can fix at mesh-resolution. Part A demonstrably **falsified "finer voxel
  fixes it."**
- **Capture quality is the dominant lever.** dreamlab/locked is motion-blur-limited
  (MUSIQ ~31) with partial coverage. The clearest path to a *fair* room is a better
  capture (short-shutter, higher coverage) — consistent with the standing frame-QA verdict.
  No amount of TSDF tuning substitutes for sharper, more complete observations.
- **ArtiFixer is the in-flight secondary lever, not a blur fix.** It can only help the
  **holey/under-observed** component; its per-scene gate trial is **pending its first
  enhanced result.** If the gate says ABANDON (blur-dominated), that is itself a useful,
  documented outcome.
- **Objects path is separate** (SAM crop → Hunyuan3D-2.1) and tracked elsewhere; this
  campaign's room work does not gate it.

**Next levers, in priority order:** (1) a better dreamlab **capture** (the binding
constraint); (2) finish the **ArtiFixer prepare → enhance → distill** run and **render the
gate verdict**; (3) if ArtiFixer helps but is costly, evaluate the lighter **Difix3D+**
fallback; (4) only after a fair native-capture room, attempt the route that leans on
LichtFeld Studio's native capabilities (the vendored tool at `vendor/lichtfeld-studio`)
per the goal's second half.

---

## Artifacts & scripts

**Scripts** (`scripts/`):

| Script | Role |
|---|---|
| `come_extract_tsdf_lowmem.py` | The tensor `VoxelBlockGrid` attempts (`--device` / `--block_resolution` / `--block_count` / `--voxel_size` / `--depth_max`). Used for approaches 1–3. |
| `come_extract_tsdf_legacy.py` | The **WORKING** legacy `ScalableTSDFVolume` extractor (approach 4 / the stable path). |
| `come_mesh_clean.py` | Connected-component floater removal (`keep_frac` default 0.02). |
| `come_clean_qa.py` | One-load clean + decimated QA copy (avoids round-tripping multi-GB PLYs). |
| `come_largest_component.py` | Keep only the largest connected component (tight main-body QA framing). |
| `blender_qa_ply.py` | Headless Blender Cycles QA render of a vertex-coloured PLY (`3q` / `top` / `3q2` modes). |

**Output artifacts** (`output/dreamlab/locked/`, gitignored):

- `model_come/test/ours_30000/{tsdf_v0050.ply, tsdf_v0070.ply}` — raw legacy-TSDF meshes.
- `refine/{room_v0050_clean.ply, room_v0070_clean.ply, qa_*.png}` — cleaned meshes + QA
  renders.
- `scene/room_come_clean.ply` — baseline scene mesh (**2.74M f**).
- `scene_come/{room_come.fbx, room_textured.obj, room_albedo.png, qa_room/top/3q2.png}` —
  textured baseline room (UE-cm, embedded albedo) + QA renders.
- `artifixer/{prep/, prepare.log, selected_train_images.txt}` — ArtiFixer prepare stage
  (in progress).

**ArtiFixer branch components:** `docker/artifixer/Dockerfile.ada-sm89` (the Ada fork),
`docker-compose.artifixer.yml` (sidecar overlay), `src/pipeline/artifixer_adapter.py`
(3DGRUT → `.ply` for CoMe/TSDF), and
[`research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md`](../research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md)
+ [`docs/artifixer-recon-enhancement.md`](./artifixer-recon-enhancement.md) for the full
decision, build, run, and gate.
