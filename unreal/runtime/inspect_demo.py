"""Vitrine UE 5.8 interactive object-inspector demo.

Per the demo spec:
  * every reconstructed object gets a subtle GREEN highlight (a fresnel rim line),
  * DOUBLE-CLICK an object -> it pops and expands into the centre of shot and
    slowly rotates, with a metadata text panel describing it,
  * DOUBLE-CLICK again -> it eases back to its original (home) transform.

Implementation notes for a headless editor + VNC:
  - Interaction runs through a resident tick callback (register_slate_post_tick_callback).
  - "Double-click" is detected from the editor's actor selection stream: two
    selections of the same Vitrine object within DOUBLE_CLICK_SECS. Selecting in the
    viewport (mouse) is the click; this keeps it driveable over VNC without a packaged
    PlayerController. (A shipping build would move this to a C++/BP PlayerController +
    cursor line-trace; the animation/state machine below is identical either way.)

Objects + metadata come from objects.json (written by the hull pipeline):
  [{ "glb": ".../chair_hull.glb", "label": "chair",
     "location": [x,y,z], "rotation":[p,y,r], "scale":[..],
     "meta": {"gaussians": 56695, "concept_score": 0.98, "source":"dreamlab"} }]
"""
import os
import json
import math

DOUBLE_CLICK_SECS = 0.45
POP_SECS = 0.6          # ease-to-centre / ease-home duration
ROT_DEG_PER_SEC = 25.0  # slow inspection spin
INSPECT_FILL = 0.45     # fraction of view height the object should fill at centre


def _log(m):
    import unreal
    unreal.log(f"[inspect] {m}")


def _eas():
    import unreal
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _ues():
    import unreal
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


