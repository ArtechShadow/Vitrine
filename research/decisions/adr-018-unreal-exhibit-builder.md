# ADR-018 — Agent-Shepherded Unreal Exhibit Builder (UE5.8 tooling decisions)

**Status:** Accepted (2026-06-20)
**Drives:** `research/prd/prd-unreal-exhibit-builder.md`, `research/ddd/unreal-exhibit-builder-context.md`, the UE-side build scripts + `mcp_bridge.py`
**Extends/refines:** ADR-016 (USD export/import), ADR-014 (oversight/recovery)
**Evidence:** 2026-06-20 UE5.8 agent-scene-building research (first-party MCP, Python automation, USD import, interaction/UMG, third-party servers)

---

## Context

The PRD wants an embedded agent to assemble a navigable, interactive exhibit from the USD scene + `v2g:*` lineage + the exhibit manifest. The UE5.8 research establishes hard constraints that shape *how*:

- **Scene construction via MCP requires a running editor.** UE5.8 ships a first-party MCP plugin (`:8000`, HTTP+SSE, loopback, no auth) with meta-tools (`list_toolsets`/`describe_toolset`/`call_tool`) + 4 shipped toolsets (Actor/Scene/MaterialInstance/Object), extensible via the **Toolset Registry** (Python `ToolsetDefinition` in `Content/Python/`). But cooked/headless builds do **not** auto-discover tools, so the full authoring toolset needs a live editor. Tool calls are **serial on the game thread** (no parallelism).
- **Python is editor-only** (3.11.8) — great for asset/scene setup (`spawn_actor_from_class`, transforms, materials, `set_metadata_tag`, WidgetComponent attach), but **cannot be runtime gameplay scripting**. **Verse is UEFN-only in 5.8** — not available for a standalone exhibit.
- **Baked USD import preserves `v2g:*`** via `UsdStageImportOptions.metadata_options` (custom attributes → asset metadata tags) and is the runtime-friendly path; the live Stage Actor is better for inspection but its transient components are awkward for gameplay.
- **Blueprint graph editing from the agent is fragile** in the first-party plugin (no BP-graph tools); robust authoring uses **pre-authored Blueprint templates** + third-party servers (`remiphilippe/mcp-unreal`, `flopperam/unreal-engine-mcp`) for `blueprint_modify`/`bp_wire`.

## Decision

1. **Two-phase build.**
   - **Phase A — headless pre-pass** (`UnrealEditor-Cmd -run=pythonscript -nullrhi`, no GPU): bake the USD → UE StaticMesh/Material assets via Interchange with `metadata_options` harvesting `v2g:*` → asset tags; emit a **build manifest** (`{object_id, asset_path, world_transform, v2g_metadata, confidence, view_synth}`).
   - **Phase B — running-editor MCP agent** (GPU + display/offscreen): the shepherd reads the manifest and drives the editor via MCP to spawn actors at the USD transforms, assign materials, set per-object highlight, attach annotation widgets, instantiate+configure interaction Blueprints, verify (viewport/PIE), iterate, and save the level.

2. **USD ingest: baked import for the exhibit runtime; Stage Actor for inspection.** This refines ADR-016: the live Stage Actor + pxr path is retained for *inspection / v2g read-back* (and the export smoke), but the **builder bakes** the scene (Interchange `metadata_options`) so objects are real `UStaticMeshActor`s that gameplay/interaction/collision attach to cleanly — with `v2g:*` preserved as asset tags and mirrored onto a runtime `ExhibitDataComponent`. USD is **meters → UE cm (100×)**; the pre-pass asserts real-world bounds.

3. **Captured color into UE needs a baked-texture or explicit VertexColor material — never raw vertex colors / `displayColor`.** UE5.8 Interchange **GLB import ignores vertex colors** (`COLOR_0`) — meshes arrive with "no materials assigned" and render flat. UE **USD import drops the `displayColor` primvar** (renders flat white). So the exhibit builder MUST emit, per asset, either **(a) a baked-texture material** (UsdUVTexture / textured GLB) or **(b) an explicit VertexColor material**; it cannot rely on the captured color riding along in the geometry. The proven bake is **Blender Smart UV Project + Cycles DIFFUSE GPU bake** (`src/pipeline/blender_assembler.py` `bake_vertex_colors_to_texture()`), and per CLAUDE.md §1 the builder reuses that capability rather than re-baking in custom Python. **Caveat (object hulls vs. room mesh):** Smart UV Project bakes cleanly on **clean watertight object hulls**, but **collapses on room-scale MILo meshes** — their many thin/disconnected components (e.g. **876 removed on scene02**) yield degenerate near-zero-area UV islands and a **near-black 2048² atlas**. Therefore the **highest-fidelity room/scene captured color is a direct gsplat (Gaussian-splat) render, not a baked mesh texture**; the builder falls back to the splat render for scene-scale color and reserves the texture bake for object hulls.

