# DDD — Unreal Exhibit Builder Bounded Context

**Status:** Active (2026-06-20)
**Drives implementation of:** PRD `prd-unreal-exhibit-builder`, ADR-018 (pending)
**Builds on:** ADR-016 (USD export/import), `research/ddd/object-reconstruction-context.md`, the `v2g:*` lineage, the `exhibit.toml` manifest
**Maps to:** `unreal/runtime/` (import_usd_stage / import_and_render / mcp_bridge), the UE-side Python build scripts, the agent shepherd

This models the agent-shepherded construction of an interactive exhibit inside the Unreal container so the build lands as coherent domain logic rather than ad-hoc Python.

---

## 1. Bounded contexts

| Context | Responsibility | Owns | Upstream/ACL |
|---|---|---|---|
| **Exhibit Assembly** (core) | Turn an imported USD scene + manifest into a navigable, interactive, annotated exhibit | the Exhibit aggregate + the build plan/loop | calls UE via the Control ACL; reads USD Ingest + Annotation |
| **USD Ingest** (ACL) | Load `scene.usda` as a live Stage Actor; expose prims + `v2g:*` customData to the domain (do not lose lineage) | the imported scene model | wraps UE USD plugin + `pxr` |
| **UE Control** (ACL) | Translate domain build intents → UE MCP (:8000) / Remote Control (:30010) / Python; return scene state | tool calls, scene queries | wraps `mcp_bridge.py` + the UE Python API |
| **Annotation** | Compose user-facing explanatory data from `v2g:*` lineage + manifest curation | Annotation value objects | reads lineage + manifest |

## 2. Ubiquitous language

- **Exhibit** — the assembled interactive scene: a reconstructed Environment + placed ExhibitObjects + a NavRig + Annotations.
- **Environment** — the reconstructed scene mesh (the space the visitor walks).
- **ExhibitObject** — one reconstructed object hull placed in the Environment, with identity, lineage, an Interaction and an Annotation.
- **Placement** — an object's world transform + collision + surface-settle result.
- **Interaction** — the visitor-facing behaviour bound to an object (select → highlight → reveal → optional inspect/orbit).
- **Annotation** — the explanatory data shown to the visitor (object identity + `v2g:*` lineage + curated manifest copy) bound to in-world UI.
- **NavRig** — the pawn/camera + lighting that make the Exhibit explorable.
- **BuilderAgent** — the embedded Claude that *shepherds* the build (query → act → verify → recover) via the Control ACL.
- **BuildPlan / BuildStep** — the ordered intents the agent executes; each step is verified.
- **Provenance flags** — `v2g:view_synth=true` etc. — measured-vs-inferred markers the exhibit stays honest about.

## 3. Aggregates, entities, value objects

- `Exhibit` (aggregate root): `{environment, objects[], nav_rig, manifest_ref, build_report}`. Invariant: every placed object resolves to the Environment's space; lineage is preserved.
- `ExhibitObject` (entity): `{object_id, mesh_ref, placement, interaction, annotation, lineage(v2g:*), confidence}`.
- `Placement` (value object): `{transform(from USD), scale_ok, collision, settled, flags[]}`.
- `Interaction` (value object): `{selectable, highlight, reveal_target(annotation), inspect_mode?}`.
- `Annotation` (value object): `{title, lineage_summary, curated_body, source: measured|inferred, ui_binding}`.
- `NavRig` (value object): `{pawn, cameras[], lighting, exposure}`.
- `BuildStep` (entity): `{kind: import|place|interact|annotate|navrig|verify, target, intent, verdict}`.

## 4. Domain services

- **ExhibitBuilder** (the agent shepherd loop): drives `import → place-all → wire-interactions → attach-annotations → navrig → verify`, each step via the Control ACL, each verified; on a failed verdict it **recovers** (retry, alternative placement, flag-and-continue) — this is the `claude_code` oversight intelligence applied in-container, NOT a blind script.
- **PlacementResolver**: USD prim transform → UE world `Placement` (units/scale check, collision, optional physics-settle onto the Environment); flags missing/low-confidence transforms.
- **InteractionWirer**: attaches the `Interaction` (selectable + custom-depth highlight + reveal trigger + inspect) to each ExhibitObject.
- **AnnotationComposer**: `v2g:*` lineage + manifest curation → `Annotation`; marks `source` measured vs inferred (honours provenance flags).
- **UE Control ACL** (`mcp_bridge.py` + UE Python): the only place domain code touches UE tool/class names.

## 5. Domain events (for the build report + recovery)

- `ExhibitImported{prim_count, v2g_objects}`
- `ObjectPlaced{object_id, transform, settled}` | `ObjectPlacementFlagged{object_id, reason}`
- `InteractionWired{object_id}` · `AnnotationAttached{object_id, source}`
- `NavRigAdded` · `BuildStepFailed{step, reason}` → `BuildStepRecovered{step, strategy}`
- `ExhibitVerified{objects_ok, flagged[]}` · `ExhibitSaved{level_ref}`

Every event feeds the **build report** (FR-7) so the exhibit's construction is auditable: what was placed, wired, annotated, flagged, and recovered.

## 6. Invariants

- **I1** Lineage preservation: every ExhibitObject retains its `v2g:*`; the Exhibit can always state measured-vs-inferred per object (provenance flags never silently dropped — ADR-016 Stage-Actor path).
- **I2** No silent breakage: a per-object failure flags the object and continues; the build never emits a half-broken Exhibit without a report.
- **I3** Spatial fidelity: objects are placed at their reconstructed USD transforms (the exhibit reflects reality), not arbitrary layout.
- **I4** ACL isolation: UE tool/class coupling lives only in the Control ACL; the build logic is engine-API-agnostic.
- **I5** Agent-shepherded: the build is driven through the verify/recover loop (oversight), so edge cases are handled, not crashed on.

## 7. Context map (flow)

```
scene.usda (+ v2g:*) ─┐                         manifest (exhibit.toml)
                      ▼                                 │
            [USD Ingest ACL] ── live Stage Actor + pxr  │
                      │  imported scene + lineage        │
                      ▼                                  ▼
            [Exhibit Assembly] ◀── BuilderAgent shepherd (query→act→verify→recover)
               PlacementResolver · InteractionWirer · AnnotationComposer
                      │  build steps (each verified)
                      ▼
            [UE Control ACL] ── MCP :8000 / Remote Control :30010 / UE Python
                      │
                      ▼
            Exhibit (saved level + build report) ──▶ preview / package / pixel-stream
```

The ADR-018 implementation must satisfy this contract: agent-shepherded, lineage-faithful, spatially-correct, ACL-isolated, recoverable. The specific UE5.8 APIs (MCP tool surface, Python authoring, interaction/UMG primitives) are decided in ADR-018 from the 5.8 tooling research.
