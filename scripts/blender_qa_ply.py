"""Headless Blender QA render of a vertex-coloured PLY (raw/cleaned CoMe mesh) so a
candidate geometry can be eyeballed before it goes through texture->FBX->UE.

  blender --background --python scripts/blender_qa_ply.py -- <in.ply> <out.png> [mode=3q|top|3q2]
"""
import bpy, sys, math, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
ply_in, out_png = a[0], a[1]
mode = a[2] if len(a) > 2 else "3q"

bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    bpy.ops.wm.ply_import(filepath=ply_in)
except Exception:
    bpy.ops.import_mesh.ply(filepath=ply_in)

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']

# vertex-colour -> Principled base colour via the mesh's colour attribute
mat = bpy.data.materials.new("vc"); mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes.get("Principled BSDF")
attr = nt.nodes.new("ShaderNodeVertexColor")
for o in meshes:
    cols = o.data.color_attributes
    if cols:
        attr.layer_name = cols[0].name
if bsdf:
    bsdf.inputs["Roughness"].default_value = 0.9
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
for o in meshes:
    o.data.materials.clear(); o.data.materials.append(mat)

coords = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
cen = mathutils.Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2))
ext = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))

cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
d = ext * 1.5
if mode == "top":
    cam.location = cen + mathutils.Vector((0.01, 0.0, d*1.2)); cam_data.lens = 35
elif mode == "3q2":
    cam.location = cen + mathutils.Vector((-d*0.75, d*0.75, d*0.55)); cam_data.lens = 28
else:
    cam.location = cen + mathutils.Vector((d*0.75, -d*0.75, d*0.55)); cam_data.lens = 28
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
print("RENDER_DONE", out_png, "ext", round(ext, 2), "verts",
      sum(len(o.data.vertices) for o in meshes))
