#!/usr/bin/env python3
"""Fast TSDF room mesh from the trained splat: render RGB+expected-depth from the
REAL COLMAP poses (gsplat) and fuse with Open3D ScalableTSDFVolume. This meshes the
*observed surfaces* (walls/floor/objects), not gaussian centres, so it is far cleaner
than Poisson-over-centres. Output is transformed into the UE frame via manifest M.

  python scripts/tsdf_room.py --ply model/splat_30000.ply \
      --colmap colmap/undistorted/sparse/0 --manifest scene/manifest.json \
      --out scene/room_tsdf.ply --max-dim 960 --stride 1
Runs in gaussian-toolkit (gsplat + open3d). GPU render is low-res/short -> low heat.
"""
import os, sys, json, argparse
import numpy as np
import torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_splat_views import load_splat, _ensure_txt_model, parse_cameras, parse_images
import open3d as o3d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True)
    ap.add_argument("--colmap", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-dim", type=int, default=960)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--voxel", type=float, default=0.02, help="world units")
    ap.add_argument("--trunc", type=float, default=0.08)
    ap.add_argument("--depth-trunc", type=float, default=25.0)
    ap.add_argument("--alpha-thr", type=float, default=0.6)
    args = ap.parse_args()

    device = torch.device("cuda:0")
    from gsplat import rasterization

    txt_dir, cleanup = _ensure_txt_model(args.colmap)
    cams = parse_cameras(os.path.join(txt_dir, "cameras.txt"))
    imgs = parse_images(os.path.join(txt_dir, "images.txt"))
    imgs.sort(key=lambda r: r["name"])
    imgs = imgs[:: args.stride]
    means, quats, scales, opac, colors, sh_deg, ng = load_splat(args.ply, device)
    print(f"loaded {ng:,} gaussians sh={sh_deg}; fusing {len(imgs)} views", flush=True)

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=args.voxel, sdf_trunc=args.trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)

    for k, rec in enumerate(imgs):
        c = cams[rec["cam"]]
        scale = min(1.0, args.max_dim / max(c["w"], c["h"]))
        W, H = int(round(c["w"] * scale)), int(round(c["h"] * scale))
        fx, fy, cx, cy = c["fx"] * scale, c["fy"] * scale, c["cx"] * scale, c["cy"] * scale
        K = torch.tensor([[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
                         dtype=torch.float32, device=device)
        vm = torch.from_numpy(rec["viewmat"]).unsqueeze(0).to(device)
        with torch.no_grad():
            out, alpha, _ = rasterization(
                means=means, quats=quats, scales=scales, opacities=opac, colors=colors,
                viewmats=vm, Ks=K.unsqueeze(0), width=W, height=H,
                near_plane=0.05, far_plane=100.0, sh_degree=sh_deg,
                render_mode="RGB+ED", packed=True, rasterize_mode="antialiased")
        rgb = out[0, ..., :3].clamp(0, 1).cpu().numpy()
        depth = out[0, ..., 3].cpu().numpy().astype(np.float32)
        a = alpha[0, ..., 0].cpu().numpy()
        depth[(a < args.alpha_thr) | (depth <= 0) | (depth > args.depth_trunc)] = 0.0
        color8 = np.ascontiguousarray((rgb * 255).astype(np.uint8))
        ci = o3d.geometry.Image(color8)
        di = o3d.geometry.Image(np.ascontiguousarray(depth))
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            ci, di, depth_scale=1.0, depth_trunc=args.depth_trunc,
            convert_rgb_to_intensity=False)
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, fx, fy, cx, cy)
        volume.integrate(rgbd, intr, rec["viewmat"].astype(np.float64))
        if k % 20 == 0:
            print(f"  [{k+1}/{len(imgs)}] integrated ({W}x{H})", flush=True)

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    print(f"raw TSDF mesh V={len(mesh.vertices):,} F={len(mesh.triangles):,}", flush=True)

    # drop tiny floating clusters (keep components with >0.5% of faces)
    tri_ids, counts, _ = mesh.cluster_connected_triangles()
    tri_ids = np.asarray(tri_ids); counts = np.asarray(counts)
    keep = counts >= max(50, int(0.005 * counts.sum()))
    mesh.remove_triangles_by_mask(~keep[tri_ids])
    mesh.remove_unreferenced_vertices()

    if args.manifest and args.manifest.lower() != "none" and os.path.exists(args.manifest):
        M = np.array(json.load(open(args.manifest))["transform"], dtype=np.float64)
        mesh.transform(M)   # COLMAP -> UE frame
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(args.out, mesh)
    bb = mesh.get_axis_aligned_bounding_box()
    print(f"[done] {args.out} V={len(mesh.vertices):,} F={len(mesh.triangles):,}", flush=True)
    print(f"  UE bounds cm: min={np.round(bb.min_bound,1)} max={np.round(bb.max_bound,1)}", flush=True)
    if cleanup:
        import shutil; shutil.rmtree(cleanup, ignore_errors=True)


if __name__ == "__main__":
    main()
