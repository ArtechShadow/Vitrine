# Vitrine — 20-Slide Technical Deck: Build Prompts

**Purpose.** This file is a build brief for a downstream Claude agent that has (a) a Google
Slides connector and (b) read access to this repository (`DreamLab-AI/Vitrine`). Each numbered
section is a self-contained prompt for **one slide**. Execute them in order. Where a prompt says
*Investigate*, open the listed repo files and pull **accurate, current** facts — do not invent
numbers; quote the repo.

**Authoring contract for the downstream agent**
- The repo is the source of truth. **Status/results change** — always re-derive "current status"
  from `docs/engineering-log.md` and `report/v5/sec_results.tex` rather than trusting any number
  baked into a prompt below.
- Keep claims defensible. If a fact isn't in the repo, omit it or mark it as a goal, not a result.
- Each slide: a crisp title, ≤6 bullets (short phrases, not sentences), one strong visual, and
  speaker notes (2–4 sentences) the presenter can read aloud.
- This is a **technical project deck** (engineering audience), not the funding pitch. The existing
  grant pitch lives at `docs/brief/ai-cop-funding-pitch-2026.md` — use it only for framing/impact.

---

## Global style guide

- **Theme:** dark, technical. Deep navy background (`#0d1b2a`-ish), off-white text, one accent
  (teal `#26c6da` / cyan) plus the project's signature deep blue `#0d47a1` for emphasis chips.
  This matches the hero diagram's palette and the existing "Vitrine" deck's dark/teal look.
