# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Splat optimisation + web-viewer derivative.

Two distinct, non-overlapping responsibilities live here:

1. :func:`optimize` -- a thin wrapper around the ``@playcanvas/splat-transform``
   npm CLI used to compress / filter / convert a trained Gaussian PLY into
   PlayCanvas-native delivery formats (``.sog``, ``.compressed-ply``, ``.spz``,
   ``.glb``, ``.ply``).  These feed the **SuperSplat / NanoGS-in-UE** track.

2. :func:`make_web_ksplat` -- produces the ``@mkkellogg/gaussian-splats-3d``
   ``.ksplat`` consumed by the embedded web viewer (``SplatViewer``).

.. rubric:: ``.ksplat`` compatibility verdict (highest-risk unknown, resolved)

The two ``.ksplat`` names refer to **UNRELATED bitstreams** and MUST NOT be
assumed interchangeable:

* ``@playcanvas/splat-transform`` (verified against **v2.7.1**) lists ``.ksplat``
  as a supported *INPUT* only -- it is **not** a supported *OUTPUT*.  Asking it
  for ``-o scene.ksplat`` fails hard with ``Error: Unsupported output file
  type``.  splat-transform can *read* mkkellogg ``.ksplat`` but can never
  *write* one.  ==> the splat-transform ``.ksplat`` path FAILS the gate; it does
  not exist.
* ``@mkkellogg/gaussian-splats-3d`` (pinned **v0.4.6** in
  ``web-interface/package.json``) defines its own ``SplatBuffer`` container.
  The only supported way to produce it is mkkellogg's own converter
  (``PlyParser.parseToUncompressedSplatArray`` -> ``SplatBufferGenerator`` ->
  ``SplatBuffer.bufferData``), i.e. the upstream ``util/create-ksplat.js``
  logic, run under Node.  :func:`make_web_ksplat` reproduces exactly that logic
  in-image (dynamic-importing the staged ESM build; no THREE dependency).
  Validated: a converted ``.ksplat`` round-trips through the exact
  ``SplatBuffer`` the pinned viewer renders, at compression levels 0/1/2.

Consequence for the pipeline: the web ``.ksplat`` derivative is produced by
:func:`make_web_ksplat`, never by :func:`optimize`.  When the mkkellogg
converter is unavailable in-image the derivative is skipped cleanly and the web
viewer falls back to progressive-loading the trained ``.ply`` directly (its
``addSplatScene`` accepts ``.ply``).

INVARIANT: the source trained ``.ply`` is only ever *read* here -- never
mutated, moved, or renamed (it is the source-of-truth for the NanoGS/UE and
mesh-extraction handoffs).

ADR Reference: ADR-006 (splat-transform web-delivery decision), ADR-022
(secure single-image; conversion runs as the ``vitrine`` user in the pipeline
venv -- there is no network listener involved).  The verdict above should also
be mirrored into the ADR narrative by the docs owner.
PRD Reference: Section 3.1.2, Section 6.1.

Typical output sizes (relative):
    Raw PLY        ~100+ MB
    .sog / .ksplat < 20 MB   (after compress + filter)

Integration point: post-3DGS training, before web delivery.
The original ``.ply`` is always retained as the source-of-truth for
downstream mesh extraction backends.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Package name as published on npm.  Pin this in the Dockerfile install.
_NPX_PACKAGE = "@playcanvas/splat-transform"

# Supported output formats.  "ksplat" is the PlayCanvas native compressed
# format; "ply" and "compressed-ply" are intermediate / full-fidelity forms.
_VALID_FORMATS = frozenset({"ksplat", "sog", "glb", "ply", "compressed-ply"})


@dataclass
class SplatOptConfig:
    """Configuration for the splat-transform optimisation stage.

    Attributes:
        crop_box: Optional 6-tuple ``(x_min, y_min, z_min, x_max, y_max,
            z_max)`` in world-space units.  Gaussians outside the box are
            removed before further processing.
        opacity_min_threshold: Gaussians with opacity below this value are
            discarded (removes floaters).  Range [0, 1]; default 0.05.
        max_scale: If set, Gaussians whose maximum axis scale exceeds this
            value are discarded (removes large background artefacts).
        sort: Reorder Gaussians in Morton (Z-order) sort for optimal
            front-to-back rendering.  Recommended True.
        output_format: Target delivery format.  Must be one of
            ``"ksplat"``, ``"sog"``, ``"glb"``, ``"ply"``, or
            ``"compressed-ply"``.
        generate_html_viewer: Emit a self-contained HTML file alongside
            the output that embeds a minimal PlayCanvas splat viewer.
        timeout: Maximum seconds to wait for the splat-transform process.
    """

    crop_box: Optional[tuple[float, float, float, float, float, float]] = None
    opacity_min_threshold: float = 0.05
    max_scale: Optional[float] = None
    sort: bool = True
    output_format: str = "ksplat"
    generate_html_viewer: bool = False
    timeout: int = 300


