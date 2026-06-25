#!/usr/bin/env python3
"""True live-UE capture of the inspect interaction: place the reconstructed objects,
x11grab the Xvfb display while driving the inspect animation (pop-to-centre ->
360 rotate -> return) over the native MCP. Output /renders/dreamlab/live_inspect.mp4.
Runs inside the (rebuilt, ffmpeg-equipped) vitrine-unreal container.
"""
import sys, os, json, math, time, subprocess
sys.path.insert(0, "/tmp"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umcp

SID = umcp.session()
OUT = "/renders/dreamlab/live_inspect.mp4"
STEP_SLEEP = 0.0  # MCP round-trip (~1.5s) already paces each pose for x11grab


def T(ts, tool, args):
    return umcp.call_tool(ts, tool, args, SID)


def xf(loc, yaw=0.0, s=1.0):
    return {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
            "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": s, "y": s, "z": s}}


def place(asset, name, loc):
    body = ("import json\n"
            "def run():\n"
            f"    a = execute_tool('editor_toolset.toolsets.scene.SceneTools.add_to_scene_from_asset',\n"
            f"        json.dumps({{'asset_path':'{asset}','name':'{name}','xform':{json.dumps(xf(loc))},'snap_to_ground':False}}))\n"
            "    return {'ref': a['returnValue']}\n")
    o = T("editor_toolset.toolsets.programmatic.ProgrammaticToolset", "execute_tool_script", {"script": body})
    return json.loads(json.loads(o["result"]["content"][0]["text"])["returnValue"])["ref"]


def set_xf(actor, loc, yaw, s=1.0):
    T("editor_toolset.toolsets.actor.ActorTools", "set_actor_transform",
      {"actor": actor, "xform": xf(loc, yaw, s), "worldspace": True})


def bounds(actor):
    o = T("editor_toolset.toolsets.actor.ActorTools", "get_actor_bounds", {"actor": actor})
    return json.loads(o["result"]["content"][0]["text"])["returnValue"]


def set_cam(loc, look):
    fwd = [look[i] - loc[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in fwd)) or 1
    fwd = [c / n for c in fwd]
    xform = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
             "rotation": {"pitch": math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1]))),
                          "yaw": math.degrees(math.atan2(fwd[1], fwd[0])), "roll": 0},
             "scale": {"x": 1, "y": 1, "z": 1}}
    T("EditorToolset.EditorAppToolset", "SetCameraTransform", {"transform": xform})
    return fwd


def lerp(a, b, t):
    s = t * t * (3 - 2 * t)
    return [a[i] + (b[i] - a[i]) * s for i in range(3)]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    chair = place("/Game/Vitrine/Objects/chair.chair", "Obj_chair", [0, 0, 0])
    place("/Game/Vitrine/Objects/dartboard.dartboard", "Obj_dartboard", [240, 90, 0])
    b = bounds(chair)
    r = max((b["max"]["x"] - b["min"]["x"]) / 2, (b["max"]["y"] - b["min"]["y"]) / 2,
            (b["max"]["z"] - b["min"]["z"]) / 2, 30)
    home = [r * 1.8, r * 1.2, 0]
    cam = [r * 4.5, -r * 2.2, r * 1.7]
    fwd = set_cam(cam, [0, 0, 0])
    center = [cam[i] + fwd[i] * (r * 2.6) for i in range(3)]
    set_xf(chair, home, 0, 0.4)
    # Clear the floating Content Browser (opened by import) and maximize the level
    # viewport (immersive F11) so the capture shows only the scene. Needs xdotool.
    env = {**os.environ, "DISPLAY": ":1"}
    for cmd in [
        "xdotool search --name 'Content Browser' windowclose",
        "xdotool search --onlyvisible --name 'Unreal Editor' windowactivate --sync",
        "xdotool mousemove 250 280 click 1",
        "xdotool key F11",
    ]:
        try:
            subprocess.run(cmd, shell=True, env=env, timeout=10)
        except Exception:
            pass
        time.sleep(0.4)
    time.sleep(2.0)

    rec = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "x11grab", "-framerate", "15", "-video_size", "1920x1080",
         "-i", ":1", "-t", "70", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", OUT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    try:
        for _ in range(3):  # settle at home
            set_xf(chair, home, 0, 0.4); time.sleep(STEP_SLEEP)
        for i in range(8):  # pop-in
            t = i / 7.0
            set_xf(chair, lerp(home, center, t), 0, 0.4 + 0.6 * (t * t * (3 - 2 * t)))
            time.sleep(STEP_SLEEP)
        for i in range(20):  # rotate 360 at centre
            set_xf(chair, center, (i / 20.0) * 360.0, 1.0); time.sleep(STEP_SLEEP)
        for i in range(6):  # pop-out
            t = i / 5.0
            set_xf(chair, lerp(center, home, t), 0, 1.0 - 0.6 * (t * t * (3 - 2 * t)))
            time.sleep(STEP_SLEEP)
        set_xf(chair, home, 0, 0.4)
    finally:
        rec.wait(timeout=80)
    print("LIVE_VIDEO", OUT, os.path.getsize(OUT) if os.path.exists(OUT) else "MISSING")


if __name__ == "__main__":
    main()
