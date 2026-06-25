#!/usr/bin/env bash
# Container-side startup for the owner ComfyUI (ADR-014), mounted + run by
# scripts/run_comfyui.sh. The gaussian-toolkit image ships ComfyUI's base deps
# but NOT the custom-node Python deps (TRELLIS2 / Hunyuan3D-2.1 / Manager), and
# its `safetensors` dist-info has corrupt metadata that makes the `transformers`
# version check raise `ValueError: ... found=None` the moment the Hunyuan3D node
# imports it — crashing ComfyUI on startup (exit 1). run_comfyui.sh recreates a
# fresh container each launch, so the repair must run here, every launch.
#
# Idempotent and quick when already satisfied. To bake these into the image
# instead (and drop this step) add them to Dockerfile.consolidated's ComfyUI phase.
set -uo pipefail
PY=/usr/bin/python3.12
SITE=/usr/local/lib/python3.12/dist-packages

echo "[comfyui-entrypoint] installing custom-node deps..."
# 1) Install the Hunyuan3D-2.1 node's own requirements.txt (diffusers, accelerate,
#    trimesh, pymeshlab, open3d, transformers, ...) plus the extras the nodes
#    import but don't pin: GitPython + toml (ComfyUI-Manager), loguru (Hunyuan3D).
HUNYUAN_REQ=/comfyui/custom_nodes/ComfyUI-Hunyuan3d-2-1/requirements.txt
[ -f "$HUNYUAN_REQ" ] && $PY -m pip install --break-system-packages -q -r "$HUNYUAN_REQ" >/dev/null 2>&1 || true
# Extras the nodes import but don't pin: GitPython+toml (Manager); loguru + rembg
# + onnxruntime (Hunyuan3D-2.1 — rembg needs an ONNX backend or it raises on import).
$PY -m pip install --break-system-packages -q GitPython toml loguru rembg onnxruntime >/dev/null 2>&1 || true

# 1b) ComfyUI-TRELLIS2 deps. These ARE pip-installable (verified 2026-06-19):
#     comfy-env, comfy-sparse-attn (ships a prebuilt cp312 wheel — no compile),
#     comfy-3d-viewers, trimesh[easy]. Without them the node fails to import
#     (ModuleNotFoundError: comfy_sparse_attn) and TRELLIS.2 — our designated
#     primary hull (ADR-015) — is silently absent. Weights live in the native
#     model tree at /comfyui/models/trellis2. Install BEFORE the safetensors
#     repair so the repair stays last.
TRELLIS_REQ=/comfyui/custom_nodes/ComfyUI-TRELLIS2/requirements.txt
[ -f "$TRELLIS_REQ" ] && $PY -m pip install --break-system-packages -q -r "$TRELLIS_REQ" >/dev/null 2>&1 || true

# 1c) ComfyUI-TRELLIS2 CUDA extensions + runtime deps (verified end-to-end
#     2026-06-19: produced a GLB from a single image). The node's comfy_env/pixi
#     "one-click install" is bypassed (we run in the main env), so install the
#     CUDA wheels directly from PozzettiAndrea's prebuilt index — these are the
#     EXACT cu130/torch2.11/cp312 builds matching this image (NO compilation).
#     If the image's torch/CUDA/python changes, update the tag in $CW below
#     (browse https://pozzettiandrea.github.io/cuda-wheels/v2/<pkg>/).
CW="https://github.com/PozzettiAndrea/cuda-wheels/releases/download"
TAG="cu130torch2.11-cp312-cp312-manylinux_2_34_x86_64.manylinux_2_35_x86_64.whl"
TAG35="cu130torch2.11-cp312-cp312-manylinux_2_35_x86_64.whl"
$PY -m pip install --break-system-packages -q --no-deps \
  "$CW/cumesh_vb-latest/cumesh_vb-1.0%2B$TAG35" \
  "$CW/o_voxel_vb_ap-latest/o_voxel_vb_ap-0.0.1%2B$TAG" \
  "$CW/flex_gemm_vb-latest/flex_gemm_vb-1.0.0%2B$TAG" \
  "$CW/flex_gemm_ap-latest/flex_gemm_ap-1.0.0%2B$TAG" \
  "$CW/drtk-latest/drtk-0.1.0%2B$TAG" >/dev/null 2>&1 || true
# Pure-python runtime deps the TRELLIS pipeline imports (utils3d needs --no-deps
# to avoid a resolver conflict; the rest install clean).
$PY -m pip install --break-system-packages -q easydict igraph xatlas zstandard >/dev/null 2>&1 || true
$PY -m pip install --break-system-packages -q --no-deps utils3d >/dev/null 2>&1 || true

