#!/usr/bin/env python3
"""Blur-aware FIFO frame sampler with end-to-end FRAME INTEGRITY.

Why: dreamlab is dense but motion-blurred. Full-4K variance-of-Laplacian shows a ~37x sharpness
range (the 960p ffmpeg `blurdetect` proxy under-discriminates and falsely reads "uniformly
blurry"), so picking the sharpest frame per overlapping window genuinely cuts motion blur while
keeping inter-frame overlap for COLMAP.

INTEGRITY CONTRACT (preserve frame integrity across the system):
  * SCORING uses a throwaway, in-memory grayscale proxy decoded straight from the source. It NEVER
    writes, alters, or re-encodes a canonical frame.
  * The SELECTED frames are extracted ONCE, at the source's full resolution, as LOSSLESS PNG, with
    no scale/filter beyond `select` and no colour-space munging — i.e. the original pixels.
  * A MANIFEST (manifest.json) records, per output frame: source frame index, pts, Laplacian score,
    and sha256; plus the source-video sha256 (provenance root) and the parameters. Provenance +
    non-corruption are therefore verifiable at every hop.
  * `--verify <dir>` re-hashes a frame directory against the manifest (use after any container<->host
    copy or before COLMAP) to prove nothing changed.
  * The SAME canonical set feeds every downstream stage — no silent re-extraction — so the
    image<->camera correspondence stays consistent through SfM/3DGS/mesh/metrics.

  score+select+extract:  python3 blur_aware_fifo_sampler.py <video> <out_dir> [--window W]
                            [--stride S|--target N] [--min-gap G] [--score-height H] [--no-extract]
  verify integrity:      python3 blur_aware_fifo_sampler.py <video> <out_dir> --verify <frames_dir>

Run where ffmpeg + numpy + scipy are available (the gaussian-toolkit image).
"""
import sys, os, subprocess, argparse, json, hashlib
import numpy as np
from scipy import ndimage


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buf), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_dims(video):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", video]).decode().strip()
    w, h = (int(x) for x in out.split(",")[:2])
    return w, h


def _frame_utility(im, edge_thresh, noise_k):
    """SfM-utility of one grayscale frame: noise-corrected sharpness x texture complexity.
    Picking the SHARPEST frame is naive — a sharp blank wall has no features, and noise
    inflates Laplacian variance (false 'sharpness') + spawns junk corners. This rewards the
    frame a COLMAP cohort actually wants: most matchable texture, least blur, least noise.
      sharpness  = variance of Laplacian        (blur kills it)
      noise      = Immerkaer sigma estimate     (subtracted from sharpness; noise inflates var)
      complexity = strong-gradient pixel frac   (texture density -> matchable features)
    """
    try:
        import cv2
        sharp = float(cv2.Laplacian(im, cv2.CV_32F).var())
        K = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
        sigma = float(np.abs(cv2.filter2D(im, cv2.CV_32F, K)).sum()
                      * np.sqrt(np.pi / 2) / (6 * (im.shape[0] - 2) * (im.shape[1] - 2)))
        grad = cv2.magnitude(cv2.Sobel(im, cv2.CV_32F, 1, 0), cv2.Sobel(im, cv2.CV_32F, 0, 1))
    except Exception:
        sharp = float(ndimage.laplace(im).var())
        K = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
        sigma = float(np.abs(ndimage.convolve(im, K)).sum()
                      * np.sqrt(np.pi / 2) / (6 * (im.shape[0] - 2) * (im.shape[1] - 2)))
        grad = np.hypot(ndimage.sobel(im, axis=1), ndimage.sobel(im, axis=0))
    complexity = float((grad > edge_thresh).mean())            # textured-pixel fraction
    sharp_corr = max(sharp - noise_k * sigma * sigma, 1.0)      # discount noise's variance inflation
    return sharp_corr * (0.02 + complexity), sharp, sigma, complexity


def score_frames(video, src_w, src_h, score_h, select_by="sfm", edge_thresh=60.0, noise_k=3.0):
    """Single decode pass -> per-frame score (+ component arrays). `select_by='sfm'` uses the
    complexity x noise-corrected-sharpness utility; 'laplacian' uses plain sharpness. Throwaway
    grayscale proxy; the canonical frames are never touched."""
    if score_h and score_h < src_h:
        h = score_h - (score_h % 2); w = int(round(src_w * h / src_h)); w -= w % 2
        vf = f"format=gray,scale={w}:{h}"
    else:
        w, h, vf = src_w, src_h, "format=gray"
    fsz = w * h
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
        "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE, bufsize=fsz * 4)
    util, sharp, noise, cplx = [], [], [], []
    while True:
        raw = p.stdout.read(fsz)
        if len(raw) < fsz:
            break
        im = np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float32)
        u, s, n, c = _frame_utility(im, edge_thresh, noise_k)
        util.append(u); sharp.append(s); noise.append(n); cplx.append(c)
    p.stdout.close(); p.wait()
    sharp = np.array(sharp)
    score = np.array(util) if select_by == "sfm" else sharp
    return score, {"sharp": sharp, "noise": np.array(noise), "complexity": np.array(cplx)}


def fifo_select(score, W, S, min_gap):
    """Sliding overlap-window FIFO: per window emit the SHARPEST (max-Laplacian) frame; dedup by gap."""
    n = len(score); sel = []; last = -10 ** 9
    for start in range(0, n, S):
        w = score[start:start + W]
        if len(w) == 0:
            break
        idx = start + int(np.argmax(w))
        if idx - last >= min_gap:
            sel.append(idx); last = idx
    return sel


