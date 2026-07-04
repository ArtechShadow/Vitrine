# Vitrine — Logo Exploration (2026-07-02)

An eight-concept identity study for **Vitrine**, the capture-adaptive pipeline that
turns ordinary video/photos of a real space into a structured, textured, game-ready
3D scene (Gaussian splatting → meshes) for Unreal Engine 5.8 / Blender. *Vitrine* is
French for a **glass display case / showcase** — so the identity sits at the meeting
point of **technical precision** and **refined, archival elegance**: a museum vitrine
for reconstructed worlds.

- **Sheet:** [`vitrine-logo-sheet-2026-07-02.png`](vitrine-logo-sheet-2026-07-02.png) — 3888×3200, single designed exploration board.
- **Marks:** [`marks/`](marks/) — the eight individual logo lockups (1536px PNG each).
- **How it was made:** marks generated with Google **Gemini 3 Pro Image ("Nano Banana Pro", `gemini-3-pro-image`)** via `report/poster/nano_banana.py`; the board (frames, typography, palettes, micro-packs) composed as SVG (librsvg) + ImageMagick. See [`docs/nano-banana-usage.md`](../../nano-banana-usage.md).

![Vitrine logo sheet](vitrine-logo-sheet-2026-07-02.png)

---

## Why these directions

Vitrine has two things to say at once, and every concept below picks a stance on the
balance between them:

1. **The engine** — it is a real-time 3D reconstruction system. Gaussian splats, point
   clouds, camera capture, lenses, scanning, mesh facets, refraction of light through
   glass. The motifs are literally the technology.
2. **The frame** — it is a *showcase*. A vitrine, a plinth, a gallery, museum framing,
   archival restraint. The product's job is to present a reconstructed object or room
   *beautifully and credibly*, not just to compute it.

The set deliberately spans that axis — from the most literal "process" mark
(**Scanline**) to the most abstract "gallery" mark (**Plinth** / **Bracket**), with the
capture-technology marks (**Prism**, **Aperture**, **Facet**) in between, plus a premium
dark variant (**Vitrine Glow**) and a type-only lockup (**Refraction**). Palettes are
kept in a coherent world — warm museum paper and ink as the shared ground, with a single
distinguishing accent per concept (spectrum, brass, cyan, emerald, amber, ember,
champagne, chromatic) — so the eight read as one family, not eight unrelated logos.

