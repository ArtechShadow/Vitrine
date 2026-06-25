# Vitrine — In-Container Claude Agent Roles

This document provisions the **Claude agents that run inside the pipeline containers** (via `claude-code`, the default `oversight.backend`/`artifact_vlm`). Each container's agent reads this so it knows **the end-to-end workflow and its specific role + responsibilities** — including the in-flight recovery it is expected to perform. Mount/point each container's `CLAUDE.md` at this file (or include it).

> Principle (do not bypass): deterministic stages run the work, but they **surface their result + a quality signal to the oversight agent**, which may accept / retry / re-engineer. The agents are the recovery layer — see [in-flight recovery & VRAM](#recovery--vram).

---

## The workflow (what every agent must know)

```
Drive/video ingest → frame extraction → COLMAP SfM (ALIKED+LightGlue / SIFT)
  → 3DGS training (LichtFeld: ImprovedGS+/MRNF/MCMC)
  → .ksplat (web)                                              [delivery]
  → SAM3 concept segmentation → key-item ranking
  → per-object hull:  orbit-render the object's splat (6 panels: F/L/B/R/top/bottom)
        → coverage-gate → FLUX.2 view completion for UNOBSERVED panels (ADR-017)
        → TRELLIS.2 multiview → PBR-textured GLB                (ADR-015)
  → environment mesh (CoMe / MILo / PGSR / TSDF)
  → USD scene graph (env mesh + per-object hulls + v2g:* lineage) + .ksplat
  → Unreal exhibit build (ADR-016/018): import USD → place objects → wire
        interactions → annotate with v2g:* → navigable interactive exhibit
```

Every object carries **`v2g:*` lineage** (video→frame→object) and provenance flags (`v2g:view_synth=true` = surface was FLUX.2-inferred, not measured). Lineage must never be silently dropped, and measured-vs-inferred must stay honest end-to-end.

---

## Per-container agents

### `gaussian-toolkit` — Pipeline Orchestrator + Oversight
The primary agent. Runs/oversees the Python pipeline (`src/pipeline`).
- **Role:** drive the stages above; for each ComfyUI/mesh/USD stage, **verify the result** (e.g. hull has geometry + PBR + full 360; mesh is watertight-ish; USD carries `v2g:*`) and **recover** on failure — retry, fall back down the strategy chain (TRELLIS.2 → Hunyuan3D → TSDF), re-prompt FLUX.2, or flag-and-continue. Never emit a half-broken object without recording it.
- **VRAM:** enforce the serial lifecycle (`model_lifecycle` + `/free`): FLUX.2 (~51 GB) and TRELLIS.2 (~24 GB) cannot co-reside on one 48 GB GPU. We have **2×48 GB** — split the generative and hull stages across GPUs where possible; otherwise `/free` between them.
- **Tools:** the LichtFeld MCP (`:45677`), ComfyUI API (`vitrine-comfyui:8188`), the pipeline modules, the registry idiot-check (`python -m pipeline.sota_registry check`).

### `vitrine-comfyui` — Generative GPU service
Hosts ComfyUI (FLUX.2 / TRELLIS.2 / Hunyuan3D / SAM3D). Not a decision-making agent — it is the GPU service the orchestrator + exhibit agents drive over the API. Its custom-node + weight state is the gating factor (see `comfyui_entrypoint.sh`); the orchestrator agent must read `/object_info` to know what's actually runnable.

### `vitrine-unreal` — Exhibit-Builder Shepherd (ADR-018)
The agent that assembles the interactive exhibit (DDD `ExhibitBuilder`).
- **Role:** in a **two-phase build** — (A) headless USD-bake pre-pass → build manifest; (B) running-editor MCP loop — **place** each reconstructed hull at its true USD transform, **wire interactions** (select → highlight → reveal → inspect via pre-authored Blueprint templates), **annotate** each object from `v2g:*` + manifest copy as in-world UMG, add a nav rig, **verify** (viewport/PIE), **iterate/recover**, and save the level + a build report.
- **Honest provenance:** annotate `v2g:view_synth=true` surfaces as *inferred*, not measured.
- **Tools:** the bridge (`mcp_bridge.py`, `:9100`) over UE first-party MCP (`:8000`) + Web Remote Control (`:30010`); UE Python (editor-only); third-party MCP servers for Blueprint editing.

---

## Recovery & VRAM
The system's self-recovery feature **exists and the agents own it** — do not bypass it:
- `model_lifecycle.ModelLifecycleManager` + `comfyui_control.free_vram` / the clients' `_free_vram()` = serial VRAM management.
- `OversightConfig` (`claude_code` overseer, model `claude-opus-4-6`) = the verify-retry / re-engineer loop.
- Each stage emits a result + quality signal; the agent decides accept / retry / recover and records it in the per-object lineage / build report.

**GPU conflict — DiffusionGemma:** the local LLM server (`diffusiongemma:cuda13`) occupies ~40 GB on GPU0. When running TRELLIS.2 hull generation (also GPU0), **stop DiffusionGemma first** (`docker stop diffusiongemma`). ComfyUI's `/free` only unloads its own models, not another process's VRAM. This is the single most common cause of TRELLIS.2 OOM.

See [`docs/engineering-log.md`](engineering-log.md), ADR-014/015/016/017/018, and the memory notes (`inflight-recovery-and-vram`, `object-reconstruction-sota-2026-06`).
