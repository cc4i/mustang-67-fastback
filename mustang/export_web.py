"""Export web-ready Draco-compressed `.glb` assets and `assembly_manifest.json` for the interactive
3D Assembly & Drive Studio (`site/public/assets/`).

Generates two lightweight glTF 2.0 binaries with full PBR materials and centered mechanical pivots:
  1. `mustang_rc.glb`: All 68 Classic RC printed car parts + 6 virtual RC electronics modules +
     4 `1.75 mm` filament reinforcement/hinge pins (`~2.5 MB` Draco-compressed).
  2. `mustang_ai_delta.glb`: The 5 AI-modified boolean shells (`AI_Body`, `AI_Glass_Rear`,
     `AI_InteriorTub`, `AI_BootTub`, `AI_BayTub`), `WaymoPod`, `GC9A01Bezel`, UV-mapped
     `AI_GC9A01_Screen` disc, all 14 real-datasheet `BOM_*` 3D boards, `H1`..`H5` cable meshes,
     and perception FOV/ToF beams (`~0.6 MB` Draco-compressed).
  3. `assembly_manifest.json`: Structured 7-stage (Classic RC) and 8-stage (AI Edition) assembly
     steps, Bambu X2D 9-plate breakdown, Stage-1 16-STL mule flags, Three.js insertion vectors,
     and exact kinematic joint definitions.

Run headlessly from the project root:
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python mustang/export_web.py
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ai_edition  # noqa: E402
import build  # noqa: E402
import doors  # noqa: E402
import engine_bay  # noqa: E402
import export  # noqa: E402
import paths  # noqa: E402
import studio  # noqa: E402

ROOT_DIR = os.path.dirname(_HERE)
WEB_ASSETS_DIR = os.path.join(ROOT_DIR, "site", "public", "assets")
BASELINE_BLEND = os.path.join(paths.OUTPUT, "mustang_67_fastback.blend")

SPIN_CENTER_PARTS = (
    "Rim_FL", "Tire_FL", "Rim_FR", "Tire_FR",
    "Rim_RL", "Tire_RL", "Rim_RR", "Tire_RR",
    "Axle_R", "AxleGear", "PinionGear", "Driveshaft",
    "MotorCoupler", "SteeringLink",
)

STAGE1_MULE_STLS = {
    "chassis.stl", "bay_tub.stl", "interior_tub.stl", "boot_tub.stl",
    "axle.stl", "diff_cover.stl", "driveshaft.stl", "pinion_gear.stl",
    "axle_gear.stl", "motor_coupler_n25.stl", "motor_coupler_1p0.stl",
    "motor_coupler_1p5.stl", "motor_coupler_tube.stl", "motor_shim_x2.stl",
    "knuckle_l.stl", "knuckle_r.stl", "steering_link.stl",
    "rim_x4.stl", "tire_x4.stl",
}

PLATES_SPEC = [
    {
        "plate": 1,
        "group": "1_body",
        "title": "Plate 1 - Fastback Body & Tinted Glass Inlays",
        "colour_name": "Burgundy + Black Inlays",
        "colour": "#6B0F1A",
        "pieces": 3,
        "notes": "Multi-colour assembled print (`body.stl` + `windshield.stl` + `rear_glass.stl`) with `tree(auto)` build-plate supports.",
        "stls": ["body.stl", "windshield.stl", "rear_glass.stl"],
    },
    {
        "plate": 2,
        "group": "1_hood",
        "title": "Plate 2 - Hinged Hood & Trunk Lid",
        "colour_name": "Burgundy",
        "colour": "#6B0F1A",
        "pieces": 2,
        "notes": "Dedicated plate so `tree(auto)` supports never crowd neighbouring parts.",
        "stls": ["hood.stl", "trunk_lid.stl"],
    },
    {
        "plate": 3,
        "group": "1_doors",
        "title": "Plate 3 - Hinged Doors (+ Roof Pod in AI Edition)",
        "colour_name": "Burgundy",
        "colour": "#6B0F1A",
        "pieces": 2,
        "pieces_ai": 3,
        "notes": "Doors print flat on their inner face (`0` supports); AI Edition adds support-free `waymo_pod.stl`.",
        "stls": ["door_l.stl", "door_r.stl"],
        "stls_ai_extra": ["waymo_pod.stl"],
    },
    {
        "plate": 4,
        "group": "2_black",
        "title": "Plate 4 - Structural Chassis, Tubs, Tires & Steering",
        "colour_name": "Black",
        "colour": "#1A1A1A",
        "pieces": 24,
        "notes": "100% support-free structural plate with `outer_only` brims on slender steering and trim parts.",
        "stls": [
            "chassis.stl", "tire_x4.stl", "grille.stl", "diff_cover.stl", "axle.stl",
            "knuckle_r.stl", "knuckle_l.stl", "steering_link.stl", "interior_tub.stl",
            "steering_wheel.stl", "door_card_r.stl", "door_card_l.stl", "bay_tub.stl",
            "valve_cover_r.stl", "valve_cover_l.stl", "air_cleaner.stl", "brace.stl",
            "hood_prop.stl", "boot_tub.stl", "motor_shim_x2.stl",
        ],
    },
    {
        "plate": 5,
        "group": "3_silver",
        "title": "Plate 5 - Torq-Thrust Rims, Front Bumper & Driveshaft",
        "colour_name": "Silver / Chrome",
        "colour": "#C8C8CC",
        "pieces": 9,
        "notes": "Support-free silver plate; `driveshaft.stl` prints flat horizontally on `Z = 0` for axial fiber strength.",
        "stls": ["rim_x4.stl", "bumper_front.stl", "grille_surround.stl", "exhaust_x2.stl", "driveshaft.stl"],
    },
    {
        "plate": 6,
        "group": "3_silver_small",
        "title": "Plate 6 - Precision Bevel Gears, Couplers & Chrome Trim",
        "colour_name": "Silver / Chrome",
        "colour": "#C8C8CC",
        "pieces": 25,
        "pieces_ai": 26,
        "notes": (
            "Isolated low-Z precision plate (`<= 10.04 mm`) with `outer_only` brims "
            "and gentle `20-25 mm/s` speeds; AI adds `gc9a01_bezel.stl`."
        ),
        "stls": [
            "corral_emblem.stl", "fog_lamp_x2.stl", "headlight_x2.stl", "park_light_x2.stl",
            "taillight_bezel_r_x3.stl", "taillight_bezel_l_x3.stl", "gas_cap.stl",
            "backup_light_x2.stl", "mirror.stl", "vent_window_r.stl", "vent_window_l.stl",
            "pinion_gear.stl", "axle_gear.stl", "motor_coupler_1p0.stl",
            "motor_coupler_1p5.stl", "motor_coupler_tube.stl", "motor_coupler_n25.stl",
        ],
        "stls_ai_extra": ["gc9a01_bezel.stl"],
    },
    {
        "plate": 7,
        "group": "3_bumper",
        "title": "Plate 7 - Swept Rear Chrome Bumper",
        "colour_name": "Silver / Chrome",
        "colour": "#C8C8CC",
        "pieces": 1,
        "notes": "Dedicated plate standing upright on `tree(auto)` supports.",
        "stls": ["bumper_rear.stl"],
    },
    {
        "plate": 8,
        "group": "4_red",
        "title": "Plate 8 - Tri-Bar Taillight Lenses",
        "colour_name": "Red",
        "colour": "#B01010",
        "pieces": 6,
        "notes": "6 concave red lenses (`outer_only` peel brims).",
        "stls": ["taillight_lens_r_x3.stl", "taillight_lens_l_x3.stl"],
    },
    {
        "plate": 9,
        "group": "5_blue",
        "title": "Plate 9 - 289 V8 Motor Shroud Block",
        "colour_name": "Ford Engine Blue",
        "colour": "#2B59C3",
        "pieces": 1,
        "notes": "Hollowed underside cavity (`Engine_N25Cavity`) disguising the `N25` gearmotor on `324.45 mm^2` flat bed rails.",
        "stls": ["engine_block.stl"],
    },
]


def _blender_vec_to_three(vec):
    """Convert a Blender Z-up vector `(bx, by, bz)` to glTF/Three.js Y-up `(bx, bz, -by)`."""
    bx, by, bz = vec
    return [round(float(bx), 3), round(float(bz), 3), round(float(-by), 3)]


def _prepare_gltf_materials():
    """Ensure all Blender materials export cleanly to glTF 2.0 PBR without Cycles-only bump artifacts."""
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF") or next(
            (n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None
        )
        if bsdf is None:
            continue
        for sock_name in ("Base Color", "Normal"):
            sock = bsdf.inputs.get(sock_name)
            if sock and sock.is_linked:
                for lnk in list(sock.links):
                    nt.links.remove(lnk)
        if mat.name == "SealedBeam":
            bsdf.inputs["Base Color"].default_value = (0.86, 0.89, 0.94, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.85
            bsdf.inputs["Roughness"].default_value = 0.12
        elif mat.name == "RingLens":
            bsdf.inputs["Base Color"].default_value = (0.78, 0.82, 0.82, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.45
            bsdf.inputs["Roughness"].default_value = 0.16
        elif mat.name == "Glass":
            bsdf.inputs["Base Color"].default_value = (0.025, 0.032, 0.045, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.15
            bsdf.inputs["Roughness"].default_value = 0.04
            if "Coat Weight" in bsdf.inputs:
                bsdf.inputs["Coat Weight"].default_value = 1.0
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 1.0
        elif mat.name == "ClearGlass":
            bsdf.inputs["Base Color"].default_value = (0.62, 0.70, 0.74, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.04
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 0.30
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"


def _make_pbr_mat(name, rgba, metallic=0.2, roughness=0.35, emission=None, emission_strength=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission is not None and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 0.999 and hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    return mat


def _apply_auto_smooth(ob, angle_deg=35.0):
    ng = bpy.data.node_groups.get("Smooth by Angle")
    if ng is not None:
        mod = ob.modifiers.get("Smooth by Angle") or ob.modifiers.new("Smooth by Angle", "NODES")
        mod.node_group = ng
        try:
            mod["Input_1"] = math.radians(angle_deg)
        except Exception:
            pass
    else:
        with bpy.context.temp_override(
            object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]
        ):
            bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))


def _bake_object(src, dg, out_name, target_col):
    """Bake an evaluated Blender object (with Smooth by Angle applied) into `target_col`."""
    _apply_auto_smooth(src, 35.0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(src.evaluated_get(dg))
    me.name = out_name
    ob = bpy.data.objects.new(out_name, me)
    ob.matrix_world = src.matrix_world.copy()
    target_col.objects.link(ob)
    return ob


def _center_mesh_origin(ob):
    """Set exact analytical rotation/shift origins so odd-toothed gears and shaved shafts have 0.0 mm runout."""
    if not ob.data or not ob.data.vertices:
        return
    verts = [v.co for v in ob.data.vertices]
    cx = 0.5 * (min(v.x for v in verts) + max(v.x for v in verts))
    cy = 0.5 * (min(v.y for v in verts) + max(v.y for v in verts))
    cz = 0.5 * (min(v.z for v in verts) + max(v.z for v in verts))
    if ob.name in ("MotorCoupler", "Driveshaft", "PinionGear"):
        # Snap Y_world = 0.0, Z_world = 19.75 mm (395 * 1/20), keeping world X midpoint
        w_mid = ob.matrix_world @ Vector((cx, cy, cz))
        c = ob.matrix_world.inverted() @ Vector((w_mid.x, 0.0, 19.75))
    elif ob.name in ("AxleGear", "Axle_R"):
        # Snap X_world = 176.75 mm (3535 * 1/20), Z_world = 16.50 mm (330 * 1/20), keeping world Y midpoint
        w_mid = ob.matrix_world @ Vector((cx, cy, cz))
        c = ob.matrix_world.inverted() @ Vector((176.75, w_mid.y, 16.50))
    elif ob.name.startswith(("Rim_", "Tire_")):
        # Revolved in local space around exact (x = 0, z = 0) hub axis
        c = Vector((0.0, cy, 0.0))
    else:
        c = Vector((cx, cy, cz))
    ob.data.transform(Matrix.Translation(-c))
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(c)


def _attach_clean_parent(child, parent):
    mw = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse.identity()
    child.matrix_basis = parent.matrix_world.inverted() @ mw


def _create_box(name, size, loc, mat, col, rot_deg=(0.0, 0.0, 0.0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
    col.objects.link(ob)
    return ob


def _create_cyl(name, radius, depth, loc, mat, col, rot_deg=(0.0, 0.0, 0.0), segs=24, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius, radius2=radius, depth=depth)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
    col.objects.link(ob)
    return ob


def _create_cone(name, r1, r2, depth, loc, mat, col, rot_deg=(0.0, 0.0, 0.0), segs=32):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r1, radius2=r2, depth=depth)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
    col.objects.link(ob)
    return ob


def _create_uv_disc(name, radius, loc, rot_deg, mat, col, segs=48):
    """Build a UV-mapped circular screen mesh `[0,1]x[0,1]` so Three.js can render live HUD emojis."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    center = bm.verts.new((0.0, 0.0, 0.0))
    ring = []
    for k in range(segs):
        ang = 2.0 * math.pi * k / segs
        ring.append(bm.verts.new((radius * math.cos(ang), radius * math.sin(ang), 0.0)))
    for k in range(segs):
        v1 = ring[k]
        v2 = ring[(k + 1) % segs]
        f = bm.faces.new((center, v1, v2))
        for loop in f.loops:
            vx, vy, _ = loop.vert.co
            # Map local XY onto upright [0,1] UV space viewed from rear (+X)
            u = 0.5 + 0.5 * (vy / radius)
            v = 0.5 - 0.5 * (vx / radius)
            loop[uv_layer].uv = (u, v)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
    col.objects.link(ob)
    return ob


