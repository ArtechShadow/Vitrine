# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""TRELLIS.2-4B client — SINGLE-image object generation (ADR-025).

The generator is conditioned on one clean, matted best-frame crop from the
``object_crops`` stage. Splat renders are never used as conditioning (the
2026-07-09 audit + upstream microsoft/TRELLIS.2#103 showed multi-image panel
conditioning underperforms a single clean image; official TRELLIS.2 is
single-image only). The splat contributes pose/scale at USD assembly.

Two executors, selected by config:

* ``native_url`` set — thin HTTP service wrapping the native TRELLIS.2
  pipeline (``scripts/trellis2_native_service.py``): ``run(image)`` +
  ``to_glb`` x2 (high/low poly, PBR bake). Preferred (PRD v4 R5).
* ``native_url`` empty — the ComfyUI single-image workflow
  (``trellis2_single_image_pbr.json``) on the runtime-verified node pack.
  Interim executor until the native service env is stood up; ComfyUI is
  otherwise 2D-only (ADR-014 as narrowed by ADR-025).

The returned GLB bytes are the artifact: callers persist them verbatim
(hash-recorded) and must not re-export through trimesh (PRD v4 R6 — the old
re-export path silently discarded the PBR material).

Usage::

    from pipeline.trellis2_client import Trellis2Client
    client = Trellis2Client(comfyui_url="http://vitrine-comfyui:8188")
    result = client.reconstruct_from_image("object_crops/0001_vase.png")
    Path("vase.glb").write_bytes(result.glb_data)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests
import trimesh

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).parent / "workflows"
TRELLIS2_SI_WORKFLOW = WORKFLOW_DIR / "trellis2_single_image_pbr.json"

_CROP_PLACEHOLDER = "CROP_IMAGE_PLACEHOLDER"


@dataclass
class Trellis2Result:
    """Result of a TRELLIS.2 single-image object generation.

    ``glb_data`` is the generator's PBR GLB byte-for-byte; ``mesh`` is a
    trimesh view of it for stats/placement only — never re-export it.
    """
    mesh: Optional[trimesh.Trimesh] = None
    glb_data: Optional[bytes] = None
    glb_low_data: Optional[bytes] = None   # decimated game-res pair (native service)
    backend: str = "trellis2-4b-single-image"
    duration_seconds: float = 0.0
    prompt_id: str = ""
    output_paths: dict[str, str] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def glb_sha256(self) -> str:
        return hashlib.sha256(self.glb_data).hexdigest() if self.glb_data else ""

    @property
    def vertex_count(self) -> int:
        return 0 if self.mesh is None else len(self.mesh.vertices)

    @property
    def face_count(self) -> int:
        return 0 if self.mesh is None else len(self.mesh.faces)

    @property
    def has_texture(self) -> bool:
        return (
            self.mesh is not None
            and getattr(self.mesh.visual, "kind", None) in ("texture", "vertex")
        )


