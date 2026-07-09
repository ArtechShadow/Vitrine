# ADR-025 — Single-Image Object Generation (retire splat-render multiview conditioning)

**Status:** Proposed (2026-07-09)
**Supersedes:** ADR-015 (TRELLIS.2 hull from splat-rendered panel set), ADR-017 (FLUX.2 generative view completion *as TRELLIS conditioning*)
**Extends:** ADR-010 (key-item hull recon — the "do no harm" principle survives), ADR-014 (agent-controlled ComfyUI — scope narrowed to 2D stages)
**Drives:** replacement of `trellis2_client.py` conditioning path, retirement of `multiview_renderer.py`/`view_completer.py` from the object pipe, new `object_crops` stage, `prd-v4-object-pipeline-convergence.md`
**Evidence:** [docs/audit/object-pipeline-audit-2026-07-09.md](../../docs/audit/object-pipeline-audit-2026-07-09.md)

---

## Context

ADR-015/017 established the current object path: per-object Gaussian PLY → six CPU-rendered
orbit panels (`trellis_6`) → FLUX.2 completion of empty panels → community
`Trellis2MultiViewImageToShape` node. The 2026-07-09 audit found this architecture broken at
every link, independent of the SAM3 silhouette bug:

1. **The conditioning mode is unofficial and counterproductive.** Official TRELLIS.2 is
   single-image only (`pipeline.run(image)`); multi-image was requested upstream (issues
   #10/#27/#77) and never shipped. Community multi-image forks report results *worse* than a
   single clean image (microsoft/TRELLIS.2 #103). Multiview-synthesis conditioning is a
   2023–24 (Zero123/InstantMesh-era) pattern the field has abandoned: modern Objaverse-XL-scale
   priors are stronger than inconsistent synthetic views.
2. **The panels themselves are pathological.** The CPU rasterizer emits premultiplied-on-black
   RGBA with no un-premultiply (object alpha 1–8/255, per `view_completer.py:137`'s own
   comment); ComfyUI `LoadImage` drops alpha, so TRELLIS mattes a near-black ghost. Directional
   slots (`front_axis:"z"`, top/bottom) assume y-up/front=+Z on arbitrary-orientation COLMAP
   worlds. Missing views are backfilled with the *front image duplicated*. FLUX.2 fills are
   512px, text-prompt-only (no geometric NVS), white-bg/studio-lit against dark scene-lit real
   panels, and the promised `v2g:view_synth` lineage is never written.
3. **The path has never worked end-to-end.** SAM3 returns boxes, `extract_objects` falls back
   to full-scene PLY copies, and no automated per-object result on real data has ever been
   validated. The objects that shipped (dreamlab) came from manual crop → Hunyuan3D-2.1
   scripting outside `src/`.

Meanwhile the source frames — the highest-fidelity observation of every object we have — are
never shown to the generator.

## Decision

**Condition the 3D generator on one clean, isolated photograph of the object, not on renders
of the splat.**

1. **Conditioning input = best source-frame crop.** New `object_crops` stage: for each SAM3
   object, select the best observing frame (silhouette area × sharpness × frontality score),
   crop with padding, matte (rembg/BiRefNet-HR), square-pad to ≥1024². Persist crop + mask +
   provenance (`frame_id`, camera pose) in the manifest. This commits the proven manual
   dreamlab path as a first-class stage.
2. **Generator = TRELLIS.2 native pipeline, single-image, via a thin HTTP service** (not the
   ComfyUI wrapper): `pipeline.run(image)` at 1024³–1536³, then `o_voxel.postprocess.to_glb`
   **twice** per object — high-poly and decimated game-res low-poly with 4K PBR bake. Persist
   the emitted GLB bytes verbatim; `texture_bake` must not touch generator meshes. ComfyUI
   remains the executor for 2D stages only (SAM3, matting, inpainting) per ADR-014.
3. **The splat provides pose/scale, never pixels.** Per-object placement (position, orientation,
   scale in scene frame) is solved from the splat + crop camera pose and applied at USD
   assembly. `multiview_renderer.py` and `view_completer.py` are retired from the object path
   (renderer retained only for previews/diagnostics, fixed to straight-alpha if kept).
4. **Occlusion/backside handling = generator prior first, image-edit second, never panel
   synthesis.** Default: accept TRELLIS.2's completion prior + seed re-rolls. Escalation for
   hero assets: image-edit second view ("show the back", Qwen-Image-Edit/FLUX-Kontext) fed as
   an *alternative single-image attempt*, best-of-N selected. ADR-017's coverage-gating idea
   survives only as a *reporting* concept (observed-vs-inferred surface flag in lineage).
5. **Genuine multiview (when a future capture protocol yields real orthogonal photos of an
   object) goes to models trained for it** — Hunyuan3D-2mv slots or Hunyuan3D-Omni point-cloud
   conditioning — never to a TRELLIS panel set.

## Alternatives considered

- **Fix the panels (GPU gsplat render, straight alpha, gravity alignment) and keep
  multiview-TRELLIS.** Rejected: even perfect renders of a *partial* splat are strictly lower
  fidelity than the source photo, and the conditioning mode itself is unofficial with
  documented quality regressions (#103). Fixing defects 3–6 individually still loses to one
  clean crop.
- **SAM 3D Objects (Meta) as primary generator.** Rejected as primary: built exactly for
  occluded multi-object scenes and gives scene-space pose, but moderate resolution/texture —
  below TRELLIS.2 for hero assets. Adopted as *optional parallel track* for layout priors and
  badly occluded objects (see PRD v4, R7).
- **Hunyuan3D 2.1 as primary.** Viable (it produced the dreamlab objects) but: heavier
  (~29 GB full PBR pipe), non-MIT community licence, no built-in high/low `to_glb` path, and
  2.5/3.x weights were never released so the branch has no open upgrade path. Retained as
  fallback and as the multiview consumer (2mv/Omni).
- **Pixal3D (TencentARC, May 2026) as primary.** TRELLIS.2 backbone with pixel-aligned input
  fidelity — likely successor, but custom non-MIT licence and one month of community soak.
  Adopted as a *gated evaluation* (PRD v4, R8), not a default.
- **Keep ComfyUI as the 3D executor.** Rejected: wrapper nodes vendor heavy CUDA deps into
  ComfyUI's env (the load-bearing out-of-tree cv2 monkey-patches are symptoms), lag upstream,
  and hide `to_glb` knobs. ComfyUI-3D-Pack is dead upstream.

## Consequences

**Positive:** conditioning matches how the model was trained (single object-centric photo);
highest-fidelity input we possess; deletes two fragile subsystems (CPU rasterizer conditioning,
FLUX view completion) and the duplicated-front/backfill and orientation-slot lies; high/low +
4K PBR comes from one supported call; ComfyUI blast radius shrinks to 2D.

**Negative / risk:** backsides are model-hallucinated (was already true — FLUX panels were
hallucinations too, just worse); mitigation via re-rolls + image-edit escalation + lineage
flag. New native-pipeline service to operate (VRAM ≥24 GB — same class as current stack).
Placement no longer falls out of hull geometry; needs the pose-solve in Decision 3. SAM3
silhouette fix is a hard prerequisite (PRD v4, R1) — boxes give bad crops too, though far less
bad than six renders of the whole room.

## Compliance

- No stage may submit `trellis2_multiview_pbr.json`; the workflow file is deleted with this ADR's implementation.
- `mesh_objects` receives image crops, never PLY renders, as generator conditioning.
- Generator GLB bytes are persisted byte-identical; any re-export is a *additional* artefact.
- Full-scene-PLY fallback and world-XY mask heuristic are removed — objects fail loudly.
- Every generated asset carries lineage: source frame id, crop bbox, matting model, generator + version, seed, `surface:observed|inferred`.
