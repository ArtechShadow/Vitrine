#!/usr/bin/env python3
"""Dependency-light caller for the Google Gemini image API (Nano Banana Pro / 2).

Reads GOOGLE_API_KEY from ~/.claude/.env (or the environment) and calls
generateContent via the REST endpoint. Supports text-to-image and
image+text (upcycling / re-render / multi-image compositing) by attaching one
or more input images as inlineData.

Current model IDs (validated live 2026-07-02 via ListModels; see
`docs/nano-banana-usage.md`):
  pro          -> gemini-3-pro-image          (Nano Banana Pro, STABLE, flagship)
  pro-preview  -> gemini-3-pro-image-preview  (preview of the same)
  flash        -> gemini-3.1-flash-image      (Nano Banana 2, STABLE, faster/cheaper)
  flash-preview-> gemini-3.1-flash-image-preview
  flash-lite   -> gemini-3.1-flash-lite-image (lightest)
  legacy       -> gemini-2.5-flash-image      (old "nano banana 1")

Key params (generationConfig.imageConfig):
  imageSize  : 512px | 1K | 2K | 4K   (Pro supports up to 4K natively)
  aspectRatio: 1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9 (and inverses)
Pro renders legible text, hex codes, and multi-panel layouts well (good for
composed sheets). thinkingConfig.thinkingLevel (flash only) trades latency for
layout planning. Multi-image in: pass --image repeatedly to blend / recolour /
restyle references while preserving composition.

Usage:
  nano_banana.py --prompt "..." [--image in.png ...] --size 4K --aspect 16:9 \
      --model pro --output out.png [--thinking high]
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

MODELS = {
    "pro": "gemini-3-pro-image",               # Nano Banana Pro (STABLE, flagship)
    "pro-preview": "gemini-3-pro-image-preview",
    "flash": "gemini-3.1-flash-image",         # Nano Banana 2 (STABLE)
    "flash-preview": "gemini-3.1-flash-image-preview",
    "flash-lite": "gemini-3.1-flash-lite-image",
    "legacy": "gemini-2.5-flash-image",        # old nano banana 1
}
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def load_api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    env_path = Path.home() / ".claude" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "GOOGLE_API_KEY":
                v = v.strip().strip('"').strip("'")
                return v
    sys.exit("ERROR: GOOGLE_API_KEY not found in env or ~/.claude/.env")


def img_part(path: str) -> dict:
    data = Path(path).read_bytes()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--image", action="append", default=[],
                    help="input image(s) for re-render/upcycling (repeatable)")
    ap.add_argument("--size", default="1K", choices=["512px", "1K", "2K", "4K"])
    ap.add_argument("--aspect", default="2:3")
    ap.add_argument("--model", default="pro", choices=list(MODELS.keys()))
    ap.add_argument("--thinking", default=None, choices=["minimal", "low", "medium", "high"],
                    help="thinkingLevel (flash* models only; ignored for pro)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    key = load_api_key()
    model = MODELS[args.model]

    parts = [img_part(p) for p in args.image]
    parts.append({"text": args.prompt})

    gen_cfg = {
        "responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {"aspectRatio": args.aspect, "imageSize": args.size},
    }
    if args.thinking and args.model.startswith("flash"):
        gen_cfg["thinkingConfig"] = {"thinkingLevel": args.thinking}

    body = {"contents": [{"parts": parts}], "generationConfig": gen_cfg}

    url = ENDPOINT.format(model=model)
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code}: {e.read().decode()[:2000]}\n")
        return 2

    cands = payload.get("candidates", [])
    if not cands:
        sys.stderr.write("No candidates. Feedback: %s\n" % json.dumps(payload.get("promptFeedback", {}))[:1000])
        return 3
    cand = cands[0]
    content = cand.get("content", {})
    if not content.get("parts"):
        sys.stderr.write("Empty content. finishReason=%s\n" % cand.get("finishReason"))
        return 4

    text_out = []
    img_bytes = None
    for part in content["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            img_bytes = base64.b64decode(inline["data"])
        elif part.get("text"):
            text_out.append(part["text"])

    if text_out:
        sys.stderr.write("MODEL: " + " ".join(text_out)[:1500] + "\n")
    if img_bytes is None:
        sys.stderr.write("No image data in response.\n")
        return 5

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img_bytes)
    print(f"OK {args.output} ({len(img_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