4. **MCP surface = Epic first-party + a custom exhibit toolset + third-party for Blueprints.** Run Epic's plugin (`:8000`) as the standard entry; add **custom `ToolsetDefinition` Python tools** (`Content/Python/`) for exhibit-specific ops (place-from-manifest, set-highlight, attach-annotation, populate-exhibit-data). Layer `mcp-unreal`/`flopperam` (Blueprint editing) + Remote Control (`:30010`) for what the first-party plugin lacks. `unreal/runtime/mcp_bridge.py` is our stable façade over all of these for the pipeline/agent.

5. **Interaction = pre-authored Blueprint templates the agent instantiates, not graphs authored from scratch.** Ship reusable templates: `BPI_ExhibitInteract` (OnHoverBegin/End, Interact), an exhibit pawn (first-person + orbit), `WBP_ObjectInfo` (data-bound UMG), a post-process outline material, and `ExhibitDataComponent`. The agent: spawns/places actors, sets `render_custom_depth`/`custom_depth_stencil_value` per object (Python), attaches `WidgetComponent` (WORLD space) + populates `ExhibitDataComponent` from `v2g:*`, and wires the interface (template-instantiate, or `blueprint_modify` via third-party). Enhanced Input drives select/interact. **All runtime logic is Blueprint** (authored in the editor phase); the packaged exhibit has no Python/MCP.

6. **The shepherd is the `claude_code` oversight agent** (ADR-014), connected through `mcp_bridge.py`, running the DDD `ExhibitBuilder` loop (query→act→verify→recover). Per-object failures **flag + continue** (DDD I2); synthesised surfaces (`v2g:view_synth=true`) are surfaced honestly in the annotation (`source: inferred`).

7. **Delivery:** editor-preview first (P0–P3); packaged binary and/or Pixel Streaming to the web (alongside the `.ksplat`) is P4. Path Tracer is out (Linux); Lumen offscreen is the render.

## Alternatives considered

- **Pure cooked/headless MCP build (no editor).** Rejected: cooked builds don't auto-discover tools; scene authoring needs a live editor. Headless is used only for the Phase-A bake pre-pass.
- **Live USD Stage Actor as the runtime scene.** Rejected for the *builder*: transient components are awkward for collision/interaction/Blueprint attach. Retained for inspection (ADR-016).
- **Agent authors Blueprint graphs from scratch.** Rejected: fragile in 5.8. Pre-authored templates + targeted `blueprint_modify` instead.
- **Verse for interaction.** Impossible in standalone UE5.8 (UEFN-only). Blueprint/C++ runtime.
- **GAS for interactions.** Overkill for an exhibit; plain BPI + Enhanced Input + line trace. (GAS available via toolset if persistent "viewed" state is later wanted.)

## Consequences

**Positive:** a realistic, buildable stack grounded in what 5.8 actually exposes; `v2g:*` survives to runtime UI; the agent does the controllable, robust parts (placement, property-set, template-instantiate, verify) and avoids the fragile parts (graph authoring); honest measured-vs-inferred surfacing; lineage-faithful and recoverable.

**Negative / risk:** requires a running GPU editor for Phase B (heavier than the export-only container — the ADR-016 container must run the editor, not just `-nullrhi`); first-party MCP is experimental (API churn toward UE6, no auth → keep loopback/bridge-fronted); third-party-server dependency for Blueprint editing; serial tool calls (no parallel authoring). **Captured color is not free:** every textured asset costs a Blender bake (object hulls only) and scene-scale color requires a *separate* gsplat render alongside the mesh — two color pipelines, not one; a naive "import the mesh and trust its colors" path renders flat white (USD) or unlit (GLB) and is a defect.

**Color-preservation contract (component filtering).** When the builder filters mesh components (e.g. dropping the 876 stray components on a room mesh), **vertex colors MUST be remapped through the kept-vertex index map** — rebuilding a `Trimesh` from filtered geometry *without* re-attaching colors yields trimesh's default gray `[102, 102, 102]` (this produced a "white/gray in UE" red herring). Use **`trimesh.graph.connected_components` + an explicit index remap**, **never `split()` + `concatenate()`** — that path **hangs at ~1.8M verts and silently drops to default gray**.

## Compliance / rollout

- Phase A pre-pass script + the build manifest schema land first (headless, testable without a GPU editor).
- The Blueprint templates + custom exhibit toolset are versioned assets in the UE project.
- `mcp_bridge.py` gains the exhibit tool surface (place/highlight/annotate/verify) over RC + first-party MCP.
- **Captured color:** the Phase-A pre-pass tags each manifest entry with its color source — **baked texture** (object hulls, via `blender_assembler.py` `bake_vertex_colors_to_texture()`) or **gsplat render** (room/scene) — and the builder assigns the matching UE material (textured/UsdUVTexture vs. VertexColor) so nothing relies on `displayColor`/`COLOR_0`. Any component-filtering step must round-trip vertex colors through the kept-vertex index map (no `split()`+`concatenate()`).
- Security: the MCP server stays loopback; the bridge (`:9100`) is the only network-exposed surface, on `v2g-net`/`visionclaw_network`.
- Supersedes nothing; refines ADR-016's "Stage Actor primary" to "baked for runtime, Stage Actor for inspection."
