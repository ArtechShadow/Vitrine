# PRD — Mesh + Textured Scene into Unreal Engine 5.8

| | |
|---|---|
| **Status** | Active (refined end-state) |
| **Owner** | Vitrine pipeline |
| **Date** | 2026-06-22 |
| **Supersedes scope of** | ADR-016 (USD-into-UE export) for the *critical delivery path* — see Non-goals |
| **Source** | 4-agent pipeline audit (dreamlab data verdict, ComfyUI staging, UE smoke, scene/object recipes) + user refinement 2026-06-22 |

---

## 1. Problem & Goal

**Problem.** The pipeline reconstructs a room and its objects from video, but the
deliverable was over-specified around a USD scene graph with `v2g:*` lineage,
live `UsdStageActor` import, interactivity, and lighting. That stack is heavy,
partially blocked, and not what the end product actually needs. We have a *working*
mesh-and-texture path that produces game-ready assets; the goal is to commit to it.

**Goal.** Deliver a **polygonal, textured 3D scene assembled in Unreal Engine 5.8**:
a single room/environment mesh plus per-object textured meshes, each independently
reconstructed and textured, placed in correct relative position inside a clean UE
level, displaying their **captured colour** (not flat white) via baked-texture
materials. This is the product. Everything else is optional or de-scoped.

The deliverable is a thing you can open in UE 5.8 and see: a recognisable room with
recognisable, correctly-placed, correctly-coloured objects in it.

---

## 2. Non-goals (explicitly de-scoped)

These are **out of the critical path**. Do not block delivery on them; do not
invest in them ahead of the FRs in §4.

1. **USD delivery is NOT required.** USD (`.usd`/`.usda`), `v2g:*` metadata,
   live `UsdStageActor` import, and full video→frame→object lineage are **dropped
   from the critical path**. FBX/OBJ/GLB game assets are the contract. (USD work
   under ADR-016 may continue independently but is not gating.)
2. **Gaussian-splat-in-UE is OPTIONAL.** A `.ksplat`/splat representation inside
   UE is a nice-to-have, not a requirement. The polygonal mesh is the deliverable.
3. **Interactivity is de-scoped.** No interactive elements, triggers, blueprints,
   physics, or gameplay logic required. Static placed meshes satisfy the contract.
4. **Lighting is de-scoped.** No bespoke lighting design, light baking, Lumen
   tuning, or relighting required. Default/unlit-adequate level lighting that lets
   baked albedo read correctly is sufficient. Interactivity + lighting are
   **low-priority stretch goals** only.

---

## 3. Users & stakeholders

| Stakeholder | Interest |
|---|---|
| **Exhibit/scene owner (primary user)** | Opens the UE level, sees the textured room + objects; uses it as a game-style asset set. |
| **Pipeline operator** | Runs the scene + object recipes end-to-end, manages serial GPU + ComfyUI restarts. |
| **Downstream (VisionFlow / web delivery)** | Consumes the assembled assets; optional `.ksplat` for web. |
| **Maintainers** | Keep the path inside fork boundaries (§6) and licence constraints (CoMe). |

---

## 4. Functional requirements

### FR-1 — Environment (room) mesh
- **FR-1.1** Produce a single watertight-enough room/environment mesh from the
  trained scene. Default extractor **CoMe**; fallback **gsplat-TSDF** (validated).
- **FR-1.2** Clean via `MeshCleaner(smooth_iterations=0)` (no over-smoothing of
  captured geometry).
- **FR-1.3** Bake textures via `texture_baker.bake_from_vertex_colors` with an
  **xatlas UV atlas**, producing an organised texture set (albedo at minimum).
- **FR-1.4** Export to **FBX** for UE import.

### FR-2 — Per-object textured meshes (≥4)
- **FR-2.1** For each key object: **SAM image-crop → Hunyuan3D-2.1 (Hy3D21
  ComfyUI graph)** → textured **GLB + OBJ + PBR maps**.
- **FR-2.2** Convert to **FBX** via `blender_obj_to_fbx.py`.
- **FR-2.3** Operate **one object per ComfyUI session** (restart-ComfyUI-per-object)
  to avoid cross-object VRAM/state crashes.
