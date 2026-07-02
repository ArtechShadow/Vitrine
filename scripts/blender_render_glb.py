"""Headless Blender PBR render of a textured GLB (object QA) from a 3/4 angle with
studio lighting, so Hunyuan3D object meshes can be judged (geometry + texture + material).

  blender --background --python scripts/blender_render_glb.py -- <in.glb> <out.png> [mode=3q|front]
"""
import bpy, sys, math, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
glb_in, out_png = a[0], a[1]
mode = a[2] if len(a) > 2 else "3q"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb_in)

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
coords = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
cen = mathutils.Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2))
ext = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)) or 1.0

cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
d = ext * 1.7
if mode == "front":
    cam.location = cen + mathutils.Vector((0.0, -d, ext*0.15))
else:
    cam.location = cen + mathutils.Vector((d*0.7, -d*0.7, ext*0.5))
cam_data.lens = 50
cam.rotation_euler = (cen - cam.location).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

# studio-ish: key area + fill + soft world
for pos, e in [((d, -d, d*1.2), 1500.0), ((-d, -d*0.5, d*0.6), 500.0)]:
    ld = bpy.data.lights.new("a", type='AREA'); ld.energy = e; ld.size = ext*1.5
    lo = bpy.data.objects.new("a", ld); bpy.context.scene.collection.objects.link(lo)
    lo.location = cen + mathutils.Vector(pos)
    lo.rotation_euler = (cen - lo.location).to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new("w"); bpy.context.scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.samples = 64; sc.cycles.device = 'CPU'
sc.render.resolution_x = 1024; sc.render.resolution_y = 1024
sc.render.film_transparent = False
sc.render.filepath = out_png
bpy.ops.render.render(write_still=True)
print("GLB_RENDER_DONE", out_png, "ext", round(ext, 3), "tris",
      sum(len(o.data.polygons) for o in meshes))
