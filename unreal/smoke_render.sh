#!/usr/bin/env bash
# Vitrine UE 5.8 OFFSCREEN (GPU/Vulkan) RHI probe (run on the HOST).
#
# Follows the nullrhi smoke-test: does -RenderOffscreen initialise the Vulkan RHI
# on GPU1 inside vitrine-unreal:5.8? This is the gate for any real render. Uses
# the NVIDIA runtime with graphics capability so the Vulkan ICD is injected.
# Reuses _smoke_probe.py (also re-confirms USD Stage Actor in GPU mode).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USD="${VITRINE_USD:-/usd_input/exhibit/scene.usda}"
GPU="${UNREAL_GPU:-1}"
LOG_HOST="$REPO/unreal/_smoke_out/unreal_render_probe.log"
mkdir -p "$REPO/unreal/_smoke_out"

echo "REPO=$REPO  GPU=$GPU  VITRINE_USD=$USD"
docker rm -f vitrine-unreal-render-probe 2>/dev/null || true

timeout 900 docker run --rm --name vitrine-unreal-render-probe \
  --runtime nvidia \
  --user 1000:1000 \
  --entrypoint bash \
  -e NVIDIA_VISIBLE_DEVICES="$GPU" \
  -e NVIDIA_DRIVER_CAPABILITIES=graphics,compute,utility \
  -e VITRINE_USD="$USD" \
  -e UE_ROOT=/opt/ue \
  -e HOME=/tmp \
  -v "$REPO/unreal/engine":/opt/ue:rw \
  -v "$REPO/output":/usd_input:ro \
  -v "$REPO/unreal/runtime":/vitrine/unreal:ro \
  vitrine-unreal:5.8 -c '
    set -uo pipefail
    echo "[host] nvidia-smi inside container:"; nvidia-smi -L || echo "[host] nvidia-smi unavailable"
    echo "[host] vulkaninfo summary:"; vulkaninfo --summary 2>/dev/null | head -30 || echo "[host] vulkaninfo unavailable"
    UE=/opt/ue/Engine/Binaries/Linux/UnrealEditor-Cmd
    cp -r /vitrine/unreal /tmp/proj
    echo "[host] launching UnrealEditor-Cmd (-RenderOffscreen, Vulkan) ..."
    "$UE" /tmp/proj/Vitrine.uproject \
      -run=pythonscript -script=/tmp/proj/_smoke_probe.py \
      -RenderOffscreen -unattended -nopause -nosplash -stdout -FullStdOutLogOutput
    rc=$?
    echo "[host] UnrealEditor-Cmd exit=$rc"
    exit $rc
  ' 2>&1 | tee "$LOG_HOST"

echo "PROBE_PIPELINE_RC=${PIPESTATUS[0]}"
echo "log: $LOG_HOST"
