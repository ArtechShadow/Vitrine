# Code Boundaries

This document defines what is Vitrine's own code, what is the vendored LichtFeld tool, and what is experimental. It exists to keep ownership clear and make contribution decisions obvious.

---

## Background: Vitrine is a standalone project

**Vitrine** is a capture-adaptive video → structured-3D-scene → Unreal Engine 5.8 game-asset pipeline. It is **not** a fork of LichtFeld-Studio.

LichtFeld-Studio is a **pinned vendored tool** — a git submodule located at `vendor/lichtfeld-studio`, fixed to tag **v0.5.3**. Vitrine uses it for native 3DGS training, rendering, and the local MCP server. We never modify it; we update it only by bumping the submodule tag. See `research/decisions/adr-021-unfork-lichtfeld-to-vendored-tool.md` for the rationale.

> **Phased un-fork note:** the legacy in-tree upstream source (`src/core/`, `src/app/`, `src/mcp/`, `src/rendering/`, `src/training/`, `src/geometry/`, `src/io/`, `src/sequencer/`, `src/visualizer/`, `src/python/`, `cmake/`, `external/`, `eval/`, `tools/`, upstream `tests/`, `CMakeLists.txt`, `vcpkg.json`) is being removed in a host-validated follow-up commit. After that cleanup, `vendor/lichtfeld-studio` is the sole location of LichtFeld code.

---

## What's ours vs. what's the vendored tool

### Vendored tool: `vendor/lichtfeld-studio` (git submodule @ v0.5.3)

Everything under `vendor/lichtfeld-studio/` belongs to the LichtFeld-Studio project (GPL-3.0, MrNeRF). **Rules:**

- **Never modify any file under `vendor/lichtfeld-studio/`.**
- **Never push to or open PRs against the upstream repository.**
- To update: change the submodule pin to the target tag, run `git submodule update --init --recursive`, rebuild, test.
- The submodule is consumed in Docker by building LichtFeld from source inside the image; the resulting binary and MCP server are the integration surface.
  > ⚠️ As of the 2026-07-09 audit the consolidated Dockerfile still clones the legacy fork (masked by `|| true`); the vendored-submodule build is the intended path but is not yet the one the image build uses. Tracked in `docs/security-gap-register.md` / master-audit #3.

### Vitrine's own code

Everything below is written and maintained by the Vitrine project. These files are GPL-3.0 (derivative work).

#### Pipeline (`src/pipeline/`) — 41 modules

The video-to-structured-3D pipeline. Takes video files and produces a **textured polygonal scene for UE 5.8** (room mesh + per-object textured meshes as game assets via FBX with baked-texture materials), plus an optional compressed `.ksplat` for web. USD is an optional/archival side-artifact, not the deliverable (UE cannot import the native USD ParticleField; see `docs/ANTIPATTERNS.md`, `adr-019`).

| Category | Modules |
|----------|---------|
| Core | `stages.py`, `cli.py`, `__main__.py`, `config.py`, `preflight.py`, `__init__.py` |
| Ingestion | `drive_ingestor.py` (rclone Drive ingest), `fibonacci_sampler.py` (Fibonacci-sphere viewpoint coverage scoring) |
| Reconstruction | `colmap_parser.py`, `coordinate_transform.py`, `frame_selector.py`, `frame_quality.py` |
| Segmentation | `sam2_segmentor.py`, `sam3_segmentor.py`, `sam3d_client.py`, `mask_projector.py` |
| Mesh extraction | `mesh_extractor.py` (TSDF), `milo_extractor.py` (MILo sidecar), `come_extractor.py` (CoMe sidecar), `gaussianwrapping_extractor.py` (GaussianWrapping in milo sidecar), `mesh_cleaner.py` |
| Hull / object recovery | `view_completer.py` (FLUX.2 view completion), `trellis2_client.py` (TRELLIS.2 hull, primary), `hunyuan3d_client.py` (Hunyuan3D-2.1, fallback), `comfyui_inpainter.py` (FLUX/ComfyUI inpainting) |
| Rendering | `multiview_renderer.py`, `gsplat_trainer.py` |
| Texturing | `texture_baker.py`, `material_assigner.py` |
| Scene assembly | `blender_assembler.py` (Blender + Cycles), `usd_assembler.py` (OpenUSD; writes `v2g:*` lineage) |
| Delivery | `splat_optimizer.py` (splat-transform CLI wrapper) |
| ComfyUI / SOTA control | `comfyui_control.py` (ComfyUI driver), `model_lifecycle.py` (serial VRAM load/unload via `/free`), `sota_registry.py` (SOTA preflight / pins) |
| Agent / orchestration | `agent_llm.py` (DiffusionGemma reasoner client), `endpoints.py` (service-DNS endpoints), `manifest.py` (exhibit manifest) |
| Utilities | `mcp_client.py`, `quality_gates.py`, `person_remover.py` |

#### Web Interface (`src/web/`)

Flask application (port 7860) for video upload, job tracking, log streaming (SSE), 3D preview, and result download. Files: `app.py`, `job_manager.py`, `pipeline_runner.py`, `static/`, `templates/`.

#### Deployment (`docker/`, `Dockerfile.consolidated`, `docker-compose.consolidated.yml`)

