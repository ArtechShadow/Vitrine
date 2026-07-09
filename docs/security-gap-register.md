# Security & assertion gap register

Status: **living** · Opened 2026-07-09 · Sources: adversarial re-audit (2026-07-09),
[`docs/audit/master-audit-2026-07-02.md`](audit/master-audit-2026-07-02.md),
[ADR-022](../research/decisions/adr-022-secure-single-image-architecture.md),
[ADR-024](../research/decisions/adr-024-internal-claude-enablement-gate.md).

This register records, for each **security/architecture assertion made in the README and
ADRs**, whether the code actually backs it, and what remains open. It exists because the
README historically stated ADR-022's *design goals* as accomplished fact. Verdicts are
adversarial: an assertion is only "TRUE" when the code enforces it.

## Legend

`FIXED (2026-07-09)` — closed by ADR-024 in this pass · `TRUE` — already backed by code ·
`PARTIAL` — partly backed · `OPEN` — asserted but not backed by code.

## Register

| # | Assertion (as marketed) | Verdict | Evidence / gap |
|---|---|---|---|
| 1 | Web panel binds loopback by default | **TRUE** | `src/web/app.py` defaults `LFS_WEB_HOST=127.0.0.1` and warns on wider binds. |
| 2 | LAN never sees any service (all host publishes loopback) | **FIXED (2026-07-09)** | Was FALSE — 7681/8188/45677/5902 published on `0.0.0.0`. ADR-024 D1 pins all five to `127.0.0.1` in `docker-compose.consolidated.yml`. |
| 3 | Web panel is the only I/O unless internal Claude is enabled | **FIXED (2026-07-09)** | Was FALSE — no gate existed; ttyd always up, Claude auto-launched on any credential. ADR-024 D2 adds `VITRINE_CLAUDE_ENABLED` (default 0) gating ttyd (`docker/vitrine-terminal.sh`, `supervisord.conf`) and `pipeline_runner._launch_claude_code()`. |
| 4 | Onboarding wizard is loopback-only | **FIXED (2026-07-09)** | Was FALSE — `onboarding/src/main.rs` bound `0.0.0.0:8088`. Now defaults `127.0.0.1:8088` via `VITRINE_ONBOARDING_HOST`. |
| 5 | VNC not LAN-reachable | **FIXED (2026-07-09)** (loopback) | Was FALSE — `x11vnc -nopw` on all interfaces. Now `-localhost` + loopback host publish. **Still OPEN:** no VNC password (relies on SSH tunnel). |
| 6 | Embedded terminal requires a token or is removed (ADR-022 D3) | **PARTIAL** | Terminal is now removed-by-default (gate) and loopback-bound when enabled, but has **no token/password of its own** when enabled. Mitigated by SSH-tunnel-only reach. |
| 7 | Single hardened mono-image is the entire runtime | **OPEN** | `milo`, `come` (compose), `artifixer` and `unreal`/`unreal-mcp-bridge` (overlay composes) remain separate sidecar images; `vitrine-comfyui` referenced but defined only via `scripts/run_comfyui.sh`. Accurate framing: "one primary image + GPU-1 batch sidecars." |
| 8 | Least-privilege isolation; secrets readable only by the service user | **OPEN** | Single shared `ubuntu` user with `NOPASSWD:ALL` sudo; ComfyUI runs as **root** (no `user=` in `supervisord.conf`); no per-component venvs; `HF_TOKEN`/`ANTHROPIC_API_KEY` passed as container-wide env, inherited by every child + visible via `docker inspect`. ADR-022 D2 not implemented. **High priority.** |
| 9 | ComfyUI not reachable beyond loopback | **PARTIAL** | Host publish now loopback (#2), but ComfyUI still `--listen 0.0.0.0` **inside** the container — required for cross-container `v2g-net` access, so left as-is by design; ComfyUI-Manager RCE risk noted by master audit remains. |
| 10 | Claude, when enabled, controls internal docker state incl. code + model files | **PARTIAL / TRUE-for-this-container** | Enabled Claude has root + unrestricted egress + RW on bind-mounted `src/pipeline`, `src/web` and the model volumes — so "code + model files" is accurate. Control of **sibling** containers via a Docker socket is **not** provisioned in this repo's own compose (no `docker.sock` mount); `docker exec milo/come` is designed to run from the host/agentbox. |

## Next actions (priority order)

1. **#8 least-privilege** — add `user=` to the ComfyUI supervisord program, create per-component OS users + venvs (ADR-022 D2), move `HF_TOKEN`/`ANTHROPIC_API_KEY` to Docker secrets. *Requires runtime validation on the rig — file-permission regressions are likely and cannot be tested in the doc environment.*
2. **#6 / #5** — add a ttyd token and a VNC password (or drop VNC) for defence-in-depth beyond the SSH tunnel.
3. **#7 mono-image** — either fold milo/come into the primary image (may be impossible due to the Python dependency conflicts that motivated the sidecars) or restate the claim accurately in the README.

## Validation note

The ADR-024 changes (#2–#5) are verifiable by inspection of the compose/supervisord/entrypoint/
Rust source. They have **not** been runtime-tested here (no container runtime in the doc
environment). Before relying on them, run `docker compose -f docker-compose.consolidated.yml
config` to confirm the port pins render, and boot once with `VITRINE_CLAUDE_ENABLED` unset to
confirm `:7681` has no listener and the pipeline queues jobs without launching Claude.
