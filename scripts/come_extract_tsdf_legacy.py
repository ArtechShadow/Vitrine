"""CoMe TSDF extraction via Open3D's LEGACY ScalableTSDFVolume (the stable path).

The new tensor VoxelBlockGrid (extract_mesh_tsdf.py) crashes in extract_triangle_mesh()
once the grid gets large: at voxel 0.006 (735,967 blocks) it abort/segfaults on BOTH
CUDA and CPU at the identical step -> an Open3D 0.19 size/overflow bug in the new API,
not a memory limit. The legacy pipelines.integration.ScalableTSDFVolume is CPU-based,
years-hardened, hashes 16^3 voxel blocks (memory ~ surface area, fits 251 GB RAM easily),
and its extract_triangle_mesh handles large meshes. Render still runs on the GPU (cuda:0);
only fusion + extraction are CPU. Two of these run one-per-GPU in parallel.

  cd /opt/come && conda run -n come python come_extract_tsdf_legacy.py \
    -m <model_path> --voxel_size 0.005 --depth_max 6.0 \
    --out_ply <model_path>/test/ours_30000/tsdf_v0050.ply
"""
import torch
from scene import Scene
import os
from gaussian_renderer import render, GaussianModel
import random
from argparse import ArgumentParser
from arguments import ModelParams, PipelineParams, get_combined_args, SplattingSettings
import numpy as np
import open3d as o3d
from tqdm import tqdm


def tsdf_legacy(views, gaussians, pipeline, background, splat_args,
                voxel_size, out_ply, depth_max, sdf_trunc):
    print(f"LEGACY ScalableTSDFVolume voxel={voxel_size} sdf_trunc={sdf_trunc} "
          f"depth_max={depth_max} -> {out_ply}", flush=True)
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel_size, sdf_trunc=sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    ALPHA_THRESH = 0.5
    with torch.no_grad():
        for view in tqdm(views, desc="TSDF integrate"):
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
                W, H, intrins[0, 0].item(), intrins[1, 1].item(),
                intrins[0, 2].item(), intrins[1, 2].item())
            extrinsic = np.asarray((view.world_view_transform.T).cpu().numpy())

            color_np = np.ascontiguousarray(
                (rgb.permute(1, 2, 0).clamp(0, 1).cpu().numpy() * 255).astype(np.uint8))
            depth_np = np.ascontiguousarray(
                depth.permute(1, 2, 0).squeeze(-1).cpu().numpy().astype(np.float32))
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(color_np), o3d.geometry.Image(depth_np),
                depth_scale=1.0, depth_trunc=depth_max, convert_rgb_to_intensity=False)
            volume.integrate(rgbd, intrinsic, extrinsic)

    print("Extract Mesh (legacy)", flush=True)
    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(out_ply, mesh)
    print(f"Mesh Extracted: {out_ply}  verts={len(mesh.vertices)} tris={len(mesh.triangles)}", flush=True)


def extract_mesh(dataset, iteration, pipeline, splat_args, voxel_size, out_ply, depth_max, sdf_trunc):
    with torch.no_grad():
        dataset.init_type = "sfm"
        dataset.depths = ""
        gaussians = GaussianModel(dataset.sh_degree)
        scene = Scene(dataset, gaussians, load_iteration=iteration, shuffle=False)
        cams = scene.getTrainCameras()
        gaussians.load_ply(os.path.join(dataset.model_path, "point_cloud",
                                        f"iteration_{iteration}", "point_cloud.ply"))
        bg_color = [1, 1, 1] if dataset.white_background else [0, 0, 0]
        background = torch.tensor(bg_color, dtype=torch.float32, device="cuda")
        pipeline.convert_SBs_python = gaussians.use_SBs  # hotfix
        gaussians.compute_3D_filter(cams)
        tsdf_legacy(cams, gaussians, pipeline, background, splat_args,
                    voxel_size, out_ply, depth_max, sdf_trunc)


if __name__ == "__main__":
    parser = ArgumentParser(description="Legacy ScalableTSDFVolume CoMe extraction")
    model = ModelParams(parser, sentinel=True)
    pipeline = PipelineParams(parser)
    ss = SplattingSettings(parser, render=True)
    parser.add_argument("--iteration", default=30_000, type=int)
    parser.add_argument("--voxel_size", type=float, default=0.005)
    parser.add_argument("--out_ply", type=str, default="")
    parser.add_argument("--depth_max", type=float, default=6.0)
    parser.add_argument("--sdf_trunc", type=float, default=0.0)  # 0 -> 5x voxel
    args = get_combined_args(parser)

    print("Rendering " + args.model_path, flush=True)
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    torch.cuda.set_device(torch.device("cuda:0"))
    splat_args = ss.get_settings(args)
    sdf_trunc = args.sdf_trunc if args.sdf_trunc > 0 else 5.0 * args.voxel_size
    out_ply = args.out_ply if args.out_ply else os.path.join(args.model_path, "test",
                                                              f"ours_{args.iteration}", "tsdf.ply")
    extract_mesh(model.extract(args), args.iteration, pipeline.extract(args), splat_args,
                 voxel_size=args.voxel_size, out_ply=out_ply, depth_max=args.depth_max,
                 sdf_trunc=sdf_trunc)
