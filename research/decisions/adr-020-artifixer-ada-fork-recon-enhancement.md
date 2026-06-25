# ADR-020 — Fork ArtiFixer for Ada (sm_89) as an optional parallel recon-enhancement branch

**Status:** Proposed (2026-06-23)
**Trial status (2026-06-24):** Fork built + sidecar UP on Ada sm_89 (v2g-net, GPU1); 14B weights staged; first dreamlab/locked trial in progress (prepare stage; empty-val + render-OOM issues fixed). Enhance/distill/mesh + gate verdict pending. See docs/scene-mesh-refinement.md.
**Extends:** ADR-017 (generative view completion — same "fill only unobserved regions" principle, applied at recon scale not panel scale), ADR-003 (pluggable mesh-extraction backends — the enhanced recon feeds CoMe/TSDF), ADR-013 (serial model lifecycle / VRAM discipline)
**Drives (if accepted):** a new `Dockerfile.cuda12.ada-sm89` fork of ArtiFixer (sidecar container + git submodule of `nv-tlabs/ArtiFixer`), a `src/pipeline/artifixer_adapter.py` (3DGRUT Gaussian → `.ply` for CoMe/TSDF), and a per-scene quality gate
**Evidence:** `research/landscape/artifixer-2026-evaluation.md`; `research/landscape/artifixer-fork-feasibility-qe.md` (9-agent QE source audit, every load-bearing claim verified at file:line); dreamlab e2e (MUSIQ ~31, holey under-observed regions)

---

## Context

Vitrine reconstructions are **noisy and holey in under-observed regions** — surfaces the cameras barely or never saw (objects against walls, occluded backs, sparse coverage) come through the 3DGS recon as floaters, ghosts, and holes, which then propagate into the CoMe/TSDF mesh and the UE deliverable. This is the project's **secondary** quality problem (the dominant one is motion blur — see below).

**ArtiFixer** (NVIDIA, SIGGRAPH 2026; `nv-tlabs/ArtiFixer`, Apache-2.0 code, NVIDIA-noncommercial weights — **fine for this non-commercial university research**) is an auto-regressive video-diffusion refiner built on Wan2.1-T2V-14B. Its opacity-mixing trick (`z_mix = O_z·z_deg + (1−O_z)·ε`) stays faithful to observed pixels (opacity≈1) and **generates freely in unobserved regions** (opacity≈0), removing floaters and filling holes via a strong generative prior. The **ArtiFixer3D** variant distills the generated views back into an explicit **3DGRUT** Gaussian recon → a cleaner splat that could yield a better downstream mesh. ArtiFixer consumes a **COLMAP-posed image set** (`images/` + `sparse/0/*.bin`) — which Vitrine already produces via ALIKED+LightGlue SfM — trains its **own** 10k-iter 3DGRUT recon, then enhances it. It does **not** consume the LichtFeld `.ply` and produces **no mesh**.

The apparent blocker was hardware: ArtiFixer's published stack mandates **FlashAttention-3/FA4 on Hopper/Blackwell (`sm_90`/`sm_100`)**, and Vitrine has 2× RTX 6000 Ada (`sm_89`, 48 GB, 200 W-capped). **The QE source audit ruled this requirement ARTIFICIAL — packaging/perf-default only, not a math/kernel dependency** (`artifixer-fork-feasibility-qe.md`, all file:line-verified):

- The only `get_device_capability()` consumer in runtime code (`model_training/net/transformer.py:158`) is a **perf-backend selector** that falls through every Hopper/Blackwell branch and returns `None` → **cuDNN SDPA** for sm_89 **with no raise/assert/exit** (`transformer.py:184–185`). `set_attention_backend` is guarded (`if attention_backend is not None`) and never fires on sm_89; the FA3 patch is `try/except`; no top-level `flash_attn` import sits in the inference path.
- The entire lock-in lives in **`Dockerfile.cuda12:27–42`** (FA3/FA4 build) **+ CI asserts** (`Dockerfile.cuda12:52–54`, `tests/container_sanity_check.py:52–55`, `tests/test_flash_attn.py`) — removable **without touching one line of application code**.
- Inference is **bf16** (~28 GB transformer; `text_encoder=None` at eval, prompts pre-encoded) under a chunked `kv_cache` pipeline (`frames_per_block=7`, `num_inference_steps=4`, `local_attn_size=21`) → **fits ONE 48 GB card**, mid-30s GB peak. The **3DGRUT** submodule builds on Ada via JIT `cpp_extension.load` (`-DTCNN_MIN_GPU_ARCH=70`, default prep = 3DGUT rasterizer, no OptiX/RT). Three adversarial refuters returned **NOT REFUTED**.

