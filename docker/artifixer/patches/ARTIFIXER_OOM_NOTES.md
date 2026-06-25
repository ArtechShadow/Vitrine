# ArtiFixer 14B enhance on RTX 6000 Ada (48GB, sm_89) — OOM fix notes (2026-06-25)

## RESULT: enhance COMPLETED — 30 corrected frames, peak VRAM 45.5/48 GB.
Output (pred = corrected): 
output/dreamlab/locked/artifixer/corrected/artifixer-14b/distilled_views_reconstructed_colmap_2_evenly_spaced_sink3/prep/frames/batch_0000/pred/*.png
(30 PNGs at 1968x3398, alongside gt/ and rendered/). rc=0, "Done!".

## The three OOMs and what actually fixed each
The OOM was NOT only the Wan VAE decode. There were THREE distinct OOMs, each
solved by a different env-gated patch (all in artifixer code under /workspace,
backed up as *.bak.*):

1. VAE encode (autoencoder_kl_wan F.pad), ~15GB. 
   FIX: vae.enable_tiling() — patch in model_training/utils/train_utils.py
   (_maybe_enable_vae_tiling, env ARTIFIXER_VAE_TILING=1), called after BOTH
   AutoencoderKLWan.from_pretrained sites (get_pipe + get_kv_cache_pipe).
   diffusers 0.38.0 tiled encode/decode verified (15GB->1.1GB standalone).

2. 3DGRUT trajectory RENDER OOM (dataset_colmap _lazy_worker_intrinsics_cache,
   rays_ori.to(device)) at ~46GB. render_from_file registers ONE intrinsic per
   frame, then eagerly moves ALL 750 full-res ray grids to GPU at once (~30GB).
   FIXES (env ARTIFIXER_LAZY_INTR=1):
   - thirdparty/3DGRUT-ArtiFixer/threedgrut/datasets/dataset_colmap.py:
     _lazy_worker_intrinsics_cache(intr_id=...) moves only the requested
     intrinsic, evicting the prior (cache size 1).
   - thirdparty/3DGRUT-ArtiFixer/threedgrut/render.py: render_from_file loop
     does `del gpu_batch, outputs; torch.cuda.empty_cache()` per frame
     (without this, ~200MB/frame leak -> OOM by frame ~155).
   - render.py num_workers env ARTIFIXER_RENDER_WORKERS=0 (avoid per-worker
     GPU ray-cache dup).
   - render_3dgrut_colmap.py computes_extra_metrics env ARTIFIXER_RENDER_METRICS=0
     (drop LPIPS VGG/SSIM off GPU during render).
   Render then completed all 750 frames at peak ~3.2GB.
   NOTE: ARTIFIXER_RENDER_DOWNSAMPLE does NOT affect the transforms-schema
   trajectory path -> render came out FULL-RES 1968x3398.

3. KV-cache init (kv_cache_pipeline _initialize_kv_cache torch.zeros), THE real
   wall. KV cache = blocks(40) x frame_seq_len x num_cache_frames(=local_attn_size)
   x heads x head_dim x 2(k+v) x 2 bytes. At local_attn_size=21 + full-res this
   is ~28GB on top of the ~28GB bf16 14B model => 56GB > 48GB.
   FIXES:
   - model_training/data/utils.py resize_to_multiple_of_16: env
     ARTIFIXER_ENHANCE_DOWNSCALE divides H,W before /16 rounding (downscales all
     resolution-bearing tensors consistently; intrinsics are ratios so stay valid).
   - --local_attn_size lowered (num_cache_frames). THIS was the dominant lever,
     not frames_per_block. 21->6 cut KV from 28GB to 8.08GB.
   mem-debug print added before KV init (env ARTIFIXER_MEM_DEBUG=1) pinpointed it.

## Working config (peak 45.5GB; baseline = 34GB model+working + 8GB KV)
Prep (reuse saved ckpt_10000.pt, fab caption to skip the 30B Qwen):
  ARTIFIXER_RENDER_DOWNSAMPLE=2 ARTIFIXER_RENDER_WORKERS=0 \
  ARTIFIXER_RENDER_METRICS=0 ARTIFIXER_LAZY_INTR=1 \
  python -m data_processing.prepare_colmap_artifixer_inputs \
    --colmap_dir .../colmap/undistorted --output_root .../artifixer/prep \
    --selected_image_names_file .../selected_train_images.txt \
    --metric_scale 0.8144547843191945 --phases render,scale,caption
  (caption.h5 pre-fabbed via artifixer_fab_caption.py BEFORE this so the 30B
   captioner download is skipped.)

Enhance (the COMPLETING command):
  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:256
  export ARTIFIXER_VAE_TILING=1 ARTIFIXER_ENHANCE_DOWNSCALE=4
  python -m model_eval.run_inference \
    --evalset reconstructed_colmap --inference_pipeline kv_cache \
    --checkpoint_pt /workspace/ckpt/artifixer-14b.pt \
    --split_path .../artifixer/prep/split.json \
    --save_dir .../artifixer/corrected --render_trajectory val_frames \
    --num_views 2 --frames_per_block 2 --sink_size 3 --local_attn_size 6 \
    --max_neighbors_per_encode 1 --save_frame_outputs_only --replace_if_exists

## Headroom / tuning
- The 14B bf16 model is a hard ~28GB floor on a 48GB card; working set + KV must
  fit in ~20GB. local_attn_size is the main KV lever; ARTIFIXER_ENHANCE_DOWNSCALE
  scales BOTH activations and KV (~res^2).
- To raise OUTPUT resolution: ARTIFIXER_ENHANCE_DOWNSCALE=3 was too big at las=6
  (KV ~21GB). At ds4 there was ~3GB margin, so las could likely go to 8-9 at ds4,
  or try ds3 + las=4. Quality vs fit tradeoff; ds4/las6 is the proven-fit point.
