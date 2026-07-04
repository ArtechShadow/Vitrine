#!/usr/bin/env python3
"""Headless Blender QA render of a textured OBJ from an elevated 3/4 angle, so a
scene mesh can be eyeballed (texture + geometry) before committing to UE import.

  blender --background --python scripts/blender_qa_render.py -- <in.obj> <out.png>
"""
import bpy, sys, math, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
obj_in, out_png = a[0], a[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    bpy.ops.wm.obj_import(filepath=obj_in)
except Exception:
    bpy.ops.import_scene.obj(filepath=obj_in)

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
coords = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
cen = mathutils.Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2))
ext = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))

mode = a[2] if len(a) > 2 else "3q"
cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
d = ext * 1.5
if mode == "top":
    cam.location = cen + mathutils.Vector((0.01, 0.0, d*1.2))
    cam_data.lens = 35
elif mode == "3q2":
    cam.location = cen + mathutils.Vector((-d*0.75, d*0.75, d*0.55))
    cam_data.lens = 28
else:  # 3q
    cam.location = cen + mathutils.Vector((d*0.75, -d*0.75, d*0.55))
    cam_data.lens = 28
cam.rotation_euler = (cen - cam.location).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

light_data = bpy.data.lights.new("sun", type='SUN'); light_data.energy = 3.5
light = bpy.data.objects.new("sun", light_data)
bpy.context.scene.collection.objects.link(light)
light.rotation_euler = (math.radians(50), math.radians(15), math.radians(35))

world = bpy.data.worlds.new("w"); bpy.context.scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 0.7

sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.samples = 48; sc.cycles.device = 'CPU'
sc.render.resolution_x = 1280; sc.render.resolution_y = 960
sc.render.filepath = out_png
bpy.ops.render.render(write_still=True)
print("RENDER_DONE", out_png, "ext", round(ext, 2))