class Trellis2Client:
    """Client for TRELLIS.2-4B single-image object generation.

    Parameters
    ----------
    comfyui_url : str
        ComfyUI URL for the interim executor (e.g. ``http://vitrine-comfyui:8188``).
    native_url : str
        Native-pipeline service URL (``scripts/trellis2_native_service.py``).
        Empty selects the ComfyUI workflow.
    timeout : int
        Maximum seconds per generation.
    resolution : str
        ``LoadTrellis2Models`` resolution: ``512`` | ``1024`` | ``1024_cascade``
        | ``1536_cascade`` (max fidelity, default).
    texture_size : int
        PBR texture resolution (default 4096).
    seed : int
        Generation seed (re-rolls are the first escalation rung, PRD v4 R7).
    ss_steps / shape_steps / tex_steps : int
        Sampling steps for the sparse-structure / shape / texture stages.
    face_count_high / face_count_low : int
        Remesh targets for the high-poly artifact and (native service only)
        the decimated low-poly pair.
    """

    def __init__(
        self,
        comfyui_url: str = "http://vitrine-comfyui:8188",
        native_url: str = "",
        timeout: int = 1800,
        poll_interval: float = 2.0,
        resolution: str = "1536_cascade",
        texture_size: int = 4096,
        seed: int = 42,
        ss_steps: int = 12,
        shape_steps: int = 12,
        tex_steps: int = 12,
        face_count_high: int = 500_000,
        face_count_low: int = 20_000,
        workflow_path: str | Path | None = None,
    ):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.native_url = native_url.rstrip("/") if native_url else ""
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.resolution = resolution
        self.texture_size = texture_size
        self.seed = seed
        self.ss_steps = ss_steps
        self.shape_steps = shape_steps
        self.tex_steps = tex_steps
        self.face_count_high = face_count_high
        self.face_count_low = face_count_low
        self.workflow_path = Path(workflow_path) if workflow_path else TRELLIS2_SI_WORKFLOW
        self.session = requests.Session()

    @classmethod
    def from_config(cls, cfg: Any) -> "Trellis2Client":
        """Construct from a Trellis2Config, reading every field defensively."""
        return cls(
            comfyui_url=getattr(cfg, "comfyui_url", "http://vitrine-comfyui:8188"),
            native_url=getattr(cfg, "native_url", ""),
            timeout=getattr(cfg, "timeout", 1800),
            resolution=getattr(cfg, "resolution", "1536_cascade"),
            texture_size=getattr(cfg, "texture_size", 4096),
            seed=getattr(cfg, "seed", 42),
            ss_steps=getattr(cfg, "ss_steps", 12),
            shape_steps=getattr(cfg, "shape_steps", 12),
            tex_steps=getattr(cfg, "tex_steps", 12),
            face_count_high=getattr(cfg, "face_count_high", 500_000),
            face_count_low=getattr(cfg, "face_count_low", 20_000),
        )

    # ------------------------------------------------------------------
    # ComfyUI interaction (native API)
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            if self.native_url:
                r = self.session.get(f"{self.native_url}/health", timeout=10)
            else:
                r = self.session.get(f"{self.comfyui_url}/system_stats", timeout=10)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def _upload_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            files = {"image": (image_path.name, f, "image/png")}
            r = self.session.post(
                f"{self.comfyui_url}/upload/image", files=files, timeout=30,
            )
        r.raise_for_status()
        return r.json().get("name", image_path.name)

    def _submit_prompt(self, prompt: dict) -> str:
        r = self.session.post(
            f"{self.comfyui_url}/prompt", json={"prompt": prompt}, timeout=30,
        )
        data = r.json()
        if data.get("error") or data.get("node_errors"):
            node_errors = data.get("node_errors", {})
            details = "; ".join(
                f"node {nid}: {e.get('errors', e)}" for nid, e in node_errors.items()
            ) if node_errors else str(data.get("error"))
            raise RuntimeError(f"ComfyUI validation error: {details}")
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"No prompt_id in response: {data}")
        return prompt_id

    def _poll_completion(self, prompt_id: str) -> dict:
        deadline = time.monotonic() + self.timeout
        last_log = 0.0
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            try:
                r = self.session.get(
                    f"{self.comfyui_url}/history/{prompt_id}", timeout=60,
                )
                hist = r.json()
            except (requests.ReadTimeout, requests.ConnectionError) as e:
                logger.debug("History poll transient error: %s", e)
                continue
            if prompt_id not in hist:
                if time.monotonic() - last_log > 30:
                    logger.info("Waiting for TRELLIS.2 prompt %s...", prompt_id[:8])
                    last_log = time.monotonic()
                continue
            entry = hist[prompt_id]
            status = entry.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return entry
            if status == "error":
                messages = entry.get("status", {}).get("messages", [])
                raise RuntimeError(f"TRELLIS.2 execution error: {messages}")
            if time.monotonic() - last_log > 30:
                logger.info("TRELLIS.2 %s status: %s", prompt_id[:8], status)
                last_log = time.monotonic()
        raise TimeoutError(f"TRELLIS.2 prompt {prompt_id} timed out after {self.timeout}s")

    def _free_vram(self) -> None:
        """POST /free to unload models + free VRAM (serial lifecycle, ADR-013).
        Best-effort, never raises. No-op for the native service (it manages its
        own lifecycle)."""
        if self.native_url:
            return
        try:
            self.session.post(
                f"{self.comfyui_url}/free",
                json={"unload_models": True, "free_memory": True}, timeout=30,
            )
            logger.info("freed ComfyUI VRAM after TRELLIS.2 generation")
        except requests.RequestException as e:  # noqa: BLE001
            logger.warning("free_vram failed: %s", e)

    def _download_file(self, filename: str, subfolder: str = "") -> bytes:
        for file_type in ("output", "temp"):
            r = self.session.get(
                f"{self.comfyui_url}/view",
                params={"filename": filename, "subfolder": subfolder, "type": file_type},
                timeout=120,
            )
            if r.status_code == 200 and len(r.content) > 0:
                return r.content
        raise FileNotFoundError(f"Cannot download {subfolder}/{filename} from ComfyUI")

    def _extract_glb_refs(self, history: dict) -> list[tuple[str, str]]:
        """Scan ComfyUI history outputs for downloadable GLB references.

        TRELLIS.2's Trellis2ExportTrimesh does not register a /history output, so
        the workflow terminates in a Preview3D node whose ui output carries the
        produced file. This scan is robust to the exact ui key (``3d``, ``gltf``,
        ``result``, ``meshes``, ``text``): it returns (filename, subfolder) pairs
        for anything ending in .glb.
        """
        refs: list[tuple[str, str]] = []
        outputs = history.get("outputs", {})

        def add(fname: str, sub: str = "") -> None:
            if fname and fname.lower().endswith(".glb"):
                refs.append((Path(fname).name, sub or str(Path(fname).parent) if "/" in fname else sub))

        for _node_id, node_output in outputs.items():
            for key, items in node_output.items():
                if not isinstance(items, list):
                    if isinstance(items, str):
                        add(items)
                    continue
                for item in items:
                    if isinstance(item, str):
                        add(item)
                    elif isinstance(item, dict):
                        fn = item.get("filename") or item.get("model_file") or ""
                        add(fn, item.get("subfolder", ""))
        return refs

    def _load_glb(self, data: bytes) -> Optional[trimesh.Trimesh]:
        """Trimesh view of a GLB for stats/placement — NOT for re-export."""
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            scene = trimesh.load(tmp.name, file_type="glb", force="scene")
        if isinstance(scene, trimesh.Scene):
            meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                return None
            return meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)
        if isinstance(scene, trimesh.Trimesh):
            return scene
        return None

    # ------------------------------------------------------------------
    # Workflow construction (ComfyUI executor)
    # ------------------------------------------------------------------

    def _build_prompt(self, uploaded_name: str, seed: int, label: str) -> dict:
        with open(self.workflow_path) as f:
            prompt = json.load(f)
        prompt = {k: v for k, v in prompt.items() if not k.startswith("_")}

        for node in prompt.values():
            ins = node.get("inputs", {})
            if ins.get("image") == _CROP_PLACEHOLDER:
                ins["image"] = uploaded_name

        # Runtime parameters (node ids per trellis2_single_image_pbr.json).
        if "1" in prompt:
            prompt["1"]["inputs"]["resolution"] = self.resolution
        if "40" in prompt:
            prompt["40"]["inputs"].update({
                "seed": seed,
                "ss_sampling_steps": self.ss_steps,
                "shape_sampling_steps": self.shape_steps,
            })
        if "45" in prompt:
            prompt["45"]["inputs"]["target_face_count"] = self.face_count_high
        if "50" in prompt:
            prompt["50"]["inputs"].update({
                "seed": seed, "tex_sampling_steps": self.tex_steps,
            })
        if "60" in prompt:
            prompt["60"]["inputs"]["texture_size"] = self.texture_size
        if "70" in prompt:
            prompt["70"]["inputs"]["filename_prefix"] = f"vitrine_object_{label}"
        return prompt

    # ------------------------------------------------------------------
    # Executors
    # ------------------------------------------------------------------

    def _generate_native(self, image_path: Path, seed: int, label: str) -> Trellis2Result:
        """POST the crop to the native-pipeline service (PRD v4 R5).

        Contract (scripts/trellis2_native_service.py): multipart ``image`` +
        form params; JSON response ``{glb_high_b64, glb_low_b64?, lineage}``.
        """
        t0 = time.monotonic()
        with open(image_path, "rb") as f:
            r = self.session.post(
                f"{self.native_url}/generate",
                files={"image": (image_path.name, f, "image/png")},
                data={
                    "seed": str(seed),
                    "resolution": self.resolution,
                    "texture_size": str(self.texture_size),
                    "ss_steps": str(self.ss_steps),
                    "shape_steps": str(self.shape_steps),
                    "tex_steps": str(self.tex_steps),
                    "face_count_high": str(self.face_count_high),
                    "face_count_low": str(self.face_count_low),
                    "label": label,
                },
                timeout=self.timeout,
            )
        r.raise_for_status()
        payload = r.json()
        result = Trellis2Result(
            backend="trellis2-native-single-image",
            duration_seconds=time.monotonic() - t0,
            lineage=payload.get("lineage", {}),
        )
        if payload.get("glb_high_b64"):
            result.glb_data = base64.b64decode(payload["glb_high_b64"])
            result.mesh = self._load_glb(result.glb_data)
        if payload.get("glb_low_b64"):
            result.glb_low_data = base64.b64decode(payload["glb_low_b64"])
        if result.glb_data is None:
            result.error = payload.get("error", "native service returned no GLB")
        return result

    def _generate_comfyui(self, image_path: Path, seed: int, label: str) -> Trellis2Result:
        """Run the single-image workflow on ComfyUI (interim executor)."""
        t0 = time.monotonic()
        # Begin from a clean GPU (serial lifecycle): a prior stage/run that
        # crashed before its own /free leaves stale models resident.
        self._free_vram()

        uploaded = self._upload_image(image_path)
        prompt = self._build_prompt(uploaded, seed=seed, label=label)
        prompt_id = self._submit_prompt(prompt)
        logger.info("Submitted TRELLIS.2 single-image prompt %s", prompt_id)

        history = self._poll_completion(prompt_id)
        elapsed = time.monotonic() - t0
        logger.info("TRELLIS.2 completed in %.1fs", elapsed)

        result = Trellis2Result(
            backend="trellis2-comfyui-single-image",
            duration_seconds=elapsed,
            prompt_id=prompt_id,
        )
        for fname, sub in self._extract_glb_refs(history):
            try:
                data = self._download_file(fname, sub)
                result.glb_data = data
                result.output_paths[f"{sub}/{fname}" if sub else fname] = fname
                result.mesh = self._load_glb(data)
                if result.mesh is not None:
                    logger.info("Loaded TRELLIS.2 object: %d verts, %d faces",
                                result.vertex_count, result.face_count)
                    break
            except (FileNotFoundError, requests.RequestException) as e:
                logger.warning("Could not download %s/%s: %s", sub, fname, e)

        if result.glb_data is None:
            result.error = "No retrievable GLB in TRELLIS.2 outputs"
            logger.warning("TRELLIS.2: %s (history outputs scanned)", result.error)

        # Serial lifecycle: free the models so the next object has full VRAM.
        self._free_vram()
        return result

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def reconstruct_from_image(
        self,
        image_path: str | Path,
        seed: int | None = None,
        label: str = "object",
        provenance: dict | None = None,
    ) -> Trellis2Result:
        """Generate a PBR-textured object GLB from ONE matted crop.

        ``provenance`` (the object_crops manifest entry) is folded into the
        result lineage so the asset traces back to its source observation.
        Backsides are model-completed (``surface: inferred``); the escalation
        ladder for hero assets is seed re-rolls + an image-edit alternative
        view, per PRD v4 R7 — never synthesized panel sets.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Crop not found: {image_path}")
        seed = self.seed if seed is None else seed
        safe = "".join(c if c.isalnum() else "_" for c in label)[:40] or "object"

        logger.info("TRELLIS.2 single-image generation: %s (%s/%d, seed=%d)",
                    image_path.name, self.resolution, self.texture_size, seed)

        if self.native_url:
            result = self._generate_native(image_path, seed, safe)
        else:
            result = self._generate_comfyui(image_path, seed, safe)

        result.lineage = {
            "conditioning": "single-image",
            "crop": str(image_path),
            "generator": "TRELLIS.2-4B",
            "executor": result.backend,
            "resolution": self.resolution,
            "seed": seed,
            "surface": "observed-front/inferred-back",
            **({"source": provenance} if provenance else {}),
            **result.lineage,
        }
        return result
