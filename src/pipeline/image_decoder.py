# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decode a capture directory of stills into COLMAP-native images.

Photo captures (the preferred, sharper alternative to video frames — see the
Drive ingest in ``src/web/app.py``) may arrive as camera-raw (DNG/CR2/NEF/ARW/…)
or HEIC/HEIF/WebP. Neither COLMAP nor the NR-IQA gate (pyiqa/MUSIQ) can read
those directly, so this stage converts everything to 8-bit sRGB **PNG**. Formats
already native to COLMAP (jpg/png/tif/bmp) pass through unchanged.

The point of this stage is that the raw-image flow has **no blockers**: it works
on the toolchain already in the container. Decoder fallback chain (first
available wins), per format group:

    raw  : rawpy         → ImageMagick ``convert`` → dcraw
    heic : pillow-heif   → ImageMagick ``convert`` → ffmpeg
    webp : Pillow        → ImageMagick ``convert`` → ffmpeg

ImageMagick with its libheif + dcraw delegates covers RAW and HEIC even when the
optional Python libs (rawpy, pillow-heif) are absent, so the stage degrades
gracefully. Anything that still cannot be decoded is reported in the manifest
(and left in place) rather than silently dropped.

Run standalone as a stage:

    python -m pipeline.image_decoder <src_dir> [<dst_dir>]
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# COLMAP / pyiqa read these directly — no conversion needed.
NATIVE_EXTS = {"jpg", "jpeg", "png", "tif", "tiff", "bmp"}
# Camera raw (decoded via rawpy or ImageMagick's dcraw delegate).
RAW_EXTS = {
    "dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf",
    "rw2", "pef", "srw", "x3f", "erf", "kdc", "dcr", "raw", "3fr", "fff", "iiq",
    "mos", "mef", "gpr", "k25",
}
HEIC_EXTS = {"heic", "heif"}
# Other non-native stills we can convert (Pillow/ImageMagick/ffmpeg).
OTHER_DECODE_EXTS = {"webp"}

# All extensions this stage recognises as an image.
ALL_IMAGE_EXTS = NATIVE_EXTS | RAW_EXTS | HEIC_EXTS | OTHER_DECODE_EXTS

_HEIF_REGISTERED = False


def _ext(p: Path) -> str:
    return p.suffix.lower().lstrip(".")


def _has(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def _tool(name: str) -> bool:
    return shutil.which(name) is not None


# --- individual decoders: return True on success, False otherwise -----------

def _decode_pillow(src: Path, dst: Path) -> bool:
    """Pillow path — webp, tif, and HEIC when pillow-heif is installed."""
    global _HEIF_REGISTERED
    try:
        from PIL import Image
        if _ext(src) in HEIC_EXTS and not _HEIF_REGISTERED:
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
                _HEIF_REGISTERED = True
            except Exception:
                return False  # no HEIC support in Pillow here
        with Image.open(src) as im:
            im.convert("RGB").save(dst, format="PNG")
        return dst.exists() and dst.stat().st_size > 0
    except Exception as exc:
        logger.debug("pillow decode failed for %s: %s", src.name, exc)
        return False


def _decode_rawpy(src: Path, dst: Path) -> bool:
    """rawpy (libraw) path — camera raw, best quality/speed when available."""
    try:
        import imageio.v3 as iio
        import rawpy
        with rawpy.imread(str(src)) as raw:
            rgb = raw.postprocess(no_auto_bright=False, output_bps=8)
        iio.imwrite(str(dst), rgb)
        return dst.exists() and dst.stat().st_size > 0
    except Exception as exc:
        logger.debug("rawpy decode failed for %s: %s", src.name, exc)
        return False


def _decode_imagemagick(src: Path, dst: Path) -> bool:
    """ImageMagick ``convert`` — universal fallback (libheif + dcraw delegates)."""
    if not _tool("convert"):
        return False
    try:
        proc = subprocess.run(
            ["convert", "-auto-orient", f"{src}[0]", str(dst)],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            return True
        # Retry without the frame selector (some raw delegates dislike [0]).
        proc = subprocess.run(
            ["convert", "-auto-orient", str(src), str(dst)],
            capture_output=True, text=True, timeout=300,
        )
        return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception as exc:
        logger.debug("imagemagick decode failed for %s: %s", src.name, exc)
        return False


def _decode_ffmpeg(src: Path, dst: Path) -> bool:
    """ffmpeg fallback — good for webp (and HEIC if built with libheif)."""
    if not _tool("ffmpeg"):
        return False
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(dst)],
            capture_output=True, text=True, timeout=300,
        )
        return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception as exc:
        logger.debug("ffmpeg decode failed for %s: %s", src.name, exc)
        return False


