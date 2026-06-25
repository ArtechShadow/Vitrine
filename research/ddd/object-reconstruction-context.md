# DDD — Object Reconstruction (Generative Recovery + Hull) Bounded Contexts

**Status:** Active
**Drives implementation of:** ADR-015, PRD `prd-object-reconstruction-sota-2026-06`
**Extends:** `research/ddd/v3-e2e-extensions.md` (Generative Recovery bounded context + ACL)
**Maps to code:** `src/pipeline/{stages,hunyuan3d_client,comfyui_inpainter,comfyui_control,multiview_renderer,sota_registry,config}.py`, `src/pipeline/workflows/*.json`

This model makes the object-reconstruction component explicit so the ADR-015 changes land as coherent domain logic, not ad-hoc branches.

---

## 1. Bounded contexts

| Context | Responsibility | Owns | Upstream/ACL |
|---|---|---|---|
| **Hull Reconstruction** | Turn a per-object Gaussian subset + orbit views into a textured mesh hull | strategy selection, fallback chain, hull artifact + lineage | calls ComfyUI via ACL; reads registry |
| **Generative Recovery** | Recover occluded/missing object appearance (inpaint, view-aware edit) before hulling | recovery request/attempt/verdict, model choice | calls ComfyUI via ACL; reads registry |
| **ComfyUI ACL** (shared) | Anti-corruption layer translating domain intents → ComfyUI graph API and back | workflow submission, polling, output retrieval, VRAM lifecycle | wraps `comfyui_control.ComfyUIControl` |
| **SOTA Registry** (shared kernel) | Single source of truth for model choice, pins, licence/VRAM posture | `Element`/`ModelSpec`, `check_environment` | none (pure) |

## 2. Ubiquitous language

- **Hull** — the reconstructed, ideally PBR-textured mesh (GLB) of one object.
- **Backend** — a concrete hull generator (TRELLIS.2, Hunyuan3D-2.1-MV, …) bound to a registry `ModelSpec` + a workflow.
- **Strategy** — the ordered, registry-derived list of backends attempted for an object (the fallback chain).
- **Recovery** — generative completion of an object's appearance prior to hulling.
- **Posture** — research (non-commercial WARN) vs commercial (non-commercial FAIL); flips defaults.
- **Staged** — model weights present on disk AND ComfyUI nodes installed/pinned, per `check_environment`.
- **Lineage** — the recorded video→frame→object→backend provenance, including every downgrade.

## 3. Aggregates, entities, value objects

**Hull Reconstruction**
- `ObjectHullRequest` (aggregate root): `{object_id, ply_path, orbit_views[], quality_preset, seed, posture}`.
- `HullStrategy` (value object): ordered `BackendChoice[]` resolved from the registry + staging state. Invariant: every member is *staged* or explicitly marked `preferred-when-available`; the chain always ends in `convex_hull` (always-available).
- `BackendChoice` (value object): `{registry_key, model_name, workflow, vram_gb, licence, staged: bool}`.
- `HullResult` (entity): `{mesh, glb_bytes, backend_used, textured: bool, pbr: bool, downgrades[], error?}`.

**Generative Recovery** (extends v3-e2e-extensions)
- `RecoveryRequest` (aggregate root): `{image, mask, instruction, model, denoise, seed, posture}`.
- `RecoveryAttempt` (entity): one ComfyUI submission + outcome.
- `RecoveryVerdict` (value object): `{accepted: bool, reason, by: agent|heuristic}` — recovery may be retried or vetoed.

**Shared**
- `ModelSpec` / `Element` (SOTA Registry shared kernel — already in `sota_registry.py`).

## 4. Domain services

- **HullStrategySelector** (`stages.py` hull section): resolves `HullStrategy` from registry + `check_environment` staging state + posture. Pure-ish: given registry+env → ordered chain. Encodes ADR-015 chain. Emits a `BackendDowngraded` event per fall-through.
- **RecoveryModelSelector** (`comfyui_inpainter.py`/`config.py`): chooses recovery model from `InpaintConfig.model` + posture (ADR-015 §3: commercial → Qwen default).
- **ComfyUI ACL** (`comfyui_control.py` + per-client wrappers): `submit_workflow → wait → download_outputs → free_vram`; the only place domain code touches ComfyUI node `class_type`s. Workflow templates live in `workflows/*.json` and are validated against `/object_info`.

## 5. Domain events (for lineage / ledger — NFR-4)

- `RecoveryRequested` / `RecoveryCompleted{model, accepted}`
- `HullStrategyResolved{chain[]}`
- `BackendAttempted{backend}` → `BackendSucceeded{backend, pbr}` | `BackendDowngraded{from, to, reason}`
- `HullProduced{object_id, backend, textured, pbr}`

All events are recorded in the per-object lineage so a downgrade (e.g. TRELLIS.2 not staged → Hunyuan, or Hunyuan untextured → SV) is never silent.

## 6. Invariants

- **I1** A backend is only *attempted* if `staged` (weights + pinned nodes), except the always-available `convex_hull`.
- **I2** No co-resident model exceeds GPU VRAM (serial lifecycle) — enforced by `check_environment` before the run, honoured by `free_vram()` between stages.
- **I3** In commercial posture, no non-commercial backend/recovery model may be the *selected* path (it may remain a WARN fallback only if never reached).
- **I4** Every workflow `class_type` exists in the target `/object_info` (validated pre-commit).
- **I5** The fallback chain is total: it always terminates in a producible hull (`convex_hull`).

## 7. Context map (flow)

```
orbit views ─┐
             ▼
   [Generative Recovery]  ── ACL ──▶ ComfyUI (FLUX.2 | Qwen-Image-Edit | FLUX.1-Fill)
             │  RecoveryVerdict
             ▼
   [Hull Reconstruction]  ── ACL ──▶ ComfyUI (TRELLIS.2* | Hunyuan3D-2.1-MV-PBR | … | convex hull)
             │  HullResult (+ downgrades)
             ▼
        USD lineage / ledger        (* = preferred-when-staged)
```

This model is the contract the ADR-015 implementation must satisfy: registry-driven strategy, honest downgrades, posture-aware recovery, ACL-isolated ComfyUI coupling.
