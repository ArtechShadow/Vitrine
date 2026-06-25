#!/bin/bash
set -e

echo "=== Gaussian Toolkit Container Starting ==="

# Expose the unified models tree WITHOUT copying. /models-staging is the
# bind-mounted unified in-repo tree (data/comfyui/models, ~200 GB, read-only).
# The previous behaviour copied it into the /opt/models volume on first run —
# that would now duplicate ~200 GB and fill the disk, so symlink each category
# into /opt/models instead (ADR: single models dir).
if [ -d "/models-staging" ] && [ "$(ls -A /models-staging 2>/dev/null)" ]; then
    echo "Linking unified models from /models-staging (no copy)..."
    mkdir -p /opt/models
    for subdir in /models-staging/*/; do
        dirname=$(basename "$subdir")
        target="/opt/models/$dirname"
        # Only link categories not already present as a real dir in the volume
        # (so any runtime-downloaded models in /opt/models are preserved).
        if [ ! -e "$target" ]; then
            ln -sfn "$subdir" "$target"
            echo "  Linked $dirname"
        fi
    done
    echo "Model staging (link) complete."
fi

# Link ComfyUI model directories
if [ -d "/opt/comfyui" ]; then
    for subdir in diffusion_models text_encoders vae loras checkpoints; do
        src="/opt/models/$subdir"
        dst="/opt/comfyui/models/$subdir"
        if [ -d "$src" ] && [ ! -L "$dst" ]; then
            rm -rf "$dst"
            ln -sf "$src" "$dst"
        fi
    done
    for subdir in trellis2 sam3d sam2 grounding-dino sams hunyuan3d UltraShape sam3; do
        src="/opt/models/$subdir"
        dst="/opt/comfyui/models/$subdir"
        if [ -d "$src" ] && [ ! -L "$dst" ]; then
            ln -sf "$src" "$dst"
        fi
    done
fi

# Start Xvfb (clean up stale locks from previous runs)
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true
Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
sleep 1
export DISPLAY=:1
fluxbox &>/dev/null &
x11vnc -display :1 -forever -nopw -shared -rfbport 5901 -bg 2>/dev/null || true

echo "VNC on port 5901"

# Ensure data directories exist
mkdir -p /data/output /data/input

# Ensure HF cache is writable by ubuntu user (for SAM3 model download)
mkdir -p /opt/hf-cache
chown -R ubuntu:ubuntu /opt/hf-cache 2>/dev/null || true

echo "Services starting via supervisord..."

# Start supervisord
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/gaussian-toolkit.conf
