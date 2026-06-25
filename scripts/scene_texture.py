#!/usr/bin/env python3
"""Scene mesh -> game-asset textured mesh, using the PROJECT'S OWN pipeline tools:
MeshCleaner (decimate/smooth so xatlas behaves) + TextureBaker.bake_from_vertex_colors
(xatlas UV atlas + rasterise TSDF vertex colours into a baked albedo PNG). UE imports
the UV+texture correctly (unlike dropped FBX vertex colours).

  python3 scene_texture.py <room_tsdf.ply> <out_dir>
Outputs <out_dir>/room_textured.obj (+ .mtl) + room_albedo.png.  Run in gaussian-toolkit.
"""
import sys, os, glob, faulthandler
faulthandler.enable()
sys.path.insert(0, "/opt/gaussian-toolkit/src")
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from pipeline.mesh_cleaner import MeshCleaner
from pipeline.texture_baker import TextureBaker, BakeConfig

IN, OUTDIR = sys.argv[1], sys.argv[2]
TARGET_FACES = int(sys.argv[3]) if len(sys.argv) > 3 else 200000
os.makedirs(OUTDIR, exist_ok=True)

orig = trimesh.load(IN, process=False)
print(f"loaded {len(orig.vertices):,} v {len(orig.faces):,} f  vcol={orig.visual.kind}", flush=True)
try:
    orig_vc = np.asarray(orig.visual.vertex_colors)[:, :3].copy()
except Exception:
    orig_vc = None
orig_xyz = np.asarray(orig.vertices).copy()

mesh = MeshCleaner().clean(orig.copy(), target_faces=TARGET_FACES,
                           smooth_iterations=0, fill_holes=False)  # smoothing -> degenerate tris crash xatlas
print(f"cleaned -> {len(mesh.vertices):,} v {len(mesh.faces):,} f", flush=True)


def has_vc(m):
    try:
        return m.visual.kind == "vertex" and len(m.visual.vertex_colors) == len(m.vertices)
    except Exception:
        return False


if orig_vc is not None and not has_vc(mesh):
    _, idx = cKDTree(orig_xyz).query(np.asarray(mesh.vertices))
    vc = np.concatenate([orig_vc[idx], np.full((len(idx), 1), 255, np.uint8)], 1).astype(np.uint8)
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=vc)
    print("re-attached vertex colours via nearest-neighbour", flush=True)

print("starting bake (xatlas UV + rasterise) ...", flush=True)
baker = TextureBaker(BakeConfig(texture_size=2048, padding_pixels=6))
textured, tex = baker.bake_from_vertex_colors(
    mesh, output_texture_path=os.path.join(OUTDIR, "room_albedo.png"))
uv_ok = getattr(textured.visual, "uv", None) is not None
print(f"baked albedo -> {tex}  uv={uv_ok}", flush=True)

out = os.path.join(OUTDIR, "room_textured.obj")
textured.export(out)
print(f"DONE -> {out}", flush=True)
for f in sorted(glob.glob(os.path.join(OUTDIR, "room_*"))):
    print(f"  {os.path.basename(f)}  {os.path.getsize(f):,}", flush=True)
