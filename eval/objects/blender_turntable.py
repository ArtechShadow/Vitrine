# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Headless-Blender turntable renderer for the R9 object eval.

Invoked by run_eval.py:  blender -b -noaudio -P blender_turntable.py -- \
    <mesh.glb> <out_dir> [views]

Renders N evenly-spaced orbit views of the object with neutral studio
lighting so successive eval runs are visually comparable frame-for-frame.
"""

import math
import sys
from pathlib import Path

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
glb_path, out_dir = Path(argv[0]), Path(argv[1])
views = int(argv[2]) if len(argv) > 2 else 8

# Clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(glb_path))

# Frame the imported object(s)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no meshes imported")

xs, ys, zs = [], [], []
for o in meshes:
    for corner in o.bound_box:
        v = o.matrix_world @ mathutils.Vector(corner)
        xs.append(v.x); ys.append(v.y); zs.append(v.z)
cx, cy, cz = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2, (max(zs)+min(zs))/2
radius = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)) * 1.6 or 1.0

# Neutral lighting + camera
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", type="SUN"))
sun.data.energy = 3.0
bpy.context.collection.objects.link(sun)
world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
bpy.context.scene.world = world

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

scene = bpy.context.scene
# WORKBENCH + texture color: grades geometry + albedo deterministically across
# Blender versions, and is immune to the PBR alpha channel (TRELLIS.2 GLBs
# carry atlas-padding alpha that EEVEE renders as transparent patchwork).
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 768
scene.render.film_transparent = False

out_dir.mkdir(parents=True, exist_ok=True)

for i in range(views):
    az = 2 * math.pi * i / views
    cam.location = (cx + radius * math.cos(az), cy + radius * math.sin(az), cz + radius * 0.35)
    direction = mathutils.Vector((cx, cy, cz)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out_dir / f"view_{i:02d}.png")
    bpy.ops.render.render(write_still=True)

print(f"turntable: {views} views -> {out_dir}")
