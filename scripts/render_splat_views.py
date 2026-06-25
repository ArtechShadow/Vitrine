"""Render RGB views of a trained 3DGS splat from real COLMAP camera poses (gsplat, GPU).

The highest-fidelity *captured colour* product for a room/scene is the Gaussian splat
itself — not a baked mesh texture (Blender's Smart-UV bake collapses on messy MILo room
meshes; see memory ue-captured-color-and-bake). This renders the splat from genuine
captured camera extrinsics, so every viewpoint is guaranteed to look into the scene.

Robust to SH degree (reads the actual f_rest count and renders at that degree) and to
binary COLMAP models (shells out to `colmap model_converter` for a TXT view if needed).

Usage:
  python scripts/render_splat_views.py \
      --ply  /data/output/scene02/model/splat_30000.ply \
      --colmap /data/output/scene02/colmap/undistorted/sparse/0 \
      --out-dir /data/output/scene02/exhibit/splat_views \
      --n-views 6
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from plyfile import PlyData

# f_rest count -> SH degree
_SH_BY_REST = {0: 0, 9: 1, 24: 2, 45: 3}


def load_splat(ply_path, device):
    ply = PlyData.read(ply_path)
    v = ply.elements[0]
    n = v.count
    names = {p.name for p in v.properties}

    xyz = np.stack([v["x"], v["y"], v["z"]], -1).astype(np.float32)
    opac = v["opacity"].astype(np.float32)
    scales = np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], -1).astype(np.float32)
    rots = np.stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], -1).astype(np.float32)

    n_rest = sum(1 for k in names if k.startswith("f_rest_"))
    sh_deg = _SH_BY_REST.get(n_rest)
    if sh_deg is None:  # unexpected layout -> floor to a known degree
        sh_deg = 3 if n_rest >= 45 else (2 if n_rest >= 24 else (1 if n_rest >= 9 else 0))
        n_rest = {0: 0, 1: 9, 2: 24, 3: 45}[sh_deg]
    n_coef = (sh_deg + 1) ** 2  # incl DC

    dc = np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], -1).astype(np.float32).reshape(n, 1, 3)
    if n_rest:
        rest = np.zeros((n, n_rest), np.float32)
        for i in range(n_rest):
            rest[:, i] = v[f"f_rest_{i}"].astype(np.float32)
        rest = rest.reshape(n, n_coef - 1, 3)
        shs = np.concatenate([dc, rest], axis=1)  # [N, n_coef, 3]
    else:
        shs = dc

    means = torch.from_numpy(xyz).to(device)
    quats = torch.from_numpy(rots).to(device)
    quats = quats / quats.norm(dim=-1, keepdim=True)
    scales_t = torch.exp(torch.from_numpy(scales).to(device))
    opac_t = torch.sigmoid(torch.from_numpy(opac).to(device))
    colors = torch.from_numpy(shs).to(device)
    return means, quats, scales_t, opac_t, colors, sh_deg, n


def _ensure_txt_model(colmap_dir):
    """Return a dir holding cameras.txt/images.txt, converting from .bin if needed."""
    d = Path(colmap_dir)
    if (d / "images.txt").exists() and (d / "cameras.txt").exists():
        return str(d), None
    tmp = tempfile.mkdtemp(prefix="colmap_txt_")
    subprocess.run(
        ["colmap", "model_converter", "--input_path", str(d),
         "--output_path", tmp, "--output_type", "TXT"],
        check=True, capture_output=True,
    )
    return tmp, tmp


def parse_cameras(path):
    cams = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        cid, model, w, h = int(p[0]), p[1], int(p[2]), int(p[3])
        params = [float(x) for x in p[4:]]
        if model in ("PINHOLE",):
            fx, fy, cx, cy = params[0], params[1], params[2], params[3]
        elif model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL"):
            fx = fy = params[0]; cx, cy = params[1], params[2]
        else:  # fallback: first param as focal
            fx = fy = params[0]; cx, cy = w / 2.0, h / 2.0
        cams[cid] = dict(w=w, h=h, fx=fx, fy=fy, cx=cx, cy=cy)
    return cams


def parse_images(path):
    """World-to-camera viewmats + camera id + name, one per registered image."""
    out = []
    lines = open(path).readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        p = line.split()
        if len(p) >= 10:
            qw, qx, qy, qz = (float(p[1]), float(p[2]), float(p[3]), float(p[4]))
            tx, ty, tz = float(p[5]), float(p[6]), float(p[7])
            cid = int(p[8]); name = p[9]
            q = np.array([qw, qx, qy, qz]); q /= np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
            ], np.float32)
            vm = np.eye(4, dtype=np.float32); vm[:3, :3] = R; vm[:3, 3] = [tx, ty, tz]
            out.append(dict(viewmat=vm, cam=cid, name=name))
            i += 2  # skip the POINTS2D line
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True)
    ap.add_argument("--colmap", required=True, help="sparse model dir (.bin or .txt)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-views", type=int, default=6)
    ap.add_argument("--max-dim", type=int, default=1600, help="cap render width for speed")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    device = torch.device("cuda:0")
    from gsplat import rasterization
    from PIL import Image

    txt_dir, cleanup = _ensure_txt_model(args.colmap)
    cams = parse_cameras(os.path.join(txt_dir, "cameras.txt"))
    imgs = parse_images(os.path.join(txt_dir, "images.txt"))
    imgs.sort(key=lambda r: r["name"])
    if not imgs:
        print("No registered images found", file=sys.stderr); sys.exit(1)

    # Evenly sample n views across the (name-sorted) capture sequence for varied vantage.
    n = min(args.n_views, len(imgs))
    idx = np.linspace(0, len(imgs) - 1, n).round().astype(int)

    means, quats, scales, opac, colors, sh_deg, ng = load_splat(args.ply, device)
    print(f"loaded {ng:,} gaussians, sh_degree={sh_deg}, VRAM={torch.cuda.memory_allocated()/1e9:.1f}GB")

    for k, ii in enumerate(idx):
        rec = imgs[int(ii)]
        c = cams[rec["cam"]]
        scale = min(1.0, args.max_dim / max(c["w"], c["h"]))
        W, H = int(round(c["w"] * scale)), int(round(c["h"] * scale))
        K = torch.tensor([[c["fx"] * scale, 0, c["cx"] * scale],
                          [0, c["fy"] * scale, c["cy"] * scale],
                          [0, 0, 1]], dtype=torch.float32, device=device)
        vm = torch.from_numpy(rec["viewmat"]).unsqueeze(0).to(device)
        with torch.no_grad():
            rgb, _, _ = rasterization(
                means=means, quats=quats, scales=scales, opacities=opac, colors=colors,
                viewmats=vm, Ks=K.unsqueeze(0), width=W, height=H,
                near_plane=0.01, far_plane=100.0, sh_degree=sh_deg,
                render_mode="RGB", packed=True, rasterize_mode="antialiased",
            )
        img = np.clip(rgb[0].cpu().numpy(), 0, 1)
        out = os.path.join(args.out_dir, f"view_{k:02d}_{Path(rec['name']).stem}.png")
        Image.fromarray((img * 255).astype(np.uint8)).save(out)
        print(f"  [{k+1}/{n}] {out}  ({W}x{H} from {rec['name']})")

    if cleanup:
        import shutil; shutil.rmtree(cleanup, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
