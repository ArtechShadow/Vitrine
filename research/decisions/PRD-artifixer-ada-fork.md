# PRD — ArtiFixer (Ada fork) as an optional reconstruction-enhancement stage

| | |
|---|---|
| **Status** | Proposed (experiment-gated; not yet committed to the pipeline) |
| **Owner** | Vitrine pipeline |
| **Date** | 2026-06-23 |
| **Scope** | **Product / requirements only.** The architecture decision (sidecar vs. submodule, adapter shape) and the domain model are **sibling docs**, not this one. |
| **Sibling docs (to be authored)** | ADR — ArtiFixer Ada-fork integration architecture; DDD addendum — refined-3DGRUT recon context |
| **Ground truth (read first)** | `research/landscape/artifixer-2026-evaluation.md` (candidate eval), `research/landscape/artifixer-fork-feasibility-qe.md` (QE source audit, file:line-verified) |
| **Relates to** | ADR-017 (generative view completion), ADR-003 (pluggable mesh backends), ADR-019 (FBX game-asset delivery), `frame-qa-sota-and-data-verdict`, `dreamlab-mesh-into-ue-pipeline` |

---

## 1. Problem & motivation

**Problem.** Vitrine reconstructions are **noisy and holey in under-observed
regions.** Where the capture circled an object or wall thoroughly, the 3DGS recon
is dense; where it did not — occluded corners, the floor, the backs of objects,
anything filmed from only one side — the splat has few or no Gaussians. Those gaps
become **floaters, ghost geometry, and missing surface** that propagate downstream
into the CoMe / gsplat-TSDF environment mesh (holes, stray bridging triangles) and
the per-object hulls. This is a real, *secondary* quality bottleneck distinct from
the dominant motion-blur ceiling (see §3, §7).

**The opportunity.** **NVIDIA ArtiFixer** (SIGGRAPH 2026; arXiv:2603.00492) is a
generative **refiner/extender** built on Wan2.1-T2V-14B that sits on top of an
existing sparse-view 3DGS/3DGRUT recon and produces **artifact-free novel-view
renderings from arbitrary viewpoints — including regions the cameras never
observed.** Its opacity-mixing trick (`z_mix = O_z·z_deg + (1−O_z)·ε`) stays
faithful to observed pixels and **generates freely only where opacity ≈ 0**, i.e.
exactly the unobserved regions that hole our recon. The **ArtiFixer3D** variant
distills those generated views back into an explicit **3DGRUT Gaussian recon**,
winning PSNR/SSIM and best multi-view consistency (MEt3R) — i.e. it can emit a
*cleaner Gaussian scene*, which is what we would feed to CoMe/TSDF for a better
mesh.

**Why now (the blocker that just fell).** ArtiFixer ships pinned to Hopper/Blackwell
(`sm_90/sm_100`). A QE source audit
(`artifixer-fork-feasibility-qe.md`, every load-bearing claim file:line-verified)
established that the requirement is **artificial — packaging-only**, not a math/kernel
dependency:

- The only `get_device_capability()` consumer
  (`model_training/net/transformer.py:158/184`) is a *perf-backend selector* that
  falls through every Hopper/Blackwell branch and returns `None` → **cuDNN SDPA on
  sm_89 with no raise**. FA3 import is `try/except`; `set_attention_backend` is
  guarded and never called on sm_89.
- The entire lock-in lives in `Dockerfile.cuda12` FA3/FA4 build steps (lines 27–42)
  + build-time CI asserts (52–54).
- The 3DGRUT submodule builds on Ada via JIT `cpp_extension.load`
  (`-DTCNN_MIN_GPU_ARCH=70`; default prep = 3DGUT rasterizer, no OptiX/RT).

**Fork = strip those Docker lines + relax the CI asserts. ZERO application-code
changes. ~1.5–2 person-days.** Inference is **bf16** (~28 GB transformer) and fits
**one** 48 GB RTX 6000 Ada under the chunked `kv_cache` pipeline. Hardware is no
longer the blocker — so the only remaining question is **whether it actually helps
our data**, which this PRD exists to make us answer **before** committing to any
pipeline wiring.

---

## 2. Goals & non-goals

### 2.1 Goals

1. **G1 — It runs on our hardware.** A forked ArtiFixer image runs end-to-end
   inference (and one prep pass) on a single RTX 6000 Ada (sm_89, 48 GB, 200 W-capped),
   producing valid output, with zero application-code changes (build/CI edits only).
