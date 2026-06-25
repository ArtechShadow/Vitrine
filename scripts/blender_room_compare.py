#!/usr/bin/env python3
"""Render CoMe-geometry vs TSDF-geometry room meshes from matched cameras so we can
judge which to texture-bake into UE. Both carry vertex colour (CoMe via NN-transfer
from the TSDF mesh), so the comparison is purely geometric fidelity.

  blender --background --python blender_room_compare.py -- <come.ply> <tsdf.ply> <out_dir>
Run in gaussian-toolkit (bundled blender)."""
import bpy, sys, math, os
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
come_ply, tsdf_ply, outdir = argv[0], argv[1], argv[2]
os.makedirs(outdir, exist_ok=True)


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    avail = sc.render.bl_rna.properties['engine'].enum_items.keys()
    sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in avail else \
        ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in avail else 'CYCLES')
    sc.render.resolution_x = 960
    sc.render.resolution_y = 720
    sc.render.film_transparent = False


def load(ply):
    try:
        bpy.ops.wm.ply_import(filepath=ply)
    except Exception:
        bpy.ops.import_mesh.ply(filepath=ply)
    ob = bpy.context.selected_objects[0]
    # vertex-colour -> emission-ish principled so it reads without lighting setup
    m = bpy.data.materials.new("vc")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 1.0
    try:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    except Exception:
        pass
    vc = nt.nodes.new("ShaderNodeVertexColor")
    layers = ob.data.color_attributes
    if len(layers):
        vc.layer_name = layers[0].name
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.6
    ob.data.materials.clear()
    ob.data.materials.append(m)
    return ob


def frame_and_render(ob, out_png, elev_deg, azim_deg):
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    ctr = sum(bb, Vector((0, 0, 0))) / 8.0
    rad = max((v - ctr).length for v in bb)
    # camera
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    el, az = math.radians(elev_deg), math.radians(azim_deg)
    dist = rad * 2.4
    cam.location = ctr + Vector((dist * math.cos(el) * math.cos(az),
                                 dist * math.cos(el) * math.sin(az),
                                 dist * math.sin(el)))
    d = (ctr - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    # sun
    s = bpy.data.lights.new("s", 'SUN'); s.energy = 2.0
    so = bpy.data.objects.new("s", s); bpy.context.scene.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(30))
    w = bpy.context.scene.world or bpy.data.worlds.new("w")
    bpy.context.scene.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
    bpy.context.scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    print("saved", out_png, flush=True)


for tag, ply in [("come", come_ply), ("tsdf", tsdf_ply)]:
    for view, (el, az) in [("persp", (35, 45)), ("top", (80, 0))]:
        fresh()
        ob = load(ply)
        nf = len(ob.data.polygons)
        frame_and_render(ob, os.path.join(outdir, f"room_{tag}_{view}.png"), el, az)
        print(f"{tag} {view}: F={nf:,}", flush=True)
print("DONE", flush=True)
