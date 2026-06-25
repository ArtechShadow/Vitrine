# PRD — Agent-Shepherded Interactive Unreal Exhibit Builder

**Status:** Active (2026-06-20)
**Drives:** ADR-018 (pending UE5.8 tooling research), `research/ddd/unreal-exhibit-builder-context.md`
**Builds on:** ADR-016 (USD scenegraph export → UE), the `v2g:*` lineage (ADR-011), the `exhibit.toml` manifest, the `claude_code` oversight agent (ADR-014)

---

## 1. Problem

The pipeline produces a USD scene graph (reconstructed environment mesh + individually-reconstructed, correctly-placed per-object hulls, each carrying `v2g:*` video→frame→object lineage) plus a `.ksplat`. Today that is a **static asset dump** — it has to be opened and hand-assembled to become anything a visitor can use. Vitrine's promise is an **exhibit**: a navigable, interactive 3D space where a visitor walks the reconstructed environment, interacts with the reconstructed objects, and learns from explanatory information. Hand-building that per exhibit does not scale and discards the structured knowledge (lineage, object identity, manifest) the pipeline already produced.

The opportunity: the Unreal container already has an embedded agent surface (MCP :8000 / Remote Control :30010, ADR-016). That agent should **shepherd the construction of the interactive exhibit automatically** from the USD scene + the exhibit manifest — placing the objects, wiring interactions, and surfacing the explanatory data — verifying and recovering as it goes.

## 2. Goals

- **G1 — Correct placement.** Each reconstructed object hull sits in the reconstructed environment at its true pose (the transform the USD carries from reconstruction), at correct scale/units, resting on surfaces with sane collision.
- **G2 — Interaction.** A visitor can select/gaze an object and get a clear response: highlight, reveal its information, optionally animate/orbit it for inspection.
- **G3 — Explanatory data.** Each object surfaces its `v2g:*` lineage + curated exhibit info (from the manifest) as in-world UI (info panels / tooltips), so the exhibit *explains itself*.
- **G4 — Navigable.** A camera/pawn lets the visitor move through the space (first-person walk and/or orbit-an-object).
- **G5 — Agent-shepherded + recoverable.** The container's Claude builds the scene via MCP/RC in a query→act→verify→iterate loop, and recovers from failures (missing transform, bad collision, OOM) rather than producing a broken scene — using the oversight intelligence, not bypassing it.
- **G6 — Reproducible & headless.** The build runs headlessly (`-nullrhi` for assembly, `-RenderOffscreen` for render/preview), is deterministic given the same inputs, and saves a reusable level + the lineage intact.

## 3. Non-goals

- Bespoke hand-authored gameplay or narrative scripting (the agent assembles from structured inputs; rich custom games are out of scope).
- Photoreal cinematics / Path Tracer (Lumen offscreen suffices; Path Tracer is Linux-unavailable anyway).
- Multiplayer / networking.
- The reconstruction itself (upstream — this consumes its USD output).
- Replacing the `.ksplat` web viewer (the Unreal exhibit is the *rich* delivery; the splat remains the lightweight one).

## 4. Requirements

### Functional
- **FR-1** Import the USD scene as a live USD Stage Actor preserving the full prim hierarchy and `v2g:*` customData (ADR-016 path).
- **FR-2** Place each object hull at its USD transform; verify scale/units; add collision; physics-settle onto the environment surface where appropriate; flag any object whose transform/coverage is missing or low-confidence (incl. `v2g:view_synth=true` synthesised surfaces).
- **FR-3** Attach an interaction component to each object: selectable (click/gaze/trace), with highlight (custom-depth outline), an info-reveal trigger, and an optional inspect mode (orbit/animate).
- **FR-4** Compose an annotation per object from `v2g:*` lineage + the manifest's curated copy, and bind it to in-world UI (3D widget / info panel) that appears on interaction.
- **FR-5** Add a navigation rig (first-person pawn + orbit camera) and basic lighting/exposure so the space is explorable.
- **FR-6** The build is driven by an agent loop over MCP/RC: query scene state → decide placement/interaction/annotation → issue tool calls → verify the result → iterate/recover. Each step is logged with its decision + verdict.
- **FR-7** Save the assembled exhibit (level + assets) and emit a build report (objects placed, interactions wired, annotations attached, anything flagged). Optional packaged/pixel-streamed delivery.

### Non-functional
- **NFR-1** Headless: assembly under `-nullrhi` (no GPU), render/preview under `-RenderOffscreen` (Lumen/Vulkan). NVIDIA Container Toolkit for GPU.
- **NFR-2** Lineage-faithful: `v2g:*` survives end-to-end; synthesised surfaces stay flagged so the exhibit can be honest about measured-vs-inferred.
- **NFR-3** Recoverable: the agent detects + recovers from per-object failures without aborting the whole build (oversight verify-retry).
- **NFR-4** Reproducible: same USD + manifest → same exhibit (deterministic placement; seeded where generative).
- **NFR-5** Pinned/portable: built on the UE5.8 Linux build container (ADR-016 amendment); no editor-GUI dependency for the core build.

## 5. Success criteria

- A visitor (in editor preview or a packaged/streamed build) can **walk the reconstructed space, click an object, and read its lineage + info** — with every object placed by the agent from the USD+manifest, no hand-authoring.
- The build report shows N objects placed at their reconstructed poses, N interactions wired, N annotations attached, and any flagged objects (missing transform / synthesised surface) called out.
- Re-running on the same inputs reproduces the exhibit; re-running after a deliberate fault (e.g. one object with a bad transform) shows the agent flag + recover rather than crash.

## 6. Phasing

- **P0** Import + place (FR-1, FR-2) + nav rig (FR-5) — a walkable reconstructed space with objects in place.
- **P1** Interaction + highlight (FR-3).
- **P2** Annotation UI from `v2g:*` + manifest (FR-4).
- **P3** Agent shepherding loop + recovery (FR-6) — the build becomes agent-driven + self-correcting.
- **P4** Save + delivery (FR-7) — packaged / pixel-streamed exhibit.

## 7. Risks & open questions

- **R1** First-party UE5.8 MCP is experimental — tool surface may be incomplete for full scene authoring; the :30010 Remote Control + Python commandlets are the stable fallback (resolve in ADR-018 from research).
- **R2** Headless authoring limits — some editor-only operations may need a running editor (not pure `-nullrhi`); the build may need a GPU editor session. (research)
- **R3** Interaction/UMG at runtime in a packaged build vs editor-time authoring — what the agent can wire programmatically vs what needs Blueprint assets. (research)
- **OQ-1** Verse availability in standalone UE5.8 (vs UEFN) as an authoring language for the agent. (research)
- **OQ-2** Delivery target: editor-preview only, packaged binary, or Pixel Streaming to the web alongside the `.ksplat`?
