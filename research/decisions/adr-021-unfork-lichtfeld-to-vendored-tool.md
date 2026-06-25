# ADR-021 — Un-fork: vendor LichtFeld-Studio as a pinned tool

**Status:** Accepted (2026-06-25)
**Supersedes:** ADR-002 (upstream sync strategy — one-way pull from MrNeRF/LichtFeld-Studio is replaced by submodule pin)
**Affects:** `BOUNDARIES.md`, `CLAUDE.md`, `README.md`, `AGENTS.md`, `CLAUDE_CONTAINER.md`, `Dockerfile.consolidated`

---

## Context

Vitrine began as an isolated fork of MrNeRF/LichtFeld-Studio (branch `gaussian-toolkit`) in March 2026. The fork model was chosen for early velocity: we could co-locate the upstream C++ source with our Python pipeline additions and build everything in one tree.

By June 2026, the fork had accumulated ~142 commits of divergence behind the upstream v0.5.3 release. Every periodic sync required resolving conflicts across the upstream source tree (`src/core/`, `src/app/`, `src/mcp/`, `src/rendering/`, `src/training/`, `src/geometry/`, `src/io/`, `src/sequencer/`, `src/visualizer/`, `src/python/`, `cmake/`, `external/`, `eval/`, `tools/`, `CMakeLists.txt`, `vcpkg.json`) even though **Vitrine has never modified any upstream file**. The entire diff between Vitrine and the upstream `main` branch consists solely of our additions (`src/pipeline/`, `src/web/`, `scripts/`, `unreal/`, `onboarding/`, `docker/`, `docs/`, `research/`); not one line of LichtFeld core has been changed.

The pain is asymmetric: the cost of the fork relationship (conflict surface, mental model, CLAUDE.md warnings, merge ceremonies, accidental-edit risk) is real and growing, while the benefit (being in the same git tree as the upstream source) is now zero — we interact with LichtFeld purely via its built binary and its MCP HTTP server, never by importing or patching its C++ source directly.

Simultaneously, upstream shipped v0.5.3 — a stable release we want to track but whose merge would touch every upstream directory at once, exactly the conflict surface the fork model can no longer handle cheaply.

The conclusion is structural: Vitrine's value (capture-adaptive pipeline, mesh/splat → UE 5.8 delivery, agentic orchestration) lives entirely in our own additions. LichtFeld is an external tool we consume, not code we develop. The fork model is the wrong abstraction.

---

## Decision

**Phased submodule un-fork:**

1. **Add `vendor/lichtfeld-studio` as a git submodule pinned to tag `v0.5.3`.** This is the canonical location of LichtFeld source going forward. The submodule is consumed: the `Dockerfile.consolidated` build step that compiled LichtFeld from the in-tree source is rewired to build from `vendor/lichtfeld-studio` instead.

2. **Remove the `upstream` git remote.** There is no longer an upstream remote to track. The `upstream` remote (`MrNeRF/LichtFeld-Studio`) is dropped from the repo's git config. Going forward, version bumps are expressed by changing the submodule SHA and pushing the updated `.gitmodules` + submodule ref.

3. **Reframe all project documentation now.** `BOUNDARIES.md`, `CLAUDE.md`, `README.md`, `AGENTS.md`, `CLAUDE_CONTAINER.md`, and all ADR cross-references are updated in this commit to reflect Vitrine as a **standalone project** that vendors LichtFeld as a pinned tool.

4. **Delete the legacy in-tree upstream source as a host-validated follow-up.** The directories `src/core/`, `src/app/`, `src/mcp/`, `src/rendering/`, `src/training/`, `src/geometry/`, `src/io/`, `src/sequencer/`, `src/visualizer/`, `src/python/`, `cmake/`, `external/`, `eval/`, `tools/`, `tests/` (upstream suite), `CMakeLists.txt`, and `vcpkg.json` will be deleted in a subsequent commit after the Docker build has been validated to build cleanly from `vendor/lichtfeld-studio`. This is a two-step process to avoid breaking the build before the rewire is confirmed.

**Update policy going forward:** to pick up a new LichtFeld release, change the submodule pin to the target tag, run `git submodule update --init --recursive`, rebuild and test, then commit the updated submodule ref. No merges, no conflict resolution, no upstream remote.

**What we never do:**
- Modify any file under `vendor/lichtfeld-studio/`.
- Push to or open pull requests against `MrNeRF/LichtFeld-Studio`.
- Re-introduce a fork relationship or upstream remote.

---

## Rationale

