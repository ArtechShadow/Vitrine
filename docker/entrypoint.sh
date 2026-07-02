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

# Web-terminal Claude login helper. The terminal (ttyd) runs `bash --login` as
# the non-root ubuntu user, so `claude --dangerously-skip-permissions` is
# allowed and a subscription login (OAuth) overrides the need for an API key.
# Provide a `claude-login` shortcut and a one-time hint on interactive shells.
cat > /etc/profile.d/10-claude-login.sh <<'PROFILE'
# Vitrine: log into Claude Code from the web terminal (no API key needed).
claude-login() { command claude --dangerously-skip-permissions "$@"; }
if [ -n "$BASH_VERSION" ]; then export -f claude-login 2>/dev/null || true; fi
case "$-" in
  *i*)
    printf '\n\033[1;36m● Claude Code\033[0m — log in with your Claude subscription (no API key needed):\n'
    printf '    run  \033[1;32mclaude-login\033[0m   then type  \033[1;32m/login\033[0m   and accept the bypass-permissions prompt once.\n'
    printf '    \033[2m(claude-login = claude --dangerously-skip-permissions; the pipeline then auto-runs jobs)\033[0m\n\n'
    ;;
esac
PROFILE
chmod 0644 /etc/profile.d/10-claude-login.sh

echo "Services starting via supervisord..."

# Start supervisord
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/gaussian-toolkit.conf
