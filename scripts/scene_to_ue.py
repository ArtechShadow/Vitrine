#!/usr/bin/env python3
"""Compute the COLMAP->UE transform (gravity up=+Z via RANSAC ground plane, scale to
cm, floor at z=0, centred XY) for the textured room mesh and write it to JSON so the
Blender step can bake it before FBX export. Also re-usable for placing objects.

  python3 scene_to_ue.py <room_textured.obj> <out_transform.json> [target_room_m]
"""
import sys, json
import numpy as np
import open3d as o3d
import trimesh

obj = sys.argv[1]
out = sys.argv[2]
TARGET_M = float(sys.argv[3]) if len(sys.argv) > 3 else 7.0

m = trimesh.load(obj, process=False)
V = np.asarray(m.vertices, dtype=np.float64)
c = np.median(V, 0)
p = V - c
ext = np.percentile(p, 98, 0) - np.percentile(p, 2, 0)
char = float(np.max(ext))

pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(p))
pcd = pcd.voxel_down_sample(voxel_size=max(char / 300.0, 1e-4))
plane, _ = pcd.segment_plane(distance_threshold=char / 150.0, ransac_n=3, num_iterations=3000)
n = np.array(plane[:3], float); n /= np.linalg.norm(n) + 1e-12


def R_align(a, b):
    a = a / (np.linalg.norm(a) + 1e-12); b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b); s = np.linalg.norm(v); cph = float(np.dot(a, b))
    if s < 1e-9:
        return np.eye(3) if cph > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - cph) / (s * s))


R = R_align(n, np.array([0.0, 0.0, 1.0]))
p1 = (R @ p.T).T
if np.median(p1[:, 2]) < 0:
    R = R_align(-n, np.array([0.0, 0.0, 1.0])); p1 = (R @ p.T).T
horiz = np.percentile(p1[:, :2], 97, 0) - np.percentile(p1[:, :2], 3, 0)
s = (TARGET_M * 100.0) / float(np.max(horiz))   # -> cm
p2 = s * p1
t2 = np.array([-np.median(p2[:, 0]), -np.median(p2[:, 1]), -np.percentile(p2[:, 2], 1.0)])

M = np.eye(4)
M[:3, :3] = s * R
M[:3, 3] = -s * (R @ c) + t2
q = (M[:3, :3] @ V.T).T + M[:3, 3]
json.dump({"transform": M.tolist(),
           "ue_bounds_cm": [list(np.round(q.min(0), 1)), list(np.round(q.max(0), 1))]},
          open(out, "w"), indent=1)
print("M written to", out, "UE bounds cm:", np.round(q.min(0), 1), np.round(q.max(0), 1))