def _decoders_for(ext: str):
    """Ordered decoder chain for a given (non-native) extension."""
    if ext in RAW_EXTS:
        return [("rawpy", _decode_rawpy), ("imagemagick", _decode_imagemagick)]
    if ext in HEIC_EXTS:
        return [("pillow-heif", _decode_pillow), ("imagemagick", _decode_imagemagick),
                ("ffmpeg", _decode_ffmpeg)]
    # webp / other
    return [("pillow", _decode_pillow), ("imagemagick", _decode_imagemagick),
            ("ffmpeg", _decode_ffmpeg)]


def decode_directory(
    src_dir: str | Path,
    dst_dir: Optional[str | Path] = None,
    *,
    log=None,
) -> dict:
    """Decode every image in ``src_dir`` into COLMAP-native PNG/JPEG.

    Args:
        src_dir: directory of captured stills (any mix of formats).
        dst_dir: where native + decoded images go. If ``None``, decode in place
            (non-native originals are replaced by their ``.png``; natives stay).
        log: optional ``callable(str)`` for progress lines (e.g. a job logger).

    Returns a manifest dict: ``total, native, decoded, failed, out_dir,
    by_ext, methods, failures``.
    """
    src = Path(src_dir)
    in_place = dst_dir is None
    dst = src if in_place else Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)

    def _emit(msg: str) -> None:
        logger.info(msg)
        if log:
            try:
                log(msg)
            except Exception:
                pass

    files = sorted(p for p in src.iterdir() if p.is_file() and _ext(p) in ALL_IMAGE_EXTS)
    manifest: dict = {
        "total": len(files), "native": 0, "decoded": 0, "failed": 0,
        "out_dir": str(dst), "by_ext": {}, "methods": {}, "failures": [],
    }
    if not files:
        _emit(f"decode: no recognised images in {src}")
        return manifest

    for p in files:
        ext = _ext(p)
        manifest["by_ext"][ext] = manifest["by_ext"].get(ext, 0) + 1

        if ext in NATIVE_EXTS:
            # Normalise to a lowercase extension: COLMAP's image reader and the
            # frame-selection globs are case-sensitive, so a `.JPG`/`.TIF`
            # capture must not keep its original case or it gets silently dropped.
            target = dst / f"{p.stem}.{ext}"
            if target.resolve() != p.resolve() and not target.exists():
                if in_place:
                    try:
                        p.replace(target)
                    except OSError:
                        shutil.copy2(str(p), str(target))
                else:
                    shutil.copy2(str(p), str(target))
            manifest["native"] += 1
            continue

        out = dst / (p.stem + ".png")
        method_used = None
        for name, fn in _decoders_for(ext):
            if fn(p, out):
                method_used = name
                break

        if method_used:
            manifest["decoded"] += 1
            manifest["methods"][method_used] = manifest["methods"].get(method_used, 0) + 1
            if in_place and p.resolve() != out.resolve():
                try:
                    p.unlink()
                except OSError:
                    pass
        else:
            manifest["failed"] += 1
            manifest["failures"].append(p.name)

    _emit(
        "decode: {total} images — {native} native, {decoded} converted, "
        "{failed} failed".format(**manifest)
        + (f"; methods={manifest['methods']}" if manifest["methods"] else "")
        + (f"; FAILED={manifest['failures'][:8]}" if manifest["failures"] else "")
    )
    return manifest


def _main(argv=None) -> int:
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Decode a capture dir to COLMAP-native images.")
    ap.add_argument("src_dir")
    ap.add_argument("dst_dir", nargs="?", default=None,
                    help="output dir (default: decode in place)")
    args = ap.parse_args(argv)
    manifest = decode_directory(args.src_dir, args.dst_dir)
    print(json.dumps(manifest, indent=2))
    # Non-zero exit only if nothing usable came out.
    return 0 if (manifest["native"] + manifest["decoded"]) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(_main())
