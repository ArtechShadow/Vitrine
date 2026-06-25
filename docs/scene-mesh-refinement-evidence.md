# Scene-Mesh Refinement — Verified Evidence & Tables

**Scope:** dreamlab locked run, scene-mesh TSDF extraction + connected-component
cleaning + ArtiFixer stage-1 prepare. Every number below was re-derived directly
from the run logs under
`/home/devuser/workspace/gaussian/LichtFeld-Studio/output/dreamlab/locked/`.
Discrepancies vs. the supplied fact sheet are flagged inline with **[NOTE]**.

Logs read (all paths relative to the `locked/` directory above):

| Attempt | Backend / config | Logs |
|---|---|---|
| 1 | CPU VoxelBlockGrid, default block_res (16) | `come_tsdf_v0050.log`, `come_tsdf_v0035.log` |
| 2 | CPU VoxelBlockGrid, block_res=8 | `come_tsdf_v0040.log`, `come_tsdf_v0060.log` |
| 3 | CUDA VoxelBlockGrid, block_res=8 | `come_tsdf_cuda_v0050.log`, `come_tsdf_cuda_v0060.log` |
| 4 | Legacy ScalableTSDFVolume (CPU) — **SUCCESS** | `come_tsdf_legacy_v0050.log`, `come_tsdf_legacy_v0070.log` |
| clean | connected-component cleaning | `refine/clean_v0050.log`, `refine/clean_v0070.log` |
| main | largest-component isolation + QA renders | `refine/main_v0050.log` |
| artifixer | ArtiFixer stage-1 prepare | `artifixer/prepare.log` |

---

## 1. TSDF backend × config stability matrix

block_resolution column: Attempt-1 runs do **not** print a `block_res` token in
their config line (`VBG device=CPU:0 voxel=… block_count=…`), consistent with the
Open3D VoxelBlockGrid default of 16. Attempts 2–3 explicitly print `block_res=8`.

| Attempt | Backend | block_res | voxel | block_count cap | active_blocks (logged) | Outcome | Failure step |
|---|---|---|---|---|---|---|---|
| 1 | CPU | 16 (default; not printed) | 0.005 | 250,000 | — (not logged) | SEGFAULT (core dumped) | Render/integrate, frame **648/750** |
| 1 | CPU | 16 (default; not printed) | 0.0035 | 600,000 | — (not logged) | SEGFAULT (core dumped) | Render/integrate, frame **203/750** |
| 2 | CPU | 8 | 0.004 | 8,000,000 | — (not logged) | SEGFAULT (core dumped) | Render/integrate, frame **618/750** |
| 2 | CPU | 8 | 0.006 | 4,000,000 | **735,967 / 4,000,000 (18.4%)** | SEGFAULT (core dumped) | After render 750/750, in **extract_triangle_mesh()** |
| 3 | CUDA | 8 | 0.005 | 1,500,000 | **1,074,138 / 1,500,000 (71.6%)** | ABORT (core dumped) | After render 750/750, in **extract_triangle_mesh().to_legacy()** |
| 3 | CUDA | 8 | 0.006 | 1,000,000 | **735,967 / 1,000,000 (73.6%)** | ABORT (core dumped) | After render 750/750, in **extract_triangle_mesh().to_legacy()** |
| 4 | Legacy (CPU) | n/a (ScalableTSDFVolume) | 0.005 | n/a | n/a | **SUCCESS** — `EXTRACT_DONE_0050` | — |
| 4 | Legacy (CPU) | n/a (ScalableTSDFVolume) | 0.007 | n/a | n/a | **SUCCESS** — `EXTRACT_DONE_0070` | — |

Notes / discrepancies:
- **[NOTE — wording]** The fact sheet labels the Attempt-1/Attempt-2 crash steps
  as "integrate frame N". The logs show those segfaults on the **"Rendering
  progress"** bar, not a bar labelled "integrate" (the legacy runs are the only
  ones with a "TSDF integrate" bar). Frame indices (648, 203, 618) match exactly;
  only the bar label differs.
