# DDD: ArtiFixer Reconstruction-Enhancement Context

Status: living document · Author: domain modelling pass · Date: 2026-06-23

**Scope of this model.** This document models a *new, optional* bounded context —
**Reconstruction Enhancement** — that wraps a Vitrine fork of **NVIDIA ArtiFixer**
(SIGGRAPH 2026; Wan2.1-T2V-14B auto-regressive video-diffusion 3DGS refiner) and
slots it as a **parallel reconstruction-enhancement branch** between Vitrine's SfM
and Meshing contexts. It defines the **domain language, entities/aggregates, and
the three interface contracts** that govern this branch. It is **domain model &
contracts only** — no Dockerfile/CI fork recipe (that lives in
`research/landscape/artifixer-fork-feasibility-qe.md`), no benchmark protocol.

This DDD is **subordinate to** `DDD-vitrine-mesh-pipeline.md` (the authoritative
mesh/UE delivery model). It adds one context and one adapter seam; it does not
redefine any existing context. Where this document and the parent DDD disagree on
an existing term, the parent wins.

**Explicitly out of scope / out of the delivered contract:**

- **Not a default stage.** Reconstruction Enhancement is **OPTIONAL, per-scene**,
  off by default — exactly the posture of the `come` sidecar (`INSTALL_COME=1`,
  gated, no prebuilt image). It is an *enhancement*, never a precondition for
  delivery.
- **Not a mesh producer.** ArtiFixer emits a refined **3DGRUT Gaussian
  reconstruction**, never a mesh. Meshing remains owned by Env-Mesh-Extraction
  (CoMe/TSDF). This context ends at "a better splat".
- **Not a deblurrer.** See §7 — the **acceptance gate** is a first-class part of
  this model, not a footnote. ArtiFixer fills *unobserved* regions and removes
  floaters; it stays faithful to observed (possibly motion-blurred) pixels. It is
  modelled as a candidate fix for Vitrine's **secondary** holey/under-observed
  problem, **not** the **dominant** motion-blur bottleneck.
- **Not a consumer of the LichtFeld `.ply`.** ArtiFixer trains its *own* 3DGRUT
  recon from COLMAP-posed images. It does not ingest, filter, or extend
  Vitrine's `gsplat_trainer` GaussianSplat (see §5.1 — the input is COLMAP, not
  the splat).

---

## 1. Ubiquitous Language (additions)

These terms extend the parent DDD's vocabulary (§1 of `DDD-vitrine-mesh-pipeline.md`).
Only **new or context-specific** terms are defined here; `SfM / COLMAP model`,
`GaussianSplat`, `EnvMesh / RoomMesh`, `CoordinateFrame`, and `v2g:*` carry their
parent meanings unchanged.