2. **G2 — Measure whether it helps a real Vitrine scene.** Run ArtiFixer3D on **one
   real dreamlab scene** and measure, against the current CoMe/TSDF baseline, whether
   it **measurably de-holes / de-noises** the splat and the resulting mesh. This is
   the decisive, first-class **acceptance gate** (§5).
3. **G3 — If (and only if) G2 passes, integrate as an OPTIONAL per-scene
   enhancement.** Slot ArtiFixer3D as a **parallel recon-enhancement branch** after
   COLMAP SfM, with an **adapter** from its 3DGRUT Gaussian output to the `.ply` that
   CoMe/TSDF consume. Off by default; opt-in per scene.
4. **G4 — Respect Vitrine boundaries.** The fork lives as a **sidecar
   container / submodule + a `src/pipeline` adapter**, never touching upstream
   LichtFeld dirs; built host-only; non-commercial weights are fine for this research
   project.

### 2.2 Non-goals (explicitly out of scope)

These are **not** what this work is for. Do not justify ArtiFixer on them, and do
not let scope creep toward them.

1. **NOT a deblur fix.** ArtiFixer's opacity-mix stays faithful to observed pixels
   (opacity ≈ 1), so it **does not deblur** motion-blurred input. It will *not* solve
   Vitrine's **dominant** bottleneck (motion blur, dreamlab MUSIQ ~31). Blur stays an
   **upstream** problem — frame-QA rejection / deblur / **recapture** (per
   `frame-qa-sota-and-data-verdict`). Any framing of ArtiFixer as a sharpness/blur
   remedy is wrong and out of scope.
2. **NOT a commercial path.** ArtiFixer weights are **NVIDIA OneWay Noncommercial**.
   This is fine for our non-commercial university research, but the enhanced recon
   and any mesh derived from it are **research/eval artifacts only** — never a
   commercial-track deliverable. (Mirrors the existing CoMe non-commercial posture.)
3. **NOT a replacement for LichtFeld 3DGS training.** ArtiFixer trains its **own**
   3DGRUT recon from COLMAP-posed images; it does **not** consume the LichtFeld
   `.ply` and produces **no mesh**. It is an *optional alternative recon source* for
   the mesh stage, not a replacement for LichtFeld's ImprovedGS+ training, the mesh
   backends (CoMe/TSDF), or the FBX→UE delivery path (ADR-019).
4. **NOT a mesh generator.** ArtiFixer emits Gaussians, not polygons. The mesh still
   comes from CoMe / gsplat-TSDF downstream of the adapter.
5. **NOT a CP=2 / multi-GPU model-parallel effort.** CP=2 is rejected for the default
   AR pipeline (CP must divide `gcd(7,7,21)=7`). The 2nd card is **data-parallel scene
   round-robin** only; no model sharding work is in scope.
6. **NOT a from-scratch ArtiFixer reimplementation.** We fork and minimally patch the
   released Apache-2.0 code; we do not rebuild the model or its training.

---

## 3. Primary hypothesis to validate

> **H1 (decisive).** Running **ArtiFixer3D** on a real dreamlab scene's
> COLMAP-posed image set produces a refined 3DGRUT Gaussian recon that, after the
> adapter → CoMe/TSDF mesh step, is **measurably less holey and less noisy** (fewer
> floaters, more complete surface in under-observed regions) than the current
> CoMe/TSDF mesh built from the LichtFeld recon — **on Ada, on our real
> (dense + motion-blurred) capture**, not merely on the sparse-but-sharp benchmark
> regime ArtiFixer was published on.

**Why this is in question.** Every ArtiFixer benchmark (Nerfbusters, DL3DV,
Mip-NeRF 360) is **sparse-but-sharp** input. Vitrine's dreamlab data is the
opposite: **dense but motion-blurred** (MUSIQ ~31). The generative prior may fill
holes beautifully on sparse-sharp data yet add little — or fight the blurry observed
pixels — on our regime. **H1 must be tested on real dreamlab data before any
integration investment.**

**Secondary hypotheses (informational, not gating):**

- **H2.** The throughput penalty of cuDNN SDPA (vs. the FA3/FA4 the model expects),
  under the 200 W cap, leaves per-scene wall-clock within an acceptable budget for an
  *optional* stage.