- **[NOTE — Attempt 2 v0060]** Fact sheet says "active_blocks=735,967/4M (18.4%)
  then SEGFAULT in extract_triangle_mesh()". Confirmed: `active_blocks=735967 /
  cap=4000000 (18.4% of cap)`, render reaches 750/750, then a bare segfault with
  no Python traceback (CPU path dies before the traceback prints) — consistent
  with dying inside the extract call.
- **[NOTE — CUDA "Open3D 0.19" attribution]** The fact sheet attributes Attempt 3
  to an "Open3D 0.19 VoxelBlockGrid extract bug". The logs do **not** print an
  Open3D version string anywhere. What the logs *do* show is the concrete error:
  `RuntimeError: [Open3D Error] … CUDA runtime error: an illegal memory access was
  encountered` raised at `vbg.extract_triangle_mesh().to_legacy()`
  (`MemoryManagerCUDA.cpp`). The "0.19" version number is **not confirmable from
  the logs**.
- The "baseline voxel 0.015 VoxelBlockGrid/CUDA → 3.2M faces" figure is **not in
  any of these eight logs** (it predates this log set; an earlier `come_tsdf.log`
  exists but was outside the assigned scope).

---

## 2. Legacy-TSDF success + cleaning results

Mesh-extract numbers from the legacy logs (`Mesh Extracted: … verts=… tris=…`),
PLY sizes from the on-disk files in `model_come/test/ours_30000/`, integrate
timing from the final `TSDF integrate: 100%` line, cleaning numbers from
`refine/clean_v00*.log`.

| voxel | verts (extract) | raw faces (tris) | PLY size on disk | integrate time | cleaned faces | floaters removed | clusters |
|---|---|---|---|---|---|---|---|
| 0.005 | 33,262,302 | 51,476,998 | 2,365,578,706 B = 2.20 GiB (**2.37 GB**) | **71 s** (`01:11`), 10.55 it/s | 30,352,446 | 21,124,552 (**41.0%**) | 1,382,549 (biggest 29,011,362) |
| 0.007 | 16,486,381 | 25,656,849 | 1,174,344,798 B = 1.09 GiB (**1.17 GB**) | **50 s** (`00:50`), 14.78 it/s | 15,908,111 | 9,748,738 (**38.0%**) | 663,042 (biggest 15,086,418) |

Verification details:
- **Sizes:** the fact sheet's "2.37GB"/"1.17GB" are **decimal GB** (÷10⁹) of the
  exact byte counts above — confirmed. In GiB they are 2.20 / 1.09.
- **Timing:** fact sheet "~71s, 10.5 it/s" and "~50s, 14.8 it/s" — confirmed
  (`750/750 [01:11<00:00, 10.55it/s]` and `750/750 [00:50<00:00, 14.78it/s]`).
- **Cleaning rule:** `kept=2` (keep clusters whose size ≥ 2% of the biggest):
  - 0.005: threshold `>= 580,227 f`, removed `21,124,552/51,476,998` → `30,352,446 f`. 21.1M removed = 41.04% (fact sheet 41% ✓; "biggest 29.0M" ✓ = 29,011,362).
  - 0.007: threshold `>= 301,728 f`, removed `9,748,738/25,656,849` → `15,908,111 f`. 9.7M removed = 38.00% (fact sheet 38% ✓; "biggest 15.1M" ✓ = 15,086,418).
- **[NOTE — minor verts mismatch]** The clean logs' "loaded" line reports slightly
  fewer verts than the extract line:
  - 0.005: extract `verts=33,262,302`, clean loaded `33,262,252 v` (−50).
  - 0.007: extract `verts=16,486,381`, clean loaded `16,486,372 v` (−9).
  Trivial (PLY round-trip / duplicate-vertex merge on reload); face counts match
  exactly across both stages. Fact-sheet "33.3M / 16.5M" round either figure fine.
- **Largest-component isolation** (`refine/main_v0050.log`): the cleaned v0050
  mesh's single largest component is `254,131 v / 556,913 f (of 3,862 clusters)`;
  the baseline mesh's largest is `1,367,174 v / 2,572,841 f (of 5 clusters)`. QA
  renders `RENDER_DONE … MAIN_DONE` emitted (Blender 5.0.1).

---

## 3. Mitigation chain (hypothesis → log evidence → conclusion)

1. **Attempt 1 — CPU VoxelBlockGrid, default block_res(16), small caps.**
   - *Hypothesis:* a modest pre-allocated block hash (250k / 600k blocks) at fine
     voxel (0.005 / 0.0035) is enough for the room.
   - *Log showed:* both runs **segfault mid-render** — `0.005` at frame **648/750**,
     `0.0035` at frame **203/750** (`Segmentation fault (core dumped)`), no
     traceback, no `active_blocks` line ever printed (died before extract).
   - *Conclusion:* the hard pre-allocated `block_count` cap overflows and corrupts
     the hash backend during integration; finer voxel → earlier overflow (648 →
     203). RAM was never the limiter (no OOM/MemoryError). Need a larger cap and/or
     smaller block_res.

2. **Attempt 2 — CPU VoxelBlockGrid, block_res=8, much larger caps.**
   - *Hypothesis:* dropping block_res 16→8 (8× fewer voxels/block) plus a huge cap
     (8M / 4M) avoids overflow.
   - *Log showed:* `0.004 / cap 8M` still **segfaults at frame 618/750** during
     render. `0.006 / cap 4M` survives integration —
     `active_blocks=735,967 / 4,000,000 (18.4%)`, render completes 750/750 — then
     **segfaults inside extract_triangle_mesh()**.
   - *Conclusion:* res8 with a sane occupancy (18.4% of cap) fixes the *integrate*
     crash, but the CPU VoxelBlockGrid **mesh extraction itself** is the new
     failure point at this grid scale. Move extraction to CUDA.

3. **Attempt 3 — CUDA VoxelBlockGrid, block_res=8.**
   - *Hypothesis:* the CUDA extract kernel is more robust than the CPU one.
   - *Log showed:* both runs integrate fine and render 750/750 with high occupancy
     (`1,074,138 / 1,500,000 = 71.6%`; `735,967 / 1,000,000 = 73.6%`), then **Abort
     (core dumped)** with a real Python traceback:
     `RuntimeError: [Open3D Error] … CUDA runtime error: an illegal memory access
     was encountered` at `vbg.extract_triangle_mesh().to_legacy()`.
   - *Conclusion:* the VoxelBlockGrid `extract_triangle_mesh` path is broken at
     large grids on **both** CPU (segfault) and CUDA (illegal memory access) — it
     is the extraction routine, not integration or RAM/VRAM, that fails. Abandon
     VoxelBlockGrid; switch to the legacy `ScalableTSDFVolume`.
   - *[NOTE]* version "0.19" not present in logs (see §1 note).

4. **Attempt 4 — Legacy `ScalableTSDFVolume` (CPU).**
   - *Hypothesis:* the older `ScalableTSDFVolume` integrator+extractor sidesteps
     the VoxelBlockGrid extract bug entirely.
   - *Log showed:* **SUCCESS** both voxels.
     `0.005` → `Mesh Extracted … verts=33262302 tris=51476998`, `EXTRACT_DONE_0050`,
     2.37 GB PLY, integrate 71 s @ 10.55 it/s.
     `0.007` → `verts=16486381 tris=25656849`, `EXTRACT_DONE_0070`, 1.17 GB PLY,
     integrate 50 s @ 14.78 it/s.
   - *Conclusion:* legacy ScalableTSDFVolume is the stable scene-mesh path. Raw mesh
     is huge and floater-laden → feed into connected-component cleaning (§2).

---

## 4. ArtiFixer pipeline stages

Source: `artifixer/prepare.log` (last write 2026-06-24 22:23:27, terminal marker
`PREPARE_FAILED`) plus the fact sheet for the downstream (not-yet-reached) stages.

| Stage | Command / step | Status | Notes |
|---|---|---|---|
| prepare | `prepare_colmap_artifixer_inputs.py` | **FAILED (this run)** | empty-val crash fixed (split now 720 train / 30 val via `selected_train_images.txt`); sm_89 JIT compile OK; 10k 3dgrut recon trained OK; then **CUDA OOM** at render step → `PREPARE_FAILED`. **[NOTE: not "currently running" — see below]** |
| run_inference | 14B enhance pass | **Not reached** | named only in the fact sheet; no occurrence in `prepare.log`. |
| run_artifixer3d | distill pass | **Not reached** | named only in the fact sheet; no occurrence in `prepare.log`. |

Prepare sub-step evidence (chronological, from `prepare.log`):
- **Empty-val fix / split:** `selected_train_images.txt` = **720 lines**;
  `prep/selected_images.txt` = 720; `Split: val, indices: [24 49 … 724 749]` =
  **30 entries**. Fact-sheet "720 train / 30 val" — **confirmed**.
- **sm_89 JIT compile:** the JIT build ran with
  `-gencode=arch=compute_89,code=sm_89` for both `lib3dgut_cc` and `lib_mcmc_cc`
  extensions (torch_extensions `py312_cu128`). Compile **completed** (it proceeded
  to training).
- **10k recon:** `🤸 Initiating new 3dgrut training` → Training Statistics table
  `n_steps=10000, n_epochs=14, training_time=405.07 s, iteration_speed=24.69 it/s`
  → `💾 Saved checkpoint … ckpt_10000.pt` (708 MB on disk) → `🥳 Training Complete.`
- **[NOTE — MAJOR discrepancy vs fact sheet]** The fact sheet says prepare is
  "currently running (3DGRUT JIT compile for sm_89 then 10k recon)." The log shows
  prepare went **past** that point — JIT and the 10k recon both finished — and then
  **crashed** during `render_reconstruction → render_3dgrut_colmap` with
  `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 78.00 MiB. GPU 0
  has a total capacity of 47.39 GiB of which 40.25 MiB is free … 47.33 GiB in use`.
  Final log line is `PREPARE_FAILED`; `prep/recon_results/` is empty. So as of this
  log the prepare stage is **failed (post-train render OOM)**, not in-progress.

---

## Key log excerpts

Attempt-1 segfaults (`come_tsdf_v0050.log` L1760 / `come_tsdf_v0035.log` L1629):
```
Rendering progress:  86%|████████▋ | 648/750 …  Segmentation fault (core dumped) python come_extract_tsdf_lowmem.py … --voxel_size 0.005 --block_count 250000 …
Rendering progress:  27%|██▋       | 203/750 …  Segmentation fault (core dumped) python come_extract_tsdf_lowmem.py … --voxel_size 0.0035 --block_count 600000 …
```

Attempt-2 res8 (`come_tsdf_v0040.log` L1732 / `come_tsdf_v0060.log` L762,L1749):
```
Rendering progress:  82%|████████▏ | 618/750 …  Segmentation fault (core dumped) … --voxel_size 0.004 --block_resolution 8 --block_count 8000000 …
active_blocks=735967 / cap=4000000 (18.4% of cap)
… 248 Segmentation fault (core dumped) … --voxel_size 0.006 --block_resolution 8 --block_count 4000000 …   (after render 750/750)
```

Attempt-3 CUDA aborts (`come_tsdf_cuda_v0050.log` L762,1698,1700 / `come_tsdf_cuda_v0060.log` L762):
```
active_blocks=1074138 / cap=1500000 (71.6% of cap)
active_blocks=735967  / cap=1000000 (73.6% of cap)
    mesh = vbg.extract_triangle_mesh().to_legacy()
