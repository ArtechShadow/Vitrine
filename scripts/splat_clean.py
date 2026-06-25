"""Clean a 3DGS .ply for NanoGS / UE import (a scripted SuperSplat substitute):
drop low-opacity floaters + spatial statistical outliers, but KEEP every gaussian
attribute (x,y,z,nx..,f_dc,f_rest[45],opacity,scale[3],rot[4]) so the splat still
renders correctly. CPU-only — safe to run alongside a GPU train.

  python splat_clean.py <in.ply> <out.ply> [opacity_thresh=0.10] [nb=20] [std=2.0]

Run in the `come` container (has plyfile / open3d / numpy)."""
import sys
import numpy as np
from plyfile import PlyData, PlyElement

inp, outp = sys.argv[1], sys.argv[2]
op_th = float(sys.argv[3]) if len(sys.argv) > 3 else 0.10
nb = int(sys.argv[4]) if len(sys.argv) > 4 else 20
std = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
scale_drop = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0  # drop top-% largest-scale splats (floaters); 0=off
aniso_max = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0   # drop splats with axis-ratio above this; 0=off

print(f"[read] {inp}", flush=True)
ply = PlyData.read(inp)
data = ply["vertex"].data
n0 = len(data)

# opacity is stored as a logit -> sigmoid; floaters are typically low-opacity haze
op = 1.0 / (1.0 + np.exp(-np.asarray(data["opacity"], dtype=np.float64)))
keep = op > op_th
print(f"[opacity>{op_th}] {int(keep.sum()):,}/{n0:,}", flush=True)
idx = np.where(keep)[0]

# scale / anisotropy prune — long-axis "spiky" floaters that opacity alone misses
# (the boundary streaks in the NanoGS splat render). Operates on stored log-scales.
if (scale_drop > 0 or aniso_max > 0) and "scale_0" in data.dtype.names:
    sc = np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], axis=1)[idx].astype(np.float64)
    max_log = sc.max(axis=1)
    max_scale = np.exp(max_log)
    aniso = np.exp(max_log - sc.min(axis=1))
    keep2 = np.ones(len(idx), bool)
    if scale_drop > 0:
        keep2 &= max_scale <= np.percentile(max_scale, 100.0 - scale_drop)
    if aniso_max > 0:
        keep2 &= aniso <= aniso_max
    idx = idx[keep2]
    print(f"[scale-prune drop_top={scale_drop}% aniso<={aniso_max}] -> {len(idx):,}", flush=True)

# spatial statistical-outlier removal on the surviving points (kills isolated floaters)
xyz = np.stack([data["x"], data["y"], data["z"]], axis=1)[idx].astype(np.float64)
try:
    import open3d as o3d
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(xyz)
    _, ind = pc.remove_statistical_outlier(nb_neighbors=nb, std_ratio=std)
    idx = idx[np.asarray(ind)]
    print(f"[outlier nb={nb} std={std}] -> {len(idx):,}", flush=True)
except Exception as e:
    print(f"[outlier skipped] {e}", flush=True)

out = data[idx]  # structured-array subset preserves ALL properties
PlyData([PlyElement.describe(out, "vertex")], text=False).write(outp)
print(f"[WROTE] {outp}  {len(out):,}/{n0:,} ({100.0*len(out)/n0:.1f}% kept)", flush=True)
