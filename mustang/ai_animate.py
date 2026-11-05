"""4-Act 3D Cable Assembly & Autonomous Gemini Robotics ER 2.0 Simulation (`mustang/ai_animate.py`).

Generates a 144-frame (24 fps, 1280x720) Cycles Metal GPU animation of the 1:20 1967 Ford Mustang
Fastback Independent AI Edition (`v3.0.0`):
  - Act 1 (f001-f048): Step-by-step 3D AI hardware placement and animated 5-Harness (`H1`-`H5`)
    cable growth (with semi-transparent X-ray tubs and lifted body shell so every internal conduit,
    chimney drop, and 40-pin Radxa Zero 3W GPIO connection is visible).
  - Act 2 (f049-f076): Body shell lowering, Hood/Doors/Trunk inspection of the 289 V8 shroud and
    rear Radxa Zero 3W deck, and sub-surface 1.28" Round GC9A01 HUD boot-up inside Glass_Rear.
  - Act 3 (f077-f108): Forward cruise with OV5647 160-deg fisheye FOV cone and VL53L1X laser beam,
    obstacle detection at <120 mm, <20 ms hardware emergency auto-brake, red GC9A01 ALERT_STOP HUD,
    and bidirectional I2S voice interaction waves (`gemini-robotics-er-2-streaming`).
  - Act 4 (f109-f144): Autonomous S-curve obstacle avoidance (`+15 deg` left steer -> `-15 deg`
    right steer -> straight cruise) with coupled 7T:9T drivetrain/wheel rotation and HAPPY HUD.
"""
import math
import os
import subprocess
import sys

try:
    import bmesh
    import bpy
    from mathutils import Euler, Matrix, Vector

    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    import ai_edition
    import body
    import doors
    import engine_bay
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

FPS = 24
END = 144
K = (1.0 / 20.0) / (1.0 / 24.0) if not IN_BLENDER else body.SCALE / (1.0 / 24.0)
SHOWCASE = "AI_Showcase"
BUILD_COLLECTIONS = ("Body", "Wheels", "Parts", "Accessories")


def _collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _layer_collection(name, lc=None):
    lc = lc or bpy.context.view_layer.layer_collection
    if lc.collection.name == name:
        return lc
    for child in lc.children:
        found = _layer_collection(name, child)
        if found:
            return found
    return None