# ---------------------------------------------------------------------------
#  Green highlight material (fresnel rim)
# ---------------------------------------------------------------------------
def green_rim_material():
    """/Game/M_GreenRim: object's own texture + an emissive green fresnel rim,
    so every object reads as 'slightly outlined in green'."""
    import unreal
    p = "/Game/M_GreenRim"
    if unreal.EditorAssetLibrary.does_asset_exist(p):
        return unreal.EditorAssetLibrary.load_asset(p)
    at = unreal.AssetToolsHelpers.get_asset_tools()
    mat = at.create_asset("M_GreenRim", "/Game", unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary
    # Fresnel -> green emissive rim
    fres = mel.create_material_expression(mat, unreal.MaterialExpressionFresnel, -500, 200)
    fres.set_editor_property("exponent", 4.0)
    green = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -500, 350)
    green.set_editor_property("constant", unreal.LinearColor(0.1, 1.0, 0.2, 1.0))
    mulrim = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -300, 250)
    mel.connect_material_expressions(fres, "", mulrim, "A")
    mel.connect_material_expressions(green, "", mulrim, "B")
    boost = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -150, 250)
    sc = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 420); sc.set_editor_property("r", 3.0)
    mel.connect_material_expressions(mulrim, "", boost, "A")
    mel.connect_material_expressions(sc, "", boost, "B")
    mel.connect_material_property(boost, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    # Base colour from the imported vertex colour so the object still looks itself.
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -500, 0)
    mel.connect_material_property(vc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    try: mat.set_editor_property("two_sided", True)
    except Exception: pass
    mel.recompile_material(mat)
    _log("created M_GreenRim")
    return mat


# ---------------------------------------------------------------------------
#  Inspect controller (state machine on a tick)
# ---------------------------------------------------------------------------
class Inspect:
    def __init__(self):
        import unreal
        self.objs = {}        # label -> {actor, home_loc, home_rot, radius, meta}
        self.state = "idle"   # idle | popping | inspecting | returning
        self.active = None    # label being inspected
        self.t = 0.0
        self.from_xf = None
        self.to_xf = None
        self.text_actor = None
        self.last_sel = None
        self.last_sel_time = -10.0
        self.clock = 0.0
        self.handle = None

    # -- registration -------------------------------------------------------
    def register(self, actor, label, meta):
        import unreal
        o, e = actor.get_actor_bounds(only_colliding_components=False)
        self.objs[label] = dict(
            actor=actor,
            home_loc=actor.get_actor_location(),
            home_rot=actor.get_actor_rotation(),
            radius=max(e.x, e.y, e.z, 1.0),
            meta=meta or {},
        )
        comp = actor.static_mesh_component
        try:
            comp.set_editor_property("render_custom_depth", True)
            comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
        except Exception:
            pass

    def start(self):
        import unreal
        self.handle = unreal.register_slate_post_tick_callback(self._tick)
        _log(f"inspect controller live ({len(self.objs)} objects) — double-click to inspect")

    # -- per-frame ----------------------------------------------------------
    def _tick(self, dt):
        import unreal
        self.clock += dt
        self._poll_double_click()
        if self.state == "popping":
            self._lerp(dt, nxt="inspecting")
        elif self.state == "inspecting":
            self._spin(dt)
        elif self.state == "returning":
            self._lerp(dt, nxt="idle", clear=True)

    def _poll_double_click(self):
        import unreal
        sel = _eas().get_selected_level_actors()
        if not sel:
            return
        a = sel[0]
        try:
            lbl = a.get_actor_label()
        except Exception:
            return
        label = lbl[4:] if lbl.startswith("Obj_") else None
        if label is None or label not in self.objs:
            return
        # second selection of the same object within the window == double-click
        if self.last_sel == label and (self.clock - self.last_sel_time) < DOUBLE_CLICK_SECS:
            self.last_sel = None
            self._on_double(label)
        else:
            self.last_sel = label
            self.last_sel_time = self.clock

    def _on_double(self, label):
        if self.state in ("popping", "returning"):
            return
        if self.state == "inspecting" and self.active == label:
            self._begin_return()
        elif self.state == "idle":
            self._begin_pop(label)

    # -- transitions --------------------------------------------------------
    def _centre_xf(self, rec):
        import unreal
        cam_loc, cam_rot = _ues().get_level_viewport_camera_info()
        fwd = cam_rot.get_forward_vector()
        # distance so the object fills ~INSPECT_FILL of the view (60deg fov assumption)
        dist = rec["radius"] / max(INSPECT_FILL * math.tan(math.radians(30)), 1e-3)
        loc = unreal.Vector(cam_loc.x + fwd.x * dist, cam_loc.y + fwd.y * dist, cam_loc.z + fwd.z * dist)
        return loc, rec["home_rot"]

    def _begin_pop(self, label):
        rec = self.objs[label]
        self.active = label
        self.from_xf = (rec["actor"].get_actor_location(), rec["actor"].get_actor_rotation())
        self.to_xf = self._centre_xf(rec)
        self.t = 0.0
        self.state = "popping"
        self._spawn_text(rec)
        _log(f"inspect '{label}'")

    def _begin_return(self):
        rec = self.objs[self.active]
        self.from_xf = (rec["actor"].get_actor_location(), rec["actor"].get_actor_rotation())
        self.to_xf = (rec["home_loc"], rec["home_rot"])
        self.t = 0.0
        self.state = "returning"
        self._despawn_text()

    def _lerp(self, dt, nxt, clear=False):
        import unreal
        self.t = min(1.0, self.t + dt / POP_SECS)
        s = self.t * self.t * (3 - 2 * self.t)  # smoothstep
        (fl, fr), (tl, tr) = self.from_xf, self.to_xf
        loc = unreal.Vector(fl.x + (tl.x - fl.x) * s, fl.y + (tl.y - fl.y) * s, fl.z + (tl.z - fl.z) * s)
        self.objs[self.active]["actor"].set_actor_location(loc, False, False)
        if self.t >= 1.0:
            self.state = nxt
            if clear:
                self.active = None

    def _spin(self, dt):
        import unreal
        rec = self.objs[self.active]
        a = rec["actor"]
        r = a.get_actor_rotation()
        a.set_actor_rotation(unreal.Rotator(r.pitch, r.yaw + ROT_DEG_PER_SEC * dt, r.roll), False)

    # -- metadata text ------------------------------------------------------
    def _spawn_text(self, rec):
        import unreal
        loc, _ = self.to_xf
        m = rec["meta"]
        lines = [rec["actor"].get_actor_label().replace("Obj_", "").upper()]
        for k in ("concept_score", "gaussians", "faces", "source"):
            if k in m:
                lines.append(f"{k}: {m[k]}")
        txt = "\n".join(lines)
        tl = unreal.Vector(loc.x, loc.y, loc.z + rec["radius"] * 1.3)
        try:
            self.text_actor = _eas().spawn_actor_from_class(unreal.TextRenderActor, tl)
            self.text_actor.set_actor_label("Vitrine_Meta")
            c = self.text_actor.text_render
            c.set_text(unreal.Text.from_string(txt))
            c.set_text_render_color(unreal.Color(120, 255, 140, 255))
            c.set_world_size(rec["radius"] * 0.18)
            c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
        except Exception as e:
            _log(f"text: {e}")

    def _despawn_text(self):
        if self.text_actor is not None:
            try: _eas().destroy_actor(self.text_actor)
            except Exception: pass
            self.text_actor = None


def main():
    import unreal
    _log("=== inspect_demo START ===")
    rim = green_rim_material()
    insp = Inspect()
    # Attach to every Obj_* actor already in the level (placed by exhibit_nanite).
    meta_path = os.environ.get("VITRINE_OBJECTS_JSON", "/usd_input/objects.json")
    metas = {}
    if os.path.isfile(meta_path):
        for o in json.load(open(meta_path)):
            metas[o["label"]] = o.get("meta", {})
    n = 0
    for a in _eas().get_all_level_actors():
        try:
            lbl = a.get_actor_label()
        except Exception:
            continue
        if not lbl.startswith("Obj_"):
            continue
        label = lbl[4:]
        try:
            for i in range(max(1, a.static_mesh_component.get_num_materials())):
                a.static_mesh_component.set_material(i, rim)
        except Exception:
            pass
        insp.register(a, label, metas.get(label))
        n += 1
    insp.start()
    globals()["_VITRINE_INSPECT"] = insp  # keep alive
    _log(f"=== inspect_demo READY: {n} interactive objects ===")


main()
