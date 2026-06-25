#!/usr/bin/env python3
"""Blender: import a textured OBJ (mtl+map_Kd), bake the COLMAP->UE transform (x0.01
so the FBX m->cm export lands in UE cm), embed the texture, export FBX for UE.

  blender --background --python scripts/blender_obj_to_fbx.py -- <in.obj> <M.json> <out.fbx>
"""
import bpy, sys, json, mathutils

a = sys.argv[sys.argv.index("--") + 1:]
obj_in, m_json, fbx_out = a[0], a[1], a[2]

bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    bpy.ops.wm.obj_import(filepath=obj_in)
except Exception:
    bpy.ops.import_scene.obj(filepath=obj_in)

M = json.load(open(m_json))["transform"]
Mfull = [[0.01 * M[r][c] for c in range(4)] for r in range(3)] + [[0, 0, 0, 1]]
Mat = mathutils.Matrix(Mfull)

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in meshes:
    o.matrix_world = Mat @ o.matrix_world
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

bpy.ops.export_scene.fbx(filepath=fbx_out, use_selection=False, path_mode='COPY',
                         embed_textures=True, mesh_smooth_type='FACE',
                         add_leaf_bones=False, bake_space_transform=False)
print("FBX", fbx_out, "verts", sum(len(o.data.vertices) for o in meshes), flush=True)