- **H3.** The 3DGRUT→`.ply` adapter preserves enough fidelity (positions, opacities,
  SH/colour) that the CoMe/TSDF mesh quality reflects the enhancement rather than
  adapter loss.

---

## 4. User / operator stories

| # | As a … | I want … | so that … |
|---|---|---|---|
| US-1 | Pipeline operator | to build a forked ArtiFixer image that runs on our RTX 6000 Ada (sm_89) | I'm not blocked by the artificial Hopper/Blackwell pin and don't need cloud H100s. |
| US-2 | Pipeline operator | to run ArtiFixer3D on **one** dreamlab scene and get a side-by-side (enhanced vs. baseline) splat + mesh | I can see, on our own data, whether it helps before anyone wires it into the pipeline. |
| US-3 | Reconstruction lead | a **measurable** de-hole / de-noise verdict (a number + a pass bar), not just "looks nicer" | the go/no-go on integration is evidence-based and reproducible. |
| US-4 | Pipeline operator (post-P1 pass) | to enable ArtiFixer3D **per scene** with an opt-in flag, feeding CoMe/TSDF via an adapter | I can apply it only to scenes with bad under-observed regions, leaving others on the cheap default path. |
| US-5 | Pipeline operator | the enhancement to slot in **after COLMAP SfM** using the `images/ + sparse/0/*.bin` Vitrine already produces | I reuse the existing ALIKED+LightGlue SfM and don't duplicate posing. |
| US-6 | Maintainer | the fork to live in a sidecar container/submodule + a `src/pipeline` adapter, host-built, never touching upstream | the fork boundary and host-only Docker policy hold, and upstream sync stays one-way. |
| US-7 | Maintainer | clear "this is non-commercial, research/eval only" provenance on any ArtiFixer-derived artifact | the NVIDIA non-commercial weight licence is never violated downstream. |
| US-8 | Reconstruction lead | a no-go to be cheap and decisive if H1 fails | we abandon ArtiFixer fast (P1 only) rather than sinking P2 integration cost into a model that doesn't help our data. |

---

## 5. Functional requirements

### FR-1 — Ada fork runs (build/CI only, zero app-code changes)
- **FR-1.1** A forked Docker build (`Dockerfile.cuda12.ada-sm89` or equivalent)
  **removes** the FA3/FA4 install block (`Dockerfile.cuda12:27–42`) and **relaxes**
  the build-time FA smoke asserts (`:52–54`), per the QE recipe. **No application
  code is modified.**
- **FR-1.2** CI / sanity-check FA asserts (`tests/container_sanity_check.py:52–55`,
  `tests/test_flash_attn.py`) are relaxed or guarded behind `get_device_capability()[0] >= 9`
  so they don't fail on sm_89.
- **FR-1.3** Inference runs with the **sm_89 default attention path** (cuDNN SDPA);
  **no** `--attention_backend _flash_3`, **no** fp8 (bf16 is the hard default,
  `run_inference.py:344`; Ada has bf16 tensor cores).
- **FR-1.4** The 3DGRUT submodule **JIT-compiles for sm_89** via `cpp_extension.load`
  (default prep = 3DGUT rasterizer; no OptiX/RT).
- **FR-1.5** The built image's `torch.cuda.get_arch_list()` **includes `sm_89`** and
  `get_device_capability()` reports `(8, 9)` (the first-run idiot-check).

### FR-2 — Integrates after COLMAP SfM (consumes Vitrine's existing SfM)
- **FR-2.1** ArtiFixer consumes a **COLMAP-posed image set** (`images/` +
  `sparse/0/*.bin`) — exactly the artifact Vitrine's ALIKED+LightGlue SfM already
  produces. **No new posing/SfM step** is introduced.
- **FR-2.2** ArtiFixer trains its **own** 3DGRUT recon (~10k iters) from that posed
  set and then enhances it (ArtiFixer3D). It does **not** consume the LichtFeld
  `.ply` (per §2 Non-goal 3).

### FR-3 — Outputs feed CoMe/TSDF via an adapter
- **FR-3.1** An **adapter** (in `src/pipeline/`) converts ArtiFixer3D's **3DGRUT
  Gaussian output** into the **`.ply` Gaussian format CoMe / gsplat-TSDF consume**
  (positions, opacities, scales, rotations, SH/colour as those backends expect).
