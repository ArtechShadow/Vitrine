# Object Pipeline Audit — SAM3 → multiview → TRELLIS.2 (2026-07-09)

Deep audit of the single-image → isolated-artefact → textured 3D object pipeline, in isolation,
plus a survey of current SOTA (July 2026) for local single-image → textured high/low 3D.

**Verdict up front:** the model choice (TRELLIS.2) is still SOTA-competitive. The conditioning
architecture around it is wrong in several compounding ways, and the automated SAM3→object path
has never actually produced a validated per-object result on real data. Your instinct that "the
multiview panel input seems wrong and the outputs are off" is correct — and the causes are
identifiable and fixable.

---

## Part A — What the pipeline actually does (verified against code)

### A.1 The active data flow

`stages.py`: `segment → extract_objects → mesh_objects → texture_bake → assemble_usd`

1. **`segment`** — SAM3 concept segmentation on sampled frames; per-concept masks unioned
   across frames **in 2D pixel space** (stages.py:1750-1759) — geometrically meaningless under a
   moving camera. Concepts from a static list in `config.py:187`.
2. **`extract_objects`** — isolates per-object Gaussian subsets from the trained splat.
   Preferred: depth-aware multiview vote (`_extract_with_mask_mv`). Fallback 1: a camera-free
   world-XY heuristic (`_extract_with_mask`, stages.py:2099 — bogus, acknowledged in-code).
   Fallback 2: **copies the entire scene PLY as the "object"** (stages.py:1893-1917).
3. **`mesh_objects`** — strategy chain ending in TRELLIS.2 (`trellis2_client.py`): CPU-renders
   6 orbit views of the per-object PLY (`multiview_renderer.py`, preset `trellis_6`), optionally
   FLUX.2-completes empty views (`view_completer.py` + `flux2_turnaround.json`), submits
   `trellis2_multiview_pbr.json`.

### A.2 The critical realization

**SAM3 image crops are never fed to TRELLIS.2.** The "multiview input" is six software
re-renders of the *segmented splat*, not the source photos. And because SAM3 currently returns
coarse bounding boxes rather than silhouettes (stages.py:1656-1661; e2e-validation doc;
engineering log 2026-07-02), `extract_objects` routinely falls back to full-scene copies — so
TRELLIS.2 has been conditioning on **six 512px CPU renders of the entire room squashed into a
unit sphere, labelled front/left/back/right/top/bottom**. The engineering log admits this
(2026-06-21: e2e object PLYs were "1M-Gaussian full-scene copies"). This alone explains the
"off" outputs.

Meanwhile, the objects that actually looked good (dreamlab set) came from an **out-of-pipeline
manual path**: hand-cropped SAM masks → Hunyuan3D-2.1 via `scripts/hy3d_turnaround.py` /
`hy3d_one.py` (engineering log 2026-06-23: "Objects = Hunyuan3D-2.1, NOT TRELLIS.2"). That
crop→3D path was never committed as a pipeline stage.

### A.3 The "multiview panel" specifically

It is not a stitched grid — `trellis2_multiview_pbr.json` feeds **six discrete images** into
`Trellis2MultiViewImageToShape` (node 40: named front/left/back/right/top/bottom slots,
`front_axis:"z"`, steps 12/12, seed 42) → `Trellis2ProcessMesh` (remesh, 500k faces) →
`Trellis2ShapeToTexturedMesh` → `Trellis2RasterizePBR` (4096²). Verified defects in this feed:

