# ArtiFixer recon-enhancement branch (ADR-020)

**Status:** trial — gated on per-scene evidence (ADR-020). Optional; the default
LichtFeld 3DGS → `.ply` path is unchanged.

NVIDIA **ArtiFixer** (Spatial Intelligence Lab, SIGGRAPH 2026; arXiv:2603.00492)
is an auto-regressive video-diffusion refiner for 3D reconstruction. Its
opacity-mixing trick stays faithful to observed pixels and **generates freely in
unobserved regions**, removing floaters/ghosts and filling holes. The
**ArtiFixer3D** variant distills the enhanced views back into an explicit
**3DGRUT** Gaussian recon. Vitrine uses it to attack the *secondary* quality
problem — noisy/holey **under-observed** regions that the LichtFeld recon cannot
fix from missing observations. It does **not** deblur (the dominant bottleneck);
see ADR-020 for the honest boundary.

## Trial status — 2026-06-24

First **dreamlab/locked** trial launched on the Ada **sm_89** fork. See
[`docs/scene-mesh-refinement.md`](./scene-mesh-refinement.md) for the consolidated
session record.

- **Sidecar UP.** Image `gaussian-toolkit-artifixer:ada-sm89` built; the `artifixer`
  sidecar is up on `v2g-net` (**GPU 1**, `ipc=host`), overlay
  `docker-compose.artifixer.yml`. The **63 GB `artifixer-14b.pt`** weight is staged
  (out of git, bind-mounted).
- **Pipeline run** (after COLMAP → BIN prep): `prepare_colmap_artifixer_inputs` (trains its
  **own** 3DGRUT recon + MoGe metric scale; **720 train / 30 val**) → `run_inference` (14B
  diffusion enhance) → `run_artifixer3d` (distill enhanced frames → clean 3DGRUT recon) → mesh.
- **Issues fixed so far:**
  - **Empty-val crash** — with no selected-images file every frame went to train, leaving
    val empty → 3DGRUT `compute_spatial_extents` `IndexError`. Fixed by a
    `selected_train_images.txt` that holds out **every 25th frame** (720 train / 30 val).
  - **sm_89 absent from the torch `arch_list`** (`sm_75/80/86/90/100/120`) — **non-fatal:**
    sm_86 cubins are forward-compatible to sm_89, and the 3DGRUT JIT compiles explicitly for 8.9.
  - **3DGRUT render-phase CUDA OOM** — being addressed via
    `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- **Status:** **prepare stage IN PROGRESS.** Enhance / distill / mesh and the **ADR-020 gate
  verdict are PENDING** — no enhanced result yet. Nothing here is a result.

## Where it sits in the pipeline

```
COLMAP SfM (ALIKED+LightGlue)
   ├─ LichtFeld 3DGS → .ply            (default path, unchanged)
   └─ [optional, per-scene gated] ArtiFixer3D:
         own 3DGRUT 10k-iter recon → diffusion enhance → enhanced 3DGRUT .ply
         → artifixer_adapter.py → CoMe/TSDF mesh → texture bake → FBX → UE
