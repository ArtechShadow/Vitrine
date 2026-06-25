# ADR-015 — Object Reconstruction SOTA Refresh (TRELLIS.2 gating, Hunyuan PBR, Qwen recovery)

**Status:** Accepted (2026-06-19)
**Amends:** ADR-010 (key-item hull reconstruction), ADR-014 (agent-controlled ComfyUI integration)
**Drives:** `research/prd/prd-object-reconstruction-sota-2026-06.md`, `research/ddd/object-reconstruction-context.md`
**Evidence:** `research/2026-06-object-reconstruction-sota.md`; live `/object_info` of `vitrine-comfyui` (605 nodes, 2026-06-19)

---

## Context

ADR-010 named TRELLIS.2-4B the primary hull backend; `sota_registry.py` encodes that. A 4-agent SOTA sweep (June 2026) **confirms** TRELLIS.2 as the correct primary on the merits (MIT, ~17–60 s/obj, full PBR, native multi-view ≤16, mature pinnable node). However, grounding the decision in the *running* system surfaced three facts that the paper-level decision missed:

1. **TRELLIS.2 ComfyUI nodes are not installed** in `vitrine-comfyui`, and the weights (~25 GB) are not staged. "Primary" is currently fiction; Hunyuan3D-2.1 is the de-facto primary.
2. **The Hunyuan3D-2.1 PBR nodes _are_ installed** (`Hy3DMultiViewsGenerator`, `Hy3DBakeMultiViews`, `Hy3D21MultiViewsGeneratorWithMetaData`, `Hy3DHighPolyToLowPolyBakeMultiViewsWithMetaData`) but our workflow does not call them — so the working path emits untextured meshes.
3. **Qwen-Image-Edit nodes _are_ installed** (`TextEncodeQwenImageEdit`/`Plus`, `QwenImageDiffsynthControlnet`). The sweep shows Qwen-Image-Edit is Apache-2.0 *and* uniquely capable of instruction-driven view rotation — the ideal commercial-safe recovery complement to non-commercial FLUX.2.

A decision made only from the leaderboard would keep chasing a backend that cannot run today while ignoring two high-value wins that are one workflow away.

## Decision

1. **Keep TRELLIS.2-4B as the *designated* primary, but gate activation on a green idiot-check.** It becomes active only when `check_environment` confirms the node pack (pinned commit) **and** weights are staged. Until then the runtime primary is Hunyuan3D-2.1. The registry/strategy selector treats TRELLIS.2 as "preferred-when-available", never as a silent failure.

2. **Complete the Hunyuan3D-2.1 hull as a real PBR backend** using the installed `Hy3DMultiViewsGenerator` → `Hy3DBakeMultiViews` paint/bake nodes, producing albedo + metallic-roughness. This is the immediate quality win and the robust runtime primary.

3. **Add Qwen-Image-Edit as a first-class recovery model** alongside FLUX.2. `InpaintConfig.model` gains `qwen-image-edit`. In **commercial** posture the recovery default is Qwen-Image-Edit; in research posture FLUX.2 remains default for its long-form instruction following.

4. **Hull fallback chain is explicit and logged:** `TRELLIS.2 (when staged)` → `Hunyuan3D-2.1 MV (PBR)` → `Hunyuan3D-2.0 MV` → `Hunyuan3D SV` → `SAM-3D (NC, last resort)` → `convex hull`. Every downgrade is recorded in the per-object lineage (NFR-4).

5. **Every workflow JSON is validated against the target `/object_info` before commit** — no `class_type` is written that the running ComfyUI does not expose.

6. **TRELLIS.2 staging is a reproducible, pinned procedure** (clone+pin node pack, `git lfs` pull with size verification, smoke `/object_info` + one GLB), tracked as PRD phase P1.

## Alternatives considered

- **Force TRELLIS.2 now (install in the critical path).** Rejected for P0: node-pack build (CuMesh/o_voxel/flash-attn wheels) is a real risk and blocks all value behind one uncertain infra step. Deferred to P1 as a gated upgrade.
- **Stay FLUX.2-only for recovery.** Rejected: leaves no commercial-safe path and ignores Qwen's view-rotation capability that directly fits occluded-face recovery.
- **Adopt Hunyuan3D 3.x.** Rejected: API/login-gated partner nodes, not local weights (violates the pipeline's offline requirement). Watch-only.
- **MV-Adapter as the conditioning generator now.** Deferred to P2: Apache-2.0 and attractive, but nodes are not installed and the orbit-render path already supplies views; sequence it after the higher-value P0/P1 work.

## Consequences

**Positive:** a real PBR primary ships immediately; a commercial-safe recovery path exists; "primary" stops being fiction; selection is registry-driven and honest; decisions are grounded in the live system.

**Negative / cost:** two ComfyUI paths to maintain (Hunyuan + Qwen) plus the gated TRELLIS.2; Qwen and TRELLIS.2 weights must be staged; the strategy selector gains branching that must be tested.

**Neutral:** Hunyuan remains licence-conditional (EU/UK) — acceptable because Qwen+TRELLIS.2 provide the clean-licence route, and posture is surfaced by the idiot-check.

## Compliance / rollout

- P0 lands with `sota_registry check` updated and a structural validation of each new workflow against `/object_info`.
- TRELLIS.2 stays WARN ("not staged") in the registry until P1 staging passes, then is pinned and promoted.
- Supersedes the ADR-010 assumption that naming a primary is sufficient — a primary must be *runnable and idiot-checked* to be active.
