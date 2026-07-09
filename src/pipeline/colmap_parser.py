# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parse COLMAP text-format reconstruction files into typed dataclasses.

Handles:
  - cameras.txt  (intrinsics: PINHOLE, SIMPLE_RADIAL, SIMPLE_PINHOLE, OPENCV, etc.)
  - images.txt   (extrinsics: quaternion + translation per image)
  - points3D.txt (sparse 3-D point cloud with colour and error)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
#  Camera model parameter counts (COLMAP convention)
# ---------------------------------------------------------------------------
CAMERA_MODEL_PARAMS: Dict[str, int] = {
    "SIMPLE_PINHOLE": 3,   # f, cx, cy
    "PINHOLE": 4,          # fx, fy, cx, cy
    "SIMPLE_RADIAL": 4,    # f, cx, cy, k1
    "RADIAL": 5,           # f, cx, cy, k1, k2
    "OPENCV": 8,           # fx, fy, cx, cy, k1, k2, p1, p2
    "OPENCV_FISHEYE": 8,   # fx, fy, cx, cy, k1, k2, k3, k4
    "FULL_OPENCV": 12,     # fx, fy, cx, cy, k1-k6, p1, p2
    "SIMPLE_RADIAL_FISHEYE": 4,
    "RADIAL_FISHEYE": 5,
    "THIN_PRISM_FISHEYE": 12,
}


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ColmapCamera:
    """Intrinsic camera parameters from cameras.txt."""
    camera_id: int
    model: str
    width: int
    height: int
    params: Tuple[float, ...]

    @property
    def focal_x(self) -> float:
        if self.model in ("PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            return self.params[0]
        return self.params[0]  # single focal for SIMPLE_* models

    @property
    def focal_y(self) -> float:
        if self.model in ("PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            return self.params[1]
        return self.params[0]

    @property
    def center_x(self) -> float:
        if self.model in ("PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            return self.params[2]
        return self.params[1]

    @property
    def center_y(self) -> float:
        if self.model in ("PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            return self.params[3]
        return self.params[2]


@dataclass(frozen=True, slots=True)
class ColmapImage:
    """Extrinsic pose for a single image from images.txt."""
    image_id: int
    qw: float
    qx: float
    qy: float
    qz: float
    tx: float
    ty: float
    tz: float
    camera_id: int
    name: str

    @property
    def quaternion(self) -> Tuple[float, float, float, float]:
        """Return (w, x, y, z) quaternion."""
        return (self.qw, self.qx, self.qy, self.qz)

    @property
    def translation(self) -> Tuple[float, float, float]:
        return (self.tx, self.ty, self.tz)


@dataclass(frozen=True, slots=True)
class ColmapPoint3D:
    """A sparse 3-D point from points3D.txt."""
    point3d_id: int
    x: float
    y: float
    z: float
    r: int
    g: int
    b: int
    error: float
    image_ids: Tuple[int, ...] = field(default=())
    point2d_idxs: Tuple[int, ...] = field(default=())


# ---------------------------------------------------------------------------
#  Parsers
# ---------------------------------------------------------------------------
_COMMENT_RE = re.compile(r"^\s*#")


def _iter_data_lines(filepath: Path):
    """Yield non-comment, non-empty lines from a COLMAP text file."""
    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or _COMMENT_RE.match(stripped):
                continue
            yield stripped


def parse_cameras_txt(filepath: Path | str) -> Dict[int, ColmapCamera]:
    """Parse a COLMAP cameras.txt file.

    Returns a dict mapping camera_id -> ColmapCamera.
    """
    filepath = Path(filepath)
    cameras: Dict[int, ColmapCamera] = {}
    for line in _iter_data_lines(filepath):
        tokens = line.split()
        camera_id = int(tokens[0])
        model = tokens[1]
        width = int(tokens[2])
        height = int(tokens[3])
        params = tuple(float(t) for t in tokens[4:])
        cameras[camera_id] = ColmapCamera(
            camera_id=camera_id,
            model=model,
            width=width,
            height=height,
            params=params,
        )
    return cameras


def parse_images_txt(filepath: Path | str) -> List[ColmapImage]:
    """Parse a COLMAP images.txt file.

    Each image occupies two lines:
      line 1: IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME
      line 2: POINTS2D[] as (X, Y, POINT3D_ID) — we skip this line.

    Returns a list of ColmapImage sorted by image_id.
    """
    filepath = Path(filepath)
    images: List[ColmapImage] = []
    data_lines = list(_iter_data_lines(filepath))
    idx = 0
    while idx < len(data_lines):
        tokens = data_lines[idx].split()
        if len(tokens) < 10:
            idx += 1
            continue
        image = ColmapImage(
            image_id=int(tokens[0]),
            qw=float(tokens[1]),
            qx=float(tokens[2]),
            qy=float(tokens[3]),
            qz=float(tokens[4]),
            tx=float(tokens[5]),
            ty=float(tokens[6]),
            tz=float(tokens[7]),
            camera_id=int(tokens[8]),
            name=tokens[9],
        )
        images.append(image)
        idx += 2  # skip the POINTS2D line
    images.sort(key=lambda img: img.image_id)
    return images


def parse_points3d_txt(filepath: Path | str) -> List[ColmapPoint3D]:
    """Parse a COLMAP points3D.txt file.

    Line format:
      POINT3D_ID X Y Z R G B ERROR TRACK[] as (IMAGE_ID, POINT2D_IDX)
    """
    filepath = Path(filepath)
    points: List[ColmapPoint3D] = []
    for line in _iter_data_lines(filepath):
        tokens = line.split()
        if len(tokens) < 8:
            continue
        track_tokens = tokens[8:]
        image_ids: List[int] = []
        point2d_idxs: List[int] = []
        for i in range(0, len(track_tokens) - 1, 2):
            image_ids.append(int(track_tokens[i]))
            point2d_idxs.append(int(track_tokens[i + 1]))
        points.append(ColmapPoint3D(
            point3d_id=int(tokens[0]),
            x=float(tokens[1]),
            y=float(tokens[2]),
            z=float(tokens[3]),
            r=int(tokens[4]),
            g=int(tokens[5]),
            b=int(tokens[6]),
            error=float(tokens[7]),
            image_ids=tuple(image_ids),
            point2d_idxs=tuple(point2d_idxs),
        ))
    return points


# ---------------------------------------------------------------------------
#  Binary parsers (cameras.bin / images.bin)
#
#  The direct-COLMAP reconstruction path emits BINARY models only (rawcapdev
#  layout: colmap/sparse/0/{cameras,images,points3D}.bin). Format per COLMAP's
#  src/colmap/scene/reconstruction_io.cc. Only the fields the pipeline needs
#  (intrinsics + poses) are decoded; 2D point tracks are skipped over.
# ---------------------------------------------------------------------------

# COLMAP camera model id -> (name, number of params).
_CAMERA_MODELS = {
    0: ("SIMPLE_PINHOLE", 3), 1: ("PINHOLE", 4), 2: ("SIMPLE_RADIAL", 4),
    3: ("RADIAL", 5), 4: ("OPENCV", 8), 5: ("OPENCV_FISHEYE", 8),
    6: ("FULL_OPENCV", 12), 7: ("FOV", 5), 8: ("SIMPLE_RADIAL_FISHEYE", 4),
    9: ("RADIAL_FISHEYE", 5), 10: ("THIN_PRISM_FISHEYE", 12),
}


def parse_cameras_bin(filepath: Path | str) -> Dict[int, ColmapCamera]:
    """Parse a COLMAP cameras.bin file into camera_id -> ColmapCamera."""
    import struct

    cameras: Dict[int, ColmapCamera] = {}
    with open(filepath, "rb") as fh:
        (num_cameras,) = struct.unpack("<Q", fh.read(8))
        for _ in range(num_cameras):
            camera_id, model_id = struct.unpack("<ii", fh.read(8))
            width, height = struct.unpack("<QQ", fh.read(16))
            name, num_params = _CAMERA_MODELS.get(model_id, (f"UNKNOWN_{model_id}", 4))
            params = struct.unpack(f"<{num_params}d", fh.read(8 * num_params))
            cameras[camera_id] = ColmapCamera(
                camera_id=camera_id, model=name,
                width=int(width), height=int(height), params=tuple(params),
            )
    return cameras


def parse_images_bin(filepath: Path | str) -> List[ColmapImage]:
    """Parse a COLMAP images.bin file (poses only; 2D tracks skipped)."""
    import struct

    images: List[ColmapImage] = []
    with open(filepath, "rb") as fh:
        (num_images,) = struct.unpack("<Q", fh.read(8))
        for _ in range(num_images):
            (image_id,) = struct.unpack("<i", fh.read(4))
            qw, qx, qy, qz, tx, ty, tz = struct.unpack("<7d", fh.read(56))
            (camera_id,) = struct.unpack("<i", fh.read(4))
            name_bytes = bytearray()
            while True:
                ch = fh.read(1)
                if ch in (b"\x00", b""):
                    break
                name_bytes.extend(ch)
            (num_points2d,) = struct.unpack("<Q", fh.read(8))
            fh.seek(24 * num_points2d, 1)   # (double x, double y, int64 p3d_id)
            images.append(ColmapImage(
                image_id=image_id, qw=qw, qx=qx, qy=qy, qz=qz,
                tx=tx, ty=ty, tz=tz, camera_id=camera_id,
                name=name_bytes.decode("utf-8", errors="replace"),
            ))
    return images


# ---------------------------------------------------------------------------
#  Format-agnostic model-directory loaders
# ---------------------------------------------------------------------------

def find_model_dir(root: Path | str) -> "Path | None":
    """Locate a COLMAP sparse model (text OR binary) under a job/colmap root."""
    root = Path(root)
    for c in (root / "sparse" / "0", root / "sparse",
              root / "undistorted" / "sparse" / "0",
              root / "undistorted" / "sparse", root):
        for ext in ("txt", "bin"):
            if (c / f"images.{ext}").exists() and (c / f"cameras.{ext}").exists():
                return c
    return None


def load_cameras(model_dir: Path | str) -> Dict[int, ColmapCamera]:
    """Load cameras from a model dir, preferring text over binary."""
    model_dir = Path(model_dir)
    if (model_dir / "cameras.txt").exists():
        return parse_cameras_txt(model_dir / "cameras.txt")
    return parse_cameras_bin(model_dir / "cameras.bin")


def load_images(model_dir: Path | str) -> List[ColmapImage]:
    """Load image poses from a model dir, preferring text over binary."""
    model_dir = Path(model_dir)
    if (model_dir / "images.txt").exists():
        return parse_images_txt(model_dir / "images.txt")
    return parse_images_bin(model_dir / "images.bin")