- **Typography:** clean sans-serif (Inter/Roboto/Arial). Generous whitespace. Left-aligned bodies.
- **Layout motifs:** two-column "cards" with a small icon header for comparisons/lists; full-bleed
  image slides for renders; a consistent footer ("Vitrine · DreamLab AI / University of Salford ·
  2026") and slide numbers.
- **Diagrams:** prefer the high-res renders in `docs/renders/` (below). If a diagram must be
  regenerated, the mermaid sources are in the repo (see each slide) and can be rendered with the
  mermaid CDN in a browser, or via `report/poster/nano_banana.py` for a stylized version.

## Asset inventory (images we created / that exist in-repo)

All paths are relative to the repo root. **Note:** `08_*` were generated in the working session
on 2026-06-29 and may be **uncommitted/local-only** — if the cloud agent clones from GitHub and
they're absent, either commit+push them first or upload the PNGs to the deck manually. `01–07`
pre-exist in the repo.

| Asset | Path | What it shows | Suggested slide(s) |
|---|---|---|---|
| **Hero pipeline (canonical)** | `docs/renders/08_capture_adaptive_pipeline_hero.png` (5200×1136) | The capture-adaptive flow: Video → DIAGNOSE → ROUTE → {SCENE: splat/mesh, OBJECTS} → UE 5.8. Browser-rendered, label-perfect. | 4, 5 (and section dividers) |
| Hero pipeline (stylized) | `docs/renders/08b_capture_adaptive_pipeline_hero_nanobanana.jpg` (5504×3072) | Same diagram, Gemini-upcycled glossy variant. | Title / dividers |
| Hero source | `docs/renders/08_capture_adaptive_pipeline_hero.mmd` (= `README.md:32`) | Mermaid source to re-render if needed. | — |
| TSDF scene mesh | `docs/renders/01_tsdf_mesh_overview.jpg`, `02_tsdf_mesh_side.jpg`, `03_tsdf_mesh_topdown.jpg` | The reconstructed room mesh (validated scene path). | 10 |
| Object in room | `docs/renders/04_object_035_room.jpg` | A reconstructed object placed in the room. | 11 |
| Composed scene | `docs/renders/05_multi_object_composed.jpg`, `06_multi_object_topdown.jpg`, `07_multi_object_rear.jpg` | Multiple objects composed in the scene. | 3, 13 |
| Conference poster | `report/poster/poster_a0_nanobanana.pdf/.png` | A0 "Video-to-Gaussian" poster. | Appendix/backup |
| Architecture (mermaid) | `docs/architecture.md:85`, `report/v5/figures/architecture.mmd` | Docker/system topology. | 16 |
| Router (mermaid) | `docs/asset-creation-decision-tree.md:11`, `report/v5/figures/router.mmd` | The authoritative capture-adaptive router with decision gates. | 4 (alt) / 15 |
| Component menu (mermaid) | `docs/asset-creation-decision-tree.md:78`, `report/v5/figures/component_menu.mmd` | Full menu of validated components + enhancers. | 5 (alt) / 17 |

## Source-of-truth files (the agent should skim these first)

- `README.md` — overview, SOTA stack, the three hero mermaid diagrams (`:32`, `:72`, `:101`).
- `CLAUDE.md` — canonical project guide, pipeline one-liner, boundaries, topology, status.
- `report/v5/main.pdf` + `report/v5/{main,sec_method,sec_results,sec_technologies,appendix_playbook}.tex`
  + `references.bib` — the 47-page academic report; **richest** source for method/results/citations.
- `docs/engineering-log.md` — live status & defects (use for "current status").
- `docs/asset-creation-decision-tree.md` — the option space / router design.
- `docs/capture-methodology.md` — the capture-quality bottleneck (the project's core finding).
- `docs/ANTIPATTERNS.md` — what does NOT work (esp. the USD→UE dead-end).
- `BOUNDARIES.md` — vendored-tool policy (LichtFeld is a tool, not the trunk).
- `research/decisions/` — ADRs: `work-order-sota-modernisation.md` (ADR-012), and ADRs for objects
  (ADR-015), the UE overlay (ADR-016), and the mesh-not-USD delivery path (ADR-019).
- `AGENTS.md` / `docs/docs/development/mcp/` — the LichtFeld MCP control surface (70+ tools).

---

# The 20 slides

## Slide 1 — Title
- **Purpose:** Set identity and one-line thesis.
- **Investigate:** `report/v5/main.tex` (title, author, affiliation), `CLAUDE.md` §1.
- **Content:** Title **"Vitrine"**; subtitle **"A Capture-Adaptive Video → Structured-3D-Scene
  Pipeline for Unreal Engine 5.8"**; author **Dr John O'Hare**; affiliation **University of
  Salford · DreamLab AI**; date **2026**. One-line tagline: *"Point it at video of a room; get an
  editable, textured 3D scene — room + object game-assets — in UE 5.8."*
- **Visual:** `docs/renders/08b_capture_adaptive_pipeline_hero_nanobanana.jpg` as a faint full-bleed
  background, or the composed scene `05_multi_object_composed.jpg`.
- **Speaker notes:** Frame Vitrine as a standalone pipeline whose job is real-video-to-game-engine.

## Slide 2 — The problem
- **Purpose:** Why this is hard and worth doing.
- **Investigate:** `report/v5/main.tex` (Introduction), `docs/brief/ai-cop-funding-pitch-2026.md`
  (motivation/impact framing), `docs/capture-methodology.md`.
- **Content:** Turning ordinary handheld video of a real space into a *usable, editable* 3D scene
  in a game engine is unsolved end-to-end. Use cases: cultural-heritage preservation, immersive/MR,
  digital twins. Pain points: messy capture, photogrammetry gaps, splats aren't game-ready meshes,
  manual cleanup dominates.
- **Visual:** a simple "raw video → ??? → game engine" motif, or a still from source footage.
- **Speaker notes:** Emphasize the gap between "a pretty splat" and "an asset an artist can use".

## Slide 3 — What Vitrine produces (the deliverable)
- **Purpose:** Make the output concrete before the how.
- **Investigate:** `CLAUDE.md` §1 (deliverable definition), `docs/ANTIPATTERNS.md` (why FBX not USD).
- **Content:** A **textured polygonal scene for UE 5.8**: (1) a **room mesh**, (2) individually
  reconstructed, correctly-placed, textured **object meshes** imported as **FBX game-assets** with
  baked-texture materials (Nanite), (3) optional compressed **`.ksplat`** for web. USD is
  optional/archival, **not** the deliverable.
- **Visual:** `docs/renders/05_multi_object_composed.jpg` + `06_multi_object_topdown.jpg`.
- **Speaker notes:** The north star is *game-style assets*, not a research artifact.

## Slide 4 — The big idea: capture-adaptive routing ★
- **Purpose:** The thesis slide — the deck's spine.
- **Investigate:** `README.md:30–52` (the hero flowchart + prose), `docs/asset-creation-decision-tree.md`.
- **Content:** Capture quality varies wildly, so **one fixed pipeline fails**. Vitrine **DIAGNOSES**
  each capture (frame-QA via MUSIQ + sharpness, SfM success, coverage, hardware) and **ROUTES** to
  the right recipe: a **SCENE** branch (splat→UE or mesh→UE) and an always-on **OBJECTS** branch.
- **Visual:** **`docs/renders/08_capture_adaptive_pipeline_hero.png`** (the canonical hero — full
  width). Alt/animated build: the router `docs/asset-creation-decision-tree.md:11`.
- **Speaker notes:** "Route by bottleneck" is the core intellectual contribution; everything after
  is detail under this idea.

## Slide 5 — End-to-end pipeline at a glance
- **Purpose:** The full stage chain in one view.
- **Investigate:** `CLAUDE.md` §1 (the pipeline one-liner), `report/v5/sec_method.tex`,
  `report/diagrams/data_flow.mmd`.
- **Content:** Ingest → frame extraction → **frame-QA (MUSIQ)** → **COLMAP SfM (ALIKED+LightGlue)**
  → **3DGS (LichtFeld v0.5.3)** → optional `.ksplat` → **SAM3 segmentation** → per-object SAM crop
  → **Hunyuan3D-2.1 / TRELLIS.2 textured GLB** → **env mesh (CoMe / TSDF)** → MeshCleaner(smooth=0)
  → **texture bake (xatlas)** → **FBX** → **UE 5.8 import (Nanite)**.
- **Visual:** the hero `08_*` again, or the component menu `docs/asset-creation-decision-tree.md:78`.
- **Speaker notes:** Note each stage is a swappable SOTA component, not bespoke code.

## Slide 6 — Stage: ingest & frame quality (MUSIQ)
- **Purpose:** Show quality is gated up front.
- **Investigate:** `src/pipeline/frame_quality.py`, `docs/capture-methodology.md`, the
  "blur-aware frame selection" approach (full-res Laplacian, FIFO sharpest-per-window).
- **Content:** Per-video drop-and-flag gate using **pyiqa MUSIQ** NR-IQA; **blur-aware selection**
  scoring sharpness on full-res frames (downscaled blur metrics lie); frame-integrity manifest +
  sha256. Garbage frames never reach SfM.
- **Visual:** a sharp-vs-blurred frame pair, or a MUSIQ-score histogram (agent may generate one).
- **Speaker notes:** This is where the pipeline earns its robustness; capture quality is the theme
  revisited on slide 19.

## Slide 7 — Stage: Structure-from-Motion (COLMAP)
- **Purpose:** Camera geometry.
- **Investigate:** `report/v5/sec_method.tex` (SfM), `report/v5/sec_technologies.tex`.
- **Content:** **COLMAP** SfM with modern features: **ALIKED** keypoints + **LightGlue** matching
  → camera poses + sparse point cloud that anchor everything downstream. Robust to the wide-baseline
  handheld captures that classic SIFT struggles with.
- **Visual:** a sparse-cloud + camera-frusta render (agent may render from COLMAP output if present).
- **Speaker notes:** Poses are the shared coordinate frame for splats, meshes, and object placement.

## Slide 8 — Stage: 3D Gaussian Splatting (LichtFeld Studio)
- **Purpose:** The radiance representation.
- **Investigate:** `README.md` (SOTA stack), `report/v5/sec_technologies.tex`,
  `vendor/lichtfeld-studio` pin (v0.5.3), `AGENTS.md`.
- **Content:** Native C++23/CUDA **3DGS training via vendored LichtFeld Studio v0.5.3**
  (ImprovedGS+, unpruned for downstream meshing). Produces the scene radiance field; optional
  **`.ksplat`** export for web viewing.
- **Visual:** a splat render of the room (agent may render via LichtFeld, or reuse a TSDF render).
- **Speaker notes:** LichtFeld does the heavy GPU lifting — but it is a *tool we call*, not our code
  (next slide).

## Slide 9 — Architecture principle: LichtFeld is a vendored tool, Vitrine is the product
- **Purpose:** The key architecture decision / discipline.
- **Investigate:** `BOUNDARIES.md`, `CLAUDE.md` §3 & §7, `AGENTS.md`,
  `docs/docs/development/mcp/`.
- **Content:** **LichtFeld Studio** is a **pinned git submodule (v0.5.3)** we never modify; we
  update it by bumping the tag. We drive it through its **first-class local MCP server (70+ tools)**
  for training, rendering, selection-editing, and export — discovery-first, not source-diving.
  Vitrine's own code (pipeline/web/onboarding/UE overlay) is the product.
- **Visual:** a two-box diagram: "Vitrine (product)" calling "LichtFeld (vendored tool) via MCP".
- **Speaker notes:** This separation keeps us on upstream SOTA without a fork-maintenance burden.

## Slide 10 — Stage: scene mesh extraction
- **Purpose:** From splat to a real polygonal room.
- **Investigate:** `report/v5/sec_method.tex` (meshing), `docs/asset-creation-decision-tree.md`,
  engineering-log entries on CoMe/TSDF/MILo.
- **Content:** Scene mesh backends: **CoMe** (default target), **gsplat-TSDF** (stable fallback,
  the validated path), **MILo**. Followed by **MeshCleaner (smooth=0)**. Honest caveat: room mesh
  fidelity is **capture-limited** (see slide 19) — the splat is fairer than the mesh on poor captures.
- **Visual:** `docs/renders/01_tsdf_mesh_overview.jpg` + `02_tsdf_mesh_side.jpg` +
  `03_tsdf_mesh_topdown.jpg` (a 3-up).
- **Speaker notes:** TSDF is the safe scene path today; CoMe is being brought up for higher quality.

## Slide 11 — Stage: object reconstruction
- **Purpose:** The per-object asset path (where quality is routed).
- **Investigate:** `research/decisions/` (ADR-015 objects), object-recon notes,
  `src/pipeline/object_discovery.py`, `report/v5/sec_method.tex`.
- **Content:** **SAM3** concept segmentation → per-object **SAM image crops** → image-to-3D via
  **TRELLIS.2 / Hunyuan3D-2.1 / SAM3D** → **textured GLB**. Objects get the quality budget because
  the room is capture-limited. Current read: **TRELLIS.2 leads** on the dreamlab objects (verify in
  engineering-log).
- **Visual:** `docs/renders/04_object_035_room.jpg` (+ object turnaround sheet if present).
- **Speaker notes:** Objects are individually reconstructed and re-placed at their SfM location.

## Slide 12 — Stage: texture bake & FBX export
- **Purpose:** Make it game-ready.
- **Investigate:** `CLAUDE.md` §1 carve-out, `docs/ANTIPATTERNS.md`, pipeline modules
  `mesh_cleaner`, `texture_baker.bake_from_vertex_colors` (xatlas), `blender_obj_to_fbx`.
- **Content:** MeshCleaner(smooth=0) → **xatlas UV unwrap** → **texture bake from vertex colors**
  (Blender Cycles GPU) → **FBX with baked-texture materials**. This is the UE-delivery path that
  replaces native USD export.
- **Visual:** a "vertex-colored mesh → UV atlas → baked FBX" 3-step strip (agent can compose).
- **Speaker notes:** Baking is what turns research geometry into an asset an artist/engine accepts.

## Slide 13 — Stage: Unreal Engine 5.8 assembly
- **Purpose:** The payoff in-engine.
- **Investigate:** `research/decisions/` (ADR-016 UE overlay), `unreal/` (engine overlay, runtime,
  mcp_bridge), `CLAUDE.md` §6 (Unreal overlay), UE native MCP notes.
- **Content:** **In-repo UE 5.8** (no Epic gate; ADR-016). Import room + object **FBX game-assets**
  with **Nanite**; optional **NanoGS** plugin to embed *real* Gaussians; control via **Web Remote
  Control (:30010)** + experimental UE MCP. Result: an editable scene of room + interactive object
  assets.
- **Visual:** `docs/renders/05_multi_object_composed.jpg` / `07_multi_object_rear.jpg`.
- **Speaker notes:** Mention Blender is used to prove/pre-scale the scene when live UE assembly is flaky.

## Slide 14 — Decision: why not USD? (the anti-pattern that shaped the design)
- **Purpose:** Show engineering judgment via a dead-end avoided.
- **Investigate:** `docs/ANTIPATTERNS.md`, `research/decisions/` (ADR-019), `CLAUDE.md` §1 carve-out.
- **Content:** LichtFeld's native USD export emits a **`ParticleField` prim UE cannot import**, and
  UE **drops vertex colours / displayColor**. So the UE deliverable uses Vitrine's own
  **mesh→texture→FBX** path, not USD. USD remains optional/archival.
- **Visual:** a red-X "USD ParticleField → UE ✗" vs green "Mesh → bake → FBX → UE ✓" comparison.
- **Speaker notes:** This is a representative "we tried the obvious thing and it failed" decision.

## Slide 15 — Capture-conditional enhancers
- **Purpose:** Show the adaptive toolbox the router can switch in.
- **Investigate:** `docs/asset-creation-decision-tree.md` (enhancer lane), ArtiFixer notes
  (`research/landscape/artifixer-*.md`), `docker/artifixer/`.
- **Content:** The router can add enhancers when a capture needs them: **ArtiFixer** (floaters/holes
  / under-observed regions — now runs on a single 48GB Ada), **deblur** (motion blur), **densification**
  (sparse coverage). These are conditional, not always-on.
- **Visual:** the router diagram `docs/asset-creation-decision-tree.md:11` highlighting the enhancer
  branch, or a before/after ArtiFixer render if present.
- **Speaker notes:** Note ArtiFixer fixes *under-observation*, not motion blur — blur is a capture fix.

## Slide 16 — Infrastructure: containers, networks & MCP control
- **Purpose:** Show it's an engineered system, not a notebook.
- **Investigate:** `docker-compose.consolidated.yml`, `unreal/docker-compose.unreal.yml`,
  `CLAUDE.md` §5–§6, `docs/architecture.md:85`.
- **Content:** Multi-container stack: **gaussian-toolkit** (COLMAP/LichtFeld/MCP/Blender/SAM3),
  **vitrine-comfyui** (FLUX.2/TRELLIS.2/Hunyuan3D-2.1/SAM3D), **milo**, **come**, **unreal** overlay
  + **unreal-mcp-bridge**. Buses: **v2g-net** + shared **visionclaw_network**. Control surfaces:
  LichtFeld MCP `:45677`, web UI `:7860`, ComfyUI `:8188`.
- **Visual:** `docs/architecture.md:85` mermaid (render it) or `report/v5/figures/architecture.mmd`.
- **Speaker notes:** GPU work is split across containers/GPUs; everything is MCP-controllable.

## Slide 17 — SOTA discipline: always-clean, version-checked, pinned
- **Purpose:** The methodology guarantee.
- **Investigate:** `CLAUDE.md` §3 (standing directives), `research/decisions/work-order-sota-modernisation.md`
  (ADR-012), `sota_registry` (`python -m pipeline.sota_registry check`).
- **Content:** Standing rules: **always run clean SOTA**; **version-check before use, then pin**
  (no HEAD clones, no floating `latest`); a single **unified ~216 GB model tree**; a **SOTA preflight
  idiot-check** validates staged weights / VRAM / pins / licence before any run.
- **Visual:** a "check latest → pin tag/commit/checkpoint → preflight" mini-flow.
- **Speaker notes:** This is why results are reproducible and the stack stays current.

## Slide 18 — Current status & results (dreamlab e2e)
- **Purpose:** Honest state of play. **Re-derive live — do not trust stale numbers.**
- **Investigate:** **`docs/engineering-log.md`** and **`report/v5/sec_results.tex`** (authoritative,
  freshest), `CLAUDE.md` status paragraph.
- **Content:** As of the report: dreamlab e2e in progress — **scene mesh→texture→UE recipe validated
  on TSDF**; **objects partially complete via Hunyuan3D/TRELLIS.2** (state the current N/total from
  the log); **CoMe being brought up**. State what's validated vs in-progress plainly.
- **Visual:** the composed-scene renders (`05/06/07`) as evidence, or a status table.
- **Speaker notes:** Lead with what's proven; be candid about what's still building.

## Slide 19 — The dominant bottleneck: capture quality
- **Purpose:** The deck's most important honest finding.
- **Investigate:** `docs/capture-methodology.md`, frame-QA verdict notes, engineering-log.
- **Content:** The limiting factor is **capture**, not algorithms. Old footage scored **MUSIQ ~19**
  and is dominated by **motion blur** (dense, not under-observed). The real lever is **recapture**:
  **4K60 short-shutter**, deliberate coverage — not bigger models or finer voxels. Routing quality to
  *objects* is the mitigation; *room* fidelity has a capture ceiling.
- **Visual:** a blur example + a "recapture spec" card.
- **Speaker notes:** This reframes "the room mesh looks rough" from a bug to a capture limit.

## Slide 20 — Roadmap & actionable next steps
- **Purpose:** Close with direction (echo the existing deck's "Actionable" slide, but technical).
- **Investigate:** `docs/engineering-log.md` (open items), `CLAUDE.md` §1 status & stretch goals,
  `research/decisions/` open ADRs.
- **Content:** Near-term: **fresh high-quality capture**; **complete CoMe** scene meshing; finish the
  **object set**; **web NanoGS / SuperSplat** path. Later: **LichtFeld-native parity**, interactive
  elements + lighting (stretch). Plus repo entry points: `README.md`, `CLAUDE.md`,
  `report/v5/main.pdf`, the LichtFeld MCP (`AGENTS.md`).
- **Visual:** the hero `08_*` as a closing bookend, or a 2-column "Now / Next" card.
- **Speaker notes:** End on the one-line thesis from slide 1, now earned.

---

### Appendix slides (optional, if the agent wants spares)
- **A1 — Poster:** embed `report/poster/poster_a0_nanobanana.png` ("Video-to-Gaussian", Salford/DreamLab).
- **A2 — Full component menu:** render `docs/asset-creation-decision-tree.md:78`.
- **A3 — The agentic controller:** render `README.md:72` (the diagnose/select/drive-tools/eval/recover loop).
- **A4 — References:** pull key citations from `report/v5/references.bib`.

### How these assets were made (for reproducibility)
- The hero (`08_*`) was rendered from the `README.md:32` mermaid by driving a headless Chrome over
  CDP (native mermaid render → crisp, label-perfect) and, as a stylized alternative, upcycled via
  the `art` skill / `report/poster/nano_banana.py` against the Google Gemini image API.
- To regenerate any in-repo mermaid diagram as an image, render it with the mermaid CDN in a browser,
  or POST the source to `https://kroki.io/mermaid/png`.
