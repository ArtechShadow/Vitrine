#!/usr/bin/env python3
"""Capture the CURRENTLY-ASSEMBLED UE scene from several angles WITHOUT re-importing
(the assets/actors are already in the live editor). Diagnostic for the assembly run that
placed room+objects but exited before capturing. Also reports each placed actor's bounds
so we can see true sizes and whether get_actor_bounds works at all.

  python3 ue_capture_only.py <out_dir>
Runs in vitrine-unreal (127.0.0.1:8000)."""
import sys, os, json, base64, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/tmp")
import umcp

SID = umcp.session()
SCENE_T = "editor_toolset.toolsets.scene.SceneTools"
ACT_T = "editor_toolset.toolsets.actor.ActorTools"
APP = "EditorToolset.EditorAppToolset"
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else "/renders/dreamlab"


def T(ts, tool, args): return umcp.call_tool(ts, tool, args, SID)
def ret(o):
    try: d = json.loads(o["result"]["content"][0]["text"])
    except Exception: return None
    return d.get("returnValue", d) if isinstance(d, dict) else d


def list_actors():
    fa = T(SCENE_T, "find_actors", {"name": "", "tag": "",
          "actor_type": {"refPath": "/Script/Engine.Actor"},
          "root": None, "bounds": None, "collision_channels": []})
    out = []
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        short = ref.split(".")[-1] if isinstance(ref, str) else str(ref)
        if any(k in short for k in ("Obj_", "Dreamlab", "Room")):
            b = ret(T(ACT_T, "get_actor_bounds", {"actor": {"refPath": ref}}))
            out.append((short, ref, b))
    return out


def cap(loc, look, name):
    fwd = [look[i] - loc[i] for i in range(3)]; n = math.sqrt(sum(c * c for c in fwd)) or 1
    fwd = [c / n for c in fwd]
    x = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
         "rotation": {"pitch": math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1]))),
                      "yaw": math.degrees(math.atan2(fwd[1], fwd[0])), "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}
    T(APP, "SelectActors", {"actors": []})
    T(APP, "SetCameraTransform", {"transform": x})
    anno = {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0, "maxLabelDistance": 0,
            "classFilter": None, "maxLabels": 0}
    c = T(APP, "CaptureViewport", {"captureTransform": x, "annotations": anno, "bShowUI": False})
    out = os.path.join(OUTDIR, name)
    os.makedirs(OUTDIR, exist_ok=True)
    for it in c.get("result", {}).get("content", []):
        if it.get("type") == "image":
            open(out, "wb").write(base64.b64decode(it["data"])); return "saved " + out
        if it.get("type") == "text":
            try:
                open(out, "wb").write(base64.b64decode(json.loads(it["text"])["returnValue"]["image"]["data"]))
                return "saved " + out
            except Exception: pass
    return "no image for " + name


def main():
    print("session", SID[:24] if SID else None, flush=True)
    acts = list_actors()
    print(f"=== {len(acts)} scene actors ===", flush=True)
    for short, ref, b in acts:
        if isinstance(b, dict) and "min" in b:
            mn, mx = b["min"], b["max"]
            ext = [round(mx["x"] - mn["x"], 1), round(mx["y"] - mn["y"], 1), round(mx["z"] - mn["z"], 1)]
            ctr = [round((mx[k] + mn[k]) / 2, 1) for k in ("x", "y", "z")]
            print(f"  {short:28s} ext_cm={ext} center={ctr}", flush=True)
        else:
            print(f"  {short:28s} bounds={str(b)[:70]}", flush=True)
    # three views of the room
    print(cap([700, 600, 400], [-100, -80, 90], "ue_come_overview.png"), flush=True)
    print(cap([0, -750, 300], [0, 0, 80], "ue_come_front.png"), flush=True)
    print(cap([550, -550, 350], [0, 0, 80], "ue_come_corner.png"), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
