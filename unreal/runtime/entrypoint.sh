#!/bin/bash
# =============================================================================
# Vitrine — Unreal Engine 5.8 headless container entrypoint (ADR-016)
#
# Launches UnrealEditor-Cmd in one of two modes controlled by RENDER_MODE:
#
#   offscreen (default) — GPU Lumen render via -RenderOffscreen (Vulkan/CUDA).
#                         Requires an NVIDIA device.  Use for MovieRenderQueue
#                         output frames.
#
#   nullrhi             — No GPU / no render context.  Use for pure USD import,
#                         scene assembly, metadata stamp and .uasset save.
#                         Safe to run without a GPU slot.
#
# Env vars (all have defaults; set in docker-compose or `docker run -e`):
#   VITRINE_USD        path to scene.usda inside the container
#                      (default /usd_input/scene.usda)
#   UE_PROJECT         path to the .uproject file
#                      (default /vitrine/unreal/Vitrine.uproject)
#   RENDER_MODE        offscreen | nullrhi  (default offscreen)
#   UE_MCP_PORT        first-party Unreal MCP listen port (default 8000)
#   UE_RC_PORT         Web Remote Control listen port (default 30010)
#   UE_SCRIPT          override the -run=pythonscript script path
#                      (default /vitrine/unreal/import_and_render.py)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve configuration
# ---------------------------------------------------------------------------
UE_ROOT="${UE_ROOT:-/opt/ue}"
VITRINE_USD="${VITRINE_USD:-/usd_input/scene.usda}"
UE_PROJECT="${UE_PROJECT:-/vitrine/unreal/Vitrine.uproject}"
RENDER_MODE="${RENDER_MODE:-offscreen}"
UE_MCP_PORT="${UE_MCP_PORT:-8000}"
UE_RC_PORT="${UE_RC_PORT:-30010}"
UE_SCRIPT="${UE_SCRIPT:-/vitrine/unreal/import_and_render.py}"

# ---------------------------------------------------------------------------
# RENDER_MODE=editor -> persistent, agent-drivable editor (default for the overlay)
# ---------------------------------------------------------------------------
# Hand off to run_editor.sh: a RESIDENT windowed UnrealEditor on an Xvfb display
# (real Vulkan RHI) that keeps Web Remote Control (:UE_RC_PORT) + the first-party
# MCP server (:UE_MCP_PORT) alive for unreal-mcp-bridge / agents, with x11vnc for
# observation. The one-shot `-run=pythonscript` commandlet path below (offscreen/
# nullrhi) loads NullDrv and exits — use it only for batch import/render jobs.
# (All verified 2026-06-21 via unreal/smoke_editor.sh.)
if [ "${RENDER_MODE}" = "editor" ]; then
    echo "=== Vitrine Unreal: persistent editor mode (Xvfb + VNC + RC/MCP) ==="
    exec "$(dirname "$0")/run_editor.sh"
fi

