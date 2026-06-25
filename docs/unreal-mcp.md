# Unreal Engine 5.8 MCP Bridge

**ADR:** ADR-016 (`research/decisions/adr-016-unreal-scenegraph-export.md`)
**Status:** **LIVE / validated end-to-end (2026-06-21).** `docker compose -f
unreal/docker-compose.unreal.yml up -d unreal unreal-mcp-bridge` brings up a
**persistent UE 5.8 editor** (`vitrine-unreal:5.8`, ~6.19 GB, in-repo engine,
GPU1, real Vulkan RHI on an Xvfb display, VNC host `:5905`) that loads `scene.usda`
as a live `UsdStageActor` and mirrors `v2g:*` onto actor tags. The editor reaches
**healthy**, the **bridge auto-starts**, and `GET http://unreal-mcp-bridge:9100/health`
proxies to `unreal:30010` and returns the RC route list. Web Remote Control
(`:30010`, **primary**) is bound `0.0.0.0` and reachable cross-container; the
first-party MCP plugin (`:8000`) is experimental/secondary (currently reports
`down` through the bridge). Offscreen MRQ render (camera/sequence) is the remaining
work. Optional downstream overlay — the pipeline does not wait on it. No Epic
GitHub-org access or `ghcr.io/epicgames` pull is required.

Launch flags & container requirements that make this work (see also
`docs/engineering-log.md`): `RENDER_MODE=editor` (default) → `run_editor.sh`;
windowed `UnrealEditor` (not `-Cmd`) on Xvfb; `-unattended` + `-ExecCmds="py …"`
(NOT `-ExecutePythonScript`, which exits); engine mounted **rw**; container as
**uid 1000** (UE refuses root); `Config/DefaultEngine.ini` →
`[HTTPServer.Listeners] DefaultBindAddress=0.0.0.0`; bring up with a **single
`-f`** (relative-path base — see the compose header).

---

## Overview

`unreal/runtime/mcp_bridge.py` is a small, dependency-light HTTP service that
bridges the Vitrine agent and pipeline to the Unreal Engine 5.8 export
container.  It unifies two distinct UE control surfaces behind a single JSON
API so the pipeline never needs to distinguish transports.

Pipeline data flow:

```
pipeline writes USD          bridge imports into UE         UE renders
scene.usda + textures  →  POST /import_usd / /assemble  →  POST /render
+ v2g:* lineage                   (live UsdStageActor)        (.png / EXR)
```

---

## UE 5.8 control surfaces

### Web Remote Control — :30010 (PRIMARY)

Unicast HTTP REST on port **30010**.  This is the **preferred and primary**
control path for container-networked deployments.  Standard Docker bridge and
overlay networks forward unicast TCP without any special configuration.

Relevant REST shapes:

| Method | Route | Purpose |
|--------|-------|---------|
| `GET`  | `/remote/info` | Liveness probe; returns editor state |
| `PUT`  | `/remote/object/call` | Invoke a UFUNCTION on any UE actor/object |
| `PUT`  | `/remote/object/property` | Read or write an actor property |
| `PUT`  | `/remote/preset` | Apply a named Remote Control preset |

The bridge uses `PUT /remote/object/call` for all high-level operations
(`import_usd`, `assemble`, `render`).

### First-party MCP plugin — :8000 (SECONDARY)

