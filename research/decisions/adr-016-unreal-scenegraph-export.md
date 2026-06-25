# ADR-016 — Unreal Engine 5.8 USD Scenegraph Export (MCP-driven GPU container)

**Status:** Proposed (2026-06-19) — provisioning gated on Epic Games account/registry access
**Drives:** `unreal/Dockerfile.unreal`, `unreal/docker-compose.unreal.yml`
**Evidence:** 2026-06-19 research sweep (Unreal 5.8 / MCP / dockerized-GPU / USD import)
**Relates to:** ADR-011 (`v2g:*` USD customData), the USD assembly stage (`scripts/assemble_usd_scene.py`, native `scene.export_usd`)

---

## Context

Vitrine produces a USD scene graph (textured environment mesh + per-object hulls, with `v2g:*` lineage customData) plus a `.ksplat`. We want to export that scene into **Unreal Engine 5.8** as a new stage of the multi-container pipeline, driven by MCP so the agent/VisionFlow stack can assemble and render it.

Key facts established by the sweep (all dated June 2026):
- **UE 5.8 released 2026-06-17** and ships an **experimental first-party MCP plugin** (HTTP+SSE on **:8000**, `http://host:8000/mcp`) — actor/lighting/material/automation tools, extensible toolset registry. Editor must be running; cooked builds can host it via `IModelContextProtocolModule::StartServer()`.
- Epic ships official GPU container images at **`ghcr.io/epicgames/unreal-engine`** (`dev-5.8`, `dev-slim-5.8`, `runtime-5.8`). Access requires **linking a GitHub account to Epic + accepting the UE EULA + `read:packages` PAT**; images publish days–weeks after a release (so `dev-5.8` may lag). Images are 30–80 GB compressed.
- Linux GPU containers support **Vulkan/OpenGL/CUDA/NVENC via the NVIDIA Container Toolkit** but **NOT DirectX → no Path Tracer / DXR**. Offscreen GPU rendering uses **`-RenderOffscreen`** + Lumen. `-nullrhi` covers non-render automation (import/assemble/save) with no GPU.
- **USD import is production-ready for asset import** (Interchange). **Critical gap: `customData` / namespaced `v2g:*` attributes are silently dropped on baked import.**
- UE embeds **Python 3.11.8**; headless commandlet `-run=pythonscript -script=...`. Web Remote Control on **:30010** (unicast, container-friendly); the built-in Python remote-exec uses multicast UDP **:6766** which standard bridge networking does not forward.

## Decision

1. **Add an `unreal` GPU service** built from `ghcr.io/epicgames/unreal-engine:dev-5.8` (fallback `dev-5.6`/`dev-5.7` until 5.8 publishes), joined to `v2g-net` + `visionclaw_network`, GPU via the NVIDIA Container Toolkit, mounting the pipeline's USD/ksplat output read-only and a renders volume read-write. Defined in `unreal/Dockerfile.unreal` + `unreal/docker-compose.unreal.yml` (separate overlay; not folded into the consolidated compose until access + image are validated).

2. **MCP surface:** enable Epic's first-party Unreal MCP plugin (:8000) as primary; run a community **Web Remote Control bridge** (:30010, unicast) as the robust, container-network-friendly control path. Avoid the multicast Python-remote-exec (:6766). Expose the bridge on `visionclaw_network` so the agent/VisionFlow reach it by name (`unreal:8000`, `unreal:30010`).