# ---------------------------------------------------------------------------
# Copy the project to a writable location.
# ---------------------------------------------------------------------------
# The runtime/ dir is bind-mounted read-only, but UnrealEditor-Cmd MUST write
# Saved/ + Intermediate/ into the project directory. Copy the project (uproject
# + scripts) under the writable HOME and repoint UE_PROJECT / UE_SCRIPT at the
# copy. (Verified via unreal/smoke_nullrhi.sh, 2026-06-21.)
PROJ_SRC_DIR="$(dirname "${UE_PROJECT}")"
WORK_PROJ_DIR="${HOME:-/tmp}/vitrine-proj"
echo "  copying project ${PROJ_SRC_DIR} -> ${WORK_PROJ_DIR} (writable Saved/Intermediate)"
rm -rf "${WORK_PROJ_DIR}"
cp -r "${PROJ_SRC_DIR}" "${WORK_PROJ_DIR}"
case "${UE_SCRIPT}" in
    "${PROJ_SRC_DIR}"/*) UE_SCRIPT="${WORK_PROJ_DIR}/${UE_SCRIPT#"${PROJ_SRC_DIR}"/}" ;;
esac
UE_PROJECT="${WORK_PROJ_DIR}/$(basename "${UE_PROJECT}")"

echo "=== Vitrine Unreal Engine container starting ==="
echo "  RENDER_MODE : ${RENDER_MODE}"
echo "  VITRINE_USD : ${VITRINE_USD}"
echo "  UE_PROJECT  : ${UE_PROJECT}"
echo "  UE_SCRIPT   : ${UE_SCRIPT}"
echo "  MCP port    : ${UE_MCP_PORT}"
echo "  RC port     : ${UE_RC_PORT}"

# ---------------------------------------------------------------------------
# Validate USD input exists (warn only — editor will error clearly if missing)
# ---------------------------------------------------------------------------
if [ ! -f "${VITRINE_USD}" ]; then
    echo "WARNING: VITRINE_USD not found at '${VITRINE_USD}' — USD Stage Actor will fail to load."
fi

# ---------------------------------------------------------------------------
# Select GPU / render flags
# ---------------------------------------------------------------------------
if [ "${RENDER_MODE}" = "nullrhi" ]; then
    RENDER_FLAGS="-nullrhi"
    echo "  GPU render  : disabled (-nullrhi); import/assemble only"
else
    # -RenderOffscreen: headless Vulkan/OpenGL offscreen context (Lumen).
    # No DirectX / Path Tracer on Linux containers.
    RENDER_FLAGS="-RenderOffscreen"
    echo "  GPU render  : enabled (-RenderOffscreen, Lumen/Vulkan)"
fi

# ---------------------------------------------------------------------------
# Ensure /renders output dir exists (MovieRenderQueue writes here)
# ---------------------------------------------------------------------------
mkdir -p /renders

# ---------------------------------------------------------------------------
# Locate UnrealEditor-Cmd
# ---------------------------------------------------------------------------
# Epic dev images place the binary under /home/ue4/UnrealEngine/Engine/Binaries/Linux/
# or /opt/unreal/Engine/Binaries/Linux/. Try the well-known paths, then fall back
# to PATH lookup.
UE_CMD=""
for candidate in \
    "${UE_ROOT}/Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "/home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "/opt/unreal/Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd"
do
    if [ -x "${candidate}" ]; then
        UE_CMD="${candidate}"
        break
    fi
done

if [ -z "${UE_CMD}" ]; then
    # Last-resort: rely on PATH (Epic's dev image sets it up in /etc/profile.d/)
    UE_CMD="UnrealEditor-Cmd"
fi

echo "  UnrealEditor-Cmd: ${UE_CMD}"

# ---------------------------------------------------------------------------
# Build the command
# ---------------------------------------------------------------------------
# Flags:
#   -run=pythonscript -script=...  run our headless Python script
#   -RCWebControlEnable            enable Web Remote Control plugin (:UE_RC_PORT)
#   -RCWebInterfaceEnable          enable the RC HTTP interface
#   -RCWebControlPort              explicit RC port (default 30010 matches EXPOSE)
#   -MCPEnable                     enable the first-party Unreal MCP plugin
#   -MCPPort                       explicit MCP port (default 8000 matches EXPOSE)
#   -unattended -nopause -nosplash standard headless flags
#   -log                           stream log to stdout
#   VITRINE_USD=... (passed as UE commandline extra, readable via FCommandLine)
# ---------------------------------------------------------------------------
exec "${UE_CMD}" \
    "${UE_PROJECT}" \
    -run=pythonscript \
    -script="${UE_SCRIPT}" \
    ${RENDER_FLAGS} \
    -RCWebControlEnable \
    -RCWebInterfaceEnable \
    -RCWebControlPort="${UE_RC_PORT}" \
    -MCPEnable \
    -MCPPort="${UE_MCP_PORT}" \
    -unattended \
    -nopause \
    -nosplash \
    -log \
    VITRINE_USD="${VITRINE_USD}"