So the open question is **not** "can we run it" (GO) but **does it actually help a real dreamlab capture**. ArtiFixer fills *unobserved* regions but **does not deblur** — in observed (motion-blurred, MUSIQ ~31) regions opacity≈1, so it stays faithful to the blurry input. It targets Vitrine's **secondary** holey/under-observed problem, **not** the dominant motion-blur bottleneck (which remains an upstream frame-QA / deblur / recapture fix, per `frame-qa-sota-and-data-verdict`).

## Decision

1. **Fork ArtiFixer to run on Ada sm_89 — build/CI changes only, zero application-code changes.** Add `nv-tlabs/ArtiFixer` (+ its `3DGRUT-ArtiFixer` submodule) as a **sidecar container + git submodule** (respecting the fork boundary — it lives alongside, not inside, upstream LichtFeld dirs), and produce a `Dockerfile.cuda12.ada-sm89` that:
   - **Strips the FA3/FA4 build block** (`Dockerfile.cuda12:27–42`, incl. the orphan `cuda-python==12.6.2.post1` reinstall) and the **build-time FA smoke asserts** (`:52–54`).
   - **Relaxes the CI asserts** (`tests/container_sanity_check.py:52–55`, `tests/test_flash_attn.py`) behind `get_device_capability()[0] >= 9`.
   - Leaves **SDPA as the attention path** (sm_89 default — do **not** pass `--attention_backend _flash_3`), **bf16** as the hard default (Ada has bf16 tensor cores — do **not** try fp8), and runs **`--context_parallel_size 1`** (CP must divide `gcd(7,7,21)=7`; **CP=2 is rejected** for the default AR pipeline). The 2nd Ada card is used for **data-parallel scene round-robin** (`torchrun --nproc_per_node 2`, CP=1), not context-parallel. See the fork-recipe summary below.

2. **Integrate ArtiFixer3D as an OPTIONAL, per-scene parallel recon-ENHANCEMENT branch tapping in after COLMAP SfM.** The branch is:

   ```
   COLMAP SfM (ALIKED+LightGlue) → [ArtiFixer3D enhance: own 3DGRUT 10k-iter recon → diffusion enhance]
     → refined 3DGRUT splat → ADAPTER → CoMe/TSDF mesh → texture bake → FBX → UE
   ```

   It runs **in parallel to** (not replacing) the LichtFeld 3DGS → `.ply` path. ArtiFixer3D consumes the **COLMAP-posed image set Vitrine already produces** (`images/` + `sparse/0/*.bin`); it does **not** consume the LichtFeld `.ply` and emits **no mesh** — its output is a 3DGRUT Gaussian recon.

3. **An ADAPTER bridges ArtiFixer3D's 3DGRUT output to the `.ply` CoMe/TSDF consume.** `src/pipeline/artifixer_adapter.py` converts the enhanced 3DGRUT Gaussian recon into the `.ply` form the existing CoMe/TSDF mesh backends (ADR-003) ingest, so the enhanced recon flows through the **unchanged** downstream mesh → texture → FBX → UE path.

4. **The branch is gated on a first-class, per-scene quality test — no blanket pipeline commitment.** Because the enhancement targets the *secondary* (holey) problem and **does not deblur**, ArtiFixer3D runs only when a per-scene gate predicts it will help, and the **first experiment is the gate's validation**: on one real dreamlab scene, measure whether ArtiFixer3D **measurably de-holes / de-noises the actual splat** (vs the current CoMe/TSDF mesh) before any volume commitment. This is the dominant **acceptance risk**, made an explicit gate (see Decision-reversal / exit criterion).

## Alternatives considered

