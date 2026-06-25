#!/usr/bin/env bash
# Vitrine — persistent UE 5.8 editor on a virtual display (ADR-016 / ADR-018).
#
# Unlike entrypoint.sh (which runs a one-shot `-run=pythonscript` commandlet that
# loads NullDrv and exits), this launches the RESIDENT windowed UnrealEditor on an
# Xvfb display so:
#   * the real Vulkan RHI initialises (GPU render works — NullDrv only happens in
#     commandlets), and
#   * the editor stays alive, keeping Web Remote Control (:UE_RC_PORT) and the
#     first-party MCP server (:UE_MCP_PORT) resident for unreal-mcp-bridge + agents.
# x11vnc exposes the display so the editor can be watched/driven (VNC).
#
# A startup python (UE_STARTUP_PY, default import_usd_stage.py) spawns the USD
# Stage Actor + mirrors v2g:* once, then the editor keeps running.
set -uo pipefail

UE_ROOT="${UE_ROOT:-/opt/ue}"
VITRINE_USD="${VITRINE_USD:-/usd_input/scene.usda}"
UE_PROJECT_SRC="${UE_PROJECT:-/vitrine/unreal/Vitrine.uproject}"
UE_RC_PORT="${UE_RC_PORT:-30010}"
UE_MCP_PORT="${UE_MCP_PORT:-8000}"
UE_STARTUP_PY="${UE_STARTUP_PY:-exhibit_startup_glb.py}"
DISPLAY_NUM="${DISPLAY_NUM:-1}"
VNC_PORT="${VNC_PORT:-5901}"
SCREEN_GEOMETRY="${SCREEN_GEOMETRY:-1920x1080x24}"

export DISPLAY=":${DISPLAY_NUM}"

# --- virtual display + VNC -------------------------------------------------
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true
echo "[editor] Xvfb ${DISPLAY} (${SCREEN_GEOMETRY})"
Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN_GEOMETRY}" -ac +extension GLX +render -noreset &
for i in $(seq 1 30); do xdpyinfo -display ":${DISPLAY_NUM}" >/dev/null 2>&1 && break; sleep 0.5; done
fluxbox >/dev/null 2>&1 &
echo "[editor] x11vnc rfbport ${VNC_PORT}"
x11vnc -display ":${DISPLAY_NUM}" -forever -nopw -shared -rfbport "${VNC_PORT}" -bg >/dev/null 2>&1 || true

# --- writable project copy (runtime/ is bind-mounted read-only) ------------
PROJ_SRC_DIR="$(dirname "${UE_PROJECT_SRC}")"
WORK="${HOME:-/tmp}/vitrine-proj"
rm -rf "${WORK}"; cp -r "${PROJ_SRC_DIR}" "${WORK}"
UE_PROJECT="${WORK}/$(basename "${UE_PROJECT_SRC}")"
STARTUP="${WORK}/${UE_STARTUP_PY}"

[ -f "${VITRINE_USD}" ] || echo "[editor] WARNING: VITRINE_USD missing at ${VITRINE_USD}"

echo "[editor] launching persistent UnrealEditor (Vulkan) — RC :${UE_RC_PORT} MCP :${UE_MCP_PORT}"
echo "[editor]   project=${UE_PROJECT} usd=${VITRINE_USD} startup=${STARTUP}"
# Flag rationale (all verified 2026-06-21):
#   -unattended      : boots fast past the Zen DDC service (a non-unattended full
#                      editor hangs in a "zen service status" retry loop in-container).
#   -ExecCmds="py …" : run the startup import via the `py` console command, NOT
#                      -ExecutePythonScript — the latter makes an -unattended editor
#                      call CloseEditor() and exit once the script finishes. -ExecCmds
#                      runs at startup and the editor stays resident, keeping RC/MCP up.
# UE 5.8 native MCP flags (per Epic docs, verified 2026-06-21): the server is
# started by -ModelContextProtocolStartServer + -ModelContextProtocolPort (the
# earlier -MCPEnable/-MCPPort were NOT real flags — why MCP read 'down'). The MCP
# HTTP listener honours [HTTPServer.Listeners] DefaultBindAddress (=0.0.0.0 in
# Config/DefaultEngine.ini) but REJECTS non-loopback Origin headers, so the bridge
# must present a loopback Origin (handled in mcp_bridge.py).
exec "${UE_ROOT}/Engine/Binaries/Linux/UnrealEditor" "${UE_PROJECT}" \
    -RCWebControlEnable -RCWebInterfaceEnable -RCWebControlPort="${UE_RC_PORT}" \
    -ModelContextProtocolStartServer -ModelContextProtocolPort="${UE_MCP_PORT}" \
    -unattended -nosplash -stdout -FullStdOutLogOutput \
    -ExecCmds="py ${STARTUP}" \
    VITRINE_USD="${VITRINE_USD}"
