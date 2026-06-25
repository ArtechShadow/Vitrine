#!/usr/bin/env bash
# Bring up the persistent UE 5.8 editor (Xvfb + VNC) DETACHED, on GPU1, joined to
# v2g-net (+ visionclaw_network) so unreal-mcp-bridge / agentbox reach it as
# `unreal`. Validates the resident-editor path before baking it into the overlay.
#
#   RC  : host :30010   MCP : host :8000   VNC : host :5903 -> :5901
# Watch:  docker logs -f vitrine-unreal-editor   |   VNC to <host>:5903
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USD="${VITRINE_USD:-/usd_input/exhibit/scene.usda}"
GPU="${UNREAL_GPU:-1}"

docker rm -f vitrine-unreal-editor 2>/dev/null || true
docker network create v2g-net >/dev/null 2>&1 || true

docker run -d --name vitrine-unreal-editor --hostname unreal \
  --runtime nvidia --user 1000:1000 \
  --network v2g-net --network-alias unreal \
  -e NVIDIA_VISIBLE_DEVICES="$GPU" \
  -e NVIDIA_DRIVER_CAPABILITIES=graphics,compute,utility \
  -e DISPLAY=:1 -e HOME=/tmp \
  -e VITRINE_USD="$USD" \
  -e UE_STARTUP_PY=import_usd_stage.py \
  -p 30010:30010 -p 8000:8000 -p 5903:5901 \
  -v "$REPO/unreal/engine":/opt/ue:rw \
  -v "$REPO/output":/usd_input:ro \
  -v "$REPO/unreal/runtime":/vitrine/unreal:ro \
  --entrypoint bash vitrine-unreal:5.8 /vitrine/unreal/run_editor.sh

docker network connect --alias unreal visionclaw_network vitrine-unreal-editor >/dev/null 2>&1 || true
echo "started vitrine-unreal-editor — RC host :30010, MCP host :8000, VNC host :5903"
echo "watch:  docker logs -f vitrine-unreal-editor"
