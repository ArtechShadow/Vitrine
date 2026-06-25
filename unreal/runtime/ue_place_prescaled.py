#!/usr/bin/env python3
"""Robust UE assembly that AVOIDS the flaky get_actor_bounds entirely: object FBXs are
pre-scaled to real-world cm (blender_prescale_objects.py) so they import at the right size
at scale=1.0, and their bottom sits at local z=0, so placing the actor at
(loc_x, loc_y, floor_z_cm) drops the object onto the floor. Heights come from the offline
object_meta.json, not UE.

  python3 ue_place_prescaled.py <room_fbx> <scaled_fbx_dir> <placements.json> <object_meta.json> <out_dir>
Runs in vitrine-unreal (127.0.0.1:8000)."""
import sys, os, json, base64, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/tmp")
import umcp

SID = umcp.session()
SCENE_T = "editor_toolset.toolsets.scene.SceneTools"
SM_T = "editor_toolset.toolsets.static_mesh.StaticMeshTools"
ACT_T = "editor_toolset.toolsets.actor.ActorTools"
OBJ_T = "editor_toolset.toolsets.object.ObjectTools"
APP = "EditorToolset.EditorAppToolset"
CLEAN_LEVEL = "/Engine/Maps/Templates/Template_Default"
FOLDER = "/Game/Vitrine/Final"
IDENT = {"location": {"x": 0, "y": 0, "z": 0}, "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}

room_fbx, objdir, pj, mj, outdir = sys.argv[1:6]


def T(ts, tool, args): return umcp.call_tool(ts, tool, args, SID)
def ret(o):
    try: d = json.loads(o["result"]["content"][0]["text"])
    except Exception: return o["result"]["content"][0]["text"] if o.get("result") else None
    return d.get("returnValue", d) if isinstance(d, dict) else d


def clean_level():
    T(SCENE_T, "load_level", {"level_path": CLEAN_LEVEL})
    fa = T(SCENE_T, "find_actors", {"name": "", "tag": "",
           "actor_type": {"refPath": "/Script/Engine.Actor"},
           "root": None, "bounds": None, "collision_channels": []})
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        if not isinstance(ref, str): continue
        short = ref.split(".")[-1]
        if short.startswith("Floor") or short.startswith("StaticMeshActor"):
            try: T(SCENE_T, "remove_from_scene", {"actor": {"refPath": ref}})
            except Exception: pass
    print("[clean] level loaded", flush=True)


def import_fbx(name, fbx):
    r = ret(T(SM_T, "import_file", {"folder_path": FOLDER, "asset_name": name,
              "source_file": fbx, "import_materials": True, "import_textures": True,
              "combine_meshes": True}))
    mesh = None
    if isinstance(r, list) and r:
        mesh = r[0].get("refPath") if isinstance(r[0], dict) else r[0]
    elif isinstance(r, dict):
        mesh = r.get("refPath")
    elif isinstance(r, str) and "produced no assets" not in r and "/Game/" in r:
        mesh = r
    if mesh:
        try: T(SM_T, "set_nanite_enabled", {"mesh": {"refPath": mesh}, "enabled": True})
        except Exception: pass
    else:
        print(f"  [import-fail] {name}: {str(r)[:80]}", flush=True)
    return mesh


def place(asset_ref, name, loc, yaw=0.0):
    xf = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
          "rotation": {"pitch": 0, "yaw": yaw, "roll": 0}, "scale": {"x": 1, "y": 1, "z": 1}}
    return ret(T(SCENE_T, "add_to_scene_from_asset", {"asset_path": asset_ref, "name": name,
               "xform": xf, "parent": None, "snap_to_ground": False}))


def tone_lighting():
    fa = T(SCENE_T, "find_actors", {"name": "DirectionalLight", "tag": "",
           "actor_type": {"refPath": "/Script/Engine.Actor"},
           "root": None, "bounds": None, "collision_channels": []})
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        if not isinstance(ref, str) or "DirectionalLight" not in ref: continue
        try: T(OBJ_T, "set_property", {"object": {"refPath": ref + ".LightComponent0"},
                                       "property_name": "Intensity", "value": 2.0})
        except Exception: pass
    print("[light] toned", flush=True)


def shoot(loc, look, out_png):
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
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    for it in c.get("result", {}).get("content", []):
        if it.get("type") == "image":
            open(out_png, "wb").write(base64.b64decode(it["data"])); print("saved", out_png, flush=True); return
        if it.get("type") == "text":
            try:
                open(out_png, "wb").write(base64.b64decode(json.loads(it["text"])["returnValue"]["image"]["data"]))
                print("saved", out_png, flush=True); return
            except Exception: pass
    print("no image", out_png, flush=True)


def main():
    print("session", SID[:20] if SID else None, flush=True)
    placements = json.load(open(pj)); meta = json.load(open(mj))
    clean_level()
    room = import_fbx("DreamlabRoom", room_fbx)
    if room:
        place(room, "DreamlabRoom", [0, 0, 0]); print("[room] placed", flush=True)
    for name, pl in placements.items():
        fbx = os.path.join(objdir, name + ".fbx")
        if not os.path.exists(fbx): continue
        mesh = import_fbx("Obj_" + name, fbx)
        if not mesh: continue
        loc = list(pl["location_cm"])
        fz = pl.get("floor_z_cm", loc[2])
        # wall-mounted items (dartboard) keep their height; floor items clamp >=0 (vacuum was -48)
        loc[2] = fz if fz > 30 else max(0.0, fz)
        place(mesh, "Obj_" + name, loc)
        print(f"[obj] {name} at {[round(x) for x in loc]} (h={meta.get(name,{}).get('height_cm','?')}cm)", flush=True)
    tone_lighting()
    # external angles read best for a thin-shell photogrammetry room (interior sees through to sky)
    shoot([720, 600, 440], [-60, -90, 90], os.path.join(outdir, "ue_come_final.png"))
    shoot([60, 60, 780], [40, -70, 40], os.path.join(outdir, "ue_come_final_top.png"))
    shoot([540, -560, 340], [-60, -60, 70], os.path.join(outdir, "ue_come_final_corner.png"))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
