# Inpainting Recovery for Gaussian Splat Training Images

## Overview

After decomposing a scene and extracting foreground objects, the original training
images contain "holes" where those objects were. To retrain a clean background-only
Gaussian splat, these holes must be filled with plausible background content. This
document covers the available inpainting models, workflow architecture, and
integration with the LichtFeld Studio pipeline.

## Available FLUX Inpainting Models

### FLUX.1 Fill Dev (Recommended)

- **Model**: `flux1-fill-dev.safetensors`
- **Source**: [Black Forest Labs](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev)
- **Type**: Purpose-built inpainting/outpainting diffusion model
- **Architecture**: FLUX rectified flow transformer, conditioned on masked image
- **Size**: ~23 GB (fp16)
- **License**: FLUX.1-dev Non-Commercial License
- **Key advantage**: Trained specifically for inpainting tasks, handles mask boundaries
  naturally without visible seams. Uses `InpaintModelConditioning` node which feeds
  the masked image directly into the model's conditioning pathway.

Required companion models:
- `clip_l.safetensors` (CLIP-L text encoder, ~235 MB)
- `t5xxl_fp16.safetensors` (T5-XXL text encoder, ~9.5 GB)
- `ae.safetensors` (FLUX autoencoder/VAE, ~320 MB)

### FLUX.1 Dev (Fallback)

