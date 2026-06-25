# UE python: build the dreamlab scene with the ROOM as a LidarPointCloud (fair splat
# appearance; UE has no native 3DGS importer) + the TRELLIS.2 object FBXs. Run on the
# LIVE editor via RC ExecutePythonCommand (exec(open(...).read())) — NOT as a blocking
# startup script. API: LidarPointCloudBlueprintLibrary.create_point_cloud_from_file.
import unreal, os, json

def L(m): unreal.log("[pc] " + str(m))
def W(m): unreal.log_warning("[pc] " + str(m))

PC = "/usd_input/dreamlab/locked/room_pointcloud_ue.ply"
OBJDIR = "/usd_input/dreamlab/assembly_v2/objects_fbx"
PJ = "/usd_input/dreamlab/assembly_v2/placements.json"
FOLDER = "/Game/Vitrine/PC"
REAL = {"chair": 95.0, "vacuum_cleaner": 115.0, "toolbox": 55.0}

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
try:
    les.new_level("/Game/Vitrine/PCScene"); L("new level")
except Exception as e:
    W("new_level " + str(e))

# --- ROOM as LiDAR point cloud ---
try:
    cloud = unreal.LidarPointCloudBlueprintLibrary.create_point_cloud_from_file(PC)
    L("create_point_cloud_from_file -> " + str(cloud) + " pts=" + str(cloud.get_num_points() if cloud else 0))
    a = eas.spawn_actor_from_class(unreal.LidarPointCloudActor, unreal.Vector(0, 0, 0))
    comp = a.get_component_by_class(unreal.LidarPointCloudComponent)
    comp.set_point_cloud(cloud)
    for prop, val in [("point_size", 6.0), ("point_size_bias", 0.0)]:
        try: comp.set_editor_property(prop, val)
        except Exception: pass
    L("room cloud actor spawned")
except Exception as e:
    W("LiDAR FAIL " + str(e))

# --- OBJECTS ---
pl = json.load(open(PJ)) if os.path.exists(PJ) else {}
at = unreal.AssetToolsHelpers.get_asset_tools()
for name, p in pl.items():
    try:
        t = unreal.AssetImportTask()
        t.filename = os.path.join(OBJDIR, name + ".fbx")
        t.destination_path = FOLDER; t.destination_name = "Obj_" + name
        t.automated = True; t.replace_existing = True
        at.import_asset_tasks([t])
        asset = unreal.EditorAssetLibrary.load_asset(FOLDER + "/Obj_" + name)
        loc = p["location_cm"]; zf = p.get("floor_z_cm", 0.0); size = REAL.get(name, 100.0)
        act = eas.spawn_actor_from_object(asset, unreal.Vector(loc[0], loc[1], zf + size / 2.0))
        L("placed " + name + " @ " + str([round(loc[0]), round(loc[1])]))
    except Exception as e:
        W("obj " + name + " " + str(e))

# --- light ---
try:
    s = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 600))
    s.set_actor_rotation(unreal.Rotator(-50, 25, 0), False)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 400))
except Exception as e:
    W("light " + str(e))

L("PC_ASSEMBLE_DONE")
