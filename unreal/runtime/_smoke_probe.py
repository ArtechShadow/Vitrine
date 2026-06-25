# Vitrine UE 5.8 boot probe (nullrhi). Validates, in order:
#   1. UnrealEditor-Cmd boots against the bind-mounted engine + loads the project
#   2. the embedded `unreal` python runtime works
#   3. `pxr` (UE USD plugin) imports and can open our scene.usda
#   4. the scene carries our v2g:* lineage (count prims + v2g-tagged prims)
#   5. a live UsdStageActor can be spawned (the highest-fidelity import path)
# Run: UnrealEditor-Cmd <proj> -run=pythonscript -script=_smoke_probe.py -nullrhi
import os
import sys


def main():
    try:
        import unreal
    except ImportError:
        print("[probe] FATAL: 'unreal' module unavailable (not in UE runtime)", file=sys.stderr)
        sys.exit(3)

    unreal.log("[probe] ===== Vitrine UE 5.8 boot probe START =====")
    unreal.log(f"[probe] unreal python OK; engine={unreal.SystemLibrary.get_engine_version()}")

    usd = os.environ.get("VITRINE_USD", "/usd_input/scene.usda")
    unreal.log(f"[probe] VITRINE_USD={usd} exists={os.path.isfile(usd)}")

    # --- pxr + USD read (v2g:* lineage) ---
    v2g_prims = 0
    total_prims = 0
    try:
        from pxr import Usd
        stage = Usd.Stage.Open(usd) if os.path.isfile(usd) else None
        if stage is None:
            unreal.log_error(f"[probe] pxr could not open stage at {usd}")
        else:
            for prim in stage.Traverse():
                total_prims += 1
                # v2g lineage is a NESTED dict (written via SetCustomDataByKey
                # ("v2g:..."), which pxr stores as customData["v2g"][subkey]).
                cd = prim.GetCustomData() or {}
                nested = cd.get("v2g")
                v2g = dict(nested) if isinstance(nested, dict) else {}
                v2g.update({str(k).split(":", 1)[1]: v
                            for k, v in cd.items() if str(k).startswith("v2g:")})
                if v2g:
                    v2g_prims += 1
                    unreal.log(f"[probe]   v2g prim {prim.GetPath()}: {sorted(v2g.keys())}")
            unreal.log(f"[probe] pxr OK: {total_prims} prims, {v2g_prims} carry v2g:*")
    except Exception as exc:  # noqa: BLE001
        unreal.log_error(f"[probe] pxr/USD step FAILED: {exc}")

    # --- live UsdStageActor spawn (best-effort; isolates headless-world issues) ---
    stage_actor_ok = False
    try:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.UsdStageActor, unreal.Vector(0, 0, 0)
        )
        actor.set_editor_property("root_layer", unreal.FilePath(usd))
        stage_actor_ok = True
        unreal.log("[probe] UsdStageActor spawned + root_layer set OK")
    except Exception as exc:  # noqa: BLE001
        unreal.log_warning(f"[probe] UsdStageActor spawn failed: {exc}")

    unreal.log(
        f"[probe] RESULT usd_exists={os.path.isfile(usd)} prims={total_prims} "
        f"v2g_prims={v2g_prims} stage_actor={stage_actor_ok}"
    )
    unreal.log("[probe] ===== Vitrine UE 5.8 boot probe END =====")


if __name__ == "__main__":
    main()
