"""CoMe TSDF mesh extraction, OOM-proofed + parameterised.

Upstream extract_mesh_tsdf.py hardcodes the Open3D VoxelBlockGrid on CUDA:0 with
block_count=50000, so a fine voxel rehashes past 48 GB VRAM and OOMs (it died at
frame 7/750 at voxel 0.002). This variant:
  * --device CPU:0     -> volume lives in host RAM (251 GB here) -> no VRAM ceiling,
                          render still runs on the GPU (cuda:0), only fusion is CPU.
  * --block_count       -> pre-size the hash map to avoid rehash stalls.
  * --voxel_size        -> go as fine as RAM allows.
  * --out_ply           -> distinct output per job (parallel sweep over two GPUs).
  * --depth_max         -> frustum/integration far clip (world units).
Per-frame debug PNG dumps (depths/, rgb_) are removed (they only slowed the loop).

Drop into /opt/come and run with cwd=/opt/come so CoMe's local modules resolve:
  cd /opt/come && conda run -n come python come_extract_tsdf_lowmem.py \
    -m <model_path> --device CPU:0 --voxel_size 0.005 --block_count 250000 \
    --out_ply <model_path>/test/ours_30000/tsdf_v0050.ply
"""
import torch
from scene import Scene
import os
from os import makedirs
from gaussian_renderer import render
import random
from tqdm import tqdm
from argparse import ArgumentParser
from arguments import ModelParams, PipelineParams, get_combined_args
from gaussian_renderer import GaussianModel
import numpy as np
import open3d as o3d
import open3d.core as o3c
import math
from arguments import ModelParams, PipelineParams, OptimizationParams, SplattingSettings


def tsdf_fusion(model_path, name, iteration, views, gaussians, pipeline, background,
                splat_args, voxel_size, device, block_count, out_ply, depth_max,
                block_resolution):
    render_path = os.path.join(model_path, name, "ours_{}".format(iteration))
    makedirs(render_path, exist_ok=True)
    o3d_device = o3d.core.Device(device)
    ALPHA_THRESH = 0.5
    # NB: block_count is a HARD pre-allocated cap in Open3D's VoxelBlockGrid, NOT a
    # grow-on-demand hint. Exceeding it corrupts the hash backend -> segfault (CPU) /
    # OOM (CUDA). Must be >= total blocks the scene needs at this voxel. block_resolution
    # 8 (vs 16) keeps each block 8x smaller (~10KB vs ~80KB) so a huge safety cap is cheap.
    print(f"VBG device={device} voxel={voxel_size} block_res={block_resolution} "
          f"block_count={block_count} depth_max={depth_max} -> {out_ply}", flush=True)

    vbg = o3d.t.geometry.VoxelBlockGrid(
        attr_names=('tsdf', 'weight', 'color'),
        attr_dtypes=(o3c.float32, o3c.float32, o3c.float32),
        attr_channels=((1), (1), (3)),
        voxel_size=voxel_size,
        block_resolution=block_resolution,
        block_count=block_count,
        device=o3d_device)

    with torch.no_grad():
        for _, view in enumerate(tqdm(views, desc="Rendering progress")):
            rendering = render(view, gaussians, pipeline, background, splat_args=splat_args)["render"]
            depth = rendering[6:7, :, :]
            alpha = rendering[7:8, :, :]
            rgb = rendering[:3, :, :]

            if view.gt_alpha_mask is not None:
                depth[(view.gt_alpha_mask < ALPHA_THRESH)] = 0
            depth[(alpha < ALPHA_THRESH)] = 0

            W = view.image_width
            H = view.image_height
            ndc2pix = torch.tensor([
                [W / 2, 0, 0, (W - 1) / 2],
                [0, H / 2, 0, (H - 1) / 2],
                [0, 0, 0, 1]]).float().cuda().T
            intrins = (view.projection_matrix @ ndc2pix)[:3, :3].T
            intrinsic = o3d.camera.PinholeCameraIntrinsic(
                width=W, height=H,
                cx=intrins[0, 2].item(), cy=intrins[1, 2].item(),
                fx=intrins[0, 0].item(), fy=intrins[1, 1].item())

            extrinsic = np.asarray((view.world_view_transform.T).cpu().numpy())

            o3d_color = o3d.t.geometry.Image(np.asarray(rgb.permute(1, 2, 0).cpu().numpy(), order="C"))
            o3d_depth = o3d.t.geometry.Image(np.asarray(depth.permute(1, 2, 0).cpu().numpy(), order="C"))
            o3d_color = o3d_color.to(o3d_device)
            o3d_depth = o3d_depth.to(o3d_device)

            intrinsic = o3d.core.Tensor(intrinsic.intrinsic_matrix, o3d.core.Dtype.Float64)
            extrinsic = o3d.core.Tensor(extrinsic, o3d.core.Dtype.Float64)

            frustum_block_coords = vbg.compute_unique_block_coordinates(
                o3d_depth, intrinsic, extrinsic, 1.0, depth_max)
            vbg.integrate(frustum_block_coords, o3d_depth, o3d_color, intrinsic,
                          intrinsic, extrinsic, 1.0, depth_max)

        try:
            active = vbg.hashmap().size()
            print(f"active_blocks={active} / cap={block_count} "
                  f"({100.0 * active / block_count:.1f}% of cap)", flush=True)
        except Exception as e:
            print(f"(could not query active block count: {e})", flush=True)
        print("Extract Mesh", flush=True)
        mesh = vbg.extract_triangle_mesh().to_legacy()
        out = out_ply if out_ply else f"{render_path}/tsdf.ply"
        o3d.io.write_triangle_mesh(out, mesh)
        print(f"Mesh Extracted: {out}  verts={len(mesh.vertices)} tris={len(mesh.triangles)}", flush=True)


