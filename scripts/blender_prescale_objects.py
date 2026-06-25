"""Pre-scale each object GLB to real-world size and export an FBX that imports at the
correct size in UE at scale=1.0 (sidesteps UE's broken get_actor_bounds). Also emits a
sidecar JSON with each object's post-scale height so the UE placer can sit the bottom on
the floor without querying UE. Sourced from the GLBs (not the existing FBXs) so the
UE-incompatible ladder.fbx is regenerated cleanly.

Unit convention matches blender_obj_to_fbx (room): 1 Blender unit == 1 m, default FBX
export -> UE imports at ×100 => cm. So size objects to REAL_SIZE_CM/100 Blender units.

  blender --background --python blender_prescale_objects.py -- <objdir> <out_fbx_dir> <out_json>
Run in gaussian-toolkit."""
import bpy, sys, json, os
from mathutils import Vector

objdir, outdir, outjson = sys.argv[sys.argv.index("--") + 1:]
os.makedirs(outdir, exist_ok=True)
REAL_SIZE_CM = {"chair": 95.0, "dartboard": 45.0, "ladder": 210.0, "vacuum_cleaner": 115.0,
                "mitre_saw": 60.0, "toolbox": 55.0, "table": 120.0, "workbench": 150.0}


def join(objs, name):
    for o in bpy.context.scene.objects:
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


meta = {}
for name in REAL_SIZE_CM:
    glb = os.path.join(objdir, name, name + ".glb")
    if not os.path.exists(glb):
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(o.name for o in bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    obj = join([o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name not in before], name)
    bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mn, mx = wbox(obj)
    ext = max(mx[i] - mn[i] for i in range(3)) or 1.0
    s = (REAL_SIZE_CM[name] / 100.0) / ext      # -> Blender metres
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    mn, mx = wbox(obj)
    # recenter: center xy at origin, bottom at z=0
    obj.location = (obj.location[0] - (mn[0] + mx[0]) / 2,
                    obj.location[1] - (mn[1] + mx[1]) / 2,
                    obj.location[2] - mn[2])
    bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mn, mx = wbox(obj)
    fbx = os.path.join(outdir, name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=False, path_mode='COPY',
                             embed_textures=True, mesh_smooth_type='FACE',
                             add_leaf_bones=False, bake_space_transform=False)
    meta[name] = {"height_cm": round((mx[2] - mn[2]) * 100, 1),
                  "footprint_cm": [round((mx[0] - mn[0]) * 100, 1), round((mx[1] - mn[1]) * 100, 1)]}
    print(f"prescaled {name} -> {REAL_SIZE_CM[name]:.0f}cm height={meta[name]['height_cm']}cm", flush=True)

json.dump(meta, open(outjson, "w"), indent=1)
print("wrote", outjson, list(meta.keys()), flush=True)