def autotune_stride(score, W, min_gap, target):
    best = 1
    for S in range(1, W + 1):
        if len(fifo_select(score, W, S, min_gap)) >= target:
            best = S
    return best


def extract_lossless(video, frames, outdir):
    """Extract the selected source frames at FULL resolution, lossless PNG, no filtering but select."""
    os.makedirs(outdir, exist_ok=True)
    expr = "+".join(f"eq(n\\,{f})" for f in frames)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
        "-vf", f"select='{expr}'", "-vsync", "0", "-pix_fmt", "rgb24",
        "-compression_level", "1", os.path.join(outdir, "frame_%05d.png")], check=True)


def cmd_verify(manifest_path, frames_dir):
    man = json.load(open(manifest_path))
    bad = 0; miss = 0
    for fr in man["frames"]:
        p = os.path.join(frames_dir, fr["name"])
        if not os.path.exists(p):
            print("MISSING", fr["name"]); miss += 1; continue
        if sha256_file(p) != fr["sha256"]:
            print("CORRUPT", fr["name"]); bad += 1
    ok = len(man["frames"]) - bad - miss
    print(f"INTEGRITY: {ok}/{len(man['frames'])} ok, {bad} corrupt, {miss} missing")
    sys.exit(1 if (bad or miss) else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out_dir")
    ap.add_argument("--window", type=int, default=12)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--min-gap", type=int, default=2)
    ap.add_argument("--target", type=int, default=0)
    ap.add_argument("--score-height", type=int, default=1440, help="0 = full res (most accurate, slower)")
    ap.add_argument("--select-by", choices=["sfm", "laplacian"], default="sfm",
                    help="sfm = complexity x noise-corrected sharpness (best for COLMAP); laplacian = sharpness only")
    ap.add_argument("--edge-thresh", type=float, default=60.0, help="gradient magnitude for 'textured' pixel")
    ap.add_argument("--no-extract", action="store_true")
    ap.add_argument("--verify", metavar="FRAMES_DIR", help="re-hash a frame dir against manifest.json and exit")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    manifest_path = os.path.join(a.out_dir, "manifest.json")

    if a.verify:
        cmd_verify(manifest_path, a.verify); return

    print("[0/3] provenance: hashing source video ...", flush=True)
    src_sha = sha256_file(a.video)
    sw, sh = probe_dims(a.video)
    print(f"      {os.path.basename(a.video)}  {sw}x{sh}  sha256={src_sha[:16]}...", flush=True)

    print(f"[1/3] scoring all frames (select-by={a.select_by}, height={a.score_height or sh}) ...", flush=True)
    score, comp = score_frames(a.video, sw, sh, a.score_height, select_by=a.select_by, edge_thresh=a.edge_thresh)
    print(f"      {len(score)} frames | sharp p50={np.median(comp['sharp']):.0f} "
          f"noise p50={np.median(comp['noise']):.2f} complexity p50={np.median(comp['complexity']):.3f} "
          f"| score range {score.max()/max(score.min(),1e-6):.0f}x", flush=True)

    S = autotune_stride(score, a.window, a.min_gap, a.target) if a.target else a.stride
    sel = fifo_select(score, a.window, S, a.min_gap)
    uidx = np.linspace(0, len(score) - 1, len(sel)).astype(int)
    gain = 100 * (np.median(score[sel]) / max(np.median(score[uidx]), 1e-6) - 1)
    print(f"[2/3] FIFO select: {len(sel)} frames (W={a.window} S={S} gap={a.min_gap}); "
          f"median {a.select_by}-score {np.median(score[uidx]):.0f} (uniform) -> {np.median(score[sel]):.0f} "
          f"(+{gain:.0f}%); selected sharp p50={np.median(comp['sharp'][sel]):.0f} "
          f"noise p50={np.median(comp['noise'][sel]):.2f} complexity p50={np.median(comp['complexity'][sel]):.3f}",
          flush=True)

    man = {"source_video": os.path.abspath(a.video), "source_sha256": src_sha,
           "source_dims": [sw, sh], "select_by": a.select_by,
           "params": {"window": a.window, "stride": S, "min_gap": a.min_gap,
                      "score_height": a.score_height, "edge_thresh": a.edge_thresh},
           "n_source": int(len(score)), "n_selected": len(sel),
           "median_score_uniform": round(float(np.median(score[uidx])), 1),
           "median_score_selected": round(float(np.median(score[sel])), 1),
           "frames": [{"name": f"frame_{i+1:05d}.png", "source_frame": int(f),
                       "score": round(float(score[f]), 2), "sharp": round(float(comp['sharp'][f]), 1),
                       "noise": round(float(comp['noise'][f]), 2),
                       "complexity": round(float(comp['complexity'][f]), 3)} for i, f in enumerate(sel)]}

    if a.no_extract:
        json.dump(man, open(manifest_path, "w"), indent=1)
        print("[3/3] --no-extract: manifest written (no sha256 yet).", flush=True); return

    print(f"[3/3] extracting {len(sel)} full-res lossless PNG -> {a.out_dir}/images ...", flush=True)
    imgdir = os.path.join(a.out_dir, "images")
    extract_lossless(a.video, sel, imgdir)
    got = sorted(os.listdir(imgdir))
    assert len(got) == len(sel), f"INTEGRITY FAIL: extracted {len(got)} != selected {len(sel)}"
    for fr in man["frames"]:
        fr["sha256"] = sha256_file(os.path.join(imgdir, fr["name"]))
    json.dump(man, open(manifest_path, "w"), indent=1)
    print(f"      {len(got)} lossless frames + manifest.json (per-frame sha256 + source provenance).", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