RuntimeError: [Open3D Error] … CUDA runtime error: an illegal memory access was encountered
… Aborted (core dumped) …
```

Attempt-4 legacy SUCCESS (`come_tsdf_legacy_v0050.log` L763,1943-1944 / `_v0070.log` L763,1855-1856):
```
LEGACY ScalableTSDFVolume voxel=0.005 sdf_trunc=0.025 depth_max=6.0 -> …/tsdf_v0050.ply
Mesh Extracted: …/tsdf_v0050.ply  verts=33262302 tris=51476998
TSDF integrate: 100%|██████████| 750/750 [01:11<00:00, 10.55it/s]
EXTRACT_DONE_0050
Mesh Extracted: …/tsdf_v0070.ply  verts=16486381 tris=25656849
TSDF integrate: 100%|██████████| 750/750 [00:50<00:00, 14.78it/s]
EXTRACT_DONE_0070
```

Cleaning (`refine/clean_v0050.log` / `refine/clean_v0070.log`):
```
clusters=1,382,549 biggest=29,011,362 kept=2 (>= 580,227 f) removed 21,124,552/51,476,998 f -> 30,352,446 f
clusters=663,042   biggest=15,086,418 kept=2 (>= 301,728 f) removed 9,748,738/25,656,849 f -> 15,908,111 f
```

ArtiFixer prepare (`artifixer/prepare.log` — train table + crash + terminal marker):
```
│ 10000   │ 14       │ 405.07 s      │ 24.69 it/s      │
… render_3dgrut_colmap … get_gpu_batch_with_intrinsics …
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 78.00 MiB. GPU 0 has a total capacity of 47.39 GiB of which 40.25 MiB is free …
PREPARE_FAILED
```

---

## Confirmation summary (fact sheet vs logs)

**CONFIRMED from logs:**
- All 8 TSDF run configs (backend, voxel, block_res where printed, block_count caps).
- Segfault frames: Attempt-1 648/750 & 203/750; Attempt-2 618/750.
- `active_blocks`: 735,967/4M (18.4%) [A2 v0060]; 1,074,138/1.5M (71.6%) & 735,967/1.0M (73.6%) [A3 CUDA].
- CPU extract segfault vs CUDA extract Abort, both in `extract_triangle_mesh()`.
- Legacy SUCCESS: verts/tris 33,262,302 / 51,476,998 and 16,486,381 / 25,656,849; PLY 2.37 GB / 1.17 GB (decimal); integrate 71 s @10.55 it/s and 50 s @14.78 it/s.
- Cleaning: 51.5M→30.4M f (21.1M=41% removed, 1,382,549 clusters, biggest 29.0M); 25.7M→15.9M f (9.7M=38% removed, 663,042 clusters, biggest 15.1M).
- ArtiFixer split fix: 720 train / 30 val.

**COULD NOT confirm / corrected:**
- **Baseline "voxel 0.015 → 3.2M faces"** — not present in any of the eight assigned logs.
- **"Open3D 0.19"** version — no version string in the logs (the CUDA error path and the bug are confirmed; the "0.19" number is not).
- **ArtiFixer "currently running"** — **CONTRADICTED**: the log shows prepare finished JIT + the 10k recon and then **crashed with CUDA OOM at the render step (`PREPARE_FAILED`)**; it is not in-progress as of this log.
- **"3.2M faces" / "29k blocks at 0.015"** baseline detail — outside this log set, unverifiable here.
- Crash-step label "integrate" for Attempts 1–2 — the bar in those logs reads **"Rendering progress"**, not "integrate" (frame numbers still match).
