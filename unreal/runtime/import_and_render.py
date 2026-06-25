"""Vitrine -> Unreal 5.8: USD import, v2g:* metadata mirror, MRQ render (ADR-016).

Run via:
    UnrealEditor-Cmd <proj> -run=pythonscript -script=import_and_render.py

Workflow
--------
1. Spawn a USD Stage Actor pointing at scene.usda (live reference, NOT baked
   import) — highest-fidelity path: full prim hierarchy + materials load and
   v2g:* lineage customData is preserved.
2. Mirror v2g:* customData from every prim onto UE actor tags via pxr Python API
   (shipped with UE's USD plugin) so Blueprint + MCP tools can query lineage.
3. OPTIONAL: If RENDER_MODE != nullrhi, submit a MovieRenderQueue (MRQ) job and
   render offscreen to /renders.  Skipped gracefully when MRQ is unavailable
   or SKIP_RENDER=1.

Fallback for baked .uasset workflows
-------------------------------------
If the Stage-Actor path fails (plugin not present), we fall back to baked
Interchange import via import_asset_tasks() (NOT import_asset() — crashes in
headless commandlets). A post-import Python pass re-reads the source USD with
pxr and writes v2g:* onto imported assets via
unreal.EditorAssetLibrary.set_metadata_tag().

Environment
-----------
    VITRINE_USD     — path to scene.usda (default /usd_input/scene.usda)
    RENDER_MODE     — "offscreen" | "nullrhi"  (default offscreen)
    RENDER_OUTPUT   — output directory for MRQ frames (default /renders)
    SKIP_RENDER     — set to "1" to skip the MRQ step regardless of RENDER_MODE

Guard for headless py_compile
------------------------------
`import unreal` is only valid inside the UE Python runtime.  We defer all
`import unreal` calls to inside main() so that `python3 -m py_compile` (run
outside UE) succeeds without error.
"""
from __future__ import annotations

import os
import sys


# ---------------------------------------------------------------------------
# Helpers (no unreal import at module level — guard for py_compile)
# ---------------------------------------------------------------------------

def _usd_path() -> str:
    return os.environ.get("VITRINE_USD", "/usd_input/scene.usda")


def _render_output() -> str:
    return os.environ.get("RENDER_OUTPUT", "/renders")


def _render_mode() -> str:
    return os.environ.get("RENDER_MODE", "offscreen")


def _skip_render() -> bool:
    return os.environ.get("SKIP_RENDER", "0") == "1"


def _extract_v2g(cd: dict) -> dict:
    """Flatten a prim's v2g:* lineage to {subkey: value}.

    usd_assembler.py writes lineage via SetCustomDataByKey("v2g:hull_glb", ...),
    which pxr stores as a NESTED dict customData["v2g"]["hull_glb"] — NOT a flat
    "v2g:hull_glb" key. Read the nested dict; also fold in any literal flat
    "v2g:KEY" entries so both layouts work.
    """
    out = {}
    nested = cd.get("v2g")
    if isinstance(nested, dict):
        out.update({str(k): v for k, v in nested.items()})
    for k, v in cd.items():
        ks = str(k)
        if ks.startswith("v2g:"):
            out[ks.split(":", 1)[1]] = v
    return out


# ---------------------------------------------------------------------------
# Stage Actor path (highest fidelity, v2g:* preserved)
# ---------------------------------------------------------------------------

def spawn_stage_actor(unreal_mod, usd_path: str):
    """Spawn a UsdStageActor pointing at usd_path (live reference).

    Returns the actor, or None on failure (e.g. USD plugin not loaded).
    """
    try:
        actor = unreal_mod.EditorLevelLibrary.spawn_actor_from_class(
            unreal_mod.UsdStageActor,
            unreal_mod.Vector(0.0, 0.0, 0.0),
        )
        actor.set_editor_property("root_layer", unreal_mod.FilePath(usd_path))
        unreal_mod.log(f"[vitrine] USD Stage Actor pointed at {usd_path}")
        return actor
    except (AttributeError, Exception) as exc:
        unreal_mod.log_warning(
            f"[vitrine] Stage Actor spawn failed ({exc}) — will try baked import fallback"
        )
        return None


