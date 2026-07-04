#!/usr/bin/env python3
"""Reconstruction-quality metrics for the ArtiFixer A/B (closes QE-audit blocker B2).

Operationally defines the three quantities the audit said were undefined, computed on a single
mesh .ply given the COLMAP cameras that produced the scene. Two meshes (baseline vs enhanced vs
raw-3DGRUT control — the B5 three-arm comparison) are each scored, then diffed.

  python3 recon_quality_metrics.py <mesh.ply> <colmap_sparse_dir> [out.json] [--min-cams K] [--floater-frac F]

Definitions (all from primary geometry — no magic):
  * UNDER-OBSERVED (B2a): a mesh vertex seen (in-frustum, in front) by < K input COLMAP cameras.
    Reported as the under-observed surface-area fraction. ArtiFixer is *supposed* to improve
    coverage here; in the dense+blurry regime the QE adversarial pass (N18) predicts it won't.
  * HOLES (B2b): boundary edges (edges adjacent to exactly one triangle). Primary measure =
    total boundary-edge length normalised by sqrt(surface_area) (scale-free "holeyness"), plus
    boundary length attributable to UNDER-OBSERVED vertices (where enhancement should act).
  * FLOATERS (B2c): connected components below `floater-frac` of the largest component's triangle
    count. Reported as floater triangle-fraction + component count. (Same definition as the
    come-tets cleanup — see come-tets-cleanup-recipe; N19: baseline mesh MUST be post-cleanup so
    ArtiFixer is not credited for floaters a 50-line pass already removes.)

Run where numpy + scipy + open3d are available (the gaussian-toolkit image, or any env with them).
"""
import sys, os, json, struct, argparse
import numpy as np


# ---------------------------------------------------------------------------
# Minimal COLMAP sparse reader (cameras.bin + images.bin) — no colmap dependency.
# ---------------------------------------------------------------------------
def _read_next_bytes(f, n, fmt):
    return struct.unpack(fmt, f.read(n))


def read_cameras_bin(path):
    cams = {}
    with open(path, "rb") as f:
        n = _read_next_bytes(f, 8, "<Q")[0]
        for _ in range(n):
            cid, model, w, h = _read_next_bytes(f, 24, "<iiQQ")
            nparams = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}.get(model, 4)
            params = _read_next_bytes(f, 8 * nparams, "<" + "d" * nparams)
            cams[cid] = {"w": w, "h": h, "model": model, "params": np.array(params)}
    return cams


def read_images_bin(path):
    imgs = []
    with open(path, "rb") as f:
        n = _read_next_bytes(f, 8, "<Q")[0]
        for _ in range(n):
            _id, qw, qx, qy, qz, tx, ty, tz, cid = _read_next_bytes(f, 64, "<idddddddi")
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2d = _read_next_bytes(f, 8, "<Q")[0]
            f.read(24 * n2d)  # skip the 2D points (x,y,point3D_id)
            imgs.append({"q": np.array([qw, qx, qy, qz]), "t": np.array([tx, ty, tz]), "cid": cid})
    return imgs


def qvec2rotmat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def pinhole_fxfycxcy(cam):
    p, m = cam["params"], cam["model"]
    if m == 0:      # SIMPLE_PINHOLE f,cx,cy
        return p[0], p[0], p[1], p[2]
    if m == 1:      # PINHOLE fx,fy,cx,cy
        return p[0], p[1], p[2], p[3]
    if m in (2, 4):  # SIMPLE_RADIAL / OPENCV f(or fx,fy),cx,cy,...
        return (p[0], p[0], p[1], p[2]) if m == 2 else (p[0], p[1], p[2], p[3])
    return p[0], p[0], p[1], p[2]


