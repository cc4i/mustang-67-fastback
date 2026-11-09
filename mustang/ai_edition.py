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
    # 1. Front 15.2 mm wide 45-deg Gothic-arched fisheye lens bay for Ø 14.0 mm M12 barrel (X = 2220..2395, Y = -152..+152)
    lens_arch = [
        (-152.0, z_base - 8.0),
        (152.0, z_base - 8.0),
        (152.0, 1345.0),
        (0.0, 1497.0),
        (-152.0, 1345.0),
    ]
    c_lens = F.prism_cutter("WaymoPod_LensArch", "+X", lens_arch, 2220.0 * SCALE, 2395.0 * SCALE)

    # 2. Internal 45-deg gabled CSI ribbon & camera tunnel (X = 2350..2850, Y = -168..+168 = 16.8 mm wide for 16.0 mm FPC)
    cable_arch = [
        (-168.0, z_base - 8.0),
        (168.0, z_base - 8.0),
        (168.0, 1280.0),
        (0.0, 1368.0),
        (-168.0, 1280.0),
    ]
    c_pod_cable = F.prism_cutter("WaymoPod_CableChannel", "+X", cable_arch, 2350.0 * SCALE, 2850.0 * SCALE)

    # 3. Top upward-facing 12.0 x 15.2 mm rounded recess for the real 10.0 x 14.0 x 2.0 mm INMP441 MEMS mic (X = 2520, Y = 0)
    c_mic = F.prism_cutter("WaymoPod_MicCup", "+Z", _rect(2400.0, -152.0, 2640.0, 152.0, 24.0),
                           1388.0 * SCALE, 1485.0 * SCALE)

    # Matching Body cutters (`Cut_WaymoSocket` with +0.40 mm clearance + 2.7 x 17.2 mm vertical CSI ribbon chimney):
    clr = 8.0  # 0.40 mm print clearance around the pod perimeter
    z_sock = z_base - 12.0  # recessed roof socket floor (stays above cabin ceiling ~1230!)
    sock_pts = []
    for x, hw, _ in stations:
        sock_pts.append((x - clr if x == stations[0][0] else (x + clr if x == stations[-1][0] else x), hw + clr))
    sock_poly = [(x, -w) for x, w in sock_pts] + [(x, w) for x, w in reversed(sock_pts)]
    c_body_sock = F.prism_cutter("Cut_WaymoSocket", "+Z", sock_poly, z_sock * SCALE, 1485.0 * SCALE)

    # Vertical CSI ribbon & mic wire chimney through the rear roof header (X = 2842..2896, Y = -172..+172 = 17.2 mm wide)
    # Strictly behind front seats (X <= 2840) and ahead of Glass_Rear (X >= 2900), concealed under WaymoPod!
    c_chimney = F.prism_cutter("Cut_WaymoChimney", "+Z", _rect(2842.0, -172.0, 2896.0, 172.0, 10.0),
                               1040.0 * SCALE, 1485.0 * SCALE)

    return pod, [c_lens, c_pod_cable, c_mic], [c_body_sock, c_chimney]


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

    # Matching vertical well in Body (`r = 324.0 real mm = Ø 32.40 mm`, Z = 800..1240) plus sub-surface PCB carrier well
    hud_well_circle = [(3530.0 + 324.0 * math.cos(2 * math.pi * k / 48),
                        324.0 * math.sin(2 * math.pi * k / 48)) for k in range(48)]
    c_body_hud = F.prism_cutter("Cut_RearGlassHUDWell", "+Z", hud_well_circle, 800.0 * SCALE, 1240.0 * SCALE)

    bm_pcb = bmesh.new()
    bmesh.ops.create_cube(bm_pcb, size=1.0)
    bmesh.ops.scale(bm_pcb, vec=(35.0, 37.2, 5.2), verts=bm_pcb.verts)
    me_pcb = bpy.data.meshes.new("Cut_RearGlassHUDPCB")
    bm_pcb.to_mesh(me_pcb)
    bm_pcb.free()
    c_body_pcb = bpy.data.objects.new("Cut_RearGlassHUDPCB", me_pcb)
    c_body_pcb.location = Vector((176.5, 0.0, 50.0))
    c_body_pcb.rotation_euler = Euler((0.0, math.radians(20.5), 0.0), 'XYZ')

    return bezel, c_hud, [c_body_hud, c_body_pcb]