| # | Severity | Defect |
|---|----------|--------|
| 1 | Blocker | SAM3 boxes-not-silhouettes → full-scene PLYs masquerading as objects (§A.2). |
| 2 | Blocker | The proven crop→3D path is uncommitted scripting; no automated single-image→3D stage exists in `src/`. |
| 3 | Critical | Directional slots assume y-up, front=+Z (`multiview_renderer.py:208-217`); COLMAP-world object PLYs have arbitrary orientation → "top"/"front" labels are frequently lies fed to a geometry-aware node. |
| 4 | Critical | CPU rasterizer accumulates premultiplied color with **no un-premultiply** (`multiview_renderer.py:729-746`); `view_completer.py:137` itself notes object pixels carry **alpha 1–8 / 255**. ComfyUI `LoadImage` drops alpha → TRELLIS mattes a near-black ghost. Also O(N) pure-Python per view — unusable at 1M gaussians. |
| 5 | High | Missing views are backfilled with **the front image duplicated** into other directional slots (`trellis2_client.py:311-318`). |
| 6 | High | FLUX.2 view completion: 512px (sub-native), text-only azimuth prompt (no geometric NVS conditioning), refs picked by coverage not adjacency, "white bg / studio light" prompt vs dark scene-lit real views → inconsistent conditioning; `v2g:view_synth` lineage never recorded. |
| 7 | High | TRELLIS PBR GLB bytes are discarded — mesh re-exported via trimesh (material loss; OBJ loses PBR) — then `texture_bake` **re-unwraps and projects splat-frame renders onto the TRELLIS-frame mesh** (stages.py:2367-2368, 2487-2544; texture_baker.py:109-168). Destructive. |
| 8 | High | Hunyuan fallback workflows (`hunyuan3d_multiview.json`, `hunyuan3d21_multiview.json`) very likely can't validate: `ImageOnlyCheckpointLoader` reads an empty `checkpoints/` dir (sota_registry.py:215-217) and the 2.1 PBR node class names don't match the installed `Hy3D21*` pack. The chain silently drops to TSDF. |
| 9 | Medium | Dead config: `hunyuan3d.{seed,turbo,multiview,num_views,render_size,camera_distance}` filtered out by `inspect.signature` (stages.py:2386-2400); TRELLIS steps hardcoded in JSON; default client endpoints still `localhost:8189/3001`. |
| 10 | Medium | Texture diffusion conditioned on the **front view only** (node 30→50) — the slot most likely to be empty/synthetic. |
| 11 | Medium | cv2 fixes are out-of-tree monkey-patches of the node pack (`trellis2_unwrap_cv2_patch.sh`, vendor-cv2 disable) — regress silently on any node update. |
| 12 | Low | No object-quality metrics anywhere (`eval/` is MipNeRF360 training only); e2e "PASS" validated plumbing on mislabelled full-scene inputs. No LOD/low-poly stage despite the high/low framing. |

Also: `Trellis2MultiViewImageToShape` is a **community-wrapper node** — official TRELLIS.2 has
no multi-image API at all (see B.2), so this entire conditioning mode is an unofficial extension
being fed its worst-case inputs.

---

## Part B — SOTA survey (July 2026, local GPU, 24–48 GB)

### B.1 Model landscape

- **TRELLIS.2 (Microsoft, Dec 2025, MIT)** — still the community default for open-weights PBR
  image-to-3D. 4B, O-Voxel rep, 512³–1536³, native PBR incl. opacity, ≥24 GB official (GGUF
  quants to ~6 GB). Includes `to_glb` (CUDA decimation/remesh/UV/bake, one call) and
  `app_texturing.py` (PBR-texture *any* supplied mesh). Weakness: hallucinated backsides from
  a single view.
- **Pixal3D (TencentARC, May 2026, SIGGRAPH 2026)** — pixel-aligned generation **on the
  TRELLIS.2 backbone**; back-projects pixel features into 3D for near-reconstruction input
  fidelity. The likely successor; custom (non-MIT) license — check terms. Evaluate head-to-head.
- **Hunyuan3D 2.1 (Tencent, open)** — the texture-quality workhorse; ~29 GB full pipeline
  (offloadable). **2.5/3.x weights were never released** — hosted only; SEO sites claiming
  otherwise are wrong. Tencent's late-2025 open drops: **Hunyuan3D-Omni** (image + point
  cloud/voxel/skeleton conditioning — "ControlNet of 3D") and **Hunyuan3D-Part**
  (P3-SAM + X-Part part segmentation/generation).
- **SAM 3D Objects (Meta, Nov 2025)** — image + mask → shape + texture + **scene-space pose**;
  built exactly for "many occluded objects in one messy photo"; ~16 GB. Lower texture/geometry
  detail than TRELLIS.2 — layout/completion tool, not hero-asset generator.
- Geometry-only tier: Hi3DGen (best normal-bridged detail), Direct3D-S2, TripoSG/SF, Step1X-3D.
  **Sparc3D: avoid** — weights never shipped; team pivoted to paid Hitem3D.
- **ComfyUI-3D-Pack is dead** (unmaintained, build failures). TRELLIS.2 wrappers
  (visualbruno / PozzettiAndrea) work but vendor heavy CUDA deps into ComfyUI's env — the main
  breakage source. Community trend: run the **native repo pipelines** (or a thin API service)
  for the 3D half; keep ComfyUI for the 2D half.

### B.2 Multiview conditioning — the direct answer