- **Rent H100 / A100-80GB and run ArtiFixer stock (no fork).** Rejected: the sm_90/sm_100 wall is **artificial** (QE audit) — a ~1.5–2 person-day build/CI fork runs it on hardware we already own, under the 200 W cap. Paying for cloud Hopper/Blackwell to dodge a 13-line Dockerfile edit is unjustified for a research project, and adds a data-egress / scheduling dependency the in-house 2× Ada box avoids.
- **Use the lighter Difix3D+ instead** (same NVIDIA-noncommercial lineage, far cheaper single-step model). **Deferred, not rejected** — kept as the lighter fallback if ArtiFixer3D's cost/quality fails the per-scene gate. ArtiFixer3D is preferred *first* because it wins the artifact-removal + novel-content benchmarks (+1.7 dB vs Difix3D+ on Nerfbusters, ≈+3 dB novel-content on DL3DV) and distills back to an explicit recon we can mesh; Difix3D+ is the cheaper retreat, not the leading candidate.
- **Just fix it upstream — recapture / deblur before recon.** This **remains the correct fix for the dominant motion-blur bottleneck** and is **not** in competition with this ADR. ArtiFixer does *not* deblur (opacity≈1 in observed regions stays faithful to blurry input); it addresses the *orthogonal* under-observed/holey problem. Upstream frame-QA rejection / deblur / recapture stays the primary lever for blur; this branch is additive for the holey secondary problem only.
- **Do nothing — accept holey under-observed regions.** Rejected as the default but retained as the fallback if the gate fails: noisy/holey under-observed recon degrades the mesh and the UE asset, and a strong, license-clear generative prior that runs on hardware we own is worth the bounded fork cost to *trial*. "Do nothing" is exactly what the exit criterion falls back to.

## Consequences

**Positive:** a strong, license-clear (research-OK) generative video-diffusion prior runs on **hardware we already own** (2× Ada, no cloud spend) for a bounded **~1.5–2 person-day** fork; it directly targets the under-observed/holey **secondary** bottleneck (floaters, ghosts, holes) that the LichtFeld recon cannot fix from missing observations; the enhanced 3DGRUT splat flows into the **unchanged** CoMe/TSDF → texture → FBX → UE path via one adapter; the branch is **optional and per-scene gated**, so it never degrades scenes it cannot help; reuses the COLMAP-posed image set Vitrine already produces (no new capture contract).

**Negative / cost:**
- **A second reconstruction stack to maintain.** ArtiFixer3D trains its **own** 3DGRUT recon (10k iters) and ships a 67.6 GB / ~16.9B-param checkpoint plus a `3DGRUT-ArtiFixer` submodule with first-run slangc/JIT compiles — a parallel recon + diffusion + 3DGRUT toolchain alongside LichtFeld, with its own VRAM lifecycle (~28 GB bf16, serial per ADR-013), forked Dockerfile/CI to track against upstream, and a captioner/prep phase (Qwen3-VL-30B, prep-time only) to manage. This is real, ongoing surface area.
- **Non-bit-identical SDPA caveat.** Dropping FA3/FA4 for cuDNN SDPA + Triton flex is **correctness-intact but not bit-identical** to the published Hopper/Blackwell numbers, and is **slower** — under the **200 W cap**, wall-clock/scene must be measured before any volume commitment (CP=1 only; 2nd card is data-parallel round-robin, not a per-scene speedup).
- **Motion-blur limitation (the acceptance risk).** ArtiFixer **does not deblur** — it stays faithful to observed (blurry, MUSIQ ~31) pixels. It cannot fix Vitrine's **dominant** bottleneck; if a dreamlab scene's quality is blur-limited rather than coverage-limited, the enhancement may show **no measurable downstream gain**. This is why the per-scene gate is first-class and the exit criterion is concrete.
- **Adapter risk.** The 3DGRUT → `.ply` adapter is new surface that must preserve geometry/colour fidelity for CoMe/TSDF; a lossy or misaligned conversion would erase the enhancement before it reaches the mesh.

**Neutral:** USD is unaffected (this branch ends at the existing mesh path, ADR-019 governs the UE deliverable); the LichtFeld `.ply` recon path is untouched and remains the default.

## Fork-recipe summary

From `artifixer-fork-feasibility-qe.md` (build/CI only — **zero app-code changes**, ~1.5–2 person-days):