@dataclass
class WebKsplatConfig:
    """Configuration for the mkkellogg ``.ksplat`` web derivative.

    These map onto the arguments of the upstream ``create-ksplat.js`` converter
    (``@mkkellogg/gaussian-splats-3d`` v0.4.x).

    Attributes:
        compression_level: mkkellogg ``.ksplat`` compression level -- ``0``
            (uncompressed f32), ``1`` (16-bit, the web default), or ``2``.
        alpha_removal_threshold: Byte-alpha cutoff [0, 255]; splats with alpha
            at or below this are dropped from the buffer (removes floaters).
            ``1`` matches the upstream converter default.
        sh_degree: Spherical-harmonics bands to retain (0-3).  ``0`` keeps only
            view-independent DC colour -- the smallest, fastest-loading web
            payload and the recommended default for the embedded viewer.
        block_size: Generator block size in world units.  ``None`` uses the
            generator's own default (5.0).
        bucket_size: Splats per spatial bucket.  ``None`` uses the generator's
            own default (256).
        node_heap_mb: ``--max-old-space-size`` for the Node converter; trained
            room PLYs are large, so the V8 old-space is raised accordingly.
        timeout: Maximum seconds to wait for the converter subprocess.
    """

    compression_level: int = 1
    alpha_removal_threshold: int = 1
    sh_degree: int = 0
    block_size: Optional[float] = None
    bucket_size: Optional[int] = None
    node_heap_mb: int = 8192
    timeout: int = 900


