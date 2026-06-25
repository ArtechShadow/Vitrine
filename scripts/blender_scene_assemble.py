#!/usr/bin/env python3
"""Reliable full-scene assembly + render in Blender (the UE live-editor MCP path is flaky:
get_actor_bounds errors, actors don't persist, room won't render). Blender bbox measurement
is deterministic, so objects size correctly. Proves the deliverable: CoMe room (UV-textured)
+ per-object textured GLBs placed/sized per placements.json.

  blender --background --python blender_scene_assemble.py -- <room_obj> <M.json> <objdir> <placements.json> <out_png>
Room OBJ is COLMAP-frame -> apply M (COLMAP->UE cm); objects are placed at UE-cm locations.
Run in gaussian-toolkit (Blender 5.0, GPU0)."""
import bpy, sys, json, math, os
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
room_obj, m_json, objdir, pj, out_png = a[0], a[1], a[2], a[3], a[4]
REAL_SIZE_CM = {"chair": 95.0, "dartboard": 45.0, "ladder": 210.0, "vacuum_cleaner": 115.0,
                "mitre_saw": 60.0, "toolbox": 55.0, "table": 120.0, "workbench": 150.0}

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
avail = sc.render.bl_rna.properties['engine'].enum_items.keys()
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in avail else (
    'BLENDER_EEVEE' if 'BLENDER_EEVEE' in avail else 'CYCLES')
sc.render.resolution_x, sc.render.resolution_y = 1280, 960


def imported_meshes(before):
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name not in before]


def join(objs, name):
    if not objs:
        return None
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active
    j.name = name
    return j


def world_bbox(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(c[i] for c in cs) for i in range(3)))
    mx = Vector((min(c[i] for c in cs) for i in range(3)))  # placeholder
    mx = Vector((max(c[i] for c in cs) for i in range(3)))
    return mn, mx


# --- room (COLMAP frame) -> UE cm via M ----------------------------------------
before = set(o.name for o in bpy.context.scene.objects)
try:
    bpy.ops.wm.obj_import(filepath=room_obj)
except Exception:
    bpy.ops.import_scene.obj(filepath=room_obj)
room = join(imported_meshes(before), "Room")
M = json.load(open(m_json))["transform"]
M4 = Matrix([[M[r][c] for c in range(4)] for r in range(3)] + [[0, 0, 0, 1]])
room.matrix_world = M4 @ room.matrix_world
print(f"[room] {len(room.data.polygons):,} tris", flush=True)

# --- objects -------------------------------------------------------------------
placements = json.load(open(pj))
placed = []
for name, pl in placements.items():
    glb = os.path.join(objdir, name, name + ".glb")
    if not os.path.exists(glb):
        continue
    before = set(o.name for o in bpy.context.scene.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception as e:
        print("  glb import fail", name, str(e)[:60], flush=True); continue
    obj = join([o for o in imported_meshes(before)], "Obj_" + name)
    if not obj:
        continue
    # reset any baked transform, measure, scale to real-world longest extent
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mn, mx = world_bbox(obj)
    ext = max(mx[i] - mn[i] for i in range(3)) or 1.0
    s = REAL_SIZE_CM.get(name, 100.0) / ext
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    mn, mx = world_bbox(obj)
    # place: center xy at location_cm, bottom z at floor_z_cm
    loc = pl["location_cm"]; floor = pl.get("floor_z_cm", loc[2])
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    obj.location = (obj.location[0] + (loc[0] - cx),
                    obj.location[1] + (loc[1] - cy),
                    obj.location[2] + (floor - mn[2]))
    bpy.context.view_layer.update()
    placed.append(name)
    print(f"[obj] {name} scale={s:.3f} -> {REAL_SIZE_CM.get(name,100):.0f}cm at {[round(x) for x in loc]}", flush=True)

print("placed objects:", placed, flush=True)

# --- lighting + world ----------------------------------------------------------
sun = bpy.data.lights.new("Sun", 'SUN'); sun.energy = 3.0
so = bpy.data.objects.new("Sun", sun); bpy.context.scene.collection.objects.link(so)
so.rotation_euler = (math.radians(55), math.radians(15), math.radians(40))
w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.7

# --- camera: frame room + objects, several angles ------------------------------
cs = []
for o in bpy.context.scene.objects:
    if o.type == 'MESH':
        cs += [o.matrix_world @ Vector(c) for c in o.bound_box]
mn = Vector((min(c[i] for c in cs) for i in range(3)))
mx = Vector((max(c[i] for c in cs) for i in range(3)))
ctr = (mn + mx) / 2
rad = max(mx[i] - mn[i] for i in range(3))

cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d)
bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam
cam_d.clip_start = 1.0; cam_d.clip_end = 100000.0; cam_d.lens = 24


def shoot(loc, look, name):
    cam.location = Vector(loc)
    d = (Vector(look) - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    out = out_png if name == "main" else out_png.replace(".png", "_" + name + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("saved", out, flush=True)


# 3/4 high view, pulled in close; top-down floor-plan; lower interior angle
shoot([ctr[0] + rad * 0.55, ctr[1] - rad * 0.65, mx[2] + rad * 0.35], ctr, "main")
shoot([ctr[0] + 5, ctr[1] + 5, mx[2] + rad * 0.9], [ctr[0], ctr[1], mn[2]], "top")
shoot([ctr[0] + rad * 0.45, ctr[1] - rad * 0.55, ctr[2] + rad * 0.15],
      [ctr[0] - rad * 0.2, ctr[1] + rad * 0.1, ctr[2]], "interior")
print("DONE", flush=True)
