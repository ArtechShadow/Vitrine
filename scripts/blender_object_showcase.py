"""Showcase the 4 reconstructed textured game-asset objects in a row at correct relative
real-world sizes (ladder tall, dartboard small), on a neutral ground, nicely lit. Reliable
Blender render — proves the per-object reconstruction quality (Hunyuan3D textured GLBs).

  blender --background --python blender_object_showcase.py -- <objdir> <out_png>
Run in gaussian-toolkit."""
import bpy, sys, math, os
from mathutils import Vector

objdir, out = sys.argv[sys.argv.index("--") + 1:]
ORDER = [("dartboard", 45.0), ("chair", 95.0), ("vacuum_cleaner", 115.0), ("ladder", 210.0)]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
av = sc.render.bl_rna.properties['engine'].enum_items.keys()
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in av else 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1600, 720


def join(objs, name):
    for o in sc.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active; j.name = name
    return j


def wbox(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(c[i] for c in cs) for i in range(3))),
            Vector((max(c[i] for c in cs) for i in range(3))))


x = 0.0
gap = 130.0
placed = []
for name, size in ORDER:
    glb = os.path.join(objdir, name, name + ".glb")
    if not os.path.exists(glb):
        continue
    before = set(o.name for o in sc.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    obj = join([o for o in sc.objects if o.type == 'MESH' and o.name not in before], "O_" + name)
    bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mn, mx = wbox(obj)
    ext = max(mx[i] - mn[i] for i in range(3)) or 1.0
    s = size / ext; obj.scale = (s, s, s)
    bpy.context.view_layer.update(); mn, mx = wbox(obj)
    w = mx[0] - mn[0]
    obj.location = (obj.location[0] + (x + w / 2 - (mn[0] + mx[0]) / 2),
                    obj.location[1] - (mn[1] + mx[1]) / 2,
                    obj.location[2] - mn[2])
    bpy.context.view_layer.update(); mn, mx = wbox(obj)
    x = mx[0] + gap
    placed.append((name, size))
    print(f"showcase {name} {size:.0f}cm w={w:.0f}", flush=True)

# ground
bpy.ops.mesh.primitive_plane_add(size=2000)
gp = bpy.context.active_object
gm = bpy.data.materials.new("g"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.22, 0.22, 0.24, 1)
gp.data.materials.append(gm)

# lighting
s = bpy.data.lights.new("s", 'SUN'); s.energy = 3.5
so = bpy.data.objects.new("s", s); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(52), math.radians(8), math.radians(35))
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.6

# camera framing the row
span = x
ctr = Vector((span / 2 - gap / 2, 0, 90))
cam_d = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
cam_d.clip_end = 100000; cam_d.lens = 40
cam.location = ctr + Vector((0, -span * 0.95, span * 0.32))
d = (ctr - cam.location).normalized()
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

os.makedirs(os.path.dirname(out), exist_ok=True)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("saved", out, "objs", placed, flush=True)
