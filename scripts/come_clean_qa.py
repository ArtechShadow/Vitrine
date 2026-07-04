"""Clean a raw legacy-TSDF CoMe mesh (connected-component floater removal) and emit
both the full cleaned mesh (for the texture step) and a decimated QA copy (for a quick
Blender eyeball), in one load to avoid round-tripping multi-GB PLYs.

  python3 come_clean_qa.py <in.ply> <out_clean.ply> <out_qa.ply> [keep_frac=0.02] [qa_faces=700000]
"""
import sys
import numpy as np
import open3d as o3d

IN, OUT_CLEAN, OUT_QA = sys.argv[1], sys.argv[2], sys.argv[3]
KEEP_FRAC = float(sys.argv[4]) if len(sys.argv) > 4 else 0.02
QA_FACES = int(sys.argv[5]) if len(sys.argv) > 5 else 700000

m = o3d.io.read_triangle_mesh(IN)
m.remove_degenerate_triangles(); m.remove_duplicated_triangles(); m.remove_duplicated_vertices()
n0 = len(m.triangles)
print(f"loaded {len(m.vertices):,} v {n0:,} f colour={m.has_vertex_colors()}", flush=True)

tri_clusters, n_tri, _ = m.cluster_connected_triangles()
tri_clusters = np.asarray(tri_clusters); n_tri = np.asarray(n_tri)
biggest = int(n_tri.max())
thresh = max(int(biggest * KEEP_FRAC), 500)
keep = np.where(n_tri >= thresh)[0]
remove_mask = ~np.isin(tri_clusters, keep)
m.remove_triangles_by_mask(remove_mask); m.remove_unreferenced_vertices()
print(f"clusters={len(n_tri):,} biggest={biggest:,} kept={len(keep)} (>= {thresh:,} f) "
      f"removed {int(remove_mask.sum()):,}/{n0:,} f -> {len(m.triangles):,} f", flush=True)

o3d.io.write_triangle_mesh(OUT_CLEAN, m)
print(f"CLEAN -> {OUT_CLEAN}  {len(m.vertices):,} v {len(m.triangles):,} f", flush=True)

# decimate for QA only (vertex clustering preserves colour reasonably + is fast)
if len(m.triangles) > QA_FACES:
    ext = max(m.get_axis_aligned_bounding_box().get_extent())
    vox = ext / 400.0
    for _ in range(10):
        md = m.simplify_vertex_clustering(vox, o3d.geometry.SimplificationContraction.Average)
        md.remove_degenerate_triangles(); md.remove_unreferenced_vertices()
        if len(md.triangles) <= QA_FACES:
            break
        vox *= 1.3
else:
    md = m
o3d.io.write_triangle_mesh(OUT_QA, md)
print(f"QA   -> {OUT_QA}  {len(md.vertices):,} v {len(md.triangles):,} f", flush=True)
