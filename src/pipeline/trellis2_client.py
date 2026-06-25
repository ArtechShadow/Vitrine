# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""TRELLIS.2-4B client for image-to-3D hull reconstruction via ComfyUI.

TRELLIS.2 is the ADR-015 designated-primary hull backend (MIT, full PBR). This
client mirrors the Hunyuan3D client's plumbing: it renders 4 canonical views
(front/left/back/right) from a per-object Gaussian PLY, feeds them through the
ComfyUI-TRELLIS2 multiview pipeline (DINOv3 conditioning -> shape diffusion ->
PBR texture diffusion -> rasterize), and returns a textured GLB.

Runtime-verified 2026-06-20 (produces geometry + PBR-textured GLBs). The node's
CUDA extensions, DINOv3 weights, and the RasterizePBR cv2 patch are installed by
``scripts/comfyui_entrypoint.sh``; see ``research/decisions/adr-015-...md`` and
``docs/engineering-log.md``.

Usage::

    from pipeline.trellis2_client import Trellis2Client
    client = Trellis2Client(comfyui_url="http://vitrine-comfyui:8188")
    result = client.reconstruct_from_gaussians("object.ply")
    result.mesh.export("hull.glb")
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests
import trimesh

from .multiview_renderer import MultiViewRenderer, RenderConfig

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).parent / "workflows"
TRELLIS2_MV_WORKFLOW = WORKFLOW_DIR / "trellis2_multiview_pbr.json"

# Placeholder tokens substituted in the workflow template (cf. the JSON). The
# full-360 panel set: equatorial front/left/back/right + top/bottom caps, mapped
# to Trellis2MultiViewImageToShape's named slots so the whole object surface
# (incl. top face + underside) is reconstructed, not just the front.
_VIEW_PLACEHOLDERS = {
    "front": "FRONT_IMAGE_PLACEHOLDER",
    "left": "LEFT_IMAGE_PLACEHOLDER",
    "back": "BACK_IMAGE_PLACEHOLDER",
    "right": "RIGHT_IMAGE_PLACEHOLDER",
    "top": "TOP_IMAGE_PLACEHOLDER",
    "bottom": "BOTTOM_IMAGE_PLACEHOLDER",
}