Recurring system elements: a **warm off-white / ivory paper** ground (#F4F1EA family),
**deep ink** for structure, the **Gaussian point-cloud** as the signature texture, and
**glass / refraction** as the connective metaphor. Wordmark shown throughout as
`VITRINE` in generous tracking.

**Designer's picks:** **01 Prism** (most on-concept, most flexible) and **08 Refraction**
(hero-tier type lockup) are the strongest primary candidates; **06 Bracket** is the best
"small / favicon / app-icon" reduction; **07 Vitrine Glow** is the natural dark-mode and
signage variant.

---

## Concepts

### 01 · Prism — `marks/vitrine-01-prism.png`
> *Capture, refracted into reconstruction.*

- **Palette:** `#F4F1EA` paper · `#1A1A1A` ink · `#7C4DFF` violet · `#22C1D6` cyan · `#E8A33D` amber
- **Type:** Geometric grotesque, wide tracking, uppercase
- **Motif:** Isometric glass display cube (vitrine) × a light ray refracting into a Gaussian splat cloud
- **Rationale:** The vitrine treated as a literal prism. A single captured ray enters the
  glass case and disperses out the far face into a spectral point-cloud — capture →
  refraction → reconstruction, in one gesture. The most *on-concept* mark and the most
  adaptable (works in mono ink, drops the spectrum for a 1-colour lockup).

### 02 · Plinth — `marks/vitrine-02-plinth.png`
> *The showcase, monogrammed.*

- **Palette:** `#F2ECE0` ivory · `#14110D` ink · `#B08D4B` brass · `#D8C9A8` sand
- **Type:** High-contrast serif, uppercase
- **Motif:** Capital **V** formed by the converging front edges of a glass museum plinth, with a soft mirror reflection
- **Rationale:** The archival, gallery-first end of the range. The letterform *is* the
  pedestal a reconstructed object stands on. Brass + ivory + a high-contrast serif read as
  museum-grade and quietly luxurious — for stationery, credits, and print.

### 03 · Aperture — `marks/vitrine-03-aperture.png`
> *Focus is reconstruction.*

- **Palette:** `#FAFAFC` white · `#101322` ink · `#2A2E6E` indigo · `#6E8BE0` periwinkle · `#22C1D6` cyan
- **Type:** Modern grotesque, geometric
- **Motif:** A camera-lens iris built entirely from Gaussian splat dots, scattered noise resolving inward to a sharp focal point
- **Rationale:** The capture-adaptive thesis as an icon: rings of points sharpen from
  outer noise into a bright, focused centre — the pipeline *finding structure in messy
  data*. Reads as lens, eye, and point-cloud simultaneously; the most "software product"
  of the set.

### 04 · Facet — `marks/vitrine-04-facet.png`
> *Reconstructed, facet by facet.*

- **Palette:** `#EEF1F0` mist · `#10201C` ink · `#0E7C66` emerald · `#3FB8A2` teal
- **Type:** Geometric sans, precise
- **Motif:** A low-poly, cut-glass gemstone shaped as a **V**, built from triangulated mesh facets
- **Rationale:** The *mesh* half of Vitrine (2DGS / PGSR / TSDF → FBX) rendered as a jewel.
  Triangulated surfaces = polygonal reconstruction; the gem = the "showcase-worthy" output.
  Polished, game-ready, exact — and the only cool-green direction, for differentiation.

### 05 · Scanline — `marks/vitrine-05-scanline.png`
> *Watch the scene build.*

- **Palette:** `#ECEAE6` warm grey · `#202225` charcoal · `#E8A33D` amber
- **Type:** Mono-inflected technical sans
- **Motif:** A glass display case crossed by a bright scan line, its lower half filling with rising voxels / points
- **Rationale:** The most literal "process" mark — a vitrine caught *mid-capture*, the scan
  sweep reconstructing an object from the floor up. Amber-on-charcoal gives it an
  instrument / engineering feel. Great for loading states, motion, and the technical brand.

### 06 · Bracket — `marks/vitrine-06-bracket.png`
> *Frame it. Showcase it.*

- **Palette:** `#F3EFE7` ivory · `#1B1B1B` ink · `#C24A2E` ember
- **Type:** Light grotesque, wide tracking
- **Motif:** Four viewfinder / registration corner brackets framing a small Gaussian splat cluster with one ember focal point
- **Rationale:** Capture-framing (a camera reticle) and museum-framing (registration marks)
  collapsed into one minimal, editorial glyph. The most reducible mark in the set — it
  survives to favicon / app-icon size and carries a single confident accent.

### 07 · Vitrine Glow — `marks/vitrine-07-glow.png`
> *The case, lit from within.*

- **Palette:** `#17181C` charcoal · `#D8B87A` champagne · `#7FD9E8` cyan glow · `#F3EFE7` warm white
- **Type:** Light sans, luminous (dark variant)
- **Motif:** A slender glass display column holding a floating, glowing reconstructed object
- **Rationale:** The premium dark-mode / signage variant: a tall vitrine with volumetric
  light and a luminous point-object inside. Champagne + cyan on charcoal reads as
  spectacle without shouting — for the app's dark UI, title cards, and exhibition screens.

### 08 · Refraction — `marks/vitrine-08-wordmark.png`
> *Seen through glass.*

- **Palette:** `#F5F2EC` paper · `#191919` ink · `#E85CC8` magenta fringe · `#4DC7E8` cyan fringe
- **Type:** High-contrast display serif
- **Motif:** A type-only `VITRINE` lockup split by a diagonal glass refraction shard, with a whisper of chromatic aberration; tagline **CAPTURE. RECONSTRUCT. SHOWCASE.**
- **Rationale:** The name itself, viewed *through* the vitrine's glass. A single refraction
  shard fractures the wordmark and disperses a hint of prism light at the break — elegant,
  hero-tier, and works with no symbol at all. Strong as the primary wordmark alongside any
  of the marks above.

---

## Files

| File | Size | Notes |
|---|---|---|
| `vitrine-logo-sheet-2026-07-02.png` | 3888×3200 | The composed exploration board (primary deliverable) |
| `marks/vitrine-01-prism.png` … `-08-wordmark.png` | 1536×1536 | Individual lockups, native background per concept |

*Marks generated with `gemini-3-pro-image` (Nano Banana Pro). Concept **03 Aperture** was
regenerated once after a first-pass critique (v1 read as a decorative mandala; v2 resolves
clearly as a capture-lens). Board typography set in DejaVu (Serif / Sans / Mono).*