3. **USD ingestion = USD Stage Actor (live reference), NOT baked import — to preserve `v2g:*`.** A `UsdStageActor` points at our `scene.usda`; the full prim hierarchy + materials load live, and `v2g:*` customData is read via the `pxr.Usd` Python API (available in UE's USD plugin) — `prim.GetCustomData()`. This is the **highest-fidelity** path (no metadata loss, preserves hierarchy).
   - **Fallback for persisted `.uasset` workflows:** baked Interchange import via `import_asset_tasks()` (NOT `import_asset()` — it crashes in commandlets), followed by a **post-import Python pass** that re-reads the source USD with `pxr` and writes `v2g:*` onto imported assets via `unreal.EditorAssetLibrary.set_metadata_tag()`.

4. **Rendering posture:** Lumen via `-RenderOffscreen` (Linux/Vulkan). **Path Tracer is out of scope on Linux** (DX12-only) — if/when path-traced stills are required, that runs on a Windows host, tracked separately. Non-render scene assembly (import USD, set metadata, save) uses `-nullrhi` (no GPU), so the assembly step can run even without a GPU slot.

5. **Provisioning is gated, not blocking the rest of the pipeline.** The Epic GitHub-org link + EULA + `read:packages` PAT is a one-time credential step (automatic, no manual Epic review; invite email within minutes). Until that token exists, the service is defined but not pulled; the pipeline's USD output is already the contract, so nothing else waits on Unreal.

## Alternatives considered

- **Baked USD import as primary.** Rejected: silently drops `v2g:*` lineage — the whole point of our scene graph. Demoted to fallback with explicit metadata re-application.
- **Python remote-exec (:6766) for MCP control.** Rejected: multicast UDP isn't forwarded over Docker bridge; Web Remote Control (:30010) + the first-party MCP (:8000) are unicast/HTTP and container-native.
- **Windows UE container (for Path Tracer).** Deferred: heavier ops; Lumen offscreen is sufficient for the exhibit/preview use case. Revisit if path-traced fidelity is required.
- **Bespoke UE build from source in-container.** Rejected vs Epic's prebuilt `dev` image — far faster to provision once registry access exists.

## Consequences

**Positive:** highest-fidelity scenegraph round-trip (hierarchy + `v2g:*` preserved via Stage Actor + pxr); agent-drivable via first-party MCP; GPU offscreen renders; cleanly isolated as an overlay service.

**Negative / cost:** large image (30–80 GB) + Epic access gating; Path Tracer unavailable on Linux; the `v2g:*` preservation requires the Stage-Actor/pxr path (more bespoke than a plain import); two control ports to manage.

**Risks:** `dev-5.8` image may not be published yet (use an earlier `dev-5.x` until then); first-party MCP is experimental (API may shift) — the :30010 bridge is the stable fallback.

## Rollout (provisioning checklist)

1. Link a GitHub account to Epic (Apps & Accounts → Connect GitHub), accept UE EULA, join the EpicGames org invite, create a `read:packages` PAT.
2. `docker login ghcr.io`; `docker pull ghcr.io/epicgames/unreal-engine:dev-5.8` (or latest available `dev-5.x`).
3. Build `unreal/Dockerfile.unreal` (adds remote-control/MCP startup + our `import_usd_stage.py`).
4. Bring up `unreal/docker-compose.unreal.yml`; health-check `:30010/remote/info`.
5. Smoke: drive `import_usd_stage.py` over MCP to load `scene.usda` as a Stage Actor; verify `v2g:*` readable via pxr; offscreen-render one frame.

## Amendment 2026-06-20 — Linux installed build (no Epic ghcr needed)

The Epic ghcr image (`ghcr.io/epicgames/unreal-engine`) is gated behind Epic↔GitHub
org membership, which we could not self-serve. Instead we now build from the **UE 5.8
Linux installed build** supplied directly in-repo: `unreal/Dockerfile.unreal` is
`FROM nvidia/cuda:…-ubuntu22.04` + UE's Linux runtime prerequisites (Vulkan/GL/X libs),
and the extracted engine tree at `unreal/engine` is **bind-mounted read-only at
`$UE_ROOT` (`/opt/ue`)**. `entrypoint.sh` resolves `UnrealEditor-Cmd` from
`$UE_ROOT/Engine/Binaries/Linux/` first. This sidesteps the ghcr credential gate
entirely while keeping the same control surface (MCP :8000 / RC :30010), the same
USD Stage Actor + pxr `v2g:*` path, and Lumen offscreen rendering. The ghcr-image
route remains a valid alternative for anyone with Epic access (drop the apt prereq
layer and set `FROM ghcr.io/epicgames/unreal-engine:dev-5.8`).

## Amendment 2026-06-21 — proven launch recipe (L7) + captured-color caveat (L2)

First real multi-capture e2e run nailed down the launch decision. **Canonical recipe
(supersedes the provisional `-run=pythonscript` / `-RenderOffscreen` notes above for
the GPU-render case):**

- **Run a persistent *windowed* `UnrealEditor` on an Xvfb display** to get the **real
  Vulkan RHI**. The `-run=pythonscript` commandlet loads **NullDrv** (no GPU render),
  so it is fine for headless import/assemble/save but cannot render — use the
  persistent windowed editor when a GPU frame is needed.
- **`-unattended`** clears the **Zen DDC hang** seen on first boot.
- Drive Python with **`-ExecCmds="py <script>"`**, **NOT `-ExecutePythonScript`** —
  the latter makes `-unattended` *exit* before the control server is up.
- Run as **uid 1000**, with the **engine mount read-write** (not read-only as the
  2026-06-20 amendment assumed — the editor writes DDC/Saved under the engine tree).
- `Config/DefaultEngine.ini` **`[HTTPServer.Listeners] DefaultBindAddress=0.0.0.0`**
  so the control surface is reachable across the docker network (not just localhost).
- Start the **native MCP** with **`-ModelContextProtocolStartServer`** +
  **`-ModelContextProtocolPort`** (these are the real flags for the first-party plugin
  named loosely as ":8000 MCP" above).

**Captured-color caveat (L2) — affects the Decision-3 Stage Actor path.** The live
`UsdStageActor` import **drops the `displayColor` primvar** (the scene renders flat
white), and Interchange **GLB import ignores vertex colors (`COLOR_0`)**. To get
captured color into UE you need either (a) a **baked-texture material**
(`UsdUVTexture` / textured GLB) or (b) an explicit **VertexColor material** — vertex
color and `displayColor` do not survive on their own. The proven bake is Blender Smart
UV Project + Cycles diffuse GPU bake (`src/pipeline/blender_assembler.py`), but Smart
UV Project **collapses on room-scale MILo meshes** (many thin/disconnected components
yield degenerate UV islands → a near-black atlas); it works on clean watertight
**hulls**, not the messy room mesh. **For room/scene-scale captured color the
highest-fidelity visual is a direct Gaussian-splat (gsplat) render, not a baked-mesh
texture in UE.** This narrows the Stage Actor's promised "highest-fidelity round-trip":
hierarchy + `v2g:*` still round-trip losslessly, but scene *color* does not — route
scene color through gsplat and reserve UE textured-USD ingest for baked hulls.

## Amendment 2026-06-22 — USD demoted: the UE deliverable is textured-mesh game assets, not USD (ADR-019)

This ADR's central premise — **USD is the delivery contract into UE** (Decision 1–3:
add a USD-export stage, ingest it as a live `UsdStageActor`, preserve `v2g:*` via
pxr) — is **demoted by ADR-019**. Three facts from the multi-capture e2e runs force
it:

1. **LichtFeld's native `scene.export_usd` emits a custom `ParticleField` /
   gaussian prim that UE's USD importer CANNOT import as a mesh.** The "highest-
   fidelity USD round-trip" promised by Decision 3 does not yield a polygonal scene
   in UE for the gaussian representation at all.
2. **The captured-color caveat (Amendment 2026-06-21, L2) is terminal for USD as the
   contract:** UE drops `displayColor`/`customData` on USD import and `COLOR_0` on
   GLB — a **baked UV texture is the only channel that survives**, so color cannot
   ride in the delivered USD.
3. **UE `import_file` accepts fbx/obj only** — the web GLB is rejected.

**Therefore (ADR-019):** the UE deliverable is **textured-mesh game assets (FBX with
embedded baked-texture material)** — env mesh + per-object hulls baked via
`texture_baker.bake_from_vertex_colors` (with `mesh_cleaner` `smooth_iterations=0` to
avoid xatlas-crashing degenerate tris), imported with a baked-texture material, with
**Nanite** carrying the polygon budget (no gaussian pruning). **USD is now an
OPTIONAL / archival side-artifact, not the delivered contract.** `v2g:*` lineage, if
needed in UE, rides on **UE asset metadata tags** (`set_metadata_tag`), not delivered
USD. The Stage-Actor + pxr path documented above remains valid only for inspection /
archival; it is no longer the UE delivery mechanism. See
`adr-019-mesh-game-assets-not-usd-into-ue.md`.
