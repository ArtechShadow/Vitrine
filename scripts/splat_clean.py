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

print(f"[read] {inp}", flush=True)
ply = PlyData.read(inp)
data = ply["vertex"].data
n0 = len(data)

# opacity is stored as a logit -> sigmoid; floaters are typically low-opacity haze
op = 1.0 / (1.0 + np.exp(-np.asarray(data["opacity"], dtype=np.float64)))
keep = op > op_th
print(f"[opacity>{op_th}] {int(keep.sum()):,}/{n0:,}", flush=True)
idx = np.where(keep)[0]

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
