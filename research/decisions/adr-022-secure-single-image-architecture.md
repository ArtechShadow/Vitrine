# ADR-022 — Secure single-image appliance with internal venv/user isolation

Status: **Accepted** (2026-07-02) · Supersedes the multi-container + host-bind-mount
model of ADR-016/021 for the *core* appliance · Companion: [PRD](../../docs/prd/vitrine-v2-secure-mega-image.md), [DDD](../../docs/design/ddd-vitrine-v2.md)

## Context

- The LichtFeld binary was consumed via a host bind-mount (`./build:/opt/gaussian-toolkit/build:ro`); when that host dir was emptied the whole training path silently fell back to gsplat (master audit blocker #3). Host-bind-mounting *code* (`src/web`, `src/pipeline`) has the same fragility class.
- ~8 services listen on `0.0.0.0` with no auth (audit finding #13). Not IT-signable.
- Operation depends on an error-prone host shell (tmux "tab 6") with fish-quoting hazards.
- ArtiFixer, ComfyUI and the Vitrine pipeline have **conflicting Python dependency stacks** (Wan2.1 diffusion vs gsplat/pyiqa vs ComfyUI) that cannot share one site-packages reliably.
- We proved LichtFeld-Studio v0.5.3 builds cleanly in `nvidia/cuda:12.8.0-devel-ubuntu24.04` (upstream's own CI recipe).

## Decision

Build **one image, the "Vitrine appliance,"** with the following architecture. Free-reign granted by the owner (2026-07-02) — not constrained by prior container choices.

### D1. Base image & multi-stage build
- Base: **`nvidia/cuda:12.8.0-devel-ubuntu24.04`** — the exact image LichtFeld v0.5.3 compiles in; `-devel` also serves COLMAP and any runtime JIT.
- **Stage `lichtfeld-builder`**: replicate upstream `ubuntu.yml` (Kitware cmake, gcc-14, vcpkg release-only, `xorg-dev/libsystemd-dev/libgtk-3-dev/...`, sm_89) → `LichtFeld-Studio` + its `liblfs_*.so` + vcpkg runtime `.so`. (Codified from the proven `lf_build2.sh`.)
- **Stage `runtime` (final)**: copy the LichtFeld binary + its runtime `.so` set into `/opt/lichtfeld/{bin,lib}` with `RUNPATH=$ORIGIN/../lib`; install the GUI runtime libs (`libgtk-3-0`, `libgdk-3-0`, USD/nvimgcodec deps) so it loads headless via Xvfb. **No bind-mount, no lib-staging, no orphaned-mount failure mode.**

### D2. Internal isolation — venvs + users (single image, separated concerns)
- **Venvs** under `/opt/venvs/`: `pipeline` (Vitrine + Flask web + torch/gsplat/pyiqa/rawpy/gdown), `artifixer` (Wan2.1 diffusion stack, its pinned torch), `comfyui` (ComfyUI + custom nodes). Native tools (CUDA, COLMAP, `/opt/lichtfeld/bin`) are shared on PATH.
- **Users** (least privilege): `vitrine` (uid 1000, web + orchestrator + terminal), `comfyui` (uid 1001), `artifixer` (uid 1002). Root only for supervisord (PID 1) + entrypoint setup.
- **Secret containment**: HF token, Anthropic key, Claude OAuth creds are `0600 vitrine:vitrine` under `/run/vitrine-secrets` (or `/home/vitrine/.claude`); **unreadable by `comfyui`/`artifixer`**. ArtiFixer jobs cannot exfiltrate credentials.
- Supervisord launches each `[program]` with its `user=` and a venv-python `command=`.

### D3. Exposure — loopback + SSH bridge (no LAN surface)
- Publish **only to the host's `127.0.0.1`** (e.g. `127.0.0.1:7860:7860`); the internal docker network still resolves `gaussian-toolkit:7860` for the agent. **Nothing on `0.0.0.0`.**
- The web UI is the sole operator surface; the embedded terminal (ttyd) requires a token or is removed. VNC gets a password or is dropped. ComfyUI/MCP/UE-RC are never LAN-reachable.
- Operators use `ssh -N -L 7860:localhost:7860 user@rig`. Instructions ship in-app + README.

### D4. Web UI is the operator plane (network/SSH inspection, tab6 = rebuild only)
- Extend the existing Flask app into the single control surface: raw drag-drop ingest (primary), Google pull (secondary), run browser + preview + per-run zip, `/api/diskusage`, `/api/health/processes`. All inspection is HTTP over the docker network / SSH bridge — no `docker exec`. The host shell is used **only** for `docker compose build/up`.

### D5. State model — bake code, volume the data (bind-mount deprecation staged)
- **Baked into the image**: all Python code (`src/pipeline`, `src/web`), the LichtFeld binary, ComfyUI + custom nodes, entrypoint/supervisor config.
- **Named volumes (external state)**: the ~216 GB model tree, `output/`, HF cache, Claude session. These are the only mounts.
- **No host *bind*-mounts of code or build.** Collapsing the model tree / `output/` further into the image is **deferred** pending the `/api/diskusage` study (R8/PRD) — a 216 GB layer is likely a non-starter, so this stays a named volume for now. **Noted, not actioned.**

## Consequences

**Positive:** one IT-signable artifact; LichtFeld can never go missing; dependency conflicts structurally impossible; least-privilege blast radius; operable by a non-expert over one SSH tunnel; reproducible (pins honoured, CI-gated).

**Negative / accepted:** larger image (multi-GB code+deps+binaries; mitigated by multi-stage dropping vcpkg buildtrees); a rebuild is heavier (mitigated by layer caching — venvs and the LichtFeld stage cache independently); the `milo`/`come`/`unreal` sidecars remain optional overlays outside the core image (acceptable — they're GPU-1 batch tools, not the operator surface).

## Alternatives rejected
- **Keep host-built LichtFeld bind-mount** — the exact failure we're eliminating.
- **Separate ArtiFixer/ComfyUI containers** — contradicts the single-image sign-off goal; venv+user isolation gives the same separation inside one image.
- **Shared single venv** — dependency hell (Wan2.1 vs gsplat vs ComfyUI torch pins).
- **Bind everything to `0.0.0.0` behind a host firewall** — not defensible for sign-off; one forwarded port = full compromise.