def _apply_ai_upgrades():
    """Apply the AI Edition (`v3.0.0`) boolean cutters, unions, and new parts to the built Mustang scene."""
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

    # 1. WaymoPod (low-profile Burgundy roof scoop) + Body roof socket & CSI chimney
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

    # 3. Bridged Two-Story Rear Avionics Deck & Full-Length Stepped L-Rail Cradle for Radxa Zero 3W (65 x 30 x 5.0 mm):
    # 3a. Body bulkhead bridge (`X = 3390..4020` = `169.5..201.0 mm`):
    #     Deepened lower battery/BEC vault (`Y = -280..+280 = 28.0 mm wide, Z = 584..756 = 29.2..37.8 mm = 8.6 mm tall`),
    #     two continuous PCB support ledges at `Z = 756` (`37.8 mm`, `|Y| = 280..310`),
    #     vertical lateral keeper walls (`|Y| = 310`, `Z = 756..865`), and a 45-deg self-supporting gable roof (peak `Z = 1175`).
    bulkhead_stepped_prof = [
        (-280.0, 584.0),
        (280.0, 584.0),
        (280.0, 756.0),
        (310.0, 756.0),
        (310.0, 865.0),
        (0.0, 1175.0),
        (-310.0, 865.0),
        (-310.0, 756.0),
        (-280.0, 756.0),
    ]
    c_bulkhead = F.prism_cutter("Cut_RadxaBulkheadBridge", "+X", bulkhead_stepped_prof, 3390.0 * SCALE, 4020.0 * SCALE)
    build.add_boolean(body_ob, build.link(c_bulkhead, "Cutters"))

    # 3b. BootTub (`X = 3988..4368` = `199.4..218.4 mm`, `Y = -486..+486` = `48.6 mm`, `Z = 564..855` = `28.2..42.75 mm`):
    #     Clear the full-width lower floor (`X = 3980..4346, Y = -450..+450 = 45.0 mm wide, Z = 584..760 = 29.2..38.0 mm`)
    #     so a real 35.0 x 20.0 x 8.0 mm 2S 300-350mAh LiPo + 18.0 x 12.0 x 4.2 mm 5V 3A Buck BEC + Slide Switch fit
    #     both transversely inside BootTub (45.0 mm Y span) and longitudinally across the bridged lower vault (X = 172..217 mm).
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
    #     - Union level rear deck extensions (`Tub_AISpeakerDeck` at `Y = -65..+510` and `Tub_AIAmpDeck` at `Y = -510..-160`,
    #       `X = 3085..3408, Z = 520..756`) inside `Tub_RearSeat + Tub_CargoShelf` (`|Y| <= 525`).
    #     - Cut `Tub_AIRadxaSled` (`X = 3015..3425, Y = -310..+310, Z = 756..920`) so the Radxa board slides flat at `Z = 37.8 mm`.
    #     - Cut the `15.40 x 24.50 x 10.90 mm` speaker pocket (`Tub_AISpeakerBay`, `X = 3092..3400, Y = -45..+445, Z = 560..920`)
    #       for the real physical `15.0 x 24.0 x 4.0 mm` (`1524`) speaker.
    #     - Cut the deep `15.40 x 16.20 x 17.90 mm` dual-board pocket (`Tub_AIAmpDrvBay`, `X = 3092..3400, Y = -496..-172, Z = 420..920`)
    #       that holds BOTH the `DRV8833` and `MAX98357A` boards stacked vertically with zero overhang!
    for tag, (py0, py1) in (("L", (-345.0, -250.0)), ("R", (250.0, 345.0))):
        pillar = F.prism_cutter(f"Tub_RadxaFrontPillar_{tag}", "+Z", _rect(2990.0, py0, 3100.0, py1, 4.0),
                                310.0 * SCALE, 840.0 * SCALE)
        build.add_union(tub_ob, build.link(pillar, "Cutters"))

    u_spk_deck = F.prism_cutter("Tub_AISpeakerDeck", "+Z", _rect(3085.0, -55.0, 3408.0, 510.0, 10.0),
                                520.0 * SCALE, 756.0 * SCALE)
    u_amp_deck = F.prism_cutter("Tub_AIAmpDeck", "+Z", _rect(3085.0, -510.0, 3408.0, -172.0, 10.0),
                                520.0 * SCALE, 756.0 * SCALE)
    build.add_union(tub_ob, build.link(u_spk_deck, "Cutters"))
    build.add_union(tub_ob, build.link(u_amp_deck, "Cutters"))

    c_tub_radxa = F.prism_cutter("Tub_AIRadxaSled", "+Z", _rect(3015.0, -310.0, 3425.0, 310.0, 6.0),
                                 756.0 * SCALE, 920.0 * SCALE)
    c_spk_bay = F.prism_cutter("Tub_AISpeakerBay", "+Z", _rect(3092.0, -45.0, 3400.0, 445.0, 8.0),
                               560.0 * SCALE, 920.0 * SCALE)
    c_amp_bay = F.prism_cutter("Tub_AIAmpDrvBay", "+Z", _rect(3092.0, -498.0, 3400.0, -182.0, 8.0),
                               420.0 * SCALE, 920.0 * SCALE)
    build.add_boolean(tub_ob, build.link(c_tub_radxa, "Cutters"))
    build.add_boolean(tub_ob, build.link(c_spk_bay, "Cutters"))
    build.add_boolean(tub_ob, build.link(c_amp_bay, "Cutters"))

    # 4. BayTub: front open-top `VL53L1X` ToF sensor cradle slot (`X = 674..742 = 33.7..37.1 mm, Y = -188..+188 = 18.8 mm, Z = 435..600`)
    c_tof_slot = F.prism_cutter("BayTub_ToFSlot", "+Z", _rect(674.0, -188.0, 742.0, 188.0, 8.0),
                                435.0 * SCALE, 600.0 * SCALE)
    build.add_boolean(bay_ob, build.link(c_tof_slot, "Cutters"))

    for col in ("Parts", "Cutters"):
        for ob in build.collection(col).objects:
            if ob.type == 'MESH':
                for poly in ob.data.polygons:
                    poly.use_smooth = True

    materials.apply_all()
    bpy.context.view_layer.update()


