"""Preview/render materials. Print colours come from the separate parts; these
only make the model read correctly on screen."""
import math

import bpy

PALETTE = {
    # name: (base colour RGBA, metallic, roughness, extra)
    "Paint": ((0.2, 0.014, 0.034, 1), 0.5, 0.22, {"coat": 1.0}),
    "PaintJamb": ((0.08, 0.006, 0.014, 1), 0.0, 0.7, {}),          # door jambs and shut faces: dull, so the gaps read dark
    "Carpet": ((0.012, 0.012, 0.012, 1), 0.0, 0.95, {}),
    "Glass": ((0.015, 0.018, 0.022, 1), 0.0, 0.08, {}),
    "Chrome": ((0.85, 0.85, 0.87, 1), 1.0, 0.08, {}),
    "SatinChrome": ((0.8, 0.8, 0.82, 1), 1.0, 0.25, {}),         # radiator cap: shows its shape rather than mirroring the studio
    "Black": ((0.02, 0.02, 0.02, 1), 0.0, 0.6, {}),
    "GlossBlack": ((0.012, 0.012, 0.012, 1), 0.0, 0.12, {"coat": 1.0}),     # painted inner fenders, firewall, brace
    "Vinyl": ((0.035, 0.035, 0.037, 1), 0.0, 0.32, {}),
    "EngineBlue": ((0.005, 0.16, 0.62, 1), 0.0, 0.35, {"coat": 0.15, "specular": 0.3}),    # Ford corporate blue
    "Rubber": ((0.025, 0.025, 0.025, 1), 0.0, 0.85, {}),
    "CastIron": ((0.07, 0.065, 0.06, 1), 0.6, 0.55, {}),
    "TailRed": ((0.22, 0.003, 0.005, 1), 0.0, 0.3, {"specular": 0.25}),   # deep red lenses: satin, so the sky above doesn't wash them out
    "Red": ((0.55, 0.01, 0.01, 1), 0.0, 0.3, {}),
    "Blue": ((0.02, 0.05, 0.4, 1), 0.0, 0.3, {}),
    "White": ((0.85, 0.85, 0.85, 1), 0.0, 0.4, {}),
    "WireBlue": ((0.16, 0.36, 0.75, 1), 0.0, 0.45, {}),           # Autolite blue plug wires
    "Steel": ((0.36, 0.36, 0.38, 1), 0.8, 0.35, {}),
    "Aluminum": ((0.62, 0.6, 0.55, 1), 0.85, 0.45, {}),
    "CastAl": ((0.40, 0.38, 0.30, 1), 0.6, 0.65, {}),             # as-cast aluminium: intake, carburettor, alternator
    "BrushedAl": ((0.72, 0.72, 0.7, 1), 0.9, 0.3, {}),            # sill scuff plates
    "TankGrey": ((0.12, 0.13, 0.13, 1), 0.6, 0.4, {}),            # radiator top tank
    "Cream": ((0.70, 0.66, 0.55, 1), 0.0, 0.5, {}),               # washer bag piping
    "ClearGlass": ((0.55, 0.6, 0.6, 1), 0.0, 0.02, {"alpha": 0.15}),   # vent window panes: see-through, with reflections
    "Lens": ((0.9, 0.9, 0.85, 1), 0.2, 0.05, {}),
    "SealedBeam": ((0.82, 0.84, 0.86, 1), 0.35, 0.1, {"flutes": 1.6, "coat": 1.0}),    # head/fog lamp lenses: glass over a grid of prisms
    # backup lamps: clear glass moulded in rings over a reflector that reads darker toward the rim
    "RingLens": ((0.42, 0.46, 0.44, 1), 0.5, 0.2, {"rings": 0.12, "rim": ((0.07, 0.08, 0.075, 1), 0.55, 1.1), "coat": 1.0}),
    # backup lamp housings and the rear bumper's bolt heads: chrome set in the car's rear face
    "RearChrome": ((0.85, 0.85, 0.87, 1), 1.0, 0.08, {"shade": (0.08, 0.04, 0.042, 1)}),
    "Hose": ((0.018, 0.018, 0.018, 1), 0.0, 0.38, {}),           # satin rubber hoses
    "Ceramic": ((0.5, 0.5, 0.48, 1), 0.4, 0.45, {}),             # ceramic-coated headers
    "Bronze": ((0.5, 0.37, 0.18, 1), 0.85, 0.45, {}),            # air filter mesh
}


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    color, metallic, rough, extra = PALETTE[name]
    mat.diffuse_color = color
    mat.metallic = min(metallic, 0.35)   # viewport only; full metal reads black in solid mode
    mat.roughness = rough
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if "coat" in extra:
        bsdf.inputs["Coat Weight"].default_value = extra["coat"]
    if "specular" in extra:
        bsdf.inputs["Specular IOR Level"].default_value = extra["specular"]
    if "flutes" in extra:                # moulded prisms: a fine 3D checker bump in object space (print mm),
        nt = mat.node_tree               # so the grid shows whichever way a lamp faces
        coord = nt.nodes.get("FluteCoord") or nt.nodes.new("ShaderNodeTexCoord")
        coord.name = "FluteCoord"
        tex = nt.nodes.get("Flutes") or nt.nodes.new("ShaderNodeTexChecker")
        tex.name = "Flutes"
        tex.inputs["Scale"].default_value = extra["flutes"]
        bump = nt.nodes.get("FluteBump") or nt.nodes.new("ShaderNodeBump")
        bump.name = "FluteBump"
        bump.inputs["Strength"].default_value = 0.5
        bump.inputs["Distance"].default_value = 0.05
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if "rings" in extra:                 # moulded rings round the lamp's axis (+X; the object carries it as
        nt = mat.node_tree               # "lens_axis"), one every extra["rings"] print mm, as a bump
        n = {}
        for name, kind in (("Coord", "ShaderNodeTexCoord"), ("Axis", "ShaderNodeAttribute"), ("Rel", "ShaderNodeVectorMath"),
                           ("Flat", "ShaderNodeVectorMath"), ("Dist", "ShaderNodeVectorMath"), ("Phase", "ShaderNodeMath"),
                           ("Wave", "ShaderNodeMath"), ("Bump", "ShaderNodeBump")):
            n[name] = nt.nodes.get("Ring" + name) or nt.nodes.new(kind)
            n[name].name = "Ring" + name
        n["Axis"].attribute_type, n["Axis"].attribute_name = 'OBJECT', "lens_axis"
        n["Rel"].operation, n["Flat"].operation, n["Dist"].operation = 'SUBTRACT', 'MULTIPLY', 'LENGTH'
        n["Flat"].inputs[1].default_value = (0.0, 1.0, 1.0)         # distance from the axis, in the lens's plane
        n["Phase"].operation, n["Wave"].operation = 'MULTIPLY', 'SINE'
        n["Phase"].inputs[1].default_value = 2 * math.pi / extra["rings"]
        n["Bump"].inputs["Strength"].default_value = 0.2
        n["Bump"].inputs["Distance"].default_value = 0.02
        nt.links.new(n["Coord"].outputs["Object"], n["Rel"].inputs[0])
        nt.links.new(n["Axis"].outputs["Vector"], n["Rel"].inputs[1])
        nt.links.new(n["Rel"].outputs["Vector"], n["Flat"].inputs[0])
        nt.links.new(n["Flat"].outputs["Vector"], n["Dist"].inputs[0])
        nt.links.new(n["Dist"].outputs["Value"], n["Phase"].inputs[0])
        nt.links.new(n["Phase"].outputs["Value"], n["Wave"].inputs[0])
        nt.links.new(n["Wave"].outputs["Value"], n["Bump"].inputs["Height"])
        nt.links.new(n["Bump"].outputs["Normal"], bsdf.inputs["Normal"])
        if "rim" in extra:               # the reflector behind reads darker toward the rim: extra["rim"] is
            rim, r0, r1 = extra["rim"]   # (colour, from, to print mm off the axis)
            for name, kind in (("Fade", "ShaderNodeMapRange"), ("Tint", "ShaderNodeMix")):
                n[name] = nt.nodes.get("Ring" + name) or nt.nodes.new(kind)
                n[name].name = "Ring" + name
            n["Fade"].interpolation_type = 'SMOOTHSTEP'
            n["Fade"].inputs["From Min"].default_value, n["Fade"].inputs["From Max"].default_value = r0, r1
            n["Tint"].data_type = 'RGBA'
            tint_a, tint_b = (i for i in n["Tint"].inputs if i.type == 'RGBA')
            tint_a.default_value, tint_b.default_value = color, rim
            nt.links.new(n["Dist"].outputs["Value"], n["Fade"].inputs["Value"])
            nt.links.new(n["Fade"].outputs["Result"], n["Tint"].inputs["Factor"])
            nt.links.new(next(o for o in n["Tint"].outputs if o.type == 'RGBA'), bsdf.inputs["Base Color"])
    if "shade" in extra:                 # chrome set in the car's rear face: EEVEE reflects only the world, but a
        nt = mat.node_tree               # reflection heading steeply forward (-X) would meet the car's own shadowed
        n = {}                           # valance and underside, so those darken to extra["shade"]
        for name, kind in (("Coord", "ShaderNodeTexCoord"), ("Split", "ShaderNodeSeparateXYZ"), ("Fac", "ShaderNodeMapRange"),
                           ("Mix", "ShaderNodeMix")):
            n[name] = nt.nodes.get("Shade" + name) or nt.nodes.new(kind)
            n[name].name = "Shade" + name
        n["Fac"].interpolation_type = 'SMOOTHSTEP'
        n["Fac"].inputs["From Min"].default_value, n["Fac"].inputs["From Max"].default_value = -0.4, -0.7
        n["Mix"].data_type = 'RGBA'
        mix_a, mix_b = (i for i in n["Mix"].inputs if i.type == 'RGBA')
        mix_a.default_value, mix_b.default_value = color, extra["shade"]
        nt.links.new(n["Coord"].outputs["Reflection"], n["Split"].inputs[0])
        nt.links.new(n["Split"].outputs["X"], n["Fac"].inputs["Value"])
        nt.links.new(n["Fac"].outputs["Result"], n["Mix"].inputs["Factor"])
        nt.links.new(next(o for o in n["Mix"].outputs if o.type == 'RGBA'), bsdf.inputs["Base Color"])
    if "alpha" in extra:                 # EEVEE: blend it over what lies behind
        bsdf.inputs["Alpha"].default_value = extra["alpha"]
        mat.surface_render_method = "BLENDED"
    return mat