| Term | Definition | Where it lives |
|---|---|---|
| **Reconstruction Enhancement** | The act of taking a posed image set and producing a *cleaner, more complete* radiance reconstruction via a generative video-diffusion prior — filling unobserved regions and removing floaters/ghosts. The verb of this context. | this context; forked ArtiFixer sidecar |
| **ColmapInputs** | The posed image set ArtiFixer consumes: an `images/` directory + `sparse/0/{cameras,images,points3D}.bin`. The *only* thing that crosses from SfM into this context. Same artifact CoMe/MILo already consume. | `colmap_parser.py` (producer side), `artifixer_extractor.py` (consumer side) |
| **Degraded render** | ArtiFixer's internal name for a noisy/holey rendering of a sparse-view recon from an arbitrary viewpoint — its *input* to the diffusion prior. In Vitrine terms, the symptom we are trying to fix (holes, floaters). Faithfully preserved where opacity≈1. | ArtiFixer `model_eval`; conceptual only — never a Vitrine artifact |
| **Opacity map (`O_z`)** | A per-pixel rendered opacity in latent space. ArtiFixer's **core trick**: `z_mix = O_z·z_deg + (1−O_z)·ε` — keep the degraded latent where opacity≈1 (faithful to *observed* content), inject Gaussian noise where opacity≈0 (generate freely in *unobserved* regions). This is *why* ArtiFixer fills holes but does **not** deblur observed pixels. | ArtiFixer internal; the mechanism behind the §7 gate |
| **Enhancement** | One run of the `ArtiFixer3D` variant over a scene's ColmapInputs: train a 3DGRUT recon (~10k iters) → roll out the 4-step causal AR generator → distil generated views back into a cleaner explicit 3DGRUT recon. The unit of work of this context. | `artifixer_extractor.run_artifixer` (the entry point) |
| **RefinedSplat (3DGRUT)** | ArtiFixer3D's output: an explicit **3DGRUT** Gaussian reconstruction (distilled, artifact-reduced). The deliverable of this context. **Flavour-distinct** from LichtFeld's GaussianSplat (see §5.2 ADAPTER open unknowns). | ArtiFixer3D output dir; consumed by the adapter |
| **Holey vs. blurry** | The discriminating language for *what this context can and cannot fix*. **Holey** = under-observed / missing / floater-corrupted geometry → ArtiFixer's target. **Blurry** = motion-blurred but *observed* pixels → ArtiFixer is faithful to these, does **not** sharpen them. The §7 gate exists to keep these separated in every decision. | this whole document; the acceptance gate |
| **EnhancedReconstruction** | The aggregate (see §3.3) wrapping a RefinedSplat plus its provenance + the adapted `.ply` that Meshing consumes. The thing that re-enters the parent pipeline. | `artifixer_extractor.py` output dict + adapted ply |

**Naming discipline.** "ArtiFixer3D" is the variant we use (wins PSNR/SSIM + best
multi-view consistency, renders an explicit recon). Plain "ArtiFixer" (sharper 2D
renders, no explicit recon) and "ArtiFixer3D+" (re-sharpen pass) are out of scope
for the mesh path; do not let their language leak into Vitrine code or config.

---

## 2. Bounded Context placement

