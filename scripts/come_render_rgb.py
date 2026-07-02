"""Render the CoMe-trained room splat to RGB from a few training views, to judge the
room's appearance-as-splat (vs the lumpy TSDF mesh). Saves splat_view_*.png.

  cd /opt/come && conda run -n come python come_render_rgb.py -m <model_path>
"""
import torch, os
from scene import Scene
from gaussian_renderer import render, GaussianModel
from argparse import ArgumentParser
from arguments import ModelParams, PipelineParams, get_combined_args, SplattingSettings
from torchvision.utils import save_image
import random, numpy as np

parser = ArgumentParser()
model = ModelParams(parser, sentinel=True)
pipeline = PipelineParams(parser)
ss = SplattingSettings(parser, render=True)
parser.add_argument("--iteration", default=30000, type=int)
parser.add_argument("--outdir", default="/data/output/dreamlab/locked/splat_qa")
args = get_combined_args(parser)
random.seed(0); np.random.seed(0); torch.manual_seed(0)
torch.cuda.set_device(torch.device("cuda:0"))
splat_args = ss.get_settings(args)

ds = model.extract(args)
ds.init_type = "sfm"; ds.depths = ""
with torch.no_grad():
    g = GaussianModel(ds.sh_degree)
    scene = Scene(ds, g, load_iteration=args.iteration, shuffle=False)
    cams = scene.getTrainCameras()
    g.load_ply(os.path.join(ds.model_path, "point_cloud", f"iteration_{args.iteration}", "point_cloud.ply"))
    bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
    pipe = pipeline.extract(args)
    pipe.convert_SBs_python = g.use_SBs
    g.compute_3D_filter(cams)
    os.makedirs(args.outdir, exist_ok=True)
    n = len(cams)
    for i in [0, n // 5, 2 * n // 5, 3 * n // 5, 4 * n // 5]:
        out = render(cams[i], g, pipe, bg, splat_args=splat_args)["render"]
        save_image(out[:3].clamp(0, 1), os.path.join(args.outdir, f"splat_view_{i:04d}.png"))
        print("saved splat_view", i, flush=True)
    print("RGB_DONE", flush=True)
