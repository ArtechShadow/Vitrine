"""Parallel Blender route to render the dreamlab scene: the room as a COLORED point cloud
(the fair splat appearance — far more controllable than UE's LiDAR render) + the TRELLIS.2
object GLBs placed/sized on the floor. Reliable QA render to check the result.

Room cloud = the SH-DC-colored gaussian export (UE-cm). Geometry-Nodes Mesh-to-Points gives
each gaussian a small emissive sphere with its colour (reads like the splat). Objects from
placements.json (location_cm + target_size_cm), bottom on floor_z_cm.

  blender --background --python blender_pointcloud_scene.py -- <cloud.ply> <objdir> <placements.json> <out_png> [radius_cm]
Run in gaussian-toolkit (Blender 5.x)."""
import bpy, sys, os, json, math
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
ply, objdir, pj, out_png = a[0], a[1], a[2], a[3]
RAD = float(a[4]) if len(a) > 4 else 3.0
REAL = {"chair": 95.0, "vacuum_cleaner": 115.0, "toolbox": 55.0, "dartboard": 45.0,
        "ladder": 210.0, "mitre_saw": 60.0, "table": 120.0, "workbench": 150.0}

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# --- room point cloud ---------------------------------------------------------
before = set(o.name for o in sc.objects)
try:
    bpy.ops.wm.ply_import(filepath=ply)
except Exception:
    bpy.ops.import_mesh.ply(filepath=ply)
pc = [o for o in sc.objects if o.type == 'MESH' and o.name not in before][0]
pc.name = "RoomCloud"
col_attr = pc.data.color_attributes[0].name if pc.data.color_attributes else "Col"
print(f"[pc] {len(pc.data.vertices):,} pts colour_attr={col_attr}", flush=True)

# emissive material from the vertex colour (renders like the splat, lighting-independent)
mat = bpy.data.materials.new("pc"); mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_type = 'GEOMETRY'; attr.attribute_name = col_attr
emit = nt.nodes.new("ShaderNodeEmission"); emit.inputs["Strength"].default_value = 1.0
outn = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(attr.outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs[0], outn.inputs["Surface"])
pc.data.materials.clear(); pc.data.materials.append(mat)

# geometry nodes: mesh -> points (radius) -> SET MATERIAL (else points render default white)
ng = bpy.data.node_groups.new("PtsNG", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
gin = ng.nodes.new("NodeGroupInput"); gout = ng.nodes.new("NodeGroupOutput")
m2p = ng.nodes.new("GeometryNodeMeshToPoints"); m2p.inputs["Radius"].default_value = RAD
setmat = ng.nodes.new("GeometryNodeSetMaterial"); setmat.inputs["Material"].default_value = mat
ng.links.new(gin.outputs[0], m2p.inputs["Mesh"])
ng.links.new(m2p.outputs["Points"], setmat.inputs["Geometry"])
ng.links.new(setmat.outputs["Geometry"], gout.inputs[0])
mod = pc.modifiers.new("pts", "NODES"); mod.node_group = ng

# --- objects ------------------------------------------------------------------
placements = json.load(open(pj)) if os.path.exists(pj) else {}
for name, p in placements.items():
    glb = os.path.join(objdir, name, name + ".glb")
    if not os.path.exists(glb):
        continue
    before = set(o.name for o in sc.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception as e:
        print("  glb fail", name, str(e)[:60], flush=True); continue
    parts = [o for o in sc.objects if o.type == 'MESH' and o.name not in before]
    for o in sc.objects: o.select_set(False)
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1: bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = "Obj_" + name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    cs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector((min(c[i] for c in cs) for i in range(3))); mx = Vector((max(c[i] for c in cs) for i in range(3)))
    ext = max((mx - mn)[i] for i in range(3)) or 1.0
    s = REAL.get(name, 100.0) / ext
    ob.scale = (s, s, s); bpy.context.view_layer.update()
    cs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector((min(c[i] for c in cs) for i in range(3))); mx = Vector((max(c[i] for c in cs) for i in range(3)))
    loc = p["location_cm"]; fl = p.get("floor_z_cm", loc[2])
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    ob.location = (ob.location[0] + loc[0] - cx, ob.location[1] + loc[1] - cy, ob.location[2] + fl - mn[2])
    print(f"[obj] {name} -> {REAL.get(name,100):.0f}cm @ {[round(loc[0]),round(loc[1])]}", flush=True)

# --- lights + world -----------------------------------------------------------
sun = bpy.data.lights.new("Sun", 'SUN'); sun.energy = 5.0
so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(55), math.radians(15), math.radians(40))
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5

# --- camera + render: frame on the OBJECT cluster (objects prominent, room behind) ---
ocs = [o.matrix_world @ Vector(c) for o in sc.objects if o.type == 'MESH' and o.name.startswith("Obj_") for c in o.bound_box]
if ocs:
    omn = Vector((min(c[i] for c in ocs) for i in range(3))); omx = Vector((max(c[i] for c in ocs) for i in range(3)))
    ctr = (omn + omx) / 2; rad = max(max((omx - omn)[i] for i in range(3)), 250.0)
else:
    ctr = Vector((150, -40, 60)); rad = 400.0
cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam); sc.camera = cam; cam_d.clip_start = 1.0; cam_d.clip_end = 1e7; cam_d.lens = 35

sc.render.engine = 'CYCLES'; sc.cycles.samples = 96; sc.cycles.device = 'CPU'
sc.render.resolution_x = 1600; sc.render.resolution_y = 900


def shoot(loc, look, suffix):
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(look) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = out_png if not suffix else out_png.replace(".png", "_" + suffix + ".png")
    os.makedirs(os.path.dirname(sc.render.filepath), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("saved", sc.render.filepath, flush=True)


d = rad * 2.2
shoot([ctr[0] + d, ctr[1] - d, ctr[2] + d * 0.55], ctr, "")          # 3/4 on objects, room behind
shoot([ctr[0] - d * 0.4, ctr[1] - d, ctr[2] + d * 0.3], ctr, "front") # lower front
print("DONE", flush=True)
