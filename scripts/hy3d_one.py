#!/usr/bin/env python3
"""Run ONE Hunyuan3D-2.1 object: upload SAM crop -> submit Hy3D21 graph -> poll ->
verify textured GLB exists. Exit codes: 0 = GLB produced, 2 = produced-but-missing,
3 = comfyui unreachable (crashed -> caller should restart+retry), 4 = rejected/timeout.

Runs inside gaussian-toolkit (has requests; reaches vitrine-comfyui:8188).
  python3 hy3d_one.py <crop_path> <out_name> [seed]
"""
import sys, os, json, time, requests

COMFY = "http://vitrine-comfyui:8188"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hy3d_turnaround import build   # reuse the validated graph


def upload(crop_path):
    name = os.path.basename(crop_path)
    with open(crop_path, "rb") as f:
        r = requests.post(COMFY + "/upload/image",
                          files={"image": (name, f, "image/png")},
                          data={"overwrite": "true"}, timeout=60)
    r.raise_for_status()
    return r.json().get("name", name)


def glb_exists(out_name):
    # comfyui writes output/dreamlab/<out>_hull_NNNNN_.glb
    try:
        r = requests.get(COMFY + "/history", timeout=10)
    except Exception:
        pass
    p = f"/comfyui/output/dreamlab"
    return p, out_name


def main():
    crop, out = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    try:
        img = upload(crop)
        print("uploaded", img, flush=True)
        api = build(img, out, seed)
        r = requests.post(COMFY + "/prompt", json={"prompt": api}, timeout=60)
    except requests.exceptions.ConnectionError as e:
        print("COMFY_DOWN at submit:", str(e)[:120], flush=True); sys.exit(3)
    if r.status_code != 200:
        print("REJECTED", r.status_code, r.text[:800], flush=True); sys.exit(4)
    pid = r.json()["prompt_id"]
    print("submitted", pid, flush=True)
    t0 = time.time()
    while time.time() - t0 < 14400:   # big-mesh bakes (e.g. ladder) can take hours
        try:
            h = requests.get(COMFY + f"/history/{pid}", timeout=20).json()
        except requests.exceptions.ConnectionError as e:
            print("COMFY_DOWN mid-run:", str(e)[:120], flush=True); sys.exit(3)
        except requests.exceptions.Timeout:
            # comfyui busy executing -> keep polling, not a crash
            time.sleep(5); continue
        if pid in h:
            st = h[pid].get("status", {})
            ok = st.get("status_str") == "success"
            print("DONE", st.get("status_str"), flush=True)
            files = []
            for nid, o in h[pid].get("outputs", {}).items():
                for k, v in o.items():
                    if isinstance(v, list):
                        for it in v:
                            if isinstance(it, dict) and it.get("filename"):
                                files.append(it["filename"])
            print("  outputs:", files, flush=True)
            glb = any(f.endswith(".glb") for f in files)
            sys.exit(0 if (ok and glb) else 2)
        time.sleep(5)
    print("TIMEOUT", flush=True); sys.exit(4)


if __name__ == "__main__":
    main()
