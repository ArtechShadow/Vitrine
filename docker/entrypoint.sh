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
# VNC is a debug surface. Bind it to loopback (-localhost) so that even with a
# host port publish it is reachable ONLY through an SSH tunnel, never the LAN
# (ADR-022 D3). The host publish is additionally pinned to 127.0.0.1 in compose.
x11vnc -display :1 -forever -nopw -localhost -shared -rfbport 5901 -bg 2>/dev/null || true

echo "VNC on 127.0.0.1:5901 (loopback-only; reach via ssh -N -L 5901:localhost:5901)"

# Ensure data directories exist
mkdir -p /data/output /data/input

# Ensure HF cache is writable by ubuntu user (for SAM3 model download)
mkdir -p /opt/hf-cache
chown -R ubuntu:ubuntu /opt/hf-cache 2>/dev/null || true

# The web terminal (ttyd) is started by supervisord — which runs as root — with
# user=ubuntu/uid 1000, but supervisord leaves HOME=/root. That made `claude`
# look for its config + credentials under /root/.claude (unreadable by ubuntu;
# /root is 0700) and HANG on login. Correct HOME for uid-1000 login shells
# before anything else runs (this runs first: 00- sorts before 10-).
cat > /etc/profile.d/00-home.sh <<'PROFILE'
# Vitrine: fix HOME for the web terminal (supervisord leaves it /root).
if [ "$(id -u)" = "1000" ] && [ "$HOME" != "/home/ubuntu" ]; then
    export HOME=/home/ubuntu USER=ubuntu LOGNAME=ubuntu
fi
PROFILE
chmod 0644 /etc/profile.d/00-home.sh

# Web-terminal Claude login helper. The terminal (ttyd) runs `bash --login` as
# the non-root ubuntu user, so `claude --dangerously-skip-permissions` is
# allowed and a subscription login (OAuth) overrides the need for an API key.
# Provide a `claude-login` shortcut and a one-time hint on interactive shells.
cat > /etc/profile.d/10-claude-login.sh <<'PROFILE'
# Vitrine: log into Claude Code from the web terminal (no API key needed).
# Only surfaced when the internal-Claude intelligence is enabled at setup
# (VITRINE_CLAUDE_ENABLED=1); otherwise the terminal itself is not started.
claude-login() { command claude --dangerously-skip-permissions "$@"; }
if [ -n "$BASH_VERSION" ]; then export -f claude-login 2>/dev/null || true; fi
case "${VITRINE_CLAUDE_ENABLED:-0}" in
  1|true|yes|on|True|YES|On)
    case "$-" in
      *i*)
        printf '\n\033[1;36m● Claude Code\033[0m — log in with your Claude subscription (no API key needed):\n'
        printf '    run  \033[1;32mclaude-login\033[0m   then type  \033[1;32m/login\033[0m   and accept the bypass-permissions prompt once.\n'
        printf '    \033[2m(claude-login = claude --dangerously-skip-permissions; the pipeline then auto-runs jobs)\033[0m\n\n'
        ;;
    esac
    ;;
esac
PROFILE
chmod 0644 /etc/profile.d/10-claude-login.sh

echo "Services starting via supervisord..."

# Start supervisord
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/gaussian-toolkit.conf
