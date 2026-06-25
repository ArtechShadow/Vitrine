"""Vitrine UE 5.8 exhibit builder — vertex-color material + lighting + framing + shot."""
import os


def _log(m):
    try:
        import unreal; unreal.log(f"[exhibit] {m}")
    except Exception:
        print(f"[exhibit] {m}")


def _eas():
    import unreal
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _all_actors():
    return _eas().get_all_level_actors()


def make_vertex_color_material():
    """Create /Game/M_Captured: VertexColor -> BaseColor, matte, two-sided."""
    import unreal
    try:
        at = unreal.AssetToolsHelpers.get_asset_tools()
        if unreal.EditorAssetLibrary.does_asset_exist("/Game/M_Captured"):
            return unreal.EditorAssetLibrary.load_asset("/Game/M_Captured")
        mat = at.create_asset("M_Captured", "/Game", unreal.Material, unreal.MaterialFactoryNew())
        mel = unreal.MaterialEditingLibrary
        vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -350, 0)
        mel.connect_material_property(vc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -350, 200)
        rough.set_editor_property("r", 0.85)
        mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        try: mat.set_editor_property("two_sided", True)
        except Exception: pass
        mel.recompile_material(mat)
        _log("created M_Captured (vertex-color)")
        return mat
    except Exception as e:
        _log(f"material create failed: {e}")
        return None


def apply_material(mat):
    import unreal
    if mat is None:
        return 0
    n = 0
    for a in _all_actors():
        try:
            comps = a.get_components_by_class(unreal.StaticMeshComponent)
        except Exception:
            comps = []
        for c in comps:
            try:
                for i in range(max(1, c.get_num_materials())):
                    c.set_material(i, mat); n += 1
            except Exception:
                pass
    _log(f"assigned vertex-color material to {n} material slot(s)")
    return n


def cleanup_default_actors():
    """Remove the default outdoor level actors (sky/atmosphere/clouds/fog/floor) —
    they don't belong in an indoor exhibit and poison scene bounds."""
    import unreal
    eas = _eas()
    KILL = ("SkyAtmosphere", "VolumetricCloud", "ExponentialHeightFog",
            "AtmosphericFog", "SkyLight", "DirectionalLight")
    KILL_LBL = ("SkySphere", "Sky_Sphere", "Floor", "Sun", "Light Source")
    n = 0
    for a in list(_all_actors()):
        try:
            cn = a.get_class().get_name(); lbl = a.get_actor_label()
        except Exception:
            continue
        if "Vitrine_" in lbl:
            continue
        if any(k in cn for k in KILL) or any(k in lbl for k in KILL_LBL):
            try:
                eas.destroy_actor(a); n += 1
            except Exception:
                pass
    _log(f"removed {n} default outdoor actor(s)")


def setup_lighting():
    import unreal
    eas = _eas(); spawned = []
    try:
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 300))
        sky.set_actor_label("Vitrine_SkyLight")
        c = sky.get_component_by_class(unreal.SkyLightComponent)
        c.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
        c.set_editor_property("real_time_capture", True); c.set_editor_property("intensity", 2.5)
        spawned.append("SkyLight")
    except Exception as e: _log(f"skylight: {e}")
    try:
        dl = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 400),
                                        unreal.Rotator(-55.0, 35.0, 0.0))
        dl.set_actor_label("Vitrine_KeyLight")
        dl.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("intensity", 2.0)
        spawned.append("DirectionalLight")
    except Exception as e: _log(f"directional: {e}")
    # Interior fill — a closed room blocks the directional sun, so add bright point
    # lights inside (the geometry is recentred so the room straddles the origin).
    try:
        for z in (1200.0, -200.0):
            pl = _eas().spawn_actor_from_class(unreal.PointLight, unreal.Vector(0, 0, z))
            pl.set_actor_label("Vitrine_Fill")
            pc = pl.get_component_by_class(unreal.PointLightComponent)
            pc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
            pc.set_editor_property("intensity", 200000.0)
            pc.set_editor_property("attenuation_radius", 9000.0)
            pc.set_editor_property("source_radius", 200.0)
        spawned.append("PointLightx2")
    except Exception as e: _log(f"pointlight: {e}")
    _log(f"lighting: {spawned}")


