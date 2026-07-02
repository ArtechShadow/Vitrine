# Capture Protocol & Onboarding

**How to shoot for reconstruction (DSLR / mirrorless / phone RAW), and how to log in and run the Dockerised Vitrine system.**

> **Capture quality is the #1 lever.** Garbage in, garbage splat. The reconstruction can only be as
> sharp as the frames you feed it: COLMAP needs sharp, overlapping, consistently-exposed images, and
> 3DGS bakes whatever it sees. No training recipe recovers motion-blurred or reflection-dominated
> footage. The pipeline's blur-gated, sharpest-per-window selection (MUSIQ + full-res Laplacian)
> protects the run, but it can only choose among frames that exist. The Drive room dataset (median
> MUSIQ ≈ 19, TV reflections) was unrecoverable and had to be re-captured.

For the full "why each rule exists" reference (movement, failure modes, troubleshooting), see
[`capture-methodology.md`](capture-methodology.md). This page is the practical field guide.

---

## 1. RAW capture on a DSLR / mirrorless

Lock everything. The pipeline assumes one consistent camera model across every frame; any automatic
adjustment between frames injects inconsistency. **Prefer RAW stills** (a systematic burst / orbit)
over video — stills give the shortest exposure, full resolution, and no inter-frame compression, the
ideal SfM input. If you must shoot video, use 4K and the shortest shutter the light allows.

| Setting | Lock to | Why |
|---|---|---|
| Format | RAW (DNG / CR3 / NEF / ARW), stills preferred | Full sensor data, no compression; decode applies camera white balance |
| Exposure mode | Full manual (M), locked | Auto-exposure re-brightens between frames; COLMAP reads a ramp as a surface change |
| Shutter | ≥ 1/250 s (≥ 1/500 s while moving) | Freezes motion — motion blur is the single most common defect |
| ISO | Lowest the light allows (100–800) | High-ISO luminance noise is matched as false features |
| Aperture | f/5.6–f/11 | Deep depth of field keeps near and far acceptably sharp |
| White balance | Fixed preset (Daylight / Cloudy); never AWB | AWB shifts colour between frames, confusing matching and seaming colour |
| Focus | Manual, fixed at mid-scene (3–5 m) | Autofocus hunts during movement; soft frames fail matching |
| Lens | 24–50 mm equiv. prime, fixed | Standard FOV, low distortion. Avoid fisheye (<16 mm) and tele (>70 mm) |
| Overlap | 70–80% frame-to-frame; each point in 5+ views | Triangulation needs baseline plus redundancy |
| Path | Slow orbit + three height passes (low / eye / high) | Every surface seen from multiple heights and angles |

**Coverage / frame-count targets.** Move slowly and smoothly (about 0.5 m/s if handheld or on a
gimbal); pause briefly at each viewpoint so the sharpest-frame selector has a crisp frame to keep.

| Subject | RAW frames | Pattern |
|---|---|---|
| Single room (3–6 m) | 200–500 | Three perimeter passes (waist / eye / raised) + one corner-to-corner cross |
| Large room (6–15 m) | 400–800 | Same, split into overlapping ≈5 m zones with 2 m shared overlap |
| Key object | 60–120 | Full 360° orbit at three heights (eye, low looking up, high looking down) |
| Detail feature | 20–40 | Slow close sweep at 30–50 cm across the surface |

**Lighting.** Even, diffuse light: overcast outdoors; large soft panels or ceiling bounce indoors.
Keep brightness consistent across the whole capture. Test it: stand centre-scene and rotate 360°
watching the meter; if it swings more than 1.5 stops, add fill to the dark side or flag the bright
source. Avoid hard moving shadows (direct sun), specular highlights, fluorescent flicker (set shutter
to 1/100 s for 50 Hz, 1/120 s for 60 Hz), and mixed colour temperature.

