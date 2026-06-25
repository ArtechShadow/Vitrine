#!/bin/bash
# When CoMe's mesh is ready: texture it the game-asset way and emit a UE FBX, reusing the
# SAME ue_transform.json M as the objects so room + objects align. CoMe trains its own
# gaussians from the same COLMAP, so its mesh is in the COLMAP world frame (== splat/objects).
# Falls back to the already-textured TSDF room_ue.fbx if the CoMe mesh has no vertex colours.
set -u
GT() { docker exec gaussian-toolkit bash -lc "$1"; }
MESH=$(docker exec come bash -lc 'ls /data/output/dreamlab/model_come/test/ours_*/mesh_*.ply 2>/dev/null | head -1' 2>/dev/null)
[ -z "$MESH" ] && { echo "no CoMe mesh yet ($MESH)"; exit 1; }
echo "CoMe mesh: $MESH"
# both come + gaussian-toolkit mount repo output at /data/output, so gaussian-toolkit sees it.
GT "cp '$MESH' /data/output/dreamlab/scene/room_come.ply; mkdir -p /data/output/dreamlab/scene_come"
# does it carry vertex colours? (bake_from_vertex_colors needs them)
HASCOL=$(GT "cd /opt/gaussian-toolkit && python3 -c \"import trimesh;m=trimesh.load('/data/output/dreamlab/scene/room_come.ply',process=False);print(getattr(m.visual,'kind',None))\" 2>/dev/null")
echo "CoMe mesh vcol kind: $HASCOL"
if echo "$HASCOL" | grep -q vertex; then
  GT "cd /opt/gaussian-toolkit && python3 /tmp/scene_texture.py /data/output/dreamlab/scene/room_come.ply /data/output/dreamlab/scene_come 120000 > /data/output/dreamlab/scene_come_tex.log 2>&1"
  GT "cd /data/output/dreamlab && blender --background --python /tmp/blender_obj_to_fbx.py -- scene_come/room_textured.obj scene/ue_transform.json scene_come/room_come.fbx > /tmp/come_fbx.log 2>&1; grep -h '^FBX' /tmp/come_fbx.log"
  echo "ROOM_FBX=/data/output/dreamlab/scene_come/room_come.fbx (CoMe, textured)"
else
  echo "CoMe mesh has NO vertex colours -> use the TSDF room_ue.fbx (already textured) as the scene mesh."
  echo "ROOM_FBX=/data/output/dreamlab/scene/room_ue.fbx (TSDF fallback)"
fi
