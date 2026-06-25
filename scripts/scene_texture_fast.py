#!/usr/bin/env python3
"""Fast scene-mesh -> game-asset texture bake for an ALREADY-CLEAN coloured mesh.

scene_texture.py routes through MeshCleaner.clean() (degenerate-removal + trimesh
mesh.split() component filter + decimate) which is pathologically slow / hangs on the
CoMe mesh (>12 min, never returns). The CoMe mesh out of come_color_texture.py is
already a single connected component with vertex colour, so we skip MeshCleaner entirely:
open3d quadric-decimate (seconds at this size) -> NN re-attach colour -> the project's
TextureBaker.bake_from_vertex_colors (xatlas UV + rasterise albedo). UE imports UV+texture
correctly (vertex colours are dropped by FBX).

  python3 scene_texture_fast.py <colored.ply> <out_dir> [target_faces]
Outputs <out_dir>/room_textured.obj (+ .mtl) + room_albedo.png. Run in gaussian-toolkit.
"""
import sys, os, glob, faulthandler
faulthandler.enable()
sys.path.insert(0, "/opt/gaussian-toolkit/src")
import numpy as np
import trimesh
import open3d as o3d
from scipy.spatial import cKDTree
from pipeline.texture_baker import TextureBaker, BakeConfig

IN, OUTDIR = sys.argv[1], sys.argv[2]
TARGET = int(sys.argv[3]) if len(sys.argv) > 3 else 200000
os.makedirs(OUTDIR, exist_ok=True)

m = o3d.io.read_triangle_mesh(IN)
rv = np.asarray(m.vertices)
rc = np.asarray(m.vertex_colors)
print(f"loaded {len(rv):,} v {len(m.triangles):,} f  colour={m.has_vertex_colors()}", flush=True)

if len(m.triangles) > TARGET:
    # Quadric decimation PRESERVES open boundaries, so on a holey room mesh it barely
    # reduces faces (418k) AND leaves thousands of tiny UV islands -> xatlas chart-packing
    # grinds for 20+ min. Vertex clustering merges vertices across the small holes ->
    # fewer faces and far fewer charts -> xatlas finishes in minutes. Grow the voxel until
    # under target.
    ext = max(m.get_axis_aligned_bounding_box().get_extent())
    vox = ext / 200.0
    for _ in range(8):
        md = m.simplify_vertex_clustering(
            voxel_size=vox, contraction=o3d.geometry.SimplificationContraction.Average)
        md.remove_degenerate_triangles(); md.remove_unreferenced_vertices()
        if len(md.triangles) <= TARGET:
            break
        vox *= 1.25
    print(f"vertex-clustered (voxel={vox:.4f})", flush=True)
else:
    md = m
mv = np.asarray(md.vertices)
mf = np.asarray(md.triangles)
print(f"decimated -> {len(mv):,} v {len(mf):,} f", flush=True)

# open3d decimation drops colour -> NN re-attach from the source vertices
if rc is not None and len(rc):
    _, idx = cKDTree(rv).query(mv)
    rgb = np.clip(rc[idx] * 255.0, 0, 255).astype(np.uint8)
else:
    rgb = np.full((len(mv), 3), 200, np.uint8)
vc = np.concatenate([rgb, np.full((len(mv), 1), 255, np.uint8)], axis=1)
mesh = trimesh.Trimesh(vertices=mv, faces=mf, process=False)
mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=vc)

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
