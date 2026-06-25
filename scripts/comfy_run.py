#!/usr/bin/env python3
"""Convert a ComfyUI UI-format workflow to API format, override the input image,
submit to the ComfyUI server, poll to completion, and report outputs.

Usage (from gaussian-toolkit, reaching vitrine-comfyui):
  python3 comfy_run.py <ui_workflow.json> <input_image_name> [out_prefix]
"""
import json, sys, time, requests

COMFY = "http://vitrine-comfyui:8188"


def ui_to_api(ui, oi):
    link_map = {}
    for l in ui.get("links", []):
        # [link_id, from_node, from_slot, to_node, to_slot, type]
        link_map[l[0]] = [str(l[1]), l[2]]
    api = {}
    for n in ui["nodes"]:
        ct = n.get("type")
        if ct in ("Note", "Reroute", "PrimitiveNode", "MarkdownNote"):
            continue
        info = oi.get(ct)
        if not info:
            continue
        inputs = {}
        conn = set()
        for inp in n.get("inputs", []):
            lk = inp.get("link")
            if lk is not None and lk in link_map:
                inputs[inp["name"]] = link_map[lk]
                conn.add(inp["name"])
        wv = list(n.get("widgets_values", []) or [])
        order = list(info["input"].get("required", {}).items()) + \
                list(info["input"].get("optional", {}).items())
        wi = 0
        for name, spec in order:
            if name in conn:
                continue
            t = spec[0]
            is_widget = isinstance(t, list) or t in ("INT", "FLOAT", "STRING", "BOOLEAN")
            if not is_widget:
                continue
            if wi < len(wv):
                inputs[name] = wv[wi]; wi += 1
                if wi < len(wv) and wv[wi] in ("randomize", "fixed", "increment", "decrement"):
                    wi += 1
        api[str(n["id"])] = {"class_type": ct, "inputs": inputs}
    return api


def main():
    ui_path, img = sys.argv[1], sys.argv[2]
    oi = requests.get(COMFY + "/object_info", timeout=30).json()
    ui = json.load(open(ui_path))
    api = ui_to_api(ui, oi)
    # override every LoadImage-style node's image to the requested input
    for nid, node in api.items():
        if "LoadImage" in node["class_type"]:
            node["inputs"]["image"] = img
    r = requests.post(COMFY + "/prompt", json={"prompt": api}, timeout=60)
    if r.status_code != 200:
        print("PROMPT REJECTED:", r.status_code, r.text[:1500]); sys.exit(1)
    pid = r.json()["prompt_id"]
    print("submitted", pid, flush=True)
    t0 = time.time()
    while time.time() - t0 < 1500:
        h = requests.get(COMFY + f"/history/{pid}", timeout=15).json()
        if pid in h:
            st = h[pid].get("status", {})
            print("DONE", st.get("status_str"), flush=True)
            outs = h[pid].get("outputs", {})
            for nid, o in outs.items():
                for k, v in o.items():
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and item.get("filename"):
                                print(f"  out[{nid}].{k}: {item['filename']} ({item.get('type')})", flush=True)
            return
        time.sleep(5)
    print("TIMEOUT", flush=True)


if __name__ == "__main__":
    main()
