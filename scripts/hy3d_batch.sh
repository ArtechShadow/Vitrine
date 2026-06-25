#!/bin/bash
# Restart-resilient Hunyuan3D-2.1 object batch (agent-side: can docker-restart comfyui).
# One object at a time, /free between, auto-restart comfyui on crash, checkpoint-skip
# objects that already have a GLB, GPU temp guard. Run from the agent host.
set -u
OBJS=${1:-"ladder mitre_saw table toolbox workbench"}
COMFY=http://vitrine-comfyui:8188
GT() { docker exec gaussian-toolkit bash -lc "$1"; }

health() { curl -s -m5 $COMFY/system_stats -o /dev/null -w '%{http_code}' 2>/dev/null; }
hy3d_ready() { GT "curl -s -m8 $COMFY/object_info 2>/dev/null" | grep -q Hy3DMeshGenerator && echo yes; }
free_vram() { curl -s -m15 -X POST $COMFY/free -H 'Content-Type: application/json' \
                 -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1; }
gpu_temp() { GT "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits" 2>/dev/null | head -1 | tr -d ' '; }
glb_done() { GT "ls /comfyui/output/dreamlab/${1}_hull*.glb" >/dev/null 2>&1; }

wait_comfy() {
  for i in $(seq 1 48); do
    [ "$(health)" = "200" ] && [ "$(hy3d_ready)" = "yes" ] && { echo "  comfy ready"; return 0; }
    sleep 5
  done
  echo "  comfy NOT ready after wait"; return 1
}
restart_comfy() { echo "  restarting vitrine-comfyui ..."; docker restart vitrine-comfyui >/dev/null 2>&1; sleep 12; wait_comfy; }

for obj in $OBJS; do
  if glb_done "$obj"; then echo "SKIP $obj (GLB exists)"; continue; fi
  echo "=== $obj  $(date +%H:%M:%S) ==="
  t=$(gpu_temp); echo "  gpu ${t}C"
  while [ "${t:-0}" -gt 82 ] 2>/dev/null; do echo "  too hot (${t}C), cooling 30s"; sleep 30; t=$(gpu_temp); done
  [ "$(health)" = "200" ] || restart_comfy
  ok=0
  for attempt in 1 2 3; do
    GT "python3 /tmp/hy3d_one.py /data/output/dreamlab/obj_crops/${obj}.png ${obj}"
    rc=$?
    echo "  $obj attempt $attempt rc=$rc"
    [ $rc -eq 0 ] && { ok=1; break; }
    if [ $rc -eq 3 ]; then restart_comfy || break; else
      # rejected/timeout/produced-missing: free + one more try
      free_vram; sleep 5
    fi
  done
  free_vram
  if [ $ok -eq 1 ]; then echo "  OK $obj"; else echo "  FAIL $obj"; fi
done
echo "BATCH COMPLETE $(date +%H:%M:%S)"
GT "ls -la /comfyui/output/dreamlab/*_hull*.glb 2>/dev/null"
