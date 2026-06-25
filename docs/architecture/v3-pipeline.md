# v3 Pipeline Design Reference

> **Status (2026-06-05): largely built; core validated end-to-end on real data.** The operational
> scaffolding (manifest, serial lifecycle, `v2g-net`, idiot-check, onboarding — ADR-013/015) is built
> and host-validated, and the reconstruct→segment→isolate→mesh→USD path was run end to end on a real
> 80-frame scene (June 2026). Still in progress: SOTA single-image hulls (TRELLIS.2/Hunyuan node
> builds), the FLUX.2 recovery loop, gemma VLM serving, and a fresh-capture (Drive→ingest→COLMAP) run.
> The design below is decided in ADR-012 through ADR-015 (amended in place to current choices); see
> [report/main_v4.tex](../../report/main_v4.tex) for the consolidated current-state account and the
> per-capability status table.

This page ties the four decision records together into a single design reference.

| Source ADR | Subject |
|-----------|---------|
| `adr-012-sota-tooling-modernisation.md` | SOTA defaults: **CoMe** mesh (default), ALIKED+LightGlue, **TRELLIS.2**/Hunyuan3D-2.1 hulls, FLUX.2-dev |
| `adr-013-ingest-manifest-serial-model-lifecycle.md` | `exhibit.toml`, `ModelLifecycleManager`, `v2g-net`, Claude Code orchestrator, DiffusionGemma reasoner tool (text-only, host-served :8084) |
| `adr-014-agent-controlled-comfyui-integration.md` | ComfyUI update/pin, Salad control API, `RecoveryController` agent loop |
| `adr-015-vitrine-web-onboarding.md` | Vitrine Onboarding wizard, hardware-aware selection, secret containment, setup→agent hand-off |

---

## `v2g-net` — Docker mesh topology

```
  ┌─────────────────────────────────────────────────────────┐
  │  v2g-net  (user-defined bridge on the .48 GPU host)      │
  │                                                          │
  │  ┌──────────────────────────────┐                        │
  │  │  gaussian-toolkit            │  ← pipeline orchestrator│
  │  │  (GPU 0)                     │    Claude Code (ttyd :7681)│
  │  │  stages.py / orchestrator.py │    addresses peers by  │
  │  │  manifest.py / lifecycle.py  │    DNS name, not IP     │
  │  └────────────┬────────────────┘                        │
  │               │  http://comfyui:8188  (graph API)        │
  │               │  http://comfyui:3001  (Salad control)    │
  │               │  http://host.docker.internal:8084 (DiffusionGemma reasoner)│
  │               │  docker exec milo / come                 │
  │               │                                          │
  │  ┌────────────▼────────────┐                            │
  │  │  comfyui                │                            │
  │  │  :8188  graph API       │                            │
  │  │  :3001  Salad control   │                            │
  │  │  FLUX.2-dev fp8mixed    │                            │
  │  │  Hunyuan3D-2.1 nodes    │                            │
  │  │  Mistral-3 enc          │                            │
  │  └─────────────────────────┘                            │
  │                                                          │
  │  ┌──────────────────┐  ┌──────────────────────────────┐  │
  │  │  milo (sidecar)  │  │  come (sidecar)              │  │
  │  │  GPU 1           │  │  GPU 1 — gated INSTALL_COME=1│  │
  │  │  CUDA 11.8       │  │  CUDA 12.1, Python 3.10      │  │
  │  │  docker exec     │  │  docker exec                 │  │
  │  └──────────────────┘  └──────────────────────────────┘  │
  └─────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────┐
  │  agent-llm  (host service, NOT on v2g-net)              │
  │  host :8084  llama-diffusion-gemma-visual-server        │
  │  DiffusionGemma 26B-A4B  Q8_0  (~4B active MoE)         │
  │  OpenAI-compatible  /v1/chat/completions  /health       │
  │  TEXT-ONLY reasoner/overseer (FR-28)                    │
  │  reached via http://host.docker.internal:8084           │
  └─────────────────────────────────────────────────────────┘
```

Service-DNS endpoints replace the hardcoded `localhost:port` values that appear in the current
`config.py` (lines 135–136, 152–153, 171). The `ModelLifecycleManager` hard-tier drives
`docker stop` / `docker start` on `comfyui` over this network; DiffusionGemma is host-served (an
external endpoint reached via `host.docker.internal:8084` / `extra_hosts: host-gateway`), not a
container the manager stops/starts. ADR-013, D-013.3.

---

## Manifest → provision → hand-off → pipeline flow

```
  User
    │
    │  opens browser → vitrine-setup (127.0.0.1:<ephemeral>)
    ▼
  ┌──────────────────────────────────────────────┐
  │  Vitrine Onboarding wizard (ADR-015)          │
  │                                              │
  │  Step 1: Exhibit identity                    │
  │  Step 2: Objects of interest                 │
  │  Step 3: Hardware probe → model selection    │  /api/hardware → nvidia-smi
  │  Step 4: HF token + Google Drive OAuth       │  tokens stored server-side only
  │  Step 5: Provision & hand-off                │
  │    ├── validate manifest (JSON Schema)       │
  │    ├── probe + pin .48 ComfyUI               │  Salad control API :3001
  │    │   (ensure FLUX.2-dev, Hunyuan3D-2.1)   │
  │    ├── start v2g-net; verify host agent-llm  │  DiffusionGemma is host-served (:8084)
  │    ├── write provision.status = "ready"      │
  │    └── emit hand-off event                  │
  └───────────────────────┬──────────────────────┘
                           │
                           │  exhibit.toml (finalised)
                           ▼
  ┌──────────────────────────────────────────────┐
  │  Claude Code overseer (ttyd :7681)  (ADR-013) │
  │  "no hidden state machine"                   │
  │                                              │
  │  1. Load manifest → materialise PipelineConfig│
  │  2. Plan: translate [[objects]] → SAM3 cpts  │
  │  3. Call pipeline stages (stateless funcs)   │
  │     via stages.py / orchestrator.py          │
  │  4. For each key-priority object:            │
  │     RecoveryController loop (ADR-014)        │
  │  5. Write artifacts → /data/output/JOB_ID/  │
  │  6. Drive write-back (rclone, ADR-015)       │
  └──────────────────────────────────────────────┘
```