- **Model**: `flux1-dev.safetensors`
- **Source**: [Black Forest Labs](https://huggingface.co/black-forest-labs/FLUX.1-dev)
- **Type**: General-purpose text-to-image model used with VAEEncodeForInpaint
- **Architecture**: Same FLUX transformer but not fine-tuned for inpainting
- **Size**: ~23 GB (fp16)
- **Approach**: Uses `VAEEncodeForInpaint` + `SetLatentNoiseMask` to inject noise
  only in masked regions. Combined with `DifferentialDiffusion` for smoother blending.
- **Quality**: Good but slightly worse mask boundary coherence than Fill model.

### FLUX 2 (Experimental)

- **Status**: ComfyUI has `EmptyFlux2LatentImage`, `Flux2Scheduler`, `Flux2MaxImageNode`,
  and `Flux2ProImageNode` nodes available, suggesting FLUX 2 support exists.
- **Availability**: No FLUX 2 inpainting-specific model identified yet.
- **CLIPLoader**: Supports `flux2` type in CLIPLoader, indicating text encoder support.

### FLUX Pro Fill (API-only)

- **Node**: `FluxProFillNode` available on the server
- **Type**: Cloud API node (requires Comfy Org API key)
- **Inputs**: image, mask, prompt, guidance (1.5-100), steps (15-50), seed
- **Quality**: Highest quality, but requires paid API access.
- **Not suitable** for local batch processing of training images.

### AliMama Inpainting ControlNet

- **Node**: `ControlNetInpaintingAliMamaApply` available
- **Type**: ControlNet-based inpainting guidance
- **Usage**: Can be combined with any base model for inpainting conditioning
- **Requires**: A compatible ControlNet model (none currently on server)
- **Approach**: Applies inpainting-specific ControlNet conditioning to positive and
  negative prompts, using the VAE to encode the masked image region.

## Workflow Architecture

### Primary Workflow: FLUX Fill

```
LoadImage ──────────────┐
                        ├──→ InpaintModelConditioning ──→ KSampler ──→ VAEDecode ──→ SaveImage
LoadImage → ImageToMask ┤                                    ↑
                        │                                    │
DualCLIPLoader ──→ CLIPTextEncode ───────────────────────────┘
                        │
UNETLoader ──→ DifferentialDiffusion ──→ FluxGuidance ──→ KSampler
                        │
VAELoader ──────────────┘
```

Key parameters:
- **Denoise**: 0.6-0.85 (0.75 default). Lower preserves more context, higher allows
  more creative fill.
- **Steps**: 20-30 (28 default). FLUX needs fewer steps than SD models.
- **CFG**: 1.0 (FLUX uses guidance scale via FluxGuidance node, not CFG).
- **Sampler**: euler with simple scheduler.
- **DifferentialDiffusion**: Ensures smooth blending at mask boundaries.

### Fallback Workflow: FLUX Dev + VAEEncodeForInpaint

```
LoadImage ────────────────────→ VAEEncodeForInpaint ──→ KSampler ──→ VAEDecode ──→ SaveImage
LoadImage → ImageToMask ──→ ↑          ↑                    ↑
                            │          │                    │
VAELoader ──────────────────┘──────────┘                    │
DualCLIPLoader → CLIPTextEncode ────────────────────────────┘
UNETLoader → DifferentialDiffusion → FluxGuidance ──→ KSampler
```

Differences from Fill workflow:
- Uses `VAEEncodeForInpaint` with `grow_mask_by=8` to feather mask edges
- No `InpaintModelConditioning`; the latent noise mask handles region masking
- Works with any FLUX diffusion model, not just the Fill variant

## Quality Comparison

| Method | Boundary Coherence | Content Quality | Speed | VRAM |
|--------|-------------------|-----------------|-------|------|
| FLUX Fill | Excellent | Excellent | ~15s/img | ~24 GB |
| FLUX Dev + VAEEncode | Good | Very Good | ~15s/img | ~24 GB |
| FLUX Pro Fill (API) | Excellent | Excellent | ~5s/img | Remote |
| AliMama ControlNet | Good | Good | ~12s/img | ~20 GB |

For Gaussian splat background recovery, FLUX Fill is strongly preferred because:
1. Boundary artifacts directly affect splat quality during retraining
2. The fill model maintains structural coherence across the inpainted region
3. Background textures (floors, walls, sky) need consistency, not creativity

## Recommended Prompts for Background Recovery

For Gaussian splat training image inpainting, use descriptive prompts about the
scene background rather than the removed object:

- Generic indoor: `"clean empty room background, matching floor and wall textures, photorealistic, consistent lighting"`
- Outdoor: `"natural ground and sky continuation, photorealistic, no objects"`
- Close-up: `"smooth continuous surface texture, matching surrounding material"`

Negative prompt: `"artifacts, distortion, blurry, text, watermark, objects, people, furniture"`

## Integration with LichtFeld Pipeline

### Pipeline State: INPAINT_BG

The orchestrator transitions to `INPAINT_BG` after object extraction (`EXTRACT_OBJECTS`
→ `MESH_OBJECTS` → `QUALITY_GATE_2` → `INPAINT_BG`).

### Configuration

The `InpaintConfig` dataclass in `src/pipeline/config.py` should be extended:

```python
@dataclass
class InpaintConfig:
    method: str = "comfyui"              # "comfyui" or "gaussian"
    comfyui_api_url: str = "http://localhost:3001"
    comfyui_direct_url: str = "http://localhost:8189"
    local_ip: str = "192.168.2.1"
    hf_token: str = ""
    model: str = "flux-fill"             # "flux-fill", "flux-dev", "auto"
    denoise: float = 0.75
    steps: int = 28
    guidance: float = 30.0
    auto_download_models: bool = True
    blend_radius: float = 2.0
    iterations: int = 10000              # for gaussian fallback
```

### Client Usage

```python
from pipeline.comfyui_inpainter import ComfyUIInpainter

with ComfyUIInpainter(
    api_url="http://localhost:3001",
    comfyui_url="http://localhost:8189",
    local_ip="192.168.2.1",
    denoise=0.75,
    steps=28,
) as inpainter:
    # Check server health
    assert inpainter.health_check()

    # Auto-download models if needed
    inpainter.ensure_flux_fill_models()

    # Inpaint single image
    result = inpainter.inpaint(
        image=source_image,      # PIL Image or numpy array
        mask=binary_mask,        # White = inpaint region
        prompt="clean empty background, photorealistic",
    )
    clean_image = result.image   # numpy H x W x 3

    # Batch process training images
    results = inpainter.inpaint_batch([
        (img1, mask1, "indoor room background"),
        (img2, mask2, "outdoor ground continuation"),
    ])
```

### ComfyUI API (in-stack)

Inpainting runs against the in-stack **`vitrine-comfyui`** container — native
ComfyUI on `:8188`, reached over the `v2g-net` bus as
`http://vitrine-comfyui:8188` (`V2G_COMFYUI_URL`). Weights load from the unified
model tree `data/comfyui/models` (FLUX.2 inpaint), so there is no model download
step and no external API — image data flows over the shared docker network and
bind mounts, not over remote API calls.

Native ComfyUI endpoints used:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/prompt` | POST | Queue a workflow for execution |
| `/history/{prompt_id}` | GET | Poll for completion + outputs |
| `/view` | GET | Fetch a rendered output image |
| `/object_info` | GET | Node/model catalog (version-check, ADR-014) |
| `/interrupt` | POST | Cancel running workflow |

Image inputs are written to the shared output/scratch mounts (or passed via the
`LoadImage` node); results are read back from `/view`.

### Models are pre-staged (no download step)

Inpainting weights live in the unified model tree `data/comfyui/models` and are
mounted into the container — there is no runtime model download. FLUX.1-Fill-dev
(`data/comfyui/models/diffusion_models/flux1-fill-dev.safetensors`) and the FLUX
text encoders are already present; version-check and pin per ADR-014 before use.

## ComfyUI capability inventory

### Available Nodes (inpainting-relevant)
- `InpaintModelConditioning` - For Fill-type inpainting models
- `VAEEncodeForInpaint` - Generic inpainting via latent masking
- `DifferentialDiffusion` - Smooth mask boundary blending
- `FluxGuidance` - FLUX-specific guidance application
- `CLIPTextEncodeFlux` - FLUX-specific CLIP encoding
- `ControlNetInpaintingAliMamaApply` - AliMama ControlNet inpainting
- `SetLatentNoiseMask` - Manual latent noise masking
- `GrowMask`, `FeatherMask`, `InvertMask` - Mask manipulation
- `ImageToMask`, `MaskToImage` - Mask conversion

### Available VAE Decoders
- `taef1_decoder.pth` (FLUX tiny AE decoder)
- `taesd3_decoder.pth` (SD3 tiny AE decoder)
- `taesd_decoder.pth` (SD1.5 tiny AE decoder)
- `taesdxl_decoder.pth` (SDXL tiny AE decoder)

### Models (pre-staged in `data/comfyui/models`)
- `diffusion_models/flux1-fill-dev.safetensors` (~23 GB)
- `text_encoders/t5xxl_fp16.safetensors` (~9.5 GB)
- `clip/clip_l.safetensors` (~235 MB)
- `vae/ae.safetensors` (~320 MB)
- Total: ~33 GB — all present in the unified tree

### GPU
- 2× NVIDIA RTX 6000 Ada Generation (48 GB VRAM each; GPU0 main, GPU1 sidecars)
- Sufficient for all FLUX models at fp16

## Gaussian Splats Repair LoRA

No specific "Gaussian Splats Repair" LoRA was identified for FLUX. The closest
approaches for improving inpainting quality in the context of splat training data:

1. **Texture consistency LoRAs**: Fine-tune on the specific scene's background
   textures to improve fill coherence. Would require generating a small training
   dataset from unmasked background regions.

2. **Architecture photography LoRAs**: Available FLUX LoRAs trained on architectural
   photography could improve indoor/outdoor scene fills.

3. **Custom training**: For production pipelines, training a LoRA on clean versions
   of the target scene type (e.g., empty rooms of similar style) would yield the
   best results.

The LoRA loader infrastructure exists on the server (`LoraLoader`, `LoraLoaderModelOnly`)
but no LoRA files are currently present.

## Recommendations

1. **Download FLUX Fill models first** - the 33 GB download is a one-time cost
   and the RTX 6000 Ada has ample VRAM.

2. **Use denoise 0.70-0.80** for background recovery - lower values preserve
   surrounding context better, critical for multi-view consistency.

3. **Grow masks by 6-10 pixels** before inpainting to avoid hard edges from
   imperfect SAM2 segmentation boundaries.

4. **Process all views of the same scene with the same seed** for temporal
   consistency across training frames.

5. **Consider the AliMama ControlNet path** as future enhancement if boundary
   quality needs improvement beyond what FLUX Fill provides.
