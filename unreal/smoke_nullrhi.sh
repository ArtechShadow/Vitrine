#!/usr/bin/env bash
# Vitrine UE 5.8 nullrhi boot smoke-test (run on the HOST).
#
# Foundational probe BEFORE the full overlay: does UnrealEditor-Cmd boot inside
# vitrine-unreal:5.8 against the bind-mounted engine, run a python commandlet,
# read our v2g:* scene.usda via pxr, and spawn a UsdStageActor? No GPU needed
# (-nullrhi), so it won't contend for GPU1.
#
# The runtime/engine mounts are read-only, so the project (which UE must write
# Saved/Intermediate into) is copied to a writable /tmp/proj inside the container.
# Log is written to data/scratch/unreal_probe.log (readable from the agentbox mount).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USD="${VITRINE_USD:-/usd_input/exhibit/scene.usda}"
LOG_HOST="$REPO/unreal/_smoke_out/unreal_probe.log"
mkdir -p "$REPO/unreal/_smoke_out"

echo "REPO=$REPO"
echo "VITRINE_USD=$USD"
echo "engine: $REPO/unreal/engine  (-> /opt/ue:ro)"
ls -la "$REPO/unreal/engine/Engine/Binaries/Linux/UnrealEditor-Cmd" || { echo "MISSING UE binary"; exit 2; }

docker rm -f vitrine-unreal-probe 2>/dev/null || true

timeout 900 docker run --rm --name vitrine-unreal-probe \
  --user 1000:1000 \
  --entrypoint bash \
  -e VITRINE_USD="$USD" \
  -e UE_ROOT=/opt/ue \
  -e HOME=/tmp \
  -v "$REPO/unreal/engine":/opt/ue:rw \
  -v "$REPO/output":/usd_input:ro \
  -v "$REPO/unreal/runtime":/vitrine/unreal:ro \
  vitrine-unreal:5.8 -c '
    set -uo pipefail
    UE=/opt/ue/Engine/Binaries/Linux/UnrealEditor-Cmd
    echo "[host] UE binary: $UE"; ls -la "$UE" || { echo "[host] UE binary missing"; exit 2; }
    echo "[host] copying project to writable /tmp/proj ..."
    cp -r /vitrine/unreal /tmp/proj
    echo "[host] launching UnrealEditor-Cmd (nullrhi) ..."
    "$UE" /tmp/proj/Vitrine.uproject \
      -run=pythonscript -script=/tmp/proj/_smoke_probe.py \
      -nullrhi -unattended -nopause -nosplash -stdout -FullStdOutLogOutput
    rc=$?
    echo "[host] UnrealEditor-Cmd exit=$rc"
    exit $rc
  ' 2>&1 | tee "$LOG_HOST"

echo "PROBE_PIPELINE_RC=${PIPESTATUS[0]}"
echo "log saved to: $LOG_HOST"