# 1d) Disable the fake cv2 shim from comfyui-sam3dobjects. It shadows the real
#     OpenCV with scipy/skimage fallbacks that segfault on large textures (4096px
#     PBR inpaint → scipy.sparse.linalg.spsolve SIGSEGV). Real OpenCV (cv2) is
#     installed in the image — the shim must not override it.
SAM3D_CV2=/comfyui/custom_nodes/comfyui-sam3dobjects/vendor/cv2
[ -d "$SAM3D_CV2" ] && mv "$SAM3D_CV2" "${SAM3D_CV2}.disabled" 2>/dev/null && \
  echo "[comfyui-entrypoint] disabled cv2 shim from comfyui-sam3dobjects" || true

# 1e) Patch a ComfyUI-TRELLIS2 PBR-rasterize bug (Trellis2RasterizePBR). The node
#     does `cv2.inpaint(single_channel, ...)[..., None]` for the metallic/roughness/
#     alpha maps; on OpenCV 4.13 that yields a 4-D array, so np.concatenate with the
#     3-D base_color raises "all the input arrays must have same number of dimensions"
#     and texturing fails. Force each map to (texture_size, texture_size, 1).
#     Idempotent (no-op once patched). Remove if the upstream pack fixes it.
UNWRAP=/comfyui/custom_nodes/ComfyUI-TRELLIS2/nodes/nodes_unwrap.py
[ -f "$UNWRAP" ] && $PY - "$UNWRAP" <<'PYEOF' >/dev/null 2>&1 || true
import sys
f=sys.argv[1]; s=open(f).read()
s=s.replace(", cv2.INPAINT_TELEA)[..., None]", ", cv2.INPAINT_TELEA).reshape(texture_size, texture_size, 1)")
open(f,"w").write(s)
PYEOF

# 2) Repair safetensors LAST. The image's safetensors imports fine on its own,
#    but installing diffusers/transformers deps above corrupts its dist-info
#    metadata ("invalid metadata entry 'name'" -> importlib version() == None),
#    which makes transformers' require_version() raise and crashes ComfyUI on
#    startup. Physically remove the broken dist-info + package, then reinstall
#    clean so this is the final, valid state. (force-reinstall alone is NOT
#    enough — pip can't overwrite the unreadable dist-info.)
echo "[comfyui-entrypoint] repairing safetensors metadata..."
rm -rf "$SITE"/safetensors "$SITE"/safetensors-*.dist-info 2>/dev/null || true
$PY -m pip install --break-system-packages -q safetensors >/dev/null 2>&1 || true

# NOTE (resolved 2026-06-19): ComfyUI-TRELLIS2's `comfy_sparse_attn` / `comfy_env`
# are installed via the pip step 1b above — comfy-sparse-attn 0.1.3 ships a prebuilt
# cp312 wheel, so no source build is needed. TRELLIS.2 is the active primary hull.

# 3) FLUX.2 Mistral-3 tokenizer fix (ComfyUI v0.8.2 bug). The Mistral tekken
#    tokenizer returns an empty list for tokenizer(""), but SDTokenizer.__init__
#    unconditionally does `self.start_token = empty[0]` → IndexError. Upstream
#    ComfyUI (post-v0.8.2) added a `len(empty) > 0` guard + explicit start_token
#    parameter. Patch both sd1_clip.py (guard) and flux.py (start_token=1).
#    Idempotent (no-op once patched). Remove when upgrading to ComfyUI ≥ 0.8.3.
SD1_CLIP=/comfyui/comfy/sd1_clip.py
[ -f "$SD1_CLIP" ] && $PY - "$SD1_CLIP" <<'PYEOF' >/dev/null 2>&1 || true
import sys
f=sys.argv[1]; s=open(f).read()
if 'len(empty) > 0' in s:
    print('[comfyui-entrypoint] sd1_clip.py already patched — skip')
    sys.exit(0)
# Add start_token=None parameter to SDTokenizer.__init__
s=s.replace('tokenizer_args={}):', 'tokenizer_args={}, start_token=None):')
# Replace the crash-prone block with the guarded version
s=s.replace(
    '        if has_start_token:\n'
    '            self.tokens_start = 1\n'
    '            self.start_token = empty[0]\n',
    '        if has_start_token:\n'
    '            if len(empty) > 0:\n'
    '                self.tokens_start = 1\n'
    '                self.start_token = empty[0]\n'
    '            else:\n'
    '                self.tokens_start = 0\n'
    '                self.start_token = start_token\n'
    '                if start_token is None:\n'
    '                    import logging\n'
    '                    logging.warning("WARNING: There\'s something wrong with your tokenizers.")\n'
)
open(f,"w").write(s)
print('[comfyui-entrypoint] sd1_clip.py patched (empty tokenizer guard)')
PYEOF

