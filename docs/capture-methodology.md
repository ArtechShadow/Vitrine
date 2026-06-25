# Video Capture Methodology for Gaussian Splatting

A practical guide to recording video that produces high-quality 3D Gaussian Splat reconstructions. Every recommendation here exists because the opposite causes COLMAP to fail, training to diverge, or the final splat to contain artifacts.

---

## Table of Contents

1. [Camera Movement](#1-camera-movement)
2. [Lighting](#2-lighting)
3. [Scenes That Work Well](#3-scenes-that-work-well)
4. [Scenes That Cause Failure](#4-scenes-that-cause-failure)
5. [Camera Settings](#5-camera-settings)
6. [Capture Patterns](#6-capture-patterns)
7. [Post-Processing Before Pipeline](#7-post-processing-before-pipeline)
8. [What NOT to Do](#8-what-not-to-do)
9. [Quick Reference Checklist](#9-quick-reference-checklist)

---

## 1. Camera Movement

The reconstruction pipeline (COLMAP feature matching followed by 3DGS training) needs sharp, well-overlapping frames. Movement quality is the single largest factor in capture success.

### Speed

- **Maximum walking speed: 0.5 m/s** (about half normal walking pace).
- If you are unsure, you are probably moving too fast. Slow down further.
- Count "one-mississippi" per step as a rough governor.

### Stabilization

| Method | Acceptable? | Notes |
|--------|-------------|-------|
| Gimbal (DJI RS, Zhiyun) | Best | Eliminates micro-shake and rolling shutter artifacts |
| Tripod dolly / slider | Best | Perfect for controlled indoor shoots |
| Handheld with two hands | Marginal | Only in bright light with fast shutter; expect some frame loss |
| Single-hand phone | Poor | Motion blur on most frames; avoid |

Handheld capture introduces per-frame motion blur that destroys feature matching. If you must go handheld, brace the camera against your body with both hands and use a wide-angle lens to reduce apparent shake.

### Trajectory

- **Orbit around objects of interest.** Full 360-degree coverage of every important item. Do not stand in one spot and pan -- physically move around the subject.
- **Move laterally, not just forward.** Walking straight ahead like a hallway video produces minimal parallax. Instead, sidestep, arc, and weave. The pipeline needs triangulation, and triangulation needs baseline (physical distance between viewpoints).
- **Overlap requirement: every point in the scene should be visible from at least 5 different viewpoints.** This means revisiting areas from different angles, not just passing through once.

### What "good movement" looks like in practice

Imagine you are a nature documentary camera operator circling a sculpture. You move slowly in a smooth arc, keeping the subject centered, then step closer, then step back out and continue the orbit at a different height. That continuous, deliberate sweep is exactly what the pipeline needs.

---

## 2. Lighting

Gaussian splatting bakes illumination into the splat. Inconsistent lighting across frames creates ghosting, floaters, and color inconsistency in the reconstruction.

### Preferred Conditions

- **Even, diffuse lighting.** Overcast sky outdoors is ideal. Indoors, use large soft light panels or bounce lights off the ceiling.
- **Consistent brightness across the capture.** If you start in a bright area and walk into a dark corridor, the reconstruction will struggle at the transition.

### What to Avoid

| Problem | Why It Fails | Mitigation |
|---------|-------------|------------|
| Direct sunlight | Hard shadows move between frames (sun angle vs. your position), confusing the optimizer | Shoot on overcast days or in open shade |
| Specular highlights | Highlights shift with viewpoint; the pipeline assumes diffuse appearance | Cover or reposition reflective items; use a polarizing filter |
| Flickering fluorescent lights | Frame-to-frame brightness variation | Replace with LED panels or increase shutter speed to a multiple of the flicker frequency (1/100s for 50Hz, 1/120s for 60Hz) |
| Mixed color temperature | Warm tungsten + cool daylight creates inconsistent white balance across the scene | Use one light type; gel mismatched sources to match |

### Practical Tip

Before recording, stand in the center of the scene and slowly rotate 360 degrees while watching your camera's exposure meter. If the meter swings more than 1.5 stops across the rotation, the lighting is too uneven. Either add fill light to the dark areas or flag (block) the bright sources.

---

## 3. Scenes That Work Well

The pipeline excels when COLMAP can find abundant, stable feature matches. These scene characteristics produce the best results:

### Texture

- **Brick, stone, wood grain, patterned fabric, foliage** -- anything with fine, non-repeating detail.
- Textured surfaces generate thousands of feature points per frame. More features = more reliable camera pose estimation = better splat.

### Materials

- **Matte and semi-matte surfaces.** Paint, plaster, unfinished wood, concrete, carpet, upholstered furniture.
- These materials reflect light diffusely, meaning their appearance stays consistent across viewpoints.

### Scale

- **Medium-scale spaces: 3-20 meters across.** A living room, a gallery, a courtyard, a workshop.
- At this scale, a handheld or gimbal-mounted camera can achieve sufficient overlap and parallax with a 60-120 second capture.

### Static Scenes

- **Nothing in the scene should move.** No people walking through, no curtains blowing, no ceiling fans, no pets.
- Even small motions (a clock pendulum, a screen displaying video) create "floater" artifacts in the reconstruction.

### Example: Ideal Scene

A furnished living room on an overcast afternoon. Wooden floors, a patterned rug, a bookshelf full of books, a brick fireplace. All lights are off (relying on even window light). No people. The TV is off. The ceiling fan is stopped.

---

## 4. Scenes That Cause Failure

These characteristics will degrade or completely break the reconstruction. Knowing the failure modes lets you either avoid them or compensate.

### Large Featureless Surfaces

- **White walls, plain ceilings, solid-color floors, smooth countertops.**
- COLMAP cannot find features on a featureless surface. The camera pose in those regions becomes unreliable. The splat fills in with noise or "floaters."
- **Mitigation:** Temporarily place textured objects (books, plants, patterned cloth) on blank surfaces during capture. Remove them from the final scene in post if needed.

### Highly Reflective Surfaces

- **Chrome fixtures, mirrors, polished metal, glass tabletops, wet floors — and TV/monitor screens.**
- Reflections change with viewpoint. The pipeline treats each reflection as a different surface, creating ghost geometry behind the reflective surface.
- **A TV/screen is the worst case:** a large, glossy, view-dependent reflector that dominates a room. Its reflections defeat both SfM (inconsistent features) and 3DGS (the SH overfits the moving reflection into floaters/haze). Combined with motion blur this is **unrecoverable** — a dataset whose hero region is a reflective TV should be abandoned and re-captured, not post-processed. (2026-06-21: the Drive room dataset was abandoned for exactly this — TV reflections + MUSIQ-19 blur.)
- **Mitigation:** Turn screens OFF (a powered-off TV is far less glossy) or cover them; cover mirrors with matte fabric; use dulling spray on small chrome objects; dry wet floors. Accept that glass and mirror regions will be low quality.

### Transparent Objects

- **Windows, glass bottles, clear vases, aquariums.**
- Light passes through and the pipeline sees the background, creating impossible depth ambiguity.
- **Mitigation:** Minimal. Tape matte paper behind glass objects if possible. Otherwise accept degraded quality in those regions.

### Moving Elements

- **People, animals, vehicles, swaying plants, flowing water, active screens.**
- Any motion between frames creates inconsistent observations of the same 3D point.
- **Mitigation:** Wait for the scene to be completely still. Pause recording if someone walks through.

### Extreme Lighting Variation

- **Bright windows + dark interior, spotlight + shadow, mixed indoor/outdoor.**
- No single exposure setting can handle both extremes. Auto-exposure will oscillate, and fixed exposure will clip one end.
- **Mitigation:** Close blinds, add fill light, or capture the bright and dark regions as separate sessions and merge later.

---

## 5. Camera Settings

Lock everything. The pipeline assumes a consistent camera model across all frames. Any automatic adjustment between frames introduces inconsistency.

### Resolution

| Setting | Recommendation |
|---------|---------------|
| Minimum | 1920x1080 (1080p) |
| Recommended | 3840x2160 (4K) |
| Maximum useful | 4K is sufficient; 8K adds storage cost without proportional quality gain |

Higher resolution means more features per frame and finer detail in the final splat. But resolution beyond 4K hits diminishing returns because the training step downsamples anyway.

### Frame Rate

- **Use 30 fps. Not 60 fps.**
- More frames does not help. At 0.5 m/s movement speed, 30 fps already produces frames every ~1.7 cm of camera translation. That is more than enough overlap.
- 60 fps doubles storage and COLMAP processing time for near-zero quality gain.
- If your camera only does 24 fps, that is fine too.

### Focus

- **Manual / fixed focus. Turn off autofocus.**
- Autofocus hunts during movement, causing some frames to be soft. Soft frames fail feature matching.
- Set focus to the middle distance of the scene (roughly 3-5 meters for a room) and leave it.
- Use a deep depth of field (small aperture, f/5.6-f/11) to keep near and far objects acceptably sharp.

### Exposure

- **Manual / fixed exposure. Turn off auto-exposure.**
- Auto-exposure changes brightness between frames. COLMAP interprets brightness changes as surface appearance changes, which degrades matching.
- Set exposure for the average brightness of the scene and accept minor under/over exposure in some areas.
- On phones: use a pro/manual camera app (e.g., Filmic Pro, ProCamera, Halide) that locks exposure.

### White Balance

- **Manual / fixed. Turn off auto white balance.**
- Auto WB shifts color temperature between frames, which (like exposure changes) confuses feature matching.
- Set to a preset (Daylight, Cloudy, Tungsten) that matches your dominant light source.

### Lens / Focal Length

| Lens Type | Acceptable? | Notes |
|-----------|-------------|-------|
| 24-50mm equivalent | Best | Standard field of view, minimal distortion |
| 18-24mm (moderate wide) | Good | More coverage per frame, slight barrel distortion (COLMAP handles this) |
| Fisheye / ultra-wide (<16mm) | Poor | Extreme distortion at edges; feature matching fails in periphery |
| Telephoto (>70mm) | Poor | Narrow FOV means you need many more frames for coverage; parallax is reduced |

### Phone-Specific Notes

Modern flagship phones (iPhone 15 Pro, Samsung S24 Ultra, Pixel 8 Pro) produce usable video if you:
1. Use the main (1x) camera, not ultra-wide or telephoto.
2. Lock focus, exposure, and white balance (requires a manual camera app).
3. Shoot in good light (phones have small sensors; low light = noise = feature matching failure).
4. Record in the highest quality mode (4K, HEVC/H.265 at high bitrate).

---

## 6. Capture Patterns

Systematic capture patterns ensure complete coverage. Do not improvise -- follow a pattern.

### Room Scan Pattern

For a rectangular room (3-8m per side):

```
Pass 1 - Low (waist height, ~1m):
  Walk the full perimeter, camera facing center.
  Duration: ~30 seconds.

Pass 2 - Eye level (~1.6m):
  Walk the perimeter again, same direction.
  Duration: ~30 seconds.

Pass 3 - High (arms raised, ~2.2m):
  Walk the perimeter again.
  Duration: ~30 seconds.

Pass 4 - Center cross:
  Walk diagonally corner-to-corner, then the other diagonal.
  Duration: ~20 seconds.

Total: ~110 seconds (about 2 minutes).
```

This gives you 3 elevation bands of the walls plus cross-coverage of the floor and ceiling. Every surface is seen from multiple heights and angles.

### Multi-Capture / Combining Sweeps

You do not need a single perfect sweep. Several independent handheld sweeps of the **same room** -- different walking approaches, at different heights -- combine into a denser, more complete reconstruction than any one sweep alone.

- **Combine multiple videos of the same scene.** Feed all sweeps into COLMAP together. They share enough overlapping surface that COLMAP registers them into one model, and the union of viewpoints fills gaps that any individual sweep misses.
- **Observed result:** a 3-sweep combined capture of a room produced ~146k points at ~95% registration, measurably better than a single perimeter sweep of the same room (~90k points). More independent approaches at varied heights = more coverage.
- **Infill minimally.** Use the extra sweeps to cover what the first one missed (a corner, a high shelf, an occluded face), not to re-shoot identical paths. Redundant near-identical passes add processing time without adding coverage.

> **The best video for the SCENE is not the best for an OBJECT.** A wide room sweep gives great environment coverage but rarely gives a clean turnaround of any single item. Objects you want as individual hulls need a **dedicated close orbit** (a full 360-degree pass tight around that object) in addition to the room sweeps -- see the Object Capture Pattern below.

### Object Capture Pattern

For an individual object (sculpture, piece of furniture, artifact):

```
Orbit 1 - Eye level:
  Full 360-degree orbit at ~1.5m distance.
  Duration: ~20 seconds.

Orbit 2 - Low angle (knee height):
  Full 360-degree orbit, camera angled slightly upward.
  Duration: ~20 seconds.

Orbit 3 - High angle (above head):
  Full 360-degree orbit, camera angled downward.
  Duration: ~20 seconds.

Total: ~60 seconds per object.
```

### Detail Pass

After the room scan and object orbits, do a slow close-up sweep of important features:

- Move camera 30-50 cm from the surface.
- Sweep slowly across the feature (text, carving, texture).
- Duration: 10-15 seconds per detail area.

### Outdoor / Large Space Pattern

For spaces larger than ~10m:

- Divide into overlapping zones (~5m radius each).
- Capture each zone using the room scan pattern.
- Walk connecting paths between zones (these transitional frames help COLMAP stitch zones together).
- Overlap between zones: at least 2m of shared visible area.

### Duration Guidelines

| Subject | Recommended Duration |
|---------|---------------------|
| Single room (3-6m) | 60-120 seconds |
| Large room (6-15m) | 120-180 seconds |
| Key object | 30-60 seconds |
| Detail feature | 10-15 seconds |
| Outdoor area (20m radius) | 3-5 minutes |

---

## 7. Post-Processing Before Pipeline

How you handle the video file between camera and pipeline matters. Lossy re-encoding destroys the features that COLMAP needs.

### File Transfer

- **Copy the original camera file directly.** MOV from iPhone, MP4 from Android/GoPro, MXF from cinema cameras.
- Use USB cable, AirDrop, or direct SD card transfer. Do not upload to Google Photos, iCloud, or any cloud service that transcodes on upload.

### If Re-Encoding Is Required

Sometimes you need to convert format (e.g., HEVC to H.264 for compatibility). Use these settings:

```bash
# FFmpeg command for minimal-loss re-encoding
ffmpeg -i input.mov \
  -c:v libx264 \
  -crf 18 \
  -preset slow \
  -pix_fmt yuv420p \
  -an \
  output.mp4
```

| Parameter | Value | Why |
|-----------|-------|-----|
| Codec | H.264 (libx264) | Universal compatibility |
| CRF | 18 | Visually lossless; lower = bigger file, 18 is the sweet spot |
| Preset | slow | Better compression efficiency (smaller file at same quality) |
| Resolution | Do not change | Never downscale before the pipeline |
| Audio | Strip (-an) | Not needed; saves space |

### Frame Extraction

The pipeline typically extracts frames from video. If you need to do it manually:

```bash
# Extract every 5th frame (6 fps from 30 fps source)
ffmpeg -i input.mp4 -vf "select=not(mod(n\,5))" -vsync vfp -q:v 2 frames/frame_%05d.jpg

# Or extract at a fixed interval (2 frames per second)
ffmpeg -i input.mp4 -vf fps=2 -q:v 2 frames/frame_%05d.jpg
```

For a typical 90-second room capture at 30 fps, extracting every 5th frame gives ~540 images. That is a good working set for COLMAP.

### Automated Frame-Quality Gate (SOTA, GPU)

Motion blur is the single most common defect in handheld video, so the pipeline QA-gates
extracted frames *algorithmically* before they reach COLMAP (`src/pipeline/frame_quality.py`):

- **`NeuralIQA`** — a SOTA **no-reference image-quality** score (MUSIQ via `pyiqa`, on GPU; falls
  back to classical metrics if unavailable). MUSIQ is perceptual and content-aware, so it catches
  blur + noise + exposure jointly — far more reliable than raw Laplacian variance. On the koniq
  scale (~0–100, higher is better) a *good* photo scores **50–75**; anything in the teens is
  unusably soft.
- **`assess_video()` → `VideoQualityVerdict`** applies a **drop-and-flag policy**: a video that
  cannot supply `min_good_frames` KEEP-grade frames is marked **`too_low_quality`** and skipped so
  the orchestrator moves to the next video rather than feeding soft footage into SfM/3DGS. Accepted
  videos return a **windowed best-of** selection — the sharpest frame within each temporal window,
  which both maximises quality and preserves coverage (the advantage of video over stills).

> **The gate cannot manufacture sharpness that was never recorded.** If every video for a scene
> gates as `too_low_quality`, that is the signal to **re-capture**, not to lower the bar. Selection
> only chooses among frames that exist. (Validated 2026-06-21: the Drive footage gated
> `too_low_quality` at median MUSIQ ~19; no training recipe recovered it.)

---

## 8. What NOT to Do

Each of these has been observed to waste hours of pipeline time or produce unusable results.

### Do NOT Download YouTube Videos as Source

YouTube re-encodes all uploads to VP9 or AV1 at variable bitrate. Fine detail (exactly the texture COLMAP needs) is the first casualty of lossy compression. A 4K YouTube download has less useful detail than a 1080p original camera file.

### Do NOT Use Phone Video in Low Light

Phone sensors are small (~1/1.3" at best). In low light, the camera compensates with:
- High ISO (introduces luminance noise that COLMAP matches as false features)
- Slow shutter (introduces motion blur)
- Computational HDR stacking (creates ghosting between stacked frames)

All three are destructive. If indoor light is dim, add light. Two $30 LED panels are a better investment than hours of failed reconstructions.

### Do NOT Pan Too Fast

Panning (rotating the camera on its axis without moving) is already less useful than translation. Fast panning guarantees motion blur on every frame. If you must pan, do it slowly (under 15 degrees per second) and only to reorient between movement segments.

### Do NOT Include Moving People in the Scene

Even a person standing "still" shifts weight, breathes, and sways. This creates a smeared ghost in the reconstruction. Clear the scene of all people and animals before recording.

### Do NOT Use Auto-Exposure

This is the most common beginner mistake. Walking from a bright window toward a dark wall causes auto-exposure to ramp up. Frames near the window are dark; frames near the wall are bright. COLMAP sees the same surface at two different brightness levels and either fails to match or creates a seam.

Lock exposure. Accept that some areas will be slightly bright or dark. A slightly over-exposed wall reconstructs perfectly. An auto-exposed wall with brightness ramps reconstructs with artifacts.

### Do NOT Use Social Media as a Transfer Mechanism

Sending video through iMessage, WhatsApp, Telegram, or any messaging app re-encodes it, typically to 720p or lower at high compression. The same applies to uploading to Instagram, TikTok, or Facebook and re-downloading.

---

## 9. Quick Reference Checklist

Print this and check it off before every capture session.

```
PRE-CAPTURE
[ ] Scene is static (no people, pets, fans, flowing water)
[ ] Lighting is even and consistent (no harsh shadows)
[ ] Reflective surfaces covered or repositioned
[ ] Featureless surfaces have temporary texture added
[ ] Camera battery charged, storage space available

CAMERA SETTINGS
[ ] Resolution: 4K (or minimum 1080p)
[ ] Frame rate: 30 fps
[ ] Focus: MANUAL, set to mid-distance
[ ] Exposure: MANUAL, set for average scene brightness
[ ] White balance: MANUAL, matched to light source
[ ] Lens: 24-50mm equivalent (main camera on phone)

CAPTURE
[ ] Movement speed: 0.5 m/s or slower
[ ] Using gimbal or stabilized mount
[ ] Perimeter passes at 3 heights (low / eye / high)
[ ] Center cross passes
[ ] 360-degree orbit of each key object at 3 heights
[ ] Detail pass of important features
[ ] Total duration: 60-120s per room, 30-60s per object

POST-CAPTURE
[ ] Transfer original file (USB/AirDrop, not cloud)
[ ] No re-encoding unless necessary
[ ] If re-encoding: H.264, CRF 18, original resolution
[ ] File stored in pipeline input directory
```

---

## Appendix: Troubleshooting Common Capture Issues

### COLMAP Fails to Register Most Images

**Symptom:** COLMAP reports only 30% of images registered.
**Likely cause:** Insufficient overlap. You moved too fast or did not revisit areas.
**Fix:** Re-capture with slower movement, more overlap, and the systematic patterns above.

If capture overlap is good but registration is still low, the cause is usually invocation, not the footage. With **COLMAP 4.1.0** the option namespace changed -- old recipes silently use the wrong flags:

- **Use the new namespaces:** `--FeatureExtraction.*` and `--FeatureMatching.*` (the old `--SiftExtraction.use_gpu` is gone).
- **Default to GPU SIFT, not CPU.** Set `--FeatureExtraction.type SIFT` and run it on the GPU. GPU SIFT gave ~100% registration on the multi-sweep captures; CPU is slower and is treated as a defect path to replace, not a default.
- **The ALIKED enum is invalid in this build.** `ALIKED` is rejected, and `ALIKED_LIGHTGLUE` needs `libcudnn.so.9`, which is missing -- so it errors out. Fall back to GPU SIFT (which is what gives the ~100% registration above).
- **Mixed cameras:** pass `--ImageReader.single_camera_per_folder` so COLMAP does not force one shared intrinsic model across sweeps shot on different devices.
- **`mkdir` the COLMAP working directory before `feature_extractor`.** The `database_parent_path` check fails (no database created) if the output directory does not already exist.

### Floater Artifacts in the Splat

**Symptom:** Semi-transparent blobs floating in mid-air in the rendered splat.
**Likely cause:** Moving objects in the scene, or reflective/transparent surfaces.
**Fix:** Remove all moving elements. Cover reflective surfaces. Re-capture.

### Blurry or Soft Reconstruction

**Symptom:** The splat looks like it is rendered through frosted glass.
**Likely cause:** Motion blur from fast movement or slow shutter speed. Alternatively, autofocus hunting.
**Fix:** Use a gimbal. Move slower. Lock focus manually. Increase shutter speed (1/200s or faster).

### Color Banding or Inconsistent Colors

**Symptom:** Visible color shifts or bands where different capture segments meet.
**Likely cause:** Auto white balance or auto-exposure was enabled.
**Fix:** Lock white balance and exposure. Re-capture.

### Reconstruction Has Holes

**Symptom:** Parts of the scene are missing entirely in the splat.
**Likely cause:** Those areas were only visible from 1-2 viewpoints (insufficient coverage).
**Fix:** Review your capture path. Ensure every surface is visible from 5+ viewpoints. Add more passes at different heights.

---

## Motion blur is the dominant defect (empirical, 2026-06-23)

On the `dreamlab` 4K/30fps capture, `recon_quality_metrics.py` measured **0% under-observed area**
(median ~90 cameras per surface point) yet a holey, noisy reconstruction — i.e. the problem is
**dense-but-motion-blurred**, not insufficient coverage. Two consequences:

1. **Score sharpness at full/high resolution.** ffmpeg `blurdetect` at 960p reads "uniformly
   blurry" (range ~1.6×) — a downscale artifact. Full-4K **variance-of-Laplacian** shows a **~105×
   sharpness range**: sharp frames *are* interleaved with blurred ones. Always measure blur at full
   res (the lowpass of a downscale erases the motion-blur signal).
2. **Blur-aware selection raises the sharpness FLOOR, not the median.** `blur_aware_fifo_sampler.py`
   oversamples and keeps the sharpest frame per overlapping FIFO window. On dreamlab the median
   sharpness rose only +7-13%, but the **bottom-quartile rose +20-38%** — it reliably drops the
   *blurriest* frames, which are the ones that poison COLMAP matches and inject blur into the splat.
   This is cheaper than recapture and preserves frame integrity (see below), but it cannot create
   detail the sensor never recorded — a sharper capture still beats selecting from a blurry one.

### Device settings — Pixel 9 Pro (and similar)

Motion blur ∝ exposure time × motion. Optimise exposure, then framerate, then resolution:

| Choice | Verdict | Why |
|---|---|---|
| **4K / 60 fps** | ✅ best video mode | 60fps caps exposure ≤1/60s (vs 1/30s) → ~half the blur; 2× candidate frames for the sampler |
| 4K / 30 fps | ❌ | longer exposure, fewer candidates |
| **8K / 30 fps** | ❌ | 30fps → long exposure → blurrier; extra pixels wasted on blurred frames. **Sharp 4K beats blurry 8K** |
| **RAW photo burst** | ✅✅ best quality | stills = very short exposure, full-res, no inter-frame compression — the ideal SfM input |

The real lever is **short exposure**: shoot in bright/even light (lets auto-exposure pick a fast
shutter), or lock **shutter ≥ 1/500s** + lock AE/AF in a pro app (mcpro24fps / FiLMiC). Move slowly
and smoothly with brief **micro-pauses** at key viewpoints — the sampler harvests those sharp frames.

### Frame integrity contract

Frames feeding reconstruction must be the **original pixels, lossless and traceable**. The sampler
scores via a throwaway in-memory proxy (never alters a canonical frame), extracts selected frames
once at full-res lossless PNG, and writes `manifest.json` with per-frame source-index + Laplacian
score + **sha256** + the source-video hash. `--verify <dir>` re-checksums after any container↔host
copy. The same canonical set feeds SfM→3DGS→mesh→metrics — no silent re-extraction — so the
image↔camera correspondence stays consistent. Remove a capture's working frames once its ingest is
fully consumed.