@dataclass
class Trellis2Result:
    """Result of a TRELLIS.2 hull reconstruction."""
    mesh: Optional[trimesh.Trimesh] = None
    glb_data: Optional[bytes] = None
    backend: str = "trellis2-4b-mv-pbr"
    views_rendered: int = 0
    duration_seconds: float = 0.0
    prompt_id: str = ""
    output_paths: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

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
    """Client for TRELLIS.2-4B hull generation via the ComfyUI-TRELLIS2 nodes.

    Parameters
    ----------
    comfyui_url : str
        Native ComfyUI URL (e.g. ``http://vitrine-comfyui:8188``).
    timeout : int
        Maximum seconds to wait for a generation (TRELLIS.2 + texture is slow;
        time-to-output is not a constraint on the reference host).
    poll_interval : float
        Seconds between history polls.
    resolution : str
        ``LoadTrellis2Models`` resolution: ``512`` | ``1024`` | ``1024_cascade``
        | ``1536_cascade`` (max fidelity, default).
    texture_size : int
        PBR rasterize texture resolution (default 4096).
    seed : int
        Generation seed.
    """

    def __init__(
        self,
        comfyui_url: str = "http://vitrine-comfyui:8188",
        timeout: int = 1800,
        poll_interval: float = 2.0,
        resolution: str = "1536_cascade",
        texture_size: int = 4096,
        seed: int = 42,
        render_size: int = 512,
        camera_distance: float = 2.5,
        workflow_path: str | Path | None = None,
    ):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.resolution = resolution
        self.texture_size = texture_size
        self.seed = seed
        self.render_size = render_size
        self.camera_distance = camera_distance
        self.workflow_path = Path(workflow_path) if workflow_path else TRELLIS2_MV_WORKFLOW
        self.session = requests.Session()
        self._renderer: MultiViewRenderer | None = None
        # Optional generative view completion (ADR-017): fills unobserved panels
        # via FLUX.2 before hull reconstruction. Set by stages.py when enabled.
        self.view_completer: Any = None

    @classmethod
    def from_config(cls, cfg: Any) -> "Trellis2Client":
        """Construct from a Trellis2Config, reading every field defensively."""
        return cls(
            comfyui_url=getattr(cfg, "comfyui_url", "http://vitrine-comfyui:8188"),
            timeout=getattr(cfg, "timeout", 1800),
            resolution=getattr(cfg, "resolution", "1536_cascade"),
            texture_size=getattr(cfg, "texture_size", 4096),
            seed=getattr(cfg, "seed", 42),
            render_size=getattr(cfg, "render_size", 512),
            camera_distance=getattr(cfg, "camera_distance", 2.5),
        )

    # ------------------------------------------------------------------
    # ComfyUI interaction (native API)
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
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
        Called after the hull so TRELLIS.2 (~24GB) is unloaded before the next
        object — and so a preceding FLUX.2 view-completion stage (~51GB) cannot
        co-reside with the hull on a single 48GB GPU. With 2x48GB the generative
        and hull stages can instead be split across GPUs (a 2nd ComfyUI on GPU1);
        this /free is the single-instance safety net. Best-effort, never raises."""
        try:
            self.session.post(
                f"{self.comfyui_url}/free",
                json={"unload_models": True, "free_memory": True}, timeout=30,
            )
            logger.info("freed ComfyUI VRAM after TRELLIS.2 hull")
        except requests.RequestException as e:  # noqa: BLE001
            logger.warning("free_vram after hull failed: %s", e)

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
    # Rendering + workflow construction
    # ------------------------------------------------------------------

    def _get_renderer(self) -> MultiViewRenderer:
        if self._renderer is None:
            self._renderer = MultiViewRenderer(RenderConfig(
                image_size=self.render_size,
                num_views=6,
                azimuth_preset="trellis_6",   # full-360: F/L/B/R + top + bottom caps
                fov_deg=49.13,
                camera_distance=self.camera_distance,
                sh_degree=3,
                center_object=True,
                scale_to_unit=True,
            ))
        return self._renderer

    def _render_and_save_views(self, ply_path: Path, work_dir: Path) -> dict[str, Path]:
        renderer = self._get_renderer()
        views = renderer.render(ply_path, output_dir=work_dir)
        view_map: dict[str, Path] = {}
        for v in views:
            label = v.camera.label
            if label in _VIEW_PLACEHOLDERS:
                view_map[label] = work_dir / f"{label}.png"
        # Backfill any missing view with the front view (TRELLIS tolerates fewer views).
        front = view_map.get("front")
        if front is None and views:
            front = work_dir / f"{views[0].camera.name}.png"
        for label in _VIEW_PLACEHOLDERS:
            if label not in view_map and front is not None:
                view_map[label] = front
        return view_map

    def _build_prompt(self, uploaded: dict[str, str], seed: int, label: str) -> dict:
        with open(self.workflow_path) as f:
            prompt = json.load(f)
        prompt = {k: v for k, v in prompt.items() if not k.startswith("_")}

        # Substitute the per-view uploaded filenames into the LoadImage nodes.
        for node in prompt.values():
            ins = node.get("inputs", {})
            for view, token in _VIEW_PLACEHOLDERS.items():
                if ins.get("image") == token:
                    ins["image"] = uploaded[view]

        # Apply runtime parameters defensively (node ids per trellis2_multiview_pbr.json).
        if "1" in prompt:
            prompt["1"]["inputs"]["resolution"] = self.resolution
        for nid in ("40", "50", "60"):
            if nid in prompt and "seed" in prompt[nid]["inputs"]:
                prompt[nid]["inputs"]["seed"] = seed
        if "60" in prompt and "texture_size" in prompt["60"]["inputs"]:
            prompt["60"]["inputs"]["texture_size"] = self.texture_size
        if "70" in prompt:
            prompt["70"]["inputs"]["filename_prefix"] = f"vitrine_hull_{label}"
        return prompt

    # ------------------------------------------------------------------
    # Public reconstruction entry point
    # ------------------------------------------------------------------

    def reconstruct_from_gaussians(
        self,
        ply_path: str | Path,
        seed: int | None = None,
        work_dir: str | Path | None = None,
        label: str = "object",
        object_desc: dict | None = None,
    ) -> Trellis2Result:
        """Reconstruct a textured hull GLB from a per-object Gaussian PLY.

        When ``view_completer`` is set (ADR-017), unobserved panels (the splat
        lacked that side) are generatively completed via FLUX.2 before the hull
        is built, so a partial capture still yields a full-360 reconstruction.
        """
        ply_path = Path(ply_path)
        if not ply_path.exists():
            raise FileNotFoundError(f"PLY not found: {ply_path}")
        seed = self.seed if seed is None else seed
        safe = "".join(c if c.isalnum() else "_" for c in label)[:40] or "object"

        t0 = time.monotonic()
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="trellis2_"))
        else:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)

        logger.info("TRELLIS.2 hull reconstruction: %s (%s/%d)",
                    ply_path.name, self.resolution, self.texture_size)
        # Begin from a clean GPU (serial lifecycle): a prior stage/run that
        # crashed or was killed before its own /free leaves stale models
        # resident, which OOMs this run. Freeing up front makes the stage robust
        # to upstream leakage, not just to its own cleanup.
        self._free_vram()
        view_paths = self._render_and_save_views(ply_path, work_dir)

        # ADR-017: generatively complete unobserved panels (coverage-gated) so a
        # partial capture still reconstructs a full 360. Best-effort — on any
        # failure (e.g. FLUX.2 not staged) fall back to the raw splat renders.
        if self.view_completer is not None:
            try:
                vc = self.view_completer.complete(
                    view_paths, object_desc=object_desc or {"label": label},
                    work_dir=work_dir / "completed", size=self.render_size,
                )
                view_paths = vc.views
                if vc.synthesised:
                    logger.info("View completion: synthesised %s; kept %s",
                                vc.synthesised, vc.kept)
            except Exception as e:  # noqa: BLE001
                logger.warning("View completion failed (%s); using raw renders", e)

        uploaded = {name: self._upload_image(p) for name, p in view_paths.items()}

        prompt = self._build_prompt(uploaded, seed=seed, label=safe)
        prompt_id = self._submit_prompt(prompt)
        logger.info("Submitted TRELLIS.2 prompt %s", prompt_id)

        history = self._poll_completion(prompt_id)
        elapsed = time.monotonic() - t0
        logger.info("TRELLIS.2 completed in %.1fs", elapsed)

        result = Trellis2Result(
            views_rendered=len(view_paths),
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
                    logger.info("Loaded TRELLIS.2 hull: %d verts, %d faces",
                                result.vertex_count, result.face_count)
                    break
            except (FileNotFoundError, requests.RequestException) as e:
                logger.warning("Could not download %s/%s: %s", sub, fname, e)

        if result.mesh is None:
            result.error = "No retrievable GLB in TRELLIS.2 outputs"
            logger.warning("TRELLIS.2: %s (history outputs scanned)", result.error)

        # Serial lifecycle: free the hull models so the next object (or stage)
        # has full VRAM headroom. The view-completer already freed FLUX.2.
        self._free_vram()
        return result
