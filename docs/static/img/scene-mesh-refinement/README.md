# Scene-Mesh Refinement — QA Render Figures

QA renders from the dreamlab scene-mesh refinement session. The `mesh-qa-*`
figures compare CoMe scene-mesh reconstructions of the motion-blur-limited
dreamlab room capture at three TSDF voxel sizes (0.015 baseline, 0.007, 0.005);
finer voxels resolve sharper detail but reproduce the same partial/lumpy
geometry, because the capture (motion blur, partial coverage) — not mesh
resolution — is the limiting factor. The `fbx-*` figures are the earlier
textured FBX game-asset (UE-ready) built from the 0.015 baseline.

Sources are under `output/dreamlab/locked/` (relative to the LichtFeld-Studio repo root).

| Dest filename | Source | What it shows | Caption |
|---|---|---|---|
| `mesh-qa-baseline-3q.png` | `refine/qa_baseline.png` | CoMe voxel 0.015 baseline mesh, 3/4 view, vertex-colour | Baseline CoMe scene mesh (TSDF voxel 0.015), 3/4 view with vertex colour. |
| `mesh-qa-v0050-3q.png` | `refine/qa_v0050.png` | CoMe voxel 0.005 mesh, 3/4 view | Finer CoMe scene mesh (TSDF voxel 0.005), 3/4 view. |
| `mesh-qa-v0070-3q.png` | `refine/qa_v0070.png` | CoMe voxel 0.007 mesh, 3/4 view | Intermediate CoMe scene mesh (TSDF voxel 0.007), 3/4 view. |
| `mesh-qa-baseline-main.png` | `refine/qa_base_main.png` | Baseline largest connected component, tight frame, 2.57M faces | Baseline mesh (voxel 0.015) largest connected component, tight frame, 2.57M faces. |
| `mesh-qa-v0050-main.png` | `refine/qa_v0050_main.png` | Voxel 0.005 largest connected component, tight frame, 557k faces | Finer mesh (voxel 0.005) largest connected component, tight frame, 557k faces. |
| `fbx-room-3q.png` | `scene_come/qa_room.png` | Baseline textured FBX game-asset, 3/4 view | Baseline (voxel 0.015) textured FBX game-asset, UE-ready, 3/4 view. |
| `fbx-room-top.png` | `scene_come/qa_top.png` | Baseline textured FBX, top-down | Baseline (voxel 0.015) textured FBX game-asset, top-down view. |
| `fbx-room-3q2.png` | `scene_come/qa_3q2.png` | Baseline textured FBX, alternate 3/4 | Baseline (voxel 0.015) textured FBX game-asset, alternate 3/4 view. |
