#!/usr/bin/env python3
"""Compute UE placement (location + target size) for each reconstructed object from
its gaussian PLY centroid/bbox, transformed by the room's COLMAP->UE matrix M. The
per-object Hunyuan3D mesh is normalised, so the UE assembler scales it so its bounds
match `target_size_cm` and sets its location to `location_cm`. Orientation defaults
to upright (yaw 0) — a first pass; refine per-object later.

  python3 compute_placements.py <objects_dir> <ue_transform.json> <out_placements.json>
Run in gaussian-toolkit (open3d/plyfile present).
"""
import sys, os, json, glob
import numpy as np
from plyfile import PlyData

objdir, mjson, out = sys.argv[1], sys.argv[2], sys.argv[3]
M = np.array(json.load(open(mjson))["transform"], dtype=np.float64)


def load_xyz(path, op_thr=0.2):
    v = PlyData.read(path)["vertex"].data
    xyz = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)
    if "opacity" in v.dtype.names:
        op = 1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float64)))
        xyz = xyz[op > op_thr]
    return xyz


def apply(M, xyz):
    return (M[:3, :3] @ xyz.T).T + M[:3, 3]


placements = {}
for p in sorted(glob.glob(os.path.join(objdir, "*.ply"))):
    name = os.path.splitext(os.path.basename(p))[0]
    try:
        xyz = load_xyz(p)
        if len(xyz) < 100:
            print("skip", name, "(too few pts)"); continue
        q = apply(M, xyz)                       # -> UE cm frame
        # robust bounds (1-99 pct) to ignore floaters
        lo = np.percentile(q, 1, 0); hi = np.percentile(q, 99, 0)
        ctr = (lo + hi) / 2.0
        size = float(np.max(hi - lo))           # largest UE-cm extent
        placements[name] = {
            "location_cm": [round(float(x), 1) for x in ctr],
            "target_size_cm": round(size, 1),
            "floor_z_cm": round(float(np.percentile(q[:, 2], 2)), 1),
            "n_pts": int(len(xyz)),
        }
        print(f"{name:16s} loc={placements[name]['location_cm']} size={size:.0f}cm")
    except Exception as e:
        print("FAIL", name, str(e)[:80])

json.dump(placements, open(out, "w"), indent=1)
print("wrote", out, "with", len(placements), "placements")
