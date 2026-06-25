"""Vitrine UE 5.8 exhibit startup — GLB-import path (captured colors + robust frame).

UE's USD import drops displayColor (flat white). UE Interchange GLB import reads
vertex colors into the mesh colour channel, so a VertexColor material shows the
captured appearance, and the imported StaticMeshActor has real bounds for framing.
Reads v2g:* from the sidecar USD (pxr) and tags the actor.
"""
import os, math


def _log(m):
    import unreal; unreal.log(f"[exhibit] {m}")


def _eas():
    import unreal
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def import_glb(glb):
    import unreal
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", glb)
    task.set_editor_property("destination_path", "/Game/Vitrine")
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    task.set_editor_property("replace_existing", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = list(task.get_editor_property("imported_object_paths") or [])
    _log(f"GLB import -> {paths[:3]}")
    for p in paths:
        a = unreal.EditorAssetLibrary.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return a
    # fallback: scan the destination folder
    for p in unreal.EditorAssetLibrary.list_assets("/Game/Vitrine", recursive=True):
        a = unreal.EditorAssetLibrary.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return a
    return None


def vc_material():
    import unreal
    p = "/Game/M_Captured"
    if unreal.EditorAssetLibrary.does_asset_exist(p):
        return unreal.EditorAssetLibrary.load_asset(p)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_Captured", "/Game", unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -350, 0)
    mel.connect_material_property(vc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    r = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -350, 220); r.set_editor_property("r", 0.9)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    try: mat.set_editor_property("two_sided", True)
    except Exception: pass
    mel.recompile_material(mat)
    return mat


def cleanup_default_actors():
    import unreal
    eas = _eas()
    KILL = ("SkyAtmosphere", "VolumetricCloud", "ExponentialHeightFog", "AtmosphericFog", "SkyLight", "DirectionalLight")
    KILL_LBL = ("SkySphere", "Sky_Sphere", "Floor", "Sun", "Light Source")
    n = 0
    for a in list(_eas().get_all_level_actors()):
        try: cn = a.get_class().get_name(); lbl = a.get_actor_label()
        except Exception: continue
        if "Vitrine_" in lbl: continue
        if any(k in cn for k in KILL) or any(k in lbl for k in KILL_LBL):
            try: eas.destroy_actor(a); n += 1
            except Exception: pass
    _log(f"removed {n} default outdoor actors")


def lighting():
    import unreal
    eas = _eas()
    try:
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 300)); sky.set_actor_label("Vitrine_Sky")
        c = sky.get_component_by_class(unreal.SkyLightComponent)
        c.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
        c.set_editor_property("real_time_capture", True); c.set_editor_property("intensity", 1.5)
    except Exception as e: _log(f"sky: {e}")
    for z in (1500.0, 100.0, -500.0):
        try:
            pl = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(0, 0, z)); pl.set_actor_label("Vitrine_Fill")
            pc = pl.get_component_by_class(unreal.PointLightComponent)
            pc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
            pc.set_editor_property("intensity", 80000.0); pc.set_editor_property("attenuation_radius", 12000.0)
        except Exception as e: _log(f"fill: {e}")


def tag_v2g(actor, usd):
    import unreal
    try:
        from pxr import Usd
        st = Usd.Stage.Open(usd); tags = list(actor.tags)
        for prim in st.Traverse():
            cd = prim.GetCustomData() or {}
            v = cd.get("v2g")
            if isinstance(v, dict):
                for k, val in v.items():
                    tags.append(unreal.Name(f"v2g:{prim.GetName()}:{k}={val}"))
        actor.set_editor_property("tags", tags)
        _log(f"tagged {len(tags)} v2g")
    except Exception as e: _log(f"v2g: {e}")


def main():
    import unreal
    _log("=== exhibit_startup_glb START ===")
    usd = os.environ.get("VITRINE_USD", "/usd_input/scene.usda")
    glb = os.path.splitext(usd)[0] + ".glb"
    _log(f"glb={glb} exists={os.path.isfile(glb)}")
    sm = import_glb(glb)
    if sm is None:
        _log("no static mesh imported; abort"); return
    eas = _eas()
    actor = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    actor.set_actor_label("Vitrine_Room")
    smc = actor.static_mesh_component
    smc.set_static_mesh(sm)
    # Keep the GLB's own textured material (baseColorTexture) — it renders reliably.
    tag_v2g(actor, usd)
    cleanup_default_actors()
    lighting()
    # frame from the real actor bounds — 3/4 exterior "dollhouse" view (robust for a
    # partial/open room mesh; interior views fall into unfilmed gaps).
    o, e = actor.get_actor_bounds(only_colliding_components=False)
    ext = max(e.x, e.y, e.z)
    loc = unreal.Vector(o.x - ext*0.85, o.y - ext*0.85, o.z + ext*0.45)
    dx, dy, dz = o.x-loc.x, o.y-loc.y, o.z-loc.z
    rot = unreal.Rotator(math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx)), 0)
    _log(f"actor bounds o=({o.x:.0f},{o.y:.0f},{o.z:.0f}) ext={ext:.0f} loc=({loc.x:.0f},{loc.y:.0f},{loc.z:.0f})")
    try:
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(loc, rot)
    except Exception:
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)
    os.makedirs("/renders", exist_ok=True)
    unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, "/renders/exhibit_view.png")
    _log("=== exhibit_startup_glb END ===")


main()
