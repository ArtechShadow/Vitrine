# Fabricate ArtiFixer's caption.h5 WITHOUT the 30B Qwen3-VL captioner: run prepare's
# `caption` phase but monkeypatch the VLM model load + generate_caption() to return a
# fixed scene caption. All real logic (eval_scene_dir paths, image indices, UMT5 encode,
# h5 layout) is reused, so the file is format-identical. Only the small UMT5 text encoder
# loads (~5.5GB) -> phased VRAM, freed on exit before the 14B enhance.
#   cd /workspace && python artifixer_fab_caption.py
import sys
sys.path.insert(0, "/workspace")

L = "/workspace/output/dreamlab/locked/artifixer"
sys.argv = ["prep",
            "--colmap_dir", "/workspace/output/dreamlab/locked/colmap/undistorted",
            "--output_root", L + "/prep",
            "--selected_image_names_file", L + "/selected_train_images.txt",
            "--phases", "caption",
            "--reconstruction_steps", "10000"]

FIXED = ("A cluttered workshop room interior: a wooden chair, an industrial wet/dry vacuum "
         "cleaner, stacked tool cases and a workbench on a wooden floor, dust-sheeted walls, "
         "soft daylight from a window. Realistic, detailed, photographic interior scene.")

import data_processing.captioning.generate_captions as gc


class _Stub:
    device = "cuda"
    def __init__(self, *a, **k): pass
    def to(self, *a, **k): return self
    def generate(self, *a, **k): return None


gc.Qwen3VLMoeForConditionalGeneration = type(
    "Q", (), {"from_pretrained": staticmethod(lambda *a, **k: _Stub())})
gc.Qwen3VLProcessor = type(
    "P", (), {"from_pretrained": staticmethod(lambda *a, **k: _Stub())})
gc.generate_caption = lambda images, fps, model, processor: FIXED

import runpy
runpy.run_module("data_processing.prepare_colmap_artifixer_inputs", run_name="__main__")
