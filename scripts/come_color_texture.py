#!/usr/bin/env python3
"""Colour CoMe's geometry-only tets mesh and texture it for UE. CoMe trains its own
gaussians from the same COLMAP, so its mesh is in the COLMAP world frame == the colour-
bearing TSDF mesh (room_tsdf.ply). Decimate the (huge) CoMe mesh, NN-transfer vertex
colour from the TSDF mesh, then hand to the project's xatlas bake. A Blender workbench
preview is rendered so we can judge CoMe-geometry vs the TSDF room before re-assembling.

  python3 come_color_texture.py <come_mesh.ply> <tsdf_colored.ply> <out_dir> [target_faces]
Run in gaussian-toolkit (open3d).
"""
import sys, os
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

come_ply, tsdf_ply, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
target = int(sys.argv[4]) if len(sys.argv) > 4 else 250000
os.makedirs(outdir, exist_ok=True)

print("loading CoMe mesh ...", flush=True)
m = o3d.io.read_triangle_mesh(come_ply)
print(f"CoMe raw: V={len(m.vertices):,} F={len(m.triangles):,}", flush=True)

# --- tets cleanup: kill the stray bridging triangles + floater islands ----------
# extract_mesh_tets.py (marching tetrahedra over a Delaunay complex) emits huge
# triangles spanning empty space + disconnected islands. Filter by edge length
# (strays are 10-100x the surface sampling) then keep big connected components.
V0 = np.asarray(m.vertices); T0 = np.asarray(m.triangles)
e = np.stack([
    np.linalg.norm(V0[T0[:, 0]] - V0[T0[:, 1]], axis=1),
    np.linalg.norm(V0[T0[:, 1]] - V0[T0[:, 2]], axis=1),
    np.linalg.norm(V0[T0[:, 2]] - V0[T0[:, 0]], axis=1)], axis=1).max(axis=1)
med = float(np.median(e))
keep = e <= med * 8.0
print(f"edge filter: median={med:.4f} drop {int((~keep).sum()):,}/{len(e):,} long tris", flush=True)
m.triangles = o3d.utility.Vector3iVector(T0[keep])
m.remove_unreferenced_vertices()
# largest connected components (drop islands < 1% of the biggest)
lab, counts, _ = m.cluster_connected_triangles()
lab = np.asarray(lab); counts = np.asarray(counts)
big = set(np.where(counts >= max(counts.max() * 0.01, 200))[0].tolist())
keep2 = np.array([l in big for l in lab])
m.remove_triangles_by_mask(~keep2)
m.remove_unreferenced_vertices()
print(f"connected-component keep: F={len(m.triangles):,} "
      f"(kept {len(big)} comps of {len(counts)})", flush=True)

if len(m.triangles) > target:
    # 29M faces -> quadric decimation OOMs (per-vertex quadrics + heap). Voxel
    # vertex-clustering is memory-safe and fast for huge meshes; then a light
    # quadric pass to hit the target if still large.
    ext = max(m.get_axis_aligned_bounding_box().get_extent())
    vox = ext / 420.0
    m = m.simplify_vertex_clustering(
        voxel_size=vox, contraction=o3d.geometry.SimplificationContraction.Average)
    m.remove_unreferenced_vertices()
    print(f"vertex-clustered (voxel={vox:.4f}) -> F={len(m.triangles):,}", flush=True)
    if len(m.triangles) > target * 2:
        m = m.simplify_quadric_decimation(target_number_of_triangles=target)
        m.remove_unreferenced_vertices()
        print(f"quadric -> F={len(m.triangles):,}", flush=True)
m.remove_degenerate_triangles(); m.remove_duplicated_vertices(); m.remove_unreferenced_vertices()
mv = np.asarray(m.vertices)

print("loading TSDF colour reference ...", flush=True)
ref = o3d.io.read_triangle_mesh(tsdf_ply)
rv = np.asarray(ref.vertices); rc = np.asarray(ref.vertex_colors)
print(f"TSDF ref: V={len(rv):,} has_colour={ref.has_vertex_colors()}", flush=True)
_, idx = cKDTree(rv).query(mv)
m.vertex_colors = o3d.utility.Vector3dVector(rc[idx])
m.compute_vertex_normals()
colored = os.path.join(outdir, "room_come_colored.ply")
o3d.io.write_triangle_mesh(colored, m)
print(f"coloured CoMe mesh -> {colored}", flush=True)

# workbench preview (reliable; shows vertex colour) from two angles
bb = m.get_axis_aligned_bounding_box(); ctr = bb.get_center(); ext = bb.get_extent()
print(f"CoMe UE-frame? extent={np.round(ext,2)} (note: COLMAP units, not yet UE cm)", flush=True)
