# Contributing to Vitrine

Thanks for your interest in contributing! Vitrine is a standalone capture-adaptive
video → structured-3D-scene → Unreal Engine 5.8 game-asset pipeline. It **vendors**
LichtFeld Studio as a pinned tool (`vendor/lichtfeld-studio`, git submodule); it is
not a fork of it (see ADR-021, `research/decisions/adr-021-unfork-lichtfeld-to-vendored-tool.md`).

## Where contributions go

- **Python pipeline** (`src/pipeline/`) — the video-to-scene stages (ingest,
  reconstruction, segmentation, mesh extraction, texturing, scene assembly). See
  `BOUNDARIES.md` for the module map and the decision framework for where new
  code belongs.
- **Flask web UI** (`src/web/`) — upload, job tracking, log streaming, 3D
  preview, and result download.
- **Docker workflow** (`docker-compose.consolidated.yml`, `Dockerfile.consolidated`,
  `docker/`) — container build and the MILo/CoMe sidecars.
- **ADRs** (`research/decisions/`) — architecture decisions. Propose significant
  changes as a new ADR before implementing them.

## The one hard rule: never touch the vendored tool

`vendor/lichtfeld-studio` is a pinned git submodule (currently v0.5.3). **Never modify
any file under `vendor/lichtfeld-studio/` and never open a PR against the upstream
repository.** If LichtFeld itself needs a fix or feature, file it upstream and wait,
or write a thin wrapper against its existing surface in `src/pipeline/mcp_client.py`.
To pick up upstream changes, bump the submodule pin to a new tag:

```bash
git -C vendor/lichtfeld-studio fetch --tags
git -C vendor/lichtfeld-studio checkout <new-tag>
git add vendor/lichtfeld-studio
```

Then rebuild the image and re-test. See `BOUNDARIES.md` for the full ownership
model and `AGENTS.md` for how Vitrine calls LichtFeld over its MCP surface at
runtime.

## Getting Started

1. **Find or propose work** — check open issues, or open one to discuss a new
   feature before writing it.
2. **Setup** — bring the stack up with `docker compose -f docker-compose.consolidated.yml up`;
   see `README.md` and `docs/` for detailed build/run instructions.
3. **Make your changes** — follow the existing style of the module you're
   touching (PEP 8 / type hints for Python, `ruff` if configured). Add or update
   tests under the relevant `tests/`.
4. **Submit a Pull Request** — describe what changed and why, link related
   issues, and note any ADR the change implements or supersedes.

## Need help?

- `README.md` for the project overview
- `BOUNDARIES.md` for what's Vitrine's vs. what's vendored
- `CLAUDE_CONTAINER.md` for the in-container orchestration workflow
- `research/decisions/` for ADRs explaining prior design choices

### Vendored-tool issues

If you hit a bug in LichtFeld-core training/rendering itself (not in how Vitrine
calls it), that belongs upstream: https://github.com/MrNeRF/LichtFeld-Studio.
Vitrine does not carry local patches to the vendored tool.

## License

Contributions are licensed under GPLv3.
