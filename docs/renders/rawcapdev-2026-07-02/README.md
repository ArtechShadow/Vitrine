# rawcapdev — first LichtFeld-native E2E (2026-07-02)

Keeper renders from the first end-to-end run on real raw capture (`rawsForDev/`, 55
Pixel DNG stills of a gallery still-life: a brass/patina vessel with a Heinz ketchup
bottle inverted on top). Driven via `docker exec` into `gaussian-toolkit` (LichtFeld
baked into the mega-image). Full source artifacts live under `output/` (gitignored).

Pipeline: decode 55/55 (rawpy) → select 50 sharpest → COLMAP **50/50 (100%)
registration, 10.4k pts** → LichtFeld `igs+` 30k iters, GPU-bound at 99% util
(~15 min, avg 32.8 it/s) → 4,000,000-gaussian splat (`splat_30000.ply`, 992 MB).

## Images

| File | What it shows |
|---|---|
| `01_wb_before_default.jpg` | Source DNG decoded with libraw's default (daylight) WB — heavy warm/orange cast. |
| `02_wb_after_camera.jpg` | Same frame decoded with `use_camera_wb=True` — neutral gallery walls. The decode fix. |
| `03_splat_render_view00.jpg` | LichtFeld-native splat, gsplat render from a COLMAP camera pose (front). |
| `03_splat_render_view18.jpg` | Splat render, oblique — window blinds, skirting, carpet, hero vessel. |
| `03_splat_render_view36.jpg` | Splat render, top-down over the vessel. |
| `04_splat_depth_view18.jpg` | Depth preview for view 18. |

## Notes / known quality

- Splat renders here are from the splat trained on the **pre-WB (warm)** frames, so
  they carry the orange cast + 3DGS floater haze — capture-limited (handheld), and a
  neutral-WB retrain is the follow-up.
- Four Vitrine defects were fixed landing this run (see the accompanying commits):
  SplatReady config-name collision, missing `--max_image_size` on undistortion (the
  GPU-starvation "hang"), `cameras.bin` uint64 parse (SIGFPE in preview render), and
  the DNG white-balance flag above.