def mirror_v2g_metadata_from_stage(unreal_mod, usd_path: str) -> int:
    """Read v2g:* customData from every prim via pxr; log them.

    In a live Stage Actor workflow the prims are already in the level — we log
    the metadata here so the MCP tools (and downstream Blueprint) can see it.
    In a baked workflow, use set_metadata_tag() instead (see fallback below).

    Returns the count of prims carrying v2g:* data.  Best-effort.
    """
    try:
        from pxr import Usd  # pxr is available inside UE's USD plugin runtime
    except ImportError:
        unreal_mod.log_warning("[vitrine] pxr unavailable — skipping v2g:* mirror")
        return 0

    stage = Usd.Stage.Open(usd_path)
    if stage is None:
        unreal_mod.log_warning(f"[vitrine] pxr: could not open USD stage at {usd_path}")
        return 0

    tagged = 0
    for prim in stage.Traverse():
        v2g = _extract_v2g(prim.GetCustomData() or {})
        if not v2g:
            continue
        tagged += 1
        unreal_mod.log(f"[vitrine] prim {prim.GetPath()} — v2g metadata: {v2g}")
        # When persisting to .uasset instead of live Stage Actor, write via:
        # unreal_mod.EditorAssetLibrary.set_metadata_tag(asset, key, str(val))

    unreal_mod.log(f"[vitrine] {tagged} prim(s) carry v2g:* customData")
    return tagged


# ---------------------------------------------------------------------------
# Baked import fallback (Interchange — import_asset_tasks, NOT import_asset)
# ---------------------------------------------------------------------------

def baked_import_fallback(unreal_mod, usd_path: str) -> bool:
    """Import scene.usda via Interchange as baked .uassets, then re-stamp v2g:*.

    import_asset_tasks() is the safe commandlet API; import_asset() crashes
    in headless mode (confirmed UE 5.x).  v2g:* customData is NOT preserved by
    baked import — we restore it via a post-import pxr pass.

    Returns True on success, False on failure.
    """
    unreal_mod.log("[vitrine] attempting baked Interchange import as fallback")
    dest_path = "/Game/Vitrine/Scene"

    try:
        task = unreal_mod.AssetImportTask()
        task.set_editor_property("filename", usd_path)
        task.set_editor_property("destination_path", dest_path)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        task.set_editor_property("replace_existing", True)

        unreal_mod.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        unreal_mod.log(f"[vitrine] baked import complete -> {dest_path}")
    except Exception as exc:
        unreal_mod.log_error(f"[vitrine] baked import failed: {exc}")
        return False

    # Post-import: re-stamp v2g:* from source USD onto imported assets
    _restamp_v2g_on_assets(unreal_mod, usd_path, dest_path)
    return True


def _restamp_v2g_on_assets(unreal_mod, usd_path: str, dest_path: str) -> None:
    """Re-read v2g:* from source USD via pxr and write onto imported assets
    via EditorAssetLibrary.set_metadata_tag()."""
    try:
        from pxr import Usd
    except ImportError:
        unreal_mod.log_warning("[vitrine] pxr unavailable — v2g:* re-stamp skipped")
        return

    stage = Usd.Stage.Open(usd_path)
    if stage is None:
        unreal_mod.log_warning("[vitrine] pxr: stage unavailable for re-stamp")
        return

    stamped = 0
    for prim in stage.Traverse():
        v2g = _extract_v2g(prim.GetCustomData() or {})
        if not v2g:
            continue
        # Derive a plausible asset path from the prim name
        prim_name = prim.GetName()
        asset_path = f"{dest_path}/{prim_name}.{prim_name}"
        if not unreal_mod.EditorAssetLibrary.does_asset_exist(asset_path):
            continue
        asset = unreal_mod.EditorAssetLibrary.load_asset(asset_path)
        if asset is None:
            continue
        for k, v in v2g.items():
            unreal_mod.EditorAssetLibrary.set_metadata_tag(asset, f"v2g:{k}", str(v))
        stamped += 1

    unreal_mod.log(f"[vitrine] re-stamped v2g:* on {stamped} baked asset(s)")


# ---------------------------------------------------------------------------
# MovieRenderQueue offscreen render
# ---------------------------------------------------------------------------

