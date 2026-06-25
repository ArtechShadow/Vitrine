# QE-Fleet Audit — ArtiFixer-Ada Fork (PRD / ADR-020 / DDD)

> 2026-06-23. 9-agent agentic-QE fleet (4 dimension reviewers + adversarial critic + synthesis)
> over the three authored decision docs. Verdict: **GO for P0 (Ada smoke test), NO-GO for P1
> (does-it-help gate) until blockers B1-B6 are closed.** Full audit below; companion docs:
> PRD-artifixer-ada-fork.md, adr-020-artifixer-ada-fork-recon-enhancement.md,
> DDD-artifixer-recon-enhancement.md.

---

# QE-Fleet Audit Synthesis — ArtiFixer-Ada Fork (PRD / ADR-020 / DDD)

Docs reviewed: `PRD-artifixer-ada-fork.md`, `adr-020-artifixer-ada-fork-recon-enhancement.md`, `DDD-artifixer-recon-enhancement.md` (all in `/home/devuser/workspace/gaussian/LichtFeld-Studio/research/decisions/`).

---

## 1. READINESS VERDICT

**NEEDS-REWORK** — to start P1. **APPROVED-WITH-FIXES** — to start the P0 Ada smoke test.

The split is the headline. The five technical fork facts (SDPA fallback, bf16 one-card fit, CP=1, 3DGRUT JIT, zero app-code) are faithfully and correctly represented across all three docs (technical-accuracy: "no BLOCKERs"). The motion-blur caveat, optional/per-scene/off-by-default posture, and the dominant-risk framing are clean and consistent. So the docs are sound enough to *build and smoke-test the fork*.

