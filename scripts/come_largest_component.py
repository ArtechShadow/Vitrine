"""Keep only the largest connected component of a mesh (drop the detached second
chunk that inflates the bbox) so a QA render frames tightly on the main room body.

  python3 come_largest_component.py <in.ply> <out.ply>
"""
import sys
import numpy as np
import open3d as o3d

m = o3d.io.read_triangle_mesh(sys.argv[1])
tc, n, _ = m.cluster_connected_triangles()
tc = np.asarray(tc); n = np.asarray(n)
biggest = int(np.argmax(n))
m.remove_triangles_by_mask(tc != biggest)
m.remove_unreferenced_vertices()
o3d.io.write_triangle_mesh(sys.argv[2], m)
print(f"largest component -> {sys.argv[2]}  {len(m.vertices):,} v {len(m.triangles):,} f "
      f"(of {len(n):,} clusters)", flush=True)
