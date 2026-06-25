# SOTA Survey — Object Turnaround / Multi-View / Image-to-3D for Vitrine

**Date:** 2026-06-19
**Author:** automated SOTA sweep (4 parallel research agents: multi-view image gen, image-to-3D mesh, ComfyUI community practice, LichtFeld upstream)
**Scope:** Refresh the object-reconstruction component of the Vitrine pipeline (orbit render → recovery → per-object hull) against the mid-2026 state of the art, irrespective of model family. Hardware target: 2× RTX 6000 Ada (48 GB, serial per object), ComfyUI-local weights, pinnable, prefer permissive licence (non-commercial acceptable for internal/exhibit use).

This document is the evidence base for the registry/config/workflow changes landed alongside it (see `engineering-log.md` and ADR-010 amendment 2026-06-19). Every recommendation is cross-checked against ≥2 sources; unverified items are flagged.

---

## 1. Executive summary — what changes

| Component | Was (June 2026, pre-sweep) | Now recommended | Why |
|---|---|---|---|
| **Primary hull backend** | TRELLIS.2 *named* primary (ADR-010) but **not implemented**; Hunyuan3D-2.1 the de-facto working primary | **Implement TRELLIS.2-4B as real primary** | MIT licence, 24 GB, 17–60 s/object (vs ~139 s Hunyuan), full PBR (base/metallic/roughness/opacity), native multi-view input (≤16 views), mature pinnable ComfyUI node. Confirmed rank-1/2 across every 2026 leaderboard. |
| **Hero-asset hull** | Hunyuan3D-2.1 (primary) | **Hunyuan3D-2.1 → secondary**, used for key/featured items | Highest open-weight texture fidelity (8K PBR), but 2–3× slower and Tencent-Community licence. Keep for hero props. |
| **Object recovery / inpaint** | FLUX.2-dev (non-commercial, long-form instruction following) | **Keep FLUX.2-dev primary; add Qwen-Image-Edit-2509 as commercial-safe + NVS-capable alternative** | Qwen-Image-Edit is **Apache-2.0** and is the only edit model benchmarked to *rotate objects under text instruction* (true instruction-driven NVS) where FLUX/Kontext cannot — directly relevant to occluded-face recovery. |
| **Dedicated turnaround/multi-view** | Hunyuan3D internal 6-view only | **Add MV-Adapter (Apache-2.0, camera-conditioned 6-view)** as an explicit orbit-conditioning option | Best-licensed dedicated NVS with stable ComfyUI node; gives camera-parametrised views rather than relying solely on Hunyuan's internal views. |
| **Input prep** | orbit render → upload | **Add BiRefNet-HR matting + optional IC-Light relight + enforce 512² square/diffuse spec** | The single biggest community-reported quality lever for image-to-3D; reduces baked-shadow false geometry and edge artefacts. |
| **LichtFeld engine** | v0.5.2 pinned | **Stay on v0.5.2 tag** (no newer tag exists); track master for RAD/sparkjs + CUDA-streams; evaluate the v0.5.0 plugin system | Upstream tag is unchanged; the opportunity is the plugin ecosystem (see §5), not a version bump. |

---

## 2. Multi-view / turnaround IMAGE generation (the conditioning step)

Three tracks exist in 2026: (1) dedicated camera-conditioned NVS diffusion; (2) end-to-end image-to-3D with an internal multi-view stage (Hunyuan3D); (3) general instruction-following editors driven to produce views.