def extract_mesh(dataset, iteration, pipeline, splat_args, voxel_size, device,
                 block_count, out_ply, depth_max, block_resolution):
    with torch.no_grad():
        dataset.init_type = "sfm"
        dataset.depths = ""
        gaussians = GaussianModel(dataset.sh_degree)
        scene = Scene(dataset, gaussians, load_iteration=iteration, shuffle=False)
        train_cameras = scene.getTrainCameras()
        gaussians.load_ply(os.path.join(dataset.model_path, "point_cloud",
                                        f"iteration_{iteration}", "point_cloud.ply"))
        bg_color = [1, 1, 1] if dataset.white_background else [0, 0, 0]
        background = torch.tensor(bg_color, dtype=torch.float32, device="cuda")
        pipeline.convert_SBs_python = gaussians.use_SBs  # hotfix
        cams = train_cameras
        gaussians.compute_3D_filter(cams)
        tsdf_fusion(dataset.model_path, "test", iteration, cams, gaussians, pipeline,
                    background, splat_args, voxel_size, device, block_count, out_ply,
                    depth_max, block_resolution)


if __name__ == "__main__":
    parser = ArgumentParser(description="OOM-proofed CoMe TSDF extraction")
    model = ModelParams(parser, sentinel=True)
    pipeline = PipelineParams(parser)
    ss = SplattingSettings(parser, render=True)
    parser.add_argument("--iteration", default=30_000, type=int)
    parser.add_argument("--voxel_size", type=float, default=0.005)
    parser.add_argument("--device", type=str, default="CUDA:0")
    parser.add_argument("--block_count", type=int, default=50000)
    parser.add_argument("--block_resolution", type=int, default=16)
    parser.add_argument("--out_ply", type=str, default="")
    parser.add_argument("--depth_max", type=float, default=6.0)
    args = get_combined_args(parser)

    print("Rendering " + args.model_path, flush=True)
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    torch.cuda.set_device(torch.device("cuda:0"))
    splat_args = ss.get_settings(args)
    extract_mesh(model.extract(args), args.iteration, pipeline.extract(args), splat_args,
                 voxel_size=args.voxel_size, device=args.device, block_count=args.block_count,
                 out_ply=args.out_ply, depth_max=args.depth_max,
                 block_resolution=args.block_resolution)