UE 5.8 ships an **experimental** first-party
[Model Context Protocol](https://modelcontextprotocol.io/) plugin that exposes
an HTTP + SSE endpoint on **port 8000** at path `/mcp`.  It provides JSON-RPC
2.0 access to actor/lighting/material/automation tools and a tool-catalogue
introspection endpoint (`tools/list`).

The bridge optionally connects to this surface for tool discovery
(`scene_info`) and can route arbitrary `tools/call` requests through it, but
all pipeline-critical operations fall back to Web Remote Control when the MCP
plugin is unavailable or returns errors.

Endpoint (inside the container network):

```
http://unreal:8000/mcp
```

### Why NOT :6766 (multicast Python remote-exec)

UE embeds a Python remote-exec socket on UDP port **6766** that uses
**multicast**, which is not forwarded over standard Docker bridge networks.
ADR-016 explicitly rejects this path for container-networked use.  Use Web
Remote Control (:30010) instead.

---

## Bridge API

The bridge listens on `$BRIDGE_PORT` (default **9100**) and exposes:

### `GET /health`

Probe Web Remote Control with exponential backoff (up to 5 attempts).
Returns RC `/remote/info` payload and whether the first-party MCP is also up.

```json
{
  "ok": true,
  "data": {
    "rc_info": { ... },
    "mcp_alive": false
  },
  "duration_s": 0.12
}
```

Returns HTTP 503 when UE is not reachable.

### `POST /import_usd`

Load a `scene.usda` as a **live USD Stage Actor** (highest-fidelity path,
preserves `v2g:*` lineage — see ADR-016 D-3).  Baked Interchange import is
explicitly avoided here because it silently drops `customData`.

Request body (all fields optional):

```json
{ "usd_path": "/usd_input/scene.usda" }
```

`usd_path` defaults to the `VITRINE_USD` environment variable.

### `POST /assemble`

Run the `unreal/runtime/import_usd_stage.py` commandlet inside the running UE
instance via Web Remote Control's `ExecutePythonScript` call.  This combines
Stage Actor creation with `v2g:*` metadata mirroring onto Actor tags.  No GPU
required — the commandlet can run against a `-nullrhi` UE process.

```json
{ "usd_path": "/usd_input/scene.usda" }
```

### `POST /render`

Trigger an offscreen MovieRenderQueue render.  The UE container must be
started with `-RenderOffscreen` and a Lumen/Vulkan GPU path.  **Path Tracer is
not available on Linux** (DirectX 12 only); see ADR-016.

Request body:

```json
{
  "output_path": "/renders/vitrine_frame.png",
  "width": 1920,
  "height": 1080,
  "preset": null
}
```

All fields are optional.  `preset` names an RC preset to apply before
rendering (e.g. a lighting/camera preset saved in the UE project).

### `GET /scene_info`

Combined snapshot: RC `/remote/info` + first-party MCP tool catalogue
(empty list when MCP is not up).

### `PUT /remote/object/call`

Generic passthrough for any Web Remote Control `/remote/object/call` call.
The request body is forwarded verbatim to the UE container.

```json
{
  "ObjectPath": "/Game/Maps/Vitrine.Vitrine:PersistentLevel.MyActor_0",
  "FunctionName": "SetSomeProp",
  "Parameters": { "Value": 42 }
}
```

---

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `UE_REMOTE_CONTROL_URL` | `http://unreal:30010` | Web Remote Control base URL |
| `UE_MCP_URL` | `http://unreal:8000/mcp` | First-party MCP endpoint |
| `BRIDGE_PORT` | `9100` | Port the bridge listens on |
| `VITRINE_USD` | `/usd_input/scene.usda` | Default USD path inside the UE container |
| `UE_REQUEST_TIMEOUT` | `30` | Per-request HTTP timeout in seconds |

---

## How the agent / pipeline calls the bridge

The pipeline produces `scene.usda` (with `v2g:*` customData) and then drives
the bridge:

```python
import requests

BRIDGE = "http://unreal-mcp-bridge:9100"

# 1. Wait for UE to be ready
resp = requests.get(f"{BRIDGE}/health")
assert resp.json()["ok"], "UE not ready"

# 2. Run the import commandlet (Stage Actor + v2g:* mirror)
resp = requests.post(f"{BRIDGE}/assemble", json={"usd_path": "/usd_input/scene.usda"})
assert resp.json()["ok"], resp.json().get("error")

# 3. Offscreen render
resp = requests.post(f"{BRIDGE}/render", json={
    "output_path": "/renders/vitrine_frame.png",
    "width": 1920,
    "height": 1080,
})
assert resp.json()["ok"], resp.json().get("error")
```

From within `v2g-net` or `visionclaw_network` the bridge is reachable as
`http://unreal-mcp-bridge:9100` (the service/container name assigned by the
compose overlay).

---

## v2g:* lineage preservation

USD `customData` with the `v2g:` namespace carries per-object lineage
(source video, frame range, reconstruction job ID, etc.) generated by the
Vitrine pipeline (ADR-011).  Baked Interchange import drops this data.

The bridge avoids data loss by:

1. Using `import_usd` / `assemble` to spawn a **live `UsdStageActor`** that
   references the `.usda` file directly — the prim hierarchy and `customData`
   remain live.
2. Running `import_usd_stage.py` (via `assemble`) which additionally reads
   `v2g:*` via the `pxr.Usd` Python API (available inside UE's USD plugin)
   and mirrors the values onto Actor tags so Blueprint logic and MCP tool
   queries can access lineage without going back to the USD file.

The **baked Interchange import** path (`import_asset_tasks()`) is available as
a fallback (e.g. for `.uasset` workflows) but requires a separate
post-import Python pass to re-apply `v2g:*` via
`unreal.EditorAssetLibrary.set_metadata_tag()`.

---

## Captured color into UE

Getting the **captured color** of a reconstruction to actually render in UE is a
separate concern from lineage, and both UE import paths drop it by default:

- **Interchange GLB import IGNORES vertex colors** (`COLOR_0`) — the mesh comes in
  as *"Mesh has primitives with no materials assigned"* and renders untextured.
- **USD import DROPS the `displayColor` primvar** — the Stage Actor renders flat
  white.

To show captured color in UE you need one of:

1. A **baked-texture material** — a `UsdUVTexture` shader (or a textured GLB) that
   references a baked color atlas. The proven baker is
   `src/pipeline/blender_assembler.py` `bake_vertex_colors_to_texture()` (Blender
   Smart UV Project + Cycles **DIFFUSE GPU** bake), not a custom per-face PIL loop.
2. An **explicit VertexColor material** that samples the mesh's vertex-color
   stream directly.

> **Caveat (room/scene scale).** Smart UV Project **collapses on room-scale MILo
> meshes**: their many thin / disconnected components (e.g. 876 removed on
> scene02) produce degenerate near-zero-area UV islands, so the bake yields a
> near-black atlas. The Blender bake is reliable on clean, watertight **hulls**,
> not the messy room mesh. For **room/scene-scale captured color** the
> highest-fidelity visual is a **direct Gaussian-splat (gsplat) render**, not a
> baked mesh texture — feed UE a textured hull GLB/USD per object and keep the
> environment as the splat render.

---

## Container networking context

The Unreal service is defined in `unreal/docker-compose.unreal.yml` (a separate
overlay layered on top of the consolidated compose — the pipeline runs without
it).  It mounts `unreal/engine`→`/opt/ue:ro` (UE_ROOT=`/opt/ue`) and
`unreal/runtime`→`/vitrine/unreal:ro`, runs on GPU1, and joins both `v2g-net`
(internal pipeline bus) and `visionclaw_network` (shared external network) so the
agent and VisionFlow app can reach it by name:

| Address | Surface |
|---------|---------|
| `unreal:30010` | Web Remote Control (primary) |
| `unreal:8000`  | First-party MCP plugin |
| `unreal-mcp-bridge:9100` | This bridge (if run as a sidecar) |

The bridge itself can run in the `gaussian-toolkit` container or as a separate
lightweight sidecar on either network; it needs only Python 3.10+ and
(optionally) the `requests` library.

---

## Community alternatives

Two community bridges exist and are noted here for reference:

- **[remiphilippe/mcp-unreal](https://github.com/remiphilippe/mcp-unreal)** — a
  Go binary MCP server that wraps the UE Remote Control REST API.  Production
  alternative if a standalone MCP-protocol bridge (rather than an HTTP JSON
  API) is needed for the agent.
- **[runreal/unreal-mcp](https://github.com/runreal/unreal-mcp)** — a Python
  MCP server targeting UE 5.x, wrapping Web Remote Control.  Closer to the
  approach used here; the bridge in this repo is a slimmer, inline variant
  with no extra dependencies beyond `requests`.

These are alternatives to consider if the first-party MCP plugin proves
unstable or the bridge needs to speak MCP protocol natively to the agent rather
than HTTP JSON.

---

## Provisioning checklist (from ADR-016)

No Epic GitHub-org access or `ghcr.io/epicgames` registry pull is needed — the
image builds from an NVIDIA CUDA base plus the UE 5.8 Linux installed build kept
in-repo.

1. Stage the engine: extract the UE 5.8 Linux installed build to `unreal/engine/`
   (~73 GB, gitignored — it holds `Engine/`).  It is bind-mounted read-only at
   `UE_ROOT=/opt/ue`.
2. Build the image (already done — `vitrine-unreal:5.8`, ~6.15 GB): builds
   `unreal/Dockerfile.unreal` `FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04` plus
   the UE Linux runtime prereqs, adding RC/MCP startup + `import_usd_stage.py`.
3. Bring up the overlay (consolidated compose + the Unreal overlay, two `-f`
   files):

   ```bash
   docker compose -f docker-compose.consolidated.yml -f unreal/docker-compose.unreal.yml up -d unreal unreal-mcp-bridge
   ```

   Then health-check `:30010/remote/info`.
4. Smoke test: call `POST /assemble` on the bridge with the test `scene.usda`;
   verify `v2g:*` tags appear on the Stage Actor; call `POST /render`; check
   `/renders/` volume.