def assign(ob, name):
    ob.data.materials.clear()
    ob.data.materials.append(material(name))


# cutter-name prefix -> material its cut faces take on the body
CUTTER_MATERIALS = [
    ("Cut_WindowOpen", "Black"), ("Cut_DoorOpen", "PaintJamb"), ("Cut_ScuffPlate", "BrushedAl"), ("Cut_Striker", "Chrome"),
    ("Cut_Glass", "Chrome"), ("Cut_Louver", "Black"), ("Cut_ScoopIntake", "Black"),
    ("Cut_ParkLight", "Paint"), ("Cut_Beltline", "Black"), ("Cut_BossSlot", "Black"), ("Cut_EngineBay", "Black"),
    ("Cut_Hinge", "Black"), ("Cut_Cabin", "Black"), ("Cut_ChassisAxle", "Black"), ("Cut_ExhaustSlot", "Black"),
    ("Cut_Keyway", "Black"), ("Cut_DoorPin", "Black"), ("Cut_LockFace", "Chrome"), ("Cut_LockPocket", "Paint"),
    ("Add_", "Chrome"), ("Cut_Grille", "Black"), ("Cut_PlateRecess", "Black"), ("Cut_BackupSocket", "Black"),
    ("Cut_DiffTunnel", "Black"), ("Cut_RearUnder", "Black"), ("Cut_Arch", "Black"),
    ("Cut_Headlight", "Paint"), ("Cut_Spokes", "Black"), ("Cut_Taillight", "Black"), ("Cut_GasCap", "Chrome"),
    ("Cut_Deck", "PaintJamb"),
]