| Do | Don't |
|---|---|
| Clear the scene: no people, pets, fans, curtains, flowing water | Leave anything moving in frame; even a "still" person sways and smears |
| Shoot matte, textured surfaces (brick, wood grain, fabric, plaster) | Rely on white walls / plain ceilings; add temporary texture (books, cloth) instead |
| Turn screens OFF; cover mirrors with matte fabric; dulling-spray chrome; dry wet floors | Leave a TV / monitor ON — worst case, typically **unrecoverable** |
| Tape matte paper behind glass / clear objects, or accept low quality there | Expect windows, glass, or aquariums to reconstruct; light passes through |
| Lock exposure, WB, focus; accept a slightly bright or dark patch | Use any "auto" mode, or walk from a bright window into a dark corridor |

> **⚠ Reflective / transparent / moving = capture failure.** A powered-on TV or monitor is a large,
> glossy, view-dependent reflector: its reflections defeat SfM (inconsistent features) and 3DGS (the
> spherical harmonics overfit the moving reflection into floaters). Combined with motion blur this is
> **unrecoverable** by post-processing. If a scene's hero region is a reflective screen, re-capture
> with it off or covered — don't try to salvage the data.

---

## 2. RAW capture on a mobile phone

A modern flagship shooting RAW stills is a genuinely good SfM source. **Validated example: 55 Pixel
DNG stills registered at 100% in COLMAP** (GPU SIFT). The rules are the DSLR rules, adapted to phone
quirks. Use the **main (1x)** camera only — not ultra-wide or tele — and shoot in good light: the
sensor is small, so low light forces noise, slow shutter, and HDR stacking.

| Device | Enable RAW / DNG | Lock AE / AF |
|---|---|---|
| Pixel | Camera settings → save RAW + JPEG (writes `.dng`) | Long-press subject to lock focus + exposure; nudge the exposure slider |
| iPhone | Settings → Camera → Formats → **Apple ProRAW**; tap `RAW` in the camera | Long-press until `AE/AF LOCK` shows |
| Pro apps (any) | Halide, Adobe Lightroom (DNG), Moment, ProCamera | Set manual shutter, ISO, WB, focus directly and lock each |

In a pro app, set shutter **≥ 1/250 s** (1/500 s while moving), ISO as low as the light allows, WB to
a fixed preset, and focus fixed at mid-scene. Brace with both hands against your body, or use a
gimbal or small tripod. **Never shoot single-hand handheld** — it puts motion blur on most frames.
Add a brief micro-pause at each viewpoint. Transfer the original files over USB or AirDrop, never
through iMessage / WhatsApp / cloud photos, which re-encode and destroy detail.

> **⚠ Phone-specific pitfalls**
> - **Auto-HDR / computational photography** stacks several exposures and can ghost moving detail.
>   RAW / ProRAW bypasses most of it; also turn off Night mode and HDR bracketing.
> - **Rolling shutter**: the CMOS sensor reads line-by-line, so fast pans skew geometry. Move slowly
>   and pause rather than sweeping.
> - **Motion blur**: in dim light the phone drops shutter automatically. Add light or raise ISO
>   modestly, and never let shutter fall below 1/125 s.

---

## 3. Objects vs. rooms

> **The best capture for a ROOM is not the best for an OBJECT.** A wide room sweep gives great
> environment coverage but rarely a clean turnaround of any single item. Objects you want as
> individual meshes need a *dedicated close orbit* in addition to the room sweeps.

- **Objects (turntable / orbit).** Full 360° passes tight around the item (roughly 1–1.5 m out) at
  three heights: eye level, low looking up, high looking down. Turntable the item if it is small
  enough and keep the camera fixed. This close orbit feeds the SAM crop and the TRELLIS.2 hull step,
  so completeness of the turnaround matters more than raw frame count.
- **Rooms (overlapping perimeter + height passes).** Walk the full perimeter facing centre at waist,
  eye, and raised heights, then cross corner-to-corner both diagonals for the floor and ceiling. You
  do not need one perfect sweep — feed several independent handheld sweeps of the *same* room together
  and their union fills the gaps. A three-sweep combined capture produced ≈146k points at ≈95%
  registration, versus ≈90k for a single perimeter sweep. Infill minimally; avoid re-shooting
  identical paths.

