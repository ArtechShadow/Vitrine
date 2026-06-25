#!/usr/bin/env python3
"""Build the dreamlab object scene + render an INSPECT-interaction video via the
UE 5.8 native MCP. Scripts the interaction (object pops to centre-of-shot, slow-
rotates, returns) and captures a viewport frame per step -> /renders/dreamlab/vid/.
ffmpeg stitches the frames to mp4 afterwards.
"""
import sys, os, json, base64, math
sys.path.insert(0, "/tmp")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umcp

SID = umcp.session()
VID = "/renders/dreamlab/vid"


def T(ts, tool, args):
    return umcp.call_tool(ts, tool, args, SID)


def xform(loc, yaw=0.0, s=1.0):
    return {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
            "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": s, "y": s, "z": s}}


def place(asset, name, loc):
    r = T("editor_toolset.toolsets.scene.SceneTools", "add_to_scene_from_asset",
          {"asset_path": asset, "name": name, "xform": xform(loc), "snap_to_ground": False})
    return r["result"]["content"][0] if "result" in r else None


def place_ref(asset, name, loc):
    body = ("import json\n"
            "def run():\n"
            f"    a = execute_tool('editor_toolset.toolsets.scene.SceneTools.add_to_scene_from_asset',\n"
            f"        json.dumps({{'asset_path':'{asset}','name':'{name}','xform':{json.dumps(xform(loc))},'snap_to_ground':False}}))\n"
            "    return {'ref': a['returnValue']}\n")
    o = T("editor_toolset.toolsets.programmatic.ProgrammaticToolset", "execute_tool_script", {"script": body})
    return json.loads(json.loads(o["result"]["content"][0]["text"])["returnValue"])["ref"]


def set_xf(actor, loc, yaw):
    T("editor_toolset.toolsets.actor.ActorTools", "set_actor_transform",
      {"actor": actor, "xform": xform(loc, yaw), "worldspace": True})


def bounds(actor):
    o = T("editor_toolset.toolsets.actor.ActorTools", "get_actor_bounds", {"actor": actor})
    d = json.loads(o["result"]["content"][0]["text"])["returnValue"]
    return d


def set_cam(loc, look):
    fwd = [look[i] - loc[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in fwd)) or 1
    fwd = [c / n for c in fwd]
    pitch = math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1])))
    yaw = math.degrees(math.atan2(fwd[1], fwd[0]))
    xf = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
          "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0},
          "scale": {"x": 1, "y": 1, "z": 1}}
    T("EditorToolset.EditorAppToolset", "SetCameraTransform", {"transform": xf})
    return loc, fwd


def capture(path):
    cam = T("EditorToolset.EditorAppToolset", "GetCameraTransform", {})["result"]["content"][0]["text"]
    cam = json.loads(cam)["returnValue"]
    c = T("EditorToolset.EditorAppToolset", "CaptureViewport",
          {"captureTransform": cam, "annotations": {}, "bShowUI": False})
    for x in c.get("result", {}).get("content", []):
        if x.get("type") == "text":
            img = json.loads(x["text"]).get("returnValue", {}).get("image", {}).get("data")
            if img:
                open(path, "wb").write(base64.b64decode(img)); return True
    return False


def lerp(a, b, t):
    s = t * t * (3 - 2 * t)
    return [a[i] + (b[i] - a[i]) * s for i in range(3)]


def main():
    os.makedirs(VID, exist_ok=True)
    chair = place_ref("/Game/Vitrine/Objects/chairnew.chairnew", "Obj_chair", [0, 0, 0])
    place_ref("/Game/Vitrine/Objects/dartboard.dartboard", "Obj_dartboard", [220, 80, 0])
    b = bounds(chair)
    r = max((b["max"]["x"] - b["min"]["x"]) / 2, (b["max"]["y"] - b["min"]["y"]) / 2,
            (b["max"]["z"] - b["min"]["z"]) / 2, 30)
    home = [0, 0, 0]
    cam_loc = [r * 4.5, -r * 2.0, r * 1.6]
    _, fwd = set_cam(cam_loc, home)
    center = [cam_loc[i] + fwd[i] * (r * 2.4) for i in range(3)]
    center[2] = cam_loc[2] + fwd[2] * (r * 2.4)

    f = 0
    # settle frames
    for _ in range(6):
        capture(f"{VID}/frame_{f:04d}.png"); f += 1
    # pop-in
    for i in range(18):
        set_xf(chair, lerp(home, center, i / 17.0), 0)
        capture(f"{VID}/frame_{f:04d}.png"); f += 1
    # inspect rotate 360
    for i in range(40):
        set_xf(chair, center, (i / 40.0) * 360.0)
        capture(f"{VID}/frame_{f:04d}.png"); f += 1
    # pop-out
    for i in range(18):
        set_xf(chair, lerp(center, home, i / 17.0), 0)
        capture(f"{VID}/frame_{f:04d}.png"); f += 1
    set_xf(chair, home, 0)
    print(f"FRAMES={f} -> {VID}")


if __name__ == "__main__":
    main()
