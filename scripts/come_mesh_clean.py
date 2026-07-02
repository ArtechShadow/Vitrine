"""Floater removal for a raw CoMe TSDF mesh via Open3D connected-components.

trimesh.split() builds a Trimesh per blob and stalls for many minutes on a 3M-face
mesh with tens of thousands of components; Open3D's cluster_connected_triangles is
C++ and returns in seconds. Keep every component with >= keep_frac of the largest
cluster's triangle count (drops detached floaters/islands, preserves the main body
plus any substantial fragment). Vertex colour is preserved.

  python3 come_mesh_clean.py <in.ply> <out.ply> [keep_frac=0.02]
"""
import sys
import numpy as np
import open3d as o3d

IN, OUT = sys.argv[1], sys.argv[2]
KEEP_FRAC = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02

m = o3d.io.read_triangle_mesh(IN)
m.remove_degenerate_triangles()
m.remove_duplicated_triangles()
m.remove_duplicated_vertices()
m.remove_non_manifold_edges()
n0 = len(m.triangles)
print(f"loaded {len(m.vertices):,} v {n0:,} f  colour={m.has_vertex_colors()}", flush=True)

tri_clusters, n_tri, _ = m.cluster_connected_triangles()
tri_clusters = np.asarray(tri_clusters)
n_tri = np.asarray(n_tri)
biggest = int(n_tri.max())
thresh = max(int(biggest * KEEP_FRAC), 200)
keep_clusters = np.where(n_tri >= thresh)[0]
remove_mask = ~np.isin(tri_clusters, keep_clusters)
m.remove_triangles_by_mask(remove_mask)
m.remove_unreferenced_vertices()
print(f"clusters={len(n_tri):,} biggest={biggest:,} kept={len(keep_clusters)} "
      f"(>= {thresh:,} f)  removed {int(remove_mask.sum()):,}/{n0:,} f", flush=True)

o3d.io.write_triangle_mesh(OUT, m)
print(f"DONE -> {OUT}  {len(m.vertices):,} v {len(m.triangles):,} f", flush=True)
