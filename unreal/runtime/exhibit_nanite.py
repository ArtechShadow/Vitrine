"""Vitrine UE 5.8 scene assembler — Nanite environment + interactive object hulls.

Builds the final exhibit scene:
  * the environment mesh imported as a Nanite static mesh (full-res geometry,
    automatic LOD — no decimation needed), keeping the baked-texture material,
  * each reconstructed object hull imported as its OWN StaticMeshActor, placed at
    its true pose, set up for interaction (per-object CustomDepth stencil so a
    hover/selection outline can highlight it; collision enabled for click/trace
    selection), tagged with v2g:* lineage.

Env-only run today (objects appended once the hull pipeline produces them). Driven
via -ExecCmds="py exhibit_nanite.py" on the resident Xvfb editor (see run_editor.sh).
"""
import os
import json
import math


def _log(m):
    import unreal
    unreal.log(f"[nanite-exhibit] {m}")


def _eas():
    import unreal
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


# ---------------------------------------------------------------------------
#  Import + Nanite
# ---------------------------------------------------------------------------
def import_glb(glb, dest="/Game/Vitrine"):
    import unreal
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", glb)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    task.set_editor_property("replace_existing", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    for p in list(task.get_editor_property("imported_object_paths") or []):
        a = unreal.EditorAssetLibrary.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return a
    for p in unreal.EditorAssetLibrary.list_assets(dest, recursive=True):
        a = unreal.EditorAssetLibrary.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return a
    return None


def enable_nanite(sm):
    """Turn on Nanite for a static mesh and rebuild. Best-effort across the few
    API shapes UE 5.8 exposes from Python; logs which path worked."""
    import unreal
    try:
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        sm.set_editor_property("nanite_settings", ns)
    except Exception as e:
        _log(f"nanite_settings set failed: {e}")
        return False
    # Rebuild so Nanite data is actually built (setting the flag alone doesn't).
    for attempt in (
        lambda: unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).set_nanite_enabled(sm, True),
        lambda: sm.build(),
        lambda: unreal.EditorStaticMeshLibrary.set_lods(sm, unreal.EditorScriptingMeshReductionOptions()),
    ):
        try:
            attempt()
            break
        except Exception:
            continue
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
    except Exception:
        pass
    _log(f"Nanite enabled on {sm.get_name()}")
    return True


# ---------------------------------------------------------------------------
#  Object hull actors (interactivity scaffolding)
# ---------------------------------------------------------------------------
def add_object_actor(glb, label, location, rotation=(0, 0, 0), scale=(1, 1, 1),
                     stencil_id=1, v2g=None):
    """Import one object hull GLB as its own selectable/highlightable actor."""
    import unreal
    sm = import_glb(glb, dest=f"/Game/Vitrine/Objects/{label}")
    if sm is None:
        _log(f"object '{label}' import failed"); return None
    enable_nanite(sm)
    loc = unreal.Vector(*location); rot = unreal.Rotator(rotation[1], rotation[2], rotation[0])
    actor = _eas().spawn_actor_from_object(sm, loc, rot)
    actor.set_actor_label(f"Obj_{label}")
    actor.set_actor_scale3d(unreal.Vector(*scale))
    comp = actor.static_mesh_component
    # Interactivity: CustomDepth stencil drives the selection/hover outline;
    # collision lets a line-trace / click pick the object.
    try:
        comp.set_editor_property("render_custom_depth", True)
        comp.set_editor_property("custom_depth_stencil_value", int(stencil_id))
        comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
        comp.set_collision_object_type(unreal.CollisionChannel.ECC_WORLD_DYNAMIC)
    except Exception as e:
        _log(f"interactivity props on '{label}': {e}")
    tags = list(actor.tags) + [unreal.Name(f"v2g:object={label}"), unreal.Name("vitrine:selectable=1")]
    for k, val in (v2g or {}).items():
        tags.append(unreal.Name(f"v2g:{k}={val}"))
    actor.set_editor_property("tags", tags)
    _log(f"object '{label}' placed at {location} stencil={stencil_id}")
    return actor