---

## `exhibit.toml` manifest

The manifest schema is the authoritative human-authored input. Full schema reference in
`research/decisions/adr-013-ingest-manifest-serial-model-lifecycle.md`, D-013.1.

```toml
schema_version = "1.0"

[exhibit]
id          = "tate-2026-bronze"
name        = "Bronze Forms — Tate Modern"
venue       = "Tate Modern, London"
date        = "2026-06-01"

[[objects]]
id           = "obj-001"
name         = "Reclining Figure"
sam3_concept = "large bronze reclining human figure"
priority     = "key"          # triggers hull + FLUX.2 recovery
expected_count = 1

[drive]
url              = "https://drive.google.com/drive/folders/<id>"
rclone_remote    = "gdrive"
writeback        = true
writeback_subdir = "vitrine-output"

[secrets]                     # env: references only — never inlined
hf_token           = "env:HF_TOKEN"
gcloud_credentials = "env:GOOGLE_APPLICATION_CREDENTIALS"

[pipeline]                    # optional overrides onto PipelineConfig defaults
mesh_backend = "milo"
matcher      = "aliked_lightglue"

[oversight]
backend      = "claude_code"  # claude_code (default) | diffusiongemma (host text reasoner :8084)
artifact_vlm = "claude_code"  # default; DiffusionGemma is text-only, so visual triage uses
                              # claude_code (or the staged gemma-4 vision fallback)

[models]                      # written by Vitrine Onboarding (ADR-015 D-015.3)
inpaint            = "flux2-dev-fp8mixed"
hull               = "hunyuan3d-2.1"
matcher            = "aliked_lightglue"
mesh               = "milo"
artifact_vlm_quant = "Q5_K_M"   # staged gemma-4 vision fallback only; the host reasoner is
                                # DiffusionGemma 26B-A4B Q8_0 (text-only), not selected here
```

**Secret rule:** `env:NAME` indirection is mandatory. The `manifest.py` loader resolves references
at parse time and strips secrets before writing the JSON run snapshot. A missing env-var is a hard,
named failure (ADR-013, D-013.1).

---

## RecoveryController agent loop

For each `priority = "key"` object, the orchestrator invokes the `RecoveryController` (ADR-014,
D-014.3). It is stateless — the orchestrator calls it, it does not call back:

```
orchestrator
    │
    ├─ plan: compose FLUX.2 inpaint graph
    │         from template + object identity + artifact_report (FR-27)
    │
    ├─ submit: POST /prompt  →  comfyui:8188 (graph API)
    │           poll /history/{id}
    │           fetch output via /view
    │
    ├─ evaluate: visual scoring needs a vision model — the staged gemma-4 vision
    │             fallback (GGUF + mmproj) or the claude_code backend; text-only
    │             DiffusionGemma (host :8084) handles the planning/reasoning, not pixels
    │             prompt: "Does this recovery look plausible for <object>?"
    │             returns: score, verdict, bbox annotations
    │
    ├─ decide:
    │   accept      → write artifact to /data/output/JOB_ID/objects/
    │   re-prompt   → adjust denoise/guidance/seed/mask, retry (bounded budget)
    │   veto        → mark unrecoverable, annotate ledger, continue
    │
    └─ release: Salad control POST /free  →  comfyui:3001
                (hard-unload FLUX.2-dev before next heavy stage)
```

Every attempt, the vision-model verdict (gemma-4 fallback / claude_code; DiffusionGemma cannot
see), and the reason are written to the per-video ledger and
`v2g:*` lineage (ADR-009/011). Nothing is silently dropped. ADR-014, D-014.3.

---

## Serial model lifecycle

The `ModelLifecycleManager` context manager wraps each pipeline stage (ADR-013, D-013.2):

```
with lifecycle.stage("inpaint", ModelSpec(engine="comfyui", vram_gb=32, isolation="hard")):
    # comfyui container started (hard tier: docker start)
    # VRAM headroom asserted ≥ 32 GB
    comfyui_inpainter.run(...)
    # comfyui container stopped (docker stop) — driver-level reclamation
```

The `soft` tier uses in-process free (ComfyUI `POST /free`, `torch.cuda.empty_cache()`). The `hard`
tier uses `docker stop` / `docker start` over `v2g-net`. FLUX.2 ↔ Hunyuan3D transitions use `hard`
to prevent VRAM fragmentation between back-to-back 32 GB + 16 GB loads.

---

## SOTA tooling defaults (ADR-012)

| Axis | Current (v2) | v3 default (proposed) | Fallback |
|------|-------------|----------------------|---------|
| Mesh backend | TSDF | **MILo** | TSDF (no sidecar) |
| SfM matching | SIFT exhaustive | **ALIKED + LightGlue** | SIFT exhaustive |
| Hull reconstruction | Hunyuan3D-2.0 | **Hunyuan3D-2.1** | Hunyuan3D-2.0 |
| Inpainting | FLUX.1-Fill-dev | **FLUX.2-dev fp8mixed** | FLUX.1-Fill-dev |

Note: earlier design drafts referenced "FLUX.1 Kontext" — that wording is superseded. The binding
inpaint target is **FLUX.2-dev** (already staged on the `.48` host), per ADR-013 model-selection
audit (2026-06-04). ADR-012, D-012.3.