But the **decisive P1 gate is hollow**: an unnamed/unverified test scene, a pass-metric tool that does not exist (and is itself an open question), a pass bar explicitly not committed, and a central A/B that is confounded — plus an architectural integration mismatch (the adapter's consumer may not exist on the default backend). These must be closed before P1 can be *executed or adjudicated*, but most do not block P0.

---

## 2. BLOCKERS (must-fix before proceeding)

### Group A — The P1 gate is not executable/adjudicable (the decisive deliverable)

- **B1. No named, on-disk P1 test scene.** *(completeness #1)* PRD §7.2 / OQ-2, ADR Decision-reversal, DDD §7. "One real dreamlab scene" is never named or shown to exist. **Fix:** resolve OQ-2 to a concrete scene id + filesystem path (`images/` + `sparse/0/*.bin`), with baseline LichtFeld `.ply` and current CoMe/TSDF mesh pinned by path. Demote from "open question" to a P1 entry precondition.

- **B2. The pass metric is not computable — no tool exists, and the doc admits it.** *(completeness #2)* PRD §7.2 + OQ-3. PASS = "≥25% reduction in under-observed hole/missing-surface area AND fewer floaters," but OQ-3 concedes no script computes it and "under-observed region" has no operational definition. **Fix:** before P1, commit (a) the under-observed mask derivation + threshold (COLMAP-frustum coverage), (b) one primary hole measure, (c) a floater/stray-component definition (min-component-vertex threshold), (d) a committed script path/owner.

- **B3. The 25% pass bar is self-invalidated.** *(completeness #3, consistency #5)* PRD §7.2 calls 25% "proposed, not derived," set at kickoff against the baseline by the same party running the experiment; ADR/DDD give no number. Unfalsifiable/gameable. **Fix:** commit 25% now, or specify a deterministic kickoff rule (e.g., bar = max(25%, 2× measured baseline hole-area noise floor over N runs)); quantify the "within noise" secondary condition.

### Group B — Architectural integration mismatch (blocks the adapter, the only new code)

- **B4. The adapter's premise may be false: CoMe (the default backend) does not consume a `.ply` — it re-trains its own Gaussians from COLMAP.** *(adversarial #1)* `come_extractor.py:249-368`, `stages.py:750-1092`. DDD §5.2's ACL converts ArtiFixer3D→`.ply` for "CoMe/TSDF," but CoMe takes a dataset root and trains, then *produces* a `point_cloud.ply` — it does not ingest one. The enhanced recon can only plausibly feed **gsplat-TSDF** (the fallback), not the default. The P1 invariant ("same backend, only recon source varies") is **not achievable on CoMe** as designed. **Fix:** resolve CoMe-vs-TSDF routing *before P0* — it decides whether the adapter is even reachable. Stop treating "CoMe/TSDF" as one interchangeable consumer.

### Group C — The A/B comparison is confounded (a PASS/FAIL would be unattributable)

- **B5. P1 confounds three variables; promote OQ-8 to a required control arm.** *(completeness #11, risk #2, adversarial #3)* PRD OQ-8. ArtiFixer3D trains its *own* 10k-iter 3DGRUT recon vs. LichtFeld's ImprovedGS+, so `ArtiFixer3D→mesh` vs `LichtFeld→mesh` moves recon-engine + enhancement + adapter-loss at once. A P1 FAIL could be caused entirely by an inferior 3DGRUT base. **Fix:** add a mandatory third arm — raw-3DGRUT (un-enhanced) → same mesh — to isolate the enhancement delta. Promote OQ-8 from open question to a required P1 control in PRD §7.2, ADR exit criterion, and DDD §7.

### Group D — Commercial-licence leakage has no enforcement

- **B6. The NVIDIA-noncommercial-weights mitigation is a label with no verified gate, on a delivery path shared with the commercial track.** *(risk #7)* PRD R10/FR-5.1/NFR-4.2, ADR + DDD §5.3. Mitigation is the `v2g:recon_enhanced=true` tag plus a "`--commercial` posture excludes the ArtiFixer branch" that is asserted to exist with no reference — and the FBX→UE path (ADR-019) is *shared* with the commercial deliverable. **Fix:** cite the actual commercial-exclusion gate (file:line) or mark it a to-build enforcement requirement with an owner; do not present "mirrors CoMe" as an existing control.

> Note: completeness flagged VRAM ceiling (#4) as a BLOCKER for P1; it is consolidated under Major M1 since it is a P0-resolvable measurement, not a P1-gate logic defect.

---

## 3. MAJOR FINDINGS

- **M1. VRAM is an unmeasured estimate with no pass ceiling.** *(completeness #4, technical #1, risk — implicit)* NFR-1.1/G1/P0-gate-3 assert "~28 GB / mid-30s peak, fits 48 GB" as fact, but the QE source says **"No inference-VRAM figure published."** P0 records peak but sets no ceiling — any peak under 48 GB OOM "passes" with zero margin. **Fix:** flag the figures as unmeasured estimates pending P0; set a concrete pass ceiling with headroom (e.g., ≤ 42 GB).

- **M2. No disk budget anywhere despite 67.6 GB checkpoint + 2nd recon stack + sidecar image.** *(completeness #5)* Consumers (67.6 GB `artifixer-14b.pt`, NGC+cu128 image, ~60 GB captioner, per-scene working set) plausibly exceed the ~200 GB free. **Fix:** add an NFR disk budget + a P0 free-space precondition; state whether the checkpoint lands in `data/comfyui/models/`.

- **M3. No rollback/cleanup/abort requirement.** *(completeness #6)* ADR "Decision-reversal" is program-level; nothing reverts the submodule, sidecar image, config key, 67.6 GB checkpoint, or `v2g:recon_*` markers on P1 FAIL. **Fix:** add an explicit "P1 artifacts are disposable, removed on FAIL" rollback requirement.

- **M4. No committed runtime/wall-clock budget — a stated P1 FAIL condition has no threshold.** *(completeness #7, risk #10)* PRD §7.2 "wall-clock the team accepts" + OQ-6 leave the gate's own pass condition unthresholded. **Fix:** commit a ceiling at P1 kickoff (e.g., FAIL if > N min/scene on one Ada @200 W); resolve OQ-6.

- **M5. Ownership unassigned for every gate and deliverable.** *(completeness #8, risk #1)* No named owner for the host build (which the agent sandbox cannot do — load-bearing human dependency), the metric script, the bar-setting, or the verdict. No risk-owner column in PRD §9 / ADR / DDD §7. **Fix:** assign accountable roles; add an Owner column; state the human-host-build precondition explicitly.

- **M6. FR-4.2 / P2-gate-2 "byte-for-byte / disabled run == current pipeline" is untestable and likely false.** *(completeness #9)* GPU/float nondeterminism makes "byte-for-byte" the wrong invariant. **Fix:** replace with code-path additivity — `recon_enhance=none` imports no ArtiFixer module, takes no new branch, verified by a named regression test.

- **M7. Adapter fidelity has no acceptance criterion — only a list of unknowns.** *(completeness #10, risk #9)* DDD §5.2 lists SH layout, activation space (critical), quaternion order, coordinate frame; "plausible scale" is undefined; frame-misalignment isn't even tracked as a PRD risk and could poison the gate indistinguishably from "didn't help." **Fix:** define a round-trip test with numbers (re-render adapted `.ply` from K held-out COLMAP poses, require PSNR ≥ X vs native 3DGRUT render); pin the scale-sanity bound to a multiple of COLMAP scene extent; add frame-alignment as a P1 sanity assertion.

- **M8. Two figures carry QE-grade authority the QE audit does not contain.** *(technical #1, #2)* ADR (lines 56/98) "67.6 GB / ~16.9B params" — not in QE, and 16.9B silently contradicts the "14B" base used everywhere; DDD reframes QE's `num_inference_steps=4` as "AR distillation steps," a substantive re-characterization. **Fix:** source 67.6 GB/param count to the evaluation doc (or drop), reconcile 16.9B vs 14B; rename the field `num_inference_steps` or flag the AR interpretation as unverified inference.

- **M9. slangc/3DGUT JIT residual risk has an empty/wrong mitigation.** *(risk #3)* PRD R6 collapses slangc + 3DGUT + gcc + arch-list into one row; "pin gcc ≤ 11" does not cover a missing/incompatible **slangc** (a separate Slang toolchain). **Fix:** split R6 per-toolchain; pin the slangc version the submodule needs + a rasterizer-only fallback.

- **M10. 2nd-reconstruction-stack maintenance is a first-class ADR consequence but absent from the PRD risk register.** *(risk #6)* Forked Dockerfile/CI drift + dual CUDA/torch/JIT toolchains. **Fix:** add a PRD §9 maintenance-burden risk (High/Med, owner = Maintainer), mitigated by the P2-only commitment + NFR-5.1 pinning.

- **M11. The "~1.5–2 person-day / zero app-code" estimate is P0-only but reused as the whole-program cost.** *(risk #8, adversarial #4)* The QE figure covers build + one E2E inference + one prep pass. P1 (metric tooling, throwaway adapter reverse-engineering, confound arm, NVS eval, CoMe/TSDF routing, host GPU-image build) is plausibly 1–2 person-*weeks*. Toolchain remediation (cu128 wheel lacking sm_89 → source rebuild) can individually blow it. **Fix:** add a PRD §9 risk that the estimate is P0-only and conditional; soften "zero app-code" to "zero *expected*"; cost/bound the P0 fix path.

---

## 4. CONSOLIDATED MINOR / NIT LIST

**Consistency (developer-divergence risks — fix first):**
- N1. **Adapter filename:** ADR `artifixer_adapter.py` vs DDD `artifixer_extractor.py` (×8, ADR-003-grounded). Fix the ADR. *(consistency #1)*
- N2. **Config key:** PRD `recon.enhance=artifixer3d` vs DDD `config.training.recon_enhance` (default `"none"`). Standardize on the DDD spelling/namespace/sentinel; update PRD FR-4.1. *(consistency #2)*
- N3. **Dockerfile:** PRD/ADR `Dockerfile.cuda12.ada-sm89` (forked build) vs DDD `docker/Dockerfile.artifixer` (sidecar) — reconcile as same-or-two, spell out the relationship. *(consistency #3)*
- N4. **Forked-source location:** DDD's "`external/`-equivalent" collides with BOUNDARIES (`external/` = upstream/do-not-touch). Name an our-additions location (`third_party/`/`vendor/`/under `src/pipeline/`); drop the `external/` reference. *(consistency #4)*

**Reproducibility / enforcement:**
- N5. NFR-5.1 lists pins but no verification they resolve; no checkpoint SHA, `v2g:artifixer_weights_sha` unsourced. Add a P0 precondition recording resolved commit/weight SHAs + image digest; run a `sota_registry`-style preflight. *(completeness #13)*
- N6. NG2 ("research/eval-only") has no enforcement test — specify the lineage marker name + the concrete CI/preflight check. *(completeness #14)* (overlaps B6)
- N7. cu128/NGC arch-list risk states the *check* but no *failure path* (wheel lacking sm_89 → `TORCH_CUDA_ARCH_LIST=8.9` + source rebuild); ADR item-7's "no-op/optional" is wrong if the cubin is absent. *(risk #4)*

**Captioner (3 reviewers — single fix):**
- N8. Pin **"Qwen3-VL-30B (~60 GB bf16)"** everywhere (PRD NFR-1.3/R7 drop "-30B"); reconcile 60 GB vs the 48+48 budget; make NFR-1.3 a default (skip) with shard-via-`device_map=auto` + P0 peak record; note the prep-time two-card hold conflicts with NFR-1.2/ADR-013; resolve OQ-7. *(completeness #12, technical #5, consistency #9, risk #5)*

**Scope / pass-bar cross-referencing:**
- N9. ADR Decision-reversal + DDD §7 should cite the PRD §7.2 quantified bar so the three don't read as independently-scoped gates. *(consistency #5)*
- N10. Add "the variant we integrate is ArtiFixer3D; plain ArtiFixer / ArtiFixer3D+ are out of scope" to PRD §2 + ADR Context (mirror DDD §1). *(consistency #6)*
- N11. Align PRD tap-point wording to "forks at COLMAP SfM, parallel to LichtFeld 3DGS training" (DDD's parallel-consumer framing). *(consistency #7)*
- N12. State P1 is a single-scene go/no-go *for further investment only* (not a generalization claim); add a ≥1-additional-scene P2 entry condition. *(completeness #15)*

**Nits (provenance/wording):**
- N13. "~10k iters" 3DGRUT count not in QE — attribute to the evaluation doc. *(technical #3)*
- N14. PRD §1 "FA3 import is try/except" understates QE (no top-level `flash_attn` import in the inference path) — align to ADR wording. *(technical #4)*
- N15. DDD §5.3 `--inference_pipeline AR` — literal value "AR" unverified by QE; write "the default (AR) inference pipeline" or verify. *(technical #6)*
- N16. PRD should reconcile "67.6 GB on-disk vs ~28 GB bf16 runtime" once at NFR-5.1. *(consistency #8)*
- N17. Difix3D+ fallback's own sm_89 feasibility is unverified — add a one-line caveat. *(risk #11)*

**Baseline-strawman caveats (adversarial — fold into B2/B3):**
- N18. Opacity-mix "fills only unobserved regions" may be backwards for dense+blurred capture (holes bordered by partial-opacity floaters get *preserved*); flag as the primary reason H1 may fail, not "test it." *(adversarial #2)*
- N19. P1 baseline must be the **post-cleanup** CoMe/TSDF mesh (`come-tets-cleanup-recipe` already de-holes for ~zero cost) — otherwise ArtiFixer is credited for removing floaters a 50-line post-process already removes. *(adversarial #5)*
- N20. A better *recapture* (already the stated data plan) may eliminate the under-observed holes ArtiFixer targets — test whether under-observation is a capture-protocol defect (free upstream fix) before maintaining a 2nd stack. *(adversarial #5)*

---

## 5. THE ONE THING THE TEAM MUST NOT LOSE SIGHT OF

**P1 is the only decision that matters, and as written it cannot render a trustworthy verdict.** Four independent reviewers converge on the same hollow core: the gate compares against an unnamed scene (B1), with a metric that doesn't exist (B2), against a bar nobody has committed (B3), through a comparison that confounds the enhancement with a weaker base recon (B5) and possibly an uncleaned strawman baseline (N19) — and the adapter feeding it may not even connect to the default backend (B4). Before spending the real money (1–2 person-*weeks*, not the advertised 1–2 days — M11), make the P1 gate **falsifiable and attributable**: a pinned scene, a committed metric+bar, a three-arm comparison, and a cleaned-mesh baseline. Otherwise P1 will produce a number that kills or greenlights the program for reasons no one can defend.

---

## GO / NO-GO (P0 Ada smoke test)

**GO** — the documented plan is sound enough to start the **P0 Ada smoke test** (the fork facts are verified, the build recipe is consistent), *provided* P0 is amended to record peak VRAM against a committed ceiling (M1), check free disk first (M2/N5), and pin resolved SHAs (N5) — but it is **NO-GO for P1** until Blockers B1–B6 are closed.
