# ADR-017 — Generative 360 View Completion (FLUX.2) before hull reconstruction

**Status:** Accepted (2026-06-20)
**Extends:** ADR-014 (agent-controlled ComfyUI / Generative Recovery), ADR-010 (coverage-masked recovery), ADR-015 (TRELLIS.2 primary hull)
**Drives:** `src/pipeline/view_completer.py`, `src/pipeline/workflows/flux2_turnaround.json`, the `Trellis2Client` render step

---

## Context

TRELLIS.2 reconstructs a hull from a multi-view panel set rendered **from the per-object Gaussian splat** (ADR-015; `trellis_6` preset = front/left/back/right/top/bottom). This is correct *when the capture is complete*. But real captures are frequently **partial** — an object filmed only from the front (against a wall, in a vitrine, never circled). Then the splat has **no Gaussians** for the occluded sides, so the corresponding panels render empty, and the hull is missing its back/top — exactly the gap observed on 2026-06-20.

Rendering "real" views from a partial splat cannot fill a region the splat never observed. The unseen surface must be **generatively completed** from the partial visual knowledge we *do* have plus a rich semantic prior — which is the original rationale for choosing FLUX.2: exceptional long-form instruction following, so a detailed (JSON-structured) prompt can describe the object and the desired view, and FLUX.2's reference conditioning keeps the generated side consistent with the observed sides.

## Decision

Insert a **coverage-gated generative view-completion stage** between the orbit render and TRELLIS.2:

1. **Coverage gating (do no harm).** For each panel, compute the splat's coverage (fraction of opaque/observed pixels in the render). Panels with coverage ≥ `keep_threshold` are **kept as real renders** — never regenerated. Only panels below `gap_threshold` (the splat genuinely lacks that side) are generated. This is ADR-010's principle: hallucinate *only* where there is no real data.

2. **Generator = FLUX.2-dev (primary), reference-conditioned + JSON-prompted.** Reuse the staged FLUX.2 stack (`flux2_dev_fp8mixed` + Mistral-3 encoder + flux2-vae) and the `ReferenceLatent` mechanism (already in `flux2_inpaint.json`): VAE-encode the **high-coverage observed panels** as reference latents, and condition generation on a structured prompt describing the object identity (SAM3 concept), the observed appearance, the target view (azimuth/elevation), and hard consistency constraints (match materials/colour of the references, neutral lighting, white background, single centred object). **Qwen-Image-Edit-2511 + Multiple-Angles LoRA** is the alternative path (Apache-2.0, camera-pose-conditioned via `TextEncodeQwenImageEditPlus`'s multi-image input — better for explicit view rotation; commercial-safe).

3. **JSON-structured prompts.** Prompts are built as a JSON object (object, view, azimuth_deg, appearance, palette, constraints, references) serialised into the FLUX.2 text field. FLUX.2's 24B Mistral-3 encoder follows long structured prompts far better than a CLIP encoder — the whole reason it was selected for the recovery component.

4. **Feed the completed panel set to TRELLIS.2.** `Trellis2Client` completes gaps (if `view_completion.enabled`) before uploading the panels, so TRELLIS.2 reconstructs from a full 360 set — real where observed, plausibly generated where not.

## Alternatives considered

- **More orbit views only (no generation).** Rejected as sufficient: more camera angles of a partial splat still render nothing for unobserved sides.
- **Single-image TRELLIS (let TRELLIS hallucinate the back).** Rejected: TRELLIS's single-view prior is weaker and uncontrolled vs a FLUX.2 prompt+reference; that is precisely the failure we saw.
- **Pure dedicated NVS (MV-Adapter/SEVA).** Deferred: camera-parametrised but weaker instruction control and licence (SEVA NC); FLUX.2/Qwen give controllable, prompt-driven completion. MV-Adapter remains a future option for the conditioning panels.

## Consequences

**Positive:** hulls become complete even from partial captures; the generated sides are controllable (prompt + references) and consistent; real geometry is preserved (coverage-gated). Realises the FLUX.2 long-instruction rationale concretely.

**Negative / risk:** generated sides are *plausible, not measured* — flagged in lineage (`v2g:view_synth=true` on completed panels) so downstream consumers know which surface is observed vs inferred. FLUX.2 generation adds time + VRAM (serial lifecycle handles it). Generation quality needs prompt/parameter iteration (like any diffusion stage).

## Compliance

- Completed panels are tagged in the per-object lineage as synthesised (not measured).
- `--commercial` posture should select the Qwen-Image-Edit path (Apache-2.0); FLUX.2-dev is non-commercial (idiot-check enforces).
- Coverage thresholds + generator are config-driven (`ViewCompletionConfig`).