- Official TRELLIS.2 is **single-image only** (`pipeline.run(image)`). Multi-image was requested
  (issues #10/#27/#77) and never shipped. Community forks (Allen-Zhou729/Trellis2_multiimage)
  re-implement TRELLIS 1's stochastic/multidiffusion trick — and issue #103 reports multi-image
  results **worse than single-image**. Where multi-image exists (TRELLIS 1
  `run_multi_image`), it takes a **list of images, never a stitched panel**; grids are
  out-of-distribution for the DINO conditioner and a known anti-pattern.
- Models actually *trained* for multiview: **Hunyuan3D-2mv** (dedicated front/back/left/right
  slots) and **Hunyuan3D-Omni** (multi-view → point cloud → geometric conditioning).
- **What practitioners do in 2026:** one clean, background-removed ~3/4-view image per object at
  1024³–1536³, seed re-rolls, optionally an image-edit model ("show the back") for a second
  attempt. Synthesized-multiview conditioning is a 2023–24 (Zero123/InstantMesh-era) pattern
  that has fallen out of favor — modern models' shape priors are strong enough that inconsistent
  synthetic views inject more noise than signal. Your six dark splat re-renders + FLUX
  hallucinations + duplicated-front backfill is the pathological version of that dead pattern.

---

## Part C — Recommendations

### C.1 Target architecture

```
scene frames ─► SAM3 (fix silhouettes) ─► per-object crop from BEST source frame
             ─► matte/complete (rembg/BiRefNet; optional inpaint for occlusion)
             ─► TRELLIS.2 native pipeline, SINGLE image, 1024³–1536³
             ─► to_glb ×2 (high-poly + decimated low-poly, 4K PBR bake)
             ─► (optional) quad retopo (Instant Meshes/Quad Remesher) + app_texturing.py re-texture
             ─► GLB → USD assembly (persist ComfyUI/native GLB bytes verbatim)
```

The splat is used for **scale and placement**, not for conditioning imagery. If scene-space
poses / occlusion completion matter more than detail for some objects, add **SAM 3D Objects**
as a parallel track and swap hero assets in.

### C.2 Ordered fix list

1. **Stop feeding splat re-renders to TRELLIS.2.** Commit the crop→3D path as a first-class
   stage: SAM3 crop from the best frame → single-image TRELLIS.2. This replaces defects 2-6 and
   10 in one move and matches how the model was trained.
2. **Fix SAM3 silhouettes** (boxes bug — investigate `Sam3Processor` mask extraction and the
   #507 bf16 patch). Everything downstream is blocked on this regardless of backend.
3. **Persist the PBR GLB bytes**; make `texture_bake` skip TRELLIS meshes (defect 7).
4. **Kill or fix the Hunyuan fallback workflows** (defect 8) — align to the proven `Hy3D21*`
   graph from `hy3d_turnaround.py`, or drop them and keep Hunyuan3D-2mv only for the rare
   genuine-multiview case.
5. **Move TRELLIS.2 off ComfyUI** to the native pipeline behind a small API service; upstream
   the cv2 patch or pin the node pack (defect 11). Keep ComfyUI for the 2D stages.
6. **Evaluate Pixal3D vs TRELLIS.2** on 5–10 dreamlab crops (mind the license).
7. **Add an object-quality eval**: fixed crop set, rendered turntable comparison + at least one
   numeric geometry metric; delete the world-XY fallback and full-scene-copy fallback so
   failures fail loudly.
8. If splat re-rendering is ever needed again (e.g., for Omni point-cloud conditioning), replace
   the CPU rasterizer with gsplat GPU rendering, un-premultiplied, straight-alpha (defect 4).

### C.3 What NOT to change

TRELLIS.2 as core generator (MIT, PBR, best open topology handling); SAM3 as segmenter
(fix, don't replace); the high/low ambition (TRELLIS.2's `to_glb` gives it nearly for free —
it just isn't wired up).

---

## Sources

Repo evidence: `src/pipeline/{trellis2_client,multiview_renderer,view_completer,stages,sota_registry}.py`,
`src/pipeline/workflows/*.json`, `scripts/hy3d_turnaround.py`, `docs/engineering-log.md`,
`docs/pipeline-e2e-validation-2026-07-02.md`, `docs/audit/master-audit-2026-07-02.md`,
`research/2026-06-object-reconstruction-sota.md`.

External:
- https://github.com/microsoft/TRELLIS.2 (single-image API, to_glb, app_texturing, MIT) + issues #10, #77, #103
- https://github.com/Allen-Zhou729/Trellis2_multiimage · https://github.com/microsoft/TRELLIS (`run_multi_image`)
- https://huggingface.co/TencentARC/Pixal3D (arXiv 2605.10922)
- https://github.com/facebookresearch/sam-3d-objects · https://ai.meta.com/blog/sam-3d/
- https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 · https://huggingface.co/tencent/Hunyuan3D-Omni · https://github.com/Tencent-Hunyuan/Hunyuan3D-Part
- https://github.com/Tencent-Hunyuan/Hunyuan3D-2/issues/316 (2.5/3.x not open)
- https://github.com/lizhihao6/Sparc3D issues #1/#22/#25 (no weights)
- https://github.com/MrForExample/ComfyUI-3D-Pack/issues/470 (dead)
- https://github.com/visualbruno/ComfyUI-Trellis2 · https://github.com/kijai/ComfyUI-Hunyuan3DWrapper · https://github.com/VAST-AI-Research/UniRig
