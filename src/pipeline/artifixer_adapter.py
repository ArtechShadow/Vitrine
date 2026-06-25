# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""ArtiFixer3D → CoMe/TSDF adapter (ADR-020).

ArtiFixer3D (the NVIDIA ArtiFixer recon-enhancement branch — see
``research/decisions/adr-020-artifixer-ada-fork-recon-enhancement.md``) trains its
own 3DGRUT Gaussian reconstruction from the COLMAP-posed image set Vitrine
already produces, enhances it with the ArtiFixer video-diffusion prior (filling
unobserved/holey regions), and **exports a standard INRIA-format 3D-Gaussian
PLY** via 3DGRUT's ``PLYExporter`` (``export_last.ply`` / ``point_cloud.ply``;
fields ``x,y,z, f_dc_*, f_rest_*, opacity, scale_*, rot_*``).

That is the SAME PLY schema LichtFeld emits and the existing mesh backends
(``mesh_extractor`` TSDF, ``come_extractor``; ADR-003) already ingest — so this
adapter does NOT re-export Gaussians. It:

  1. locates the enhanced 3DGRUT recon PLY under an ArtiFixer3D output root,
  2. validates it carries the 3DGS vertex properties the mesh backends need,
  3. optionally applies a world similarity transform (means + rotations + scales)
     for COLMAP/LichtFeld frame alignment, and
  4. writes the adapted PLY where the mesh stage consumes it.

ADAPTER RISK (ADR-020): the conversion must preserve geometry/colour fidelity,
and the 3DGRUT↔COLMAP/LichtFeld coordinate convention must be confirmed on the
first real scene. The default path is an **identity copy** (no transform) plus a
validation report; pass ``world_transform`` only once alignment is measured.

CLI:  python -m pipeline.artifixer_adapter <artifixer3d_output_root> <out.ply>
"""

from __future__ import annotations

import argparse
import logging
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Candidate names 3DGRUT writes its final recon to (configs/base_gs.yaml export_ply,
#: threedgrut/trainer.py), most-preferred first.
_PLY_CANDIDATES = ("export_last.ply", "point_cloud.ply")

#: Vertex properties a 3DGS PLY must carry for the TSDF / CoMe backends.
_REQUIRED_PROPS = ("x", "y", "z", "opacity",
                   "scale_0", "scale_1", "scale_2",
                   "rot_0", "rot_1", "rot_2", "rot_3",
                   "f_dc_0", "f_dc_1", "f_dc_2")


class ArtifixerAdapterError(RuntimeError):
    """Raised when the ArtiFixer3D recon PLY is missing or not a 3DGS PLY."""


@dataclass
class AdaptResult:
    src_ply: Path
    out_ply: Path
    num_gaussians: int
    transformed: bool
    missing_props: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
#  Locate + validate
# ---------------------------------------------------------------------------

def find_artifixer3d_ply(output_root: str | Path) -> Path:
    """Find the enhanced 3DGRUT recon PLY under an ArtiFixer3D output root.

    Searches for ``export_last.ply`` / ``point_cloud.ply`` (direct child first,
    then recursively, newest match wins). Raises :class:`ArtifixerAdapterError`
    if none is found."""
    root = Path(output_root)
    if root.is_file() and root.suffix == ".ply":
        return root
    if not root.exists():
        raise ArtifixerAdapterError(f"ArtiFixer3D output root not found: {root}")

    for name in _PLY_CANDIDATES:
        direct = root / name
        if direct.exists():
            return direct
    matches: list[Path] = []
    for name in _PLY_CANDIDATES:
        matches.extend(root.rglob(name))
    if not matches:
        raise ArtifixerAdapterError(
            f"no 3DGRUT recon PLY ({' / '.join(_PLY_CANDIDATES)}) under {root}; "
            "did the ArtiFixer3D distill phase finish and export_ply.enabled=true?")
    # newest by mtime — the freshest distilled recon
    return max(matches, key=lambda p: p.stat().st_mtime)


def validate_3dgs_ply(ply_path: str | Path) -> tuple[int, tuple[str, ...]]:
    """Return (num_gaussians, missing_required_props) for a candidate 3DGS PLY."""
    from plyfile import PlyData

    data = PlyData.read(str(ply_path))
    try:
        vtx = data["vertex"]
    except (KeyError, IndexError) as e:
        raise ArtifixerAdapterError(f"{ply_path}: no 'vertex' element") from e
    props = set(vtx.data.dtype.names or ())
    missing = tuple(p for p in _REQUIRED_PROPS if p not in props)
    return int(len(vtx.data)), missing


# ---------------------------------------------------------------------------
#  Optional world similarity transform (means + rotations + scales)
# ---------------------------------------------------------------------------

def _rotmat_to_wxyz(R) -> tuple[float, float, float, float]:
    """3x3 rotation matrix -> (w, x, y, z) quaternion (INRIA PLY rot order)."""
    m = R
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = 0.5 / math.sqrt(t + 1.0)
        w = 0.25 / s
        x = (m[2][1] - m[1][2]) * s
        y = (m[0][2] - m[2][0]) * s
        z = (m[1][0] - m[0][1]) * s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s
    return w, x, y, z


def _quat_mul_wxyz(a, b):
    """Hamilton product of two (w,x,y,z) quaternions."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _apply_world_transform(vtx, world_transform) -> None:
    """In-place apply a 4x4 similarity transform (rotation*scale + translation)
    to a 3DGS vertex array: means (xyz), rotation quats (rot_0..3 = wxyz), and
    log-scales (scale_0..2). Uniform scale is taken as the mean column norm of
    the upper-left 3x3 (a non-uniform/shear transform would not be a valid
    Gaussian similarity and is rejected)."""
    import numpy as np

    M = np.asarray(world_transform, dtype=np.float64).reshape(4, 4)
    A = M[:3, :3]
    t = M[:3, 3]
    col_norms = np.linalg.norm(A, axis=0)
    if col_norms.std() > 1e-3 * max(col_norms.mean(), 1e-9):
        raise ArtifixerAdapterError(
            "world_transform is non-uniform/sheared; only similarity "
            "(rotation+uniform-scale+translation) is valid for Gaussians")
    scale = float(col_norms.mean())
    R = A / scale  # pure rotation

    xyz = np.stack([vtx["x"], vtx["y"], vtx["z"]], axis=1).astype(np.float64)
    xyz = xyz @ R.T * scale + t
    vtx["x"], vtx["y"], vtx["z"] = xyz[:, 0].astype(np.float32), \
        xyz[:, 1].astype(np.float32), xyz[:, 2].astype(np.float32)

    # log-scales shift by ln(scale)
    if abs(scale - 1.0) > 1e-9:
        ln_s = math.log(scale)
        for k in ("scale_0", "scale_1", "scale_2"):
            vtx[k] = (vtx[k].astype(np.float64) + ln_s).astype(np.float32)

    # rotate the per-Gaussian quaternions: q' = q_R * q
    qR = _rotmat_to_wxyz([[R[i][j] for j in range(3)] for i in range(3)])
    qw, qx, qy, qz = (vtx["rot_0"].astype(np.float64), vtx["rot_1"].astype(np.float64),
                      vtx["rot_2"].astype(np.float64), vtx["rot_3"].astype(np.float64))
    nw, nx, ny, nz = _quat_mul_wxyz(qR, (qw, qx, qy, qz))
    norm = np.sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
    norm[norm == 0] = 1.0
    vtx["rot_0"], vtx["rot_1"], vtx["rot_2"], vtx["rot_3"] = (
        (nw / norm).astype(np.float32), (nx / norm).astype(np.float32),
        (ny / norm).astype(np.float32), (nz / norm).astype(np.float32))


