"""Vitrine -> Unreal 5.8 USD ingest (ADR-016), run via:
    UnrealEditor-Cmd <proj> -run=pythonscript -script=import_usd_stage.py

HIGHEST-FIDELITY path: load scene.usda as a *live USD Stage Actor* (not a baked
import) so the full prim hierarchy + materials load and the v2g:* lineage
customData is preserved — baked Interchange import silently drops customData
(confirmed UE5.8). We read v2g:* via the pxr Python API (shipped with UE's USD
plugin) and mirror it onto UE Actor tags / asset metadata so Blueprint + the MCP
tools can query lineage.

Env: VITRINE_USD (default /usd_input/scene.usda).
"""
from __future__ import annotations
import os

import unreal


def _usd_path() -> str:
    return os.environ.get("VITRINE_USD", "/usd_input/scene.usda")


def spawn_stage_actor(usd_path: str) -> "unreal.UsdStageActor":
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.UsdStageActor, unreal.Vector(0, 0, 0)
    )
    actor.set_editor_property("root_layer", unreal.FilePath(usd_path))
    unreal.log(f"[vitrine] USD Stage Actor pointed at {usd_path}")
    return actor


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


def mirror_v2g_metadata(usd_path: str, actor: "unreal.UsdStageActor") -> int:
    """Read v2g:* customData from each prim via pxr and stamp it onto the live
    Stage Actor as actor tags (queryable from MCP/Blueprint) in the form
    ``v2g:<primName>:<key>=<value>``. Returns the count of prims carrying v2g
    metadata. Best-effort: pxr ships inside UE's USD plugin; if absent we skip
    rather than fail."""
    try:
        from pxr import Usd
    except ImportError:
        unreal.log_warning("[vitrine] pxr unavailable — skipping v2g:* mirror")
        return 0

    stage = Usd.Stage.Open(usd_path)
    if stage is None:
        unreal.log_warning(f"[vitrine] could not open USD stage {usd_path}")
        return 0

    tags = []
    tagged = 0
    for prim in stage.Traverse():
        v2g = _extract_v2g(prim.GetCustomData() or {})
        if not v2g:
            continue
        tagged += 1
        name = prim.GetName()
        unreal.log(f"[vitrine] {prim.GetPath()} v2g={v2g}")
        for k, v in v2g.items():
            tags.append(unreal.Name(f"v2g:{name}:{k}={v}"))

    if tags and actor is not None:
        try:
            existing = list(actor.tags)
            actor.set_editor_property("tags", existing + tags)
            unreal.log(f"[vitrine] stamped {len(tags)} v2g tag(s) onto the Stage Actor")
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning(f"[vitrine] could not set actor tags: {exc}")

    unreal.log(f"[vitrine] {tagged} prim(s) carry v2g:* customData")
    return tagged


def main() -> None:
    usd = _usd_path()
    if not os.path.exists(usd):
        unreal.log_error(f"[vitrine] USD not found: {usd}")
        return
    actor = spawn_stage_actor(usd)
    mirror_v2g_metadata(usd, actor)
    unreal.log("[vitrine] USD stage ingest complete; MCP (:8000) + RC (:30010) live")


if __name__ == "__main__":
    main()
