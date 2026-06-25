# PRD — Object Reconstruction SOTA Refresh (2026-06)

**Status:** Active
**Owner:** Vitrine pipeline (object-reconstruction component)
**Drives:** ADR-015, `research/ddd/object-reconstruction-context.md`
**Evidence base:** `research/2026-06-object-reconstruction-sota.md` (4-agent SOTA sweep) + live ComfyUI `/object_info` inventory of `vitrine-comfyui` (605 nodes, probed 2026-06-19)

---

## 1. Problem

The per-object hull stage (orbit render → recovery → image-to-3D mesh) is the weakest, least-finished part of the Vitrine pipeline. Three concrete gaps, all confirmed against the *running* system:

1. **The named primary hull backend does not exist in code.** ADR-010 names TRELLIS.2-4B the primary hull; `sota_registry.py` lists it primary — but there is no `trellis2_client.py`, no workflow JSON, and **the TRELLIS.2 ComfyUI nodes are not installed** in `vitrine-comfyui`. The de-facto working primary is Hunyuan3D-2.1.
2. **The working Hunyuan3D path emits untextured meshes.** `hunyuan3d21_multiview.json` runs shape (DiT → `VAEDecodeHunyuan3D`) but never invokes the installed PBR paint/bake nodes (`Hy3DMultiViewsGenerator` → `Hy3DBakeMultiViews`), so output lacks albedo/metallic-roughness. The registry already flags this ("current workflow has NO paint node => untextured").
3. **Recovery is locked to a single non-commercial model.** Object/occluded-face recovery uses only FLUX.2-dev (non-commercial). The 2026 sweep shows **Qwen-Image-Edit** (Apache-2.0) is both commercial-safe and the only edit model benchmarked to perform *instruction-driven view rotation* — and its nodes are already installed. There is no commercial-safe recovery path today.

## 2. Goals

- **G1** — Ship a real, primary-quality, **PBR-textured** hull for the common case, validated against the live ComfyUI.
- **G2** — Provide a **commercial-safe, view-aware recovery** path (in addition to FLUX.2) so output is not licence-blocked.
- **G3** — Make the hull backend a **clean, registry-driven strategy** with an explicit, honest fallback chain (no silent degradation).
- **G4** — Raise input quality with the community-proven levers (matting, lighting, 512² spec) where they touch our code.
- **G5** — Land TRELLIS.2 as a **gated, staged** primary upgrade with a reproducible install + smoke-test, not a dangling reference.
- **G6** — Keep everything **pinned and idiot-checkable** (`sota_registry.check_environment`).

## 3. Non-goals

- Replacing the 3DGS training, SfM, or environment-mesh stages (separate components).
- Adopting API-only hull services (Hunyuan3D 3.x, Tripo v3, Rodin) as anything but optional add-ons — the pipeline requirement is local weights.
- A LichtFeld engine version bump — upstream tag is still v0.5.2 (no newer release). Plugin-ecosystem evaluation is tracked separately.
- Commercial licence clearance (legal task); we surface licence posture, we do not adjudicate it.

## 4. Requirements

### Functional
- **FR-1** Hull backend selection is registry-driven with a deterministic fallback chain: `TRELLIS.2 (when staged)` → `Hunyuan3D-2.1 MV (PBR)` → `Hunyuan3D-2.0 MV` → `Hunyuan3D SV` → `SAM-3D (NC, last resort)` → `convex hull`. Every fall-through is logged with reason.
- **FR-2** The Hunyuan3D-2.1 hull workflow produces PBR output (albedo + metallic-roughness) via the installed `Hy3DMultiViewsGenerator`/`Hy3DBakeMultiViews` nodes.
- **FR-3** Recovery supports a selectable model: `flux2` (default, long-form description) | `qwen-image-edit` (commercial-safe, view-aware) | `flux-fill` (lightweight fallback), surfaced in `InpaintConfig.model`.
- **FR-4** A new validated workflow JSON exists per added path; every `class_type` is verified present in the target ComfyUI `/object_info` before commit.
- **FR-5** Input-prep: optional BiRefNet-HR matting + 512² square/centre-crop/diffuse normalisation hook applied before any hull/recovery submission, behind a config flag (default off until the matting node is installed).
- **FR-6** TRELLIS.2 install is reproducible: a staging script (node-pack clone+pin, `git lfs` weight pull with size verification, `/object_info` smoke check) and registry pin; the backend activates only when `check_environment` confirms nodes+weights.

### Non-functional
- **NFR-1 (VRAM)** Serial per-object lifecycle on a single 48 GB Ada; no co-resident model may exceed 48 GB (idiot-check enforces).
- **NFR-2 (Licence posture)** Default research/non-commercial (WARN); `--commercial` flips non-commercial models to FAIL. A commercial-safe path (Qwen recovery + TRELLIS.2/Hunyuan hull) must pass `--commercial` for the recovery+hull elements.
- **NFR-3 (Pinning)** No floating `latest`/HEAD: every model + ComfyUI node carries a pinned commit/tag/checkpoint (ADR-012 T6).
- **NFR-4 (No silent degradation)** Any backend downgrade, missing weight, or skipped stage is logged and reflected in the per-object lineage/ledger.
- **NFR-5 (Reproducibility)** Workflows are deterministic given a seed; staging scripts verify artifact integrity (non-zero, expected size) — the #1 community failure (git-lfs pointer stubs) is guarded.

## 5. Success metrics

- Hunyuan3D-2.1 hull returns a GLB with non-empty albedo + MR textures on a smoke object. *(verifiable: inspect output GLB materials)*
- `qwen-image-edit` recovery completes a masked-region edit end-to-end on the live ComfyUI. *(verifiable: submit + history success)*
- `python -m pipeline.sota_registry check --commercial` shows a PASS-able recovery+hull path (no non-commercial FAIL on the chosen commercial route).
- TRELLIS.2: `check_environment` reports nodes+weights present after running the staging script; one smoke GLB produced.

## 6. Phasing

- **P0 (now, no new infra):** Qwen recovery workflow + config; Hunyuan3D-2.1 PBR completion; registry corrections; PRD/ADR/DDD; engineering log. All validatable against the running ComfyUI.
- **P1 (host infra):** TRELLIS.2 node-pack install + weight staging + smoke test; promote to primary on green idiot-check.
- **P2 (quality):** BiRefNet-HR matting + IC-Light relight nodes install + input-prep hook; revisit MV-Adapter (Apache-2.0 camera-conditioned turnaround) as an alternate conditioning option.

## 7. Risks & dependencies

- **R1** TRELLIS.2 node-pack build (CuMesh/o_voxel wheels, flash-attn) may fail in-container → P1 gated, P0 ships value regardless.
- **R2** Tencent-Community licence excludes EU/UK → Hunyuan hull is commercial-conditional; Qwen+TRELLIS.2 give the clean-licence route.
- **R3** Qwen-Image-Edit weights not yet staged → staging dependency; nodes are present.
- **R4** Host docker uses the legacy builder; image rebuilds are slow → prefer node/weight staging into the running container over image rebuilds where possible.

## 8. Open questions

- OQ-1 Does the installed Hunyuan paint stack need the `2mv` shape weights vs `dit-v2-1`? (probe during P0 impl.)
- OQ-2 TRELLIS.2 node pack: `visualbruno` (mature, Win-oriented, FP8/flash-attn) vs `PozzettiAndrea` (Linux/pixi). Decide during P1 against the container toolchain.
- OQ-3 Should recovery default flip to Qwen for the commercial posture automatically based on `commercial_use`? (ADR-015 decision.)
