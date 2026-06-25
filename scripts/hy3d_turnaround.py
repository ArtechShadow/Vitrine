#!/usr/bin/env python3
"""Hunyuan3D-2.1 single-image -> 6-view turnaround sheet + textured mesh.

Feeds a SAM object crop (uploaded to ComfyUI input) through the Hy3D21 graph:
  LoadImageWithTransparency -> MeshGenerator -> VAEDecode -> trimesh
  + CameraConfig -> MultiViewsGeneratorWithMetaData (albedo = turnaround panels)
  -> BakeMultiViewsWithMetaData (textured trimesh) -> ExportMesh (glb)
  + SaveImage(albedo) = the turnaround sheet.

Usage (from gaussian-toolkit): python3 hy3d_turnaround.py <image_name> <out_name> [seed]
"""
import sys, json, time, requests

COMFY = "http://vitrine-comfyui:8188"


def build(image_name, out_name, seed=42):
    return {
        "14": {"class_type": "Hy3D21LoadImageWithTransparency", "inputs": {"image": image_name}},
        "4": {"class_type": "Hy3D21VAELoader", "inputs": {"model_name": "Hunyuan3D-vae-v2-1-fp16.ckpt"}},
        "37": {"class_type": "Hy3DMeshGenerator", "inputs": {
            "model": "hunyuan3d-dit-v2-1-fp16.ckpt", "image": ["14", 0],
            "steps": 25, "guidance_scale": 7.5, "seed": seed, "attention_mode": "sdpa"}},
        "9": {"class_type": "Hy3D21VAEDecode", "inputs": {
            "vae": ["4", 0], "latents": ["37", 0], "box_v": 1.01, "octree_resolution": 192,
            "num_chunks": 64000, "mc_level": 0.0, "mc_algo": "mc",
            "enable_flash_vdm": True, "force_offload": True}},
        "19": {"class_type": "Hy3D21CameraConfig", "inputs": {
            "camera_azimuths": "0, 90, 180, 270, 0, 180", "camera_elevations": "0, 0, 0, 0, 90, -90",
            "view_weights": "1, 0.5, 1, 0.5, 1, 1", "ortho_scale": 1.1}},
        "20": {"class_type": "Hy3D21MultiViewsGeneratorWithMetaData", "inputs": {
            "trimesh": ["9", 0], "camera_config": ["19", 0], "view_size": 768, "image": ["14", 0],
            "steps": 10, "guidance_scale": 3.0, "texture_size": 1024, "unwrap_mesh": True,
            "seed": seed, "output_name": out_name}},
        "21": {"class_type": "Hy3DBakeMultiViewsWithMetaData", "inputs": {
            "pipeline": ["20", 0], "albedo": ["20", 1], "mr": ["20", 2], "metadata": ["20", 3]}},
        "44": {"class_type": "Hy3D21ExportMesh", "inputs": {
            "trimesh": ["21", 2], "filename_prefix": "dreamlab/" + out_name + "_hull",
            "file_format": "glb", "save_file": True}},
        "46": {"class_type": "SaveImage", "inputs": {
            "images": ["20", 1], "filename_prefix": "dreamlab/" + out_name + "_turnaround"}},
    }


def main():
    image, out = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    api = build(image, out, seed)
    r = requests.post(COMFY + "/prompt", json={"prompt": api}, timeout=60)
    if r.status_code != 200:
        print("REJECTED", r.status_code, r.text[:1200]); sys.exit(1)
    pid = r.json()["prompt_id"]
    print("submitted", pid, flush=True)
    t0 = time.time()
    while time.time() - t0 < 1500:
        h = requests.get(COMFY + f"/history/{pid}", timeout=15).json()
        if pid in h:
            st = h[pid].get("status", {})
            print("DONE", st.get("status_str"), flush=True)
            for nid, o in h[pid].get("outputs", {}).items():
                for k, v in o.items():
                    if isinstance(v, list):
                        for it in v:
                            if isinstance(it, dict) and it.get("filename"):
                                print(f"  [{nid}].{k}: {it['filename']} ({it.get('type')})", flush=True)
            return
        time.sleep(5)
    print("TIMEOUT", flush=True)


if __name__ == "__main__":
    main()
