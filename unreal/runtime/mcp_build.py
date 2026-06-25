#!/usr/bin/env python3
"""Build the Vitrine interactive scene in the live editor via the UE 5.8 native MCP.

Runs inside the vitrine-unreal container (talks to 127.0.0.1:8000). Uses umcp.py.
Validated viewport captures are written under /renders (= project output/renders),
never /tmp. Reusable: import object hull FBX -> Nanite StaticMesh -> place -> shoot.
"""
import sys, os, json, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/tmp")
import umcp

IDENT = {"location": {"x": 0, "y": 0, "z": 0},
         "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}

RENDERS = "/renders/dreamlab"


def _script(body):
    """Wrap a run()-body in the execute_tool helpers + send via MCP."""
    sid = umcp.session()
    header = (
        "import json\n"
        "def T(name, args):\n"
        "    return execute_tool(name, json.dumps(args))\n"
        "def imp(folder, name, src):\n"
        "    return T('editor_toolset.toolsets.static_mesh.StaticMeshTools.import_file',\n"
        "        {'folder_path': folder, 'asset_name': name, 'source_file': src,\n"
        "         'import_materials': True, 'import_textures': True, 'combine_meshes': True})\n"
        "def nanite(ref):\n"
        "    return T('editor_toolset.toolsets.static_mesh.StaticMeshTools.set_nanite_enabled',\n"
        "        {'mesh': {'refPath': ref}, 'enabled': True})\n"
        "def place(asset, name, xform):\n"
        "    return T('editor_toolset.toolsets.scene.SceneTools.add_to_scene_from_asset',\n"
        "        {'asset_path': asset, 'name': name, 'xform': xform, 'snap_to_ground': False})\n"
        "def focus(actors):\n"
        "    return T('EditorToolset.EditorAppToolset.FocusOnActors', {'actors': actors})\n"
        "def getcam():\n"
        "    return T('EditorToolset.EditorAppToolset.GetCameraTransform', {})\n"
        "def find(name):\n"
        "    return T('editor_toolset.toolsets.scene.SceneTools.find_actors', {'name': name})\n"
    )
    out = umcp.call_tool("editor_toolset.toolsets.programmatic.ProgrammaticToolset",
                         "execute_tool_script", {"script": header + body}, sid)
    txt = out["result"]["content"][0]["text"]
    try:
        return json.loads(json.loads(txt)["returnValue"]), sid
    except Exception:
        return {"raw": txt}, sid


def capture(cam, out_png, sid=None):
    sid = sid or umcp.session()
    c = umcp.call_tool("EditorToolset.EditorAppToolset", "CaptureViewport",
                       {"captureTransform": cam, "annotations": {}, "bShowUI": False}, sid)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    for x in c.get("result", {}).get("content", []):
        if x.get("type") == "image":
            open(out_png, "wb").write(base64.b64decode(x["data"]))
            return f"saved {out_png} ({os.path.getsize(out_png)} bytes)"
        if x.get("type") == "text":
            try:
                img = json.loads(x["text"]).get("returnValue", {}).get("image", {}).get("data")
                if img:
                    open(out_png, "wb").write(base64.b64decode(img))
                    return f"saved {out_png} ({os.path.getsize(out_png)} bytes)"
            except Exception:
                pass
            return "capture text: " + x["text"][:160]
    return "no image"


def import_object(name, fbx, folder="/Game/Vitrine/Objects"):
    body = (
        "def run():\n"
        f"    r = imp('{folder}', '{name}', '{fbx}')\n"
        "    ref = r['returnValue'][0]['refPath'] if r.get('returnValue') else None\n"
        "    out = {'ref': ref}\n"
        "    if ref:\n"
        "        try: out['nanite'] = nanite(ref)\n"
        "        except Exception as e: out['nanite_err'] = str(e)[:120]\n"
        "    return out\n"
    )
    return _script(body)


def place_and_shoot(asset_ref, name, out_png):
    body = (
        "def run():\n"
        f"    a = place('{asset_ref}', '{name}', {json.dumps(IDENT)})\n"
        "    actor = a['returnValue']\n"
        "    focus([actor])\n"
        "    return {'actor': actor, 'cam': getcam()['returnValue']}\n"
    )
    res, sid = _script(body)
    cam = res.get("cam")
    cap = capture(cam, out_png, sid) if cam else f"no cam: {res}"
    return {"place": res, "capture": cap}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "import":
        print(import_object(sys.argv[2], sys.argv[3])[0])
    elif cmd == "shoot":
        print(place_and_shoot(sys.argv[2], sys.argv[3], sys.argv[4]))
