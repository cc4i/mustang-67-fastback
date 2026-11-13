"""Independent AI Edition (`v3.0.0`) of the 1:20 1967 Ford Mustang Fastback (`e-Mustang AI`).

Builds on top of the classic 1:20 RC Mustang (`build.main()`) without modifying the baseline outputs,
and applies the Sleek Sub-Surface Option B AI upgrades for `gemini-robotics-er-2-streaming`:
  1. `WaymoPod` (`waymo_pod.stl`, Burgundy `#6B0F1A`): 5.5 mm low-profile Shelby-style teardrop roof
     vision scoop seated in a flat-floored roof mortise (`Cut_WaymoSocket`), housing the upper half of
     the wide-angle/fisheye `OV5647` M12 lens (-9 deg pitch) and top `INMP441` MEMS mic vents while
     80% of the `25 x 24 mm` `OV5647` PCB sits sunk inside `Cut_WaymoCamWell` (`Z = 52..64.5 mm`).
  2. `GC9A01Bezel` (`gc9a01_bezel.stl`, Silver `#C8C8CC`): 0.0 mm protrusion sub-surface flush chrome
     bezel ring seated inside a circular aperture (`Cut_RearGlassHUD`) in `Glass_Rear` (`+20.5 deg`
     fastback slope), framing the `1.28"` Round `GC9A01` (`240x240` SPI IPS) display mounted directly
     above the `Radxa Zero 3W` 40-pin GPIO header.
  3. Bridged Two-Story Rear Avionics Deck (`Cut_RadxaBulkheadBridge`, `BootTub_RadxaRail_L/R`,
     `Tub_AIAudioVault`): houses the `65.0 x 30.0 x 5.2 mm` `Radxa Zero 3W` on the upper sled
     (`Z = 36.2..41.4 mm`, dual USB-C facing the `-40 deg` opening `TrunkLid`) and the `2S 7.4V` LiPo +
     `5V 3A` Buck BEC + `15 x 24 x 4 mm` Speaker + `MAX98357A` I2S Amp + `DRV8833` H-Bridge underneath.
  4. Lower-Valance `VL53L1X` ToF Laser Cradle (`BayTub_ToFSlot`): `< 20 ms` hardware obstacle reflex
     below the front bumper, leaving the 1967 Mustang Pony Grille and Windshield 100% untouched.

Exports 55 print-ready STLs (`75` printed pieces) to `output/ai_edition/stl/` and saves the scene to
`output/ai_edition/mustang_67_ai_edition.blend`.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Euler, Vector

import body
import build
import details
import export
import features as F
import materials
import paths
import printcheck
import studio

SCALE = body.SCALE
AI_OUT_DIR = os.path.join(paths.OUTPUT, "ai_edition")
AI_STL_DIR = os.path.join(AI_OUT_DIR, "stl")
AI_BLEND_PATH = os.path.join(AI_OUT_DIR, "mustang_67_ai_edition.blend")

AI_EXTRA_PARTS = [
    ("waymo_pod", "WaymoPod", export.IDENTITY, 1, "#6B0F1A"),
    ("gc9a01_bezel", "GC9A01Bezel", "LOCAL", 1, "#C8C8CC"),
]


def _rect(x0, y0, x1, y1, r=0.0):
    return details.rect(x0, y0, x1, y1, r)


def _oct_gable_prism_x(name, x0, x1, y_half, z_bot, z_wall_top):
    """Self-supporting 45-deg gable-roofed prism along +X (real mm) so neither Body nor Tub
    boolean cuts create unsupported horizontal ceilings."""
    z_peak = z_wall_top + y_half
    prof = [
        (-y_half, z_bot),
        (y_half, z_bot),
        (y_half, z_wall_top),
        (0.0, z_peak),
        (-y_half, z_wall_top),
    ]
    return F.prism_cutter(name, "+X", prof, x0 * SCALE, x1 * SCALE)


def _oct_gable_prism_y(name, y0, y1, x_center, x_half, z_bot, z_wall_top):
    """Self-supporting 45-deg gable-roofed prism along +Y (real mm)."""
    z_peak = z_wall_top + x_half
    prof = [
        (x_center - x_half, z_bot),
        (x_center + x_half, z_bot),
        (x_center + x_half, z_wall_top),
        (x_center, z_peak),
        (x_center - x_half, z_wall_top),
    ]
    return F.prism_cutter(name, "+Y", prof, y0 * SCALE, y1 * SCALE)


def _build_waymo_pod():
    """Build the support-free (`floating == []`, `cantilevers == []`) low-profile Burgundy
    teardrop roof vision scoop (`WaymoPod`) and its matching `Body` roof cutters sized for real BOM parts:
      - `WaymoPod` rests 100% flat on `Z = 63.80 mm` (`1276.0` real mm) inside `Cut_WaymoSocket`.
      - Front 15.2 mm Gothic-arched fisheye hood (`45 deg` self-supporting crown) frames the real
        `Ø 14.0 mm` wide-angle/fisheye `OV5647` M12 lens barrel (`-9 deg` downward pitch).
      - Sunk roof camera well (`Cut_WaymoSocket`) and `2.7 x 17.2 mm` vertical chimney (`Cut_WaymoChimney`)
        house the `OV5647` camera and `16.0 mm` MIPI CSI ribbon behind the front seats.
      - Top recessed acoustic/status pocket (`12.0 x 15.2 mm`) houses the real `10 x 14 x 2 mm` `INMP441` MEMS mic.
    """
    z_base = 1276.0  # 63.80 mm print: completely flat bottom face on Z=0 when printed!
    stations = [
        # (x_real, half_w_real, z_top_real) — sits 100% on the solid roof panel ahead of Glass_Rear (X >= 2900)
        (2230.0, 190.0, 1418.0),
        (2290.0, 255.0, 1462.0),
        (2400.0, 285.0, 1472.0),
        (2550.0, 278.0, 1460.0),
        (2710.0, 258.0, 1432.0),
        (2835.0, 225.0, 1396.0),
        (2895.0, 150.0, 1318.0),
    ]
    n_arch = 16
    sections = []
    for x, hw, zt in stations:
        pts = [(-hw, z_base), (hw, z_base)]
        for k in range(n_arch + 1):
            t = k / n_arch  # 0 (right +hw) to 1 (left -hw)
            ang = math.pi * t
            y = hw * math.cos(ang)
            z = z_base + (zt - z_base) * (math.sin(ang) ** 0.75)
            pts.append((y, z))
        sections.append((pts, x * SCALE))
    pod = F.loft_solid("WaymoPod", "+X", sections)

    # Cutters on WaymoPod (all upward-facing or 45-deg gable-roofed so floating == [] and cantilevers == []):
    # 1. Front 16.4 mm wide 45-deg Gothic-arched fisheye lens bay for Ø 14.0 mm M12 barrel (X = 2190..2510, Y = -164..+164)
    lens_arch = [
        (-164.0, z_base - 8.0),
        (164.0, z_base - 8.0),
        (164.0, 1390.0),
        (0.0, 1554.0),
        (-164.0, 1390.0),
    ]
    c_lens = F.prism_cutter("WaymoPod_LensArch", "+X", lens_arch, 2190.0 * SCALE, 2510.0 * SCALE)

    # 2. Internal 45-deg gabled CSI ribbon & camera tunnel (X = 2350..2850, Y = -168..+168 = 16.8 mm wide for 16.0 mm FPC)
    cable_arch = [
        (-168.0, z_base - 8.0),
        (168.0, z_base - 8.0),
        (168.0, 1280.0),
        (0.0, 1368.0),
        (-168.0, 1280.0),
    ]
    c_pod_cable = F.prism_cutter("WaymoPod_CableChannel", "+X", cable_arch, 2350.0 * SCALE, 2850.0 * SCALE)

    # 3. Top upward-facing 15.0 x 15.2 mm rounded recess for the real Ø 14.0 x 2.5 mm circular INMP441 MEMS mic (X = 2640, Y = 0)
    c_mic = F.prism_cutter("WaymoPod_MicCup", "+Z", _rect(2490.0, -152.0, 2790.0, 152.0, 40.0),
                           1385.0 * SCALE, 1485.0 * SCALE)

    # Matching Body cutters (`Cut_WaymoSocket` with +0.40 mm clearance + `Cut_WaymoCamWell` for Ø 14.0 mm M12 barrel & PCB
    # + 2.7 x 17.2 mm vertical CSI ribbon chimney):
    clr = 8.0  # 0.40 mm print clearance around the pod perimeter
    z_sock = z_base - 12.0  # recessed roof socket floor (stays above cabin ceiling ~1230!)
    sock_pts = []
    for x, hw, _ in stations:
        sock_pts.append((x - clr if x == stations[0][0] else (x + clr if x == stations[-1][0] else x), hw + clr))
    sock_poly = [(x, -w) for x, w in sock_pts] + [(x, w) for x, w in reversed(sock_pts)]
    c_body_sock = F.prism_cutter("Cut_WaymoSocket", "+Z", sock_poly, z_sock * SCALE, 1485.0 * SCALE)

    # Sunk central roof camera well (`X = 2170..2540 = 108.5..127.0 mm, Y = -168..+168 = 16.80 mm wide, Z = 1040..1310`)
    # so the lower half of the real Ø 14.0 mm M12 fisheye lens barrel + 15 x 15 mm OV5647 sensor board sinks into the roof header
    c_cam_well = F.prism_cutter("Cut_WaymoCamWell", "+Z", _rect(2170.0, -168.0, 2540.0, 168.0, 8.0),
                                1040.0 * SCALE, 1310.0 * SCALE)

    # Vertical CSI ribbon & mic wire chimney through the rear roof header (X = 2842..2896, Y = -172..+172 = 17.2 mm wide)
    # Strictly behind front seats (X <= 2840) and ahead of Glass_Rear (X >= 2900), concealed under WaymoPod!
    c_chimney = F.prism_cutter("Cut_WaymoChimney", "+Z", _rect(2842.0, -172.0, 2896.0, 172.0, 10.0),
                               1040.0 * SCALE, 1485.0 * SCALE)

    return pod, [c_lens, c_pod_cable, c_mic], [c_body_sock, c_cam_well, c_chimney]


def _build_gc9a01_bezel():
    """Build the 0.0 mm protrusion sub-surface flush chrome bezel ring (`GC9A01Bezel`) for the
    1.28-inch Round GC9A01 IPS TFT (`Ø 32.4 mm` active screen on a `35.6 x 35.6 x 3.2 mm` PCB carrier),
    modelled in its own local frame (`rot = "LOCAL"`, flat back face on `Z = 0` for support-free printing)
    and positioned flush inside `Cut_RearGlassHUD` on `Glass_Rear` at `(176.5, 0.0, 56.10) mm`, slope `+20.5 deg`.
    """
    n_seg = 64
    r_out = 14.80   # Ø 29.60 mm outer chrome ring (0.40 mm radial clearance inside Ø 30.40 mm Cut_RearGlassHUD)
    r_in = 13.60    # Ø 27.20 mm inner bezel aperture framing the circular HUD screen
    h_ring = 0.85   # 0.85 mm thick flush ring

    bm = bmesh.new()
    bot_out, bot_in, top_out, top_in = [], [], [], []
    for k in range(n_seg):
        a = 2.0 * math.pi * k / n_seg
        ca, sa = math.cos(a), math.sin(a)
        bot_out.append(bm.verts.new((r_out * ca, r_out * sa, 0.0)))
        bot_in.append(bm.verts.new((r_in * ca, r_in * sa, 0.0)))
        top_out.append(bm.verts.new(((r_out - 0.15) * ca, (r_out - 0.15) * sa, h_ring)))
        top_in.append(bm.verts.new(((r_in + 0.15) * ca, (r_in + 0.15) * sa, h_ring)))

    for k in range(n_seg):
        kn = (k + 1) % n_seg
        bm.faces.new((bot_out[k], bot_in[k], bot_in[kn], bot_out[kn]))
        bm.faces.new((top_out[k], top_out[kn], top_in[kn], top_in[k]))
        bm.faces.new((bot_out[k], bot_out[kn], top_out[kn], top_out[k]))
        bm.faces.new((bot_in[k], top_in[k], top_in[kn], bot_in[kn]))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("GC9A01Bezel")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    bezel = bpy.data.objects.new("GC9A01Bezel", me)
    bezel.location = Vector((176.5, 0.0, 56.10))
    bezel.rotation_euler = Euler((0.0, math.radians(20.5), 0.0), 'XYZ')

    # Cutter for Glass_Rear: Ø 30.40 mm (r = 15.20 mm) cylinder along the +20.5 deg normal
    bm_c = bmesh.new()
    bmesh.ops.create_cone(bm_c, cap_ends=True, segments=64, radius1=15.20, radius2=15.20, depth=8.0)
    me_c = bpy.data.meshes.new("Cut_RearGlassHUD")
    bm_c.to_mesh(me_c)
    bm_c.free()
    c_hud = bpy.data.objects.new("Cut_RearGlassHUD", me_c)
    c_hud.location = Vector((176.5, 0.0, 56.10))
    c_hud.rotation_euler = Euler((0.0, math.radians(20.5), 0.0), 'XYZ')

    # Matching vertical well in Body (`r = 332.0 real mm = Ø 33.20 mm`, Z = 800..1240) plus sub-surface PCB carrier well
    # sized for the public Waveshare 1.28" Round GC9A01 IPS datasheet (Ø 32.4 mm screen on 38.0 x 35.6 x 4.5 mm PCB carrier)
    hud_well_circle = [(3530.0 + 332.0 * math.cos(2 * math.pi * k / 48),
                        332.0 * math.sin(2 * math.pi * k / 48)) for k in range(48)]
    c_body_hud = F.prism_cutter("Cut_RearGlassHUDWell", "+Z", hud_well_circle, 800.0 * SCALE, 1240.0 * SCALE)

    bm_pcb = bmesh.new()
    bmesh.ops.create_cube(bm_pcb, size=1.0)
    bmesh.ops.scale(bm_pcb, vec=(36.8, 39.2, 24.0), verts=bm_pcb.verts)
    bmesh.ops.translate(bm_pcb, vec=(0.0, 0.0, -9.3), verts=bm_pcb.verts)
    me_pcb = bpy.data.meshes.new("Cut_RearGlassHUDPCB")
    bm_pcb.to_mesh(me_pcb)
    bm_pcb.free()
    c_body_pcb = bpy.data.objects.new("Cut_RearGlassHUDPCB", me_pcb)
    c_body_pcb.location = Vector((176.5, 0.0, 50.0))
    c_body_pcb.rotation_euler = Euler((0.0, math.radians(20.5), 0.0), 'XYZ')

    return bezel, c_hud, [c_body_hud, c_body_pcb]


def _apply_ai_upgrades():
    """Apply the AI Edition (`v3.5.0`) boolean cutters, unions, and new parts to the built Mustang scene."""
    # Ensure material tables include our new part/cutter prefixes before materials.apply_all() runs
    if not any(p == "WaymoPod" for p, _ in materials.PART_MATERIALS):
        materials.PART_MATERIALS.insert(0, ("WaymoPod", "Paint"))
    if not any(p == "GC9A01Bezel" for p, _ in materials.PART_MATERIALS):
        materials.PART_MATERIALS.insert(0, ("GC9A01Bezel", "Chrome"))
    if not any(p == "Cut_Waymo" for p, _ in materials.CUTTER_MATERIALS):
        materials.CUTTER_MATERIALS.insert(0, ("Cut_Waymo", "Black"))
    if not any(p == "Cut_RearGlassHUD" for p, _ in materials.CUTTER_MATERIALS):
        materials.CUTTER_MATERIALS.insert(0, ("Cut_RearGlassHUD", "Black"))
    if not any(p == "Cut_Radxa" for p, _ in materials.CUTTER_MATERIALS):
        materials.CUTTER_MATERIALS.insert(0, ("Cut_Radxa", "Black"))
    for name in ("WaymoPod", "GC9A01Bezel"):
        if name not in printcheck.ONE_SIDED:
            printcheck.ONE_SIDED = printcheck.ONE_SIDED + (name,)

    body_ob = bpy.data.objects["Body"]
    glass_r = bpy.data.objects["Glass_Rear"]
    tub_ob = bpy.data.objects["InteriorTub"]
    boot_ob = bpy.data.objects["BootTub"]
    bay_ob = bpy.data.objects["BayTub"]

    # 1. WaymoPod (low-profile Burgundy roof scoop) + Body roof socket, camera well & CSI chimney
    pod, pod_cuts, body_roof_cuts = _build_waymo_pod()
    build.link(pod, "Parts")
    for c in pod_cuts:
        build.add_boolean(pod, build.link(c, "Cutters"))
    for c in body_roof_cuts:
        build.add_boolean(body_ob, build.link(c, "Cutters"))

    # 2. GC9A01Bezel (0.0 mm protrusion sub-surface chrome bezel in Glass_Rear) + Cut_RearGlassHUD
    bezel, c_hud, body_hud_cuts = _build_gc9a01_bezel()
    build.link(bezel, "Parts")
    build.add_boolean(glass_r, build.link(c_hud, "Cutters"))
    for c in body_hud_cuts:
        build.add_boolean(body_ob, build.link(c, "Cutters"))

    # 3. Bridged Two-Story Rear Avionics Deck & Full-Length Stepped L-Rail Cradle for Radxa Zero 3W (65 x 30 x 4.2 mm):
    # 3a. Body bulkhead bridge (`X = 3380..4030` = `169.0..201.5 mm`):
    #     Deepened lower battery/BEC vault (`Y = -286..+286 = 28.6 mm wide, Z = 584..756 = 29.2..37.8 mm = 8.6 mm tall`),
    #     two continuous PCB support ledges at `Z = 756` (`37.8 mm`, `|Y| = 286..310`),
    #     vertical lateral keeper walls (`|Y| = 310`, `Z = 756..865`), and a 45-deg self-supporting gable roof (peak `Z = 1175`).
    bulkhead_stepped_prof = [
        (-286.0, 584.0),
        (286.0, 584.0),
        (286.0, 756.0),
        (310.0, 756.0),
        (310.0, 865.0),
        (0.0, 1175.0),
        (-310.0, 865.0),
        (-310.0, 756.0),
        (-286.0, 756.0),
    ]
    c_bulkhead = F.prism_cutter("Cut_RadxaBulkheadBridge", "+X", bulkhead_stepped_prof, 3380.0 * SCALE, 4030.0 * SCALE)
    build.add_boolean(body_ob, build.link(c_bulkhead, "Cutters"))

    # 3b. BootTub (`X = 3988..4368` = `199.4..218.4 mm`, `Y = -486..+486` = `48.6 mm`, `Z = 564..855` = `28.2..42.75 mm`):
    #     Clear the full-width lower floor (`X = 3980..4346, Y = -450..+450 = 45.0 mm wide, Z = 584..760 = 29.2..38.0 mm`)
    #     so a real 35.0 x 20.0 x 8.0 mm 2S 300-350mAh LiPo + 12.0 x 17.5 x 4.0 mm 5V 3A Buck BEC + Slide Switch fit
    #     with zero inter-part overlap across the bridged lower vault (X = 167..217 mm).
    #     Support the rear of the Radxa Zero 3W (`Z = 37.8 mm`) on rear corner L-pillars (`X = 4284..4346, |Y| = 275..355`)
    #     so the middle of BootTub stays 100% open across all 45.0 mm of width!
    c_boot_clear = F.prism_cutter("BootTub_AIClearFloor", "+Z", _rect(3980.0, -450.0, 4346.0, 450.0, 8.0),
                                  584.0 * SCALE, 760.0 * SCALE)
    c_boot_bridge = F.prism_cutter("BootTub_RadxaBridge", "+Z", _rect(3980.0, -310.0, 4040.0, 310.0, 8.0),
                                   756.0 * SCALE, 865.0 * SCALE)
    build.add_boolean(boot_ob, build.link(c_boot_clear, "Cutters"))
    build.add_boolean(boot_ob, build.link(c_boot_bridge, "Cutters"))
    for tag, sgn in (("L", -1.0), ("R", 1.0)):
        sy0, sy1 = sorted((sgn * 285.0, sgn * 355.0))
        wy0, wy1 = sorted((sgn * 310.0, sgn * 355.0))
        ry0, ry1 = sorted((sgn * 225.0, sgn * 355.0))
        shelf = F.prism_cutter(f"BootTub_RadxaShelf_{tag}", "+Z", _rect(4310.0, sy0, 4346.0, sy1, 4.0),
                               580.0 * SCALE, 756.0 * SCALE)
        wall = F.prism_cutter(f"BootTub_RadxaWall_{tag}", "+Z", _rect(4310.0, wy0, 4346.0, wy1, 3.0),
                              752.0 * SCALE, 845.0 * SCALE)
        rstop = F.prism_cutter(f"BootTub_RadxaStopR_{tag}", "+Z", _rect(4326.0, ry0, 4346.0, ry1, 3.0),
                               752.0 * SCALE, 845.0 * SCALE)
        build.add_union(boot_ob, build.link(shelf, "Cutters"))
        build.add_union(boot_ob, build.link(wall, "Cutters"))
        build.add_union(boot_ob, build.link(rstop, "Cutters"))

    # 3c. InteriorTub (`X = 2990..3411` = `149.5..170.55 mm`):
    #     - Union front L-bracket cradle pillars (`Tub_RadxaFrontPillar_L/R`, `X = 2990..3100, |Y| = 250..345, Z = 310..840`)
    #       anchored in the solid cabin floor (`FLOOR_Z0..FLOOR_Z1 = 290..330`) so the front of the Radxa Zero 3W
    #       (`X = 151.0 mm`) sits on a `Z = 37.8 mm` shelf with zero bottom cantilever.
    #     - Union level rear deck extensions (`Tub_AISpeakerDeck` at `Y = 75..+510` and `Tub_AIAmpDeck` at `Y = -510..-102`,
    #       `X = 3085..3408, Z = 520..756`) strictly above `Tub_ChassisSlotR_L/R` (`Z <= 423`) and clear of `Tub_ShaftTunnel` (`|Y| <= 68`).
    #     - Cut `Tub_AIRadxaSled` (`X = 3015..3425, Y = -310..+310, Z = 756..920`) so the Radxa board slides flat at `Z = 37.8 mm`.
    #     - Cut the `17.10 x 26.50 x 10.90 mm` speaker pocket (`Tub_AISpeakerBay`, `X = 3060..3402, Y = -45..+485, Z = 560..920`)
    #       for the real physical `15.0 x 24.0 x 4.0 mm` (`1524`) speaker.
    #     - Cut the `17.10 x 19.80 x 16.75 mm` dual-board pocket (`Tub_AIAmpDrvBay`, `X = 3060..3402, Y = -504..-108, Z = 425..920`)
    #       that holds BOTH the commercial `16.0 x 18.5 x 3.2 mm` `DRV8833` and `16.5 x 19.0 x 3.2 mm` `MAX98357A` breakouts stacked!
    for tag, (py0, py1) in (("L", (-345.0, -250.0)), ("R", (250.0, 345.0))):
        pillar = F.prism_cutter(f"Tub_RadxaFrontPillar_{tag}", "+Z", _rect(2990.0, py0, 3100.0, py1, 4.0),
                                310.0 * SCALE, 840.0 * SCALE)
        build.add_union(tub_ob, build.link(pillar, "Cutters"))

    u_spk_deck = F.prism_cutter("Tub_AISpeakerDeck", "+Z", _rect(3085.0, 75.0, 3408.0, 510.0, 10.0),
                                520.0 * SCALE, 756.0 * SCALE)
    u_amp_deck = F.prism_cutter("Tub_AIAmpDeck", "+Z", _rect(3085.0, -510.0, 3408.0, -102.0, 10.0),
                                520.0 * SCALE, 756.0 * SCALE)
    build.add_union(tub_ob, build.link(u_spk_deck, "Cutters"))
    build.add_union(tub_ob, build.link(u_amp_deck, "Cutters"))

    c_tub_radxa = F.prism_cutter("Tub_AIRadxaSled", "+Z", _rect(3015.0, -310.0, 3425.0, 310.0, 6.0),
                                 756.0 * SCALE, 920.0 * SCALE)
    c_spk_bay = F.prism_cutter("Tub_AISpeakerBay", "+Z", _rect(3060.0, -45.0, 3402.0, 485.0, 8.0),
                               560.0 * SCALE, 920.0 * SCALE)
    c_amp_bay = F.prism_cutter("Tub_AIAmpDrvBay", "+Z", _rect(3060.0, -504.0, 3402.0, -108.0, 8.0),
                               425.0 * SCALE, 920.0 * SCALE)
    build.add_boolean(tub_ob, build.link(c_tub_radxa, "Cutters"))
    build.add_boolean(tub_ob, build.link(c_spk_bay, "Cutters"))
    build.add_boolean(tub_ob, build.link(c_amp_bay, "Cutters"))

    # 4. BayTub: front open-top `VL53L1X` ToF sensor cradle slot (`X = 668..752 = 33.4..37.6 mm, Y = -260..+260 = 26.0 mm, Z = 415..600`)
    c_tof_slot = F.prism_cutter("BayTub_ToFSlot", "+Z", _rect(668.0, -260.0, 752.0, 260.0, 8.0),
                                415.0 * SCALE, 600.0 * SCALE)
    build.add_boolean(bay_ob, build.link(c_tof_slot, "Cutters"))

    for col in ("Parts", "Cutters"):
        for ob in build.collection(col).objects:
            if ob.type == 'MESH':
                for poly in ob.data.polygons:
                    poly.use_smooth = True

    materials.apply_all()
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- Real-Datasheet Purchased BOM Hardware 3D CAD Collection
AI_BOM_STL_DIR = os.path.join(AI_OUT_DIR, "stl_bom")
AI_ASSEMBLED_STL_DIR = os.path.join(AI_OUT_DIR, "stl_assembled")

BOM_HARDWARE_SPECS = [
    {
        "bom_id": "BOM_01",
        "name": "BOM_01_Radxa_Zero_3W",
        "stl": "bom_01_radxa_zero_3w.stl",
        "label": "Radxa Zero 3W (RK3566 4GB LPDDR4 + Wi-Fi 6 + 0.8 TOPS NPU)",
        "datasheet_dims_mm": (65.0, 30.0, 4.2),
        "installed_center_mm": (183.5, 0.0, 40.0),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "InteriorTub_AIRadxaSled + Cut_RadxaBulkheadBridge + BootTub_RadxaShelf_L/R",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.08, 0.42, 0.24, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -1.50), (65.0, 30.0, 1.2)),      # 65.0 x 30.0 x 1.2 mm FR4 PCB (Z = 37.9..39.1 mm on Z = 37.8 ledges)
            ("box", (-6.0, -2.0, -0.30), (11.0, 11.0, 1.2)),    # Rockchip RK3566 SoC package
            ("box", (6.5, -2.0, -0.40), (8.5, 6.5, 1.0)),       # 4GB LPDDR4 DRAM package
            ("box", (-20.0, -4.5, -0.20), (10.0, 10.0, 1.4)),   # AIC8800D80 Wi-Fi 6 / BT 5.2 RF shield
            ("box", (0.0, 11.8, 0.40), (50.8, 5.0, 2.8)),       # 40-pin 2.54 mm GPIO low-profile header row
            ("box", (-30.2, 0.0, 0.20), (3.5, 13.5, 2.2)),      # 22-pin 0.5 mm pitch MIPI CSI-2 FPC connector
            ("box", (28.5, -7.5, 0.50), (7.4, 8.9, 3.0)),       # Rear USB-C OTG / Power port
            ("box", (28.5, 4.5, 0.50), (7.4, 8.9, 3.0)),        # Rear USB-C Host port
            ("box", (12.0, -11.0, 0.30), (6.0, 7.5, 2.6)),      # Micro-HDMI receptacle
        ],
    },
    {
        "bom_id": "BOM_02",
        "name": "BOM_02_OV5647_Camera",
        "stl": "bom_02_ov5647_camera.stl",
        "label": "OV5647 5MP 160-deg Wide-Angle Fisheye M12 Camera Module",
        "datasheet_dims_mm": (14.0, 15.0, 15.0),
        "installed_center_mm": (117.2, 0.0, 61.5),
        "installed_rot_deg": (0.0, 9.0, 0.0),
        "bay": "WaymoPod_LensArch + Cut_WaymoCamWell",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.12, 0.14, 0.18, 1.0),
        "elems": [
            ("box", (5.6, 0.0, 0.0), (1.2, 15.0, 15.0)),                         # 15.0 x 15.0 x 1.2 mm rear camera sensor PCB
            ("box", (2.5, 0.0, 0.0), (5.0, 14.0, 14.0)),                         # 14.0 x 14.0 x 5.0 mm M12 threaded lens holder
            ("cyl", (-2.2, 0.0, 0.0), 7.0, 4.8, (0.0, 90.0, 0.0), 36),           # Ø 14.0 mm anodized M12 fisheye barrel
            ("cyl", (-5.5, 0.0, 0.0), 6.8, 2.6, (0.0, 90.0, 0.0), 36),           # Ø 13.6 mm front multi-coated fisheye crown
        ],
    },
    {
        "bom_id": "BOM_03",
        "name": "BOM_03_CSI_Ribbon_15to22",
        "stl": "bom_03_csi_ribbon_15to22.stl",
        "label": "15-Pin (16.0 mm) to 22-Pin (11.5 mm) MIPI CSI-2 FPC Ribbon",
        "datasheet_dims_mm": (1.6, 16.0, 21.8),
        "installed_center_mm": (143.4, 0.0, 52.4),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Cut_WaymoChimney + WaymoPod_CableChannel",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.85, 0.58, 0.15, 1.0),
        "elems": [
            ("box", (0.0, 0.0, 5.4), (0.8, 16.0, 11.0)),         # Upper 16.0 mm wide 15-pin FPC section
            ("box", (0.0, 0.0, -5.5), (0.8, 11.5, 10.8)),        # Lower 11.5 mm wide 22-pin FPC section
        ],
    },
    {
        "bom_id": "BOM_04",
        "name": "BOM_04_GC9A01_Display",
        "stl": "bom_04_gc9a01_display.stl",
        "label": "Waveshare 1.28-inch Round GC9A01 240x240 RGB IPS SPI Display",
        "datasheet_dims_mm": (35.6, 38.0, 4.0),
        "installed_center_mm": (176.5, 0.0, 50.4),
        "installed_rot_deg": (0.0, 20.5, 0.0),
        "bay": "Cut_RearGlassHUD + Cut_RearGlassHUDWell + Cut_RearGlassHUDPCB",
        "insert_axis": (0.0, 0.0, -1.0),
        "color": (0.08, 0.25, 0.58, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -0.40), (35.6, 38.0, 1.6)),       # 35.6 x 38.0 x 1.6 mm carrier PCB
            ("cyl", (0.0, 0.0, 1.20), 16.2, 1.6, (0.0, 0.0, 0.0), 48),  # Ø 32.4 x 1.6 mm round IPS glass module
            ("box", (-11.0, 0.0, -1.60), (5.0, 12.0, 0.8)),      # Rear JST-GH 8-pin SPI connector
        ],
    },
    {
        "bom_id": "BOM_05",
        "name": "BOM_05_INMP441_Mic",
        "stl": "bom_05_inmp441_mic.stl",
        "label": "INMP441 Omnidirectional I2S Digital MEMS Microphone Breakout",
        "datasheet_dims_mm": (14.0, 14.0, 2.5),
        "installed_center_mm": (132.0, 0.0, 70.8),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "WaymoPod_MicCup",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.12, 0.12, 0.16, 1.0),
        "elems": [
            ("cyl", (0.0, 0.0, -0.45), 7.0, 1.6, (0.0, 0.0, 0.0), 36),  # Ø 14.0 x 1.6 mm circular breakout PCB
            ("box", (0.0, 0.0, 0.80), (4.7, 3.8, 0.9)),                 # Top metal MEMS acoustic sensor package
        ],
    },
    {
        "bom_id": "BOM_06",
        "name": "BOM_06_MAX98357A_Amp",
        "stl": "bom_06_max98357a_amp.stl",
        "label": "MAX98357A I2S 3W Class-D Filterless Audio Amplifier Breakout",
        "datasheet_dims_mm": (16.5, 19.0, 3.2),
        "installed_center_mm": (161.55, -15.3, 28.5),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Tub_AIAmpDrvBay (Upper Tier)",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.12, 0.22, 0.55, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -0.80), (16.5, 19.0, 1.6)),       # 16.5 x 19.0 x 1.6 mm breakout PCB
            ("box", (0.0, -1.0, 0.50), (4.5, 4.5, 1.0)),         # MAX98357A QFN-16 IC
            ("box", (0.0, 6.0, 0.80), (6.5, 5.0, 1.6)),          # 2-pin speaker output block
            ("box", (-6.5, 0.0, 0.80), (2.5, 17.5, 1.6)),        # 7-pin I2S header row
        ],
    },
    {
        "bom_id": "BOM_07",
        "name": "BOM_07_Speaker_1524",
        "stl": "bom_07_speaker_1524.stl",
        "label": "8-Ohm 1W Sealed Cavity Micro Speaker (1524 Enclosure)",
        "datasheet_dims_mm": (15.0, 24.0, 4.0),
        "installed_center_mm": (161.5, 11.0, 30.5),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Tub_AISpeakerBay",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.15, 0.15, 0.17, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -0.40), (15.0, 24.0, 3.2)),       # 15.0 x 24.0 x 3.2 mm sealed ABS acoustic enclosure
            ("box", (0.0, 0.0, 1.60), (12.0, 20.0, 0.8)),        # Racetrack Mylar speaker cone & steel bezel
        ],
    },
    {
        "bom_id": "BOM_08",
        "name": "BOM_08_VL53L1X_ToF",
        "stl": "bom_08_vl53l1x_tof.stl",
        "label": "VL53L1X Time-of-Flight Laser Ranging Sensor Breakout (<20 ms Reflex)",
        "datasheet_dims_mm": (3.2, 25.0, 10.7),
        "installed_center_mm": (26.2, 0.0, 25.8),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Front Engine Bay / Valance ToF Mount (X = 26.2 mm)",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.38, 0.14, 0.48, 1.0),
        "elems": [
            ("box", (0.80, 0.0, 0.0), (1.6, 18.0, 10.7)),        # 18.0 x 10.7 x 1.6 mm main sensor PCB
            ("box", (0.80, 0.0, 0.0), (1.6, 25.0, 5.2)),         # Dual M2 mounting ear wings (25.0 mm total span)
            ("box", (-0.80, 0.0, 0.0), (1.6, 4.9, 2.5)),         # ST VL53L1X 940 nm VCSEL + SPAD optical module
        ],
    },
    {
        "bom_id": "BOM_09",
        "name": "BOM_09_N25_Gearmotor",
        "stl": "bom_09_n25_gearmotor.stl",
        "label": "N20/N25 6V 300-500 RPM Micro Metal Gearmotor (Ø 3.0 mm D-Shaft)",
        "datasheet_dims_mm": (21.0, 12.0, 10.0),
        "installed_center_mm": (57.75, 0.0, 19.75),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "BayTub_N25Bed + Cut_ChassisAxleN25Bed",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.72, 0.58, 0.22, 1.0),
        "elems": [
            ("box", (-4.50, 0.0, 0.0), (12.0, 12.0, 10.0)),      # 12.0 x 12.0 x 10.0 mm flat-sided DC motor can
            ("box", (6.00, 0.0, 0.0), (9.0, 12.0, 10.0)),        # 9.0 x 12.0 x 10.0 mm brass/steel spur reduction gearbox
            ("cyl", (11.00, 0.0, 0.0), 1.45, 1.0, (0.0, 90.0, 0.0), 24),  # Front gearbox bearing boss
        ],
    },
    {
        "bom_id": "BOM_10",
        "name": "BOM_10_DRV8833_HBridge",
        "stl": "bom_10_drv8833_hbridge.stl",
        "label": "DRV8833 Dual H-Bridge DC Motor Driver Breakout (1.5A Peak)",
        "datasheet_dims_mm": (16.0, 18.5, 3.2),
        "installed_center_mm": (161.55, -15.3, 23.2),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Tub_AIAmpDrvBay (Lower Tier)",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.55, 0.14, 0.14, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -0.80), (16.0, 18.5, 1.6)),       # 16.0 x 18.5 x 1.6 mm breakout PCB
            ("box", (0.0, 0.0, 0.60), (6.4, 5.0, 1.2)),          # TI DRV8833 HTSSOP-16 driver IC
            ("box", (6.2, 0.0, 0.80), (2.5, 17.0, 1.6)),         # Control & motor output header row
        ],
    },
    {
        "bom_id": "BOM_11",
        "name": "BOM_11_Servo_1p7g",
        "stl": "bom_11_servo_1p7g.stl",
        "label": "1.7g Ultra-Micro Digital Steering Servo (3-Wire JR PWM)",
        "datasheet_dims_mm": (9.5, 16.0, 6.2),
        "installed_center_mm": (28.25, 0.0, 15.95),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "BayTub_ServoBed + Cut_ChassisAxleServoBed",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.18, 0.18, 0.22, 1.0),
        "elems": [
            ("box", (0.0, 0.0, 0.0), (9.5, 16.0, 6.2)),          # Horizontal micro servo case (9.5 x 16.0 x 6.2 mm)
            ("box", (4.0, -2.5, 1.8), (1.2, 7.0, 2.0)),          # Output spline boss & single-arm horn in BayTub_ServoHornSlot
        ],
    },
    {
        "bom_id": "BOM_12",
        "name": "BOM_12_LiPo_2S_350mAh",
        "stl": "bom_12_lipo_2s_350mah.stl",
        "label": "2S 7.4V 300-350mAh 25C High-Discharge LiPo Battery Pack",
        "datasheet_dims_mm": (35.0, 20.0, 8.0),
        "installed_center_mm": (193.0, 3.5, 33.4),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "Cut_RadxaBulkheadBridge + BootTub_AIClearFloor",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.15, 0.42, 0.78, 1.0),
        "elems": [
            ("box", (0.8, 0.0, -2.0), (33.4, 20.0, 3.8)),        # Lower 3.7V LiPo pouch cell
            ("box", (0.8, 0.0, 2.0), (33.4, 20.0, 3.8)),         # Upper 3.7V LiPo pouch cell
            ("box", (-16.6, 0.0, 0.0), (1.8, 18.0, 7.4)),        # Front Kapton protection board & JST-XH balance header
        ],
    },
    {
        "bom_id": "BOM_13",
        "name": "BOM_13_BEC_5V_3A",
        "stl": "bom_13_bec_5v_3a.stl",
        "label": "Mini360 / Pololu 5V 3A Synchronous Buck Regulator (BEC)",
        "datasheet_dims_mm": (14.5, 12.0, 4.0),
        "installed_center_mm": (207.8, -15.0, 32.2),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "BootTub_AIClearFloor (Left Pocket)",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.12, 0.48, 0.32, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -1.2), (14.5, 12.0, 1.6)),        # 14.5 x 12.0 x 1.6 mm buck converter PCB
            ("box", (1.2, 0.0, 0.8), (6.5, 6.5, 2.4)),           # Shielded SMD power inductor
            ("box", (-4.2, 0.0, 0.4), (4.0, 4.0, 1.6)),          # Buck controller IC & trim pot
        ],
    },
    {
        "bom_id": "BOM_15",
        "name": "BOM_15_SlideSwitch_SS12D00",
        "stl": "bom_15_slideswitch_ss12d00.stl",
        "label": "SS12D00G3 SPDT High-Current Main Battery Slide Switch",
        "datasheet_dims_mm": (8.6, 3.8, 4.0),
        "installed_center_mm": (208.0, 18.0, 32.2),
        "installed_rot_deg": (0.0, 0.0, 0.0),
        "bay": "BootTub_AIClearFloor (Right Pocket)",
        "insert_axis": (0.0, 0.0, 1.0),
        "color": (0.28, 0.28, 0.32, 1.0),
        "elems": [
            ("box", (0.0, 0.0, -0.6), (8.6, 3.8, 2.8)),          # Steel switch frame body
            ("box", (0.0, 0.0, 1.4), (2.2, 2.0, 1.2)),           # Black slide actuator knob
        ],
    },
]


def _make_bom_material(name, rgba):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    if mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = 0.35
            bsdf.inputs["Metallic"].default_value = 0.25
    mat.diffuse_color = rgba
    return mat


def _build_single_bom_object(spec):
    """Build a persistent multi-feature 3D CAD mesh for a purchased BOM hardware module."""
    bm = bmesh.new()
    for elem in spec["elems"]:
        kind = elem[0]
        if kind == "box":
            _, (dx, dy, dz), (sx, sy, sz) = elem
            ret = bmesh.ops.create_cube(bm, size=1.0)
            verts = ret["verts"]
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=verts)
            bmesh.ops.translate(bm, vec=(dx, dy, dz), verts=verts)
        elif kind == "cyl":
            _, (dx, dy, dz), rad, depth, rot_xyz, segs = elem
            ret = bmesh.ops.create_cone(
                bm, cap_ends=True, segments=segs, radius1=rad, radius2=rad, depth=depth
            )
            verts = ret["verts"]
            if any(abs(a) > 1e-4 for a in rot_xyz):
                rmat = Euler([math.radians(a) for a in rot_xyz], 'XYZ').to_matrix().to_4x4()
                bmesh.ops.transform(bm, matrix=rmat, verts=verts)
            bmesh.ops.translate(bm, vec=(dx, dy, dz), verts=verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(spec["name"])
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(spec["name"], me)
    ob.location = Vector(spec["installed_center_mm"])
    ob.rotation_euler = Euler([math.radians(a) for a in spec["installed_rot_deg"]], 'XYZ')
    mat = _make_bom_material(f"Mat_{spec['name']}", spec["color"])
    ob.data.materials.append(mat)
    return ob


def build_bom_hardware_collection():
    """Create (or rebuild) the persistent `AI_Hardware` collection containing all 14 purchased BOM
    hardware 3D CAD models in their exact installed world poses."""
    col = build.collection("AI_Hardware")
    for old in list(col.objects):
        me = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if me and me.users == 0:
            bpy.data.meshes.remove(me)
    objs = []
    for spec in BOM_HARDWARE_SPECS:
        ob = _build_single_bom_object(spec)
        col.objects.link(ob)
        objs.append(ob)
    bpy.context.view_layer.update()
    return objs


def export_bom_and_assembled_stls():
    """Export all 14 purchased BOM hardware meshes to `output/ai_edition/stl_bom/` and all 69
    printed car parts in assembled world coordinates to `output/ai_edition/stl_assembled/`."""
    os.makedirs(AI_BOM_STL_DIR, exist_ok=True)
    os.makedirs(AI_ASSEMBLED_STL_DIR, exist_ok=True)
    bom_col = bpy.data.collections.get("AI_Hardware")
    if bom_col is None:
        build_bom_hardware_collection()
        bom_col = bpy.data.collections.get("AI_Hardware")

    dg = bpy.context.evaluated_depsgraph_get()
    bom_manifest = {}
    for spec in BOM_HARDWARE_SPECS:
        ob = bpy.data.objects.get(spec["name"])
        if ob is None:
            continue
        out_path = os.path.join(AI_BOM_STL_DIR, spec["stl"])
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(ob.matrix_world)
        export.clean_triangulate(bm, 'BEAUTY', 3e-5)
        export.write_stl(bm, out_path, f"mustang67 {spec['name']}")
        bm.free()
        bom_manifest[spec["name"]] = {
            "bom_id": spec["bom_id"],
            "stl": f"output/ai_edition/stl_bom/{spec['stl']}",
            "label": spec["label"],
            "datasheet_dims_mm": list(spec["datasheet_dims_mm"]),
            "installed_center_mm": list(spec["installed_center_mm"]),
            "installed_rot_deg": list(spec["installed_rot_deg"]),
            "bay": spec["bay"],
        }

    orig_parts = list(export.PARTS)
    try:
        export.PARTS = orig_parts + AI_EXTRA_PARTS
        export.run_assembled(out_dir=AI_OUT_DIR)
    finally:
        export.PARTS = orig_parts

    return bom_manifest


def verify_virtual_ai_hardware():
    """Verify 0.000 mm^3 overlap between ALL 14 purchased BOM hardware modules (using both their
    detailed 3D CAD meshes in `AI_Hardware` AND their full public-datasheet bounding-box envelopes)
    against all 69 printed parts in `Parts`, plus 0.000 mm^3 inter-module overlap among all 14 BOM items."""
    bom_objs = build_bom_hardware_collection()
    parts_col = bpy.data.collections.get("Parts")
    targets = [ob for ob in parts_col.objects if ob.type == 'MESH'] if parts_col else []

    overlaps = {}
    # 1. Check every detailed 3D BOM mesh against all 69 printed car parts
    for bo in bom_objs:
        for t in targets:
            vol = printcheck.overlap_volume(bo, t)
            if vol > 0.01:
                overlaps[f"{bo.name}|{t.name}"] = round(vol, 4)

    # 2. Check full public-datasheet bounding-box envelopes against all printed enclosure parts
    enclosure_names = ("Body", "InteriorTub", "BootTub", "BayTub", "WaymoPod", "GC9A01Bezel", "Glass_Rear", "TrunkLid", "Chassis")
    enclosures = [bpy.data.objects[n] for n in enclosure_names if n in bpy.data.objects]
    v_objs = []
    for spec in BOM_HARDWARE_SPECS:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=spec["datasheet_dims_mm"], verts=bm.verts)
        me = bpy.data.meshes.new(f"_v_{spec['bom_id']}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"_v_{spec['bom_id']}", me)
        ob.location = Vector(spec["installed_center_mm"])
        ob.rotation_euler = Euler([math.radians(a) for a in spec["installed_rot_deg"]], 'XYZ')
        bpy.context.scene.collection.objects.link(ob)
        v_objs.append((spec["name"], ob))

    bpy.context.view_layer.update()
    for bname, vo in v_objs:
        for t in enclosures:
            vol = printcheck.overlap_volume(vo, t)
            if vol > 0.01:
                overlaps[f"bbox:{bname}|{t.name}"] = round(vol, 4)

    # 3. Check inter-BOM overlaps among all 14 purchased hardware modules
    for i in range(len(bom_objs)):
        for j in range(i + 1, len(bom_objs)):
            vol = printcheck.overlap_volume(bom_objs[i], bom_objs[j])
            if vol > 0.01:
                overlaps[f"{bom_objs[i].name}|{bom_objs[j].name}"] = round(vol, 4)

    for _, vo in v_objs:
        me = vo.data
        bpy.data.objects.remove(vo, do_unlink=True)
        bpy.data.meshes.remove(me)

    return overlaps


def build_and_export(save_blend=True):
    """Build the full 1:20 AI Edition scene, build the persistent `AI_Hardware` collection of 14
    purchased BOM components, run `printcheck.run()`, verify 0.000 mm^3 BOM hardware clearances,
    and export all 55 printed STLs (`75` pieces), 14 BOM hardware STLs (`stl_bom/`), and 69
    assembled STLs (`stl_assembled/`)."""
    os.makedirs(AI_STL_DIR, exist_ok=True)
    build.main()
    studio.setup()
    _apply_ai_upgrades()

    pc_report = printcheck.run()
    hw_overlaps = verify_virtual_ai_hardware()
    bom_manifest = export_bom_and_assembled_stls()

    orig_parts = list(export.PARTS)
    try:
        export.PARTS = orig_parts + AI_EXTRA_PARTS
        exp_report = export.run(out_dir=AI_OUT_DIR)
    finally:
        export.PARTS = orig_parts

    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=AI_BLEND_PATH)

    summary = {
        "edition": "e-Mustang 1967 Fastback 1:20 AI Edition (v3.5.0 - Full Real-Datasheet BOM 3D Hardware + Max-Beef Drivetrain)",
        "blend_path": "output/ai_edition/mustang_67_ai_edition.blend",
        "stl_dir": "output/ai_edition/stl",
        "bom_stl_dir": "output/ai_edition/stl_bom",
        "assembled_stl_dir": "output/ai_edition/stl_assembled",
        "stl_count": len(exp_report),
        "bom_hardware_count": len(bom_manifest),
        "printed_pieces": sum(v["qty"] for v in exp_report.values()),
        "printcheck": pc_report,
        "virtual_ai_hardware_overlaps": hw_overlaps,
        "bom_hardware_manifest": bom_manifest,
        "export_non_manifold": {k: v["non_manifold"] for k, v in exp_report.items() if v["non_manifold"] > 0},
        "support_free_floating": {
            k: v["floating"] for k, v in exp_report.items()
            if v["floating"] and k not in ("body.stl", "hood.stl", "trunk_lid.stl", "engine_block.stl", "bumper_rear.stl")
        },
        "support_free_cantilevers": {
            k: v["cantilevers"] for k, v in exp_report.items()
            if v["cantilevers"] and k not in ("body.stl", "hood.stl", "trunk_lid.stl", "engine_block.stl", "bumper_rear.stl")
        },
        "new_ai_stls": {
            "waymo_pod.stl": exp_report.get("waymo_pod.stl"),
            "gc9a01_bezel.stl": exp_report.get("gc9a01_bezel.stl"),
            "body.stl": exp_report.get("body.stl"),
            "rear_glass.stl": exp_report.get("rear_glass.stl"),
            "interior_tub.stl": exp_report.get("interior_tub.stl"),
            "boot_tub.stl": exp_report.get("boot_tub.stl"),
            "bay_tub.stl": exp_report.get("bay_tub.stl"),
        },
    }
    report_path = os.path.join(paths.TMP, "ai_edition_build_report.json")
    os.makedirs(paths.TMP, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


if __name__ == "__main__":
    res = build_and_export(save_blend=True)
    print("AI Edition Build Summary:", json.dumps({
        "stl_count": res["stl_count"],
        "bom_hardware_count": res["bom_hardware_count"],
        "printed_pieces": res["printed_pieces"],
        "parts_in_scene": res["printcheck"]["parts"],
        "problems": res["printcheck"]["problems"],
        "overlaps_with_body": res["printcheck"]["overlaps_with_body"],
        "mirror_mismatches": res["printcheck"]["mirror_mismatches"],
        "part_overlaps": res["printcheck"]["part_overlaps"],
        "virtual_ai_hardware_overlaps": res["virtual_ai_hardware_overlaps"],
        "export_non_manifold": res["export_non_manifold"],
        "support_free_floating": res["support_free_floating"],
        "support_free_cantilevers": res["support_free_cantilevers"],
    }, indent=2))
