# ArtiFixer (NVIDIA, SIGGRAPH 2026) — candidate-model evaluation for Vitrine

> Mapped 2026-06-23 via multi-agent research (paper + code + HF + lineage, adversarially
> verified). Context: Vitrine is **non-commercial university research**, so the NVIDIA
> non-commercial weights license is **not** a blocker (see memory
> `project-noncommercial-research-licensing`). The real blockers are **hardware** and a
> **quality-fit mismatch** — detailed below.

- Project: <https://research.nvidia.com/labs/sil/projects/artifixer/>
- Paper: *ArtiFixer: Enhancing and Extending 3D Reconstruction with Auto-Regressive Diffusion Models* — arXiv:2603.00492, SIGGRAPH 2026, NVIDIA Spatial Intelligence Lab.
- Code: <https://github.com/nv-tlabs/ArtiFixer> (**Apache-2.0**, fully released, not a placeholder)
- Weights: <https://huggingface.co/nvidia/ArtiFixer> — `artifixer-14b.pt`, **67.6 GB**, ~16.9B params, **NVIDIA OneWay Noncommercial** (public, ungated). Base: Wan2.1-T2V-14B (Apache-2.0).

## What it is

A **refiner/extender** that sits on top of an existing sparse-view 3DGS/3DGRUT reconstruction
and produces **artifact-free novel-view renderings from arbitrary viewpoints — including
regions the cameras never observed**. It is *not* a from-scratch reconstructor and *not* a
mesh generator.

## Method (two phases)

1. **Bidirectional fine-tune + opacity mixing.** Fine-tunes Wan2.1-T2V-14B (frozen VAE +
   text encoder) on degraded 3D renderings → clean GT (flow-matching). Conditioning: degraded
   RGB latent, rendered **opacity maps**, per-pixel **Plücker raymaps**, K=6 reference views
   (cross-attn), optional VLM caption (Qwen3-VL). **Core trick:**
   `z_mix = O_z·z_deg + (1−O_z)·ε` — per pixel, ≈ the degraded latent where opacity≈1
   (faithful to observed content) and → Gaussian noise where opacity≈0 (generate freely in
   unobserved regions). The single ablation the paper calls *essential* (denoising the input
   render = +3.47 dB).
2. **Causal AR distillation (Self-Forcing + DMD).** Distills the bidirectional teacher into a
   **4-step causal auto-regressive** student that rolls out on its own outputs (removes
   exposure bias/drift) and emits **hundreds of frames per pass** — a **70× speedup**
   (14B: 0.12 → 8.36 FPS on GB300).

**Variants:** **ArtiFixer** (sharpest renders, wins LPIPS/FID) · **ArtiFixer3D** (distills
generated views back into an explicit 3DGRUT recon; wins PSNR/SSIM + best multi-view
consistency MEt3R; renders at native ~268 FPS) · **ArtiFixer3D+** (re-applies the AR generator
on top of ArtiFixer3D to restore sharpness).

## Results (headline)

The abstract's "+1–3 dB PSNR" is a **task/baseline-dependent envelope**, verified:
- Artifact removal vs Difix3D+: **+1.7 dB** Nerfbusters, **+2.15 dB** DL3DV.
- Novel-content (large holes) vs GenFusion: **≈+3 dB** DL3DV.
- Sparse-view vs CAT3D (Mip-NeRF 360): **+0.9 / +1.2 / +1.6 dB** at 3/6/9-view.
- All benchmarks are **sparse-but-sharp** input — none is dense-but-motion-blurred.

## Availability / hardware

- Code Apache-2.0; weights NVIDIA-noncommercial (**fine for our research use**).
- **Stack:** NGC PyTorch 25.01, torch 2.11 / CUDA 12.8, **mandatory FlashAttention-3 (Hopper)
  + FA4 (Blackwell)** built from source (`sm_90`/`sm_100`), MoGe depth, COLMAP, a `3DGRUT-ArtiFixer`
  submodule. Tested HW: **A100 80GB / H100 / GB200**. No inference-VRAM figure published.
- Training cost: 128× H100, ~15k GPU-hrs (full) / ~4k (near-full-quality recipe).

## Fit for Vitrine — verdict: **TRIAL on the right hardware; NOT a pipeline component yet**

Licensing is cleared (research use). Two independent blockers remain:

1. ~~**Hardware mismatch (hard).**~~ **RESOLVED — the sm_90/sm_100 wall is ARTIFICIAL (QE source
   audit, 2026-06-23). A fork runs on our 2× RTX 6000 Ada (sm_89) — verdict GO, ~1.5–2 person-days,
   ZERO application-code changes.** See `artifixer-fork-feasibility-qe.md` (full QE ruling). In short:
   the only `get_device_capability()` consumer (`model_training/net/transformer.py:158`) is a *perf
   selector* that falls through to **cuDNN SDPA** for sm_89 with no raise; FA3/FA4 are guarded
   (`try/except`, `if attention_backend is not None`) and live only in `Dockerfile.cuda12:27-42` +
   CI asserts. Inference is **bf16** (~28 GB transformer, text-encoder=None at eval) under a chunked
   `kv_cache` pipeline → **fits ONE 48 GB card**; 3DGRUT builds via JIT `cpp_extension.load`
   (`-DTCNN_MIN_GPU_ARCH=70`, no `-gencode` pin; default prep is the **3DGUT rasterizer**, no
   OptiX/RT). Fork = strip the FA3/FA4 Docker block + relax CI asserts; run `--context_parallel_size 1`
   (note: CP=2 is rejected for the default AR config — `gcd(7,7,21)=7`; use data-parallel scene
   round-robin across the 2 cards instead). Residual risks to test first: SDPA-vs-FA3 throughput
   under the 200 W cap; confirm the cu128 wheel's `get_arch_list()` includes sm_89; first-run
   slangc/JIT compile; gcc ≤ 11 for nvcc; prep-time Qwen3-VL-30B captioner needs `device_map=auto`
   sharding (or skip/swap). So hardware is **not** the blocker.
2. **Quality-fit mismatch (now the ONLY real question).** Vitrine's dominant bottleneck is **motion blur**
   (dreamlab MUSIQ ~31). ArtiFixer's opacity-mix **stays faithful to observed pixels** (opacity≈1),
   so it **does not deblur** — it fills *unobserved* regions and removes floaters/ghosts. It would
   help the **secondary** under-observed/holey problem, not the primary blur. Blur stays an
   upstream fix (frame-QA rejection / deblur / **recapture**, per `frame-qa-sota-and-data-verdict`).

Also: it **produces no mesh** and **doesn't consume the LichtFeld `.ply`** — its shipped entry
point is **COLMAP-posed images** (which we already produce), from which it trains its *own*
3DGRUT recon. So integration = a parallel reconstruction branch feeding CoMe/TSDF, not an
in-line `.ply` filter.

**Single open question to resolve before any integration effort:** *does ArtiFixer3D measurably
de-hole/de-noise a real dreamlab splat, or only the sparse/holey regime it was benchmarked on?*
Answer on one scene (on adequate HW) first. Lighter lineage alternative to weigh: **Difix3D+**
(same NVIDIA-noncommercial family, far cheaper single-step model).
