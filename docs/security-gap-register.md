# Security & assertion gap register

Status: **living** · Opened 2026-07-09 · Sources: adversarial re-audit (2026-07-09),
[`docs/audit/master-audit-2026-07-02.md`](audit/master-audit-2026-07-02.md),
[ADR-022](../research/decisions/adr-022-secure-single-image-architecture.md),
[ADR-024](../research/decisions/adr-024-internal-claude-enablement-gate.md).

> **Runtime validation pass (2026-07-09, evening — on the rig).** The ADR-024
> changes were validated AND APPLIED live: the running `gaussian-toolkit`
> container predated ADR-024 and was still publishing 7681/8188/45677/5902 on
> `0.0.0.0` — recreated from the current compose; `ss -tlnp` now shows ALL
> pipeline ports (7860/7681/8188/8200/45677/5902) on `127.0.0.1` only. Three
> NEW findings fixed in the same pass (see #11–#13). The in-image ttyd gate
> (#3) needs the next image rebuild — the baked `supervisord.conf` predates it;
> until then the loopback publish is the control. Traversal probes against the
> live file API confirmed the jail (`../`, encoded, absolute, run-id traversal
> all refused; extension allow-list enforced).

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
| 3 | Web panel is the only I/O unless internal Claude is enabled | **FIXED + LIVE (2026-07-10)** | Was FALSE — no gate existed; ttyd always up. ADR-024 D2 adds `VITRINE_CLAUDE_ENABLED` (default 0) gating ttyd (`docker/vitrine-terminal.sh`, `supervisord.conf`). **Image rebuilt 2026-07-10 and container recreated; runtime-verified: with the default, `:7681` has NO listener** (was a live listener until this rebuild — the baked conf had predated the gate). |
| 4 | Onboarding wizard is loopback-only | **FIXED (2026-07-09)** | Was FALSE — `onboarding/src/main.rs` bound `0.0.0.0:8088`. Now defaults `127.0.0.1:8088` via `VITRINE_ONBOARDING_HOST`. |
| 5 | VNC not LAN-reachable | **FIXED (2026-07-09)** (loopback) | Was FALSE — `x11vnc -nopw` on all interfaces. Now `-localhost` + loopback host publish. **Still OPEN:** no VNC password (relies on SSH tunnel). |
| 6 | Embedded terminal requires a token or is removed (ADR-022 D3) | **PARTIAL** | Terminal is now removed-by-default (gate) and loopback-bound when enabled, but has **no token/password of its own** when enabled. Mitigated by SSH-tunnel-only reach. |
| 7 | Single hardened mono-image is the entire runtime | **OPEN** | `milo`, `come` (compose), `artifixer` and `unreal`/`unreal-mcp-bridge` (overlay composes) remain separate sidecar images; `vitrine-comfyui` referenced but defined only via `scripts/run_comfyui.sh`. Accurate framing: "one primary image + GPU-1 batch sidecars." |
| 8 | Least-privilege isolation; secrets readable only by the service user | **OPEN** | Single shared `ubuntu` user with `NOPASSWD:ALL` sudo; ComfyUI runs as **root** (no `user=` in `supervisord.conf`); no per-component venvs; `HF_TOKEN`/`ANTHROPIC_API_KEY` passed as container-wide env, inherited by every child + visible via `docker inspect`. ADR-022 D2 not implemented. **High priority.** |
| 9 | ComfyUI not reachable beyond loopback | **PARTIAL** | Host publish now loopback (#2), but ComfyUI still `--listen 0.0.0.0` **inside** the container — required for cross-container `v2g-net` access, so left as-is by design; ComfyUI-Manager RCE risk noted by master audit remains. |
| 10 | Claude, when enabled, controls internal docker state incl. code + model files | **PARTIAL / TRUE-for-this-container** | Enabled Claude has root + unrestricted egress + RW on bind-mounted `src/pipeline`, `src/web` and the model volumes — so "code + model files" is accurate. Control of **sibling** containers via a Docker socket is **not** provisioned in this repo's own compose (no `docker.sock` mount); `docker exec milo/come` is designed to run from the host/agentbox. |
| 11 | Owner ComfyUI (`run_comfyui.sh` :8200) loopback-only | **FIXED (2026-07-09 pm)** | Was FALSE and missed by #9's verdict — the script published `-p 8200:8188` on `0.0.0.0` (ComfyUI: no auth, RCE-class Manager surface). Now `-p 127.0.0.1:8200:8188`; live-verified. Cross-container access unchanged (v2g-net service DNS). |
| 12 | `LFS_WEB_HOST=127.0.0.1` compose default is "secure by default" | **FIXED (2026-07-09 pm) — was a functional regression, not a hardening** | In-container loopback bind made the pinned host publish (and therefore the documented SSH-tunnel path) DEAD: docker-proxy connects to the container's bridge IP, never its loopback. The boundary is the `host_ip: 127.0.0.1` publish; compose now sets the in-container bind to `0.0.0.0` with the rationale documented in compose + `app.py`. Live-verified: `:7860` answers via the tunnel path AND remains loopback-pinned on the host. |
| 13 | File API rejects malformed paths cleanly | **FIXED (2026-07-09 pm)** | Live probe found `%00` (NUL) in `?path=` produced a 500 (unhandled exception past the jail). `files_api._jailed` now rejects control bytes with 400. Traversal probes (plain/encoded/absolute/run-id) all correctly 403/404. |
| 14 | ttyd / VNC have a second factor beyond the tunnel | **DONE + LIVE (2026-07-10)** | `VITRINE_TTYD_CREDENTIAL` (ttyd basic-auth) + `VITRINE_VNC_PASSWORD` (x11vnc) added + plumbed through compose. **Image rebuilt + container recreated 2026-07-10; both branches runtime-verified** (disabled → no listener; enabled → loopback ttyd, warns when no credential). Default remains tunnel-only (warned at boot); operators set values for the second factor. Closes the action items under #5/#6 at the config level. |

## Next actions (priority order)

1. **#8 least-privilege** — add `user=` to the ComfyUI supervisord program, create per-component OS users + venvs (ADR-022 D2), move `HF_TOKEN`/`ANTHROPIC_API_KEY` to Docker secrets. *Requires runtime validation on the rig — file-permission regressions are likely.* **Now the highest open item.**
2. ~~Image rebuild~~ — **DONE 2026-07-10** (image `ed36b0bd26e6`, container recreated): ttyd gate (#3) + credential paths (#14) are LIVE; SPA baked (retires the live-injection).
3. **#7 mono-image** — either fold milo/come into the primary image (may be impossible due to the Python dependency conflicts that motivated the sidecars) or restate the claim accurately in the README.
4. **Set the #14 credentials** in the operator `.env` when enabling the terminal / using VNC.

## Validation note

**Superseded 2026-07-09 pm:** the runtime validation the original note requested has been
performed on the rig — compose port pins render AND are applied (containers recreated);
`ss -tlnp` shows every pipeline port loopback-only; the web tunnel path works (after fixing
#12); live traversal + malformed-path probes ran against the file API (#13). Remaining
runtime caveat: the ttyd gate itself activates at the next image rebuild (baked conf),
tracked as action 2 above.
