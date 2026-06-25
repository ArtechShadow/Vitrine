# ADR-019 — UE delivery is textured-mesh game assets (FBX), not USD

**Status:** Accepted (2026-06-22)
**Drives:** the UE import path (`unreal/runtime/import_*.py`, `mcp_bridge.py`), `src/pipeline/texture_baker.py` (`bake_from_vertex_colors`), `src/pipeline/mesh_cleaner.py`, the exhibit-builder Phase-A bake pre-pass
**Supersedes/demotes:** ADR-016's "USD scenegraph is the UE delivery contract" (USD → optional/archival side-artifact); ADR-011's "delivered USD is the self-describing contract" (lineage now rides on UE asset metadata tags)
**Extends/refines:** ADR-018 (exhibit builder — this ADR fixes the *delivered asset format* its bake produces), ADR-003 (mesh backends), ADR-010 (hulls)
**Evidence:** 2026-06 multi-capture e2e runs driving UE 5.8; ADR-016 L2 captured-color caveat; ADR-018 §3 color-preservation contract; UE 5.8 Interchange / `import_file` behaviour

---

## Context

The Vitrine end-state is a **textured polygonal scene navigable inside Unreal
Engine 5.8** — environment mesh + per-object hulls, correctly placed, with their
captured colour intact. Earlier ADRs (016, 011, 018) assumed the delivered
contract into UE was the **USD scene graph** (`scene.usda` + `v2g:*` customData),
imported either as a live `UsdStageActor` or baked via Interchange. The
multi-capture e2e runs invalidated that assumption. Three hard technical facts —
each independently observed driving the live UE 5.8 editor — force a different
delivery format:

1. **LichtFeld's native USD export is not mesh-importable into UE.** The native
   `scene.export_usd` path emits a custom **`ParticleField` / gaussian prim** for
   the scene representation. UE's USD importer (Interchange / `UsdStageActor`)
   **cannot import that prim as a renderable mesh** — there is no UE
   counterpart to a LichtFeld gaussian particle field. The native-USD round-trip
   that ADR-016 promised as "highest-fidelity" does not yield a polygonal scene in
   UE at all for the gaussian representation.

2. **UE silently drops every "colour rides in the geometry" channel.** On import
   UE 5.8 drops **vertex colours on FBX and OBJ and GLB (`COLOR_0`)**, and drops
   USD **`displayColor` / `customData`** (the ADR-016 L2 caveat, the ADR-018 §3
   contract). A mesh whose captured colour lives in vertex colours arrives **flat
   white / unlit**. The **only** channel that reliably survives is a **baked UV
   texture** bound through a material — captured colour must be baked into a
   texture atlas before it crosses the UE boundary, regardless of mesh container.

3. **UE `import_file` accepts fbx/obj only — GLB is rejected.** The pipeline's
   web-delivery hull format (`.glb`, ADR-006) cannot be handed to UE's
   `import_file` directly; it is rejected (fbx/obj only). So even setting colour
   aside, GLB is not a valid UE ingest container.

Taken together: the "deliver the USD scene graph into UE" contract is unrealisable
(fact 1), the "let colour ride on vertex colours / `displayColor`" assumption is
false (fact 2), and the web GLB is not a UE-ingestible container (fact 3). The
delivered UE asset has to be a **baked, textured, FBX game asset**, not USD and not
vertex-coloured geometry.

## Decision

1. **The UE deliverable is textured-mesh game assets in FBX, not USD.** Both the
   environment mesh and each per-object hull are delivered to UE as **FBX files
   with an embedded baked-texture material**. USD is **demoted to an optional /
   archival side-artifact** — it may still be emitted for inspection and external
   archival, but it is **no longer the contract** the UE stage consumes.

2. **Captured colour is baked to a UV texture before the UE boundary.** Each
   env/object mesh goes through:
   - **`mesh_cleaner` with `smooth_iterations=0`** — Laplacian smoothing is
     skipped because it produces degenerate / near-zero-area triangles that
     **crash xatlas** during UV parameterization. Cleaning runs (component / dup
     handling) but **no smoothing pass**.
   - **`texture_baker.bake_from_vertex_colors`** — xatlas generates the UV atlas
     and the per-vertex captured colour is baked into a texture image.
   - **FBX export with the texture embedded**, imported into UE with a
     **baked-texture material** bound to it. Captured colour reaches UE through the
     texture, the one channel UE does not drop.

3. **Nanite owns the polygon budget — do NOT prune gaussians for UE.** UE 5.8
   **Nanite** virtualised geometry handles the dense triangle counts of the
   captured meshes directly. There is no gaussian-pruning / decimation step gated
   on a UE polygon budget; deliver the full-resolution baked mesh and let Nanite
   manage LOD.

4. **`v2g:*` lineage, if carried into UE, rides on UE asset metadata tags — not on
   delivered USD.** Because USD is no longer the delivered contract, the lineage
   that ADR-011 authored as USD `v2g:*` customData is mirrored onto **UE asset
   metadata tags** (`unreal.EditorAssetLibrary.set_metadata_tag`) at import time,
   sourced from the build manifest / sidecars. The USD side-artifact may still
   carry `v2g:*` for archival, but the **live carrier inside UE is asset tags**.

