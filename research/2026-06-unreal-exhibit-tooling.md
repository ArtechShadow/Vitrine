# UE5.8 Agent Scene-Building Tooling — Research Reference (2026-06-20)

Grounding for ADR-018 (agent-shepherded exhibit builder). UE5.8 released 2026-06-17. Key facts an exhibit-builder agent must work within; full source list at the end.

## First-party MCP plugin (experimental)
- Endpoint `http://127.0.0.1:8000/mcp` (Streamable HTTP+SSE only; no stdio/WebSocket), loopback-only, DNS-rebind defended, **no auth**. Port via `-ModelContextProtocolPort=N`.
- Setup: enable "Unreal MCP" plugin + Auto Start Server; `ModelContextProtocol.GenerateClientConfig ClaudeCode`; `ModelContextProtocol.RefreshTools` after authoring toolsets.
- **Discovery-first meta-tools**: `list_toolsets`, `describe_toolset`, `call_tool` (avoids dumping 100+ schemas).
- **Shipped toolsets**: ActorTools (transforms, labels, hierarchy, components), SceneTools, MaterialInstanceTools, ObjectTools, + GASToolsets (AttributeSet, C++ `AICallable` example, disabled by default).
- **Gaps**: no Blueprint-graph edit, no USD-import tool, no collision/physics, no UMG creation, no level-save (call explicitly), no PIE control, no transactional batch. Tool calls are **serial on the game thread** (no parallel).
- **Extensible**: Python `ToolsetDefinition` in any `Content/Python/` + `@toolset_registry.tool_call` (type hints + docstrings → JSON schema); or C++ `UToolsetDefinition` + `UFUNCTION(meta=(AICallable))`; or runtime `IModelContextProtocolModule::AddTool()`.
- **Cooked/headless builds do NOT auto-discover tools** → full authoring needs a **running editor**.

## Python (editor-only, 3.11.8)
- `spawn_actor_from_class`, `set_actor_location/rotation/scale3d`, `static_mesh_component.set_static_mesh/set_material`, `EditorAssetLibrary.set_metadata_tag/get_metadata_tag_values` (for `v2g:*`), `BlueprintFactory`/`WidgetBlueprintFactory` create, `add_component(WidgetComponent)`, `save_current_level`.
- BP **graph** editing from Python is fragile/underdocumented → use templates or third-party `blueprint_modify`.
- Headless: `UnrealEditor-Cmd <proj> -ExecutePythonScript=x.py [-nullrhi]` (full editor, no display) or `-run=pythonscript -script=x.py -nullrhi` (lighter, no asset/level load). Physics/render ops need a display/GPU.
- **Python is editor-only — NOT runtime gameplay scripting.** **Verse is UEFN-only in 5.8** (standalone Verse → UE6, late 2027).

## USD import
- **Stage Actor** (live, transforms preserved, transient components — awkward for gameplay) vs **baked import** (Interchange; recommended for runtime). `UsdStageImportOptions.metadata_options` harvests custom `v2g:*` attributes → asset metadata tags. Units: USD meters → UE cm (**100× scale**) — assert bounds post-import. Collision set post-import on the `UStaticMesh`. Physics-settle via downward `line_trace_single` sweep, or trust the USD transform.

## Interaction / UMG
- Stack: `BPI_ExhibitInteract` (OnHoverBegin/End, Interact) + Enhanced Input (production-ready) + line trace + **custom-depth outline** (`set_render_custom_depth(True)` + stencil value, post-process material) + overlap TriggerVolumes. GAS optional/overkill.
- Explanatory UI: `WidgetComponent` (`WidgetSpace.WORLD` billboard) + a runtime `ExhibitDataComponent` populated from asset metadata at BeginPlay, data-bound to `WBP_ObjectInfo`. Cesium "metadata → dynamic UI" is the reference pattern.
- Agent can set custom-depth + attach widgets + populate data via Python loop; the interaction **event graph** is best a pre-authored template (or third-party `bp_nodes`/`bp_wire`).

## Realistic architecture (→ ADR-018)
- **Phase A (headless commandlet, no GPU)**: bake USD → UE assets + harvest `v2g:*` → JSON build manifest `{object_id, asset_path, world_transform, v2g_metadata}`.
- **Phase B (running editor + GPU)**: MCP agent reads manifest → spawn at transforms, materials, custom-depth, attach widgets, populate ExhibitData, wire BPI (template/`blueprint_modify`), save level, PIE-verify, iterate.
- **Packaged runtime**: no Python/MCP — interaction is Blueprint (Enhanced Input + BPI + trace), highlight is custom-depth+PP material, info is data-bound UMG WidgetComponent.

## Third-party MCP servers (fill first-party gaps)
- `remiphilippe/mcp-unreal` (49 tools; headless build/test; `blueprint_modify`; RC :30010 + plugin :8090), `flopperam/unreal-engine-mcp` (`bp_create/bp_nodes/bp_wire`, `scene_compose`, `pie_test_bp`), `ue-mcp.com` (WS :9877, widget tools), StraySpark (207 tools + bearer auth, transactional). Recommendation: Epic first-party + mcp-unreal/flopperam for Blueprints + RC :30010, fronted by our `mcp_bridge.py`.

## Caveats
No auth on the MCP server (keep loopback, bridge-front); USD level-import + Pregen are experimental (baked is production); serial tool calls; UE5.8 is the last UE5 — MCP is a UE6 foundation, expect churn.

## Sources
Epic UE5.8 release notes + Unreal MCP docs + USD/Python/Enhanced-Input/UMG/GAS docs; byteiota, StraySpark, explainx, cryptobriefing, gamefromscratch writeups; mcp-unreal / flopperam / ue-mcp / UMG-MCP repos; Cesium metadata-UI; Tom Looman custom-depth; UE6 announcement. (Full URL list in the ADR-018 research thread.)
