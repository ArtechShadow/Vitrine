#!/usr/bin/env python3
"""Capture the ALREADY-ASSEMBLED dreamlab scene in UE from INTERIOR cameras (the room
mesh reads far better from inside than the outside-blob overview). Run AFTER
ue_assemble_scene.py has assembled room+objects in the live editor.

  python3 ue_interior_shots.py
Runs in vitrine-unreal (native MCP 127.0.0.1:8000)."""
import sys, os, json, base64, math
sys.path.insert(0, "/tmp"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umcp

SID = umcp.session()
APP = "EditorToolset.EditorAppToolset"


def cap(loc, look, out):
    fwd = [look[i] - loc[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in fwd)) or 1.0
    fwd = [c / n for c in fwd]
    x = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
         "rotation": {"pitch": math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1]))),
                      "yaw": math.degrees(math.atan2(fwd[1], fwd[0])), "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}
    umcp.call_tool(APP, "SelectActors", {"actors": []}, SID)
    umcp.call_tool(APP, "SetCameraTransform", {"transform": x}, SID)
    anno = {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0, "maxLabelDistance": 0,
            "classFilter": None, "maxLabels": 0}
    c = umcp.call_tool(APP, "CaptureViewport",
                       {"captureTransform": x, "annotations": anno, "bShowUI": False}, SID)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    for it in c.get("result", {}).get("content", []):
        if it.get("type") == "image":
            open(out, "wb").write(base64.b64decode(it["data"])); print("saved", out, flush=True); return
        if it.get("type") == "text":
            try:
                img = json.loads(it["text"])["returnValue"]["image"]["data"]
                open(out, "wb").write(base64.b64decode(img)); print("saved", out, flush=True); return
            except Exception:
                pass
    print("no image", out, flush=True)


# interior cameras (UE cm). room bounds x[-276,519] y[-394,419] z[-30,244]; chair@[1,72] vac@[261,-68]
SHOTS = [
    ([330, 280, 150], [1, 72, 30], "chair"),
    ([-60, 160, 150], [261, -68, 30], "vacuum"),
    ([470, 340, 180], [40, 0, 40], "wide"),
]
for loc, look, name in SHOTS:
    cap(loc, look, f"/renders/dreamlab/ue_interior_{name}.png")
print("DONE", flush=True)
