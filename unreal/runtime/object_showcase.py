#!/usr/bin/env python3
"""Object showcase: the reconstructed textured game-asset objects, lined up in a clean
UE level, normalised to a uniform size and well-framed. Reuses the already-imported
/Game/Vitrine/Final/Obj_<name> assets (no re-import → no import hang). Robust to the
flaky get_actor_bounds (retries; falls back to a default scale).

  python3 object_showcase.py [out_png]   (in vitrine-unreal)
"""
import sys, os, json, base64, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umcp

SID = umcp.session()
SC = "editor_toolset.toolsets.scene.SceneTools"
ACT = "editor_toolset.toolsets.actor.ActorTools"
APP = "EditorToolset.EditorAppToolset"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/renders/dreamlab/ue_objects_showcase.png"
OBJS = ["chair", "vacuum_cleaner", "dartboard", "ladder", "mitre_saw", "toolbox"]
TARGET = 120.0  # uniform showcase size (cm)


def T(ts, t, a): return umcp.call_tool(ts, t, a, SID)
def ret(o):
    try: d = json.loads(o["result"]["content"][0]["text"])
    except Exception: return None
    return d.get("returnValue", d) if isinstance(d, dict) else d


def clean():
    T(SC, "load_level", {"level_path": "/Engine/Maps/Templates/Template_Default"})
    fa = T(SC, "find_actors", {"name": "", "tag": "", "actor_type": {"refPath": "/Script/Engine.Actor"},
           "root": None, "bounds": None, "collision_channels": []})
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        if ref.split(".")[-1].startswith(("Floor", "StaticMeshActor")):
            try: T(SC, "remove_from_scene", {"actor": {"refPath": ref}})
            except Exception: pass


def max_extent(ref):
    for _ in range(6):
        b = ret(T(ACT, "get_actor_bounds", {"actor": {"refPath": ref}}))
        if isinstance(b, dict) and "min" in b:
            mn, mx = b["min"], b["max"]
            return max(mx["x"] - mn["x"], mx["y"] - mn["y"], mx["z"] - mn["z"])
        time.sleep(1)
    return None


def xf(loc, s, yaw=0): return {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
    "rotation": {"pitch": 0, "yaw": yaw, "roll": 0}, "scale": {"x": s, "y": s, "z": s}}


def main():
    clean()
    present = []
    for name in OBJS:
        asset = f"/Game/Vitrine/Final/Obj_{name}.Obj_{name}"
        actor = ret(T(SC, "add_to_scene_from_asset", {"asset_path": asset, "name": "Show_" + name,
                     "xform": xf([0, 0, 0], 1), "parent": None, "snap_to_ground": False}))
        if not actor or (isinstance(actor, str) and "Persistent" not in actor and "refPath" not in str(actor)):
            print("  no asset", name); continue
        aref = actor.get("refPath") if isinstance(actor, dict) else actor
        present.append((name, aref))
    n = len(present); print("placing", n, "objects:", [p[0] for p in present], flush=True)
    for i, (name, aref) in enumerate(present):
        ext = max_extent(aref)
        s = (TARGET / ext) if ext else 80.0
        x = (i - (n - 1) / 2.0) * 200.0
        try:
            T(ACT, "set_actor_transform", {"actor": {"refPath": aref},
              "xform": xf([x, 0, TARGET / 2], s), "worldspace": True})
            print(f"  [{name}] ext={ext} scale={s:.1f} x={x:.0f}", flush=True)
        except Exception as e:
            print("  place fail", name, str(e)[:80], flush=True)
    # frame the row head-on, slightly above
    span = max(300.0, n * 200.0)
    loc = [0, -span * 0.9, TARGET * 1.1]; look = [0, 0, TARGET / 2]
    fwd = [look[i] - loc[i] for i in range(3)]; nn = math.sqrt(sum(c * c for c in fwd)) or 1
    fwd = [c / nn for c in fwd]
    x = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
         "rotation": {"pitch": math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1]))),
                      "yaw": math.degrees(math.atan2(fwd[1], fwd[0])), "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}
    T(APP, "SelectActors", {"actors": []})
    T(APP, "SetCameraTransform", {"transform": x})
    anno = {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0, "maxLabelDistance": 0,
            "classFilter": None, "maxLabels": 0}
    c = T(APP, "CaptureViewport", {"captureTransform": x, "annotations": anno, "bShowUI": False})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for it in c.get("result", {}).get("content", []):
        if it.get("type") == "image": open(OUT, "wb").write(base64.b64decode(it["data"])); print("saved", OUT); break
        if it.get("type") == "text":
            try: open(OUT, "wb").write(base64.b64decode(json.loads(it["text"])["returnValue"]["image"]["data"])); print("saved", OUT); break
            except Exception: pass
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