## Alternatives considered

- **Native LichtFeld USD → UE (ADR-016 Decision 3, "Stage Actor primary").**
  Rejected as the deliverable: the native export's `ParticleField` / gaussian prim
  is **un-importable as a mesh** by UE's USD importer. The Stage-Actor path also
  drops `displayColor` (renders flat white) even where prims do load. Retained only
  as an optional archival/inspection artifact, not the contract.
- **Vertex-colour GLB or FBX → UE (rely on colour riding in geometry).** Rejected:
  UE drops vertex colours on FBX, OBJ, and GLB (`COLOR_0`) — the mesh renders flat
  white / unlit. Colour must be a baked texture, not vertex colour. (And GLB is not
  even an accepted `import_file` container.)
- **A UE gaussian-splat plugin (render the gaussians natively in UE).** Optional,
  orthogonal — it can preview the splat, but it is **not the textured-mesh
  game-asset deliverable** this ADR fixes. The contract is a polygonal, textured,
  Nanite-managed scene; a splat plugin is a separate preview path.
- **Pruned/decimated mesh to fit a UE polygon budget.** Rejected: unnecessary —
  Nanite handles the polygon count, and decimation would discard captured detail.

## Consequences

**Positive:** captured colour **reliably reaches UE** (the baked texture is the one
channel UE does not drop); the path reuses the project's own
`texture_baker.bake_from_vertex_colors` + `mesh_cleaner` (CLAUDE.md §3.1 — prefer
existing capability over new custom Python); the output is a **game-asset-correct**,
Nanite-friendly textured FBX that UE consumes natively; no fragile dependence on
USD `customData` / `displayColor` survival; no gaussian-pruning step to tune.

**Negative / cost:** the delivered contract **loses USD's structured scene graph +
`customData` lineage** as the thing UE consumes — lineage must now be **carried as
UE asset metadata tags** (set at import), an extra mirroring step instead of "it's
in the USD". Each textured asset costs a **bake** (xatlas + texture render), and the
`smooth_iterations=0` requirement means we forgo Laplacian smoothing to keep xatlas
stable (the meshes are not smoothed before bake). The web GLB (ADR-006) and the UE
FBX are now **two distinct delivery formats** of the same mesh.

**Risks / caveats (inherited from ADR-016 L2 / ADR-018 §3):**
- **Room/scene-scale captured colour does not bake cleanly.** xatlas / UV bake
  works on **clean watertight object hulls**, but **room-scale MILo meshes**
  (many thin/disconnected components) yield degenerate UV islands → a near-black
  atlas. For scene-scale colour the highest-fidelity visual remains a **direct
  gsplat render**, not a baked-mesh texture — this ADR fixes the *asset format* and
  the *object-hull* colour path; scene-scale colour still routes through gsplat.
- **Component filtering must remap vertex colours through the kept-vertex index
  map** before the bake (ADR-018 §"Color-preservation contract"); rebuilding a mesh
  from filtered geometry without re-attaching colours yields trimesh's default gray.

## Related Decisions

- `adr-016-unreal-scenegraph-export.md` — its "USD scenegraph is the UE delivery
  contract / Stage Actor primary" decision is **demoted by this ADR** to an optional
  archival artifact (see ADR-016 Amendment 2026-06-22). The `ParticleField`
  un-importability and the `displayColor`/`COLOR_0` drops it documented are the
  forcing facts here.
- `adr-011-usd-metadata-enrichment.md` — its `v2g:*` USD customData schema is no
  longer the **delivered** contract; lineage rides on UE asset metadata tags (see
  ADR-011 Amendment 2026-06-22). The schema content is unchanged; only its delivered
  carrier moves.
- `adr-018-unreal-exhibit-builder.md` — this ADR fixes the **delivered asset
  format** the exhibit builder's Phase-A bake produces (textured FBX game assets);
  ADR-018 §3 already established the baked-texture-vs-vertex-colour and the
  gsplat-for-scene-scale split this ADR formalises as the contract.
- `adr-006-splat-transform-web-delivery.md` — the web `.ksplat` / `.glb` delivery is
  unchanged and separate; the UE FBX is a distinct delivery target.
- `adr-003-pluggable-mesh-extraction-backends.md` / `adr-010-key-item-hull-recon.md`
  — supply the env mesh and per-object hulls that this ADR bakes and exports as FBX.

## References

- ADR-016 Amendment 2026-06-21 (L2) — UE drops `displayColor` and `COLOR_0`; baked
  texture is the only captured-colour channel.
- ADR-018 §3 + "Color-preservation contract" — bake-vs-vertex-colour, gsplat for
  scene scale, vertex-colour index remap on component filtering.
- `src/pipeline/texture_baker.py` `bake_from_vertex_colors` (xatlas UV atlas bake).
- `src/pipeline/mesh_cleaner.py` (`smooth_iterations` — set to 0 to avoid
  xatlas-crashing degenerate triangles).