def scene_bounds():
    """Union bounds of real geometry actors (exclude tiny lights + huge unbound vols)."""
    import unreal
    bmn = bmx = None
    for a in _all_actors():
        lbl = ""
        try: lbl = a.get_actor_label()
        except Exception: pass
        if "Vitrine_" in lbl:  # skip our lights/PPV
            continue
        try:
            o, e = a.get_actor_bounds(only_colliding_components=False)
        except Exception:
            continue
        try:
            _log(f"  bound-candidate {a.get_class().get_name()} '{lbl}' ext=({e.x:.0f},{e.y:.0f},{e.z:.0f})")
        except Exception:
            pass
        if e.x < 5 or e.x > 8000 or e.y > 8000:
            continue
        lo = unreal.Vector(o.x-e.x, o.y-e.y, o.z-e.z); hi = unreal.Vector(o.x+e.x, o.y+e.y, o.z+e.z)
        if bmn is None: bmn, bmx = lo, hi
        else:
            bmn = unreal.Vector(min(bmn.x,lo.x), min(bmn.y,lo.y), min(bmn.z,lo.z))
            bmx = unreal.Vector(max(bmx.x,hi.x), max(bmx.y,hi.y), max(bmx.z,hi.z))
    return bmn, bmx


def frame_and_shoot(out_path="/renders/exhibit_view.png", w=1920, h=1080):
    import unreal, math
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bmn = bmx = None
    # Primary: the imported environment static-mesh asset bbox (reliable; the
    # UsdStageActor itself reports zero bounds in this World-Partition map).
    try:
        for ap in ("/Game/UsdAssets/SM_Environment", "/Game/UsdAssets/SM_Room", "/Game/UsdAssets/Room"):
            if unreal.EditorAssetLibrary.does_asset_exist(ap):
                sm = unreal.EditorAssetLibrary.load_asset(ap)
                bb = sm.get_bounding_box()
                bmn, bmx = bb.min, bb.max
                _log(f"asset bbox {ap}: min=({bmn.x:.0f},{bmn.y:.0f},{bmn.z:.0f}) max=({bmx.x:.0f},{bmx.y:.0f},{bmx.z:.0f})")
                break
    except Exception as e:
        _log(f"asset bbox failed: {e}")
    if bmn is None:
        bmn, bmx = scene_bounds()
    if bmn is not None:
        # The mesh was recentred so its vertex MEDIAN is the origin -> look at origin
        # (the bbox centre is skewed by asymmetric geometry). Back the camera off by
        # the bbox half-extent so the whole room frames.
        ext = max(bmx.x-bmn.x, bmx.y-bmn.y, bmx.z-bmn.z)
        # INTERIOR camera near the geometry origin (median), looking slightly down;
        # mesh is double-sided so all surfaces render.
        loc = unreal.Vector(-ext*0.18, -ext*0.18, ext*0.06)
        dx, dy, dz = 0.0-loc.x, 0.0-loc.y, 0.0-loc.z
        rot = unreal.Rotator(math.degrees(math.atan2(dz, math.hypot(dx,dy))),
                             math.degrees(math.atan2(dy,dx)), 0.0)
        _log(f"interior view ext={ext:.0f} loc=({loc.x:.0f},{loc.y:.0f},{loc.z:.0f})")
    else:
        loc, rot = unreal.Vector(0,0,150), unreal.Rotator(-10,0,0); _log("no bounds; default view")
    try:
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(loc, rot)
    except Exception:
        try: unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)
        except Exception as e: _log(f"viewport: {e}")
    try:
        unreal.AutomationLibrary.take_high_res_screenshot(w, h, out_path); _log(f"screenshot -> {out_path}")
    except Exception as e: _log(f"screenshot: {e}")


def main():
    _log("=== build_exhibit START ===")
    cleanup_default_actors()
    # Rely on the USD UsdPreviewSurface (reads displayColor primvar) for captured
    # colors rather than overriding with a VertexColor material (which is blank if
    # UE stored colors as a primvar, not the mesh vertex-color channel).
    setup_lighting()
    frame_and_shoot()
    _log("=== build_exhibit END ===")


main()