# ---------------------------------------------------------------------------
#  Adapt
# ---------------------------------------------------------------------------

def adapt(artifixer3d_output: str | Path, out_ply: str | Path, *,
          world_transform: Optional[list] = None,
          strict: bool = True) -> AdaptResult:
    """Locate the enhanced 3DGRUT recon, validate it, and write the PLY the mesh
    backends consume.

    ``world_transform`` (optional 4x4 row-major similarity) aligns the 3DGRUT
    frame to the COLMAP/LichtFeld frame — leave None (identity copy) until the
    alignment is measured on a real scene (ADR-020 adapter risk). ``strict``
    raises on missing 3DGS properties; set False to copy through with a warning.
    """
    src = find_artifixer3d_ply(artifixer3d_output)
    n, missing = validate_3dgs_ply(src)
    if missing:
        msg = f"{src}: not a 3DGS PLY — missing {missing}"
        if strict:
            raise ArtifixerAdapterError(msg)
        logger.warning(msg)

    out = Path(out_ply)
    out.parent.mkdir(parents=True, exist_ok=True)

    if world_transform is None:
        shutil.copy2(src, out)
        logger.info("ArtiFixer3D adapter: copied %d-gaussian recon %s -> %s "
                    "(identity; confirm 3DGRUT↔COLMAP alignment on first scene)",
                    n, src, out)
        return AdaptResult(src, out, n, transformed=False, missing_props=missing)

    from plyfile import PlyData

    data = PlyData.read(str(src))
    _apply_world_transform(data["vertex"], world_transform)
    data.write(str(out))
    logger.info("ArtiFixer3D adapter: wrote %d-gaussian recon with world transform -> %s", n, out)
    return AdaptResult(src, out, n, transformed=True, missing_props=missing)


def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ArtiFixer3D 3DGRUT recon -> CoMe/TSDF PLY adapter (ADR-020)")
    ap.add_argument("artifixer3d_output", help="ArtiFixer3D output root (or a .ply directly)")
    ap.add_argument("out_ply", help="Destination PLY for the mesh stage")
    ap.add_argument("--no-strict", action="store_true", help="warn (don't raise) on missing 3DGS props")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    res = adapt(args.artifixer3d_output, args.out_ply, strict=not args.no_strict)
    print(f"adapted: {res.src_ply} -> {res.out_ply}  ({res.num_gaussians} gaussians, "
          f"transformed={res.transformed}, missing={res.missing_props or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