# ---------------------------------------------------------------------------
def camera_coverage(verts, cams, imgs, near=1e-3):
    """Per-vertex count of cameras that see the vertex (in front + within image bounds)."""
    cov = np.zeros(len(verts), dtype=np.int32)
    V = np.hstack([verts, np.ones((len(verts), 1))])
    for im in imgs:
        cam = cams.get(im["cid"])
        if cam is None:
            continue
        fx, fy, cx, cy = pinhole_fxfycxcy(cam)
        R = qvec2rotmat(im["q"]); t = im["t"]
        Xc = (R @ verts.T).T + t          # world -> camera
        z = Xc[:, 2]
        infront = z > near
        u = fx * Xc[:, 0] / np.where(infront, z, 1) + cx
        v = fy * Xc[:, 1] / np.where(infront, z, 1) + cy
        inb = infront & (u >= 0) & (u < cam["w"]) & (v >= 0) & (v < cam["h"])
        cov += inb.astype(np.int32)
    return cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh"); ap.add_argument("sparse_dir"); ap.add_argument("out", nargs="?")
    ap.add_argument("--min-cams", type=int, default=2)
    ap.add_argument("--floater-frac", type=float, default=0.01)
    a = ap.parse_args()
    import open3d as o3d

    m = o3d.io.read_triangle_mesh(a.mesh)
    m.remove_duplicated_vertices(); m.remove_degenerate_triangles(); m.remove_unreferenced_vertices()
    V = np.asarray(m.vertices); T = np.asarray(m.triangles)
    if len(T) == 0:
        print("empty mesh", file=sys.stderr); sys.exit(2)
    area = float(m.get_surface_area())

    # --- floaters: connected components ---
    lab = np.asarray(m.cluster_connected_triangles()[0])
    counts = np.bincount(lab)
    big = counts.max()
    floater_comps = int((counts < a.floater_frac * big).sum())
    floater_tris = int(counts[counts < a.floater_frac * big].sum())
    floater_frac = floater_tris / len(T)

    # --- holes: boundary edges (edge used by exactly one triangle) ---
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    E = np.sort(E, axis=1)
    uniq, cnt = np.unique(E, axis=0, return_counts=True)
    bnd = uniq[cnt == 1]
    bnd_len = float(np.linalg.norm(V[bnd[:, 0]] - V[bnd[:, 1]], axis=1).sum()) if len(bnd) else 0.0
    holeyness = bnd_len / (area ** 0.5 + 1e-9)

    # --- coverage / under-observed ---
    cams = read_cameras_bin(os.path.join(a.sparse_dir, "cameras.bin"))
    imgs = read_images_bin(os.path.join(a.sparse_dir, "images.bin"))
    cov = camera_coverage(V, cams, imgs)
    under = cov < a.min_cams
    under_frac = float(under.mean())
    # boundary length that touches under-observed vertices (where enhancement should act)
    bnd_under = bnd[under[bnd[:, 0]] | under[bnd[:, 1]]] if len(bnd) else bnd
    bnd_under_len = float(np.linalg.norm(V[bnd_under[:, 0]] - V[bnd_under[:, 1]], axis=1).sum()) if len(bnd_under) else 0.0

    res = {
        "mesh": a.mesh, "n_verts": int(len(V)), "n_tris": int(len(T)), "surface_area": area,
        "n_cameras": len(imgs), "min_cams_threshold": a.min_cams,
        "floaters": {"n_components": int(len(counts)), "floater_components": floater_comps,
                     "floater_tri_fraction": round(floater_frac, 5),
                     "largest_component_tri_fraction": round(float(big) / len(T), 4)},
        "holes": {"boundary_edges": int(len(bnd)), "boundary_length": round(bnd_len, 3),
                  "holeyness_scalefree": round(holeyness, 4),
                  "boundary_length_in_underobserved": round(bnd_under_len, 3)},
        "coverage": {"under_observed_vertex_fraction": round(under_frac, 4),
                     "median_cams_per_vertex": int(np.median(cov)),
                     "well_observed_fraction": round(float((cov >= a.min_cams).mean()), 4)},
    }
    print(json.dumps(res, indent=2))
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=2)
        print("wrote", a.out, file=sys.stderr)


if __name__ == "__main__":
    main()
