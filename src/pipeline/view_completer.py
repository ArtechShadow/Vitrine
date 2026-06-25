# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generative 360 view completion (ADR-017).

When an object's capture is partial, the Gaussian splat has no data for the
unobserved sides, so the orbit renderer produces empty panels and the hull is
missing its back/top. This module fills those gaps generatively: it keeps the
panels the splat *did* observe and, for the empty slots only (coverage-gated —
do no harm to real geometry), prompts FLUX.2 to synthesise a plausible novel
view that is consistent with the observed panels (used as reference latents).

This is ADR-014's Generative Recovery applied to the full turnaround, and the
concrete realisation of the FLUX.2 long-form-instruction rationale: a JSON-
structured prompt describes the object identity, the target view, and hard
consistency constraints, which the Mistral-3 encoder follows.

Completed panels are *plausible, not measured* — callers should tag them as
synthesised in the per-object lineage (``v2g:view_synth=true``).
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).parent / "workflows"
FLUX2_TURNAROUND_WORKFLOW = WORKFLOW_DIR / "flux2_turnaround.json"

# Panel label -> (azimuth_deg, elevation_deg) for prompt construction. Matches
# the renderer's ``trellis_6`` preset (multiview_renderer.generate_orbit_cameras).
_VIEW_GEOMETRY = {
    "front": (0, 0), "left": (90, 0), "back": (180, 0), "right": (270, 0),
    "top": (0, 85), "bottom": (0, -85),
}


@dataclass
class CompletedView:
    label: str
    path: Path
    synthesised: bool      # True if FLUX.2-generated, False if real splat render
    coverage: float        # splat coverage fraction of the original render


@dataclass
class ViewCompletionResult:
    views: dict[str, Path] = field(default_factory=dict)
    synthesised: list[str] = field(default_factory=list)   # labels that were generated
    kept: list[str] = field(default_factory=list)          # labels kept as real renders
    error: Optional[str] = None