```

It consumes the **COLMAP-posed image set Vitrine already produces** (`images/` +
`sparse/0/*.bin`), trains its *own* 3DGRUT recon, and emits a standard 3DGS PLY —
it does **not** consume the LichtFeld `.ply` and produces **no mesh**.

## Components in this repo

| Artifact | Purpose |
|---|---|
| `docker/artifixer/ArtiFixer/` | Pinned git submodule of `nv-tlabs/ArtiFixer` @ `c320752` (Apache-2.0 code; recursive incl. `3DGRUT-ArtiFixer`). |
| `docker/artifixer/Dockerfile.ada-sm89` | Ada (sm_89) fork of upstream `Dockerfile.cuda12` — strips the FlashAttention-3/4 (Hopper/Blackwell) install + CI asserts; **zero application-code changes** (the model falls through to cuDNN SDPA on Ada). |
| `docker-compose.artifixer.yml` | Optional sidecar overlay on `v2g-net` (GPU 1, `sleep infinity` + `docker exec`, like milo/come). |
| `src/pipeline/artifixer_adapter.py` | Locates + validates the enhanced 3DGRUT recon PLY and writes the PLY the CoMe/TSDF backends ingest (ADR-003). Optional similarity transform for COLMAP/LichtFeld alignment. |
| `research/decisions/adr-020-*`, `research/landscape/artifixer-*`, `PRD-artifixer-ada-fork.md`, `DDD-artifixer-recon-enhancement.md`, `artifixer-ada-qe-audit.md` | The decision, candidate-model evaluation, 9-agent QE source audit (fork ruling = **GO**), PRD, DDD, QE audit. |

## The model weight (not in git)

`artifixer-14b.pt` — **67.6 GB**, ~16.9B params, base Wan2.1-T2V-14B. Licence:
**NVIDIA OneWay Noncommercial** (fine for this non-commercial university
research; the *code* is Apache-2.0). It is **not** committed (gitignored) and not
baked into the image — it is bind-mounted at runtime.

- Downloaded location on the reference host: `~/artifixer-ada/ckpt/artifixer-14b.pt`.
- The sidecar mounts `${ARTIFIXER_CKPT_DIR}` → `/workspace/ckpt:ro`. Point that
  env var at the weight dir, or symlink the repo default:
  ```bash
  mkdir -p data/artifixer && ln -s ~/artifixer-ada/ckpt data/artifixer/ckpt   # gitignored
  # or: export ARTIFIXER_CKPT_DIR=$HOME/artifixer-ada/ckpt
  ```

## Build the image (Ada sm_89)

`FROM nvcr.io/nvidia/pytorch:25.01-py3` (public, no NGC login). Builds torch
2.11 cu128, the 3DGRUT submodule (JIT/slangc), MoGe, diffusers. Legacy builder
(no BuildKit/buildx on this host):

```bash
DOCKER_BUILDKIT=0 docker build -f docker/artifixer/Dockerfile.ada-sm89 \
    -t gaussian-toolkit-artifixer:ada-sm89 docker/artifixer
# or:  docker compose -f docker-compose.consolidated.yml -f docker-compose.artifixer.yml build artifixer
```

## Stand it up on v2g-net

```bash
docker compose -f docker-compose.consolidated.yml -f docker-compose.artifixer.yml up -d artifixer
docker exec artifixer python -c "import torch; print('arch', torch.cuda.get_arch_list())"  # expect sm_89
```

The container idles (`sleep infinity`); drive it with `docker exec` like milo/come.

## Run (per-scene, gated)

ArtiFixer3D consumes a *prepared scene root* (COLMAP `images/` + `sparse/0`):

```bash
# 1. prepare COLMAP inputs (uses the Qwen3-VL-30B captioner — prep-time only;
#    needs device_map=auto sharding or a smaller --captioning_model_id)
docker exec artifixer python -m data_processing.prepare_colmap_artifixer_inputs --help
# 2. run ArtiFixer3D distillation (own 3DGRUT recon → diffusion enhance → distill)
docker exec artifixer python -m data_processing.run_artifixer3d --scene_root <prepared> ...
# 3. adapt the enhanced 3DGRUT recon PLY for the mesh stage
python -m pipeline.artifixer_adapter <scene_root>/artifixer3d /data/output/<run>/enhanced.ply
# 4. mesh as usual (CoMe/TSDF) from the adapted PLY
```

Run with `--context_parallel_size 1` (CP must divide `gcd(7,7,21)=7`; **CP=2 is
invalid** for the default AR pipeline); the 2nd Ada card is for data-parallel
scene round-robin (`torchrun --nproc_per_node 2`, CP=1), not context-parallel.
Do **not** pass `--attention_backend _flash_3`; bf16 is the hard default (no fp8).

## The per-scene gate (the actual experiment)

ArtiFixer3D runs only when a per-scene gate predicts it will help, and the
**first run validates the gate**: on one real dreamlab scene, measure whether the
enhanced 3DGRUT recon yields a **measurably less holey / less noisy** downstream
CoMe/TSDF mesh than the current path, at acceptable wall-clock under the 200 W
cap. Exit criterion (ADR-020): **PROCEED** to wire the gated branch only on a
measurable gain; **FALL BACK to Difix3D+** if it helps but is too costly;
**ABANDON** if the scene is blur-dominated (ArtiFixer cannot deblur).

## Build/standup status (2026-06-24)

Image `gaussian-toolkit-artifixer:ada-sm89` built (54.6 GB) and the sidecar is up
on `v2g-net`. QE residual risks, now resolved/open:

- ✅ **Runs on Ada.** `torch.cuda.is_available()` True, capability `(8,9)`; a real
  bf16 matmul and `scaled_dot_product_attention` both execute. Note the cu128
  wheel's `get_arch_list()` is `['sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']`
  — **no explicit `sm_89`**; Ada runs via Ampere `sm_86` binary-compat (verified).
- ✅ **No FlashAttention-3 dependency.** The ArtiFixer app stack
  (`data_processing.run_artifixer3d`, `prepare_colmap_artifixer_inputs`) imports
  clean in-container — the fork ruling holds (cuDNN SDPA path).
- ⚠️ **GPU compose gotcha (fixed).** `runtime: nvidia` + `deploy.resources.devices`
  together break CUDA init ("CUDA unknown error" while `nvidia-smi` works); the
  overlay uses `runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES=1` only.
- ⏳ **Open (per-scene run):** 14B bf16 (~28 GB) full model load + 3DGRUT JIT
  compile under the 200 W cap; SDPA-vs-FA3 throughput; and the 3DGRUT→`.ply`
  adapter's geometry/colour fidelity + 3DGRUT↔COLMAP alignment (adapter defaults
  to identity copy — measure before enabling a `world_transform`).

See `research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md` and
`research/landscape/artifixer-fork-feasibility-qe.md` for the full audit.
