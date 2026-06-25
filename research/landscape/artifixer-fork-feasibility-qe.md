# ArtiFixer fork feasibility on 2× RTX 6000 Ada (sm_89) — QE source audit

> 2026-06-23. 9-agent QE fleet (5 facet audits → 3 adversarial refuters → verdict) over the
> cloned source (`github.com/nv-tlabs/ArtiFixer` + `3DGRUT-ArtiFixer` submodule). Every
> load-bearing claim verified at file:line. Companion: `artifixer-2026-evaluation.md`.

## Ruling

**The sm_90/sm_100 requirement is ARTIFICIAL — a packaging/perf-default, not a hard
math/kernel dependency.** The only `torch.cuda.get_device_capability()` consumer in runtime
code (`model_training/net/transformer.py:158`) is a *perf-backend selector* that falls through
every Hopper/Blackwell branch and returns `None` → cuDNN SDPA for sm_89 **with no raise/assert/exit**.
The entire lock-in lives in `Dockerfile.cuda12` FA3/FA4 build steps + CI asserts — removable
**without touching one line of application code**.

## Fork feasibility on 2×48 GB Ada — **GO** (not TRIAL)

| Factor | Finding | Verdict |
|---|---|---|
| **Attention** | SDPA fallback IS the code's own `major<9` default (`transformer.py:184-185 return None`); `set_attention_backend` is never called on sm_89 (guarded `if attention_backend is not None`); 4× `dispatch_attention_fn(backend=None)` → `F.scaled_dot_product_attention`; the one `flex_attention` site runs Triton (`_FLEX_BLOCK_SIZE=128`, FLASH only under `major>=9`). No top-level `flash_attn` import in the inference path; FA3 patch is `try/except`. | **PASS** |
| **3DGRUT build** | JIT via `torch.utils.cpp_extension.load`, no `-gencode`/`CUDA_ARCHITECTURES` pin, only `-DTCNN_MIN_GPU_ARCH=70` (sm_89 > 70). Default prep = **3DGUT rasterizer** (`colmap_3dgut_sparse`), no OptiX/RT-core need. `pip install -e .` → JIT auto-detects sm_89. | **PASS** |
| **VRAM** | 14B **bf16** ≈ 28 GB (text_encoder=None at eval, prompts pre-encoded); chunked `kv_cache` (`frames_per_block=7`, `num_inference_steps=4`, `local_attn_size=21`) bounds activations → **fits ONE 48 GB card**, mid-30s GB peak. 2nd card = throughput bonus, not a fit requirement. No offload/quant needed (none in codebase, none required). | **PASS** |

Three adversarial refuters (attention/kernel, build-system, memory/parallelism) each returned
**NOT REFUTED** with source evidence. No fp8, no TransformerEngine, no Hopper/Blackwell PTX
intrinsic, no NVLink-fabric collective, no weight-sharding necessity anywhere in the inference path.

## Minimal-fork recipe (build/CI only — zero app-code changes)

1. **[trivial]** `Dockerfile.cuda12:27-42` — delete the FA3 Hopper build block + FA4 `flash-attn-4`
   install + the orphan `cuda-python==12.6.2.post1` reinstall (it only repairs FA4's cuda-python bump). ~13 lines.
2. **[trivial]** `Dockerfile.cuda12:52-54` — delete the build-time FA smoke asserts.
3. **[trivial]** No attention flag needed (sm_89 default = SDPA). Do **not** pass `--attention_backend _flash_3`.
4. **[trivial]** bf16 already the hard default (`run_inference.py:344`); Ada has bf16 tensor cores. Do **not** try fp8.
5. **[trivial]** `tests/container_sanity_check.py:52-55` — relax FA asserts or guard behind `get_device_capability()[0]>=9` (CI-only).
6. **[trivial]** `tests/test_flash_attn.py` — guard the no-FA4 `sys.exit(1)` behind `major>=9`.
7. **[trivial, optional]** `3DGRUT-ArtiFixer/install_env.sh:54` — append `8.9` to `TORCH_CUDA_ARCH_LIST` (no-op for the `pip install -e .` path).
8. **[trivial, optional]** drop unused `FLASH_ATTN_MAX_JOBS/NVCC_THREADS` ARGs + `gcc-11` (only FA3 nvcc needed them).

**Parallelism:** leave **CP=1** — CP must divide `gcd(7,7,21)=7` (`run_inference.py:741`), so CP=2 is
rejected for the default AR pipeline (valid CP∈{1,7}). For 2-card speedup use **data-parallel scene
round-robin** (`torchrun --nproc_per_node 2`, CP=1). (CP=2 only works on `--inference_pipeline bidirectional`.)

## Residual risks (test first)

- **SDPA-vs-FA3 throughput** — cuDNN SDPA + Triton flex are slower than FA3/FA4; under the 200 W cap,
  measure wall-clock/scene before committing to volume. Output is correctness-intact, not bit-identical.
- **NGC base override** — Dockerfile builds FROM `nvcr.io/nvidia/pytorch:25.01-py3` then pip-installs
  `torch==2.11.0 cu128` over it; confirm the built image's `torch.cuda.get_arch_list()` includes `sm_89`.
- **slangc / 3DGUT JIT** first-run compile on a clean Ada box (toolchain, not arch).
- **gcc ≤ 11 for nvcc** (toolchain pin) — will bite JIT if host nvcc sees gcc ≥ 12.
- **Prep-phase Qwen3-VL-30B captioner** (~60 GB bf16) needs `device_map=auto` to shard across both
  cards (96 GB), or skip / use a smaller `--captioning_model_id`. Prep-time only, not `run_inference`.

## Effort & first experiment

**~1.5–2 person-days** (~0.5 Dockerfile/CI edits, ~1 build+run one E2E inference + one prep pass, +0.5 buffer).

**First experiment:** build the forked `Dockerfile.cuda12.ada-sm89` (items 1–2, 5–6), then on one
RTX 6000 Ada:
```
python -c "import torch; print(torch.cuda.get_arch_list(), torch.cuda.get_device_capability())"
python -m model_eval.run_inference --checkpoint_pt artifixer-14b.pt --context_parallel_size 1 ...  # one short scene
```
This single run validates: (a) sm_89 in the cubin arch-list, (b) the selector prints `auto SDPA (cuDNN)`
and produces output, (c) 14B bf16 fits one 48 GB card under the chunked kv_cache pipeline, (d) 3DGRUT JIT
compiles for Ada.

> Note: this proves it RUNS on our hardware. The separate, still-open question (`artifixer-2026-evaluation.md`)
> is whether it HELPS a dense+motion-blurred dreamlab capture or only the sparse/holey benchmark regime —
> answer that on the same first run by eyeballing a dreamlab scene's enhanced splat vs the current CoMe/TSDF mesh.
