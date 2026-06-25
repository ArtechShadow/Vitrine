#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a Vitrine exhibit scene.usda from an environment mesh (+ optional object
hulls) and COLMAP cameras, with v2g:* lineage. Mesh -> UsdGeom.Mesh (points,
faceVertexCounts/Indices, vertex displayColor); cameras -> UsdGeom.Camera from
COLMAP poses. Designed for the UE 5.8 UsdStageActor import path (ADR-016).

Usage:
  python3 scripts/exhibit_builder.py \
    --env-mesh output/scene01/model_milo/mesh.ply \
    --colmap   output/scene01/colmap/undistorted/sparse/0 \
    --job-dir  output/scene01 \
    -o output/scene01/exhibit/scene.usda
"""
from __future__ import annotations
import argparse, math, os, sys
from pathlib import Path
import numpy as np


def _load_mesh(path):
    import trimesh
    m = trimesh.load(str(path), force="mesh")
    verts = np.asarray(m.vertices, dtype=np.float32)
    faces = np.asarray(m.faces, dtype=np.int32)
    cols = None
    vc = getattr(m.visual, "vertex_colors", None)
    if vc is not None and len(vc) == len(verts):
        cols = (np.asarray(vc)[:, :3].astype(np.float32) / 255.0)
    return verts, faces, cols


def _largest_components(verts, faces, cols, keep_ratio=0.01):
    """Keep mesh components with >= keep_ratio of total faces (drop floaters).
    Uses fast graph connected-components + index remap so vertex colors are
    preserved by indexing (trimesh's split+concatenate-with-colors is O(n) slow
    and hangs on million-vertex meshes; default-grey loss is silent)."""
    import trimesh
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    comps = trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(faces)))
    if len(comps) == 0:
        return verts, faces, cols
    total = len(faces)
    keep = [c for c in comps if len(c) >= keep_ratio * total]
    if not keep:
        keep = [max(comps, key=len)]
    kept = np.concatenate(keep)
    new_faces = faces[kept]
    used = np.unique(new_faces)
    remap = np.full(len(verts), -1, dtype=np.int64); remap[used] = np.arange(len(used))
    out_v = verts[used].astype(np.float32)
    out_f = remap[new_faces].astype(np.int32)
    out_c = cols[used] if cols is not None else None
    return out_v, out_f, out_c


def _decimate(verts, faces, cols, target_faces):
    """Quadric-decimate to ~target_faces (GPU-irrelevant, fast C++), transferring
    vertex colors by nearest original vertex (kept appearance)."""
    if len(faces) <= target_faces:
        return verts, faces, cols
    import fast_simplification
    reduction = max(0.0, 1.0 - float(target_faces) / float(len(faces)))
    nv, nf = fast_simplification.simplify(verts, faces, target_reduction=reduction)
    nv = np.asarray(nv, np.float32); nf = np.asarray(nf, np.int32)
    ncols = None
    if cols is not None:
        from scipy.spatial import cKDTree
        _, idx = cKDTree(verts).query(nv, k=1)
        ncols = cols[idx]
    print(f"decimated {len(faces)} -> {len(nf)} faces (reduction {reduction:.2f})")
    return nv, nf, ncols


def _read_colmap_cameras(sparse_dir):
    """Return list of (name, c2w 4x4, fx,fy,cx,cy,w,h) from COLMAP TXT/BIN."""
    sparse = Path(sparse_dir)
    # ensure TXT
    if not (sparse / "images.txt").exists() and (sparse / "images.bin").exists():
        import subprocess
        subprocess.run(["colmap", "model_converter", "--input_path", str(sparse),
                        "--output_path", str(sparse), "--output_type", "TXT"],
                       check=False, capture_output=True)
    cams = {}
    cf = sparse / "cameras.txt"
    if cf.exists():
        for ln in cf.read_text().splitlines():
            if ln.startswith("#") or not ln.strip():
                continue
            t = ln.split(); cid = int(t[0]); model = t[1]; w = int(t[2]); h = int(t[3])
            p = list(map(float, t[4:]))
            if model == "PINHOLE":
                fx, fy, cx, cy = p[0], p[1], p[2], p[3]
            elif model == "SIMPLE_PINHOLE":
                fx = fy = p[0]; cx, cy = p[1], p[2]
            else:
                fx, fy, cx, cy = p[0], p[0], p[1], p[2]
            cams[cid] = (fx, fy, cx, cy, w, h)
    out = []
    imf = sparse / "images.txt"
    if imf.exists():
        lines = [l for l in imf.read_text().splitlines() if not l.startswith("#") and l.strip()]
        for i in range(0, len(lines), 2):
            t = lines[i].split()
            qw, qx, qy, qz = map(float, t[1:5]); tx, ty, tz = map(float, t[5:8])
            cid = int(t[8]); name = t[9]
            n = math.sqrt(qw*qw+qx*qx+qy*qy+qz*qz); qw,qx,qy,qz = qw/n,qx/n,qy/n,qz/n
            R = np.array([[1-2*(qy*qy+qz*qz),2*(qx*qy-qw*qz),2*(qx*qz+qw*qy)],
                          [2*(qx*qy+qw*qz),1-2*(qx*qx+qz*qz),2*(qy*qz-qw*qx)],
                          [2*(qx*qz-qw*qy),2*(qy*qz+qw*qx),1-2*(qx*qx+qy*qy)]])
            t_vec = np.array([tx, ty, tz])
            w2c = np.eye(4); w2c[:3,:3] = R; w2c[:3,3] = t_vec
            c2w = np.linalg.inv(w2c)
            if cid in cams:
                out.append((name, c2w, *cams[cid]))
    return out


def build(env_mesh, colmap, job_dir, out_path, keep_ratio=0.01, max_cameras=12, target_faces=1_000_000, bake_texture=True):
    from pxr import Usd, UsdGeom, UsdShade, Gf, Sdf, Kind, Vt
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    verts, faces, cols = _load_mesh(env_mesh)
    n0 = len(faces)
    verts, faces, cols = _largest_components(verts, faces, cols, keep_ratio)
    print(f"env mesh: {len(verts)} verts, {len(faces)} faces (was {n0}; floaters dropped), colors={cols is not None}")
    verts, faces, cols = _decimate(verts, faces, cols, target_faces)
    # Recenter to origin + clip outlier spikes so the UE bbox is tight + centred
    # (the StageActor reports ext=0 and a stray vertex otherwise mis-frames the cam).
    import trimesh as _tm
    _m = _tm.Trimesh(verts, faces,
                     vertex_colors=(cols if cols is None else (cols * 255).astype(np.uint8)),
                     process=False)
    med = np.median(_m.vertices, axis=0)
    _m.apply_translation(-med)
    r = np.linalg.norm(_m.vertices, axis=1)
    keep = r <= (np.percentile(r, 99.0) * 1.4)
    fmask = keep[_m.faces].all(axis=1)
    _m.update_faces(fmask); _m.remove_unreferenced_vertices()
    verts = np.asarray(_m.vertices, np.float32); faces = np.asarray(_m.faces, np.int32)
    vc = getattr(_m.visual, "vertex_colors", None)
    cols = (np.asarray(vc)[:, :3].astype(np.float32) / 255.0) if vc is not None and len(vc) == len(verts) else cols
    print(f"final mesh: {len(verts)} verts, {len(faces)} faces, colors={cols is not None}, recentred+clipped")

    # Fast colored GLB export — UE Interchange reads GLB vertex colors into the mesh
    # color channel reliably (unlike USD displayColor), so a vertex-color material
    # shows the captured appearance. Written next to the USD.
    try:
        glb_path = Path(out_path).with_suffix(".glb")
        if uv is not None and tex_img is not None:
            from trimesh.visual import TextureVisuals
            from trimesh.visual.material import PBRMaterial
            mat = PBRMaterial(baseColorTexture=tex_img, baseColorFactor=[255, 255, 255, 255],
                              metallicFactor=0.0, roughnessFactor=0.9, doubleSided=True)
            vis = TextureVisuals(uv=uv, image=tex_img, material=mat)
            _gm = _tm.Trimesh(verts, faces, visual=vis, process=False)
        else:
            vc8 = (cols * 255).astype(np.uint8) if cols is not None else None
            _gm = _tm.Trimesh(verts, faces, vertex_colors=vc8, process=False)
        _gm.export(str(glb_path))
        print(f"wrote {'textured' if uv is not None else 'colored'} GLB {glb_path.name} ({glb_path.stat().st_size/1e6:.1f} MB)")
    except Exception as e:
        import traceback; print(f"GLB export failed: {e}\n{traceback.format_exc()[:300]}")

    # Bake vertex colors -> UV texture (fast: xatlas UV + per-face flat PIL fill,
    # O(texture pixels)). UE imports textured materials 100% reliably, unlike
    # vertex colors / displayColor. Texture carries the captured appearance.
    uv = None; tex_rel = None; tex_img = None
    if bake_texture and cols is not None:
        try:
            import xatlas
            from PIL import Image, ImageDraw
            vmap, fout, uvs = xatlas.parametrize(verts, faces)
            nv = verts[vmap]; nc = (np.clip(cols[vmap], 0, 1) * 255).astype(np.uint8)
            TS = 2048
            img = Image.new("RGB", (TS, TS), (128, 120, 110)); dr = ImageDraw.Draw(img)
            px = (uvs * [TS - 1, TS - 1]); px[:, 1] = (TS - 1) - px[:, 1]  # flip V
            tri = fout
            fc = nc[tri].mean(axis=1).astype(np.uint8)  # per-face avg color
            for i in range(len(tri)):
                a, b, c = tri[i]
                dr.polygon([tuple(px[a]), tuple(px[b]), tuple(px[c])],
                           fill=(int(fc[i, 0]), int(fc[i, 1]), int(fc[i, 2])))
            tex_path = Path(out_path).parent / "scene_texture.png"
            img.save(str(tex_path))
            verts = nv.astype(np.float32); faces = fout.astype(np.int32)
            uv = uvs.astype(np.float32); tex_rel = tex_path.name; tex_img = img; cols = None
            print(f"baked texture {tex_rel} ({TS}px): {len(verts)} verts (UV), {len(faces)} faces")
        except Exception as e:
            import traceback; print(f"texture bake failed: {e}\n{traceback.format_exc()[:400]}")

    stage = Usd.Stage.CreateNew(str(out_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(world.GetPrim())
    Usd.ModelAPI(world.GetPrim()).SetKind(Kind.Tokens.assembly)
    wp = world.GetPrim()
    wp.SetCustomDataByKey("v2g:pipeline_version", "1.0")
    wp.SetCustomDataByKey("v2g:job_dir", str(job_dir))
    wp.SetCustomDataByKey("v2g:env_mesh", str(env_mesh))
    wp.SetCustomDataByKey("v2g:up_axis", "Y")

    env = UsdGeom.Xform.Define(stage, "/World/Environment")
    mesh = UsdGeom.Mesh.Define(stage, "/World/Environment/Room")
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(verts))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 3, np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.reshape(-1)))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)  # interior views must render back faces
    if uv is not None and tex_rel:
        # textured path: st primvar + UsdUVTexture -> diffuseColor (UE-reliable)
        stpv = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        stpv.Set(Vt.Vec2fArray.FromNumpy(uv.astype(np.float32)))
        mat = UsdShade.Material.Define(stage, "/World/Environment/Room/CapturedMat")
        surf = UsdShade.Shader.Define(stage, "/World/Environment/Room/CapturedMat/Surface")
        surf.CreateIdAttr("UsdPreviewSurface")
        surf.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)
        surf.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        streader = UsdShade.Shader.Define(stage, "/World/Environment/Room/CapturedMat/stReader")
        streader.CreateIdAttr("UsdPrimvarReader_float2")
        streader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        stout = streader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        tex = UsdShade.Shader.Define(stage, "/World/Environment/Room/CapturedMat/diffuseTex")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(f"./{tex_rel}")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(stout)
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        texout = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        surf.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texout)
        mat.CreateSurfaceOutput().ConnectToSource(surf.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
        UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(mat)
    elif cols is not None:
        pv = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "displayColor", Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.vertex)
        pv.Set(Vt.Vec3fArray.FromNumpy(cols))
        # UsdPreviewSurface that reads the displayColor vertex primvar -> UE 5.8
        # imports this as a real vertex-color material (plain displayColor alone
        # imports as a flat white default material).
        mat = UsdShade.Material.Define(stage, "/World/Environment/Room/CapturedMat")
        surf = UsdShade.Shader.Define(stage, "/World/Environment/Room/CapturedMat/Surface")
        surf.CreateIdAttr("UsdPreviewSurface")
        surf.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.85)
        surf.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        reader = UsdShade.Shader.Define(stage, "/World/Environment/Room/CapturedMat/cvReader")
        reader.CreateIdAttr("UsdPrimvarReader_float3")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("displayColor")
        reader.CreateInput("fallback", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0.5, 0.5, 0.5))
        rout = reader.CreateOutput("result", Sdf.ValueTypeNames.Float3)
        surf.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(rout)
        mat.CreateSurfaceOutput().ConnectToSource(surf.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
        UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(mat)
    mesh.GetPrim().SetCustomDataByKey("v2g:source", "milo-sdf" if "milo" in str(env_mesh) else "tsdf")
    Usd.ModelAPI(mesh.GetPrim()).SetKind(Kind.Tokens.component)

    # cameras (subsample) for UE viewpoint placement
    cam_root = UsdGeom.Xform.Define(stage, "/World/Cameras")
    if colmap:
        cams = _read_colmap_cameras(colmap)
        if cams:
            step = max(1, len(cams)//max_cameras)
            for i, (name, c2w, fx, fy, cx, cy, w, h) in enumerate(cams[::step][:max_cameras]):
                cam = UsdGeom.Camera.Define(stage, f"/World/Cameras/cam_{i:02d}")
                xf = cam.AddTransformOp(); xf.Set(Gf.Matrix4d(*c2w.T.flatten().tolist()))
                ha = 36.0; cam.CreateHorizontalApertureAttr(ha)
                cam.CreateFocalLengthAttr(float(fx / w * ha))
                cam.CreateVerticalApertureAttr(ha * h / w)
                cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 1000.0))
            print(f"wrote {min(len(cams[::step]), max_cameras)} cameras")
    stage.GetRootLayer().Save()
    print(f"WROTE {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env-mesh", required=True)
    p.add_argument("--colmap", default=None)
    p.add_argument("--job-dir", default="")
    p.add_argument("--keep-ratio", type=float, default=0.01)
    p.add_argument("--target-faces", type=int, default=1_000_000)
    p.add_argument("--no-bake-texture", action="store_true")
    p.add_argument("-o", "--output", required=True)
    a = p.parse_args()
    build(a.env_mesh, a.colmap, a.job_dir, a.output, a.keep_ratio,
          target_faces=a.target_faces, bake_texture=not a.no_bake_texture)


if __name__ == "__main__":
    main()
