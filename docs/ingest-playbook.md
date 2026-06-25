# Ingest Playbook — video → CoMe mesh → UE (reworked 2026-06-23)

The current best-practice, lessons-learned recipe for taking a capture to a textured game-asset
scene. Supersedes ad-hoc steps. Every "❌ lesson" is a mistake this project actually made — heed it.

---

## 0. Capture (the single biggest lever)

Motion blur, not coverage, is the usual bottleneck (`recon_quality_metrics.py` measured **0%
under-observed** on dense room captures). Motion blur ∝ exposure time × motion.

- **4K / 30 fps at the *highest bitrate* the app allows.** ❌ Do NOT shoot 60 fps: at a fixed
  bitrate ceiling, 60 fps **halves bits/frame** → more compression softening (measured: −26 %
  bits/frame → −27 % sharpness). 30 fps gives sharper individual frames.
- **Short exposure is the real fix:** bright/even light, or lock **shutter ≥ 1/500 s** + lock
  AE/AF/WB in a pro app (mcpro24fps / FiLMiC). Locked exposure is *good* (consistent appearance for
  matching); blown highlights become local holes — masked later.
- **Move slowly, smoothly, micro-pause** ~½ s at key viewpoints (the sampler harvests those).
- **Best quality = RAW photo burst** (no video compression, very short exposure) — if feasible.
- Portrait is fine — `rotation=-90` metadata is auto-applied by ffmpeg on decode (frames come out
  upright); confirm extracted size, don't trust the raw stream WxH.

## 1. Ingest + probe

```
hf download / gdown <id> -O data/raw/<scene>/capture.mp4   # auth via ~/.hf_token if HF throttles
ffprobe -show_entries stream=codec_name,width,height,r_frame_rate,bit_rate,nb_frames
# bits/frame = bitrate / fps  ← the real sharpness predictor; check rotation side_data
```

## 2. Frame selection — `scripts/blur_aware_fifo_sampler.py`

```
python3 scripts/blur_aware_fifo_sampler.py <video> output/<scene> \
    --window 8 --target 800 --score-height 1440 --select-by sfm
```
- **`--select-by sfm`** (default): per overlap window keep the max **SfM-utility** frame =
  *texture complexity × noise-corrected sharpness*. ❌ Don't select on raw blur alone — a sharp
  blank wall has no features, and noise inflates Laplacian variance (false sharpness).
- **Score at full/high res** (1440+). ❌ 960 p `blurdetect` under-discriminates (downscale erases
  the high-freq blur signal — it falsely read "uniformly blurry"; full-4K Laplacian showed 37–105×).
- **Target ~700–900 frames.** ❌ Do NOT go 1500+ — COLMAP global bundle-adjustment cost scales
  badly with image count; 1,656 frames made one BA round take 32 min (~4 h total). A room
  reconstructs just as well from ~750 well-spread sharp frames.
- Output is **lossless full-res PNG + `manifest.json`** (per-frame source-index, sharp/noise/
  complexity, **sha256**, source-video hash). `--verify <dir>` re-checksums after any hop — frame
  integrity is preserved across container↔host↔COLMAP↔mesh.
- To re-trim an existing set without re-extracting: re-bin the manifest by `source_frame`, keep the
  max-score frame per bin, symlink.

## 3. Masking (optional) — `src/pipeline/scene_masking.py`

```
python3 -m pipeline.scene_masking output/<scene>/images output/<scene> \
    --colmap-mask-dir output/<scene>/colmap_masks [--people]
```
- Highlight masking is **model-free** (numpy). Person masking needs a SAM/seg model in ComfyUI.
- Writes **both** conventions: COLMAP `<dir>/<img>.png` (255=keep) + LichtFeld `<scene>/masks/<img>`.
- ❌ Don't over-invest in masking for the **CoMe** path: SfM already RANSAC-rejects a moving person,
  and **CoMe (Confidence-based Mesh Extraction) drops transient/low-confidence regions by design**.
  Masking's real payoff is the **LichtFeld** path (`--mask-mode ignore`, loss-level). For CoMe,
  COLMAP `--ImageReader.mask_path` (one flag) is enough.

## 4. SfM — direct COLMAP (NOT SplatReady, which ignores masks)

> LichtFeld has **no SfM of its own** (it only *reads* a COLMAP/transforms model) — so our COLMAP is
> required, not a duplication. ❌ COLMAP 4.1's rig/frame refactor renamed flags — verify against
> `colmap <stage> --help` on the actual build, don't trust old recipes: `--FeatureExtraction.use_gpu`
> / `--FeatureMatching.use_gpu` (not `--SiftExtraction.use_gpu`), and **`--Mapper.ba_global_frames_ratio`**
> (NOT `ba_global_images_ratio` — "images" → "frames"; the old name aborts the mapper with
> `set -e`). The log saying `num_reg_frames=` is the tell that this build is frames-terminology.

