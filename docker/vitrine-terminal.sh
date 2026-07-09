#!/bin/bash
# =============================================================================
# Vitrine internal-Claude terminal gate  (ADR-022 D3 / ADR-024)
# =============================================================================
# The ttyd web terminal is the ONLY interactive control surface for the
# in-container Claude intelligence. By default it is DISABLED so that the sole
# operator I/O is the web upload + runtime-feedback panel on :7860 (reached over
# an SSH tunnel). It is enabled only when the operator opts in at setup by
# setting VITRINE_CLAUDE_ENABLED=1 (see .env.example / docker-compose).
#
# When disabled this script exits 0 so supervisord (autorestart=unexpected)
# marks the program EXITED and does NOT churn-restart it — leaving TCP :7681
# with no listener even though the loopback port mapping exists.
#
# When enabled, ttyd is bound to 127.0.0.1 inside the container. Combined with
# the loopback-pinned host publish, the terminal is reachable ONLY through an
# explicit SSH tunnel (`ssh -N -L 7681:localhost:7681`), never from the LAN.
# =============================================================================
set -euo pipefail

ENABLED="${VITRINE_CLAUDE_ENABLED:-0}"
case "${ENABLED,,}" in
    1|true|yes|on)
        echo "[vitrine-terminal] VITRINE_CLAUDE_ENABLED=${ENABLED} — starting gated ttyd on 127.0.0.1:7681"
        # --interface 127.0.0.1: bind loopback only (SSH-tunnel reachable, never LAN).
        exec /usr/local/bin/ttyd \
            --interface 127.0.0.1 \
            --port 7681 \
            --writable \
            --uid 1000 --gid 1000 \
            bash --login
        ;;
    *)
        echo "[vitrine-terminal] VITRINE_CLAUDE_ENABLED=${ENABLED} — internal Claude terminal DISABLED."
        echo "[vitrine-terminal] Operator I/O is the web panel on :7860 only. Set VITRINE_CLAUDE_ENABLED=1 to enable."
        exit 0
        ;;
esac