def _make_mat(name, rgba, metallic=0.1, roughness=0.35, emission_rgba=None, emission_strength=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission_rgba is not None and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_rgba
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def _box_mesh(name, size, loc=(0, 0, 0), rot_deg=(0, 0, 0), mat=None, col=None, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
    if mat:
        me.materials.append(mat)
    if col:
        col.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def _cyl_mesh(name, radius, depth, loc=(0, 0, 0), rot_deg=(0, 0, 0), mat=None, col=None, parent=None, segs=32):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius, radius2=radius, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
    if mat:
        me.materials.append(mat)
    if col:
        col.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def _cone_mesh(name, r1, r2, depth, loc=(0, 0, 0), rot_deg=(0, 0, 0), mat=None, col=None, parent=None, segs=32):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r1, radius2=r2, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], 'XYZ')
    if mat:
        me.materials.append(mat)
    if col:
        col.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def _cable_curve(name, pts, radius=0.55, mat=None, col=None, parent=None, ribbon_width=0.0):
    """Create a 3D curve tube (or flat FPC ribbon if ribbon_width > 0) with animatable bevel_factor_end."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = 12
    cu.bevel_depth = radius
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    if ribbon_width > 0.0:
        cu.extrude = ribbon_width * 0.5
        cu.bevel_depth = 0.18
    spline = cu.splines.new('POLY')
    spline.points.add(len(pts) - 1)
    for i, (x, y, z) in enumerate(pts):
        spline.points[i].co = (x, y, z, 1.0)
    ob = bpy.data.objects.new(name, cu)
    if mat:
        cu.materials.append(mat)
    if col:
        col.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def _key_fly_in(ob, start_offset, f_start, f_land):
    """Key an object hidden until f_start, then smoothly flying in from start_offset to rest pose at f_land."""
    rest = ob.location.copy()
    ob.animation_data_clear()
    if f_start > 1:
        ob.hide_viewport = ob.hide_render = True
        ob.keyframe_insert("hide_viewport", frame=1)
        ob.keyframe_insert("hide_render", frame=1)
        ob.keyframe_insert("hide_viewport", frame=f_start - 1)
        ob.keyframe_insert("hide_render", frame=f_start - 1)
    ob.hide_viewport = ob.hide_render = False
    ob.keyframe_insert("hide_viewport", frame=f_start)
    ob.keyframe_insert("hide_render", frame=f_start)

    ob.location = rest + Vector(start_offset)
    ob.keyframe_insert("location", frame=f_start)
    ob.location = rest
    ob.keyframe_insert("location", frame=f_land)


def _key_cable_growth(ob, f_start, f_done):
    """Animate a cable curve growing from 0.0 to 1.0 along its path between f_start and f_done."""
    cu = ob.data
    cu.animation_data_clear()
    ob.animation_data_clear()
    if f_start > 1:
        ob.hide_viewport = ob.hide_render = True
        ob.keyframe_insert("hide_viewport", frame=1)
        ob.keyframe_insert("hide_render", frame=1)
        ob.keyframe_insert("hide_viewport", frame=f_start - 1)
        ob.keyframe_insert("hide_render", frame=f_start - 1)
    ob.hide_viewport = ob.hide_render = False
    ob.keyframe_insert("hide_viewport", frame=f_start)
    ob.keyframe_insert("hide_render", frame=f_start)

    cu.bevel_factor_end = 0.0
    cu.keyframe_insert("bevel_factor_end", frame=f_start)
    cu.bevel_factor_end = 1.0
    cu.keyframe_insert("bevel_factor_end", frame=f_done)


def _key_vis_window(ob, windows):
    """Show `ob` only inside [(f_on, f_off), ...] frame intervals."""
    ob.animation_data_clear()
    ob.hide_viewport = ob.hide_render = True
    ob.keyframe_insert("hide_viewport", frame=1)
    ob.keyframe_insert("hide_render", frame=1)
    for f0, f1 in windows:
        ob.hide_viewport = ob.hide_render = False
        ob.keyframe_insert("hide_viewport", frame=f0)
        ob.keyframe_insert("hide_render", frame=f0)
        ob.hide_viewport = ob.hide_render = True
        ob.keyframe_insert("hide_viewport", frame=f1)
        ob.keyframe_insert("hide_render", frame=f1)


def _camera_point(elev, azim, dist, target):
    e, a = math.radians(elev), math.radians(azim)
    d = Vector((-math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    return Vector(target) + d * dist


def setup_ai_simulation():
    """Bake the 69 AI Edition parts + 9 AI hardware modules + 5 animated cable harnesses (`H1`-`H5`)
    + perception/HUD VFX and keyframe the 144-frame 4-Act simulation."""
    if "WaymoPod" not in bpy.data.objects:
        if os.path.exists(ai_edition.AI_BLEND_PATH):
            bpy.ops.wm.open_mainfile(filepath=ai_edition.AI_BLEND_PATH)
        else:
            ai_edition.build_and_export(save_blend=True)

    scene = bpy.context.scene
    col = _collection(SHOWCASE)
    for ob in list(col.objects):
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me and me.users == 0:
            if isinstance(me, bpy.types.Mesh):
                bpy.data.meshes.remove(me)
            elif isinstance(me, bpy.types.Curve):
                bpy.data.curves.remove(me)

    for name in BUILD_COLLECTIONS:
        lc = _layer_collection(name)
        if lc:
            lc.hide_viewport = False
        bpy.data.collections[name].hide_viewport = False

    bpy.data.objects["Hood"].rotation_euler = (0, 0, 0)
    if "TrunkLid" in bpy.data.objects:
        bpy.data.objects["TrunkLid"].rotation_euler = (0, 0, 0)
    for side in doors.SIDES:
        bpy.data.objects[f"Door_{doors.tag(side)}"].rotation_euler = (0, 0, 0)
        kn = bpy.data.objects.get(f"Knuckle_{doors.tag(side)}")
        if kn is not None:
            kn.rotation_euler = (0, 0, 0)

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    root = bpy.data.objects.new("SC_Root", None)
    col.objects.link(root)

    copies = {}
    for name in BUILD_COLLECTIONS:
        for src in bpy.data.collections[name].objects:
            if src.type != 'MESH' or (name == "Accessories" and src.name != "HoodProp"):
                continue
            me = bpy.data.meshes.new_from_object(src.evaluated_get(dg))
            me.name = f"SC_{src.name}"
            ob = bpy.data.objects.new(f"SC_{src.name}", me)
            ob.matrix_world = src.matrix_world.copy()
            col.objects.link(ob)
            for poly in me.polygons:
                poly.use_smooth = True
            copies[src.name] = ob

    for name in BUILD_COLLECTIONS:
        _layer_collection(name).hide_viewport = True
        bpy.data.collections[name].hide_viewport = True
        bpy.data.collections[name].hide_render = True
    bpy.data.collections["Cutters"].hide_viewport = True
    bpy.data.collections["Cutters"].hide_render = True
    _layer_collection(SHOWCASE).hide_viewport = False
    col.hide_viewport = False
    col.hide_render = False

    ng = bpy.data.node_groups.get("Smooth by Angle")
    for ob in copies.values():
        if ng is not None:
            mod = ob.modifiers.get("Smooth by Angle") or ob.modifiers.new("Smooth by Angle", 'NODES')
            mod.node_group = ng
            try:
                mod["Input_1"] = math.radians(35)
            except Exception:
                pass

    # Center origins on rotating wheels, rear axle, and SteeringLink so rotations/shifts occur around part centers
    for w_name in (
        "Rim_FL", "Tire_FL", "Rim_FR", "Tire_FR",
        "Rim_RL", "Tire_RL", "Rim_RR", "Tire_RR",
        "Axle_R", "AxleGear", "SteeringLink",
    ):
        if w_name in copies and copies[w_name].data.vertices:
            w_ob = copies[w_name]
            verts = [v.co for v in w_ob.data.vertices]
            cx = 0.5 * (min(v.x for v in verts) + max(v.x for v in verts))
            cy = 0.5 * (min(v.y for v in verts) + max(v.y for v in verts))
            cz = 0.5 * (min(v.z for v in verts) + max(v.z for v in verts))
            center = Vector((cx, cy, cz))
            w_ob.data.transform(Matrix.Translation(-center))
            w_ob.location = Vector(w_ob.location) + (w_ob.matrix_world.to_3x3() @ center)

    bpy.context.view_layer.update()

    # Parent riders (Doors, Knuckles, Upper Shell Group) and link all top-level car parts to SC_Root
    upper_body_parts = (
        "Body", "Glass_Windshield", "Glass_Rear", "Hood", "TrunkLid",
        "Door_L", "Door_R", "Bumper_F", "Bumper_R", "Grille", "GrilleSurround",
        "Corral", "Headlight_L", "Headlight_R", "Fog_L", "Fog_R", "ParkLight_L", "ParkLight_R",
        "TaillightBezel_L0", "TaillightBezel_L1", "TaillightBezel_L2",
        "TaillightBezel_R0", "TaillightBezel_R1", "TaillightBezel_R2",
        "TaillightLens_L0", "TaillightLens_L1", "TaillightLens_L2",
        "TaillightLens_R0", "TaillightLens_R1", "TaillightLens_R2",
        "BackupLight_L", "BackupLight_R", "GasCap", "Brace", "SteeringWheel",
    )
    upper_group = bpy.data.objects.new("SC_UpperBodyGroup", None)
    col.objects.link(upper_group)
    upper_group.parent = root
    bpy.context.view_layer.update()

    for side in doors.SIDES:
        t = doors.tag(side)
        door = copies[f"Door_{t}"]
        for rider in [copies[n] for n in (f"DoorCard_{t}", f"DoorVent_{t}", f"Mirror_{t}") if n in copies]:
            m = rider.matrix_world.copy()
            rider.parent = door
            rider.matrix_parent_inverse = door.matrix_world.inverted()
            rider.matrix_world = m
        kn = copies[f"Knuckle_{t}"]
        w_tag = "FL" if side < 0 else "FR"
        for rider in [copies[n] for n in (f"Rim_{w_tag}", f"Tire_{w_tag}") if n in copies]:
            m = rider.matrix_world.copy()
            rider.parent = kn
            rider.matrix_parent_inverse = kn.matrix_world.inverted()
            rider.matrix_world = m

    # Group EngineBlock + ValveCovers + AirCleaner
    eng_block = copies["EngineBlock"]
    for n in ("ValveCover_L", "ValveCover_R", "AirCleaner"):
        if n in copies:
            m = copies[n].matrix_world.copy()
            copies[n].parent = eng_block
            copies[n].matrix_parent_inverse = eng_block.matrix_world.inverted()
            copies[n].matrix_world = m

    for name, ob in copies.items():
        if ob.parent is not None:
            continue
        target_parent = upper_group if name in upper_body_parts else root
        m = ob.matrix_world.copy()
        ob.parent = target_parent
        ob.matrix_parent_inverse = target_parent.matrix_world.inverted()
        ob.matrix_world = m

    bpy.context.view_layer.update()

    # Make InteriorTub and BayTub slightly translucent dark gunmetal during Act 1 so the under-floor
    # H4 cable conduit growth is clearly visible from above, while still looking solid inside the cabin!
    mat_tub_xray = _make_mat("AI_TubCutaway", (0.09, 0.10, 0.12, 1.0), metallic=0.2, roughness=0.4, alpha=0.52)
    for tub_name in ("InteriorTub", "BayTub", "BootTub"):
        if tub_name in copies:
            copies[tub_name].data.materials.clear()
            copies[tub_name].data.materials.append(mat_tub_xray)

    # Create Distinct High-Contrast Materials for the 9 AI Modules & 5 Cable Harnesses
    m_radxa = _make_mat("AI_Mat_RadxaPCB", (0.04, 0.52, 0.22, 1.0), metallic=0.25, roughness=0.3)
    m_gold = _make_mat("AI_Mat_GoldPin", (0.95, 0.76, 0.18, 1.0), metallic=0.9, roughness=0.2)
    m_chip = _make_mat("AI_Mat_Chip", (0.08, 0.08, 0.10, 1.0), metallic=0.3, roughness=0.25)
    m_motor = _make_mat("AI_Mat_N25Brass", (0.88, 0.66, 0.18, 1.0), metallic=0.85, roughness=0.25)
    m_servo = _make_mat("AI_Mat_ServoCyan", (0.08, 0.58, 0.88, 1.0), metallic=0.2, roughness=0.3)
    m_tof = _make_mat("AI_Mat_ToFPurple", (0.55, 0.16, 0.85, 1.0), metallic=0.3, roughness=0.3)
    m_lipo = _make_mat("AI_Mat_LiPoRed", (0.85, 0.12, 0.15, 1.0), metallic=0.2, roughness=0.35)
    m_bec = _make_mat("AI_Mat_BECAmber", (0.95, 0.52, 0.06, 1.0), metallic=0.3, roughness=0.3)
    m_spk = _make_mat("AI_Mat_SpkTeal", (0.05, 0.72, 0.68, 1.0), metallic=0.35, roughness=0.3)
    m_amp = _make_mat("AI_Mat_AmpMagenta", (0.85, 0.15, 0.58, 1.0), metallic=0.25, roughness=0.3)
    m_drv = _make_mat("AI_Mat_DrvBlue", (0.14, 0.32, 0.90, 1.0), metallic=0.25, roughness=0.3)

    # Emissive Cable Materials so every wire harness pops vividly in 3D renders
    m_cab_h1_fpc = _make_mat("AI_Cab_H1_FPC", (1.0, 0.55, 0.08, 1.0), roughness=0.25,
                             emission_rgba=(1.0, 0.55, 0.08, 1.0), emission_strength=1.6)
    m_cab_h1_mic = _make_mat("AI_Cab_H1_Mic", (0.15, 0.95, 0.45, 1.0), roughness=0.25,
                             emission_rgba=(0.15, 0.95, 0.45, 1.0), emission_strength=1.8)
    m_cab_h2_hud = _make_mat("AI_Cab_H2_HUD", (0.05, 0.88, 1.0, 1.0), roughness=0.2,
                             emission_rgba=(0.05, 0.88, 1.0, 1.0), emission_strength=2.2)
    m_cab_h3_aud = _make_mat("AI_Cab_H3_Aud", (0.95, 0.22, 0.75, 1.0), roughness=0.25,
                             emission_rgba=(0.95, 0.22, 0.75, 1.0), emission_strength=1.8)
    m_cab_h3_spk = _make_mat("AI_Cab_H3_Spk", (0.10, 0.92, 0.82, 1.0), roughness=0.25,
                             emission_rgba=(0.10, 0.92, 0.82, 1.0), emission_strength=1.8)
    m_cab_h4_mot = _make_mat("AI_Cab_H4_Mot", (1.0, 0.22, 0.12, 1.0), roughness=0.25,
                             emission_rgba=(1.0, 0.22, 0.12, 1.0), emission_strength=2.0)
    m_cab_h4_srv = _make_mat("AI_Cab_H4_Srv", (1.0, 0.68, 0.08, 1.0), roughness=0.25,
                             emission_rgba=(1.0, 0.68, 0.08, 1.0), emission_strength=1.8)
    m_cab_h4_tof = _make_mat("AI_Cab_H4_ToF", (0.35, 0.55, 1.0, 1.0), roughness=0.25,
                             emission_rgba=(0.35, 0.55, 1.0, 1.0), emission_strength=2.0)
    m_cab_h5_pwr = _make_mat("AI_Cab_H5_Pwr", (1.0, 0.12, 0.18, 1.0), roughness=0.2,
                             emission_rgba=(1.0, 0.12, 0.18, 1.0), emission_strength=2.2)

    # Emissive HUD & Perception VFX Materials
    m_hud_bg = _make_mat("AI_HUD_ScreenBG", (0.02, 0.04, 0.08, 1.0), metallic=0.1, roughness=0.1)
    m_hud_cyan = _make_mat("AI_HUD_CyanGlow", (0.05, 0.92, 1.0, 1.0),
                           emission_rgba=(0.05, 0.92, 1.0, 1.0), emission_strength=6.5)
    m_hud_red = _make_mat("AI_HUD_RedAlert", (1.0, 0.12, 0.08, 1.0),
                          emission_rgba=(1.0, 0.12, 0.08, 1.0), emission_strength=8.0)
    m_fov_cone = _make_mat("AI_VFX_FOVMat", (0.05, 0.85, 1.0, 1.0), roughness=0.2,
                           emission_rgba=(0.05, 0.85, 1.0, 1.0), emission_strength=1.8, alpha=0.18)
    m_tof_green = _make_mat("AI_VFX_ToFGreen", (0.10, 1.0, 0.35, 1.0), roughness=0.2,
                            emission_rgba=(0.10, 1.0, 0.35, 1.0), emission_strength=4.5, alpha=0.55)
    m_tof_red = _make_mat("AI_VFX_ToFRed", (1.0, 0.08, 0.08, 1.0), roughness=0.2,
                          emission_rgba=(1.0, 0.08, 0.08, 1.0), emission_strength=7.5, alpha=0.75)

    # -------------------------------------------------------------------------
    # BUILD THE 9 COLOUR-CODED 3D AI HARDWARE MODULES
    # -------------------------------------------------------------------------
    # Wave 1 Hardware: Front VL53L1X ToF, 1.7g Servo, N25 Motor
    mod_tof = _box_mesh("AI_Mod_VL53L1X", (2.6, 15.0, 4.8), (35.2, 0.0, 24.5), mat=m_tof, col=col, parent=root)
    mod_servo = _box_mesh("AI_Mod_Servo1p7g", (6.5, 13.5, 10.0), (30.5, 0.0, 22.5), mat=m_servo, col=col, parent=root)
    mod_n25 = _box_mesh("AI_Mod_N25Motor", (21.0, 11.0, 9.5), (58.2, 0.0, 19.75), mat=m_motor, col=col, parent=root)

    # Wave 2 Hardware: Lower Trunk 2S LiPo + 5V 3A BEC + Cabin Speaker + MAX98357A + DRV8833
    mod_lipo = _box_mesh("AI_Mod_LiPo2S", (14.5, 14.0, 5.2), (209.2, 5.8, 32.6), mat=m_lipo, col=col, parent=root)
    mod_bec = _box_mesh("AI_Mod_BEC5V", (14.0, 9.5, 4.0), (209.2, -7.8, 32.4), mat=m_bec, col=col, parent=root)
    mod_spk = _box_mesh("AI_Mod_Speaker1524", (14.8, 24.0, 4.2), (162.4, 10.0, 30.8), mat=m_spk, col=col, parent=root)
    mod_amp = _box_mesh("AI_Mod_MAX98357A", (13.5, 7.2, 3.6), (162.4, -12.5, 30.6), mat=m_amp, col=col, parent=root)
    mod_drv = _box_mesh("AI_Mod_DRV8833", (13.5, 7.2, 3.6), (162.4, -20.5, 30.6), mat=m_drv, col=col, parent=root)

    # Wave 3 Hardware: Radxa Zero 3W (65 x 30 x 5.2 mm) + Gold 40-pin GPIO Header + RK3566 SoC + CSI Socket
    mod_radxa = _box_mesh("AI_Mod_RadxaZero3W", (65.0, 30.0, 1.8), (183.5, 0.0, 37.2), mat=m_radxa, col=col, parent=root)
    _box_mesh("AI_Mod_RadxaGPIO", (50.8, 5.0, 2.8), (-5.5, -11.8, 2.3), mat=m_gold, col=col, parent=mod_radxa)
    _box_mesh("AI_Mod_RadxaSoC", (14.0, 14.0, 1.6), (-1.5, 1.5, 1.6), mat=m_chip, col=col, parent=mod_radxa)
    _box_mesh("AI_Mod_RadxaCSI", (3.2, 12.5, 2.2), (-30.3, 0.0, 1.7), mat=m_gold, col=col, parent=mod_radxa)

    # Wave 4 Hardware: Sub-Surface 1.28" Round GC9A01 HUD + Animated Eyes/Alerts & OV5647 + INMP441 in WaymoPod
    mod_hud = _cyl_mesh("AI_Mod_GC9A01Screen", 13.5, 1.2, (176.5, 0.0, 55.65), (0.0, 20.5, 0.0),
                        mat=m_hud_bg, col=col, parent=root, segs=48)
    _cyl_mesh("AI_HUD_CyanRing", 12.8, 1.35, (0.0, 0.0, 0.15), (0.0, 0.0, 0.0),
              mat=m_hud_cyan, col=col, parent=mod_hud, segs=48)
    hud_eye_l = _cyl_mesh("AI_HUD_EyeL", 3.2, 1.55, (-1.2, -4.6, 0.35), (0.0, 0.0, 0.0),
                          mat=m_hud_cyan, col=col, parent=mod_hud, segs=24)
    hud_eye_r = _cyl_mesh("AI_HUD_EyeR", 3.2, 1.55, (-1.2, 4.6, 0.35), (0.0, 0.0, 0.0),
                          mat=m_hud_cyan, col=col, parent=mod_hud, segs=24)
    hud_alert_red = _cyl_mesh("AI_HUD_AlertRed", 13.0, 1.65, (0.0, 0.0, 0.25), (0.0, 0.0, 0.0),
                              mat=m_hud_red, col=col, parent=mod_hud, segs=48)

    mod_cam = _cyl_mesh("AI_Mod_OV5647Lens", 4.2, 6.0, (115.2, 0.0, 65.8), (0.0, -81.0, 0.0),
                        mat=m_hud_cyan, col=col, parent=root, segs=32)
    mod_mic = _cyl_mesh("AI_Mod_INMP441Mic", 4.4, 1.4, (125.0, 0.0, 68.4), (0.0, 0.0, 0.0),
                        mat=m_gold, col=col, parent=root, segs=32)

    # -------------------------------------------------------------------------
    # BUILD THE 5 ANIMATED 3D CABLE HARNESSES (H1-H5)
    # -------------------------------------------------------------------------
    # Harness H4: Under-Floor Driver-Side Conduit (Y = -5.8 mm, Z = 18.0 mm)
    cab_h4_mot = _cable_curve(
        "AI_Cab_H4_Motor",
        [(58.2, -3.5, 19.8), (66.0, -5.2, 18.2), (105.0, -5.2, 18.2), (144.0, -5.2, 18.2),
         (156.0, -14.0, 29.5), (162.4, -20.5, 31.5)],
        radius=0.62, mat=m_cab_h4_mot, col=col, parent=root,
    )
    cab_h4_srv = _cable_curve(
        "AI_Cab_H4_Servo",
        [(30.5, -3.8, 22.0), (48.0, -6.0, 18.5), (105.0, -6.0, 18.5), (146.0, -6.0, 18.5),
         (156.0, -11.8, 39.8), (163.0, -11.8, 40.5)],
        radius=0.52, mat=m_cab_h4_srv, col=col, parent=root,
    )
    cab_h4_tof = _cable_curve(
        "AI_Cab_H4_ToF",
        [(35.2, -4.5, 24.5), (48.0, -6.8, 19.0), (105.0, -6.8, 19.0), (147.0, -6.8, 19.0),
         (155.0, -12.5, 40.2), (160.0, -12.5, 40.8)],
        radius=0.55, mat=m_cab_h4_tof, col=col, parent=root,
    )

    # Harness H5: Lower Trunk 2S LiPo + 5V 3A BEC Power Distribution
    cab_h5_pwr = _cable_curve(
        "AI_Cab_H5_Power",
        [(209.2, 5.8, 33.5), (209.2, -7.8, 33.5), (195.0, -13.5, 35.0),
         (162.4, -20.5, 32.0), (160.0, -11.2, 40.8)],
        radius=0.72, mat=m_cab_h5_pwr, col=col, parent=root,
    )

    # Harness H3: Rear Cabin Deck Audio (MAX98357A + 1524 Speaker) & DRV8833 Logic
    cab_h3_aud = _cable_curve(
        "AI_Cab_H3_AudioDrv",
        [(162.4, -16.5, 32.0), (165.0, -14.0, 38.5), (175.0, -11.8, 40.8), (195.0, -11.8, 40.8)],
        radius=0.60, mat=m_cab_h3_aud, col=col, parent=root,
    )
    cab_h3_spk = _cable_curve(
        "AI_Cab_H3_SpeakerPair",
        [(162.4, -12.5, 31.8), (156.0, -2.0, 32.2), (162.4, 10.0, 32.2)],
        radius=0.58, mat=m_cab_h3_spk, col=col, parent=root,
    )

    # Harness H2: Sub-Surface 1.28" Round GC9A01 HUD (<12 mm direct drop to Radxa SPI3 pins)
    cab_h2_hud = _cable_curve(
        "AI_Cab_H2_HUD",
        [(176.5, -2.5, 54.8), (175.0, -8.5, 47.0), (174.0, -11.8, 40.8)],
        radius=0.65, mat=m_cab_h2_hud, col=col, parent=root,
    )

    # Harness H1: Roof WaymoPod (OV5647 15-to-22-pin CSI Ribbon + INMP441 I2S Mic) down Cut_WaymoChimney
    cab_h1_fpc = _cable_curve(
        "AI_Cab_H1_CSIRibbon",
        [(118.5, 0.0, 65.5), (132.0, 0.0, 65.2), (143.4, 0.0, 64.0),
         (143.4, 0.0, 44.0), (153.2, 0.0, 39.5)],
        radius=0.25, mat=m_cab_h1_fpc, col=col, parent=root, ribbon_width=8.5,
    )
    cab_h1_mic = _cable_curve(
        "AI_Cab_H1_MicI2S",
        [(125.0, -2.5, 67.8), (142.8, -5.5, 64.0), (142.8, -8.5, 44.0),
         (168.0, -11.8, 40.8), (192.0, -11.8, 40.8)],
        radius=0.55, mat=m_cab_h1_mic, col=col, parent=root,
    )

    # -------------------------------------------------------------------------
    # BUILD PERCEPTION & VOICE VFX (ACT 3 & ACT 4) + TEST TRACK OBSTACLE
    # -------------------------------------------------------------------------
    vfx_fov = _cone_mesh("AI_VFX_FisheyeFOV", 1.2, 15.0, 76.0, (74.0, 0.0, 62.5), (0.0, -83.0, 0.0),
                         mat=m_fov_cone, col=col, parent=root, segs=32)
    vfx_tof_g = _cone_mesh("AI_VFX_ToFGreenBeam", 0.8, 9.0, 75.0, (-25.5, 0.0, 20.0), (0.0, -90.0, 0.0),
                           mat=m_tof_green, col=col, parent=root, segs=24)
    vfx_tof_r = _cone_mesh("AI_VFX_ToFRedBeam", 1.2, 12.0, 48.0, (-12.0, 0.0, 20.0), (0.0, -90.0, 0.0),
                           mat=m_tof_red, col=col, parent=root, segs=24)
    vfx_wave1 = _cyl_mesh("AI_VFX_VoiceWave1", 11.0, 0.6, (125.0, 0.0, 71.5), (0.0, 0.0, 0.0),
                          mat=m_hud_cyan, col=col, parent=root, segs=36)
    vfx_wave2 = _cyl_mesh("AI_VFX_VoiceWave2", 18.0, 0.5, (125.0, 0.0, 74.5), (0.0, 0.0, 0.0),
                          mat=m_cab_h1_fpc, col=col, parent=root, segs=36)

    # Scale Road Obstacle Cone placed ahead of the car at X = -92 mm, Y = 0 mm
    obs_cone = _cone_mesh("AI_Track_Obstacle", 14.0, 2.5, 28.0, (-92.0, 0.0, 14.0), (0.0, 0.0, 0.0),
                          mat=m_lipo, col=col, parent=None, segs=32)
    obs_stripe = _cone_mesh("AI_Track_ObstacleStripe", 9.2, 5.2, 9.0, (0.0, 0.0, 2.5), (0.0, 0.0, 0.0),
                            mat=_make_mat("AI_WhiteStripe", (0.96, 0.96, 0.98, 1.0), roughness=0.2),
                            col=col, parent=obs_cone, segs=32)

    # -------------------------------------------------------------------------
    # KEYFRAME ACT 1 (f001-f048): HARDWARE FLY-IN & 5-HARNESS CABLE GROWTH
    # -------------------------------------------------------------------------
    # Lift SC_UpperBodyGroup +88 mm in Z during Act 1 (f001-f044) so the entire interior/trunk/engine
    # bay and all 5 cable harnesses are 100% unobstructed, then lower smoothly onto the chassis by f054!
    upper_group.animation_data_clear()
    upper_group.location = (0.0, 0.0, 115.0)
    upper_group.keyframe_insert("location", frame=1)
    upper_group.keyframe_insert("location", frame=42)
    upper_group.location = (0.0, 0.0, 0.0)
    upper_group.keyframe_insert("location", frame=54)

    # Hide EngineBlock during Act 1 so N25 motor + H4 conduit are exposed, then drop EngineBlock at f044-f054
    _key_fly_in(eng_block, (0.0, 0.0, 65.0), 44, 54)

    # Wave 1 (f001-f012): Front VL53L1X ToF, 1.7g Servo, N25 Motor + Harness H4 (Under-Floor Conduit)
    _key_fly_in(mod_tof, (-18.0, 0.0, 28.0), 1, 6)
    _key_fly_in(mod_servo, (0.0, 0.0, 32.0), 2, 7)
    _key_fly_in(mod_n25, (0.0, 0.0, 35.0), 3, 8)
    _key_cable_growth(cab_h4_mot, 6, 14)
    _key_cable_growth(cab_h4_srv, 7, 15)
    _key_cable_growth(cab_h4_tof, 8, 16)

    # Wave 2 (f013-f024): Lower Trunk 2S LiPo + 5V BEC (H5) + Speaker & MAX98357A/DRV8833 (H3-B)
    _key_fly_in(mod_lipo, (0.0, 0.0, 36.0), 13, 18)
    _key_fly_in(mod_bec, (0.0, 0.0, 36.0), 14, 19)
    _key_fly_in(mod_spk, (0.0, 18.0, 32.0), 15, 20)
    _key_fly_in(mod_amp, (0.0, -18.0, 32.0), 16, 21)
    _key_fly_in(mod_drv, (0.0, -18.0, 32.0), 16, 21)
    _key_cable_growth(cab_h5_pwr, 18, 24)
    _key_cable_growth(cab_h3_spk, 19, 25)

    # Wave 3 (f023-f034): Radxa Zero 3W slides horizontally (-X, -Z) into the 3-Zone Stepped L-Rail Cradle + H3-A/C
    _key_fly_in(mod_radxa, (42.0, 0.0, 22.0), 23, 30)
    _key_cable_growth(cab_h3_aud, 28, 34)

    # Wave 4 (f033-f046): Sub-Surface 1.28" Round GC9A01 HUD (H2) + WaymoPod OV5647 & INMP441 Chimney Drop (H1)
    _key_fly_in(mod_hud, (0.0, 0.0, 28.0), 33, 38)
    _key_cable_growth(cab_h2_hud, 36, 41)
    _key_fly_in(mod_cam, (0.0, 0.0, 32.0), 36, 41)
    _key_fly_in(mod_mic, (0.0, 0.0, 32.0), 36, 41)
    if "WaymoPod" in copies:
        _key_fly_in(copies["WaymoPod"], (0.0, 0.0, 38.0), 37, 43)
    if "GC9A01Bezel" in copies:
        _key_fly_in(copies["GC9A01Bezel"], (18.0, 0.0, 18.0), 35, 41)
    _key_cable_growth(cab_h1_fpc, 39, 46)
    _key_cable_growth(cab_h1_mic, 40, 47)

    # -------------------------------------------------------------------------
    # KEYFRAME ACT 2 (f049-f076): HINGES OPEN/CLOSE & SUB-SURFACE HUD BOOT-UP
    # -------------------------------------------------------------------------
    hood = copies["Hood"]
    hood.animation_data_clear()
    for f, deg in [(1, 0.0), (48, 0.0), (55, engine_bay.HOOD_OPEN_DEG), (65, engine_bay.HOOD_OPEN_DEG), (74, 0.0)]:
        hood.rotation_euler = (0.0, math.radians(deg), 0.0)
        hood.keyframe_insert("rotation_euler", index=1, frame=f)

    trunk = copies["TrunkLid"]
    trunk.animation_data_clear()
    for f, deg in [(1, 0.0), (48, 0.0), (55, -engine_bay.TRUNK_OPEN_DEG), (68, -engine_bay.TRUNK_OPEN_DEG), (75, 0.0)]:
        trunk.rotation_euler = (0.0, math.radians(deg), 0.0)
        trunk.keyframe_insert("rotation_euler", index=1, frame=f)

    for side in doors.SIDES:
        t = doors.tag(side)
        door = copies[f"Door_{t}"]
        door.animation_data_clear()
        for f, deg in [(1, 0.0), (48, 0.0), (56, doors.OPEN_DEG), (66, doors.OPEN_DEG), (74, 0.0)]:
            door.rotation_euler = (0.0, 0.0, math.radians(side * deg))
            door.keyframe_insert("rotation_euler", index=2, frame=f)

    # Restore solid black material appearance on tubs once body closes (by animating alpha on AI_TubCutaway)
    bsdf_tub = next((n for n in mat_tub_xray.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf_tub and "Alpha" in bsdf_tub.inputs:
        bsdf_tub.inputs["Alpha"].default_value = 0.50
        bsdf_tub.inputs["Alpha"].keyframe_insert("default_value", frame=1)
        bsdf_tub.inputs["Alpha"].keyframe_insert("default_value", frame=44)
        bsdf_tub.inputs["Alpha"].default_value = 1.0
        bsdf_tub.inputs["Alpha"].keyframe_insert("default_value", frame=54)

    # -------------------------------------------------------------------------
    # KEYFRAME ACT 3 & ACT 4 (f077-f144): AI PERCEPTION, REFLEX BRAKE & S-CURVE DRIVE
    # -------------------------------------------------------------------------
    _key_vis_window(vfx_fov, [(74, 144)])
    _key_vis_window(vfx_tof_g, [(74, 86), (102, 144)])
    _key_vis_window(vfx_tof_r, [(86, 102)])
    _key_vis_window(hud_alert_red, [(86, 102)])
    _key_vis_window(vfx_wave1, [(87, 105), (132, 144)])
    _key_vis_window(vfx_wave2, [(89, 105), (134, 144)])
    _key_vis_window(obs_cone, [(72, 144)])
    _key_vis_window(obs_stripe, [(72, 144)])

    # Animate HUD Eye Gaze (shift Y in mod_hud local space when steering left/right in Act 3/4)
    for eye, y_base in ((hud_eye_l, -4.6), (hud_eye_r, 4.6)):
        eye.animation_data_clear()
        for f, dy in [(1, 0.0), (96, 0.0), (104, -2.2), (118, -2.2), (126, 2.0), (135, 0.0), (144, 0.0)]:
            eye.location = (-1.2, y_base + dy, 0.35)
            eye.keyframe_insert("location", index=1, frame=f)

    # Car trajectory (`SC_Root` location & Z-yaw) + front steering (`Knuckle_L/R` + `SteeringLink`) + wheel spin
    # Car drives forward along -X:
    #   f076..f086: cruises forward from X=0 to X=-42 mm, then VL53L1X auto-brakes in front of obstacle at X=-92 mm!
    #   f086..f098: stopped while VL53L1X red laser + GC9A01 ALERT_STOP + voice reasoning active
    #   f098..f106: steers +15 deg Left while stationary/starting
    #   f106..f136: drives forward from X=-42 to X=-168 mm while shifting laterally to Y=-42 mm around obstacle!
    drive_keys = [
        # (frame, root_x, root_y, yaw_deg, steer_deg)
        (1, 0.0, 0.0, 0.0, 0.0),
        (75, 0.0, 0.0, 0.0, 0.0),
        (86, -42.0, 0.0, 0.0, 0.0),     # Auto-brake stop before obstacle!
        (98, -42.0, 0.0, 0.0, 0.0),     # Hold stop during voice/HUD alert
        (104, -44.0, -1.5, -3.0, 15.0), # Full +15 deg left steer
        (118, -96.0, -28.0, -14.0, 15.0),
        (128, -138.0, -42.0, 6.0, -14.0),  # Counter-steer right to straighten in new lane
        (138, -165.0, -44.0, 0.0, 0.0),
        (144, -168.0, -44.0, 0.0, 0.0),
    ]
    root.animation_data_clear()
    kn_l = copies["Knuckle_L"]
    kn_r = copies["Knuckle_R"]
    s_link = copies["SteeringLink"]
    kn_l.animation_data_clear()
    kn_r.animation_data_clear()
    s_link.animation_data_clear()
    s_link_base_y = s_link.location.y

    for f, rx, ry, yaw, steer in drive_keys:
        root.location = (rx, ry, 0.0)
        root.rotation_euler = (0.0, 0.0, math.radians(yaw))
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", index=2, frame=f)

        s_rad = math.radians(steer)
        kn_l.rotation_euler = (0.0, 0.0, s_rad)
        kn_r.rotation_euler = (0.0, 0.0, s_rad)
        kn_l.keyframe_insert("rotation_euler", index=2, frame=f)
        kn_r.keyframe_insert("rotation_euler", index=2, frame=f)

        s_link.location.y = s_link_base_y - 3.2 * math.sin(s_rad)
        s_link.keyframe_insert("location", index=1, frame=f)

    # Spin wheels and 7T:9T drivetrain proportional to distance traveled
    wheel_r = 16.5
    for w_name in ("Rim_FL", "Tire_FL", "Rim_FR", "Tire_FR", "Rim_RL", "Tire_RL", "Rim_RR", "Tire_RR", "Axle_R", "AxleGear"):
        if w_name not in copies:
            continue
        w_ob = copies[w_name]
        w_ob.animation_data_clear()
        dist_accum = 0.0
        prev_x, prev_y = 0.0, 0.0
        for f, rx, ry, _, _ in drive_keys:
            dist_accum += math.hypot(rx - prev_x, ry - prev_y)
            prev_x, prev_y = rx, ry
            ang = -dist_accum / wheel_r
            w_ob.rotation_euler = (0.0, ang, 0.0)
            w_ob.keyframe_insert("rotation_euler", index=1, frame=f)

    # -------------------------------------------------------------------------
    # CAMERA CHOREOGRAPHY ACROSS ALL 4 ACTS
    # -------------------------------------------------------------------------
    target = bpy.data.objects.get("SC_CamTarget") or bpy.data.objects.new("SC_CamTarget", None)
    if target.name not in col.objects:
        col.objects.link(target)
    cam = bpy.data.objects.get("SC_Camera")
    if cam is None:
        cam = bpy.data.objects.new("SC_Camera", bpy.data.cameras.get("SC_Camera") or bpy.data.cameras.new("SC_Camera"))
    if cam.name not in col.objects:
        col.objects.link(cam)
    cam.data.lens = 45
    cam.data.clip_start, cam.data.clip_end = 1.0, 5000.0
    cam.constraints.clear()
    track = cam.constraints.new('TRACK_TO')
    track.target = target
    track.track_axis, track.up_axis = 'TRACK_NEGATIVE_Z', 'UP_Y'

    cam_keys = [
        # Act 1: Close-up X-Ray/Cutaway views of the 5 cable harnesses assembling
        (1, 34, -36, 225, (85, -5, 24)),     # Wave 1: Front bay + under-floor H4 conduit
        (14, 38, -58, 210, (115, -8, 26)),   # Following H4 conduit rearward
        (24, 36, 135, 185, (182, -5, 36)),   # Wave 2 & 3: Rear trunk LiPo/BEC (H5) + Radxa Zero 3W L-rail slide-in (H3)
        (34, 28, 152, 165, (172, 0, 44)),    # Wave 4: Close-up of 40-pin GPIO + H2 GC9A01 HUD drop
        (44, 32, 118, 195, (148, 0, 52)),    # Wave 4: Roof WaymoPod OV5647 + INMP441 chimney drop (H1)
        # Act 2: Body shell lowers, panels open & close, rear fastback HUD boot-up
        (54, 22, -35, 310, (110, 0, 32)),    # Full car with Hood, Doors, Trunk open
        (66, 20, 158, 215, (175, 0, 46)),    # Rear 3/4 close-up: Sub-surface GC9A01 HUD glowing through Glass_Rear + open Trunk
        (75, 18, -32, 310, (95, 0, 28)),     # Ready to launch
        # Act 3: Forward cruise, obstacle detection & <20 ms VL53L1X reflex auto-brake
        (86, 22, -42, 260, (10, -5, 28)),    # Emergency stop right in front of red/white cone + red laser beam!
        (94, 24, -48, 255, (15, -5, 30)),    # Hold front-side 3/4 view showing red laser + roof voice waves + cone
        (102, 22, 142, 235, (65, -5, 38)),   # Rear 3/4 view showing red GC9A01 ALERT_STOP HUD + LOOK_LEFT
        (110, 26, -42, 285, (-15, -18, 28)), # Front wheels steer +15 deg Left & start S-curve
        # Act 4: Autonomous S-curve obstacle avoidance & hero finish
        (122, 26, -45, 290, (-35, -28, 28)), # S-curve pass around obstacle
        (136, 18, -34, 275, (-65, -42, 28)), # Hero front/side 3/4 pose after clearing obstacle
        (144, 20, 148, 235, (-25, -44, 38)), # Final rear 3/4 hero look at glowing GC9A01 HAPPY HUD
    ]
    cam.animation_data_clear()
    target.animation_data_clear()
    for f, elev, azim, dist, tgt in cam_keys:
        cam.location = _camera_point(elev, azim, dist, tgt)
        cam.keyframe_insert("location", frame=f)
        target.location = Vector(tgt)
        target.keyframe_insert("location", frame=f)

    scene.camera = cam
    scene.frame_start, scene.frame_end = 1, END
    scene.render.fps = FPS
    scene.frame_set(1)
    return {"parts": len(copies), "frames": END}


HUD_CAPTIONS = [
    (1, 14, "ACT 1.1 — FRONT SENSORS & HARNESS H4 (UNDER-FLOOR CONDUIT)",
     "VL53L1X ToF (Pins 1,3,5,11,14) + 1.7g Servo (Pin 7) + N25 Motor (DRV8833 AOUT1/2) -> 4.0x5.0mm Driver Conduit",
     "CRUISE", 420, 0.0),
    (15, 24, "ACT 1.2 — LOWER TRUNK POWER VAULT (H5) & CABIN AUDIO DECK (H3-B)",
     "2S 7.4V LiPo + 5V 3A Buck BEC -> Radxa Pins 4/6 & DRV8833 VM | 15x24x4mm Speaker (Tub_AISpeakerBay) <- MAX98357A",
     "CRUISE", 420, 0.0),
    (25, 34, "ACT 1.3 — RADXA ZERO 3W L-RAIL SLIDE-IN & 40-PIN GPIO HOOKUP (H3-A/C)",
     "65x30x5.2mm Radxa slides onto Z=36.0mm 3-Zone L-Rail | I2S3 Amp (Pins 2,6,12,35,40,37) + DRV8833 (Pins 32,33,36,30)",
     "THINKING", 380, 0.0),
    (35, 48, "ACT 1.4 — SUB-SURFACE 1.28\" GC9A01 HUD (H2) & ROOF POD CHIMNEY DROP (H1)",
     "GC9A01 SPI3 -> Pins 1,9,19,23,24,18,22,16 (<12mm drop) | OV5647 15-to-22p CSI + INMP441 Mic -> Cut_WaymoChimney",
     "CRUISE", 360, 0.0),
    (49, 75, "ACT 2 — BODY INTEGRATION, V8 MOTOR SHROUD & SUB-SURFACE REAR WINDOW HUD",
     "0.0mm Exterior Protrusion GC9A01 Rear Window HUD + 5.5mm Shelby Teardrop Roof Scoop (80% Sunk Below Roofline)",
     "CRUISE", 340, 0.0),
    (76, 85, "ACT 3.1 — GEMINI-ROBOTICS-ER-2-STREAMING LIVE AUTONOMOUS CRUISE",
     "Streaming 160-deg OV5647 Fisheye Video (5 FPS) + 16kHz I2S Audio | VL53L1X Front Laser Polling @ 50Hz",
     "CRUISE", 240, 0.0),
    (86, 98, "ACT 3.2 — VL53L1X <20ms HARDWARE REFLEX AUTO-BRAKE & BIDIRECTIONAL VOICE",
     "EMERGENCY STOP: Obstacle @ 92mm (<120mm threshold) -> DRV8833 Brake | GC9A01 HUD: ALERT_STOP | Speaking via MAX98357A",
     "ALERT_STOP", 92, 0.0),
    (99, 108, "ACT 3.3 — GEMINI ER 2.0 TOOL CALL: drive_and_steer(steer=+15.0) + LOOK_LEFT",
     "AI Agent Plans Evasive Left Lane Change Around Obstacle -> 1.7g Servo Pivots Knuckle_L/R +15.0 deg Left",
     "LOOK_LEFT", 145, 15.0),
    (109, 134, "ACT 4.1 — AUTONOMOUS S-CURVE OBSTACLE AVOIDANCE & 7T:9T LIVE AXLE SPIN",
     "Proportional PWM Throttle + Coupled Ackermann Steering (+15 deg Left -> -14 deg Right -> Straight Lane Recovery)",
     "SPEAKING", 380, -12.0),
    (135, 144, "ACT 4.2 — OBSTACLE CLEARED & CHARISMATIC 1967 MUSTANG VOICE GREETING",
     "GC9A01 Rear Fastback Window HUD Displays HAPPY Expression + Live Voice Waveform Equalizer",
     "HAPPY", 520, 0.0),
]


def _annotate_frames_with_hud(out_dir):
    """Burn the top telemetry bar + bottom-right live 240x240 circular GC9A01 HUD inset onto each PNG frame."""
    from PIL import Image, ImageDraw, ImageFont

    sys_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys_root not in os.sys.path:
        os.sys.path.insert(0, sys_root)
    from ai_edition.drivers.gc9a01_display import GC9A01Display

    hud = GC9A01Display(simulate=True)
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 19)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Menlo.ttc", 13)
        font_badge = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    for frame in range(1, END + 1):
        fpath = os.path.join(out_dir, f"frame_{frame:04d}.png")
        if not os.path.exists(fpath):
            continue
        cap = next((c for c in HUD_CAPTIONS if c[0] <= frame <= c[1]), HUD_CAPTIONS[-1])
        _, _, title, subtitle, emotion, tof_mm, steer_deg = cap

        img = Image.open(fpath).convert("RGBA")
        w, h = img.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Top translucent telemetry banner
        draw.rectangle([(0, 0), (w, 64)], fill=(10, 14, 22, 210))
        accent = (255, 50, 50, 255) if emotion == "ALERT_STOP" else (0, 225, 255, 255)
        draw.rectangle([(0, 61), (w, 64)], fill=accent)
        draw.text((18, 9), title, fill=accent, font=font_title)
        draw.text((18, 36), subtitle, fill=(230, 238, 248, 255), font=font_sub)

        # Frame counter badge (top-right)
        draw.rounded_rectangle([(w - 152, 12), (w - 16, 48)], radius=8, fill=(24, 32, 48, 230), outline=accent, width=2)
        draw.text((w - 138, 22), f"FRAME {frame:03d}/{END}", fill=(255, 255, 255, 255), font=font_badge)

        # Render live 240x240 circular GC9A01 HUD inset in bottom-right corner
        hud_img = hud.render_hud(
            emotion=emotion,
            message="STOP 92mm!" if emotion == "ALERT_STOP" else f"ToF {tof_mm}mm",
            steering_deg=steer_deg,
            throttle=0.0 if emotion == "ALERT_STOP" else (0.48 if frame >= 76 else 0.0),
            tof_mm=tof_mm,
            voice_level=0.75 if emotion in ("SPEAKING", "ALERT_STOP", "HAPPY") else 0.12,
        ).convert("RGBA")
        hud_size = 156
        hud_resized = hud_img.resize((hud_size, hud_size), Image.Resampling.LANCZOS)

        # Circular mask for HUD inset
        mask = Image.new("L", (hud_size, hud_size), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.ellipse([(2, 2), (hud_size - 3, hud_size - 3)], fill=255)

        hx, hy = w - hud_size - 20, h - hud_size - 36
        draw.rounded_rectangle([(hx - 10, hy - 28), (w - 10, h - 10)], radius=14,
                               fill=(10, 14, 22, 215), outline=accent, width=2)
        draw.text((hx + 6, hy - 22), "GC9A01 1.28\" REAR HUD", fill=accent, font=font_badge)
        out = Image.alpha_composite(img, overlay)
        out.paste(hud_resized, (hx, hy), mask)
        out.convert("RGB").save(fpath, quality=95)


def _build_storyboard_and_videos(out_dir):
    """Compile MP4, GIF, and 6-panel HD storyboard from the rendered frames."""
    from PIL import Image

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mp4_ai = os.path.join(root_dir, "output", "ai_edition", "mustang_67_ai_simulation.mp4")
    mp4_docs = os.path.join(root_dir, "docs", "images", "ai_simulation.mp4")
    gif_docs = os.path.join(root_dir, "docs", "images", "ai_simulation.gif")
    story_docs = os.path.join(root_dir, "docs", "images", "ai_simulation_storyboard.jpg")
    os.makedirs(os.path.dirname(mp4_ai), exist_ok=True)
    os.makedirs(os.path.dirname(mp4_docs), exist_ok=True)

    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", os.path.join(out_dir, "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        mp4_ai,
    ], check=True)
    subprocess.run(["cp", mp4_ai, mp4_docs], check=True)

    subprocess.run([
        "ffmpeg", "-y", "-i", mp4_ai,
        "-vf", "fps=12,scale=720:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
        gif_docs,
    ], check=True)

    # 6-Panel Storyboard (3x2 grid) of key cable assembly & AI drive milestones
    pick_frames = [14, 24, 44, 66, 92, 122]
    tiles = [Image.open(os.path.join(out_dir, f"frame_{f:04d}.png")).convert("RGB") for f in pick_frames]
    tw, th = 640, 360
    tiles = [t.resize((tw, th), Image.Resampling.LANCZOS) for t in tiles]
    grid = Image.new("RGB", (tw * 3, th * 2))
    for idx, tile in enumerate(tiles):
        r, c = divmod(idx, 3)
        grid.paste(tile, (c * tw, r * th))
    grid.save(story_docs, quality=92)
    return {"mp4": mp4_docs, "gif": gif_docs, "storyboard": story_docs}


def render_ai_simulation(out_dir=None, res=(1280, 720), samples=6, frames=None):
    """Setup and render all 144 frames of the 4-Act AI Cable Assembly & Autonomous Drive simulation."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = out_dir or os.path.join(root_dir, "tmp", "ai_sim_frames")
    os.makedirs(out_dir, exist_ok=True)
    setup_ai_simulation()

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for dev in prefs.devices:
        dev.use = True
    scene.cycles.device = 'GPU'
    scene.cycles.samples = samples
    scene.cycles.max_bounces = 3
    scene.cycles.transparent_max_bounces = 3
    scene.cycles.use_denoising = True
    scene.render.use_persistent_data = True
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'

    frame_list = frames or list(range(1, END + 1))
    for f in frame_list:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(out_dir, f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)

    if frames is None:
        subprocess.run([
            "uv", "run", "--with", "pillow", "python3",
            os.path.abspath(__file__), "--postprocess", out_dir,
        ], check=True)
    return {"out_dir": out_dir, "frames_rendered": len(frame_list)}


if __name__ == "__main__":
    if "--postprocess" in sys.argv:
        idx = sys.argv.index("--postprocess")
        target_dir = sys.argv[idx + 1]
        _annotate_frames_with_hud(target_dir)
        res = _build_storyboard_and_videos(target_dir)
        print("Post-processed AI Simulation:", res)
    else:
        res = render_ai_simulation()
        print("AI Simulation Complete:", res)
