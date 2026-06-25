#!/bin/bash
# Start the CoMe sidecar on GPU1 (UE idle there; object batch owns GPU0) and run the
# documented CoMe path on the dreamlab COLMAP: train (its own gaussians) + extract the
# real-world marching-tetrahedra mesh. Detached + logged so it survives the night.
# Run from the agent (its docker CLI == host daemon). CoMe = non-commercial (research/eval).
set -u
IMG=gaussian-toolkit-come:latest
REPO_HOST=/home/john/githubs/gaussian/LichtFeld-Studio
SCENE=${1:-/data/output/dreamlab/locked}             # scene root (override as $1 for future runs)
DS=$SCENE/colmap/undistorted                          # images/ + sparse/ (full 750-img merged model)
OUT=$SCENE/model_come
LOG=$SCENE/come_train.log
# NB: CoMe needs a near-full GPU. Full-res 4K OOMs at ~33GB if UE (14GB) shares GPU1 ->
# stop vitrine-unreal first (re-assembled later) AND use -r 2 (half-res; plenty for a mesh).
RES="-r 2"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
docker stop vitrine-unreal >/dev/null 2>&1 || true

if ! docker images --format '{{.Repository}}' | grep -q gaussian-toolkit-come; then
  echo "come image not built yet"; exit 1
fi
# (re)start the come container on GPU1
docker rm -f come >/dev/null 2>&1 || true
docker run -d --name come --runtime nvidia -e NVIDIA_VISIBLE_DEVICES=1 \
  -v "$REPO_HOST/output":/data/output --network v2g-net \
  --entrypoint sleep "$IMG" infinity
sleep 2
docker ps --filter name=come --format '{{.Names}} {{.Status}}' | grep -q come && echo "come container up on GPU1" || { echo "come FAILED to start"; docker logs come 2>&1 | tail -5; exit 1; }
CONDA=/opt/miniconda/bin/conda
docker exec come bash -lc "$CONDA run -n come python -c \"import torch;print('come torch',torch.__version__,'cuda',torch.cuda.is_available())\"" 2>&1 | tail -2

# Ensure fused_ssim: the --entrypoint sleep override above skips the image entrypoint that
# normally builds it, and a freshly (re)created container loses any runtime-installed copy.
# decoupled-fused-ssim ships its dir as decoupled_fused_ssim/ but train.py imports fused_ssim
# -> build (sm_89) then symlink-alias. Idempotent.
docker exec come bash -lc '
  C=/opt/miniconda/bin/conda
  $C run -n come python -c "import fused_ssim" 2>/dev/null && { echo "fused_ssim present"; exit 0; }
  echo "building decoupled-fused-ssim (sm_89) + aliasing fused_ssim..."
  cd /opt/come && export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.9
  $C run -n come pip install --no-build-isolation ./submodules/decoupled-fused-ssim
  SP=$($C run -n come python -c "import decoupled_fused_ssim,os;print(os.path.dirname(os.path.dirname(decoupled_fused_ssim.__file__)))")
  ln -sfn "$SP/decoupled_fused_ssim" "$SP/fused_ssim"
  $C run -n come python -c "import fused_ssim" && echo "fused_ssim ensured"
'

# CoMe's loader expects the model under sparse/0/ in classic format; image_undistorter writes it
# flat at sparse/ in COLMAP 4.1 binary (+rigs/frames). Ensure sparse/0/ TXT (sidesteps the 4.1
# binary/rig-frame mismatch in CoMe's reader). Runs in gaussian-toolkit (which has colmap).
docker exec gaussian-toolkit bash -lc "S=$DS/sparse; [ -f \$S/0/images.txt ] || { mkdir -p \$S/0 && colmap model_converter --input_path \$S --output_path \$S/0 --output_type TXT && echo 'prepared sparse/0 TXT for CoMe'; }" 2>&1 | tail -2

# train + extract, detached, single log (NVIDIA_VISIBLE_DEVICES=1 -> only GPU1 visible -> cuda:0)
docker exec -d come bash -lc "cd /opt/come && export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && \
  $CONDA run -n come python train.py --splatting_config configs/hierarchical.json -s $DS -m $OUT $RES > $LOG 2>&1 && \
  $CONDA run -n come python extract_mesh_tets.py -m $OUT >> $LOG 2>&1 && \
  echo COME_PIPELINE_DONE >> $LOG"
echo "CoMe train+extract launched -> $LOG (== output/dreamlab/come_train.log)"
