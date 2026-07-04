# Nano Banana (Google Gemini image API) — usage & current model IDs

Practical reference for generating images in this repo via
[`report/poster/nano_banana.py`](../report/poster/nano_banana.py) (a dependency-light
REST caller) or direct `curl`. **Validated live on 2026-07-02** against the
`generativelanguage.googleapis.com` v1beta endpoint.

> Auth: the key is in the environment as `GOOGLE_GEMINI_API_KEY`. The helper reads
> `GOOGLE_API_KEY` (or `~/.claude/.env`), so call it with
> `GOOGLE_API_KEY="$GOOGLE_GEMINI_API_KEY"`.

## Current models ("Nano Banana" family)

The API was recently updated: the Gemini-3 image models graduated from `-preview` to
**stable** aliases. Prefer the stable IDs.

| Helper `--model` | Model ID | Marketing name | Notes |
|---|---|---|---|
| `pro` *(default)* | **`gemini-3-pro-image`** | **Nano Banana Pro** | Flagship. Best text/hex/layout rendering, up to **4K**. Use for logos, sheets, posters, anything with legible text. |
| `pro-preview` | `gemini-3-pro-image-preview` | Nano Banana Pro (preview) | Same model, preview channel. |
| `flash` | `gemini-3.1-flash-image` | Nano Banana 2 | Faster / cheaper; supports `thinkingLevel`. |
| `flash-preview` | `gemini-3.1-flash-image-preview` | Nano Banana 2 (preview) | |
| `flash-lite` | `gemini-3.1-flash-lite-image` | — | Lightest / fastest. |
| `legacy` | `gemini-2.5-flash-image` | "Nano Banana 1" | Old model; avoid unless matching prior output. |

Also present (different API shape — `:predict`, not `:generateContent`):
`imagen-4.0-generate-001` / `-ultra-` / `-fast-`.

**Verify the live list any time** (models change):
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_GEMINI_API_KEY&pageSize=200" \
  | python3 -c "import sys,json;[print(m['name']) for m in json.load(sys.stdin)['models'] if 'image' in m['name'].lower()]"
```

## Endpoint & request shape

```
POST https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent
Header: x-goog-api-key: $KEY        (or ?key=$KEY)
```
```jsonc
{
  "contents": [{ "parts": [
    { "inlineData": { "mimeType": "image/png", "data": "<base64>" } },  // optional, repeatable
    { "text": "<prompt>" }
  ]}],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": { "aspectRatio": "1:1", "imageSize": "4K" },
    "thinkingConfig": { "thinkingLevel": "high" }   // flash* models only
  }
}
```
The returned image is base64 in `candidates[0].content.parts[*].inlineData.data`; any
`text` parts are the model's commentary (surfaced on stderr by the helper).

### Key params
- **`imageConfig.imageSize`**: `512px` | `1K` | `2K` | `4K`. Pro renders 4K natively.
- **`imageConfig.aspectRatio`**: `1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9` (and inverses).
- **`thinkingConfig.thinkingLevel`** (`minimal|low|medium|high`): **flash\* only** — trades
  latency for layout planning. Ignored by `pro`.
- **Multi-image in**: attach multiple `inlineData` parts (helper: repeat `--image`) to
  blend / recolour / restyle references while preserving composition (upcycling, re-render).

## Helper CLI

```bash
GOOGLE_API_KEY="$GOOGLE_GEMINI_API_KEY" python3 report/poster/nano_banana.py \
  --prompt "…" [--image ref1.png --image ref2.png] \
  --size 4K --aspect 16:9 --model pro --output out.png [--thinking high]
```

## Prompt patterns that worked (logo / design work, 2026-07-02)

Learned building `docs/renders/logos/` (eight Vitrine logo concepts):

- **Pro renders short wordmarks reliably.** Ask for an exact spelling explicitly —
  `the wordmark VITRINE, spelled exactly V I T R I N E, uppercase` — and it lands
  correctly, including small taglines (`CAPTURE. RECONSTRUCT. SHOWCASE.`). Verify anyway.
- **State the medium up front**: *"Professional brand-identity logo design… flat vector
  aesthetic, crisp edges, no photographic noise, generous even margins."* This kills the
  default glossy-3D-render look and yields clean, printable marks.
- **Give exact hex codes in the prompt** (`ink #1A1A1A`, `cyan #22C1D6`) — it honours them
  closely, so the output matches your palette system.
- **Name the background** (`on a warm off-white museum-paper background #F4F1EA`) — useful
  when you want each concept to sit on its own brand ground.
- **Add explicit negatives** to steer away from clichés: `no mandala, flower, or sunburst
  motif` fixed an aperture concept that first read as decorative.
- **One idea per generation.** Generate individual marks (square `1:1`, `2K`) and compose
  the multi-panel board yourself (SVG + ImageMagick) for pixel-perfect, legible captions —
  more reliable than asking the model to render an entire annotated sheet with tiny hex
  text. (Pro *can* do full composed sheets; do that only when you don't need exact type.)
- **Iterate cheaply**: 2K `1:1` marks generate in ~20-40s each; run a batch in parallel
  (background jobs), review as a `montage` contact sheet, then regenerate only the weak one.

## Composition toolchain in this environment

- **No `rsvg-convert` CLI**, but ImageMagick 7 (`magick`) has the **RSVG delegate**
  (librsvg) — render SVG with `magick board.svg -flatten board.png` (honours
  `letter-spacing`, gradients, `×`/`→`/`·` glyphs via DejaVu). MSVG/Pango also available.
- **No PIL/Pillow.** Use ImageMagick for resize/composite/montage.
- 16-bit PNGs from the API can fail to re-encode with a bare `magick … out.png`; force
  8-bit with `-depth 8 PNG24:out.png`.
- Fonts available: **DejaVu** (Sans / Serif / Mono / Condensed / ExtraLight), Liberation,
  Noto CJK. No commercial display faces — set brand type in DejaVu or bring your own TTF.