```
colmap feature_extractor --database_path DB --image_path img --ImageReader.single_camera 1 \
    --ImageReader.camera_model OPENCV --ImageReader.mask_path <colmap_masks> --FeatureExtraction.use_gpu 1
colmap sequential_matcher --database_path DB --FeatureMatching.use_gpu 1 \
    --SequentialMatching.overlap 10 --SequentialMatching.quadratic_overlap 1
colmap mapper --database_path DB --image_path img --output_path sparse \
    --Mapper.ba_global_frames_ratio 1.32 --Mapper.ba_global_points_ratio 1.32   # ← fewer global-BA rounds
colmap image_undistorter --image_path img --input_path sparse/0 --output_path undistorted --output_type COLMAP
```
Sequential matcher (video frames are ordered). The mapper is **CPU-bound** (BA) — GPU idles during it.

- ❌ **Sequential-only matching fragments room video.** On the locked dreamlab capture, `overlap 10`
  gave a *disconnected* graph (6,477 verified pairs) → COLMAP split into 7 sub-models, largest only
  **537/750 (72%)**. Fix: **exhaustive matching** (`colmap exhaustive_matcher --FeatureMatching.use_gpu 1`)
  — at 750 frames it verified all `C(750,2)=280,875` pairs (~28 min on GPU0) and the re-map registered
  **750/750 into one model** (367k pts, 1.16px reproj). For a room (all frames co-visible) exhaustive is
  the right default; vocab-tree loop detection is the lighter alternative once frame count climbs past ~1k.
- ❌ **Undistort the LARGEST model, not `sparse/0`.** COLMAP numbers sub-models by completion, not size —
  `ls sparse/*/ | head -1` can grab a 2-image fragment. Select by registered-image count.

## 5. Mesh — CoMe (preferred) — `scripts/run_come.sh` + `come_extractor`

CoMe trains its **own** gaussians (30k iters, GPU1) from the undistorted COLMAP, then
`extract_mesh_tets.py` (real-world marching tetrahedra). ❌ Two CoMe-on-a-fresh-container gotchas
`run_come.sh` now auto-handles: (1) **fused_ssim** — `train.py` imports `fused_ssim` but the vendored
pkg is `decoupled_fused_ssim`; build it (`pip install --no-build-isolation submodules/decoupled-fused-ssim`,
`TORCH_CUDA_ARCH_LIST=8.9`) **and symlink** `decoupled_fused_ssim → fused_ssim` in site-packages, else
`ModuleNotFoundError`. (2) **layout** — CoMe wants the model at `sparse/0/` in classic format, but
`image_undistorter` writes it flat at `sparse/` in COLMAP 4.1 binary → `colmap model_converter
--output_type TXT` into `sparse/0/`. (3) **tetra-triangulation** — `extract_mesh_tets.py` needs the
`tetranerf` C++ ext (best-effort build, usually absent on a fresh container) → **prefer
`extract_mesh_tsdf.py`** (no tetranerf, and the TSDF mesh is cleaner than raw tets, which needs heavy
cleanup just to reach TSDF-parity).
❌ **TSDF `--voxel_size` is in COLMAP world units, not normalized** — the `0.002` default assumes a
unit scene and OOMs Open3D's voxel-block grid (our room spans ~9.58 units → 0.002 = 4790 cells, OOM
at frame 7/750). Compute the robust scene extent (2–98 pct of `points3D`) and set `voxel ≈ extent/~640`
(we used **0.015** → 3.2M-face mesh in 5.5 min). Then **clean floaters with Open3D
`cluster_connected_triangles`** (37k components; keep ≥0.5 % of the largest, `remove_triangles_by_mask`)
— NOT `trimesh.split` (builds a Trimesh per blob → ~20 min stall on 3.2M faces). Result: 2.7M-face
vertex-coloured room mesh, bbox tightened to the true room extent. CoMe is NON-COMMERCIAL — fine here.

## 6. Texture → FBX → UE

`scene_texture_fast.py` (xatlas bake; skip MeshCleaner — it hangs) → `scene_to_ue.py` (M, gravity-
align) → `blender_obj_to_fbx.py` (×0.01) → UE `ue_place_prescaled.py` (restart-first, scale=1.0,
no `get_actor_bounds`). See `dreamlab-mesh-into-ue-pipeline`, `ue-live-assembly-flaky-use-blender`.

## Run hygiene

- **GPU split:** GPU0 = gaussian-toolkit (COLMAP, LichtFeld, ComfyUI). GPU1 = come / milo.
- **Thermals:** re-arm the 15-min Monitor before GPU-heavy stages; 200 W cap, throttle ~83 °C.
- **Disk:** watch it (4K frame sets are GB-scale); remove a capture's working frames once its ingest
  is fully consumed (keep during active work).
- **Don't reinvent** what LichtFeld provides (masks, PPISP exposure modelling); **do** provide what it
  lacks (SfM, mask *generation*). The flag error + the 4 h COLMAP were both "engineering past" symptoms.
