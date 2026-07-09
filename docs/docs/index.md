---
sidebar_position: 1
---

# Getting Started — Vitrine

**Vitrine** is a standalone capture-adaptive video → structured-3D-scene → Unreal Engine 5.8
game-asset pipeline. CLI/package id: `vitrine`. The web setup tool is **Vitrine Onboarding**.
Code identifiers still say `video2splat` / `gaussian-toolkit`; a full code/repo rename is a
separate scheduled follow-up (ADR-015).

> **Vendored tool:** Native 3DGS training, rendering, and MCP control come from
> **LichtFeld Studio** (`vendor/lichtfeld-studio`, pinned at tag v0.5.3). Vitrine never
> modifies it; updates are a submodule bump only.

## v3 Architecture — Largely Implemented

A redesigned end-to-end pipeline is largely implemented; validated end-to-end on the rawcapdev run
(2026-07-02). Key additions:

- **`exhibit.toml` manifest** — a single human-authored TOML file is the pipeline's one input, carrying exhibit identity, objects of interest, Drive source, secrets (as `env:` references only), and pipeline/oversight overrides. Decided in ADR-013.
- **Claude Code as orchestrator** — the in-container Claude Code agent drives the stateless pipeline stages; there is no hidden state machine. DiffusionGemma 26B-A4B (host-served, OpenAI-compatible :8084) is the local **text** reasoner/overseer tool it calls, not a second orchestrator. It is text-only, so bulk per-frame *visual* artifact triage defaults to `claude_code` (a staged gemma-4 vision model is the fallback). ADR-013.
- **Serial model lifecycle** — a `ModelLifecycleManager` loads and unloads models stage-by-stage, bounding peak VRAM to the largest single stage rather than the sum of all stages. ADR-013.
- **`v2g-net` Docker mesh** — service-DNS endpoints replace hardcoded IP addresses; the orchestrator addresses peers as `http://comfyui:8188` etc. ADR-013.
- **Agent-controlled ComfyUI recovery** — the existing .48 ComfyUI (FLUX.2-dev + Hunyuan3D-2.1) is updated/pinned via the Salad add-on control API and driven by a `RecoveryController` plan→submit→VLM-evaluate→decide loop. ADR-014.
- **Vitrine Onboarding** — a frameworkless vanilla-JS + Rust/Axum setup wizard that edits the manifest, probes hardware for model selection, contains secrets server-side, and hands off to the Claude Code overseer. ADR-015. (The Rust/Axum binary and manifest-write route are implemented today; the hardware probe, OAuth, and provisioning flows in the full design remain unbuilt.)

See [v3 Pipeline Design](../architecture/v3-pipeline.md) and [Vitrine Onboarding](../onboarding.md) for details.

---