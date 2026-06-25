# ArtiFixer — single-48GB-GPU OOM fix

ArtiFixer ([nv-tlabs/ArtiFixer](https://github.com/nv-tlabs/ArtiFixer), vendored as the
`docker/artifixer/ArtiFixer` submodule) OOMs on a 48 GB GPU out of the box. This patch makes the **14B
enhance fit on a single RTX 6000 Ada** (peak ~45.5 GB, validated 2026-06-25).

A clean `--recurse-submodules` clone pulls pristine upstream code, so the fix must be re-applied:

```bash
cd docker/artifixer/ArtiFixer
git apply ../patches/vitrine-ada-48gb-oom-fix.patch
pip install -U "diffusers==0.38.0"      # tiled Wan VAE (PR #12521)
```

All changes are **env-gated** (off by default, upstream behaviour preserved). Validated-fit run:

```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:256 \
ARTIFIXER_VAE_TILING=1 ARTIFIXER_ENHANCE_DOWNSCALE=4 \
python -m model_eval.run_inference --evalset reconstructed_colmap --inference_pipeline kv_cache \
  --checkpoint_pt /workspace/ckpt/artifixer-14b.pt --split_path <prep>/split.json \
  --save_dir <out>/corrected --render_trajectory val_frames \
  --num_views 2 --frames_per_block 2 --sink_size 3 --local_attn_size 6 \
  --max_neighbors_per_encode 1 --save_frame_outputs_only --replace_if_exists
```

**The "VAE decode OOM" was three separate walls** — full diagnosis in
[`ARTIFIXER_OOM_NOTES.md`](ARTIFIXER_OOM_NOTES.md):
1. **VAE encode** `F.pad` OOM → `vae.enable_tiling()` (needs diffusers ≥ 0.38.0).
2. **3DGRUT trajectory render** eagerly moved all 750 full-res ray-grids to GPU (~46 GB) → lazy
   per-intrinsic caching + per-frame cleanup (→ 3.2 GB).
3. **KV-cache init = 28 GB** (the real wall, atop the ~28 GB bf16 14B model) → the dominant lever is
   **`--local_attn_size`** (num_cache_frames), *not* `--frames_per_block`. `las 21→6` cut KV 28 GB → 8 GB.

The bf16 14B model is a hard ~28 GB floor, so `ARTIFIXER_ENHANCE_DOWNSCALE=4` + `--local_attn_size 6` is
the validated-fit point (~3 GB headroom). `downscale=3` did not fit.