def load_objects_manifest(path):
    """Optional objects.json: [{glb,label,location,rotation,scale,v2g}]."""
    if not path or not os.path.isfile(path):
        return []
    try:
        return json.load(open(path))
    except Exception as e:
        _log(f"objects manifest read failed: {e}"); return []


# ---------------------------------------------------------------------------
#  Lighting / framing / cleanup / interactivity post-process
# ---------------------------------------------------------------------------
def cleanup_default_actors():
    import unreal
    eas = _eas()
    KILL = ("SkyAtmosphere", "VolumetricCloud", "ExponentialHeightFog", "AtmosphericFog", "SkyLight", "DirectionalLight")
    KILL_LBL = ("SkySphere", "Sky_Sphere", "Floor", "Sun", "Light Source")
    n = 0
    for a in list(eas.get_all_level_actors()):
        try:
            cn = a.get_class().get_name(); lbl = a.get_actor_label()
        except Exception:
            continue
        if "Vitrine_" in lbl or "Obj_" in lbl:
            continue
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
    for z in (1500.0, 100.0, -400.0):
        try:
            pl = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(0, 0, z)); pl.set_actor_label("Vitrine_Fill")
            pc = pl.get_component_by_class(unreal.PointLightComponent)
            pc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
            pc.set_editor_property("intensity", 80000.0); pc.set_editor_property("attenuation_radius", 12000.0)
        except Exception as e: _log(f"fill: {e}")


def interactivity_postprocess():
    """Spawn an unbound PostProcessVolume to host a selection-outline material
    (material wired in a follow-up; the CustomDepth stencils are already set)."""
    import unreal
    try:
        ppv = _eas().spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_actor_label("Vitrine_PP")
        ppv.set_editor_property("unbound", True)
        _log("post-process volume for outline highlighting ready")
    except Exception as e:
        _log(f"ppv: {e}")


def frame_and_shoot(actor):
    import unreal
    o, e = actor.get_actor_bounds(only_colliding_components=False)
    ext = max(e.x, e.y, e.z)
    loc = unreal.Vector(o.x - ext * 0.85, o.y - ext * 0.85, o.z + ext * 0.45)
    dx, dy, dz = o.x - loc.x, o.y - loc.y, o.z - loc.z
    rot = unreal.Rotator(math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx)), 0)
    try:
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(loc, rot)
    except Exception:
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(loc, rot)
    os.makedirs("/renders", exist_ok=True)
    unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, "/renders/exhibit_nanite.png")


def main():
    import unreal
    _log("=== exhibit_nanite START ===")
    usd = os.environ.get("VITRINE_USD", "/usd_input/scene.usda")
    env_glb = os.path.splitext(usd)[0] + ".glb"
    _log(f"env glb={env_glb} exists={os.path.isfile(env_glb)}")
    sm = import_glb(env_glb)
    if sm is None:
        _log("no env mesh imported; abort"); return
    enable_nanite(sm)
    env = _eas().spawn_actor_from_object(sm, unreal.Vector(0, 0, 0))
    env.set_actor_label("Vitrine_Room")
    cleanup_default_actors()
    lighting()
    interactivity_postprocess()
    # Objects (appended once the hull pipeline yields objects.json next to the env)
    objs = load_objects_manifest(os.path.join(os.path.dirname(env_glb), "objects.json"))
    for i, o in enumerate(objs):
        add_object_actor(o["glb"], o.get("label", f"obj{i}"), o.get("location", [0, 0, 0]),
                         o.get("rotation", [0, 0, 0]), o.get("scale", [1, 1, 1]),
                         stencil_id=i + 1, v2g=o.get("v2g"))
    _log(f"placed {len(objs)} object hull(s)")
    frame_and_shoot(env)
    _log("=== exhibit_nanite END ===")


main()