- **FR-3.2** The adapter's output drives the **existing** mesh path unchanged:
  `.ply` → CoMe (default) / gsplat-TSDF (fallback) → `MeshCleaner(smooth=0)` →
  xatlas texture bake → FBX → UE (ADR-019). ArtiFixer adds an alternative *recon
  source*; it does not alter the mesh/texture/delivery contract.
- **FR-3.3** ArtiFixer produces **no mesh** itself (§2 Non-goal 4) — the mesh is the
  downstream backend's job.

### FR-4 — Optional, per-scene
- **FR-4.1** The enhancement is **off by default** and enabled **per scene** via an
  opt-in flag/config (e.g. `recon.enhance=artifixer3d`), mirroring how CoMe is gated
  (`INSTALL_COME=1`, off by default).
- **FR-4.2** When disabled, the pipeline behaves **exactly as today** (LichtFeld
  recon → mesh); the ArtiFixer branch is purely additive and never on the critical
  path.
- **FR-4.3** The branch is a **parallel** recon source — selecting it swaps the
  `.ply` fed to the mesh stage; it does not modify or gate the default LichtFeld
  training.

### FR-5 — Provenance & licensing posture
- **FR-5.1** Any ArtiFixer-derived artifact (refined splat, adapter `.ply`, mesh) is
  tagged as **generatively enhanced** and **research/eval-only** in lineage (a
  `v2g:*`-style marker analogous to ADR-017's `v2g:view_synth=true`), so downstream
  consumers know surface in under-observed regions is **inferred, not measured**, and
  that the artifact is non-commercial.

---

## 6. Non-functional requirements

### NFR-1 — Fits one 48 GB card in bf16
- **NFR-1.1** 14B inference in **bf16** (~28 GB transformer; `text_encoder=None` at
  eval, prompts pre-encoded) must fit **one** RTX 6000 Ada (48 GB) under the chunked
  `kv_cache` pipeline (`frames_per_block=7`, `num_inference_steps=4`,
  `local_attn_size=21`), peaking mid-30s GB. **No fp8, no quantization, no
  offloading.**
- **NFR-1.2** **CP=1** (context-parallel size 1). CP=2 is **rejected** for the
  default AR pipeline (`run_inference.py:741`; CP must divide `gcd(7,7,21)=7`). Use
  the **2nd card for data-parallel scene round-robin** (`torchrun --nproc_per_node 2`,
  CP=1), not model parallelism.
- **NFR-1.3** The **prep-phase Qwen3-VL captioner** (~60 GB bf16) — used only at prep,
  not in `run_inference` — must either shard across both cards (`device_map=auto`,
  96 GB), be **skipped**, or use a smaller `--captioning_model_id`. It must not gate
  the inference VRAM budget.

### NFR-2 — 200 W power cap
- **NFR-2.1** All runs assume the **~200 W per-card cap**. Per-scene wall-clock must
  be **measured** under that cap (cuDNN SDPA is slower than the FA3/FA4 the model
  expects). For an *optional* stage the budget is lenient, but it must be recorded so
  the optional-stage cost is known (H2).

### NFR-3 — Host-only Docker build
- **NFR-3.1** The forked image is built **on the host** (no docker-in-docker; the
  agent sandbox cannot build GPU images). NGC base `nvcr.io/nvidia/pytorch:25.01-py3`
  is pullable; host has ~200 GB free, hf + git + docker.
- **NFR-3.2** First-run JIT/`slangc` compile of 3DGRUT on a clean Ada box is a
  toolchain risk (not an arch risk); **gcc ≤ 11 for nvcc** must be satisfied or the
  JIT path breaks.

### NFR-4 — Fork-boundary & licence compliance
- **NFR-4.1** The fork lives entirely in **our** space: a **sidecar container /
  submodule** + a **`src/pipeline` adapter** + docs. **No upstream LichtFeld dir is
  touched** (`src/core`, `src/app`, `src/mcp`, `src/rendering`, `src/training`,
  `src/geometry`, `src/io`, `cmake/`, `external/`, etc.). No upstream PRs; one-way
  sync.
- **NFR-4.2** ArtiFixer code is **Apache-2.0** (fork-safe); weights are **NVIDIA
  non-commercial** (fine for research). No commercial-track use of any
  ArtiFixer-derived artifact (ties to FR-5.1).

### NFR-5 — Reproducibility
- **NFR-5.1** Pin the fork: exact ArtiFixer + `3DGRUT-ArtiFixer` submodule commits,
  the `artifixer-14b.pt` checkpoint, the cu128 torch wheel, and the NGC base tag (no
  HEAD clones, no floating `latest`; per CLAUDE.md §3 directive).

---

## 7. Success criteria & acceptance gates

The program advances **only** by passing gates in order. The decisive gate is **P1**.

### 7.1 P0 gate — "It RUNS on Ada" (smoke)

**Pass conditions (all required):**
1. `python -c "import torch; print(torch.cuda.get_arch_list(), torch.cuda.get_device_capability())"`
   in the forked image reports **`sm_89` in the arch list** and **`(8, 9)`**
   (FR-1.5).
2. One **short** ArtiFixer inference run on a small posed scene completes with
   `--context_parallel_size 1`, the attention selector resolves to **auto SDPA
   (cuDNN)** (no raise, no FA backend), and produces valid output frames (FR-1.3).
3. **14B bf16 fits one 48 GB card** under the chunked `kv_cache` pipeline — peak VRAM
   recorded, no OOM (NFR-1.1).
4. The **3DGRUT submodule JIT-compiles** for sm_89 and trains a recon (FR-1.4).

P0 proves feasibility only. It does **not** prove usefulness.

### 7.2 P1 gate — "Does it HELP one dreamlab scene?" (DECISIVE)

Run **ArtiFixer3D** on **one real dreamlab scene** (the same COLMAP-posed set
Vitrine produced) → adapter → **the same CoMe/TSDF mesh path**, and compare to the
**current CoMe/TSDF mesh built from the LichtFeld recon (baseline)**.

**Metric (the de-hole / de-noise measure).** A composite, computed on the **same
mesh backend** for enhanced vs. baseline so the only variable is the recon source:

- **Primary — surface completeness in under-observed regions.** Reduction in
  **hole area / missing-surface** on the mesh (e.g. fraction of under-observed-region
  surface now closed; boundary-edge / open-boundary length; largest-hole area), and
  reduction in **floater / stray-component count** (isolated components, stray
  bridging triangles à la the CoMe tets-cleanup problem). Measured on the
  **under-observed regions specifically** (floor, occluded corners, object backs) —
  not whole-scene averages that the observed regions would dominate.
- **Secondary — splat-level NVS sanity.** On a small **held-out** set of real views,
  enhanced-recon render error (PSNR/LPIPS) is **no worse** than baseline in observed
  regions (confirming the enhancement didn't degrade faithful content), with any gain
  concentrated in under-observed views.
- **Qualitative corroboration (required, not sufficient alone).** Side-by-side
  enhanced-vs-baseline mesh/splat capture showing the named under-observed regions.

**Pass bar (must be set concretely at P1 start and recorded — proposed default):**

> **PASS** iff, on the chosen dreamlab scene, ArtiFixer3D→CoMe/TSDF achieves a
> **≥ 25 % reduction in under-observed-region hole/missing-surface area AND a
> reduction in floater/stray-component count**, with **no regression** (Δ within
> noise) in observed-region NVS error and **no new gross artifacts** in the
> qualitative side-by-side — at a per-scene wall-clock the team accepts for an
> optional stage under the 200 W cap.

> **FAIL / NO-GO** if the de-hole gain is within measurement noise, OR the
> enhancement helps only the sparse/holey benchmark regime and not our
> dense+motion-blurred capture, OR it introduces new artifacts (hallucinated
> geometry in observed regions, AR drift), OR the wall-clock is prohibitive even for
> an optional stage. **A FAIL ends the program at P1 — no P2.** (The pass bar
> percentage is set at P1 kickoff against the actual baseline mesh; 25 % is the
> proposed default, not a derived constant.)

**Hard caveat baked into the gate (do not let it pass on the wrong evidence):**
ArtiFixer **does not deblur**. Improvement must be demonstrably about
**under-observation / holes / floaters**, **not** about sharpness. Any "it looks
sharper" result is *not* a pass — sharpness in observed regions is governed by the
blurry input (§2 Non-goal 1), and a sharpness claim signals the metric is measuring
the wrong thing.

### 7.3 P2 gate — "Pipeline integration" (only if P1 PASSED)

**Pass conditions:**
1. The adapter (FR-3.1) is a stable, tested `src/pipeline` component; its output
   `.ply` drives CoMe/TSDF unchanged (FR-3.2), with adapter-fidelity (H3) confirmed
   not to be the dominant error source.
2. The branch is **opt-in per scene**, **off by default**, and a disabled run is
   byte-for-byte the current pipeline (FR-4.1/4.2).
3. Provenance markers (FR-5.1) tag enhanced artifacts research/eval-only.
4. Fork-boundary + host-only-build + licence NFRs (NFR-3/4/5) all hold.

---

## 8. Phased plan

| Phase | Question | Work | Exit |
|---|---|---|---|
| **P0 — Smoke (RUNS on Ada)** | Does the fork run on sm_89 at all? | Build `Dockerfile.cuda12.ada-sm89` (strip FA3/FA4, relax CI asserts); one short inference + one prep pass on a small scene; record arch-list, attention path, VRAM peak, JIT compile. ~1.5–2 person-days. | **§7.1 pass** → P1. Fail → fix toolchain (gcc/JIT/arch-list) or stop. |
| **P1 — Helps? (DECISIVE)** | Does ArtiFixer3D measurably de-hole/de-noise a **real dreamlab** splat+mesh vs. CoMe/TSDF baseline, on Ada? | Set the pass bar against the actual baseline mesh; run ArtiFixer3D on one dreamlab scene → throwaway adapter → same mesh backend; compute the §7.2 metric vs. baseline; produce the side-by-side. | **§7.2 PASS** → P2. **FAIL → STOP (no integration).** |
| **P2 — Integrate (only if P1 passed)** | Make it a production-quality optional stage. | Harden the adapter into `src/pipeline`; wire the opt-in per-scene flag; sidecar container/submodule per the (sibling) ADR; provenance tags; data-parallel 2-card round-robin; pin everything. | **§7.3 pass** → optional stage available; ADR + DDD addendum finalised. |

**Sequencing note.** P0 and the **build-feasibility** half of P1 share the same
forked image, so the smoke run *and* the first dreamlab enhancement can come from one
build (per the QE "first experiment" note). P1's **decision** is nonetheless a
separate, explicit gate — feasibility ≠ usefulness.

---

## 9. Risks & mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **It doesn't help our data** — gains live only in the sparse-sharp benchmark regime, not dense+motion-blurred dreamlab. | Med–High | High (kills the case) | This is **H1** — make it the P1 gate (§7.2). Test on real dreamlab data first; cheap, decisive no-go; **stop at P1** if it fails. |
| R2 | Team mistakes ArtiFixer for a **deblur** fix and judges P1 on sharpness. | Med | High (wrong decision) | §2 Non-goal 1 + the §7.2 hard caveat: a sharpness result is **not** a pass; the metric measures holes/floaters in under-observed regions only. |
| R3 | **cuDNN SDPA throughput** (no FA3/FA4) under 200 W makes per-scene wall-clock too slow even for an optional stage. | Med | Med | Measure wall-clock at P0/P1 (H2, NFR-2.1); it's an *optional* stage so the budget is lenient; data-parallel 2-card round-robin amortises batches. |
| R4 | **Adapter fidelity loss** — 3DGRUT→`.ply` conversion, not the enhancement, dominates mesh error. | Med | Med | H3; validate adapter round-trip (positions/opacity/SH) at P1 with a throwaway adapter before P2; isolate adapter loss from enhancement gain. |
| R5 | **Hallucinated geometry** in observed regions / AR drift introduces new artifacts. | Low–Med | High | §7.2 "no new gross artifacts" + "no observed-region regression" pass conditions; provenance tag (FR-5.1) flags inferred surface. |
| R6 | **First-run JIT/toolchain** breakage (slangc, 3DGUT, gcc ≤ 11 for nvcc, cu128 arch-list missing sm_89). | Med | Med (P0 only) | QE residual-risk checklist; confirm `get_arch_list()` includes sm_89 (FR-1.5); pin gcc ≤ 11; first-run compile is toolchain, not arch. |
| R7 | **Prep-phase Qwen3-VL captioner** (~60 GB) OOMs the VRAM plan. | Low | Low | NFR-1.3: `device_map=auto` shard across both cards, skip, or use a smaller captioner; prep-only, not in `run_inference`. |
| R8 | **Scope creep** — ArtiFixer drifts toward replacing LichtFeld, a commercial path, or a CP=2 effort. | Med | Med | §2 Non-goals 2/3/5 are explicit; it stays an *optional parallel* recon source, non-commercial, CP=1. |
| R9 | **Fork-boundary violation** — adapter/sidecar leaks into upstream dirs. | Low | High (merge pain) | NFR-4.1; all code in `src/pipeline` + sidecar/submodule; one-way upstream sync; reviewed against `BOUNDARIES.md`. |
| R10 | **NVIDIA non-commercial weight** used on a commercial-track artifact. | Low | High (legal) | FR-5.1 provenance markers; research/eval-only posture mirrored from CoMe; idiot-check / `--commercial` posture excludes the ArtiFixer branch. |

---

## 10. Out of scope

- **The architecture decision** (sidecar container vs. git submodule vs. both;
  exact adapter design; how the per-scene flag threads through `stages.py`) — that is
  the **sibling ADR**, not this PRD.
- **The domain model** (where the refined-3DGRUT recon sits in the bounded-context
  map; ubiquitous-language terms for "EnhancedRecon") — that is the **sibling DDD
  addendum**.
- **Deblur / motion-blur remediation** — upstream frame-QA / recapture problem (§2
  Non-goal 1).
- **CP=2 / model-parallel sharding** of the AR pipeline (§2 Non-goal 5).
- **Lighter-lineage alternatives** (e.g. **Difix3D+**, the cheaper single-step
  NVIDIA-noncommercial cousin). Noted in the eval doc as a fallback to weigh; not part
  of *this* PRD's scope, but a natural pivot if P1 fails on cost rather than on
  quality.
- **Web `.ksplat` delivery** of the enhanced splat — orthogonal (ADR-006); the
  enhanced splat could feed it, but that's not a requirement here.

---

## 11. Open questions

1. **Pass bar number.** Is **25 % under-observed-region hole-area reduction** the
   right bar, or should it be calibrated to the *worst* dreamlab scene (most
   under-observed) vs. a *typical* one? Set concretely at P1 kickoff against the
   actual baseline mesh.
2. **Which dreamlab scene for P1?** Pick the scene with the **most pronounced
   under-observed / holey** problem (so the prior has something to fill), or a
   *typical* scene (so the result generalises)? Likely the former for a clean
   yes/no signal.
3. **De-hole metric tooling.** What exactly computes "hole/missing-surface area in
   under-observed regions" on our meshes — open-boundary-edge length, a coverage mask
   from the COLMAP frustums, largest-hole area, component count? Needs a concrete,
   reproducible script before P1 (ties to §7.2).
4. **Adapter format precision.** Does CoMe/gsplat-TSDF need full SH (degree?),
   per-Gaussian opacity/scale/rotation, or a reduced subset from the 3DGRUT output?
   Determines adapter completeness (FR-3.1) and whether adapter loss (R4/H3) is even a
   concern.
5. **Does the AR prior fight blurry observed pixels?** On dense+blurred input the
   opacity-mix keeps observed pixels — but does it produce *seams* between faithful
   (blurry) observed regions and sharp generated unobserved regions on a real
   dreamlab scene? An artifact to watch for explicitly at P1.
6. **Per-scene cost ceiling.** What wall-clock (under 200 W) is the team actually
   willing to pay for an *optional* per-scene enhancement — minutes, tens of minutes,
   hours? Needed to turn H2 into a P1 pass/fail dimension.
7. **Prep captioner: skip or shard?** Is the Qwen3-VL caption materially helpful for
   *our* indoor-room scenes, or can we skip it (NFR-1.3) and simplify the prep VRAM
   story entirely?
8. **3DGRUT-trained recon quality on dreamlab.** ArtiFixer trains its *own* 10k-iter
   3DGRUT recon, not LichtFeld's ImprovedGS+. Is that base recon (before enhancement)
   even competitive with our LichtFeld recon on dreamlab data? If the base is worse,
   the enhancement has to overcome that deficit before it can beat the baseline — a
   confound to control for at P1.

---

*References: `research/landscape/artifixer-2026-evaluation.md`,
`research/landscape/artifixer-fork-feasibility-qe.md` (QE source audit),
`research/decisions/PRD-mesh-scene-into-ue.md`, `adr-017-generative-view-completion.md`,
`adr-003-pluggable-mesh-extraction-backends.md`, `adr-019-mesh-game-assets-not-usd-into-ue.md`,
`DDD-vitrine-mesh-pipeline.md`, `BOUNDARIES.md`, `CLAUDE.md` (workspace), and the audit
memory notes (`frame-qa-sota-and-data-verdict`, `dreamlab-mesh-into-ue-pipeline`,
`come-tets-cleanup-recipe`, `inflight-recovery-and-vram`).*
