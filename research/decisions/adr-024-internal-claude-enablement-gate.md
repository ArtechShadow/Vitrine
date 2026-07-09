# ADR-024 — Internal-Claude enablement gate + full loopback host-publish pinning

Status: **Accepted** (2026-07-09) · Companion: [ADR-022](adr-022-secure-single-image-architecture.md)
(secure single-image appliance), [ADR-023](adr-023-archivespace-ux-consolidation.md)
(UX consolidation) · Audit input: [master-audit-2026-07-02 finding #13](../../docs/audit/master-audit-2026-07-02.md)

## Context

ADR-022 D3 decided "nothing on `0.0.0.0`; the web app is the single operator plane;
the embedded terminal requires a token or is removed." The master audit (finding #13)
and the 2026-07 adversarial re-audit both found that decision was **never executed**:
the Flask panel (:7860) was correctly loopback-pinned, but `docker-compose.consolidated.yml`
still published ttyd (:7681), ComfyUI (:8188), the LichtFeld MCP (:45677) and VNC (:5902)
on **all interfaces**, ttyd ran writable with no auth, VNC ran `-nopw` on all interfaces,
and the pipeline auto-launched Claude Code whenever any credential happened to be present.
There was **no enablement flag** — the in-container Claude intelligence was always live.

The intended product posture is: **the web upload + runtime-feedback panel is the only
operator I/O by default; the internal Claude intelligence is an explicit opt-in enabled at
setup, and only then does an interactive control surface exist.**

## Decision

D1 — **Pin every host publish to `127.0.0.1`.** All ports in
`docker-compose.consolidated.yml` (7860, 7681, 8188, 45677, 5902) are published on
loopback only. The LAN boundary no longer depends on any in-container bind address; the
sole external path is an SSH tunnel.

D2 — **Introduce `VITRINE_CLAUDE_ENABLED` (default `0`).** This single flag gates the
in-container Claude intelligence:
- ttyd (the Claude control terminal) is started by `docker/vitrine-terminal.sh` **only**
  when the flag is truthy; otherwise the wrapper exits 0 and supervisord
  (`autorestart=unexpected`, `exitcodes=0`) leaves `:7681` with no listener.
- `pipeline_runner._launch_claude_code()` refuses to auto-launch Claude Code unless the
  flag is set — regardless of whether an API key or OAuth session exists.
- The `claude-login` interactive hint is only printed when the flag is set.

D3 — **When enabled, ttyd binds `127.0.0.1` inside the container** (`--interface 127.0.0.1`),
so even the enabled terminal is reachable only through an SSH tunnel, never the LAN.

D4 — **VNC binds loopback** (`x11vnc -localhost`) as a debug-only surface.

D5 — **The Rust onboarding wizard defaults to `127.0.0.1:8088`** (was `0.0.0.0:8088`),
with `VITRINE_ONBOARDING_HOST` as an explicit opt-in.

## Consequences

- The default posture now matches the marketed "web panel is the only in/out" claim: with
  `VITRINE_CLAUDE_ENABLED=0`, no interactive shell exists and Claude never auto-starts.
- SSH-tunnel workflows are unchanged (`ssh -N -L 7860:localhost:7860`, and per-port tunnels
  for the loopback debug surfaces when needed).

## Deliberately still open (flagged, not closed here)

These remain gaps and are **not** claimed as done — see `docs/audit/master-audit-2026-07-02.md`
and `docs/security-gap-register.md`:

- ttyd, when enabled, has no token/password of its own (relies on loopback + SSH tunnel).
- VNC has no password (relies on loopback + SSH tunnel).
- ComfyUI still `--listen 0.0.0.0` **inside** the container (required for cross-container
  `v2g-net` access); only the host publish is loopback-pinned.
- ADR-022 D2 least-privilege isolation (separate OS users, per-component venvs, `user=` on
  the ComfyUI supervisord program which still runs as root, Docker-secret mounting of
  HF/Anthropic tokens instead of container-wide env) is **not** implemented.
- The "single mono-image" claim remains aspirational: milo/come/artifixer/unreal are still
  separate sidecar images.