- **FR-2.4** Deliver **≥4** independently-reconstructed, textured object meshes.
  Current state: **4/8 done** (chair, dartboard, vacuum_cleaner, ladder); strong
  candidates to round out / replace marginals: mitre_saw, toolbox.

### FR-3 — Assembly in UE 5.8
- **FR-3.1** Import the room mesh + all object meshes into a **clean UE 5.8 level**.
- **FR-3.2** Place each object at its **correct relative position/scale/orientation**
  within the room (recovered from the reconstruction; objects sit where they were
  captured, not at origin).
- **FR-3.3** Assign **baked-texture materials** so each mesh displays captured
  colour. No flat-white / default-material meshes in the delivered level.

### FR-4 — Material correctness
- **FR-4.1** Room material drives from the baked atlas (FR-1.3).
- **FR-4.2** Object materials drive from Hunyuan3D PBR/albedo maps (FR-2.1).
- **FR-4.3** Texture coordinates survive the FBX round-trip (UV atlas / object UVs
  preserved through Blender conversion and UE import).

---

## 5. Acceptance criteria (THE contract)

> **A UE 5.8 render (screenshot / viewport capture) showing the textured room
> mesh together with ≥4 textured object meshes, each placed in correct relative
> position, with their captured colour displaying correctly — i.e. recognisably
> textured, NOT flat white / default material.**

Pass conditions, all required:
1. One UE 5.8 level loads the room mesh + ≥4 object meshes.
2. Room mesh shows baked captured colour (the rendered room is visually the
   captured room, not untextured grey/white).