- **Zero-modification fork.** Vitrine has never modified a single file in the upstream source tree. A fork that never patches the upstream is not a fork in any meaningful sense — it is a build dependency that happens to live in the same git repo. Moving it to a submodule makes the relationship accurate.
- **Conflict surface disappears.** The pain of periodic upstream sync (resolving changes across 20+ upstream directories we do not own) drops to zero. Bumping the submodule tag is deterministic: there are no Vitrine-side changes to reconcile against upstream changes because we have none.
- **Clean ownership model.** After the in-tree source is removed, `vendor/lichtfeld-studio` is unmistakably "not ours" and `src/pipeline/` et al. are unmistakably ours. There is no ambiguity about what may be edited.
- **v0.5.3 is available immediately.** We pin to the stable release we want rather than deferring it behind a merge ceremony.
- **Documentation and agent instructions simplify.** The "do not modify upstream dirs" warnings, the one-way pull policy, the merge conflict resolution rules, and the upstream-remote references in CLAUDE.md, BOUNDARIES.md, and CLAUDE_CONTAINER.md are all replaced by a single simpler rule: do not touch `vendor/lichtfeld-studio/`.

---

## Consequences

### Positive

- **No more merge conflicts on upstream syncs.** Bumping the submodule tag is a single-line commit; there is no conflict surface.
- **Clearer identity.** Vitrine is described accurately as a standalone pipeline that uses LichtFeld as a tool, which is what it has always been in practice.
- **Simpler agent/developer instructions.** The BOUNDARIES.md decision framework no longer requires a "do not modify upstream dirs" section; the rule is implicit in the submodule structure.
- **Immediate access to v0.5.3.** New MCP tools, training improvements, and stability fixes in v0.5.3 are available as soon as the Docker build is validated against the submodule.
- **Reduced repo cognitive overhead.** Removing ~20 upstream directories from the editable tree eliminates a large class of accidental edits and reduces `git status` noise.

### Negative

- **Two-step transition.** Until the in-tree upstream source is deleted (the follow-up commit), both the submodule and the legacy source coexist in the tree. The Docker build must be carefully switched to build from the submodule before the legacy source is removed; running both in parallel risks stale-build confusion.
- **Submodule UX overhead.** Developers must remember `git submodule update --init --recursive` after clones and after submodule bumps. CI must explicitly initialise submodules. This is a well-understood git pattern but is a minor additional step compared to a plain checkout.
- **No cherry-picks from upstream.** If a specific upstream fix is needed before a full stable tag is available, the path is either wait for the next tag or temporarily pin to a commit SHA (acceptable but less clean than a tag). The old fork allowed selective cherry-picks; the submodule model encourages full-tag bumps.
- **Build time unchanged.** LichtFeld is still built from source inside the Docker image; the submodule only changes where that source lives, not how long compilation takes.

### Neutral

- The LichtFeld MCP server (`http://localhost:45677/mcp`) continues to be the integration surface for all LichtFeld-native operations (training, rendering, scene export). Nothing in the pipeline touches LichtFeld source directly; this change is invisible to runtime behaviour.
- GPL-3.0 obligations are unchanged. The vendored submodule is GPL-3.0; Vitrine's own additions remain GPL-3.0 as a derivative work.
- ADR-002 (upstream sync strategy, one-way pull, v0.5.2 tag) is superseded. ADR-008 (Vulkan migration gating) remains valid as a future submodule-bump trigger.

---

## Alternatives Considered

- **Continue the fork, absorb v0.5.3 via merge.** Rejected. The merge touches every upstream directory simultaneously with hundreds of commits; resolving conflicts across files we have never modified is pure ceremony with no benefit. The conflict surface will only grow with each subsequent release.
- **Fork + scripted overwrite (replace upstream dirs wholesale on each sync).** Rejected. A scripted overwrite is a submodule in disguise but without git's integrity guarantees (content-addressed SHA pinning, explicit update mechanics, submodule status visibility). It is strictly worse than a submodule.
- **Separate repos (Vitrine repo + LichtFeld as a sibling clone).** Considered and rejected in favour of the submodule. A sibling clone is not versioned; two developers can silently have different LichtFeld versions. The submodule pins the exact commit SHA in the Vitrine repo, making the LichtFeld version part of the reproducible build definition.
- **Keep the fork but stop syncing.** Rejected. Freezing on an old LichtFeld version indefinitely forfeits v0.5.3 improvements and accumulates growing divergence from a codebase we do not control. The clean break is better than slow drift.

---

## Related Decisions

- `adr-002-upstream-sync-strategy.md` — **Superseded.** The v0.5.2 sync and one-way pull isolation policy it defined are replaced by the submodule pin model.
- `adr-008-defer-vulkan-migration.md` — Still valid; Vulkan migration remains a future submodule-bump trigger when v0.5.x ships a stable headless Vulkan path.
- `adr-019-mesh-game-assets-not-usd-into-ue.md` — Unchanged; the UE deliverable (textured FBX game assets) is unaffected by how LichtFeld is vendored.
- `adr-020-artifixer-ada-fork-recon-enhancement.md` — Unchanged; ArtiFixer lives in its own sidecar submodule, orthogonal to the LichtFeld vendor change.
- `BOUNDARIES.md` — Updated in this commit to reflect the new standalone + vendored-tool ownership model.