FLUX_PY=/comfyui/comfy/text_encoders/flux.py
[ -f "$FLUX_PY" ] && $PY - "$FLUX_PY" <<'PYEOF' >/dev/null 2>&1 || true
import sys
f=sys.argv[1]; s=open(f).read()
if 'start_token=1' in s:
    print('[comfyui-entrypoint] flux.py already patched — skip')
    sys.exit(0)
# Patch Mistral3Tokenizer to pass start_token=1 to parent (so the guarded
# fallback in sd1_clip.py uses token 1 instead of None when the Mistral
# tokenizer returns an empty list for encode("")).
s=s.replace(
    'tokenizer_args=load_mistral_tokenizer(self.tekken_data), tokenizer_data=tokenizer_data)',
    'tokenizer_args=load_mistral_tokenizer(self.tekken_data), tokenizer_data=tokenizer_data, start_token=1)'
)
open(f,"w").write(s)
print('[comfyui-entrypoint] flux.py patched (Mistral3Tokenizer start_token=1)')
PYEOF

# ---------------------------------------------------------------------------
# Hunyuan3D-2.1 object-constructor enablement (the SAM-crop turnaround path).
# Builds the two extensions the paint/export stages need, patches the paintpbr
# loaders for trust_remote_code, and symlinks the staged 2.1 weights into the
# folders the Hy3D21 nodes scan. Idempotent. The custom_rasterizer build bypasses
# PyTorch's strict CUDA-version check (system nvcc 12.8 vs torch cu130 — the kernel
# links fine against cu130 torch). See memory object-recon-sam-crop-turnaround-redo.
HY3D=/comfyui/custom_nodes/ComfyUI-Hunyuan3d-2-1
SP=$($PY -c 'import site;print(site.getsitepackages()[0])' 2>/dev/null || echo /usr/local/lib/python3.12/dist-packages)
_build_ext() {  # $1 = ext source dir, $2 = .so glob to copy
    ( cd "$1" && TORCH_CUDA_ARCH_LIST=8.9 $PY -c "
import torch.utils.cpp_extension as c; c._check_cuda_version=lambda *a,**k: None
import runpy,sys; sys.argv=['setup.py','build_ext','--inplace']; runpy.run_path('setup.py',run_name='__main__')" >/dev/null 2>&1
      cp -f build/lib*/$2 "$SP/" 2>/dev/null )
}
if [ -d "$HY3D" ]; then
    $PY -c 'import torch,custom_rasterizer' >/dev/null 2>&1 || {
        echo "[comfyui-entrypoint] building custom_rasterizer ..."
        _build_ext "$HY3D/hy3dpaint/custom_rasterizer" "custom_rasterizer_kernel*.so"
        cp -rn "$HY3D/hy3dpaint/custom_rasterizer/custom_rasterizer" "$SP/" 2>/dev/null || true; }
    $PY -c 'import mesh_inpaint_processor' >/dev/null 2>&1 || {
        echo "[comfyui-entrypoint] building mesh_inpaint_processor ..."
        _build_ext "$HY3D/hy3dpaint/DifferentiableRenderer" "mesh_inpaint_processor*.so"; }
    sed -i 's/torch_dtype=torch.float16$/torch_dtype=torch.float16, trust_remote_code=True/' "$HY3D/hy3dpaint/utils/multiview_utils.py" 2>/dev/null || true
    sed -i 's/DiffusionPipeline.from_pretrained(\*\*stable_diffusion_config)/DiffusionPipeline.from_pretrained(**stable_diffusion_config, trust_remote_code=True)/' "$HY3D/hy3dpaint/hunyuanpaintpbr/unet/model.py" 2>/dev/null || true
fi
_DIT=/comfyui/models/hunyuan3d-2.1/hunyuan3d-dit-v2-1/model.fp16.ckpt
_VAE=/comfyui/models/hunyuan3d-2.1/hunyuan3d-vae-v2-1/model.fp16.ckpt
[ -f "$_DIT" ] && ln -sf "$_DIT" /comfyui/models/diffusion_models/hunyuan3d-dit-v2-1-fp16.ckpt 2>/dev/null || true
[ -f "$_VAE" ] && ln -sf "$_VAE" /comfyui/models/vae/Hunyuan3D-vae-v2-1-fp16.ckpt 2>/dev/null || true

echo "[comfyui-entrypoint] launching ComfyUI on :8188 ..."
# CUDA_VISIBLE_DEVICES (set by run_comfyui.sh) already masks to the chosen GPU,
# so the in-container device index is 0.
exec $PY main.py --listen 0.0.0.0 --port 8188 --cuda-device 0 \
    --extra-model-paths-config /comfyui/extra_model_paths.yaml --preview-method auto