def _create_cable_mesh(name, pts, radius, mat, col, ribbon_width=0.0):
    """Create a curve cable and bake it into a triangulated `MESH` so glTF exports it cleanly."""
    cu = bpy.data.curves.new(f"_cu_{name}", "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 10
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    if ribbon_width > 0.0:
        cu.extrude = ribbon_width * 0.5
        cu.bevel_depth = 0.16
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (x, y, z) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1.0)
    cu.materials.append(mat)
    tmp_ob = bpy.data.objects.new(f"_tmp_{name}", cu)
    bpy.context.scene.collection.objects.link(tmp_ob)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp_ob.evaluated_get(dg))
    me.name = name
    for p in me.polygons:
        p.use_smooth = True
    bpy.data.objects.remove(tmp_ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def _export_collection_glb(col, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in col.objects:
        if ob.type == "MESH":
            ob.hide_viewport = False
            ob.hide_set(False)
            ob.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=out_path,
        use_selection=True,
        export_format="GLB",
        export_yup=True,
        export_apply=False,
        export_materials="EXPORT",
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
    )
    return os.path.getsize(out_path)


def export_classic_rc_glb():
    """Build or open the baseline 1:20 Mustang scene and export `mustang_rc.glb`."""
    if os.path.exists(BASELINE_BLEND):
        bpy.ops.wm.open_mainfile(filepath=BASELINE_BLEND)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build.main()
        studio.setup()

    # Reset all hinged/steered poses to neutral 0 deg
    for h_name in export.HINGED:
        if h_name in bpy.data.objects:
            bpy.data.objects[h_name].rotation_euler = (0.0, 0.0, 0.0)
    for col_name in ("Body", "Wheels", "Parts", "Accessories"):
        c = bpy.data.collections.get(col_name)
        if c:
            c.hide_viewport = False
    sc_old = bpy.data.collections.get("Showcase")
    if sc_old:
        for ob in list(sc_old.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(sc_old)

    _prepare_gltf_materials()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    web_col = bpy.data.collections.new("WebRC")
    bpy.context.scene.collection.children.link(web_col)

    sources = []
    for col_name in ("Body", "Wheels", "Parts", "Accessories"):
        c = bpy.data.collections.get(col_name)
        if not c:
            continue
        for src in sorted(c.objects, key=lambda o: o.name):
            if src.type != "MESH":
                continue
            if col_name == "Accessories" and src.name not in ("HoodProp", "MotorShim_0p5"):
                continue
            sources.append(src)

    baked = {}
    for src in sources:
        tmp_name = f"__web_{src.name}"
        baked[src.name] = _bake_object(src, dg, tmp_name, web_col)

    # Remove original build collections so canonical names (`Body`, `Hood`, etc.) do not collide
    for col_name in ("Body", "Wheels", "Parts", "Accessories", "Cutters", "Studio"):
        c = bpy.data.collections.get(col_name)
        if c:
            for ob in list(c.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.collections.remove(c)

    for orig_name, ob in baked.items():
        ob.name = orig_name
        ob.data.name = orig_name

    # Position MotorShim_0p5 neatly under the N25 motor bed if present
    if "MotorShim_0p5" in baked:
        baked["MotorShim_0p5"].location = Vector((57.75, 0.0, 14.55))
        baked["MotorShim_0p5"].rotation_euler = (0.0, 0.0, 0.0)

    for sp_name in SPIN_CENTER_PARTS:
        if sp_name in baked:
            _center_mesh_origin(baked[sp_name])

    bpy.context.view_layer.update()

    # Build clean parent hierarchies (Identity matrix_parent_inverse for clean glTF nodes)
    for side in doors.SIDES:
        t = doors.tag(side)
        door = baked[f"Door_{t}"]
        for r_name in (f"DoorCard_{t}", f"DoorVent_{t}", f"Mirror_{t}"):
            if r_name in baked:
                _attach_clean_parent(baked[r_name], door)
        kn = baked[f"Knuckle_{t}"]
        w_tag = "FL" if side < 0 else "FR"
        for r_name in (f"Rim_{w_tag}", f"Tire_{w_tag}"):
            if r_name in baked:
                _attach_clean_parent(baked[r_name], kn)

    eng = baked["EngineBlock"]
    for r_name in ("ValveCover_L", "ValveCover_R", "AirCleaner"):
        if r_name in baked:
            _attach_clean_parent(baked[r_name], eng)

    # Add Classic RC Virtual Electronics + 1.75 mm Filament Pins so Stage 3, 4, 6 & 7 visualize them clearly
    m_servo = _make_pbr_mat("Web_ServoCyan", (0.08, 0.58, 0.88, 1.0), metallic=0.2, roughness=0.3)
    m_motor = _make_pbr_mat("Web_N25Brass", (0.88, 0.66, 0.18, 1.0), metallic=0.82, roughness=0.25)
    m_esc = _make_pbr_mat("Web_ESCBlue", (0.14, 0.36, 0.92, 1.0), metallic=0.25, roughness=0.3)
    m_rx = _make_pbr_mat("Web_RxGreen", (0.08, 0.62, 0.32, 1.0), metallic=0.25, roughness=0.3)
    m_lipo = _make_pbr_mat("Web_LiPoRed", (0.86, 0.14, 0.16, 1.0), metallic=0.2, roughness=0.35)
    m_wire = _make_pbr_mat(
        "Web_FloorWireAmber", (1.0, 0.58, 0.08, 1.0), roughness=0.25,
        emission=(1.0, 0.58, 0.08, 1.0), emission_strength=1.2,
    )
    m_fil = _make_pbr_mat(
        "Web_FilamentPinOrange", (1.0, 0.42, 0.04, 1.0), roughness=0.28,
        emission=(1.0, 0.42, 0.04, 1.0), emission_strength=0.9,
    )

    _create_box("RC_Servo1p7g", (9.5, 16.0, 6.2), (28.25, 0.0, 15.95), m_servo, web_col)
    _create_box("RC_N25Motor", (21.0, 11.0, 10.0), (57.75, 0.0, 19.75), m_motor, web_col)
    _create_box("RC_ESC5A", (18.0, 13.0, 5.0), (206.0, -11.5, 32.5), m_esc, web_col)
    _create_box("RC_Rx2p4G", (14.0, 10.0, 4.0), (213.0, -11.5, 37.5), m_rx, web_col)
    _create_box("RC_LiPo2S", (30.0, 17.0, 7.5), (208.5, 11.5, 33.2), m_lipo, web_col)
    _create_cable_mesh(
        "RC_FloorWire5",
        [
            (31.0, -4.0, 18.5), (58.0, -5.8, 18.2), (105.0, -6.1, 18.2),
            (152.0, -6.1, 18.5), (185.0, -9.5, 29.5), (204.0, -11.5, 32.5),
        ],
        radius=0.68,
        mat=m_wire,
        col=web_col,
    )

    # Raw 1.75 mm PLA filament reinforcement cores (kingpins) & door hinge pins
    _create_cyl("RC_KingpinCore_L", 0.875, 7.2, (39.6, -29.8, 17.4), m_fil, web_col)
    _create_cyl("RC_KingpinCore_R", 0.875, 7.2, (39.6, 29.8, 17.4), m_fil, web_col)
    _create_cyl("RC_DoorPin_L", 0.875, 21.0, (83.0, -39.75, 28.5), m_fil, web_col)
    _create_cyl("RC_DoorPin_R", 0.875, 21.0, (83.0, 39.75, 28.5), m_fil, web_col)

    bpy.context.view_layer.update()
    hinge_pivots_3js = {}
    for h_name in ("Hood", "TrunkLid", "Door_L", "Door_R", "Knuckle_L", "Knuckle_R"):
        if h_name in baked:
            hinge_pivots_3js[h_name] = _blender_vec_to_three(baked[h_name].matrix_world.translation)

    rc_glb_path = os.path.join(WEB_ASSETS_DIR, "mustang_rc.glb")
    rc_bytes = _export_collection_glb(web_col, rc_glb_path)
    return rc_bytes, hinge_pivots_3js


def export_ai_delta_glb():
    """Open or build the AI Edition scene and export `mustang_ai_delta.glb`."""
    if os.path.exists(ai_edition.AI_BLEND_PATH):
        bpy.ops.wm.open_mainfile(filepath=ai_edition.AI_BLEND_PATH)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        ai_edition.build_and_export(save_blend=False)

    if bpy.data.collections.get("AI_Hardware") is None:
        ai_edition.build_bom_hardware_collection()

    for h_name in export.HINGED:
        if h_name in bpy.data.objects:
            bpy.data.objects[h_name].rotation_euler = (0.0, 0.0, 0.0)
    for col_name in ("Body", "Wheels", "Parts", "Accessories", "AI_Hardware"):
        c = bpy.data.collections.get(col_name)
        if c:
            c.hide_viewport = False

    _prepare_gltf_materials()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    ai_col = bpy.data.collections.new("WebAIDelta")
    bpy.context.scene.collection.children.link(ai_col)

    ai_baked = {}
    # 1. Bake the 5 boolean-modified AI shells (`AI_Body`, `AI_Glass_Rear`, `AI_InteriorTub`, `AI_BootTub`, `AI_BayTub`)
    for shell_name in ("Body", "Glass_Rear", "InteriorTub", "BootTub", "BayTub"):
        src = bpy.data.objects[shell_name]
        target_name = f"AI_{shell_name}"
        ai_baked[target_name] = _bake_object(src, dg, f"__ai_{target_name}", ai_col)

    # 2. Bake the 2 new AI printed parts (`WaymoPod`, `GC9A01Bezel`)
    for extra_name in ("WaymoPod", "GC9A01Bezel"):
        src = bpy.data.objects[extra_name]
        ai_baked[extra_name] = _bake_object(src, dg, f"__ai_{extra_name}", ai_col)

    # 3. Bake all 14 real-datasheet BOM hardware 3D CAD meshes (`BOM_01`..`BOM_15`)
    hw_col = bpy.data.collections.get("AI_Hardware")
    if hw_col:
        for src in sorted(hw_col.objects, key=lambda o: o.name):
            if src.type == "MESH":
                ai_baked[src.name] = _bake_object(src, dg, f"__ai_{src.name}", ai_col)

    # Remove all original collections BEFORE assigning canonical names so Blender never appends `.001`
    for col_name in ("Body", "Wheels", "Parts", "Accessories", "Cutters", "Studio", "AI_Hardware", "AI_Showcase", "Showcase"):
        c = bpy.data.collections.get(col_name)
        if c:
            for ob in list(c.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.collections.remove(c)

    for target_name, ob in ai_baked.items():
        ob.name = target_name
        ob.data.name = target_name

    # 4. UV-mapped circular 1.28" GC9A01 HUD live screen disc flush inside GC9A01Bezel
    m_hud_screen = _make_pbr_mat(
        "Web_AI_GC9A01Screen", (0.04, 0.08, 0.14, 1.0), metallic=0.05, roughness=0.12,
        emission=(0.08, 0.85, 0.96, 1.0), emission_strength=1.0,
    )
    _create_uv_disc("AI_GC9A01_Screen", 13.55, (176.35, 0.0, 55.92), (0.0, 20.5, 0.0), m_hud_screen, ai_col)

    # 5. Bake the 9 colour-coded cable tubes across Harnesses H1..H5
    cables_spec = [
        ("AI_Cab_H1_CSIRibbon", (1.0, 0.55, 0.08, 1.0), 0.25, 8.2, [
            (118.5, 0.0, 65.5), (132.0, 0.0, 65.2), (143.4, 0.0, 64.0),
            (143.4, 0.0, 44.0), (153.2, 0.0, 39.5),
        ]),
        ("AI_Cab_H1_MicI2S", (0.15, 0.95, 0.45, 1.0), 0.52, 0.0, [
            (132.0, -2.5, 69.5), (142.8, -5.5, 64.0), (142.8, -8.5, 44.0),
            (168.0, -11.8, 40.8), (192.0, -11.8, 40.8),
        ]),
        ("AI_Cab_H2_HUD", (0.05, 0.88, 1.0, 1.0), 0.62, 0.0, [
            (176.5, -2.5, 53.5), (175.0, -8.5, 46.5), (174.0, -11.8, 40.8),
        ]),
        ("AI_Cab_H3_AudioDrv", (0.95, 0.22, 0.75, 1.0), 0.56, 0.0, [
            (161.5, -15.3, 30.0), (165.0, -14.0, 38.5), (175.0, -11.8, 40.8), (195.0, -11.8, 40.8),
        ]),
        ("AI_Cab_H3_SpeakerPair", (0.10, 0.92, 0.82, 1.0), 0.55, 0.0, [
            (161.5, -13.0, 29.8), (156.0, -2.0, 31.2), (161.5, 10.0, 31.2),
        ]),
        ("AI_Cab_H4_Motor", (1.0, 0.22, 0.12, 1.0), 0.58, 0.0, [
            (58.2, -3.5, 19.8), (66.0, -5.5, 18.2), (105.0, -5.5, 18.2),
            (144.0, -5.5, 18.2), (156.0, -14.0, 24.5), (161.5, -15.3, 24.2),
        ]),
        ("AI_Cab_H4_Servo", (1.0, 0.68, 0.08, 1.0), 0.50, 0.0, [
            (30.5, -3.8, 18.0), (48.0, -6.2, 18.5), (105.0, -6.2, 18.5),
            (146.0, -6.2, 18.5), (156.0, -11.8, 39.8), (163.0, -11.8, 40.5),
        ]),
        ("AI_Cab_H4_ToF", (0.35, 0.55, 1.0, 1.0), 0.52, 0.0, [
            (27.5, -4.5, 24.5), (48.0, -6.9, 19.0), (105.0, -6.9, 19.0),
            (147.0, -6.9, 19.0), (155.0, -12.5, 40.2), (160.0, -12.5, 40.8),
        ]),
        ("AI_Cab_H5_Power", (1.0, 0.12, 0.18, 1.0), 0.66, 0.0, [
            (207.8, 4.0, 33.4), (207.8, -14.5, 32.5), (195.0, -13.5, 35.0),
            (168.0, -11.8, 40.8),
        ]),
    ]
    for c_name, rgba, rad, r_w, pts in cables_spec:
        c_mat = _make_pbr_mat(f"Mat_{c_name}", rgba, roughness=0.25, emission=rgba, emission_strength=1.4)
        _create_cable_mesh(c_name, pts, rad, c_mat, ai_col, ribbon_width=r_w)

    # 6. Perception FOV cone (`OV5647` 160-deg) + `VL53L1X` ToF laser cone + road cone obstacle
    m_fov = _make_pbr_mat(
        "Mat_AI_FOV", (0.05, 0.85, 1.0, 1.0), roughness=0.2,
        emission=(0.05, 0.85, 1.0, 1.0), emission_strength=1.5, alpha=0.16,
    )
    m_tof = _make_pbr_mat(
        "Mat_AI_ToFBeam", (0.12, 1.0, 0.42, 1.0), roughness=0.2,
        emission=(0.12, 1.0, 0.42, 1.0), emission_strength=2.8, alpha=0.42,
    )
    m_cone = _make_pbr_mat("Mat_AI_ConeOrange", (0.96, 0.32, 0.06, 1.0), roughness=0.35)
    _create_cone("AI_VFX_FisheyeFOV", 1.2, 16.0, 74.0, (74.0, 0.0, 62.0), m_fov, ai_col, rot_deg=(0.0, -81.0, 0.0))
    _create_cone("AI_VFX_ToFBeam", 0.8, 8.5, 70.0, (-22.0, 0.0, 22.0), m_tof, ai_col, rot_deg=(0.0, -90.0, 0.0))
    _create_cone("AI_Track_Obstacle", 12.0, 2.2, 26.0, (-72.0, 0.0, 13.0), m_cone, ai_col, rot_deg=(0.0, 0.0, 0.0))

    # Remove all other collections before exporting selection
    for col_name in ("Body", "Wheels", "Parts", "Accessories", "Cutters", "Studio", "AI_Hardware", "AI_Showcase", "Showcase"):
        c = bpy.data.collections.get(col_name)
        if c:
            for ob in list(c.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.collections.remove(c)

    ai_glb_path = os.path.join(WEB_ASSETS_DIR, "mustang_ai_delta.glb")
    ai_bytes = _export_collection_glb(ai_col, ai_glb_path)
    return ai_bytes


def build_assembly_manifest(rc_bytes, ai_bytes, hinge_pivots_3js):
    """Build the complete structured JSON manifest driving the 3D Assembly & Drive web app."""
    # Map STL -> plate number
    stl_to_plate = {}
    for p in PLATES_SPEC:
        for s in p["stls"] + p.get("stls_ai_extra", []):
            stl_to_plate[s] = p["plate"]

    # Map object prefix / exact name -> (stl_file, qty, colour)
    stl_lookup = {}
    for key, ob_name, _rot, qty, col_hex in export.PARTS + ai_edition.AI_EXTRA_PARTS:
        fname = f"{key}_x{qty}.stl" if qty > 1 else f"{key}.stl"
        stl_lookup[ob_name] = (fname, qty, col_hex)
    for key, ob_name, _host, col_hex in export.INLAYS:
        stl_lookup[ob_name] = (f"{key}.stl", 1, col_hex)

    def resolve_stl(ob_name):
        if ob_name in stl_lookup:
            return stl_lookup[ob_name]
        base = ob_name.rsplit("_", 1)[0]
        for k, val in stl_lookup.items():
            if "_" in k and k.rsplit("_", 1)[0] == base:
                return val
        return ("", 1, "#888888")

    #Insertion vectors in Blender space `(bx, by, bz)` -> converted to Three.js `(bx, bz, -by)`:
    # Note: `+Z` bottom-up into car means part starts BELOW car `(0, 0, -55)` and moves `+Z` to `0`.
    # `-Z` top-down drop means part starts ABOVE car `(0, 0, +55)` and drops `-Z` to `0`.
    parts_meta = []

    def add_printed(node, label, stage_rc, stage_ai, start_offset_blender, tip):
        stl_file, qty, col_hex = resolve_stl(node)
        plate_num = stl_to_plate.get(stl_file)
        parts_meta.append({
            "node": node,
            "label": label,
            "category": "printed",
            "stl": stl_file,
            "plate": plate_num,
            "in_stage1_mule": stl_file in STAGE1_MULE_STLS,
            "qty": qty,
            "colour": col_hex,
            "stage_rc": stage_rc,
            "stage_ai": stage_ai,
            "start_offset_3js": _blender_vec_to_three(start_offset_blender),
            "tip": tip,
        })

    # Stage 1: Fastback Body Shell & Multi-Colour Glass Inlays
    add_printed("Body", "1967 Fastback Body Shell", 1, 1, (0, 0, 42),
                "Prints upright on Plate 1 (`1_body`) with `tree(auto)` build-plate supports (`0.12 mm` Arachne walls).")
    add_printed("Glass_Windshield", "Tinted Front Windshield Inlay", 1, 1, (-18, 0, 26),
                "Multi-colour black PLA inlay printed flush inside `Body` on Plate 1.")
    add_printed("Glass_Rear", "Tinted Fastback Rear Glass Inlay", 1, 1, (22, 0, 26),
                "Multi-colour black PLA inlay; in AI Edition `Cut_RearGlassHUD` opens a circular `Ø 30.4 mm` HUD window.")

    # Stage 2: Twin-Cowl Cabin & Engine Bay Liners (+Z bottom-up)
    add_printed("SteeringWheel", "3-Spoke Brushed-Chrome Steering Wheel", 2, 2, (16, 0, 14),
                "Plugs into the 5-pod twin-cowl dashboard before lifting `InteriorTub` into `Body`.")
    add_printed("InteriorTub", "Twin-Cowl Cabin & Waterfall Console Tub", 2, 2, (0, 0, -56),
                "Pushes straight up (`+Z`) into `Body`; open-bottom `45°` gable tunnel clears the driveshaft.")
    add_printed("BayTub", "Front Engine Liner & Motor/Servo Cradle", 2, 2, (0, 0, -56),
                "Pushes straight up (`+Z`) into front nose; houses `1.7g` servo (`BayTub_ServoBed`) and `N25` motor (`BayTub_N25Bed`).")

    # Stage 3: Motor, Servo, Open-Bottom Driveshaft & Floor Conduit
    add_printed("MotorShim_0p5", "Motor Height Calibration Z-Shims (0.48 mm)", 3, 3, (0, 0, 34),
                "Use `0`, `1`, or `2` shims under `10 mm`, `9 mm`, or `8 mm` flat-can motors to align shaft to `Z = 19.75 mm`.")
    add_printed("MotorCoupler", "Heavy-Duty Ø 6.60 mm Multi-Fit Motor Coupler", 3, 3, (14, 0, 28),
                "Pick from 4 couplers on Plate 6 (`0` grooves = `Ø 3.0 mm` N25 D-shaft, `1` = `1.0 mm`, `2` = `1.5 mm`, `3` = tube).")
    add_printed("Driveshaft", "Horizontal Bed-Flat Octagonal Driveshaft", 3, 3, (0, 0, -44),
                "Prints flat on `Z = 0` (`+63%` torsional stiffness); lifts straight up (`+Z`) into the open-bottom U-channel.")
    add_printed("PinionGear", "Collared 7-Tooth Bevel Pinion Gear", 3, 3, (12, 0, -44),
                "Presses onto the rear `3.64 mm` driveshaft tenon (`Ø 6.40 mm` bearing collar, solid tooth-root core).")

    # Stage 4: Filament-Core Hybrid Steering, 9T Live Rear Axle & Hand-Slide Wheels (Sub-assembly)
    add_printed("Chassis", "Sub-Frame Locking Chassis Plate", 4, 4, (0, 0, -52),
                "Features 9 mortise-and-tenon sub-frame locks and hollow `Ø 2.60 mm` double-shear front kingpin posts.")
    add_printed("Knuckle_L", "Left Front Steering Knuckle (Ø 4.30 mm Barrel)", 4, 4, (0, -22, -32),
                "Drops onto `Chassis_Kingpin_L` (`±15°` sweep) with a `Ø 1.80 mm` proud tie-rod pin.")
    add_printed("Knuckle_R", "Right Front Steering Knuckle (Ø 4.30 mm Barrel)", 4, 4, (0, 22, -32),
                "Drops onto `Chassis_Kingpin_R` (`±15°` sweep) with `0.125 mm`/side smooth running clearance.")
    add_printed("SteeringLink", "Reinforced Tie-Rod Steering Link", 4, 4, (-16, 0, -28),
                "Snaps over both `Ø 1.80 mm` knuckle pins (`0.90-1.18 mm` eyelet walls); center slot engages servo horn.")
    add_printed("AxleGear", "Collared 9-Tooth Crown Bevel Gear", 4, 4, (0, 14, -44),
                "`3.625 mm` wide crown gear (`Ø 8.00 mm` collar) meshes at `90°` with the `7T` `PinionGear`.")
    add_printed("Axle_R", "Max-Beef 3.60 mm Octagonal Live Rear Axle", 4, 4, (0, 48, -52),
                "Slides laterally through `Ø 4.10 mm` `Chassis_BossR` bearings and `AxleGear`'s octagonal bore.")
    add_printed("DiffCover", "Rear Differential Cover (`45°` Gable Pocket)", 4, 4, (0, 0, -70),
                "Snaps underneath `Chassis` to enclose the `7T:9T` bevel gear mesh.")
    for side_tag, y_dir, side_lbl in (("FL", -1, "Front-Left"), ("FR", 1, "Front-Right"), ("RL", -1, "Rear-Left"), ("RR", 1, "Rear-Right")):
        add_printed(f"Rim_{side_tag}", f"{side_lbl} Torq-Thrust 5-Spoke Rim", 4, 4, (0, y_dir * 34, -52),
                    "`Ø 9.60 mm` hub with 8-lobe octagonal bore and `1.80 mm` reinforced lip neck.")
        add_printed(f"Tire_{side_tag}", f"{side_lbl} Radial Tire (6-Key Hand-Slide)", 4, 4, (0, y_dir * 52, -52),
                    "Zero radial undercut (`0.22 mm`/side gap): slides onto rim by hand from inboard side across 6 drive keys.")

    # Stage 6: Hollowed 289 V8 Shroud & Rear Electronics Tub (-Z top-down)
    add_printed("EngineBlock", "Hollowed 289 V8 Motor Shroud Block", 6, 6, (0, 0, 58),
                "Lowers straight down (`-Z`, `0°` pitch) over the `N25` motor, clearing `BayTub_Booster` by `0.45 mm`.")
    add_printed("ValveCover_L", "Left Finned Cobra Valve Cover", 6, 6, (0, -14, 70),
                "Glues onto left cylinder bank of `EngineBlock` (printed at `45°` for crisp fins).")
    add_printed("ValveCover_R", "Right Finned Cobra Valve Cover", 6, 6, (0, 14, 70),
                "Glues onto right cylinder bank of `EngineBlock`.")
    add_printed("AirCleaner", "Oval Cobra Finned Air Cleaner", 6, 6, (0, 0, 76),
                "Crowns the 289 V8 intake manifold directly above the hidden motor.")
    add_printed("Brace", "Export Shock-Tower Monte Carlo Brace", 6, 6, (0, 0, 48),
                "Clips across the front shock towers behind the radiator.")
    add_printed("BootTub", "Divided Rear Trunk Electronics Tub", 6, 6, (0, 0, 52),
                "Drops straight down (`-Z`) into trunk; holds ESC + Receiver + LiPo (or `2S LiPo` + `5V BEC` in AI Edition).")

    # Stage 7: Exterior Chrome, Snap-Lock Doors (`1.75 mm` Filament Pins), Hood & Trunk
    add_printed("Grille", "Recessed Honeycomb Front Grille", 7, 7, (-36, 0, 0),
                "Seats into the 1967 V-prow nose opening.")
    add_printed("GrilleSurround", "7-Layer Stepped Chrome Grille Surround", 7, 7, (-44, 0, 0),
                "Frames the recessed grille with crisp Arachne chrome walls.")
    add_printed("Corral", "Running Pony & Corral Grille Emblem", 7, 7, (-52, 0, 0),
                "Presses into the central grille boss.")
    add_printed("Bumper_F", "Front Chrome Blade Bumper", 7, 7, (-48, 0, -8),
                "Prints upside-down support-free on Plate 5 and mounts below the V-prow nose.")
    add_printed("Bumper_R", "Rear Swept Chrome Bumper", 7, 7, (48, 0, -6),
                "Hugs the tucked rear quarter corners beneath the tri-bar taillights.")
    for s_tag, y_s in (("L", -1), ("R", 1)):
        add_printed(f"Headlight_{s_tag}", f"{'Left' if y_s < 0 else 'Right'} 7-Inch Sealed-Beam Headlight", 7, 7, (-38, y_s * 8, 0),
                    "Presses into the deep-recessed outer headlight bucket.")
        add_printed(f"FogLamp_{s_tag}", f"{'Left' if y_s < 0 else 'Right'} Grille Fog Lamp", 7, 7, (-42, y_s * 6, 0),
                    "Seats inboard of the corral bar.")
        add_printed(f"ParkLight_{s_tag}", f"{'Left' if y_s < 0 else 'Right'} Lower Valance Park Light", 7, 7, (-36, y_s * 6, -8),
                    "Snaps into the lower front valance recess.")
        add_printed(f"BackupLight_{s_tag}", f"{'Left' if y_s < 0 else 'Right'} Rear Valance Backup Lamp", 7, 7, (38, y_s * 6, -8),
                    "Presses into the lower rear valance below the bumper.")
        add_printed(f"Exhaust_{s_tag}", f"{'Left' if y_s < 0 else 'Right'} Dual Chrome Exhaust Tip", 7, 7, (40, y_s * 6, -12),
                    "Slides into the rear valance exhaust cutout.")
        for idx in (0, 1, 2):
            add_printed(f"TailBezel_{s_tag}{idx}", f"Tri-Bar Taillight Chrome Bezel ({s_tag}{idx})", 7, 7, (38, y_s * 4, 2),
                        "Concave chrome bezel from precision Plate 6 (`outer_only` brim).")
            add_printed(f"Taillight_{s_tag}{idx}", f"Tri-Bar Red Taillight Lens ({s_tag}{idx})", 7, 7, (46, y_s * 4, 2),
                        "Red PLA lens (`Plate 8`) pressing into its matching `TailBezel`.")
    add_printed("GasCap", "Vented GT Pop-Open Rear Gas Cap", 7, 7, (42, 0, 4),
                "Centers between the tri-bar taillights on the rear cove panel.")
    for s_tag, y_s in (("L", -1), ("R", 1)):
        add_printed(f"Door_{s_tag}", f"{'Driver' if y_s < 0 else 'Passenger'} Hinged Door Shell", 7, 7, (0, y_s * 42, 0),
                    "Swings `+55°` on `1.75 mm` PLA filament pins (`Ø 1.84 mm` sill press bore, `Ø 2.00 mm` door running bore).")
        add_printed(f"DoorVent_{s_tag}", f"{'Driver' if y_s < 0 else 'Passenger'} Chrome Vent Window Frame", 7, 7, (0, y_s * 26, 12),
                    "Lower tenon is captured mechanically inside the `Door` + `DoorCard` sill U-channel.")
        add_printed(f"DoorCard_{s_tag}", f"{'Driver' if y_s < 0 else 'Passenger'} Contoured Interior Door Card", 7, 7, (0, -y_s * 18, 0),
                    "`45°` rear mortise boss + upper mirror-tongue keyway snap-lock into `Door` without cantilevers.")
    add_printed("Mirror_L", "Driver Side Chrome Racing Mirror", 7, 7, (0, -24, 10),
                "Keys into the driver door upper beltline socket.")
    add_printed("Hood", "Hinged Louvered 1967 Hood (+42°)", 7, 7, (0, 0, 48),
                "Pivots `+42°` on front hinge pegs for instant battery/motor inspection.")
    add_printed("HoodProp", "Swing-Up Hood Prop Rod", 7, 7, (0, -12, 36),
                "Holds `Hood` open at `+42°` while showcasing the 289 V8 engine bay.")
    add_printed("TrunkLid", "Hinged Fastback Trunk Lid (-40°)", 7, 7, (0, 0, 46),
                "Pivots `-40°` to expose `BootTub` power switch and `Radxa Zero 3W` USB-C ports.")

    # Stage 8 (AI Edition Only): Roof Vision Scoop & Sub-Surface Rear Window Emoji HUD
    add_printed("WaymoPod", "Shelby-Style Roof Vision Scoop (`waymo_pod.stl`)", None, 8, (0, 0, 44),
                "Support-free burgundy pod seating in `Cut_WaymoSocket` over `OV5647` `160°` fisheye lens & `INMP441` mic.")
    add_printed("GC9A01Bezel", "Flush Chrome Rear Window HUD Bezel (`gc9a01_bezel.stl`)", None, 8, (18, 0, 18),
                "`0.0 mm` exterior protrusion sub-surface ring framing the `1.28\"` Round `GC9A01` `240x240` Emoji HUD.")

    # Classic RC Virtual Electronics & Filament Pins
    rc_hw = [
        ("RC_Servo1p7g", "1.7g Micro Digital Steering Servo", "rc_hw", "9.5 x 16.0 x 6.2 mm", "#1494E0", 3, None, (0, 0, 36),
         "Seats from above into `BayTub_ServoBed` behind radiator; horn pin engages `SteeringLink_HornSlot`."),
        ("RC_N25Motor", "N20/N25 / 21x11 mm Brushed Gearmotor", "rc_hw", "21.0 x 11.0 x 10.0 mm", "#E0A82E", 3, None, (0, 0, 38),
         "Drops into `BayTub_N25Bed` (`Z = 19.75 mm` shaft centerline) completely hidden beneath `EngineBlock`."),
        ("RC_FloorWire5", "5-Wire Under-Floor Conduit Bundle", "rc_hw", "3 Servo + 2 Motor Leads", "#FF9414", 3, None, (0, 0, -24),
         "Threads invisibly through the enclosed driver-side floor conduit (`Y = -8.1..-4.1 mm`) to `BootTub`."),
        ("RC_KingpinCore_L", "Left 1.75 mm Raw Filament Kingpin Core", "rc_hw", "Ø 1.75 x 7.5 mm PLA Snip", "#FF6B0A", 4, 4, (0, 0, -28),
         "Pushes up through `Cut_ChassisSteerCore_L` (`Ø 1.80 mm`) for `>8x` axial-fiber kingpin shear strength."),
        ("RC_KingpinCore_R", "Right 1.75 mm Raw Filament Kingpin Core", "rc_hw", "Ø 1.75 x 7.5 mm PLA Snip", "#FF6B0A", 4, 4, (0, 0, -28),
         "Pushes up through `Cut_ChassisSteerCore_R` (`Ø 1.80 mm`) for double-shear reinforcement."),
        ("RC_ESC5A", "5A Bi-Directional Micro Brushed ESC", "rc_hw", "18 x 13 x 5 mm (or 433MHz H-Bridge)", "#245CEB", 6, None, (0, 0, 42),
         "Seats in left bay of `BootTub`; provides smooth proportional forward/brake/reverse throttle."),
        ("RC_Rx2p4G", "2.4GHz 3-Channel Micro Hobby Receiver", "rc_hw", "14 x 10 x 4 mm", "#149E52", 6, None, (0, 0, 46),
         "Connects CH1 to front `1.7g` steering servo and CH2 to `5A` brushed ESC."),
        ("RC_LiPo2S", "1S/2S 300mAh LiPo Battery Pack", "rc_hw", "30 x 17 x 7.5 mm", "#DC2428", 6, None, (0, 0, 44),
         "Captures between `BootTub_BatRail0/1` in the right trunk bay."),
        ("RC_DoorPin_L", "Driver Door 1.75 mm Filament Hinge Pin", "rc_hw", "Ø 1.75 mm PLA Pin", "#FF6B0A", 7, 7, (0, 0, -24),
         "Presses into `Ø 1.84 mm` `Body` sill bore while `Door_L` pivots smoothly on its `Ø 2.00 mm` bore."),
        ("RC_DoorPin_R", "Passenger Door 1.75 mm Filament Hinge Pin", "rc_hw", "Ø 1.75 mm PLA Pin", "#FF6B0A", 7, 7, (0, 0, -24),
         "Presses into `Ø 1.84 mm` `Body` sill bore while `Door_R` swings `+55°`."),
    ]
    for node, label, cat, spec_str, col_hex, s_rc, s_ai, off_b, tip in rc_hw:
        parts_meta.append({
            "node": node,
            "label": label,
            "category": cat,
            "stl": spec_str,
            "plate": None,
            "in_stage1_mule": s_rc in (3, 4),
            "qty": 1,
            "colour": col_hex,
            "stage_rc": s_rc,
            "stage_ai": s_ai,
            "start_offset_3js": _blender_vec_to_three(off_b),
            "tip": tip,
        })

    # AI Edition Real-Datasheet 14 BOM Modules + HUD Screen + H1..H5 Harnesses
    bom_stage_map = {
        "BOM_08_VL53L1X_ToF": (3, (-20, 0, 32), "Front valance `< 20 ms` emergency auto-brake laser sensor (`BayTub_ToFSlot`)."),
        "BOM_11_Servo_1p7g": (3, (0, 0, 34), "Front `1.7g` digital PWM servo (`PWM14_M0`) seated in `BayTub_ServoBed`."),
        "BOM_09_N25_Gearmotor": (3, (0, 0, 38), "`N25` 6V 300-500 RPM gearmotor (`Ø 3.0 mm` D-shaft) in `BayTub_N25Bed`."),
        "BOM_10_DRV8833_HBridge": (6, (0, -18, 34), "`DRV8833` dual H-bridge motor driver stacked in lower `Tub_AIAmpDrvBay`."),
        "BOM_06_MAX98357A_Amp": (6, (0, -18, 40), "`MAX98357A` 3W Class-D I2S audio amp stacked in upper `Tub_AIAmpDrvBay`."),
        "BOM_07_Speaker_1524": (6, (0, 18, 36), "`15 x 24 x 4 mm` sealed micro speaker seated in `Tub_AISpeakerBay`."),
        "BOM_12_LiPo_2S_350mAh": (6, (0, 0, 42), "`2S 7.4V 350mAh` LiPo pack on the open `45 mm` `BootTub_AIClearFloor`."),
        "BOM_13_BEC_5V_3A": (6, (0, 0, 44), "`5V 3A` synchronous buck regulator powering `Radxa Zero 3W` (`H5`)."),
        "BOM_15_SlideSwitch_SS12D00": (6, (0, 0, 44), "`SS12D00G3` main battery power slide switch in right `BootTub` pocket."),
        "BOM_01_Radxa_Zero_3W": (6, (40, 0, 26), "`Radxa Zero 3W` (`RK3566` 4GB + Wi-Fi 6) sliding onto `Z = 37.8 mm` L-rail sled."),
        "BOM_04_GC9A01_Display": (8, (0, 0, -28), "Waveshare `1.28\"` Round `GC9A01` `240x240` SPI IPS display (`< 12 mm` drop to GPIO)."),
        "BOM_02_OV5647_Camera": (8, (0, 0, 36), "`OV5647` `160°` fisheye M12 camera (`-9°` pitch) seated in `Cut_WaymoCamWell`."),
        "BOM_03_CSI_Ribbon_15to22": (8, (0, 0, 34), "15-to-22-pin MIPI CSI-2 FPC ribbon dropping straight down `Cut_WaymoChimney`."),
        "BOM_05_INMP441_Mic": (8, (0, 0, 40), "`INMP441` omnidirectional I2S MEMS mic for `" + '"Hey Mustang"' + "` wake word & barge-in."),
    }
    for spec in ai_edition.BOM_HARDWARE_SPECS:
        b_name = spec["name"]
        s_ai, off_b, tip = bom_stage_map[b_name]
        rgba = spec["color"]
        hex_c = "#{:02X}{:02X}{:02X}".format(int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))
        dims = " x ".join(str(d) for d in spec["datasheet_dims_mm"]) + " mm"
        parts_meta.append({
            "node": b_name,
            "label": spec["label"],
            "category": "ai_bom",
            "stl": f"{spec['bom_id']} ({dims})",
            "plate": None,
            "in_stage1_mule": s_ai in (3, 6),
            "qty": 1,
            "colour": hex_c,
            "stage_rc": None,
            "stage_ai": s_ai,
            "start_offset_3js": _blender_vec_to_three(off_b),
            "tip": tip,
        })

    parts_meta.append({
        "node": "AI_GC9A01_Screen",
        "label": "GC9A01 240x240 Expressive Emoji HUD Screen",
        "category": "ai_bom",
        "stl": "Ø 32.4 mm Active IPS Matrix",
        "plate": None,
        "in_stage1_mule": False,
        "qty": 1,
        "colour": "#0DE0F5",
        "stage_rc": None,
        "stage_ai": 8,
        "start_offset_3js": _blender_vec_to_three((0, 0, -28)),
        "tip": "Renders 12 live expressive vector emojis (`HAPPY`, `HEART_EYES`, `ALERT_STOP`, `THINKING`, etc.) at `240x240`.",
    })

    ai_cables_meta = [
        (
            "AI_Cab_H4_Motor", "Harness H4-A: Motor Drive Leads (`DRV8833 -> N25`)",
            "#FF381F", 3, "Routes through driver-side floor conduit.",
        ),
        (
            "AI_Cab_H4_Servo", "Harness H4-B: Steering PWM (`PWM14_M0 -> 1.7g Servo`)",
            "#FFAD14", 3, "Routes through driver-side floor conduit.",
        ),
        ("AI_Cab_H4_ToF", "Harness H4-C: Laser I2C (`I2C3 -> VL53L1X ToF`)", "#598CFF", 3, "400 kHz I2C front reflex bus."),
        ("AI_Cab_H5_Power", "Harness H5: 2S LiPo + 5V 3A BEC Power Bus", "#FF1F2E", 6, "Powers Radxa Zero 3W + motor H-bridge."),
        (
            "AI_Cab_H3_AudioDrv", "Harness H3-A: I2S0 Audio & Motor Logic (`GPIO -> Amp/DRV`)",
            "#F238BF", 6, "Short rear-deck GPIO jumper harness.",
        ),
        (
            "AI_Cab_H3_SpeakerPair", "Harness H3-B: Speaker Twisted Pair (`MAX98357A -> 1524`)",
            "#1AEBD1", 6, "Crosses rear deck above shaft tunnel.",
        ),
        (
            "AI_Cab_H2_HUD", "Harness H2: SPI3 Display Drop (`< 12 mm` to `GC9A01`)",
            "#0DE0FF", 8, "Ultra-short SPI3 drop from rear glass to Radxa header.",
        ),
        (
            "AI_Cab_H1_CSIRibbon", "Harness H1-A: MIPI CSI-2 Camera Ribbon (`OV5647 -> Radxa`)",
            "#FF8C14", 8, "Drops vertically down `Cut_WaymoChimney`.",
        ),
        (
            "AI_Cab_H1_MicI2S", "Harness H1-B: I2S0 Mic Harness (`INMP441 -> Radxa`)",
            "#26F273", 8, "Shielded 5-wire MEMS mic run down roof chimney.",
        ),
    ]
    for c_node, c_lbl, c_hex, s_ai, c_tip in ai_cables_meta:
        parts_meta.append({
            "node": c_node,
            "label": c_lbl,
            "category": "ai_cable",
            "stl": "40-Pin Radxa Harness",
            "plate": None,
            "in_stage1_mule": s_ai in (3, 6),
            "qty": 1,
            "colour": c_hex,
            "stage_rc": None,
            "stage_ai": s_ai,
            "start_offset_3js": [0.0, 12.0, 0.0],
            "tip": c_tip,
        })

    stages_common_1_to_7 = [
        {
            "stage": 1,
            "title": "Fastback Shell & Multi-Colour Glass Inlays",
            "vector": "Plate 1 Assembled Print",
            "xray": False,
            "camera": {"pos": [-165, 95, 195], "target": [112, 34, 0]},
            "summary": "Print `body.stl` with flush black `windshield.stl` and `rear_glass.stl` inlays in one multi-colour job on Plate 1.",
            "bullets": [
                "Lofted from 1967 Mustang station tables at `1:20` scale (`226 x 91 x 66 mm`).",
                "Zero hand-sculpted polygons: every louver, V-prow crease, and recess is procedural Python CAD.",
            ],
        },
        {
            "stage": 2,
            "title": "Twin-Cowl Cabin & Front Bay Liners",
            "vector": "+Z Bottom-Up Slide",
            "xray": True,
            "camera": {"pos": [-115, 110, 185], "target": [105, 28, 0]},
            "summary": (
                "Plug `SteeringWheel` into the 5-pod twin-cowl dash, then push `InteriorTub` "
                "and `BayTub` straight up (`+Z`) into `Body`."
            ),
            "bullets": [
                "Open-bottom `45°` gable shaft tunnels allow drop-in bottom-up driveshaft installation.",
                "Dedicated driver-side wire conduit (`4.0 x 5.05 mm`) isolates wiring from the spinning shaft.",
            ],
        },
        {
            "stage": 3,
            "title": "Motor, Servo, Conduit & Open-Bottom Driveshaft",
            "vector": "+Z U-Channel & Conduit",
            "xray": True,
            "camera": {"pos": [-85, 88, 155], "target": [85, 24, 0]},
            "summary": (
                "Seat the front `1.7g` servo and `N25` gearmotor (+ Z-shims & multi-fit `MotorCoupler`), "
                "thread the floor conduit, and lift `Driveshaft + PinionGear` (`7T`) into the open-bottom U-channel."
            ),
            "bullets": [
                "4 indexed couplers on Plate 6 fit `Ø 1.0 mm`, `Ø 1.5 mm`, silicone sleeve, or `Ø 3.0 mm` N25 D-shafts.",
                "Horizontal bed-flat octagonal `Driveshaft` (`+63%` torsional stiffness) prints with zero supports.",
            ],
        },
        {
            "stage": 4,
            "title": "Filament-Core Kingpins, 9T Live Axle & Wheels",
            "vector": "Rolling Sub-Assembly",
            "xray": True,
            "camera": {"pos": [-110, -35, 175], "target": [110, 14, 0]},
            "summary": (
                "Slide `1.75 mm` PLA filament cores into `Chassis` kingpins, snap `Knuckle_L/R` + `SteeringLink`, "
                "thread the `3.60 mm` octagonal `Axle_R` through `AxleGear` (`9T`) + `DiffCover`, "
                "and hand-slide the 4 `6`-key tires onto the rims."
            ),
            "bullets": [
                "`7.5 mm` snips of raw `1.75 mm` filament inside `Ø 2.60 mm` kingpins give `> 8x` shear strength.",
                "Zero-undercut `6`-key tires slide onto reinforced `1.80 mm`-lip Torq-Thrust rims by hand.",
            ],
        },
        {
            "stage": 5,
            "title": "Straight +Z Rolling Chassis Marriage",
            "vector": "+Z 9-Boss Snap Lock",
            "xray": True,
            "camera": {"pos": [245, 58, 155], "target": [125, 22, 0]},
            "summary": (
                "Push the complete rolling `Chassis` straight up (`+Z`) onto `Body`: 9 mortise-and-tenon bosses "
                "lock `BayTub` and `InteriorTub`, `PinionGear` (`7T`) meshes at `90°` with `AxleGear` (`9T`), "
                "and the servo horn engages `SteeringLink`."
            ),
            "bullets": [
                "Kingpin top tips seat `1.30 mm` deep into `Body` sockets for true double-shear support.",
                "Collared `7T:9T` bevel differential transfers smooth forward & reverse torque to the live rear axle.",
            ],
        },
        {
            "stage": 6,
            "title": "289 V8 Motor Shroud & Rear Electronics Deck",
            "vector": "-Z Top-Down Drop",
            "xray": True,
            "camera": {"pos": [-95, 118, 145], "target": [115, 34, 0]},
            "summary": (
                "Lower the hollowed Ford-blue 289 `EngineBlock` (+ Cobra valve covers & air cleaner) "
                "straight down (`-Z`) over the `N25` motor, and install `BootTub` + rear power/control modules in the trunk."
            ),
            "bullets": [
                "`EngineBlock` completely disguises the electric motor with `0.45 mm` vertical booster clearance.",
                "Classic RC houses `2.4GHz Rx + 5A ESC + LiPo` (or 4-wire keyfob); AI Edition mounts the 2-story `Radxa Zero 3W` deck.",
            ],
        },
        {
            "stage": 7,
            "title": "1.75 mm Filament Door Hinges, Chrome & Panels",
            "vector": "Pin-Hinge & Trim Lock",
            "xray": False,
            "camera": {"pos": [-155, 78, 190], "target": [112, 30, 0]},
            "summary": (
                "Snap chrome bumpers, grille, and tri-bar taillights onto `Body`, interlock `DoorVent` + `DoorCard` "
                "into `Door_L/R` on `1.75 mm` filament hinge pins, and seat `Hood` (`+42°`) & `TrunkLid` (`-40°`)."
            ),
            "bullets": [
                "`Ø 1.84 mm` sill press bore + `Ø 2.00 mm` door bore turn raw `1.75 mm` filament into crisp `+55°` door hinges.",
                "Car is now 100% assembled and ready to steer, spin gears, and open all 4 hinged panels!",
            ],
        },
    ]

    stage_8_ai = {
        "stage": 8,
        "title": "AI Roof Vision Pod & Rear Window Emoji HUD",
        "vector": "Sub-Surface Option B",
        "xray": False,
        "camera": {"pos": [255, 96, 150], "target": [148, 48, 0]},
        "summary": (
            "Seat the `OV5647` `160°` fisheye camera + `INMP441` mic under `WaymoPod` (routing `H1` down `Cut_WaymoChimney`), "
            "and mount the `1.28\"` Round `GC9A01` `240x240` IPS display flush inside `Glass_Rear` with `GC9A01Bezel`."
        ),
        "bullets": [
            "`0.0 mm` exterior protrusion rear-window Emoji HUD with `< 12 mm` SPI3 jumper drop (`H2`) to `Radxa Zero 3W`.",
            'Unlocks `gemini-robotics-er-2-streaming` maneuvers, `< 20 ms` `VL53L1X` brake reflex, and `"Hey Mustang"` voice!',
        ],
    }

    manifest = {
        "project": "1967 Ford Mustang Fastback (`e-Mustang`) - 1:20 Printable RC & Gemini AI Studio",
        "version": "3.6.0",
        "scale": "1:20",
        "dimensions_mm": [226, 91, 66],
        "assets": {
            "rc_glb": "assets/mustang_rc.glb",
            "rc_glb_bytes": rc_bytes,
            "ai_delta_glb": "assets/mustang_ai_delta.glb",
            "ai_delta_glb_bytes": ai_bytes,
        },
        "counts": {
            "classic_rc": {"parts": 67, "stls": 53, "pieces": 73, "plates": 9},
            "ai_edition": {"parts": 69, "stls": 55, "pieces": 75, "plates": 9, "bom_modules": 14, "harnesses": 5},
            "stage1_mule": {"stls": 16, "pieces": 23, "print_time_hrs": 2.5},
        },
        "kinematics": {
            "hood_max_deg": engine_bay.HOOD_OPEN_DEG,
            "trunk_max_deg": engine_bay.TRUNK_OPEN_DEG,
            "door_max_deg": doors.OPEN_DEG,
            "steer_max_deg": 15.0,
            "steering_link_shift_mm": 0.83,
            "bevel_gear_ratio_pinion_to_axle": [7, 9],
            "hinge_pivots_3js": hinge_pivots_3js,
        },
        "plates": PLATES_SPEC,
        "stages_rc": stages_common_1_to_7,
        "stages_ai": stages_common_1_to_7 + [stage_8_ai],
        "ai_swapped_shells": ["Body", "Glass_Rear", "InteriorTub", "BootTub", "BayTub"],
        "parts": parts_meta,
    }

    manifest_path = os.path.join(WEB_ASSETS_DIR, "assembly_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path, manifest


def main():
    os.makedirs(WEB_ASSETS_DIR, exist_ok=True)
    rc_bytes, pivots = export_classic_rc_glb()
    ai_bytes = export_ai_delta_glb()
    manifest_path, manifest = build_assembly_manifest(rc_bytes, ai_bytes, pivots)
    sys.stderr.write(
        f"\n[export_web] OK: mustang_rc.glb={rc_bytes / 1024 / 1024:.2f} MB | "
        f"mustang_ai_delta.glb={ai_bytes / 1024 / 1024:.2f} MB | "
        f"parts={len(manifest['parts'])} -> {manifest_path}\n"
    )


if __name__ == "__main__":
    main()