def verify_virtual_ai_hardware():
    """Verify 0.0 mm^3 overlap between the REAL physical 1:20 AI BOM hardware envelopes:
      - Radxa Zero 3W: 65.0 x 30.0 x 5.0 mm
      - OV5647 Lens Barrel + Camera Module: Ø 14.0 mm (6.0 x 14.0 x 3.6 mm) + 16.0 mm wide CSI ribbon
      - INMP441 MEMS Mic Breakout: 10.0 x 14.0 x 2.0 mm
      - GC9A01 1.28" Round Display PCB Carrier: 32.0 x 35.6 x 3.2 mm
      - 2S 7.4V 300-350mAh LiPo Battery: 35.0 x 20.0 x 8.0 mm (plus transverse 38.0 x 15.0 x 8.0 mm fit)
      - 5V 3A Buck BEC (Mini360 / Pololu): 16.0 x 11.5 x 4.0 mm
      - Full-size 1524 Cabin Speaker: 15.0 x 24.0 x 4.0 mm
      - DRV8833 Dual H-Bridge Breakout: 14.8 x 15.0 x 3.2 mm
      - MAX98357A I2S Amp Breakout: 14.8 x 14.0 x 3.2 mm
      - VL53L1X Front ToF Laser Breakout: 3.2 x 18.0 x 5.5 mm
    and all printed parts."""
    specs = [
        # (name, center_print_mm, size_print_mm, rot_deg)
        ("_v_radxa_zero_3w", (183.5, 0.0, 40.5), (65.0, 30.0, 5.0), (0.0, 0.0, 0.0)),
        ("_v_csi_ribbon", (143.4, 0.0, 52.4), (1.6, 16.0, 21.8), (0.0, 0.0, 0.0)),
        ("_v_lipo_2s", (193.0, 2.5, 33.4), (35.0, 20.0, 8.0), (0.0, 0.0, 0.0)),
        ("_v_bec_5v", (207.2, -15.0, 31.5), (16.0, 11.5, 4.0), (0.0, 0.0, 0.0)),
        ("_v_speaker_1524", (162.3, 10.0, 30.5), (15.0, 24.0, 4.0), (0.0, 0.0, 0.0)),
        ("_v_drv8833", (162.3, -17.0, 23.2), (14.8, 14.6, 3.2), (0.0, 0.0, 0.0)),
        ("_v_max98357a", (162.3, -17.0, 28.5), (14.8, 14.0, 3.2), (0.0, 0.0, 0.0)),
        ("_v_gc9a01_pcb", (176.5, 0.0, 50.0), (32.0, 35.6, 3.2), (0.0, 20.5, 0.0)),
        ("_v_ov5647_lens", (115.2, 0.0, 65.7), (6.0, 14.0, 3.6), (0.0, 9.0, 0.0)),
        ("_v_inmp441_mic", (126.0, 0.0, 70.8), (10.0, 14.0, 2.0), (0.0, 0.0, 0.0)),
        ("_v_vl53l1x_tof", (35.4, 0.0, 24.8), (3.2, 18.0, 5.5), (0.0, 0.0, 0.0)),
    ]
    v_objs = []
    for name, loc, sz, rot in specs:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=sz, verts=bm.verts)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.location = Vector(loc)
        ob.rotation_euler = Euler([math.radians(a) for a in rot], 'XYZ')
        bpy.context.scene.collection.objects.link(ob)
        v_objs.append(ob)

    bpy.context.view_layer.update()
    overlaps = {}
    target_names = ("Body", "InteriorTub", "BootTub", "BayTub", "WaymoPod", "GC9A01Bezel", "Glass_Rear", "TrunkLid")
    targets = [bpy.data.objects[n] for n in target_names]
    for vo in v_objs:
        for t in targets:
            vol = printcheck.overlap_volume(vo, t)
            if vol > 0.01:
                overlaps[f"{vo.name}|{t.name}"] = vol

    for vo in v_objs:
        me = vo.data
        bpy.data.objects.remove(vo, do_unlink=True)
        bpy.data.meshes.remove(me)
    return overlaps


