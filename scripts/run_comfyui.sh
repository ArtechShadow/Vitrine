#!/usr/bin/env bash
# Launch the canonical "owner" ComfyUI (ADR-014 endpoint).
#
# Runs data/comfyui (with its custom nodes: TRELLIS2, Hunyuan3D-2.1,
# SAM3D) on GPU0, published on host :8200. The gaussian-toolkit image is reused
# purely as a CUDA + torch 2.11 + ComfyUI-deps runtime.
#
# Models live in the UNIFIED tree data/comfyui/models (ADR: single models dir).
# It is ComfyUI's native models path (inside the /comfyui mount), so there is no
# separate /staging mount any more — extra_model_paths.yaml just registers the
# custom folder types (trellis2/hunyuan3d/sam3d/…) against base /comfyui/models.
#
# IMPORTANT: --entrypoint override is REQUIRED. The gaussian-toolkit image's
# entrypoint is supervisord (which would start the image's OWN bare /opt/comfyui
# on GPU1 and ignore this command). Overriding it runs the owner's /comfyui/main.py.
#
# Verified: FLUX.2 (flux2_dev_fp8mixed.safetensors) is visible in UNETLoader from
# the native models tree (data/comfyui/models/diffusion_models/…).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMFY_DIR="${COMFYUI_DIR:-$REPO_DIR/data/comfyui}"
PORT="${COMFYUI_HOST_PORT:-8200}"
GPU="${COMFYUI_GPU:-0}"
IMAGE="${COMFYUI_IMAGE:-gaussian-toolkit:latest}"

# HuggingFace token (optional): the custom nodes (TRELLIS2 pulls the 1.3B TRELLIS.2
# DiTs from microsoft/TRELLIS.2-4B; Hunyuan3D/DINOv3 likewise) fetch weights from
# HF on first use. A token gives higher rate limits + faster, non-throttled
# downloads (ComfyUI logs "unauthenticated requests ... please set HF_TOKEN"
# otherwise). Read from ~/.hf_token (gitignored) or the HF_TOKEN env — never
# hardcoded. Absent => unauthenticated (still works, just slower/rate-limited).
HF_TOKEN="${HF_TOKEN:-}"
if [[ -z "$HF_TOKEN" && -f "$HOME/.hf_token" ]]; then
  HF_TOKEN="$(tr -d '[:space:]' < "$HOME/.hf_token")"
fi

# comfyui_entrypoint.sh (mounted) repairs the image safetensors metadata and
# installs the custom-node deps before launching ComfyUI — see that script.
docker rm -f vitrine-comfyui 2>/dev/null || true
# Host publish pinned to loopback (ADR-024 D1 posture): ComfyUI has NO auth and
# a known RCE-class surface (master audit); LAN reach is via ssh -L only.
# Cross-container access is unaffected (v2g-net service DNS, not the publish).
docker run -d --name vitrine-comfyui --runtime nvidia --user 0:0 \
  -e CUDA_VISIBLE_DEVICES="$GPU" -e HF_TOKEN="$HF_TOKEN" \
  -p "127.0.0.1:${PORT}:8188" \
  -v "$COMFY_DIR":/comfyui \
  -v "$SCRIPT_DIR/comfyui_entrypoint.sh":/comfyui_entrypoint.sh:ro \
  -w /comfyui --entrypoint bash \
  "$IMAGE" /comfyui_entrypoint.sh

# Join the v2g-net so the gaussian-toolkit pipeline can reach it by name as
# http://vitrine-comfyui:8188 (set V2G_COMFYUI_URL accordingly).
docker network create v2g-net >/dev/null 2>&1 || true
docker network connect v2g-net vitrine-comfyui >/dev/null 2>&1 || true

# Also join the shared external visionclaw_network (if present) so the VisionFlow
# app (host :4000) and the agentbox / Claude Code environment can reach ComfyUI
# directly as http://vitrine-comfyui:8188. Non-fatal if the network is absent.
docker network connect visionclaw_network vitrine-comfyui >/dev/null 2>&1 || true

echo "vitrine-comfyui launched on host :${PORT} (GPU${GPU}); owner ComfyUI + native data/comfyui/models tree."
echo "Pipeline endpoint: V2G_COMFYUI_URL=http://vitrine-comfyui:8188 (over v2g-net)"