3. ≥4 object meshes each show their own captured/recovered texture (not flat white,
   not the room's texture, not default material).
4. Objects are in plausibly correct relative placement inside the room (chair on
   the floor, dartboard on/near a wall, etc.), not stacked at origin.
5. A single render frame demonstrates 2–4 simultaneously.

If the render shows flat-white or default-material meshes for the room or any of
the 4 objects, **the contract is not met.**

---

## 6. Constraints

### Hardware / runtime
- **GPU: single RTX 6000 Ada, 48 GB.** Serial GPU usage — models do not co-reside
  (e.g. FLUX.2 cannot share VRAM with TRELLIS.2 on 48 GB; lifecycle is serial
  `/free`).
- **~200 W thermal caps** in effect — sustained throughput is bounded; plan for
  serial, not parallel, GPU stages.
- **ComfyUI is restart-per-object** (FR-2.3) — object generation is sequential and
  must tolerate/recover from ComfyUI crashes (oversight=claude_code recovery path).

### Licensing
- **CoMe is non-commercial (research/eval only).** CoMe-derived environment meshes
  are **research/eval artifacts**, not for commercial delivery. For any
  commercial-track output, use the **gsplat-TSDF fallback** (FR-1.1). CoMe stays
  gated/off-by-default (`INSTALL_COME=1`).

### Fork & architecture boundaries (BOUNDARIES.md)
- All new work lives in **our** dirs (`src/pipeline/`, `scripts/`, `unreal/`,
  `docker/`, docs). **Do not modify upstream** (`src/core`, `src/app`, `src/mcp`,
  `src/rendering`, `src/training`, `src/geometry`, `src/io`, `cmake/`, `external/`,
  `CMakeLists.txt`, `vcpkg.json`). One-way upstream sync; no upstream PRs.
- **UE 5.8 overlay** is in-repo (`unreal/engine/`, bind-mounted RO at
  `UE_ROOT=/opt/ue`), built from the NVIDIA CUDA base (no Epic GitHub gate).
  Control via Web Remote Control `:30010` (primary), first-party UE MCP `:8000`
  (secondary), `unreal/runtime/mcp_bridge.py` `:9100`.

### Tooling constraints (carried from working recipes)
- Object turnarounds feed **SAM image crops**, not orbit renders, into Hy3D21.
- The `sam3dobjects` vendored `cv2` shim must stay disabled (segfaults at 4096px).
- UE baked importer drops `customData`/vertex colours — colour comes from the
  **baked atlas / PBR maps on the mesh**, not from importer-preserved vertex colour.

---

## 7. Quality bar & known limits

**Data verdict (dreamlab capture).**
- **COLMAP is strong:** 600/600 frames registered, mean reprojection error
  **1.03 px**, coherent whole-room coverage — **NOT fragmented**. Geometry/pose is
  not the bottleneck.
- **Frame quality MUSIQ ~31** — *usable* (well above the abandon threshold ~19).
  **Motion blur is the ceiling.** Residual haze is worst on the **under-observed
  floor**; expect some softness/haze in the room mesh texture, acceptable for the
  contract.
- **Objects:** ~4 solid (**chair, mitre_saw, toolbox, dartboard**), 2 marginal
  (**vacuum, ladder**), 2 **SAM over-segmented** (**table, workbench** → need a
  SAM re-crop before they're reconstructible).

**Quality bar for delivery.**
- Room mesh: recognisable, correctly-textured room; haze/softness from MUSIQ ~31
  is tolerated, especially on the floor.
- Object meshes: recognisable silhouette + captured/recovered texture; the 4
  delivered objects should come from the solid/recoverable set, not the
  over-segmented pair.

**Known limits (accepted, not blockers).**
- Floor texture haze (under-observation × motion blur).
- table/workbench require SAM re-crop to escape over-segmentation (deferred unless
  needed to reach ≥4).
- Object failures observed so far were **infrastructure** (ComfyUI crashes, TRELLIS
  empty-input) — **not raw-data** — and are addressed by restart-per-object +
  recovery, not by recapture.

---

## 8. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | ComfyUI crashes mid-object stall the serial object queue. | High | Med | Restart-per-object (FR-2.3) + claude_code oversight recovery; checkpoint completed objects. |
| R2 | Texture/UVs lost across OBJ/GLB → FBX → UE round-trip → flat-white in render. | Med | High (fails §5) | Validate UVs + material after each conversion; the §5 render is the gate. |
| R3 | CoMe licence used on a commercial-track output. | Low | High (legal) | Default to gsplat-TSDF for any commercial output; keep CoMe gated/off. |
| R4 | Object relative placement wrong (objects at origin / wrong scale). | Med | High (fails §5.4) | Carry placement transforms from reconstruction; verify in viewport before sign-off. |
| R5 | Marginal objects (vacuum/ladder) don't texture cleanly, dropping below ≥4. | Med | Med | Backfill from solid set (mitre_saw, toolbox); SAM re-crop table/workbench only if needed. |
| R6 | VRAM contention / thermal throttle slows or OOMs a stage. | Med | Med | Strict serial GPU lifecycle + `/free`; respect 200 W caps; one model resident at a time. |
| R7 | Scope creep back into USD/interactivity/lighting. | Med | Med | This PRD: §2 de-scopes them; do not gate delivery on them. |

---

## 9. Definition of Done

The PRD is **Done** when **all** hold:

1. **Scene mesh:** a room/environment mesh exists, cleaned
   (`smooth_iterations=0`), texture-baked (xatlas atlas), exported to FBX, and
   imported into UE 5.8 with its baked-texture material.
2. **Objects:** **≥4** independently-reconstructed object meshes (from the
   solid/recoverable set) exist as textured FBX (via Hy3D21 → `blender_obj_to_fbx.py`)
   and are imported into UE 5.8 with their PBR/albedo materials.
3. **Assembly:** a single clean UE 5.8 level contains the room + ≥4 objects, each
   in correct relative position/scale/orientation.
4. **The contract render (§5):** a UE 5.8 render is produced and saved showing the
   textured room + ≥4 textured objects displaying captured colour — **not flat
   white / default material** — with objects correctly placed.
5. **Boundaries respected:** all new code in our dirs; no upstream edits; CoMe vs
   gsplat-TSDF chosen per the licence constraint (§6) for the output's track.

Stretch (not required for Done): `.ksplat`-in-UE, interactivity, custom lighting,
USD export, table/workbench re-crop to reach 8/8 objects.

---

*References: `CLAUDE.md` (workspace), `BOUNDARIES.md`, `research/decisions/`
(ADR-015 object recon, ADR-016 UE export), `docs/engineering-log.md`,
`docs/capture-methodology.md`, and the audit memory notes
(object-recon SAM-crop redo, UE captured-color & bake, frame-QA verdict,
in-flight recovery & VRAM, cv2 shim segfault).*
