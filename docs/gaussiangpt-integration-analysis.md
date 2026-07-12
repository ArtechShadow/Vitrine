# GaussianGPT integration analysis

Status: **assessment** · 2026-07-09 · Author: architecture review
Subject: [GaussianGPT (ECCV'26)](https://github.com/nicolasvonluetzow/GaussianGPT),
von Lützow, Rössle, Schmid, Nießner (TU Munich) · [arXiv 2603.26661](https://arxiv.org/abs/2603.26661)

## TL;DR

GaussianGPT is an **autoregressive generative** model for 3D Gaussian scenes: it
compresses Gaussians into a discrete token grid (VQ-VAE over a sparse 3D CNN) and models
those tokens with a GPT-2-style causal transformer, then samples new tokens and decodes
them back to Gaussians. It does unconditional generation, **completion**, and
**outpainting** with one model.

**Verdict for Vitrine: not a strong fit for the core pipeline — do not integrate into the
trunk now.** Vitrine is a *faithful reconstruction* pipeline for cultural-heritage
digitisation where invented geometry is a liability and provenance (`v2g:*`) is the point;
GaussianGPT *hallucinates* plausible geometry and is trained on synthetic furnished rooms,
not museum objects. It is, however, a credible **optional, clearly-flagged future
experiment** for one narrow job — completing/outpainting *unobserved environment/background*
regions of a room splat as a "speculative visualization," never mixed into provenance-tracked
hero assets, and only after domain fine-tuning. A concrete, low-blast-radius integration
path is sketched at the end so it is ready if that experiment is greenlit.

## What GaussianGPT actually is (grounded in the repo + paper)

Pipeline is two trained models joined by a tokenization step:

1. **VQ-VAE** (`train_ae.py`) — a sparse 3D CNN (MinkowskiEngine) with lookup-free
   quantization (LFQ) that compresses per-voxel Gaussians into discrete codebook indices,
   supervised by a `gsplat` re-rendering loss + occupancy + codebook-entropy losses.
   Codebook size 4,096; scene voxel size 20 cm after three downsampling stages from a 2.5 cm
   base grid; objects on a 128³ grid.
2. **Tokenization** (`tokenize_dataset.py`) — runs the frozen encoder over the dataset,
   serializes each latent grid to a 1-D stream by fixed `xyz` traversal, writes per-scene
   token streams (optionally 8× rotation/mirror augmented).
3. **GPT** (`train_gpt.py`) — a decoder-only causal transformer (GPT-2-medium default,
   `n_embd=1024`, `n_layer=24`; builds on **nanochat**, uses 3D RoPE, QK-norm, Muon
   optimizer) that models the interleaved position/feature token stream by next-token
   prediction. Scene context window 16,384 tokens (one full chunk); object 8,192.
4. **Inference** — sample from the GPT (nucleus sampling, temperature 0.9) and decode
   through the frozen VQ-VAE to generate / complete / tile scenes, then render with gsplat.

Key repo facts relevant to us:

- **License: MIT** (permissive — no copyleft or non-commercial clause, unlike CoMe). Fits
  Vitrine's data-sovereignty/air-gap posture: weights are self-hostable.
- **Pre-trained checkpoints released** (2026-07-01): VQ-VAE + GPT trained on **3D-FRONT**,
  and a VQ-VAE+GPT pre-trained on **3D-FRONT + ASE** then fine-tuned on 3D-FRONT. Hosted at
  TUM. **Object-level checkpoints are not yet available.**
- **Training data**: PhotoShape (chairs), 3D-FRONT (synthetic furnished rooms), Aria
  Synthetic Environments (synthetic indoor). All **synthetic indoor scenes / furniture** —
  no real captures, no heritage objects.
- **Input domain**: "Voxel-GS" = the simplified Scaffold-GS from L3DG — **one Gaussian per
  voxel, no MLP, no hierarchy**; 3D-FRONT uses 2.5 cm voxels, **SH degree capped at 1**,
  point cloud from back-projected depth. Attributes stored pre-activation (logits) as
  `anchor`+`offset` dicts.
- **Dependency stack**: CUDA 12.9, PyTorch 2.8, `gsplat`, `pytorch3d`, Flash-Attention
  2.8.2, and **MinkowskiEngine** (needs a CUDA-12 fork + GCC ≤ 13; notoriously fragile to
  build). Compiled-from-source, GPU-visible install.
- **Compute**: trained on 4× GH200 (scenes) / 4× A6000; ~1 day GPT training on scenes after
  ~4 days autoencoder. Inference is single-GPU and shardable (SLURM array friendly).

## Fit assessment against Vitrine

### Where it aligns (the genuine attractions)

- **Same representation family.** Both sides are explicit 3D Gaussians. Vitrine already
  vendors `gsplat` (`src/pipeline/gsplat_trainer.py`) and its own CLAUDE notes reference
  nanochat/Muon — so the building blocks are not foreign.
- **Addresses a real Vitrine weakness.** Vitrine's dominant failure modes are sparse
  coverage, holes and floaters (the entire reason ArtiFixer exists). Completion/outpainting
  is exactly the shape of that problem.
- **Permissive licence + self-hosted weights** suit the air-gapped, on-prem appliance.
- **Sidecar-friendly.** Vitrine already isolates conflict-prone tooling (milo/come) as
  conda sidecars, so GaussianGPT's heavy env fits the existing architectural pattern rather
  than fighting it.

### Where it does not fit (the disqualifiers for core use)

1. **Generative, not reconstructive — a values conflict.** Vitrine's core deliverable is a
   *faithful* digitisation of a *real* object with lineage metadata. GaussianGPT invents
   plausible-but-fabricated geometry and appearance. Feeding its output into a
   provenance-tracked heritage asset would silently manufacture detail that never existed —
   the one thing a cultural-heritage pipeline must not do.
2. **Domain mismatch.** The released models are trained on synthetic furnished rooms
   (3D-FRONT/ASE) and chairs (PhotoShape). A brass patina vessel, a gallery still-life, or an
   irregular heritage room is far outside that distribution; zero-shot completion would be
   low quality and confidently wrong. **Object checkpoints are not released at all.** Any
   serious use needs fine-tuning on a heritage corpus Vitrine does not currently have at
   scale.
3. **Representation conversion + appearance loss.** Vitrine trains LichtFeld `igs+` splats
   at SH degree 3. GaussianGPT ingests Voxel-GS (one Gaussian per 2.5 cm voxel, SH ≤ 1,
   anchor/offset logit dicts). Converting into and out of that domain is scriptable but
   lossy on exactly the view-dependent appearance Vitrine works to preserve.
4. **End-state mismatch.** Vitrine's terminal artifact is a **textured polygonal UE 5.8
   game asset**, not Gaussians. GaussianGPT output would require yet another
   Gaussian→mesh→FBX hop, at lower fidelity than capture-trained splats.
5. **Operational weight.** MinkowskiEngine + CUDA 12.9 + Torch 2.8 + Flash-Attention is a
   heavy, brittle, separate environment to build, pin and maintain — real cost for a
   capability that is speculative for this domain, and it further undercuts the (already
   aspirational) "single mono-image" story.

### Scorecard

| Dimension | Fit |
|---|---|
| Representation compatibility (3DGS) | ✅ good |
| Licence / air-gap / sovereignty (MIT, self-hosted) | ✅ good |
| Solves a real Vitrine gap (holes/coverage) | ✅ in principle |
| Purpose alignment (faithful reconstruction vs generation) | ❌ conflicts |
| Domain match (heritage objects/rooms vs synthetic furniture) | ❌ poor, needs fine-tune |
| Input/appearance fidelity (SH≤1 Voxel-GS conversion) | ⚠️ lossy |
| End-state alignment (Gaussians vs textured UE mesh) | ⚠️ extra hop |
| Dependency / ops burden (MinkowskiEngine stack) | ❌ heavy |

## Recommendation

**Do not integrate into the core pipeline.** It is the wrong tool for faithful heritage
reconstruction and its released models are out of domain.

**Optionally, greenlight a scoped R&D spike** (not on the critical path) for a single,
clearly-bounded use case: **speculative completion/outpainting of unobserved *environment*
regions** — walls, floor, empty room extent behind the capture frustum — to produce an
*explicitly-labelled* "speculative reconstruction" visualization for presentation/context,
strictly separated from the provenance-tracked hero assets. Guardrails would be
non-negotiable: any GaussianGPT-derived geometry is tagged `v2g:synthetic=true` (or excluded
from the lineage graph entirely), never merged into an object mesh, and always visually/UX
distinguished from measured geometry. Even this requires fine-tuning on a room corpus closer
to Vitrine's captures than 3D-FRONT.

If that spike is approved, the minimal, low-blast-radius path is below. Until then this stays
an analysis, not code.

## Minimal integration path (only if the spike is approved)

Mirrors the existing milo/come sidecar pattern so nothing touches the trunk until proven:

1. **Sidecar, not mono-image.** Add `docker/Dockerfile.gaussiangpt` + a `gaussiangpt` conda
   env (CUDA 12.9 / Torch 2.8 / MinkowskiEngine fork), built behind an
   `INSTALL_GAUSSIANGPT=0` gate exactly like `INSTALL_COME`. Pre-stage the MIT checkpoints
   into the unified models tree; pin the exact git commit and checksum.
2. **Capability probe.** Add `is_gaussiangpt_available()` + a `sota_registry` entry with
   caveats (out-of-domain checkpoints, SH≤1, generative) so a missing/failed sidecar never
   hard-breaks a run — same discipline as every other backend.
3. **Converters (the real work).** `lichtfeld_ply → Voxel-GS anchor/offset dict` (voxelize
   at 2.5 cm, one Gaussian/voxel, SH clamp) and back (`decode_scene.py` payload →
   INRIA `.ply` via their `scripts/convert_pt_to_ply.py`). Validate round-trip fidelity on a
   real captured splat before anything else.
4. **New optional stage** `complete_environment(splat, prompt_mode="spatial_half_x")` calling
   `complete_chunks.py` / `generate_scene.py`, wired **off by default**, output written to a
   separate `speculative/` tree and tagged synthetic.
5. **Provenance guardrails + UX flag** as above, reviewed before any operator-facing use.
6. **Fine-tune track (separate, longer):** curate a heritage-room corpus, fine-tune the
   VQ-VAE+GPT from the `both` checkpoint; only then consider promoting the stage beyond R&D.

## Sources

- Paper: [GaussianGPT: Towards Autoregressive 3D Gaussian Scene Generation](https://arxiv.org/abs/2603.26661) (ECCV'26)
- Code: [github.com/nicolasvonluetzow/GaussianGPT](https://github.com/nicolasvonluetzow/GaussianGPT) (MIT)
- Related in-tree: `src/pipeline/gsplat_trainer.py`, `src/pipeline/artifixer_adapter.py`,
  `docs/asset-creation-decision-tree.md`, `research/decisions/adr-015-*` (TRELLIS.2 hull).
