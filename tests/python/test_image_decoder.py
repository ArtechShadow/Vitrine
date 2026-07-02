# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hermetic tests for the raw-image decode stage (src/pipeline/image_decoder.py).

CPU-only, no GPU/container/network. Covers the 2026-07-02 blocker: a native
capture with an UPPERCASE extension (`.JPG`) or a non-jpg/png format (`.tif`,
`.webp`) must land in the staged dir with a lowercase, COLMAP-/frame-globbable
extension — otherwise select_frames silently drops it and the run fails.
"""

import pathlib
import sys

import pytest

# Make `pipeline` importable from the working tree (conftest only adds src/python).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from pipeline.image_decoder import decode_directory  # noqa: E402

Image = pytest.importorskip("PIL.Image", reason="Pillow required for decode tests")


def _img(path, fmt, color=(120, 60, 30)):
    Image.new("RGB", (16, 12), color).save(path, format=fmt)


def test_native_extensions_lowercased_and_all_formats_land(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    dst = tmp_path / "out"
    _img(src / "A.JPG", "JPEG")   # uppercase native -> ext must lowercase (blocker)
    _img(src / "b.png", "PNG")    # lowercase native passthrough
    _img(src / "C.TIF", "TIFF")   # uppercase tif native
    _img(src / "d.webp", "WEBP")  # non-native -> decoded to .png via Pillow

    m = decode_directory(src, dst)

    names = sorted(p.name for p in dst.iterdir() if p.is_file())
    # No output may keep an uppercase extension — COLMAP's reader and the
    # frame-selection globs are case-sensitive on the extension.
    for n in names:
        ext = n.rsplit(".", 1)[1]
        assert ext == ext.lower(), f"{n}: uppercase extension survived decode"

    assert "A.jpg" in names   # stem preserved, extension lowercased
    assert "b.png" in names
    assert "C.tif" in names
    assert "d.png" in names   # webp converted to png
    assert m["native"] + m["decoded"] == 4
    assert m["failed"] == 0


def test_no_images_returns_zero(tmp_path):
    src = tmp_path / "empty"
    src.mkdir()
    m = decode_directory(src, tmp_path / "o")
    assert m["total"] == 0
    assert m["native"] == 0
    assert m["decoded"] == 0


def test_in_place_rename_lowercases_extension(tmp_path):
    src = tmp_path / "cap"
    src.mkdir()
    _img(src / "SHOT.JPG", "JPEG")
    m = decode_directory(src)  # in place
    names = sorted(p.name for p in src.iterdir() if p.is_file())
    assert names == ["SHOT.jpg"]
    assert m["native"] == 1