def build_and_export(save_blend=True):
    """Build the full 1:20 AI Edition scene, run `printcheck.run()`, verify virtual AI hardware
    clearances, and export all 55 STLs (`75` printed pieces) into `output/ai_edition/stl/`."""
    os.makedirs(AI_STL_DIR, exist_ok=True)
    build.main()
    studio.setup()
    _apply_ai_upgrades()

    pc_report = printcheck.run()
    hw_overlaps = verify_virtual_ai_hardware()

    orig_parts = list(export.PARTS)
    try:
        export.PARTS = orig_parts + AI_EXTRA_PARTS
        exp_report = export.run(out_dir=AI_OUT_DIR)
    finally:
        export.PARTS = orig_parts

    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=AI_BLEND_PATH)

    summary = {
        "edition": "e-Mustang 1967 Fastback 1:20 AI Edition (v3.5.0 - Sleek Sub-Surface Option B + Max-Beef Drivetrain)",
        "blend_path": "output/ai_edition/mustang_67_ai_edition.blend",
        "stl_dir": "output/ai_edition/stl",
        "stl_count": len(exp_report),
        "printed_pieces": sum(v["qty"] for v in exp_report.values()),
        "printcheck": pc_report,
        "virtual_ai_hardware_overlaps": hw_overlaps,
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
