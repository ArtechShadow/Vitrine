F=/comfyui/custom_nodes/ComfyUI-TRELLIS2/nodes/nodes_unwrap.py
python3.12 - "$F" <<'PY'
import sys,re
f=sys.argv[1]; s=open(f).read()
before=s.count("[..., None]")
s=s.replace(", cv2.INPAINT_TELEA)[..., None]", ", cv2.INPAINT_TELEA).reshape(texture_size, texture_size, 1)")
open(f,"w").write(s)
print("patched lines (was [...,None]):", before, "remaining:", s.count("cv2.INPAINT_TELEA)[..., None]"))
print("reshape count now:", s.count("reshape(texture_size, texture_size, 1)"))
PY