PART_MATERIALS = [
    ("Letters_", "Chrome"), ("AirCleaner_Filter", "Bronze"), ("Engine_HoseClamp", "Chrome"), ("Engine_Hose", "Hose"),
    ("Engine_Belt", "Rubber"), ("Engine_WireSep", "Black"), ("Engine_Wire", "WireBlue"), ("Engine_Header", "Ceramic"),
    ("Engine_FanHub", "Steel"), ("Engine_Fan", "Black"), ("Engine_Intake", "CastAl"), ("Engine_HeaterNeck", "CastAl"),
    ("Engine_Carb", "CastAl"), ("Engine_AltSlot", "Black"), ("Engine_DistBody", "CastAl"), ("Engine_CrankPulley", "Black"),
    ("Engine_PumpPulley", "Black"), ("Engine_Bellhousing", "CastIron"), ("Engine_CoilLead", "Red"),
    ("Engine_BootCoil", "Black"), ("Engine_CoilTower", "Black"), ("ValveCover_R_Logo", "Blue"),
    ("ValveCover_L_BreatherTop", "Chrome"), ("AirCleaner_Nut", "Steel"), ("Engine_Boot", "Black"), ("Engine_Coil", "Black"),
    ("Engine_DistCap", "Black"), ("Engine_DistTower", "Black"), ("Engine_DistVacuum", "Chrome"), ("Engine_FuelLine", "Steel"),
    ("Engine_AltPulley", "Chrome"), ("Engine_Alternator", "CastAl"), ("Engine_OilFilter", "EngineBlue"),
    ("BayTub_Bushing", "Red"), ("BayTub_Cable", "Rubber"), ("BayTub_Harness", "Rubber"), ("BayTub_RadCap", "SatinChrome"),
    ("BayTub_RadTank", "TankGrey"), ("BayTub_RadOverflow", "Rubber"), ("BayTub_MCCap", "Chrome"), ("BayTub_MCBail", "Steel"),
    ("BayTub_BrakeLine", "Steel"), ("BayTub_TowerNut", "Steel"), ("BayTub_HeaterFitting", "Steel"),
    ("BayTub_WasherCap", "Aluminum"), ("BayTub_WasherPiping", "Cream"), ("BayTub_WasherGrommet", "Steel"),
    ("BayTub_WasherLabel", "White"), ("BayTub_WasherFord", "White"), ("BayTub_Washer", "Vinyl"), ("DoorHandle", "Chrome"),
    ("DoorLock", "Chrome"), ("DoorMirrorSlot", "Black"), ("DoorCardTrim", "Chrome"), ("DoorCardKnob", "White"),
    ("DoorCard", "Vinyl"), ("DoorLatchRotor", "Black"), ("DoorLatchScrew", "Steel"), ("DoorLatch", "Chrome"),
    ("DoorSeal", "Rubber"), ("DoorBracket", "Black"), ("DoorBumper", "Rubber"), ("DoorVentPane", "ClearGlass"),
    ("DoorVent", "Chrome"), ("Door_L_Skin", "Paint"), ("Door_R_Skin", "Paint"), ("DoorCove", "Paint"), ("Door", "PaintJamb"),
    ("Bumper_R_Guard", "Rubber"), ("Bumper_R_Bolt", "RearChrome"), ("GasCap_Face", "SatinChrome"), ("ExhaustBore", "Black"),
    ("BackupLens", "RingLens"), ("BackupLight", "RearChrome"), ("GasCap_Ring", "Black"), ("GasCap_TriR", "Red"), ("GasCap_TriW", "White"),
    ("GasCap_TriFrame", "Black"), ("DiffCover", "Black"), ("GasCap_TriB", "Blue"),
    ("Exhaust", "Chrome"), ("Body", "Paint"), ("Rim", "Chrome"), ("Axle", "Black"), ("Tire", "Rubber"), ("Bumper", "Chrome"),
    ("GrilleSurround", "Chrome"), ("Corral", "Chrome"), ("Mirror", "Chrome"), ("FogLamp", "Chrome"), ("Grille_Bar", "Chrome"),
    ("Grille", "Black"),
    ("Chassis", "Black"), ("InteriorTub", "Carpet"), ("HoodProp", "Black"), ("Hood_LouverCut", "Black"),
    ("Hood_PropHole", "Black"), ("Hood", "Paint"), ("BayTub", "GlossBlack"), ("EngineBlock", "EngineBlue"),
    ("Engine_", "EngineBlue"), ("ValveCover", "Black"), ("AirCleaner", "Black"), ("Brace", "GlossBlack"),
    ("Tub_SeatTrim", "Chrome"), ("Tub_GaugeBezel", "Chrome"), ("Tub_DashTrim", "Chrome"), ("Tub_ConsoleTrim", "Chrome"),
    ("Tub_Shifter", "Chrome"), ("Tub_", "Vinyl"), ("SteeringWheel", "Vinyl"), ("Headlight", "Chrome"), ("Taillight", "TailRed"),
    ("TailBezel", "Chrome"), ("GasCap", "Chrome"), ("Glass_", "Glass"), ("HeadRing", "Chrome"), ("HeadLens", "SealedBeam"),
    ("FogRing", "Chrome"), ("FogLens", "SealedBeam"), ("ParkLight", "Chrome"), ("ParkRing", "Chrome"), ("ParkLens", "Lens"),
    ("FenderTriR", "Red"), ("FenderTriW", "White"), ("FenderTriB", "Blue"),
]


def _check_order(table):
    """First match wins, so a prefix listed after a shorter one it starts with would never apply."""
    for i, (p, _) in enumerate(table):
        for q, _ in table[i + 1:]:
            assert not q.startswith(p), f"material prefix {q!r} is shadowed by {p!r}"


_check_order(CUTTER_MATERIALS)
_check_order(PART_MATERIALS)


def apply_all():
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        table = CUTTER_MATERIALS if ob.name.startswith(("Cut_", "Add_")) else PART_MATERIALS
        for prefix, mat in table:
            if ob.name.startswith(prefix):
                assign(ob, mat)
                break
        else:
            if ob.name.startswith("Cut_"):
                assign(ob, "Paint")
        for mod in ob.modifiers:
            if mod.type == 'BOOLEAN':
                mod.material_mode = 'TRANSFER'
