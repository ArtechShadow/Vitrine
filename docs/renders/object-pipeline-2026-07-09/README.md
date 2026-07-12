# Object pipeline convergence — proof assets (2026-07-09)

First fully-automated **frames → isolated artefact → textured 3D asset** run on
real capture data (rawcapdev, 55×8K frames), after the ADR-025 / PRD v4
convergence landed. Every image below was produced by the committed pipeline —
no manual cropping, no out-of-tree scripts.

| # | Asset | What it proves |
|---|-------|----------------|
| 01 | `01_source_frame.jpg` | The capture: brass patina vessel + inverted ketchup bottle + wooden block. |
| 02 | `02_sam3_silhouettes_fixed.jpg` | **R1 fixed**: SAM3 pixel-accurate silhouettes (vessel/bottle/block). The "coarse boxes" defect was an HWC/CHW bug in our `Sam3Processor` call — masks were being interpolated onto a W×3 grid. One-line fix (`sam3_segmentor._to_pil`). |
| 03–05 | `0x_crop_*.png` | **R3**: `object_crops` best-frame mattes — the ONLY conditioning the 3D generator receives (native res up to 3175², SAM-silhouette alpha, full provenance in `crops.json`). |
| 06–07 | `0x_generated_metal_container_*.png` | **R4/R5/R6**: single-image TRELLIS.2 (1536_cascade, 4K PBR), GLB persisted byte-identical. Front = observed surface; back = model-completed (`surface: inferred` in lineage). |
| 08–09 | `0x_generated_{bottle,wooden_block}.png` | Same path, remaining objects. Renders are WORKBENCH+texture turntables from the R9 eval harness. |

## Run metrics (eval baseline: `eval/objects/references.json`)

| Object | Isolated gaussians | Crop | GLB | Faces | Gen time |
|---|---|---|---|---|---|
| metal container | 1,094,860 / 4M (6 views) | 3175² | 54.8 MB PBR | 492,107 | 441 s |
| bottle | 246,155 / 4M | 1457² | PBR | 483,178 | 158 s |
| wooden block | 249,912 / 4M | 1456² | PBR | 466,038 | 130 s |

3/3 generated, 0 regressions vs the manual dreamlab baseline class
(2026-07-02 manual vessel: 483,671 faces). Generation on GPU 1
(`COMFYUI_GPU=1`), TRELLIS.2-4B via the single-image ComfyUI workflow;
GLBs + full 8-view turntables in `output/object_e2e/` and
`output/eval_objects/` (gitignored — regenerate with
`eval/objects/run_eval.py`).

See `docs/engineering-log.md` (2026-07-09), ADR-025, and
`docs/audit/object-pipeline-audit-2026-07-09.md` for the full story.