def is_splat_transform_available() -> bool:
    """Return True if the splat-transform CLI can be invoked.

    Executes ``npx @playcanvas/splat-transform --help`` with a short
    timeout.  Returns False on ``FileNotFoundError`` (npx/node not on
    PATH), ``TimeoutExpired``, or non-zero exit code.
    """
    try:
        result = subprocess.run(
            ["npx", "--yes", _NPX_PACKAGE, "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        available = result.returncode == 0
        if available:
            logger.debug("splat-transform is available via npx")
        else:
            logger.debug(
                "splat-transform --help returned rc=%d; stderr: %s",
                result.returncode,
                result.stderr[:200],
            )
        return available
    except FileNotFoundError:
        logger.debug("npx not found; splat-transform unavailable")
        return False
    except subprocess.TimeoutExpired:
        logger.debug("splat-transform availability check timed out")
        return False


def _build_cli_args(
    input_ply: Path,
    output_path: Path,
    config: SplatOptConfig,
) -> list[str]:
    """Construct the splat-transform CLI argument list.

    Builds a single compound command that applies: crop (if requested),
    opacity / scale filtering, sort, and format conversion / compression
    in one invocation where the CLI supports it.  For CLIs that require
    chained invocations the orchestrating function is responsible for
    calling this in stages; this helper targets the single-pass form.

    Returns:
        List of strings suitable for :func:`subprocess.run`.
    """
    cmd: list[str] = ["npx", "--yes", _NPX_PACKAGE]

    # Primary subcommand: compress handles quantisation + format conversion.
    # Additional flags enable crop, filter, and sort within the same pass.
    cmd.append("compress")
    cmd.extend([str(input_ply), "-o", str(output_path)])

    if config.crop_box is not None:
        box_str = ",".join(str(v) for v in config.crop_box)
        cmd.extend(["--box", box_str])

    if config.opacity_min_threshold > 0:
        cmd.extend(["--alpha-min", str(config.opacity_min_threshold)])

    if config.max_scale is not None:
        cmd.extend(["--scale-max", str(config.max_scale)])

    if config.sort:
        cmd.append("--sort")

    if config.generate_html_viewer:
        cmd.append("--html")

    return cmd


def optimize(
    input_ply: str,
    output_dir: str,
    config: Optional[SplatOptConfig] = None,
) -> dict[str, Any]:
    """Run splat-transform to optimise a trained Gaussian PLY for delivery.

    Applies crop -> filter -> sort -> compress -> convert in a single
    subprocess call where supported by the CLI.  The original PLY is
    never modified.

    Args:
        input_ply: Absolute path to the trained Gaussian PLY file.
        output_dir: Directory where the compressed output will be written.
            Created if it does not exist.
        config: Optimisation settings.  Defaults are used if ``None``.

    Returns:
        Dictionary with the following keys:

        - ``success`` (bool): Whether the optimisation completed.
        - ``output_path`` (str | None): Path to the output file.
        - ``input_size_mb`` (float): Input PLY size in megabytes.
        - ``output_size_mb`` (float): Output file size in megabytes (0.0
          on failure).
        - ``compression_ratio`` (float): ``input / output`` ratio (1.0 on
          failure).
        - ``duration`` (float): Wall-clock seconds for the subprocess.
        - ``error`` (str | None): Human-readable error message on failure.
    """
    cfg = config or SplatOptConfig()

    result: dict[str, Any] = {
        "success": False,
        "output_path": None,
        "input_size_mb": 0.0,
        "output_size_mb": 0.0,
        "compression_ratio": 1.0,
        "duration": 0.0,
        "error": None,
    }

    if cfg.output_format not in _VALID_FORMATS:
        result["error"] = (
            f"Invalid output_format '{cfg.output_format}'. "
            f"Must be one of: {sorted(_VALID_FORMATS)}"
        )
        return result

    if cfg.output_format == "ksplat":
        # splat-transform (v2.7.1) cannot emit .ksplat: it lists .ksplat as a
        # supported INPUT but not a supported OUTPUT ('-o *.ksplat' fails with
        # "Unsupported output file type").  The @mkkellogg web viewer consumes an
        # UNRELATED .ksplat bitstream -- produce it with make_web_ksplat().
        # splat-transform is reserved for the .sog/.compressed-ply/.spz/.glb
        # SuperSplat/NanoGS-in-UE track.
        result["error"] = (
            "splat-transform cannot produce '.ksplat' (input-only format in "
            "v2.7.1). Use make_web_ksplat() for the @mkkellogg web viewer "
            "derivative; keep optimize() for .sog/.compressed-ply/.spz/.glb."
        )
        return result

    input_path = Path(input_ply)
    if not input_path.exists():
        result["error"] = f"Input PLY not found: {input_ply}"
        return result

    input_size_bytes = input_path.stat().st_size
    result["input_size_mb"] = input_size_bytes / (1024 * 1024)

    if not is_splat_transform_available():
        result["error"] = "splat-transform not available (npx / Node.js missing)"
        return result

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Derive output filename: same stem, new extension.
    ext_map = {
        "ksplat": ".ksplat",
        "sog": ".sog",
        "glb": ".glb",
        "ply": ".ply",
        "compressed-ply": ".ply",
    }
    output_ext = ext_map[cfg.output_format]
    output_stem = input_path.stem + "_optimized"
    output_path = out_dir / (output_stem + output_ext)

    cmd = _build_cli_args(input_path, output_path, cfg)

    logger.info("splat-transform command: %s", " ".join(cmd))

    t_start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
        )
        result["duration"] = time.time() - t_start

        if proc.returncode != 0:
            result["error"] = (
                f"splat-transform failed (rc={proc.returncode}): "
                f"{proc.stderr[-1000:]}"
            )
            logger.error(
                "splat-transform stderr: %s",
                proc.stderr[-2000:],
            )
            return result

    except subprocess.TimeoutExpired:
        result["duration"] = time.time() - t_start
        result["error"] = f"splat-transform timed out after {cfg.timeout}s"
        logger.error("splat-transform timed out (%ds)", cfg.timeout)
        return result
    except OSError as exc:
        result["duration"] = time.time() - t_start
        result["error"] = f"Failed to launch splat-transform: {exc}"
        logger.error("splat-transform OSError: %s", exc)
        return result

    if not output_path.exists():
        result["error"] = (
            f"splat-transform succeeded but output not found: {output_path}"
        )
        return result

    output_size_bytes = output_path.stat().st_size
    output_size_mb = output_size_bytes / (1024 * 1024)
    compression_ratio = (
        input_size_bytes / output_size_bytes if output_size_bytes > 0 else 1.0
    )

    result["success"] = True
    result["output_path"] = str(output_path)
    result["output_size_mb"] = output_size_mb
    result["compression_ratio"] = compression_ratio

    logger.info(
        "splat-transform complete: %s -> %s (%.1f MB -> %.1f MB, %.1fx, %.1fs)",
        input_path.name,
        output_path.name,
        result["input_size_mb"],
        output_size_mb,
        compression_ratio,
        result["duration"],
    )

    return result


# ---------------------------------------------------------------------------
# mkkellogg .ksplat web derivative
# ---------------------------------------------------------------------------
#
# Produces the @mkkellogg/gaussian-splats-3d .ksplat consumed by the embedded
# web viewer.  See the module docstring for the compatibility verdict: this is
# the ONLY supported way to emit that bitstream (splat-transform cannot).

_MKKELLOGG_PACKAGE = "@mkkellogg/gaussian-splats-3d"

# ESM build filename inside the published npm package (v0.4.x).
_MKKELLOGG_MODULE_BASENAME = "gaussian-splats-3d.module.js"

# Node binary (overridable for non-standard images).
_NODE_BIN = os.environ.get("LFS_NODE_BIN", "node")

# Node ESM converter.  Mirrors the pinned upstream util/create-ksplat.js
# (v0.4.6) but (a) dynamic-imports whichever ESM build is staged in-image via an
# absolute file:// URL passed as argv, and (b) drops the THREE dependency by
# letting the generator default the scene centre to (0,0,0).  Emits one JSON
# line on stdout on success; a stack trace on stderr + exit(3) on failure.
_KSPLAT_CONVERTER_MJS = r"""
import * as fs from 'node:fs';

const [ , , moduleUrl, inputFile, outputFile,
        compArg, alphaArg, blockArg, bucketArg, shArg ] = process.argv;

function opt(v) { return (v === undefined || v === '-') ? undefined : v; }

const compressionLevel = opt(compArg)   !== undefined ? parseInt(compArg, 10)   : 1;
const alphaThreshold   = opt(alphaArg)  !== undefined ? parseInt(alphaArg, 10)  : 1;
const blockSize        = opt(blockArg)  !== undefined ? parseFloat(blockArg)    : undefined;
const bucketSize       = opt(bucketArg) !== undefined ? parseInt(bucketArg, 10) : undefined;
const shDegree         = opt(shArg)     !== undefined ? parseInt(shArg, 10)     : 0;
const sectionSize = 0;
const sceneCenter = undefined; // default 0,0,0 -- avoids the THREE dependency

try {
    const GS = await import(moduleUrl);
    const raw = fs.readFileSync(inputFile);
    const ab = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
    const fmt = GS.LoaderUtils.sceneFormatFromPath(inputFile.toLowerCase().trim());

    let splatBuffer;
    if (fmt === GS.SceneFormat.Ply || fmt === GS.SceneFormat.Splat) {
        const arr = (fmt === GS.SceneFormat.Ply)
            ? GS.PlyParser.parseToUncompressedSplatArray(ab, shDegree)
            : GS.SplatParser.parseStandardSplatToUncompressedSplatArray(ab);
        const gen = GS.SplatBufferGenerator.getStandardGenerator(
            alphaThreshold, compressionLevel, sectionSize, sceneCenter, blockSize, bucketSize);
        splatBuffer = gen.generateFromUncompressedSplatArray(arr);
    } else {
        splatBuffer = new GS.SplatBuffer(ab);
    }

    fs.writeFileSync(outputFile, Buffer.from(splatBuffer.bufferData));
    const splatCount = splatBuffer.getSplatCount ? splatBuffer.getSplatCount() : null;
    process.stdout.write(JSON.stringify(
        { ok: true, bytes: splatBuffer.bufferData.byteLength, splatCount: splatCount }) + '\n');
} catch (err) {
    process.stderr.write(String((err && err.stack) || err) + '\n');
    process.exit(3);
}
"""

# Node probe: confirm the staged ESM build imports AND exposes the exact symbols
# the converter needs (three must be resolvable from the module's location).
_KSPLAT_PROBE_JS = (
    "import(process.env.MKK_MODULE).then((m)=>{"
    "const ok=m&&m.PlyParser&&m.SplatBufferGenerator&&m.SplatBuffer"
    "&&m.LoaderUtils&&m.SceneFormat;process.exit(ok?0:4);"
    "}).catch((e)=>{process.stderr.write(String(e&&e.message||e));process.exit(3);});"
)


def _mkkellogg_module_candidates() -> list[Path]:
    """Return existing ``@mkkellogg/gaussian-splats-3d`` ESM builds, in priority
    order: ``$LFS_MKKELLOGG_MODULE`` first, then npm install trees (which carry
    a resolvable ``three`` peer), then the Track-1 vendored drop last."""
    candidates: list[Path] = []

    env_override = os.environ.get("LFS_MKKELLOGG_MODULE")
    if env_override:
        candidates.append(Path(env_override))

    # repo root: .../src/pipeline/splat_optimizer.py -> parents[2] == repo root
    repo_root = Path(__file__).resolve().parents[2]
    rel = Path(_MKKELLOGG_PACKAGE) / "build" / _MKKELLOGG_MODULE_BASENAME
    candidates += [
        repo_root / "node_modules" / rel,
        repo_root / "web-interface" / "node_modules" / rel,
        repo_root / "src" / "web" / "frontend" / "node_modules" / rel,
        Path("/opt/gaussian-toolkit/node_modules") / rel,
        Path("/usr/local/lib/node_modules") / rel,
        Path("/usr/lib/node_modules") / rel,
        # Vendored bundles last: they may externalise 'three' and thus not be
        # Node-importable on their own (caught by the probe).
        repo_root / "src" / "web" / "static" / "vendor" / rel,
        repo_root / "src" / "web" / "static" / "vendor"
        / "gaussian-splats-3d" / _MKKELLOGG_MODULE_BASENAME,
    ]

    seen: set[str] = set()
    existing: list[Path] = []
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            existing.append(cand)
    return existing


def find_mkkellogg_module() -> Optional[Path]:
    """Return the first existing ``gaussian-splats-3d.module.js`` on disk.

    File-existence only (no Node probe) -- useful for diagnostics.  For a build
    that is actually *importable* under Node (``three`` resolvable + expected
    exports) use :func:`resolve_mkkellogg_module`.
    """
    candidates = _mkkellogg_module_candidates()
    return candidates[0] if candidates else None


def _probe_module(module: Path) -> bool:
    """Return True if *module* imports under Node and exposes the converter's
    required exports (which requires its ``three`` peer to be resolvable)."""
    try:
        probe_env = {**os.environ, "MKK_MODULE": module.resolve().as_uri()}
        result = subprocess.run(
            [_NODE_BIN, "--input-type=module", "-e", _KSPLAT_PROBE_JS],
            capture_output=True,
            text=True,
            timeout=60,
            env=probe_env,
        )
        if result.returncode == 0:
            return True
        logger.debug(
            "mkkellogg module probe failed for %s (rc=%d): %s",
            module, result.returncode, result.stderr[:300],
        )
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("mkkellogg module probe error for %s: %s", module, exc)
        return False


def resolve_mkkellogg_module() -> Optional[Path]:
    """Return the first staged ESM build that actually imports under Node.

    Probes candidates in priority order and returns the first whose import
    succeeds (so a non-importable vendored bundle never shadows a working npm
    install).  Returns ``None`` if Node is missing or no candidate imports.
    """
    if not is_node_available():
        logger.debug("node not available; mkkellogg ksplat converter unavailable")
        return None
    for module in _mkkellogg_module_candidates():
        if _probe_module(module):
            return module
    return None


def is_node_available() -> bool:
    """Return True if the Node runtime can be invoked."""
    try:
        result = subprocess.run(
            [_NODE_BIN, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def is_mkkellogg_ksplat_converter_available() -> bool:
    """Return True iff the mkkellogg ``.ksplat`` converter can run in-image.

    Requires Node AND a staged ESM build whose exports import cleanly (which in
    turn requires ``three`` to be resolvable from the build's directory).  This
    performs a real dry-import probe rather than a mere file-existence check, so
    a missing peer ``three`` is caught here (=> the derivative is skipped and the
    viewer falls back to the ``.ply``).
    """
    return resolve_mkkellogg_module() is not None


def make_web_ksplat(
    input_ply: str,
    output_dir: str,
    config: Optional[WebKsplatConfig] = None,
    output_name: str = "scene.ksplat",
) -> dict[str, Any]:
    """Convert a trained Gaussian PLY into an mkkellogg-compatible ``.ksplat``.

    Runs the in-image Node converter (see module docstring).  The source
    ``.ply`` is opened read-only and is never modified.

    Args:
        input_ply: Absolute path to the trained Gaussian ``.ply``.
        output_dir: Directory to write the derivative into; created if absent.
        config: Conversion settings; defaults used if ``None``.
        output_name: Output filename (default ``scene.ksplat`` -- the name the
            web splat route discovers first).

    Returns:
        Dictionary with keys:

        - ``success`` (bool)
        - ``skipped`` (bool): True when the converter is unavailable / there is
          nothing to convert -- a clean, non-error outcome that signals the
          caller to fall back to serving the ``.ply``.
        - ``output_path`` (str | None)
        - ``output_name`` (str)
        - ``splat_count`` (int | None)
        - ``input_size_mb`` / ``output_size_mb`` (float)
        - ``compression_ratio`` (float)
        - ``duration`` (float)
        - ``reason`` (str | None): why the stage was skipped.
        - ``error`` (str | None): hard-failure message.
    """
    cfg = config or WebKsplatConfig()

    result: dict[str, Any] = {
        "success": False,
        "skipped": False,
        "output_path": None,
        "output_name": output_name,
        "splat_count": None,
        "input_size_mb": 0.0,
        "output_size_mb": 0.0,
        "compression_ratio": 1.0,
        "duration": 0.0,
        "reason": None,
        "error": None,
    }

    input_path = Path(input_ply)
    if not input_path.is_file():
        result["skipped"] = True
        result["reason"] = f"source PLY not found: {input_ply}"
        return result

    input_size_bytes = input_path.stat().st_size
    result["input_size_mb"] = input_size_bytes / (1024 * 1024)

    # Resolve a *working* module (probes candidates until one imports under
    # Node).  A missing Node, a missing ESM build, or a build whose 'three' peer
    # is unresolvable all yield None -- "converter unavailable" -- and must skip
    # cleanly so the caller falls back to serving the trained .ply.
    module = resolve_mkkellogg_module()
    if module is None:
        result["skipped"] = True
        result["reason"] = (
            "mkkellogg .ksplat converter unavailable in-image (node, the "
            "gaussian-splats-3d ESM build, or its 'three' peer is missing); "
            "fall back to serving the trained .ply"
        )
        return result

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / output_name

    # Write the converter to a private temp file (its module resolution is by
    # absolute file:// URL, so the script's own location is irrelevant).
    import tempfile

    script_dir = tempfile.mkdtemp(prefix="ksplat_conv_")
    script_path = Path(script_dir) / "convert.mjs"
    script_path.write_text(_KSPLAT_CONVERTER_MJS)

    def _arg(v: Any) -> str:
        return "-" if v is None else str(v)

    cmd = [
        _NODE_BIN,
        f"--max-old-space-size={int(cfg.node_heap_mb)}",
        str(script_path),
        module.resolve().as_uri(),
        str(input_path),
        str(output_path),
        _arg(cfg.compression_level),
        _arg(cfg.alpha_removal_threshold),
        _arg(cfg.block_size),
        _arg(cfg.bucket_size),
        _arg(cfg.sh_degree),
    ]

    logger.info(
        "mkkellogg ksplat convert: %s -> %s (comp=%s, sh=%s)",
        input_path.name,
        output_path.name,
        cfg.compression_level,
        cfg.sh_degree,
    )

    t_start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
        )
        result["duration"] = time.time() - t_start

        if proc.returncode != 0:
            result["error"] = (
                f"ksplat converter failed (rc={proc.returncode}): "
                f"{proc.stderr[-1000:]}"
            )
            logger.error("ksplat converter stderr: %s", proc.stderr[-2000:])
            return result

        # Parse the converter's JSON summary line (last non-empty stdout line).
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    summary = json.loads(line)
                    result["splat_count"] = summary.get("splatCount")
                except json.JSONDecodeError:
                    pass
                break

    except subprocess.TimeoutExpired:
        result["duration"] = time.time() - t_start
        result["error"] = f"ksplat converter timed out after {cfg.timeout}s"
        logger.error("ksplat converter timed out (%ds)", cfg.timeout)
        return result
    except OSError as exc:
        result["duration"] = time.time() - t_start
        result["error"] = f"Failed to launch ksplat converter: {exc}"
        logger.error("ksplat converter OSError: %s", exc)
        return result
    finally:
        shutil.rmtree(script_dir, ignore_errors=True)

    if not output_path.exists() or output_path.stat().st_size == 0:
        result["error"] = (
            f"ksplat converter reported success but output missing/empty: "
            f"{output_path}"
        )
        return result

    output_size_bytes = output_path.stat().st_size
    result["success"] = True
    result["output_path"] = str(output_path)
    result["output_size_mb"] = output_size_bytes / (1024 * 1024)
    result["compression_ratio"] = (
        input_size_bytes / output_size_bytes if output_size_bytes > 0 else 1.0
    )

    logger.info(
        "mkkellogg ksplat complete: %s (%.1f MB -> %.1f MB, %.1fx, %s splats, %.1fs)",
        output_path.name,
        result["input_size_mb"],
        result["output_size_mb"],
        result["compression_ratio"],
        result["splat_count"],
        result["duration"],
    )

    return result


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Optimise a trained Gaussian PLY via PlayCanvas splat-transform"
    )
    parser.add_argument("--input-ply", required=True, help="Path to trained PLY file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument(
        "--format",
        default="ksplat",
        choices=sorted(_VALID_FORMATS),
        help="Output format (default: ksplat)",
    )
    parser.add_argument(
        "--opacity-threshold",
        type=float,
        default=0.05,
        help="Minimum opacity threshold for filtering (default: 0.05)",
    )
    parser.add_argument(
        "--max-scale",
        type=float,
        default=None,
        help="Maximum Gaussian scale; larger splats are removed (default: none)",
    )
    parser.add_argument(
        "--crop-box",
        default=None,
        help="Crop bounding box as 'xmin,ymin,zmin,xmax,ymax,zmax'",
    )
    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Disable Morton-order sort",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate an HTML viewer alongside the output",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Subprocess timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--web-ksplat",
        action="store_true",
        help="Emit an @mkkellogg web-viewer .ksplat via make_web_ksplat() "
        "(instead of running splat-transform). splat-transform cannot "
        "produce .ksplat.",
    )
    parser.add_argument(
        "--compression-level",
        type=int,
        default=1,
        choices=(0, 1, 2),
        help="ksplat compression level for --web-ksplat (default: 1)",
    )
    parser.add_argument(
        "--alpha-removal",
        type=int,
        default=1,
        help="ksplat byte-alpha removal threshold 0-255 for --web-ksplat "
        "(default: 1)",
    )
    parser.add_argument(
        "--sh-degree",
        type=int,
        default=0,
        help="Spherical-harmonics bands to keep for --web-ksplat (default: 0)",
    )
    parser.add_argument(
        "--block-size",
        type=float,
        default=None,
        help="ksplat generator block size for --web-ksplat (default: generator)",
    )
    parser.add_argument(
        "--bucket-size",
        type=int,
        default=None,
        help="ksplat generator bucket size for --web-ksplat (default: generator)",
    )
    parser.add_argument(
        "--node-heap-mb",
        type=int,
        default=8192,
        help="Node --max-old-space-size for --web-ksplat (default: 8192)",
    )

    args = parser.parse_args()

    if args.web_ksplat:
        web_cfg = WebKsplatConfig(
            compression_level=args.compression_level,
            alpha_removal_threshold=args.alpha_removal,
            sh_degree=args.sh_degree,
            block_size=args.block_size,
            bucket_size=args.bucket_size,
            node_heap_mb=args.node_heap_mb,
            timeout=args.timeout if args.timeout != 300 else 900,
        )
        result = make_web_ksplat(args.input_ply, args.output_dir, web_cfg)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if (result["success"] or result["skipped"]) else 1)

    crop_box = None
    if args.crop_box:
        parts = [float(v) for v in args.crop_box.split(",")]
        if len(parts) != 6:
            parser.error("--crop-box must have exactly 6 comma-separated values")
        crop_box = tuple(parts)  # type: ignore[assignment]

    cfg = SplatOptConfig(
        crop_box=crop_box,
        opacity_min_threshold=args.opacity_threshold,
        max_scale=args.max_scale,
        sort=not args.no_sort,
        output_format=args.format,
        generate_html_viewer=args.html,
        timeout=args.timeout,
    )

    result = optimize(args.input_ply, args.output_dir, cfg)
    print(json.dumps(result, indent=2))