class ViewCompleter:
    """Coverage-gated FLUX.2 view completion for the TRELLIS.2 panel set.

    Parameters
    ----------
    comfyui_url : str
        ComfyUI endpoint (the FLUX.2 stack must be staged).
    gap_threshold : float
        Panels with coverage <= this are treated as unobserved and generated.
    keep_threshold : float
        Panels with coverage >= this are always kept as real renders.
        Between the two thresholds the panel is kept (real data preferred).
    steps, guidance, seed : sampler params for FLUX.2.
    max_references : int
        How many observed panels to feed as reference latents (workflow has 2).
    """

    def __init__(
        self,
        comfyui_url: str = "http://vitrine-comfyui:8188",
        gap_threshold: float = 0.02,
        keep_threshold: float = 0.10,
        steps: int = 28,
        guidance: float = 4.0,
        seed: int = 42,
        max_references: int = 2,
        timeout: int = 600,
        poll_interval: float = 2.0,
        workflow_path: str | Path | None = None,
    ):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.gap_threshold = gap_threshold
        self.keep_threshold = keep_threshold
        self.steps = steps
        self.guidance = guidance
        self.seed = seed
        self.max_references = max_references
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.workflow_path = Path(workflow_path) if workflow_path else FLUX2_TURNAROUND_WORKFLOW
        self.session = requests.Session()

    @classmethod
    def from_config(cls, cfg: Any) -> "ViewCompleter":
        return cls(
            comfyui_url=getattr(cfg, "comfyui_url", "http://vitrine-comfyui:8188"),
            gap_threshold=getattr(cfg, "gap_threshold", 0.02),
            keep_threshold=getattr(cfg, "keep_threshold", 0.10),
            steps=getattr(cfg, "steps", 28),
            guidance=getattr(cfg, "guidance", 4.0),
            seed=getattr(cfg, "seed", 42),
            max_references=getattr(cfg, "max_references", 2),
            timeout=getattr(cfg, "timeout", 600),
        )

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    @staticmethod
    def coverage(image_path: Path) -> float:
        """Fraction of the panel occupied by the object (splat coverage).

        Uses the alpha channel when present (the renderer writes RGBA with a
        transparent background); otherwise falls back to the fraction of pixels
        that differ from a near-black/near-white background. Returns 0.0 on any
        read error (treated as a gap)."""
        try:
            from PIL import Image
            im = Image.open(image_path)
            arr = np.asarray(im)
            if arr.ndim == 3 and arr.shape[2] == 4:
                # Count any non-transparent pixel. Gaussian-splat renders are
                # soft (most object pixels carry low alpha 1-8), so a higher
                # threshold (e.g. >8) wrongly reads observed panels as empty and
                # the whole panel set as gaps. This matches the renderer's own
                # alpha_coverage notion (alpha > 0).
                return float((arr[..., 3] > 0).mean())
            # No alpha: object pixels are those not near the background corners.
            rgb = arr[..., :3].astype(np.int16) if arr.ndim == 3 else arr.astype(np.int16)
            bg = rgb[0, 0]
            diff = np.abs(rgb - bg).sum(axis=-1)
            return float((diff > 24).mean())
        except Exception as e:  # noqa: BLE001 - any failure => treat as gap
            logger.warning("coverage(%s) failed: %s -> 0.0", image_path, e)
            return 0.0

    # ------------------------------------------------------------------
    # Prompt construction (JSON-structured, per ADR-017)
    # ------------------------------------------------------------------

    def _build_prompt(self, view_label: str, object_desc: dict, ref_labels: list[str]) -> str:
        az, el = _VIEW_GEOMETRY.get(view_label, (0, 0))
        spec = {
            "task": "Generate ONE clean novel orthographic view of a single object "
                    "for a 360-degree turnaround, to be used for 3D reconstruction.",
            "object": object_desc.get("label") or object_desc.get("concept") or "object",
            "target_view": view_label,
            "azimuth_deg": az,
            "elevation_deg": el,
            "appearance": object_desc.get("appearance")
                or "match the exact object, colours, materials and proportions shown "
                   "in the reference views",
            "reference_views_provided": ref_labels,
            "constraints": [
                "identical object, materials, colour and scale as the references",
                "physically plausible continuation of the unseen side",
                "neutral even studio lighting, no harsh shadows or reflections",
                "pure white background, single centred object, fully in frame",
                "no text, watermark, people, or extra objects",
            ],
        }
        return ("Render the following object view exactly per this JSON specification.\n"
                + json.dumps(spec, indent=2))

    # ------------------------------------------------------------------
    # ComfyUI plumbing
    # ------------------------------------------------------------------

    def _upload_image(self, path: Path) -> str:
        with open(path, "rb") as f:
            r = self.session.post(
                f"{self.comfyui_url}/upload/image",
                files={"image": (path.name, f, "image/png")}, timeout=30,
            )
        r.raise_for_status()
        return r.json().get("name", path.name)

    def _submit(self, prompt: dict) -> str:
        r = self.session.post(f"{self.comfyui_url}/prompt", json={"prompt": prompt}, timeout=30)
        data = r.json()
        if data.get("error") or data.get("node_errors"):
            raise RuntimeError(f"ComfyUI validation error: {data.get('node_errors') or data.get('error')}")
        pid = data.get("prompt_id")
        if not pid:
            raise RuntimeError(f"No prompt_id: {data}")
        return pid

    def _poll(self, prompt_id: str) -> dict:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            try:
                hist = self.session.get(f"{self.comfyui_url}/history/{prompt_id}", timeout=60).json()
            except (requests.ReadTimeout, requests.ConnectionError):
                continue
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {}).get("status_str", "unknown")
                if status == "success":
                    return entry
                if status == "error":
                    raise RuntimeError(f"FLUX.2 view-gen error: {entry.get('status', {}).get('messages')}")
        raise TimeoutError(f"FLUX.2 view-gen {prompt_id} timed out")

    def _download_image(self, history: dict, out_path: Path) -> Optional[Path]:
        for node_output in history.get("outputs", {}).values():
            for img in node_output.get("images", []) or []:
                if not isinstance(img, dict):
                    continue
                r = self.session.get(
                    f"{self.comfyui_url}/view",
                    params={"filename": img.get("filename", ""),
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output")},
                    timeout=60,
                )
                if r.status_code == 200 and r.content:
                    out_path.write_bytes(r.content)
                    return out_path
        return None

    def _free_vram(self) -> None:
        """POST /free to unload models + free VRAM. FLUX.2 (~34GB) + Mistral-3
        (~17GB) ~= 51GB cannot co-reside with TRELLIS.2 (~24GB) on a 48GB card,
        so the completer MUST free FLUX.2 before the hull stage loads (serial
        lifecycle, ADR-013). Best-effort — never raises."""
        try:
            self.session.post(
                f"{self.comfyui_url}/free",
                json={"unload_models": True, "free_memory": True}, timeout=30,
            )
            logger.info("freed ComfyUI VRAM after view completion (FLUX.2 unloaded)")
        except requests.RequestException as e:  # noqa: BLE001
            logger.warning("free_vram after view completion failed: %s", e)

    def _build_workflow(self, prompt_text: str, ref1: str, ref2: str, size: int) -> dict:
        with open(self.workflow_path) as f:
            wf = json.load(f)
        wf = {k: v for k, v in wf.items() if not k.startswith("_")}
        wf["4"]["inputs"]["image"] = ref1
        wf["16"]["inputs"]["image"] = ref2
        wf["7"]["inputs"]["text"] = prompt_text
        wf["6"]["inputs"]["width"] = size
        wf["6"]["inputs"]["height"] = size
        wf["13"]["inputs"]["seed"] = self.seed
        wf["13"]["inputs"]["steps"] = self.steps
        wf["9"]["inputs"]["guidance"] = self.guidance
        return wf

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def complete(
        self,
        views: dict[str, Path],
        object_desc: dict | None = None,
        work_dir: str | Path | None = None,
        size: int = 512,
    ) -> ViewCompletionResult:
        """Fill unobserved panels generatively; keep observed panels as-is.

        Parameters
        ----------
        views : dict[label -> Path]
            Rendered panels from the splat (some may be empty/low-coverage).
        object_desc : dict
            Object metadata for the prompt (``label``/``concept``, ``appearance``).
        Returns a ViewCompletionResult with the completed ``views`` mapping and
        which labels were synthesised vs kept.
        """
        object_desc = object_desc or {}
        work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="viewcomplete_"))
        work_dir.mkdir(parents=True, exist_ok=True)

        cov = {label: self.coverage(p) for label, p in views.items()}
        observed = sorted(
            (l for l, c in cov.items() if c >= self.keep_threshold),
            key=lambda l: cov[l], reverse=True,
        )
        gaps = [l for l, c in cov.items() if c <= self.gap_threshold]
        result = ViewCompletionResult(views=dict(views))

        if not observed:
            result.error = "no observed panel above keep_threshold — cannot reference-condition"
            logger.warning("ViewCompleter: %s (coverage=%s)", result.error, cov)
            return result
        if not gaps:
            result.kept = list(views.keys())
            logger.info("ViewCompleter: all %d panels observed; nothing to synthesise", len(views))
            return result

        # Upload the top reference panels once.
        ref_labels = observed[: self.max_references]
        if len(ref_labels) == 1:
            ref_labels = ref_labels * 2  # workflow expects two reference slots
        try:
            ref_names = [self._upload_image(views[l]) for l in ref_labels]
        except requests.RequestException as e:
            result.error = f"reference upload failed: {e}"
            return result

        for label in gaps:
            try:
                prompt_text = self._build_prompt(label, object_desc, ref_labels[:1] + ref_labels[1:2])
                wf = self._build_workflow(prompt_text, ref_names[0], ref_names[1], size)
                pid = self._submit(wf)
                logger.info("FLUX.2 completing '%s' view (refs=%s) prompt %s",
                            label, ref_labels, pid[:8])
                hist = self._poll(pid)
                out = work_dir / f"{label}.png"
                if self._download_image(hist, out):
                    result.views[label] = out
                    result.synthesised.append(label)
                    logger.info("Synthesised '%s' view -> %s", label, out)
                else:
                    logger.warning("FLUX.2 produced no image for '%s'; leaving original", label)
            except Exception as e:  # noqa: BLE001 - one bad view must not abort the rest
                logger.warning("View completion failed for '%s': %s", label, e)

        # Unload FLUX.2 before the hull stage loads (serial lifecycle, ADR-013):
        # FLUX.2 (~34GB) + Mistral-3 (~17GB) cannot co-reside with TRELLIS.2 on a
        # single 48GB GPU.
        self._free_vram()
        result.kept = [l for l in views if l not in result.synthesised]
        return result
