<!--
SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Vendored front-end libraries (`src/web/static/vendor/`)

Pinned, **locally-served** builds for the loopback web UI. The Flask service
serves these under `/static/vendor/...`, so the browser makes **zero CDN
requests** — required for the IT-signable / offline / loopback-only posture
(ADR-022). Nothing here is fetched at runtime; the files are committed and
baked into the mega-image.

Do **not** edit these files. Refresh only by re-running the procedure below and
bumping the pins + hashes here in the same change.

## Pins (verified latest per directive §3, 2026-07-02)

| Library | Vendored version | Latest on npm (checked 2026-07-02) | License | File | SHA-256 |
|---|---|---|---|---|---|
| `three` | **0.178.0** | 0.185.1 | MIT | `three/three.module.min.js` | `c49cf3f5bfd5d7fb588b19d725e70e5bf9d88e2a4e040ffb9a64a7f8f5fb372d` |
| `@mkkellogg/gaussian-splats-3d` | **0.4.7** | 0.4.7 (latest) | MIT | `gaussian-splats-3d/gaussian-splats-3d.module.js` | `f273394134c9174e49bf42bb4ea0945caaad4fdd63023b8996cc6cd248f52a6b` |
| `@google/model-viewer` | **4.3.1** | 4.3.1 (latest) | Apache-2.0 | `model-viewer/model-viewer.min.js` | `283b0672384614b4847636c306fc93fe4b1fcadc76d668b4e47f0ca76bcf033b` |

Upstream PR #6 (ArchiveSpace) pinned `@mkkellogg/gaussian-splats-3d@^0.4.6`
and `three@^0.175.0`. We bump gaussian-splats-3d to its latest `0.4.7`.

### Why `three` is pinned to 0.178.0 and not the latest 0.185.1

`gaussian-splats-3d@0.4.7` declares `peerDependencies: { "three": ">=0.160.0" }`
and has **not been republished since 2025-01-25**. Its module build imports
only the bare specifier `three` (it bundles its own `OrbitControls`), so `three`
is the single external dependency. `three` 0.180+ (Sep 2025 →) carried build /
API churn that gaussian-splats-3d has never been validated against. `0.178.0`
(2025-06-30) is the newest `three` in the same, tested-compatible era — a
deliberate, minimal, forward bump over the PR's `0.175.0` that stays inside the
known-good window. Revisit when gaussian-splats-3d publishes a release tested
against newer `three`.

## How these are wired (no build toolchain, no importmap sprawl)

- `viewer_splat.html` declares a one-entry import map: bare `"three"` →
  `/static/vendor/three/three.module.min.js`. It then
  `import * as GaussianSplats3D from ".../gaussian-splats-3d.module.js"`, whose
  internal `import … from 'three'` resolves through that map. gaussian-splats-3d
  spawns its sort worker from an **inline Blob URL** (no external worker file),
  and the viewer is created with `sharedMemoryForWorkers:false` +
  `gpuAcceleratedSort:false` — so **no SharedArrayBuffer, hence no COOP/COEP
  headers** are required on the loopback server.
- `viewer.html` loads `model-viewer.min.js` as a self-contained ES module
  (`<script type="module" src="/static/vendor/model-viewer/model-viewer.min.js">`);
  it bundles its own `three` and registers the `<model-viewer>` element. No
  import map needed.

## Refresh procedure

`npm`/`curl`-to-file are unavailable in some sandboxes; this uses stdlib Python
only. Run from the repo root, then update the pins + SHA-256 table above.

```python
import urllib.request, tarfile, tempfile, os, shutil, hashlib

PINS = {
    "three":                          ("three",                          "0.178.0"),
    "@mkkellogg/gaussian-splats-3d":  ("@mkkellogg%2Fgaussian-splats-3d","0.4.7"),
    "@google/model-viewer":           ("@google%2Fmodel-viewer",         "4.3.1"),
}
DEST = "src/web/static/vendor"
PICK = {  # (path-inside-tarball, dest-relative-path)
    "three": ("package/build/three.module.min.js", "three/three.module.min.js"),
    "@mkkellogg/gaussian-splats-3d": (
        "package/build/gaussian-splats-3d.module.js",
        "gaussian-splats-3d/gaussian-splats-3d.module.js"),
    "@google/model-viewer": ("package/dist/model-viewer.min.js", "model-viewer/model-viewer.min.js"),
}
LICENSE = {  # (path-inside-tarball, dest-relative-path)
    "three": ("package/LICENSE", "three/LICENSE"),
    "@mkkellogg/gaussian-splats-3d": ("package/LICENSE", "gaussian-splats-3d/LICENSE"),
    "@google/model-viewer": ("package/LICENSE", "model-viewer/LICENSE"),
}

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()

with tempfile.TemporaryDirectory() as tmp:
    for name, (enc, ver) in PINS.items():
        short = enc.split("%2F")[-1]
        url = f"https://registry.npmjs.org/{enc}/-/{short}-{ver}.tgz"
        tgz = os.path.join(tmp, f"{short}.tgz")
        req = urllib.request.Request(url, headers={"User-Agent": "vitrine-vendor/1.0"})
        open(tgz, "wb").write(urllib.request.urlopen(req, timeout=120).read())
        ex = os.path.join(tmp, short)
        with tarfile.open(tgz) as t:
            t.extractall(ex, filter="data")
        for src_rel, dst_rel in (PICK[name], LICENSE[name]):
            dst = os.path.join(DEST, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ex, src_rel), dst)
        js = os.path.join(DEST, PICK[name][1])
        print(sha256(js), PICK[name][1])
```