1. Delete `Dockerfile.cuda12:27–42` (FA3 Hopper block + FA4 `flash-attn-4` install + orphan `cuda-python==12.6.2.post1` reinstall, ~13 lines).
2. Delete the build-time FA smoke asserts (`Dockerfile.cuda12:52–54`).
3. No attention flag (sm_89 default = SDPA); do **not** pass `--attention_backend _flash_3`.
4. bf16 is the hard default (`run_inference.py:344`); Ada has bf16 tensor cores — do **not** try fp8.
5. Relax CI FA asserts behind `get_device_capability()[0] >= 9` (`tests/container_sanity_check.py:52–55`).
6. Guard `tests/test_flash_attn.py`'s no-FA4 `sys.exit(1)` behind `major >= 9`.
7. *(optional)* Append `8.9` to `TORCH_CUDA_ARCH_LIST` in `3DGRUT-ArtiFixer/install_env.sh:54` (no-op for the `pip install -e .` JIT path).
8. *(optional)* Drop unused `FLASH_ATTN_MAX_JOBS/NVCC_THREADS` ARGs + `gcc-11` (FA3-only).
9. **Parallelism:** CP=1 (CP must divide `gcd(7,7,21)=7`; valid CP∈{1,7}); 2-card speedup via **data-parallel scene round-robin** (`torchrun --nproc_per_node 2`, CP=1).

**Residual risks to verify on the first build/run** (per the QE audit): SDPA-vs-FA3 throughput under the 200 W cap; the built image's `torch.cuda.get_arch_list()` includes `sm_89` (Dockerfile pip-installs `torch==2.11.0 cu128` over the NGC `nvcr.io/nvidia/pytorch:25.01-py3` base); first-run slangc/3DGUT JIT compile; gcc ≤ 11 for nvcc; prep-phase Qwen3-VL-30B captioner needs `device_map=auto` sharding (or skip / smaller `--captioning_model_id`) — prep-time only.

## Decision-reversal / exit criterion

This is a **trial gated on evidence**, not a standing commitment. Run the bounded fork + **one** ArtiFixer3D enhancement on **one real dreamlab scene** (the same run validates the fork: sm_89 in the cubin arch-list, the selector prints `auto SDPA (cuDNN)` and produces output, 14B bf16 fits one 48 GB card, 3DGRUT JIT compiles for Ada).

- **PROCEED** to wire the branch + adapter into the per-scene-gated pipeline **only if** the enhanced 3DGRUT recon yields a **measurably less holey / less noisy** downstream CoMe/TSDF mesh than the current path on that scene, at an acceptable wall-clock/scene under the 200 W cap.
- **FALL BACK to Difix3D+** (the lighter NVIDIA-noncommercial alternative) if ArtiFixer3D helps but its cost/throughput is impractical.
- **ABANDON (do nothing)** if the dreamlab scene shows **no measurable downstream gain** — i.e. its quality loss is blur-dominated (which ArtiFixer cannot fix) rather than coverage-dominated. In that case the lever returns to upstream frame-QA / deblur / recapture, and no second reconstruction stack is adopted.

## Related Decisions

- `adr-017-generative-view-completion.md` — same "generate **only** where there is no real data" principle (FLUX.2 fills unobserved *panels* before hull recon); this ADR applies the analogue at **recon scale** via ArtiFixer's opacity-mix, feeding the mesh stage instead of TRELLIS.2.
- `adr-003-pluggable-mesh-extraction-backends.md` — the enhanced 3DGRUT recon feeds the **existing** CoMe/TSDF backends via the new adapter; no change to the backends themselves.
- `adr-013-ingest-manifest-serial-model-lifecycle.md` — ArtiFixer's ~28 GB bf16 footprint obeys the serial VRAM lifecycle alongside the existing FLUX.2/TRELLIS.2/Hunyuan stages.
- `adr-019-mesh-game-assets-not-usd-into-ue.md` — governs the unchanged downstream UE deliverable (textured FBX game assets) the enhanced mesh ultimately flows into.

## References

- `research/landscape/artifixer-2026-evaluation.md` — candidate-model evaluation (method, results envelope, the quality-fit verdict).
- `research/landscape/artifixer-fork-feasibility-qe.md` — 9-agent QE source audit (the file:line fork ruling, minimal-fork recipe, residual risks, first experiment).
- ArtiFixer — arXiv:2603.00492, SIGGRAPH 2026, NVIDIA Spatial Intelligence Lab; code `github.com/nv-tlabs/ArtiFixer` (Apache-2.0); weights `huggingface.co/nvidia/ArtiFixer` (`artifixer-14b.pt`, 67.6 GB, NVIDIA OneWay Noncommercial). Base: Wan2.1-T2V-14B (Apache-2.0).
- `frame-qa-sota-and-data-verdict` (memory) — motion blur is the dominant bottleneck (dreamlab MUSIQ ~31); deblur/recapture is the upstream lever ArtiFixer does **not** replace.