Reconstruction Enhancement is a **Supporting** context (like Env-Mesh-Extraction
and Texturing) — it improves the delivered artifact but is never on the critical
path by default. It inserts a *fork in the lineage* after SfM: the parent pipeline
can take the direct route (LichtFeld GaussianSplat → mesh) or the enhanced route
(ColmapInputs → RefinedSplat → mesh).

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  Vitrine context map with the OPTIONAL Reconstruction-Enhancement branch         │
│                                                                                 │
│  ┌────────────┐   ┌─────────────────────────────┐                               │
│  │ Ingest&QA  │──▶│ Reconstruction (SfM + 3DGS)  │                              │
│  │ (CORE)     │   │ CORE                          │                             │
│  └────────────┘   │  COLMAP model ───────────────┼──┐  ColmapInputs              │
│       frames      │  GaussianSplat (LichtFeld)    │  │  (images/ + sparse/0/*.bin)│
│                   └──────────────┬────────────────┘  │                          │
│                                  │ splat (direct route, default)                │
│                                  │                    ▼                          │
│                                  │      ┌──────────────────────────────────┐    │
│                                  │      │ Reconstruction Enhancement       │    │
│                                  │      │ (SUPPORTING, OPTIONAL, per-scene)│    │
│                                  │      │  forked ArtiFixer3D sidecar      │    │
│                                  │      │  → RefinedSplat (3DGRUT)         │    │
│                                  │      └─────────────────┬────────────────┘    │
│                                  │            ╔═══════════▼════════════╗         │
│                                  │            ║  ADAPTER (ACL)         ║         │
│                                  │            ║  3DGRUT → LichtFeld    ║         │
│                                  │            ║  .ply flavour          ║         │
│                                  │            ╚═══════════╤════════════╝         │
│                                  │                        │ adapted .ply         │
│                                  ▼                        ▼                      │
│                       ┌──────────────────────────────────────────┐              │
│                       │ Env-Mesh-Extraction (CoMe / TSDF) SUPP    │  ◀ GATE §7  │
│                       └──────────────────┬───────────────────────┘              │
│                                          ▼  RoomMesh                             │
│                          Texturing → UE-Assembly  (unchanged, parent DDD)        │
└───────────────────────────────────────────────────────────────────────────────┘
```

| Context | Type | Relationship to Reconstruction Enhancement |
|---|---|---|
| **Ingest & QA** | Core | Upstream-of-upstream. Its **MUSIQ gate** is what decides whether a scene is *blurry* — and blur is exactly what this context cannot fix (§7). The two are complementary, not substitutes. |
| **Reconstruction (SfM + 3DGS)** | Core | **Supplier** of `ColmapInputs` (the COLMAP model). It is *not* a supplier of its GaussianSplat to this context (ArtiFixer ignores the `.ply`). The branch point lives here. |
| **Reconstruction Enhancement** | Supporting (new) | **This context.** Consumes ColmapInputs; produces RefinedSplat + adapted `.ply`. |
| **Env-Mesh-Extraction (CoMe/TSDF)** | Supporting | **Customer.** Consumes the adapted `.ply` exactly as it would the LichtFeld splat. The §7 acceptance gate is enforced *at this boundary* (did the enhanced mesh actually beat the direct mesh?). |
| **Texturing / UE-Assembly** | Supporting / Generic | **Unaware.** They see only "a mesh"; whether it came from the direct or enhanced route is invisible to them. No changes. |

**Why a new context and not a setting on Reconstruction.** The *language* changes
at this seam (degraded render, opacity map, AR rollout, 3DGRUT flavour), the
*runtime* changes (a separate forked sidecar with its own CUDA/torch stack), and
the *trust model* changes (a generative prior *invents* geometry — the parent
Reconstruction context never does). Folding it into Reconstruction would blur all
three. It is its own context, gated behind its own ACL, exactly like CoMe.

---

## 3. Aggregates, Entities & Value Objects

Convention (as parent DDD): **AR** = aggregate root, **E** = entity, **VO** = value
object.

### 3.1 Scene (the lineage anchor)

- **Scene** (AR) — the per-scene unit of enhancement work; the decision boundary
  for "enhance or not". Identity = the scene/run id already used by the
  orchestrator. It owns the choice of route (direct vs enhanced) and the §7
  verdict.
  - **EnhancementDecision** (VO) — `{enabled: bool, reason, scene_type∈{bounded,unbounded}}`.
    Mirrors `CoMeConfig.scene_type`; defaults to *disabled*.
  - *Invariant:* a Scene may only enter Reconstruction Enhancement if SfM has
    produced valid ColmapInputs (§3.2) **and** the scene was not flagged unusable
    by the MUSIQ gate. (Enhancing a scene the QA gate already rejected for blur is
    pointless — §7.)

### 3.2 ColmapInputs (the input aggregate — shared kernel with SfM)

- **ColmapInputs** (AR) — the posed image set, owned upstream by the
  Reconstruction context's `ColmapModel`, *read-only* here.
  - **PosedImageSet** (VO) — `{images_dir: Path, sparse_dir: Path}` where
    `sparse_dir` holds `cameras.bin`, `images.bin`, `points3D.bin`. Same shape
    `come_extractor._find_sparse_dir` / `_find_dataset_root` already resolve.
  - *Invariant:* this context **never mutates** ColmapInputs. It is a Shared
    Kernel borrowed from Reconstruction (the one COLMAP CoordinateFrame). ArtiFixer
    reads poses; it must not re-solve or re-export them upstream.

### 3.3 EnhancedReconstruction (the output aggregate)

- **EnhancedReconstruction** (AR) — one completed Enhancement: the RefinedSplat
  plus its adapted `.ply` and provenance. The thing that re-enters the parent
  pipeline at Meshing.
  - **RefinedSplat** (VO) — `{format: "3dgrut", recon_dir: Path, native_ply: Path}`
    — ArtiFixer3D's explicit Gaussian recon in *its own* on-disk layout.
  - **AdaptedSplat** (VO) — `{ply_path: Path, gaussian_flavour: "lichtfeld",
    sh_degree, gaussian_count}` — the `.ply` produced by the ADAPTER (§5.2),
    field-compatible with what CoMe/TSDF parse today.
  - **EnhancementProvenance** (VO) — the `v2g:*` extension for this branch:
    `{v2g:recon_backend: "artifixer3d", v2g:recon_enhanced: true,
    v2g:artifixer_commit, v2g:artifixer_weights_sha, v2g:enhance_iters,
    v2g:ar_steps, v2g:frames_per_block}`. Carried so the final GameAsset can be
    traced to the enhanced (vs direct) route.
  - *Invariant:* an EnhancedReconstruction exists **iff** the ADAPTER has produced
    an AdaptedSplat in the LichtFeld `.ply` flavour. A raw 3DGRUT recon dir is
    **not** a valid output of this context — Meshing cannot consume it (§5.2).

**Aggregate boundary note.** Scene is the *consistency boundary* for the
enhance/skip decision and the §7 verdict; EnhancedReconstruction is the
*consistency boundary* for "a usable enhanced splat exists". The two never share
mutable state — Scene holds the decision, EnhancedReconstruction holds the result.

---

## 4. Domain Events / branch flow

The enhancement branch is event-ordered like the parent pipeline. Events here slot
*between* `SfmSolved` and `EnvMeshExtracted` from the parent DDD's §4.

```
SfmSolved                     (reconstruct)        Frames → ColmapModel  [parent context]
  ├─(direct route, default)──▶ SplatTrained        ColmapModel → LichtFeld GaussianSplat
  └─(enhanced route, opt-in)
        EnhancementRequested   (per-scene gate)     Scene marked for enhancement   ◀ OPT-IN
        ColmapInputsHandedOff  (—)                  PosedImageSet validated + passed to sidecar
        EnhancementRan         (artifixer_extractor) ColmapInputs → RefinedSplat (3DGRUT) [sidecar]
        SplatAdapted           (artifixer_extractor) RefinedSplat → AdaptedSplat (.ply)   ◀ ADAPTER
  ──────────────────────────▶ EnvMeshExtracted     adapted .ply → RoomMesh  [parent CoMe/TSDF]
        EnhancementAccepted?   (§7 acceptance gate) did enhanced mesh beat direct mesh?  ◀ GATE
```

The two routes **rejoin at `EnvMeshExtracted`**: from Meshing onward the parent
pipeline is identical. The only artifact that crosses back in is the AdaptedSplat
`.ply`. `EnhancementAccepted?` is a *measured* gate (§7), not an automatic pass —
on a real dreamlab scene, the enhanced route must demonstrably improve the
downstream mesh, or the Scene reverts to the direct route.

---

## 5. Interface Contracts (the load-bearing section)

Three contracts govern this context. (a) and (c) are *reused/established* shapes;
(b) is the **new, genuinely uncertain** seam and gets the most detail.

### 5.1 (a) Input contract — from SfM (`ColmapInputs`)

**Supplier:** Reconstruction (SfM). **Consumer:** Reconstruction Enhancement.
**Pattern:** Shared Kernel (the one COLMAP CoordinateFrame) + Customer–Supplier.

ArtiFixer's shipped entry point consumes a **COLMAP-posed image set** — precisely
what Vitrine already produces via ALIKED+LightGlue SfM and what CoMe/MILo already
consume. The contract is therefore *already satisfied* by existing artifacts.

| Field | Producer | Expectation |
|---|---|---|
| `images/` | `stages.py::reconstruct` | Undistorted RGB frames, the admitted (post-MUSIQ-gate) keep-set. Filenames must match `images.bin` entries. |
| `sparse/0/cameras.bin` | COLMAP | Intrinsics. ArtiFixer + 3DGRUT read the COLMAP camera model. |
| `sparse/0/images.bin` | COLMAP | Per-frame extrinsics (poses) in the COLMAP frame. |
| `sparse/0/points3D.bin` | COLMAP | Sparse point cloud (3DGRUT init). |

**Contract guarantees / absorbed quirks:**
- Discovery reuses `_find_sparse_dir` / `_find_dataset_root` (already proven in
  `come_extractor.py`, mirrored from MILo) — ArtiFixer wants the *dataset root*
  containing both `sparse/` and `images/`, identical to CoMe.
- **No `.ply` is passed.** This is the key asymmetry vs the direct route:
  ArtiFixer ignores `gsplat_trainer`'s GaussianSplat and trains its **own** 3DGRUT
  recon (~10k iters) from these inputs. The LichtFeld training stage and the
  enhancement branch are *parallel consumers of the same ColmapInputs*, not
  pipeline-sequential.
- The CoordinateFrame is borrowed read-only. ArtiFixer's RefinedSplat **must come
  back in the same COLMAP frame** so CoMe/TSDF mesh it without a re-solve. This is
  an explicit ADAPTER obligation (§5.2) and an open unknown to verify (does 3DGRUT
  preserve the COLMAP world frame, or apply a normalisation/recentre?).

### 5.2 (b) ADAPTER contract — `RefinedSplat (3DGRUT)` → LichtFeld `.ply`  ⚠ NEW SEAM

**Supplier:** ArtiFixer3D (3DGRUT recon). **Consumer:** Env-Mesh-Extraction
(CoMe/TSDF). **Pattern:** Anti-Corruption Layer (the adapter *is* the ACL).
**Code home:** `src/pipeline/artifixer_extractor.py` (§6).

This is the only genuinely novel contract. CoMe/TSDF consume a **LichtFeld-flavour
Gaussian `.ply`**; ArtiFixer3D emits a **3DGRUT-flavour** recon. The adapter must
translate one into the other — or prove they are already compatible.

**Target `.ply` field layout (what CoMe/TSDF consume today).** Verified against
`src/pipeline/mesh_extractor.py` (the canonical Vitrine splat-ply reader):

```
x, y, z, nx, ny, nz,
f_dc_0..2,           # SH band-0 (diffuse colour), 3 coeffs
f_rest_0..N,         # SH higher bands — Vitrine reader counts what is present
                     #   and zero-pads up to degree-3 (45 rest coeffs); it does
                     #   NOT assume a fixed 45 (a real recon emitted fewer →
                     #   the hardcoded range(45) bug; now n_rest is counted)
opacity,             # logit-space; reader applies sigmoid downstream
scale_0..2,          # LOG-space; reader applies exp()
rot_0..3             # quaternion (w,x,y,z order per the reader's column stack)
```

**ADAPTER obligations:**

| Concern | Obligation |
|---|---|
| **Field naming** | Emit exactly the `f_dc_*` / `f_rest_*` / `opacity` / `scale_*` / `rot_*` property names above. 3DGRUT may name/store these differently — the adapter renames. |
| **SH layout** | Match the reader's tolerant SH handling: emit `f_rest_0..N` for whatever band count 3DGRUT uses; the reader zero-pads to degree-3. **Open unknown:** 3DGRUT's SH convention/ordering — confirm coefficient interleaving matches `f_dc` then per-band `f_rest`, not an alternative packing. |
| **Activation space** | The reader applies `exp()` to scales and treats opacity as logit (sigmoid). **Open unknown (critical):** does 3DGRUT store scales already-activated (linear) or log-space, and opacity activated (0..1) or logit? A mismatch silently produces a degenerate mesh (giant/zero Gaussians). The adapter must detect and convert to LichtFeld's log/logit convention. |
| **Quaternion order** | Reader stacks `rot_0..3` as `(w,x,y,z)` (or `(x,y,z,w)` — verify the column order in `mesh_extractor`). 3DGRUT's quaternion order must be matched/reordered. |
| **Coordinate frame** | RefinedSplat must land in the **COLMAP world frame** (§5.1). If 3DGRUT recenters/normalises, the adapter inverts that transform back to COLMAP before writing the `.ply`. |
| **3DGRUT-vs-3DGS flavour** | **The headline open unknown.** 3DGRUT (3D Gaussian *Ray Tracing*) and LichtFeld's 3DGS (rasteriser) are *both* explicit Gaussian clouds, but may differ in: SH degree, whether a `nx,ny,nz` normal block is present (Vitrine reader reads it but mesh backends may not need it), per-Gaussian density/opacity semantics, and any 3DGUT-rasterizer-specific extra attributes. **The adapter must be validated empirically** — the cleanest path is to round-trip one ArtiFixer3D recon through the adapter into CoMe/TSDF and inspect the mesh, exactly as the §7 first experiment does. |

**Adapter output = AdaptedSplat (VO, §3.3).** A single `.ply` at a known path, plus
metadata (`gaussian_flavour="lichtfeld"`, `sh_degree`, `gaussian_count`) so the
caller can assert the conversion before handing to Meshing.

**Failure mode the ACL must absorb.** If the activation-space or quaternion
conventions are guessed wrong, the `.ply` *parses fine* but meshes into garbage.
The adapter therefore carries a **sanity assertion** (e.g. median Gaussian scale in
a plausible metric range for the scene) and raises rather than emitting a silently
degenerate splat — the same defensive posture `come_extractor` takes around
sidecar failure.

### 5.3 (c) Orchestration boundary — sidecar exec (like milo/come)

**Pattern:** Anti-Corruption Layer over a sidecar CLI, identical in shape to
`come_extractor` / `milo_extractor`.

The forked ArtiFixer runs in its **own sidecar container** (its CUDA 12.8 / torch
2.11 / NGC 25.01 stack is incompatible with the main container, exactly as CoMe's
CUDA 12.1 / Py3.10 stack is). Orchestration is **host-only `docker exec`** into
that sidecar — no docker-in-docker, respecting the §6 Vitrine topology rule.

The entry point follows the **ADR-003 mesh-backend interface** (three public
symbols), adapted from a *mesh* backend to a *recon-enhancement* backend:

```python
@dataclass
class ArtiFixerConfig:
    enhance_iters: int = 10_000        # 3DGRUT training iters
    ar_steps: int = 4                  # causal AR distillation steps (hard default)
    frames_per_block: int = 7          # kv_cache chunk; CP must divide gcd(7,7,21)=7
    context_parallel_size: int = 1     # CP=1 — CP=2 rejected for the AR pipeline
    scene_type: str = "unbounded"      # bounded|unbounded (mirrors CoMeConfig)
    captioning_model_id: str | None = None   # Qwen3-VL prep caption; None = skip
    train_timeout: int = 7200
    enhance_timeout: int = 3600

def is_artifixer_available() -> bool:
    """True if the forked artifixer sidecar (docker exec) is reachable."""

def run_artifixer(colmap_dir: str, output_dir: str,
                  config: ArtiFixerConfig | None = None) -> dict[str, Any]:
    """ColmapInputs → RefinedSplat → AdaptedSplat (.ply). Never raises to caller;
    errors captured in the returned dict (same contract as run_come)."""
```

**Sidecar contract / absorbed quirks** (the ACL's job):
- Probe the `artifixer` sidecar via `docker exec ... python -c "import torch"`
  (mirrors `_come_exec_prefix`); container working dir set with `-w`, host cwd
  `None` (the `_run_cwd` pattern — container paths don't exist on the host).
- Translate ArtiFixer's `model_eval.run_inference` CLI flags
  (`--checkpoint_pt`, `--context_parallel_size 1`, `--inference_pipeline` AR,
  COLMAP source/output dirs) into the `run_artifixer` call — never expose them
  upward.
- **Do not** pass `--attention_backend _flash_3` (sm_89 default = cuDNN SDPA; the
  fork strips FA3/FA4). bf16 is the hard default; never request fp8.
- 2-card use = **data-parallel scene round-robin** (CP=1), not CP=2. If the
  orchestrator enhances multiple scenes, it may dispatch them across the two Ada
  cards; the ACL exposes a `device`/`gpu_id` parameter for that, but a single
  Enhancement uses one 48 GB card.
- **Licensing gate** (mirrors `is_come_available`'s ADR-004 warning): emit a
  WARNING that ArtiFixer **weights** are NVIDIA OneWay Noncommercial (code is
  Apache-2.0). Fine for this non-commercial research project; the warning keeps
  the boundary explicit. Make the sidecar an explicit opt-in build arg
  (e.g. `INSTALL_ARTIFIXER=1`), no prebuilt image — the `come` posture exactly.

---

## 6. Where the adapter code lives & fork-boundary compliance

| Artifact | Location | Rationale |
|---|---|---|
| **Adapter / orchestration** | `src/pipeline/artifixer_extractor.py` | Our-additions tree (§7 BOUNDARIES). New backend module, `{name}_extractor.py` naming convention (ADR-003 §"New backend modules"). Implements the three-symbol interface. |
| **Forked ArtiFixer source** | git submodule under `external/`-equivalent in our tree **or** baked into the sidecar image; **never** in upstream LichtFeld dirs | Apache-2.0 code; the Dockerfile/CI fork (strip FA3/FA4, relax CI asserts) lives in `docker/` per the QE recipe. |
| **Sidecar image / compose** | `docker/Dockerfile.artifixer` + a service in `docker-compose.consolidated.yml` (gated, off by default) | Mirrors the `milo`/`come` sidecar pattern; host-only build. |
| **Config key** | `config.training.recon_enhance: "none" | "artifixer3d"` (default `"none"`) | Parallel to `config.training.mesh_method`; selection lives in `stages.py`, not `orchestrator.py` (ADR-003 dispatch rule). |
| **Provenance** | `v2g:recon_*` keys threaded through `stages.py` / `manifest.py` | Extends the existing `v2g:*` lineage so the enhanced route is traceable. |

**Boundary compliance.** This context touches **only** our-additions trees
(`src/pipeline/`, `docker/`, config, docs). It modifies **no** upstream LichtFeld
directory. The forked ArtiFixer is a sidecar + submodule, never merged into
LichtFeld; it is GPL-incompatible-free (Apache-2.0 code in its own process,
non-commercial weights — fine for research). One-way: we never push to NVIDIA's
ArtiFixer repo.

---

## 7. The acceptance gate (the load-bearing rule for this context)

> **Reconstruction Enhancement MAY be adopted for a scene ONLY IF, on a real
> dreamlab capture, the enhanced route produces a measurably better downstream
> mesh than the direct route. ArtiFixer fills HOLES; it does NOT deblur OBSERVED
> pixels. It must therefore be validated against Vitrine's actual failure mode
> (holey, secondary) and must NOT be sold as a fix for the dominant failure mode
> (motion blur).**

This mirrors the **bake invariant**'s status in the parent DDD: it is the single
rule that justifies this context's existence and bounds its claims.

Why it is first-class, not a caveat:
- The **opacity-mix mechanism** (`z_mix = O_z·z_deg + (1−O_z)·ε`, §1) *guarantees*
  faithfulness to observed pixels where opacity≈1. Motion-blurred-but-observed
  geometry sits at opacity≈1 → ArtiFixer reproduces the blur, does not sharpen it.
  This is architectural, not tunable.
- Every published ArtiFixer benchmark is **sparse-but-sharp** input (Nerfbusters,
  DL3DV, Mip-NeRF 360 sparse-view). **None** is dense-but-motion-blurred. The
  benchmark regime ≠ Vitrine's dreamlab regime (MUSIQ ~31, motion blur dominant).
- Blur remains an **upstream** fix (frame-QA rejection / deblur / **recapture**,
  per `frame-qa-sota-and-data-verdict`). Reconstruction Enhancement is
  **complementary** to the MUSIQ gate, never a substitute.

**Gate enforcement point.** The `EnhancementAccepted?` event (§4) is evaluated at
the Env-Mesh-Extraction boundary: mesh the **direct** splat and the **adapted**
splat for the same dreamlab scene, compare the meshes (hole/floater reduction in
under-observed regions; no regression elsewhere). Only a demonstrated win promotes
`recon_enhance` from per-scene experiment to a recommended option. Until then it
stays **off by default**, an opt-in experiment — never a pipeline commitment.

**First experiment (the open question this DDD does not pre-answer).** *Does
ArtiFixer3D measurably de-hole/de-noise a real dreamlab splat, or only the
sparse/holey benchmark regime it was trained on?* Answer on one scene first, by
eyeballing the enhanced→adapted→CoMe/TSDF mesh against the current direct mesh.
The ADAPTER unknowns in §5.2 (flavour, activation space, quaternion order, frame)
are resolved on this same run.

---

## 8. Context-mapping patterns

| Relationship | Pattern | Rationale |
|---|---|---|
| Reconstruction (SfM) → Reconstruction Enhancement | Shared Kernel (CoordinateFrame) + Customer–Supplier (ColmapInputs) | The posed image set is the borrowed, read-only contract; the COLMAP frame is shared, never re-solved. |
| Reconstruction Enhancement → Env-Mesh-Extraction | Anti-Corruption Layer (the ADAPTER) | 3DGRUT flavour is translated into LichtFeld `.ply` flavour; CoMe/TSDF never see 3DGRUT's model. |
| Pipeline ↔ forked ArtiFixer sidecar | Anti-Corruption Layer (sidecar CLI) | `artifixer_extractor.py` hides the sidecar's flags/CUDA stack/AR config — same as `come_extractor` hides CoMe. |
| Reconstruction Enhancement ↔ direct route | Conformist (toward Meshing) | The enhanced route conforms to the *same* `.ply`→mesh contract the direct route already satisfies; Meshing is route-agnostic. |
| Ingest&QA (MUSIQ gate) ↔ Reconstruction Enhancement | Separate Ways (complementary, non-overlapping) | Blur is fixed upstream by QA; holes are (maybe) fixed here. The §7 gate keeps the two concerns from being conflated. |

---

## 9. Mapping summary: context → code home

```
Reconstruction Enhancement  → src/pipeline/artifixer_extractor.py
  (input ACL)                 reuses come_extractor's _find_sparse_dir/_find_dataset_root pattern
  (orchestration ACL)         docker exec into `artifixer` sidecar  (milo/come pattern)
  (ADAPTER ACL)               3DGRUT recon → LichtFeld .ply (fields per mesh_extractor.py)
Forked ArtiFixer (Apache-2.0) → submodule + docker/Dockerfile.artifixer (host-only build, gated)
Sidecar service               → docker-compose.consolidated.yml  (INSTALL_ARTIFIXER=1, off by default)
Backend selection             → stages.py  (config.training.recon_enhance, ADR-003 dispatch rule)
Provenance                    → stages.py / manifest.py  (v2g:recon_* keys)
Acceptance gate (§7)          → evaluated at the Env-Mesh-Extraction boundary, per-scene
```

---

## 10. Relationship to prior docs

- **Subordinate to** `DDD-vitrine-mesh-pipeline.md` — adds one Supporting context
  and one ACL adapter; redefines nothing in the parent.
- **Implements the interface of** `adr-003-pluggable-mesh-extraction-backends.md`
  — the three-symbol pattern (`XConfig` / `is_X_available` / `run_X`), generalised
  from a *mesh* backend to a *recon-enhancement* backend. ADR-003's own §Risks
  anticipated this ("a future backend [that] requires … pre-trained Gaussian
  weights rather than COLMAP directory" — here the divergence is the *output* side:
  a 3DGRUT recon needing an adapter, absorbed by `XConfig`/the ACL).
- **Grounded in** `research/landscape/artifixer-2026-evaluation.md` (model
  evaluation, quality-fit verdict) and `artifixer-fork-feasibility-qe.md` (sm_89
  fork feasibility, CP=1, bf16, sidecar recipe) — all engineering facts are cited
  from those, not re-derived here.
- **Complements** the MUSIQ-gate decision in `frame-qa-sota-and-data-verdict`
  (memory) — blur is an upstream QA/recapture problem; this context targets holes.
- A future **ADR** ("ArtiFixer as optional recon-enhancement backend") should
  ratify the §7 gate outcome and pin the fork commit/weights SHA before any
  default-on promotion.
```
