#!/usr/bin/env python3
"""Capture a clean, well-framed still of the assembled dreamlab room: deselect all
(remove the gizmo), optionally enter PIE/game-view (hide editor billboards), frame
from the room's real bounds. Writes /renders/dreamlab/<out>.png."""
import sys, os, json, base64, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/tmp")
import umcp

SID = umcp.session()
APP = "EditorToolset.EditorAppToolset"
SCENE_T = "editor_toolset.toolsets.scene.SceneTools"
ACTOR_T = "editor_toolset.toolsets.actor.ActorTools"
RENDERS = "/renders/dreamlab"
out_name = sys.argv[1] if len(sys.argv) > 1 else "ue_room_clean"
# optional camera override: cx cy cz  lx ly lz
OVER = [float(x) for x in sys.argv[2:8]] if len(sys.argv) >= 8 else None


def ret(o):
    txt = o["result"]["content"][0]["text"]
    try:
        d = json.loads(txt)
    except Exception:
        return txt
    return d.get("returnValue", d) if isinstance(d, dict) else d


def find_room():
    fa = umcp.call_tool(SCENE_T, "find_actors",
        {"name": "DreamlabRoom", "tag": "", "actor_type": {"refPath": "/Script/Engine.Actor"},
         "root": None, "bounds": None, "collision_channels": []}, SID)
    arr = ret(fa)
    for a in arr:
        ref = a.get("refPath") if isinstance(a, dict) else a
        if "DreamlabRoom" in ref:
            return ref
    return arr[0].get("refPath") if arr else None


def cam_xform(loc, look):
    fwd = [look[i] - loc[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in fwd)) or 1
    fwd = [c / n for c in fwd]
    return {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
            "rotation": {"pitch": math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1]))),
                         "yaw": math.degrees(math.atan2(fwd[1], fwd[0])), "roll": 0},
            "scale": {"x": 1, "y": 1, "z": 1}}


def capture(xform, out_png):
    # all-off annotation config: gridSpacing 0 -> no grid, maxLabelDistance/maxLabels 0 -> no labels
    anno = {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0,
            "maxLabelDistance": 0, "classFilter": None, "maxLabels": 0}
    umcp.call_tool(APP, "SetCameraTransform", {"transform": xform}, SID)
    c = umcp.call_tool(APP, "CaptureViewport",
                       {"captureTransform": xform, "annotations": anno, "bShowUI": False}, SID)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    for x in c.get("result", {}).get("content", []):
        if x.get("type") == "image":
            open(out_png, "wb").write(base64.b64decode(x["data"])); return "saved " + out_png
        if x.get("type") == "text":
            try:
                img = json.loads(x["text"])["returnValue"]["image"]["data"]
                open(out_png, "wb").write(base64.b64decode(img)); return "saved " + out_png
            except Exception:
                return "text:" + x["text"][:120]
    return "no image"


def main():
    room = find_room()
    print("room actor:", room)
    # deselect everything -> no transform gizmo in the shot
    umcp.call_tool(APP, "SelectActors", {"actors": []}, SID)
    b = ret(umcp.call_tool(ACTOR_T, "get_actor_bounds", {"actor": {"refPath": room}}, SID))
    mn, mx = b["min"], b["max"]
    ctr = [(mn["x"] + mx["x"]) / 2, (mn["y"] + mx["y"]) / 2, (mn["z"] + mx["z"]) / 2]
    half = [(mx["x"] - mn["x"]) / 2, (mx["y"] - mn["y"]) / 2, (mx["z"] - mn["z"]) / 2]
    diag = math.sqrt(sum(h * h for h in half))
    print("room ctr", [round(x) for x in ctr], "half", [round(x) for x in half])
    if OVER:
        xf = cam_xform(OVER[:3], OVER[3:6])
    else:
        d = [0.62, 0.62, 0.30]; dist = diag * 1.6
        loc = [ctr[0] + d[0] * dist, ctr[1] + d[1] * dist, ctr[2] + d[2] * dist]
        xf = cam_xform(loc, ctr)
    print(capture(xf, os.path.join(RENDERS, out_name + ".png")))


if __name__ == "__main__":
    main()
