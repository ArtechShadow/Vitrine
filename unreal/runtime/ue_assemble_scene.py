#!/usr/bin/env python3
"""Assemble the textured polygonal scene in UE 5.8 as game assets (the end-state).

Replaces the purged vertex-colour assembler: imports FBX with BAKED-TEXTURE materials
(import_materials=True) — NOT a VertexColor material (UE renders those white). Loads a
clean level, places the room at identity (already UE-framed) + each object scaled/located
from `placements.json` (computed from gaussian-PLY bounds), tones the over-bright sun so
the baked albedo reads correctly, and captures.

  python3 ue_assemble_scene.py <room_fbx> <obj_fbx_dir> <placements.json> [out_png]
Runs in vitrine-unreal (talks to 127.0.0.1:8000). FBX paths are container paths
(/usd_input/... = repo output/).
"""
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
# Real-world longest-extent priors (cm). placements.json target_size_cm is derived from
# the gaussian-PLY bbox which is inflated by loose SAM masks (chair=293, table=522cm),
# so prefer a sane per-object prior and fall back to the clamped bbox estimate.
REAL_SIZE_CM = {"chair": 95.0, "dartboard": 45.0, "ladder": 210.0, "vacuum_cleaner": 115.0,
                "mitre_saw": 60.0, "toolbox": 55.0, "table": 120.0, "workbench": 150.0}
IDENT = {"location": {"x": 0, "y": 0, "z": 0}, "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
         "scale": {"x": 1, "y": 1, "z": 1}}


def T(ts, tool, args):
    return umcp.call_tool(ts, tool, args, SID)


def ret(o):
    txt = o["result"]["content"][0]["text"]
    try:
        d = json.loads(txt)
    except Exception:
        return txt
    return d.get("returnValue", d) if isinstance(d, dict) else d


def clean_level():
    T(SCENE_T, "load_level", {"level_path": CLEAN_LEVEL})
    fa = T(SCENE_T, "find_actors", {"name": "", "tag": "",
           "actor_type": {"refPath": "/Script/Engine.Actor"},
           "root": None, "bounds": None, "collision_channels": []})
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        short = ref.split(".")[-1]
        if short.startswith("Floor") or short.startswith("StaticMeshActor"):
            try: T(SCENE_T, "remove_from_scene", {"actor": {"refPath": ref}})
            except Exception: pass
    print("[clean] level loaded", flush=True)


def import_textured(name, fbx):
    r = ret(T(SM_T, "import_file", {"folder_path": FOLDER, "asset_name": name,
              "source_file": fbx, "import_materials": True, "import_textures": True,
              "combine_meshes": True}))
    mesh = None
    if isinstance(r, list) and r:
        mesh = r[0].get("refPath") if isinstance(r[0], dict) else r[0]
    elif isinstance(r, (str, dict)):
        mesh = r.get("refPath") if isinstance(r, dict) else r
    if mesh:
        try: T(SM_T, "set_nanite_enabled", {"mesh": {"refPath": mesh}, "enabled": True})
        except Exception as e: print("  nanite", name, str(e)[:60])
    return mesh


def place(asset_ref, name, xform):
    return ret(T(SCENE_T, "add_to_scene_from_asset", {"asset_path": asset_ref, "name": name,
               "xform": xform, "parent": None, "snap_to_ground": False}))


def actor_max_extent(actor_ref):
    # get_actor_bounds is flaky right after an import/place — retry (proven in
    # object_showcase.py). Returns None if it never resolves so the caller can fall back.
    import time
    for _ in range(6):
        b = ret(T(ACT_T, "get_actor_bounds", {"actor": {"refPath": actor_ref}}))
        if isinstance(b, dict) and "min" in b and "max" in b:
            mn, mx = b["min"], b["max"]
            return max(mx["x"] - mn["x"], mx["y"] - mn["y"], mx["z"] - mn["z"])
        time.sleep(1)
    return None


def xf(loc, s=1.0, yaw=0.0):
    return {"location": {"x": loc[0], "y": loc[1], "z": loc[2]},
            "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": s, "y": s, "z": s}}


def tone_lighting():
    """Drop the Template directional sun so the baked albedo doesn't blow out."""
    fa = T(SCENE_T, "find_actors", {"name": "DirectionalLight", "tag": "",
           "actor_type": {"refPath": "/Script/Engine.Actor"},
           "root": None, "bounds": None, "collision_channels": []})
    for a in (ret(fa) or []):
        ref = a.get("refPath") if isinstance(a, dict) else a
        if "DirectionalLight" not in ref: continue
        for prop, val in [("Intensity", 1.5)]:
            try:
                T(OBJ_T, "set_property", {"object": {"refPath": ref + ".LightComponent0"},
                                          "property_name": prop, "value": val})
            except Exception as e:
                print("  light tone fail", str(e)[:80])
    print("[light] toned directional sun", flush=True)


def capture(loc, look, out_png):
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
            open(out_png, "wb").write(base64.b64decode(it["data"])); return "saved " + out_png
        if it.get("type") == "text":
            try:
                img = json.loads(it["text"])["returnValue"]["image"]["data"]
                open(out_png, "wb").write(base64.b64decode(img)); return "saved " + out_png
            except Exception: pass
    return "no image"


def main():
    room_fbx, objdir, pj = sys.argv[1], sys.argv[2], sys.argv[3]
    out_png = sys.argv[4] if len(sys.argv) > 4 else "/renders/dreamlab/ue_final_overview.png"
    placements = json.load(open(pj)) if os.path.exists(pj) else {}
    clean_level()
    # room
    room = import_textured("DreamlabRoom", room_fbx)
    if room: place(room, "DreamlabRoom", IDENT); print("[room] placed", flush=True)
    # objects
    for name, pl in placements.items():
        fbx = os.path.join(objdir, name + ".fbx")
        if not os.path.exists(fbx):
            print("  skip (no fbx)", name); continue
        mesh = import_textured("Obj_" + name, fbx)
        if not mesh: continue
        actor = place(mesh, "Obj_" + name, IDENT)
        aref = actor.get("refPath") if isinstance(actor, dict) else actor
        try:
            # gaussian-PLY bbox is inflated by loose SAM masks (clutter/floor) -> prefer a
            # real-world size prior; fall back to the clamped bbox estimate.
            tgt = REAL_SIZE_CM.get(name, max(40.0, min(float(pl["target_size_cm"]), 200.0)))
            cur = actor_max_extent(aref); s = (tgt / cur) if cur else 1.0
            loc = list(pl["location_cm"]); loc[2] = pl.get("floor_z_cm", loc[2]) + tgt / 2
            T(ACT_T, "set_actor_transform", {"actor": {"refPath": aref},
                "xform": xf(loc, s), "worldspace": True})
            print(f"[obj] {name} scale={s:.2f} loc={[round(x) for x in loc]}", flush=True)
        except Exception as e:
            print("  place fail", name, str(e)[:80])
    tone_lighting()
    # overview camera from a high back corner of the room
    print(capture([700, 600, 400], [-100, -80, 90], out_png), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