---

## 4. Login, onboarding & system use

The system is a single hardened Docker image that is **loopback-only by design** (ADR-022): the web
services never listen on the LAN. You reach them by forwarding their ports over SSH.

### Log in (SSH tunnel)

1. Open a tunnel to the web UI port:
   ```bash
   ssh -N -L 7860:localhost:7860 <user>@<rig>
   ```
   Add more `-L` forwards as needed: `-L 8088:localhost:8088` (onboarding wizard),
   `-L 7681:localhost:7681` (web terminal).
2. In your browser open `http://localhost:7860`.
3. **First run only:** open the web terminal (`:7681`) and complete the authenticated Claude login
   *inside the container*. The session persists in the `claude-session` volume; a run with no
   logged-in session fails fast with a clear message.

### Web UI tour (`:7860`)

- **Ingest** — drag-and-drop RAW / images, or paste a Google-Drive URL. Ingest prefers raw images
  over video, and raw images are preferred over video whenever both are present.
- **Run browser** — a per-run file browser with inline image, mesh, and splat previews.
- **Download** — a streamed per-run `.zip` of the outputs.
- **3D viewers** — a Gaussian-splat viewer, and a per-object `<model-viewer>` at `/mesh-view/<id>`.

### Onboarding wizard (`:8088`, Rust / Axum)

The wizard builds one `exhibit.toml` manifest that the orchestrator consumes. It is re-entrant:
restarting reloads the existing manifest and resumes where you left off.

1. **Exhibit** — id, display name, venue, date, curator, description.
2. **Objects of interest** — per object: id, name, free-text SAM3 concept (e.g. "large bronze
   reclining figure"), and priority (`key` or `standard`).
3. **Hardware & model selection** — probes GPU count / VRAM and recommends the best-fitting models
   (inpaint, hull, matcher, mesh). Accept or override any field.
4. **Secrets & login** — HuggingFace token and Google-Drive OAuth. Credentials are held server-side;
   the manifest stores only `env:` references, never a token in the browser, the TOML, or git.
5. **Provision & hand-off** — validate the manifest, verify services are ready, then hand off to the
   in-container Claude Code overseer, which plans the actual run.

### What runs, and where outputs land

On ingest the pipeline runs:

> decode (DNG / HEIC → PNG, camera WB) → frame QA & selection (MUSIQ + full-res Laplacian,
> sharpest-per-window) → COLMAP SfM → LichtFeld 3DGS (ImprovedGS+, "igs+") → SAM segment →
> TRELLIS.2 object mesh → texture bake → assemble.

Outputs are written per-run under `output/` (gitignored); browse, preview, and zip-download them in
the web UI, with optional Drive write-back to the source folder.

> **Loopback-only is intentional.** Keep it that way. The correct remote-access path is the SSH
> tunnel above, not opening a LAN port. The service binding is a security boundary (ADR-022), not a
> limitation to work around.

---

## 5. Good-capture checklist

Run this before every session:

- [ ] Scene fully static: no people, pets, fans, curtains, flowing water.
- [ ] Even, consistent light; meter swings under 1.5 stops on a 360° turn.
- [ ] Screens OFF / covered; mirrors and chrome covered; glass backed with matte paper.
- [ ] Blank walls given temporary texture; battery charged, storage free.
- [ ] Format RAW (stills preferred); exposure, WB, and focus all MANUAL and locked.
- [ ] Shutter ≥ 1/250 s (1/500 s moving); ISO 100–800; f/5.6–f/11; 24–50 mm.
- [ ] Move ≈ 0.5 m/s, two-handed / gimbal; micro-pause at each viewpoint.
- [ ] Room: three height passes + cross, 70–80% overlap, 5+ views per point.
- [ ] Objects: dedicated tight 360° orbit at three heights, per object.
- [ ] Transfer originals over USB / AirDrop; no cloud, no messaging apps, no re-encode.