| File | Purpose |
|------|---------|
| `Dockerfile.consolidated` | Main container (Ubuntu 24.04, CUDA 12.8, Python 3.12); builds LichtFeld from `vendor/lichtfeld-studio` |
| `docker/Dockerfile.milo` | MILo + optional GaussianWrapping sidecar (Ubuntu 22.04, CUDA 11.8, Python 3.10) |
| `docker/Dockerfile.come` | CoMe sidecar (Ubuntu 22.04, CUDA 12.1, Python 3.10) — gated: `INSTALL_COME=1` |
| `docker-compose.consolidated.yml` | Three-container compose: main + milo + come |
| `docker/entrypoint.sh` | Container entry script |
| `docker/supervisord.conf` | Process manager configuration |
| `docker/install_milo.sh`, `docker/install_come.sh`, `docker/install_gaussianwrapping.sh` | Sidecar dependency installers |
| `docker/run_docker.sh` | Launch helper |

#### Unreal Engine 5.8 overlay (`unreal/`)

Self-contained UE 5.8 overlay (ADR-016/ADR-019). Imports the textured mesh scene (FBX, baked-texture materials) as game-style UE assets. The textured-mesh/FBX scene is the contract; USD/Stage-Actor is a legacy/optional path.

| Path | Purpose |
|------|---------|
| `unreal/Dockerfile.unreal` | UE 5.8 image (`vitrine-unreal:5.8`), FROM NVIDIA CUDA base — no Epic GitHub-org access required |
| `unreal/docker-compose.unreal.yml` | Overlay compose for `unreal` + `unreal-mcp-bridge` containers (GPU1) |
| `unreal/engine/` | UE 5.8 Linux installed build (~73 GB, gitignored), bind-mounted read-only at `UE_ROOT=/opt/ue` |
| `unreal/runtime/` | `Vitrine.uproject`, `entrypoint.sh`, `import_and_render.py`, `import_usd_stage.py`, `mcp_bridge.py` (HTTP proxy :9100) |

#### Scripts (`scripts/`)

Pipeline runners, test harnesses, and utilities: `run_gallery_pipeline.py`, `run_object_separation.py`, `run_tsdf_mesh.py`, `assemble_gallery_usd.py`, `lichtfeld_mcp_bridge.py` (stdio MCP bridge for Claude Code), `hardware_trace.py`, `test_*.py`.

#### Onboarding Wizard (`onboarding/`)

Rust/Axum exhibit-manifest wizard (port 8088). Produces `exhibit.toml` for pipeline runs.

#### Research (`research/`)

ADRs, PRDs, DDDs, landscape analyses, and work orders. Research context for development decisions; not user-facing documentation.

#### Documentation (`docs/`)

Docusaurus site covering build, MCP, architecture, ADRs, workflows, troubleshooting, and pipeline output renders.

#### Our root files

| File | Purpose |
|------|---------|
| `README.md` | Vitrine project overview |
| `AGENTS.md` | Agent operating guide for MCP-driven workflows |
| `CLAUDE_CONTAINER.md` | Claude Code instructions inside the container |
| `BOUNDARIES.md` | This file |

---

## Decision framework

When deciding where new code goes:

1. **Does it belong in LichtFeld (3DGS training, rendering, MCP server internals)?** — Do not write it here. File an issue against `vendor/lichtfeld-studio` or wait for the submodule to be bumped; if truly missing, write a thin wrapper in `src/pipeline/mcp_client.py`.
2. **Does it extend the video-to-scene pipeline?** — Put it in `src/pipeline/`.
3. **Does it add a web endpoint or UI page?** — Put it in `src/web/`.
4. **Does it change container configuration?** — Put it in `docker/` or update `Dockerfile.consolidated`.
5. **Is it a research exploration or literature review?** — Put it in `research/`.
6. **Is it a one-off script or test harness?** — Put it in `scripts/`.
7. **Does it require CUDA 11.8 / Python 3.10?** — Put it in the MILo sidecar (`docker/Dockerfile.milo`).
8. **Does it require CUDA 12.1 / Python 3.10?** — Put it in the CoMe sidecar (`docker/Dockerfile.come`).
9. **Is it a new mesh extraction backend?** — Follow the ADR-003 uniform interface: `XConfig` dataclass, `is_X_available() -> bool`, `run_X(colmap_dir, output_dir, config) -> dict`. Name the module `{name}_extractor.py` in `src/pipeline/`. Add dispatch in `stages._select_mesh_backend()`.

---

## Experimental

Components built but not yet validated end-to-end.

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| SAM3 concept segmentation | `sam3_segmentor.py`, `sam3d_client.py` | Client built, needs HF_TOKEN | Text+visual concept prompts (4M concepts) |
| Texture baking | `texture_baker.py` | Skeleton written | Depends on clean mesh + xatlas |
| Material assignment | `material_assigner.py` | Skeleton written | Depends on texture baking |
| FLUX background inpainting | `comfyui_inpainter.py` | Client built | ComfyUI workflow dependency |
| ArtiFixer3D recon enhancement | `artifixer_adapter.py` (planned) | Sidecar UP, trial in progress | Optional, per-scene gated — see ADR-020 |