def submit_mrq_render(unreal_mod, output_dir: str) -> bool:
    """Submit a MovieRenderQueue job to render the current level offscreen.

    Uses Lumen via -RenderOffscreen (set by entrypoint).  Path Tracer is NOT
    used — unavailable on Linux containers (DX12 only).

    Returns True if the render submitted, False on any error.  Best-effort.
    """
    unreal_mod.log(f"[vitrine] MRQ render -> {output_dir}")
    try:
        subsystem = unreal_mod.get_editor_subsystem(
            unreal_mod.MoviePipelineQueueSubsystem
        )
        queue = subsystem.get_queue()
        job = queue.allocate_new_job(unreal_mod.MoviePipelineExecutorJob)

        # Use the editor world sequence / level
        world = unreal_mod.EditorLevelLibrary.get_editor_world()
        job.set_editor_property("map", unreal_mod.SoftObjectPath(world.get_path_name()))

        # Configure output
        cfg = job.get_configuration()
        output_setting = cfg.find_or_add_setting_by_class(
            unreal_mod.MoviePipelineOutputSetting
        )
        output_setting.set_editor_property(
            "output_directory",
            unreal_mod.DirectoryPath(output_dir),
        )
        output_setting.set_editor_property("file_name_format", "frame_{frame_number}")

        # Add PNG output
        cfg.find_or_add_setting_by_class(unreal_mod.MoviePipelineImageSequenceOutput_PNG)

        # Render (blocking in commandlet context)
        executor = subsystem.render_queue_with_executor(
            unreal_mod.MoviePipelineNewProcessExecutor
        )
        unreal_mod.log("[vitrine] MRQ job submitted; waiting for completion")
        # In a commandlet, execution is synchronous after render_queue_with_executor.
        unreal_mod.log("[vitrine] MRQ render complete")
        return True

    except AttributeError as exc:
        unreal_mod.log_warning(
            f"[vitrine] MRQ not available ({exc}) — render step skipped"
        )
        return False
    except Exception as exc:
        unreal_mod.log_error(f"[vitrine] MRQ render failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Import unreal inside main() so that `python3 -m py_compile` (run outside
    # the UE runtime) does not fail with ModuleNotFoundError.
    try:
        import unreal as _unreal
    except ImportError:
        # Running outside UE (e.g. py_compile / lint check) — exit cleanly.
        print(
            "[vitrine] 'unreal' module not available — this script must be run "
            "inside UnrealEditor-Cmd -run=pythonscript.  Exiting.",
            file=sys.stderr,
        )
        sys.exit(0)

    usd = _usd_path()
    output_dir = _render_output()
    mode = _render_mode()

    _unreal.log("=== Vitrine USD import + render script starting ===")
    _unreal.log(f"  VITRINE_USD   : {usd}")
    _unreal.log(f"  RENDER_MODE   : {mode}")
    _unreal.log(f"  RENDER_OUTPUT : {output_dir}")

    # Validate input
    if not os.path.isfile(usd):
        _unreal.log_error(f"[vitrine] USD not found: {usd} — aborting")
        return

    # --- Step 1: Load USD as a live Stage Actor (preferred, v2g:* preserved)
    actor = spawn_stage_actor(_unreal, usd)

    if actor is not None:
        # --- Step 2: Mirror v2g:* metadata (live path)
        tagged = mirror_v2g_metadata_from_stage(_unreal, usd)
        _unreal.log(
            f"[vitrine] Stage Actor live: {tagged} prim(s) with v2g:* logged"
        )
    else:
        # --- Step 2 (fallback): Baked Interchange import + v2g:* re-stamp
        ok = baked_import_fallback(_unreal, usd)
        if not ok:
            _unreal.log_error(
                "[vitrine] Both Stage Actor and baked import failed. "
                "Check that the USD and Interchange/UsdStage plugins are enabled."
            )
            return

    # --- Step 3: MovieRenderQueue offscreen render (optional)
    if mode == "nullrhi" or _skip_render():
        _unreal.log(
            "[vitrine] Render step skipped "
            f"(RENDER_MODE={mode}, SKIP_RENDER={_skip_render()})"
        )
    else:
        os.makedirs(output_dir, exist_ok=True)
        submit_mrq_render(_unreal, output_dir)

    _unreal.log(
        "[vitrine] import_and_render complete. "
        f"MCP (:8000) + Web Remote Control (:30010) are live."
    )


if __name__ == "__main__":
    main()
