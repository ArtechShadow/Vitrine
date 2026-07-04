"""Convert a 3DGS gaussian PLY (CoMe/LichtFeld) to a colored point cloud in UE-cm, so
UE's built-in LidarPointCloud plugin can render the room's (fair) splat appearance even
though UE has no native Gaussian-splat importer. Colour = SH DC term; low-opacity
gaussians dropped; positions transformed by the same COLMAP->UE-cm matrix as the room mesh
so the cloud aligns with the placed objects.

  python3 gaussian_to_ue_pointcloud.py <gaussians.ply> <ue_transform.json> <out_pointcloud.ply> [opacity_thresh]
"""
import sys, json
import numpy as np
from plyfile import PlyData, PlyElement

IN, MJSON, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
OP_THRESH = float(sys.argv[4]) if len(sys.argv) > 4 else 0.15
SH_C0 = 0.28209479177387814

p = PlyData.read(IN)
v = p["vertex"].data
xyz = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)
fdc = np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], 1).astype(np.float64)
rgb = np.clip(0.5 + SH_C0 * fdc, 0, 1)
op = 1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float64))) if "opacity" in v.dtype.names else np.ones(len(xyz))
keep = op > OP_THRESH
print(f"loaded {len(xyz):,} gaussians; kept {int(keep.sum()):,} (opacity>{OP_THRESH})", flush=True)
xyz, rgb = xyz[keep], rgb[keep]

M = np.asarray(json.load(open(MJSON))["transform"], dtype=np.float64)
R, t = M[:3, :3], M[:3, 3]
q = (R @ xyz.T).T + t  # -> UE-cm, aligned with the room mesh + placed objects
print(f"UE-cm bounds: min {np.round(q.min(0),1)} max {np.round(q.max(0),1)}", flush=True)

rgb8 = (rgb * 255.0).astype(np.uint8)
verts = np.empty(len(q), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"),
                                ("red", "u1"), ("green", "u1"), ("blue", "u1")])
verts["x"], verts["y"], verts["z"] = q[:, 0], q[:, 1], q[:, 2]
verts["red"], verts["green"], verts["blue"] = rgb8[:, 0], rgb8[:, 1], rgb8[:, 2]
PlyData([PlyElement.describe(verts, "vertex")], text=False).write(OUT)
print(f"DONE -> {OUT}  {len(q):,} colored points", flush=True)