| Model | Release | ComfyUI node | HF repo | Licence | VRAM | Output | Fit |
|---|---|---|---|---|---|---|---|
| **MV-Adapter** | Dec 2024 (ICCV'25) | `huanngzh/ComfyUI-MVAdapter` | `huanngzh/mv-adapter` | **Apache-2.0** | ~14 GB | 6 views @768 px, camera-conditioned, ControlNet-compat | **Best-licensed dedicated NVS.** Plugs into any SDXL checkpoint. Cap 768 px; instruction-following limited to SDXL backbone. |
| **Qwen-Image-Edit-2509** | Aug 2025 (upd Dec'25) | native; `HM-RunningHub/ComfyUI_RH_Qwen-Image` | `Qwen/Qwen-Image-Edit` | **Apache-2.0** | 24 GB (8 GB GGUF) | single-image edit; **instruction-driven view rotation** | Benchmarked above FLUX.1-Kontext/SeedEdit on instruction NVS; commercial-safe. **New recovery option.** |
| **SEVA / Stable Virtual Camera** | Mar 2025, v1.1 Jun'25 (ICCV'25) | `Pablerdo/ComfyUI-StableVirtualCameraWrapper` | `stabilityai/stable-virtual-camera` | Non-commercial | ~12–20 GB | 1–1000 frames, arbitrary trajectory | Highest-quality orbital NVS (beats CAT3D/ViewCrafter). NC-only → internal/exhibit use only. |
| **FLUX.2-dev** | Nov 2025 | ComfyUI-GGUF (Q4–Q8) | `black-forest-labs/FLUX.2-dev` | Non-commercial | 90 GB FP / 12–14 GB Q8 | single-image; best long-form prompt adherence (Mistral-3 24B encoder) | **Current recovery primary.** No camera-parametrised multi-view yet. |
| SV3D | Mar 2024 | native ComfyUI | `stabilityai/sv3d` | Non-commercial | ~20 GB | 21 orbit frames @576 px | Clean orbits, low res, no v2. |
| Era3D | 2024 | `MrForExample/ComfyUI-3D-Pack` | `pengHTYX/MacLab-Era3D-512-6view` | research (unverified) | 16 GB | 6 views + normals @512 px | Use only if you need paired normals. |
| FLUX.1-Kontext + turnaround LoRA | Jun/Jul 2025 | native FLUX | `reverentelusarca/kontext-turnaround-sheet-lora-v1` | Non-commercial | 18–20 GB | 5-view sheet | **Layout sheet, not metric NVS.** Stylised assets only — not for photoreal mesh conditioning. |
| Zero123++ v1.2 | 2024 | `ComfyUI-Easy-Use` | `sudo-ai/zero123plus-v1.2` | research | 8–12 GB | 6 views @320 px | Legacy lightweight fallback. |

**Instruction-following ranking (the FLUX.2 rationale, re-checked):** FLUX.2-dev (24B Mistral-3 encoder) remains the strongest open-weight *long-form* prompt follower, but **Qwen-Image-Edit is the better choice when the instruction implies a geometric/view change**, and it is Apache-2.0. HiDream-I1 (MIT, 17B) is a strong T2I but has no multi-view conditioning. Recommendation: **keep FLUX.2 for rich appearance description, add Qwen-Image-Edit for view-aware recovery and as the commercial-safe path.**

**Top-3 multi-view approaches for us:** (1) Hunyuan3D-2.1 internal 6-view (already wired) for the integrated path; (2) **MV-Adapter** for explicit camera-conditioned orbit sheets (new, Apache-2.0); (3) SEVA for highest-quality orbital frames where NC licence is acceptable.

---

## 3. Image-to-3D / multi-view-to-3D MESH (the hull step)

| Model | Release | ComfyUI node | HF repo | Licence | VRAM | PBR | Speed/obj | Verdict |
|---|---|---|---|---|---|---|---|---|
| **TRELLIS.2-4B** | Dec 16 2025 | `visualbruno/ComfyUI-Trellis2` (Win) · `PozzettiAndrea/ComfyUI-TRELLIS2` (Linux) | `microsoft/TRELLIS.2-4B` | **MIT** | 24 GB | ✅ base/metallic/roughness/opacity | 17–60 s | **PRIMARY.** Fast, permissive, multi-view (≤16), handles open/non-manifold topology. |
| **Hunyuan3D-2.1** | Jun 13 2025 | `visualbruno/ComfyUI-Hunyuan3d-2-1` · `kijai/ComfyUI-Hunyuan3DWrapper` | `tencent/Hunyuan3D-2.1` | Tencent-Community (verify EU/UK) | 10–29 GB | ✅ up to 8K | ~139 s | **SECONDARY / hero assets.** Best texture fidelity. |
| Pixal3D | May 2026 (SIGGRAPH'26) | `Saganaki22/Pixal3D-ComfyUI` | `TencentARC/Pixal3D` | MIT (verify NOTICE/EU) | ~30 GB | ✅ | 6–7 min | **TERTIARY/future.** TRELLIS.2 backbone + pixel-aligned latents → near-reconstruction fidelity. New, slow, licence ambiguity. |
| Step1X-3D | May 13 2025 | `Yuan-ManX/ComfyUI-Step1X-3D` | `stepfun-ai/Step1X-3D` | **Apache-2.0** | 27–29 GB | ⚠️ unconfirmed | ~152 s | Cleanest licence; verify PBR channels before relying. Stylised support. |
| SAM-3D-Objects | 2025 | `ComfyUI-SAM3DObjects` | `facebookresearch/sam-3d-objects` | Non-commercial | 32 GB | ✅ | ~40 min | **Last-resort fallback only** (already in stack). NC + very slow. |
| Hunyuan3D 3.0/3.1 | Feb 2026 | ComfyUI Partner Nodes | — (API) | proprietary API | — | ✅ + parts/UV/topology | <60 s | **API/login-gated, not local weights.** Watch only. |
| Hi3DGen | Mar 2025 (ICCV'25) | `Stable-X/ComfyUI-Hi3DGen` | `Stable-X/Hi3DGen` | MIT | 12–24 GB | ❌ geometry-only | — | Best raw geometry; needs external texturing. Defer. |
| TripoSG | Feb 2025 | `fredconex/ComfyUI-TripoSG` | `VAST-AI/TripoSG` | MIT | 8 GB | ❌ | fast | Geometry-only, single-view. |
| Direct3D-S2 | May 2025 (NeurIPS'25) | none | `wushuang98/Direct3D-S2` | MIT | 10–24 GB | ❌ (OBJ) | — | No ComfyUI node, no PBR. Skip. |
| PartCrafter | Jul 2025 (NeurIPS'25) | via 3D-Pack | `wgsxm/PartCrafter` | MIT | 8 GB | ❌ | — | **Part-aware** decomposition (≤16 parts, no seg input). Future option for complex objects. |
| SF3D | 2024 | `MrForExample/ComfyUI-3D-Pack` | `stabilityai/stable-fast-3d` | Stability (gated) | 6 GB | ⚠️ albedo only | ~0.5 s | Fast pre-screen/triage only. |

**Recommended hull fallback chain:** `TRELLIS.2-4B (MIT, primary)` → `Hunyuan3D-2.1 MV (hero/texture quality)` → `Hunyuan3D-2.0 MV` → `Hunyuan3D single-view` → `SAM-3D-Objects (NC, last resort)` → `convex hull`.

**Not yet usable:** Hunyuan3D-2.5 (no confirmed open weights), Hunyuan3D-3.x (API only).

---

## 4. Community / practitioner tips (apply to our ComfyUI calls)

1. **git-lfs before any model pull** — the single most common failure across TRELLIS.2 and Hunyuan3D is corrupted/pointer-stub downloads. Stage scripts must `git lfs install` and verify file sizes (non-zero, expected GB) before use.
2. **Background matting: BiRefNet-HR** (`ComfyUI-RMBG`) beats rembg on fine edges; run before any 3D model. BEN2 is runner-up.
3. **Lighting normalisation: IC-Light** (`ComfyUI-IC-Light-Native`) — strip bg → relight neutral top-light → feed 3D. Directional shadows bake in as false geometry.
4. **Input spec (universal):** 512×512, square centre-crop (Lanczos), single centred object, white/transparent bg, even diffuse light. Larger input does **not** help TRELLIS.2 (trained on 512 crops).
5. **TRELLIS.2 pitfalls:** disconnect IPAdapter nodes during 3D gen (backend conflict); `--lowvram --force-fp16` halves VRAM; single-GPU only (multi-GPU batch ~36% error rate) → matches our serial-per-object model.
6. **Hunyuan3D pitfalls:** run shape and texture as separate workflows + offload between (avoids 29 GB peak); pin KJNodes if using kijai wrapper; `opencv-contrib-python` not `opencv-python`.
7. **Multi-view input:** front+back minimum; all four sides substantially improves hidden-face geometry; **scale/exposure consistency across views matters more than view count** (seam artefacts otherwise).
8. **Denoise:** TRELLIS.2 texture bake ~0.6; Hunyuan paint ≤0.75; mesh-hole inpaint 0.4–0.5 subtle / 0.75–0.85 full replace.

---

## 5. LichtFeld Studio upstream + plugin ecosystem

- **Latest tag is still v0.5.2 (21 Apr 2026)** — our current pin. No v0.5.3/v0.6. **No version bump available.** Master has ~200–400 untagged commits since (RAD/sparkjs export — currently *broken* vs latest sparkjs, issue #1310; CUDA-streams PR #1302; equirectangular COLMAP loader PR #1289). **Do not chase master for RAD export yet.**
- **v0.5.0 introduced a real plugin system** (per-plugin Python `uv` envs, marketplace, hot-reload, undo/redo integration, plugins can expose extra MCP endpoints) **and the MCP server itself.** v0.5.1 added MRNF densification, NanoGS sparsification, **3DGS USD import/export**, depth modes. These are the relevant capabilities, not a tag bump.
- **Community plugins worth evaluating** (none modify our fork boundary; all are separate installs):
  - `alexmgee/lichtfeld-360-plugin` — **mirrors our exact SfM stack** (demux DJI/Insta360 → frames → SAM3 masking → COLMAP 4.1 ALIKED N16/N32 + LightGlue). Strong reference / potential adoption for the capture front-end.
  - `shadygm/Lichtfeld-COLMAP-Plugin` — pycolmap SfM (incremental + GLOMAP) inside LichtFeld.
  - `shadygm/Lichtfeld-Densification-Plugin` — RoMa-v2 dense init, +0.63 % PSNR / 13 % faster.
  - `jacobvanbeets/SplatReady` (MIT) — video→COLMAP dataset (the `splat_ready` referenced in work-order item 6).
- **Mesh extraction (MILo/CoMe/GaussianWrapping/PGSR/TSDF) remain standalone, not LichtFeld plugins** — our Docker-sidecar approach is correct and unchanged.
- **3DGS techniques upstream adopted in 2026:** ImprovedGS+ (our training primary — confirmed native since v0.5.0, −26.8 % time vs MCMC), MRNF, NanoGS, PPISP, 3DGUT, Faster-GS (bounty winner, 2.4× rasterise). Worth tracking: HAC++ (100× compression), MILo mesh-in-the-loop.

**Build/upgrade hazards if we ever move past v0.5.2:** plugin API v1 rejects `min_/max_lichtfeld_version` manifest fields; SDL3 replaced GLFW; ImGui→RmlUI panel migration; CUDA 12.8 min + driver ≥570; vcpkg rolls monthly (pin a dated commit, not floating).

---

## 6. Concrete action list (tracked in engineering log)

- [x] Fix consolidated Docker build (rclone `RCLONE_VERSION`→`--version` env collision; `env -u`).
- [ ] **Implement TRELLIS.2-4B hull client + workflow**, wire as primary in the hull fallback chain.
- [ ] Add **Qwen-Image-Edit** recovery workflow + config option (commercial-safe, view-aware).
- [ ] Add **MV-Adapter** camera-conditioned turnaround workflow option.
- [ ] Update `sota_registry.py` pins with verified models/dates/licences/node commits from this survey.
- [ ] Add input-prep hardening: BiRefNet-HR matting hook, 512² square/diffuse enforcement, git-lfs staging guard.
- [ ] Document upstream plugin ecosystem decision (adopt `lichtfeld-360`/`SplatReady` references) in work-order.

---

## 7. Open / unverified items to resolve before commercial deployment

- Hunyuan3D-2.x **Tencent-Community licence excludes EU/UK** — verify against deployment jurisdiction.
- Pixal3D LICENSE/NOTICE (MIT vs EU-exclusion residue from TRELLIS.2 dependency) — inspect directly.
- Step1X-3D PBR channel separation — run an inference test, inspect GLB materials.
- Era3D licence — research-only until confirmed.
- Leaderboard scores (Pixazo/Hi3DEval) — directional only; methodology not public.

*Full per-agent source lists retained in the engineering log / research thread.*
