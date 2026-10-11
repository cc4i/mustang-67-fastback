"""Engine bay: opening hood, the bay in the body, the black bay liner and the V8.

The hood is cut from the body and pivots on two printed pegs at its rear corners that drop
into open-top slots in the body (lift it out, drop it back). Underneath, a black liner ("bay
tub": inner fenders with shock towers, firewall, radiator support, radiator, battery, washer
bottle, brake booster) carries a small-block V8 printed in blue, with black valve covers and
air cleaner. Everything under the hood is sized from the hood's real underside so it clears
when closed. Units are real-car millimetres unless noted; SCALE converts to print mm.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import body
import details
import features as F
from body import SCALE
from details import line_band, rect
from features import text_solid, tube
from interior import _box, _cylinder, _side_profile

# ---------------------------------------------------------------- layout

HOOD_FRONT_X, HOOD_REAR_X = 140.0, 1630.0
HOOD_HALF_FRONT, HOOD_HALF_REAR = 615.0, 640.0
HOOD_OUTLINE = F.rounded_poly([(HOOD_FRONT_X, -HOOD_HALF_FRONT), (HOOD_REAR_X, -HOOD_HALF_REAR),
                               (HOOD_REAR_X, HOOD_HALF_REAR), (HOOD_FRONT_X, HOOD_HALF_FRONT)], [40, 12, 12, 40])
GAP, REAR_GAP = 5.0, 40.0        # around the hood (real mm); the rear gap lets the rear edge swing as it opens
RECESS_OUTLINE = F.rounded_poly([(HOOD_FRONT_X - GAP, -(HOOD_HALF_FRONT + GAP)), (HOOD_REAR_X + REAR_GAP, -(HOOD_HALF_REAR + GAP)),
                                 (HOOD_REAR_X + REAR_GAP, HOOD_HALF_REAR + GAP), (HOOD_FRONT_X - GAP, HOOD_HALF_FRONT + GAP)],
                                [40, 12, 12, 40])
HOOD_T = 1.1                     # hood skin (print mm)
RIB_DEPTH = 1.0                  # underside bracing below the skin (print mm)
RIB_TOP = 0.65                   # ribs reach this far up into the skin: below the 0.5 mm louver slots
LEDGE_DROP = 0.08                # clearance between the closed hood's skin and the ledge it rests on (print mm)

BAY_X0, BAY_X1, BAY_HALF = 300.0, 1625.0, 560.0
WALL_T = 30.0                    # liner wall thickness
LINER_FIT = 5.0                  # liner-to-bay clearance (real mm, ~0.2 mm)
FLOOR_Z0, FLOOR_Z1 = body.Z_BOTTOM, body.Z_BOTTOM + 40.0
BOSS_X0, BOSS_X1, BOSS_TOP = 727.0, 857.0, 400.0   # clear of the chassis front axle boss

PEG_R, PEG_Y0, PEG_Y1 = 13.0, 625.0, 667.0         # hinge pegs (real mm)
PIVOT_DROP = 24.0                                  # pivot sits ~1 mm under the surface at the rear corners
# The crowned hood stands well above the pivot at its centre, so a pivot at the rear edge would
# swing the edge back into the cowl. With the pivot ~3.75 mm ahead of the edge the rear lip dips
# into a shallow plenum instead (as on the real car).
PIVOT_X = HOOD_REAR_X - 90.0
PLENUM_DEPTH = 80.0                                # plenum floor below the pivot (real mm)
SLOT_CLEAR = 4.0
HOOD_OPEN_DEG = 50.0                               # prop-rod angle

BRACE_T = 1.0 / SCALE            # V brace thickness (real mm)
TOWER_ROUND = 18.0               # shock-tower top edge rounding
TANK_H = 55.0                    # radiator top tank height
RAD_CAP = (385.0, 110.0)         # filler neck, off-centre on the tank (clear of the prop-rod socket)
TANK_RIB_PITCH, TANK_RIB_R = 28.0, 9.0   # half-round corrugations over the top tank
RAD_INLET_X1 = 448.0             # the radiator's hose necks stand out to here (the hoses end 4 mm short)
UPPER_HOSE_Y = 212.0             # upper hose: thermostat housing to the passenger-side tank inlet
LOWER_HOSE_END = (RAD_INLET_X1 + 4.0, -235.0, 355.0)   # lower hose: water pump to the driver-side outlet, under the shroud
FAN_Z, FAN_R = 590.0, 170.0      # fan centre height and blade tip radius
SHROUD_LIP = 22.0                # the fan shroud: a panel over the core, standing on the floor, and a short rolled lip round
                                 # the fan opening (a deeper funnel prints as a long cantilever off the radiator)
WASHER_T = 55.0                  # the washer bag's thickness off the apron
WASHER_X, WASHER_Z0 = (420.0, 630.0), 520.0
HEATER_CORE = [(372.0, 600.0), (300.0, 770.0)]   # heater hose fittings on the firewall (y, z)
HEATER_FITTING = 25.0
SCRIPT_FONT = "/System/Library/Fonts/Supplemental/Brush Script.ttf"


def surface_z(tree, x, y):
    """Body outer surface height (real mm) at plan position (x, y)."""
    return details.hit_w(tree, "+Z", x, y) / SCALE


def rib_bottom(tree, x, y):
    """Lowest point of the closed hood's underside bracing above (x, y) (real mm)."""
    return surface_z(tree, x, y) - (HOOD_T + RIB_DEPTH) / SCALE


def headroom(tree, x0, x1, y0, y1, clearance=0.4, n=6):
    """Highest z (real mm) a part may reach under the closed hood over a plan rectangle."""
    lo = min(rib_bottom(tree, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n) for i in range(n + 1) for j in range(n + 1))
    return lo - clearance / SCALE


def front_top(tree):
    """Highest the radiator support may stand under the closed hood (real mm)."""
    f = LINER_FIT
    return headroom(tree, BAY_X0 + f, 440.0, -(BAY_HALF - f), BAY_HALF - f, clearance=0.5)


def rad_top(tree):
    """Top of the radiator's top tank (real mm), a little under the support."""
    return front_top(tree) - 20.0


def pivot(tree):
    z = surface_z(tree, PIVOT_X, HOOD_HALF_REAR) - PIVOT_DROP
    return Vector((PIVOT_X, 0.0, z))


# ---------------------------------------------------------------- body cuts

def body_cutters(tree, body_mesh):
    """[(name, cutter)]: hood recess, the bay, and the hinge pockets/slots."""
    P = pivot(tree)
    cuts = [("Cut_HoodRecess", F.surface_cutter("Cut_HoodRecess", body_mesh, "+Z", RECESS_OUTLINE, HOOD_T + LEDGE_DROP,
                                                rings=10, tree=tree)),
            ("Cut_EngineBay", F.prism_cutter("Cut_EngineBay", "+Z", rect(BAY_X0, -BAY_HALF, BAY_X1, BAY_HALF, 0),
                                             (body.Z_BOTTOM - 60) * SCALE, 80.0))]
    c = SLOT_CLEAR
    half = HOOD_HALF_REAR + GAP + 3
    cuts.append(("Cut_HingePlenum", F.prism_cutter(
        "Cut_HingePlenum", "+Z", rect(P.x - 70.0, -half, HOOD_REAR_X + REAR_GAP, half, 0), (P.z - PLENUM_DEPTH) * SCALE, 80.0)))
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        y0, y1 = sorted((s * (HOOD_HALF_REAR + GAP), s * (PEG_Y1 + c)))
        cuts.append((f"Cut_HingeSlot_{tag}", F.prism_cutter(
            f"Cut_HingeSlot_{tag}", "+Z", rect(P.x - PEG_R - c, y0, P.x + PEG_R + c, y1, 0), (P.z - PEG_R - c) * SCALE, 80.0)))
    return cuts


# ---------------------------------------------------------------- hood

def _hood_ribs():
    """Plan outlines of the underside bracing (perimeter, spine, cross bars, corner diagonals)."""
    x0, x1, h, w = BAY_X0 + 30, BAY_X1 - 30, 499.0, 19.0
    e = 6.0          # inner ribs stop just inside the frame: no coplanar end faces in the union
    ribs = [rect(x0, -h, x0 + w, h, 0), rect(x1 - w, -h, x1, h, 0),
            rect(x0 + e, h - w, x1 - e, h, 0), rect(x0 + e, -h, x1 - e, -h + w, 0),
            rect(x0 + e, -w / 2, x1 - e, w / 2, 0)]
    for x in (700.0, 1150.0):
        ribs.append(rect(x - w / 2, -h + e, x + w / 2, h - e, 0))
    for s in (-1, 1):
        ribs.append(line_band((x0 + 20, s * (h - 20)), (690.0, s * 30), w))
        ribs.append(line_band((1160.0, s * 30), (x1 - 20, s * (h - 20)), w))
    return ribs


PROP_HOOD_POINT = (420.0, 0.0)          # where the prop rod meets the hood underside
PROP_BASE = (320.0, 0.0)                # socket on the radiator support


def hood_parts(tree, body_mesh):
    """(hood, union pieces, cut pieces, pivot). The hood is modelled closed, in place."""
    P = pivot(tree)
    hood = F.surface_solid("Hood", body_mesh, "+Z", HOOD_OUTLINE, lambda u, v: -HOOD_T, lambda u, v: 0.0,
                           rings=24, tree=tree, step=0.4)
    pieces = [p for _, p in details.hood_scoop_pieces(tree, body_mesh)]
    for k, outline in enumerate(_hood_ribs()):
        # ribs reach well up into the skin so the union is robust to the two surfaces' sampling
        pieces.append(F.surface_solid(f"Hood_Rib{k}", body_mesh, "+Z", outline, lambda u, v: -(HOOD_T + RIB_DEPTH),
                                      lambda u, v: -RIB_TOP, rings=2, tree=tree, step=0.5))
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        y0, y1 = sorted((s * 600.0, s * (HOOD_HALF_REAR - 2)))
        pieces.append(F.surface_solid(f"Hood_HingeBoss_{tag}", body_mesh, "+Z", rect(P.x - 45.0, y0, P.x + 45.0, y1, 0),
                                      lambda u, v: -(PIVOT_DROP + PEG_R + 8) * SCALE, lambda u, v: -0.1, rings=3, tree=tree))
        pieces.append(_cylinder(f"Hood_Peg_{tag}", (P.x, s * PEG_Y0, P.z), (P.x, s * PEG_Y1, P.z), PEG_R, 20))
    # cup for the prop rod's upper end
    px, py = PROP_HOOD_POINT
    pieces.append(F.surface_solid("Hood_PropCup", body_mesh, "+Z", F.circle(px, py, 28.0, 20),
                                  lambda u, v: -(HOOD_T + RIB_DEPTH + 0.6), lambda u, v: -RIB_TOP, rings=3, tree=tree))
    cuts = [p for _, p in details.hood_louver_cutters(tree, body_mesh)]
    cuts.append(F.surface_solid("Hood_PropHole", body_mesh, "+Z", F.circle(px, py, 0.65 / SCALE, 16),
                                lambda u, v: -(HOOD_T + RIB_DEPTH + 1.0), lambda u, v: -(HOOD_T + 0.2), rings=2, tree=tree))
    return hood, pieces, cuts, P


def set_hood_pivot(hood, pieces, P):
    """Move the hood's origin to the hinge axis and parent its feature pieces, so rotating the hood
    object about its local Y opens it."""
    Ps = P * SCALE
    hood.data.transform(Matrix.Translation(-Ps))
    hood.location = Ps
    bpy.context.view_layer.update()
    for p in pieces:
        p.parent = hood
        p.matrix_parent_inverse = hood.matrix_world.inverted()


def open_angle_point(P, point, deg):
    """Where a closed-hood point ends up after opening by deg about the hinge (real mm)."""
    v = Vector(point) - P
    rot = Matrix.Rotation(math.radians(deg), 3, 'Y')
    return P + rot @ v


# ---------------------------------------------------------------- bay liner (black)

def _wall_gusset(name, x0, x1, y_wall, out, z):
    """45 degree wedge under something standing `out` mm off an apron's inner face (y_wall), whose
    underside is at z: it carries that underside so it prints without support."""
    yw = y_wall - math.copysign(2.0, out)                  # (from 2 mm inside the apron: no coplanar faces)
    return F.prism_cutter(name, "+X", [(yw, z - abs(out)), (y_wall + out, z + 1.0), (yw, z + 1.0)], x0 * SCALE, x1 * SCALE)


def liner_parts(tree):
    """(liner, union pieces, cut pieces, brace_level) for the black bay liner. Factory layout: the
    battery and starter relay at the passenger-side front, the washer bag hanging on the driver-side
    apron, the brake booster and master cylinder on the driver side of the firewall."""
    f = LINER_FIT
    xa, xb, h = BAY_X0 + f, BAY_X1 - f, BAY_HALF - f
    liner = F.prism_cutter("BayTub", "+Z", rect(BOSS_X1 + f, -h, xb, h, 20), FLOOR_Z0 * SCALE, FLOOR_Z1 * SCALE)
    pieces = [F.prism_cutter("BayTub_FloorFront", "+Z", rect(xa, -h, BOSS_X0 - f, h, 20), FLOOR_Z0 * SCALE, FLOOR_Z1 * SCALE)]
    cuts = []
    # common level for the shock-tower tops, firewall top and the V brace that rests on them
    brace_top = min(headroom(tree, 1000, 1600, -460, 460, clearance=0.4), headroom(tree, 1560, 1620, -525, 525))
    level = brace_top - BRACE_T
    # inner fenders: top edge just under the hood ledge, notched over the axle boss, and dropped
    # below the plenum floor near the hinge where the hood's rear corners dip as it opens
    P = pivot(tree)
    plenum_floor = P.z - PLENUM_DEPTH - 15.0

    def apron_top(x, s):
        z = surface_z(tree, x, s * BAY_HALF) - (HOOD_T + LEDGE_DROP + 0.3) / SCALE
        return min(z, plenum_floor) if x > P.x - 110.0 else z

    for s in (-1, 1):
        xs = sorted(set([xa + (xb - xa) * k / 16 for k in range(17)] + [P.x - 111.0, P.x - 109.0]))
        ledge = [(x, apron_top(x, s)) for x in xs]
        prof = [(xa, FLOOR_Z0), (BOSS_X0 - f, FLOOR_Z0), (BOSS_X0 - f, BOSS_TOP), (BOSS_X1 + f, BOSS_TOP),
                (BOSS_X1 + f, FLOOR_Z0), (xb, FLOOR_Z0)] + list(reversed(ledge))
        y0, y1 = sorted((s * h, s * (h - WALL_T)))
        pieces.append(_side_profile(f"BayTub_Apron{s}", prof, y0, y1))
        # shock tower down to the frame rail, its top rounded off, three nuts round the shock mount
        y0, y1 = sorted((s * (h - WALL_T + 5), s * 400.0))
        tower = rect(880.0, y0, 1160.0, y1, 40)
        top = rect(880.0 + TOWER_ROUND, y0 + TOWER_ROUND, 1160.0 - TOWER_ROUND, y1 - TOWER_ROUND, 40 - TOWER_ROUND)
        shoulder = F.offset_closed(tower, -TOWER_ROUND * 0.3)
        pieces.append(F.loft_solid(f"BayTub_Tower{s}", "+Z", [(tower, FLOOR_Z0 * SCALE), (tower, (level - TOWER_ROUND) * SCALE),
                                                               (shoulder, (level - TOWER_ROUND * 0.3) * SCALE), (top, level * SCALE)]))
        for k, (x, y) in enumerate(((1090.0, 470.0), (1112.0, 428.0), (1068.0, 505.0))):
            pieces.append(_cylinder(f"BayTub_TowerNut{s}{k}", (x, s * y, level - 4), (x, s * y, level + 6), 10, 6))
    # firewall and radiator support
    pieces.append(_box("BayTub_Firewall", xb - WALL_T, xb, -h, h, FLOOR_Z0, level, 0))
    support_top, tank_top = front_top(tree), rad_top(tree)
    pieces.append(_box("BayTub_RadSupport", xa, xa + WALL_T, -h, h, FLOOR_Z0, support_top, 0))
    # radiator: core, a satin top tank with rounded top edges and half-round corrugations, the
    # octagonal chrome cap with its overflow tube, the upper hose inlet (passenger side), and a fan
    # shroud below the tank: a panel over the core with a short rolled lip round the fan
    rad_x1 = 425.0
    tank_x0, tank_x1, tank_z0 = xa + WALL_T, rad_x1 + 6.0, tank_top - TANK_H
    pieces.append(_box("BayTub_Radiator", tank_x0, rad_x1, -380.0, 380.0, FLOOR_Z0, tank_z0 + 5, 25))
    tank = F.rounded_poly([(tank_x0, tank_z0), (tank_x1, tank_z0), (tank_x1, tank_top), (tank_x0, tank_top)], [0, 0, 40, 40], 10)
    pieces.append(F.prism_cutter("BayTub_RadTank", "+Y", tank, -392.0 * SCALE, 392.0 * SCALE))
    over = [p for p in F.offset_closed(tank, -3.0) if p[1] > tank_z0 + 10.0]          # just under the tank's skin
    over.sort(key=lambda p: p[0])
    taper = [3.0, 5.0, 7.0]                     # the ribs' ends sink into the tank's faces (no overhang to start in mid-air)
    rib_r = taper + [TANK_RIB_R] * (len(over) - 6) + taper[::-1]
    cx, cy = RAD_CAP
    hose_z = tank_top - TANK_H / 2
    y = -392.0 + TANK_RIB_PITCH / 2
    k = 0
    while y < 392.0:
        if abs(y - cy) > 70.0 and abs(y - UPPER_HOSE_Y) > 32.0:
            pieces.append(tube(f"BayTub_RadTankRib{k}", [(x, y, z) for x, z in over], rib_r, 12))
            k += 1
        y += TANK_RIB_PITCH
    pieces.append(_cylinder("BayTub_RadNeck", (cx, cy, tank_top - 5), (cx, cy, tank_top + 10), 22, 20))
    pieces += [_cylinder("BayTub_RadCap", (cx, cy, tank_top + 8), (cx, cy, tank_top + 15), 31, 8),    # octagonal skirt,
               _cylinder("BayTub_RadCapDome", (cx, cy, tank_top + 14), (cx, cy, tank_top + 19), 22, 24),   # domed top
               _cylinder("BayTub_RadCapButton", (cx, cy, tank_top + 18), (cx, cy, tank_top + 21), 8, 16)]
    # overflow tube from the filler neck along the tank's rear top edge and down past its driver-side
    # end (clear of it) into the floor
    pieces.append(tube("BayTub_RadOverflow", F.chaikin([(cx + 14, cy - 12, tank_top + 6), (tank_x1 - 12, cy - 60, tank_top - 2),
                                                        (tank_x1 - 10, -300.0, tank_top - 8), (tank_x1 - 10, -405.0, tank_top - 30),
                                                        (tank_x1 - 10, -405.0, FLOOR_Z1 - 5.0)], 2), 7, 8))
    pieces.append(_cylinder("BayTub_RadInlet", (rad_x1 - 5, UPPER_HOSE_Y, hose_z), (RAD_INLET_X1, UPPER_HOSE_Y, hose_z), 19))
    _, oy, oz = LOWER_HOSE_END
    pieces.append(_cylinder("BayTub_RadOutlet", (rad_x1 - 5, oy, oz), (RAD_INLET_X1, oy, oz), 16))
    shroud_top = tank_z0 - 8
    fy, fz = 0.0, FAN_Z
    pieces.append(_box("BayTub_Shroud", rad_x1 - 5, rad_x1 + 15, -370.0, 370.0, FLOOR_Z1 - 5, shroud_top, 30))
    pieces.append(_cylinder("BayTub_ShroudLip", (rad_x1 + 10, fy, fz), (rad_x1 + 15 + SHROUD_LIP, fy, fz), FAN_R + 30, 64))
    hole_r = FAN_R + 18
    cuts.append(_cylinder("BayTub_ShroudHole", (rad_x1 - 5, fy, fz), (rad_x1 + 20 + SHROUD_LIP, fy, fz), hole_r, 64))
    # radiator core texture, seen through the shroud opening (the core face there is at rad_x1 - 5)
    for k, y in enumerate(range(-int(hole_r) + 20, int(hole_r) - 19, 30)):
        dz = math.sqrt(max(0.0, (hole_r - 6) ** 2 - (abs(y) + 5) ** 2))
        cuts.append(F.prism_cutter(f"BayTub_RadFin{k}", "+X", rect(y - 5.0, fz - dz, y + 5.0, fz + dz, 0),
                                   (rad_x1 - 12.0) * SCALE, (rad_x1 - 3.0) * SCALE))
    # battery and starter relay (passenger side front), cables to the relay and the apron
    s = 1
    wall_in = s * (h - WALL_T)                                # inner face of the passenger-side apron
    bat_top = min(760.0, headroom(tree, 360, 600, 395, h - WALL_T + 5) - 30.0)    # room for the posts and cables
    pieces.append(_box("BayTub_Battery", 360.0, 600.0, 395.0, h - WALL_T + 5, FLOOR_Z0, bat_top, 12))
    pieces.append(_cylinder("BayTub_BatPos", (420.0, 470.0, bat_top - 5), (420.0, 470.0, bat_top + 22), 16))
    pieces.append(_cylinder("BayTub_BatNeg", (540.0, 470.0, bat_top - 5), (540.0, 470.0, bat_top + 22), 16))
    pieces.append(_box("BayTub_Solenoid", 640.0, 700.0, wall_in - 38, wall_in, 600.0, 660.0, 8))
    pieces.append(_wall_gusset("BayTub_SolenoidGusset", 645.0, 695.0, wall_in, -38.0, 600.0))
    pieces.append(tube("BayTub_CablePos", [(420.0, 470.0, bat_top + 18), (560.0, 490.0, bat_top + 14),
                                           (655.0, wall_in - 30, 666.0)], 11, 8))
    pieces.append(tube("BayTub_CableNeg", [(540.0, 470.0, bat_top + 18), (600.0, wall_in - 12, 640.0),
                                           (600.0, wall_in - 8, 560.0)], 11, 8))
    # washer bag hanging flat on the driver-side apron: a soft pillow with a cream bead round its
    # face, grommets in its top corners, a big label, the cap on a short neck. Its underside rises
    # at 45 degrees off the apron, so it prints without support.
    wall_in = -(h - WALL_T)
    x0, x1 = WASHER_X
    z0 = WASHER_Z0
    wb_top = min(760.0, headroom(tree, x0, x1, -525, -470) - 40.0)
    yi = wall_in + WASHER_T
    face_z0 = z0 + WASHER_T

    def bag(d, inset):                   # section d mm off the apron
        return F.rounded_poly([(x0 + inset, z0 + d), (x1 - inset, z0 + d), (x1 - inset, wb_top - inset), (x0 + inset, wb_top - inset)],
                              [30, 30, 22, 22])
    t = WASHER_T
    pillow = [(-3.0, 2.0), (0.35 * t, 3.0), (0.6 * t, 5.0), (0.8 * t, 8.0), (0.92 * t, 12.0), (t, 18.0)]   # (mm off the apron, inset)
    pieces.append(F.loft_solid("BayTub_Washer", "-Y", [(bag(d, inset), -(wall_in + d) * SCALE) for d, inset in pillow]))
    # the bead's centre line is just inside the face, so it grows out of the bag rather than
    # starting in mid-air
    e = 23.0
    ring = F.resample(rect(x0 + e, face_z0 + 10.0, x1 - e, wb_top - e, 10), 20.0)
    pieces.append(tube("BayTub_WasherPiping", [(x, yi - 0.5, z) for x, z in ring], 2.5, 8, closed=True))
    nx = (x0 + x1) / 2 + 20.0
    pieces.append(_cylinder("BayTub_WasherNeck", (nx, yi - WASHER_T / 2, wb_top - 10), (nx, yi - WASHER_T / 2, wb_top + 15), 12))
    pieces.append(_cylinder("BayTub_WasherCap", (nx, yi - WASHER_T / 2, wb_top + 12), (nx, yi - WASHER_T / 2, wb_top + 26), 18, 24))
    lx0, lz0, lx1, lz1, w = x0 + 36.0, face_z0 + 22.0, x1 - 36.0, wb_top - 44.0, 3.0     # the label's border
    strips = ((lx0, lz0, lx1, lz0 + w), (lx0, lz1 - w, lx1, lz1), (lx0, lz0, lx0 + w, lz1), (lx1 - w, lz0, lx1, lz1))
    for k, (u0, v0, u1, v1) in enumerate(strips):
        pieces.append(F.prism_cutter(f"BayTub_WasherLabel{k}", "-Y", rect(u0, v0, u1, v1, 0), (-yi - 1.5) * SCALE, (-yi + 2.0) * SCALE))
    # the script and grommets are let into the bag (raised on its upright face they would start in
    # mid-air); no bold pass, which breaks this joined-up script's mesh
    lc = (lx0 + lx1) / 2
    cuts.append(text_solid("BayTub_WasherFord", "Ford", 40.0, 0.3, (lc, yi, (lz0 + lz1) / 2 + 4.0), (-1, 0, 0), (0, 0, 1),
                           embed=0.1, font=SCRIPT_FONT, center=True))
    for k, gx in enumerate((x0 + 42.0, x1 - 42.0)):
        cuts.append(_cylinder(f"BayTub_WasherGrommet{k}", (gx, yi + 2.4, wb_top - 33.0), (gx, yi - 30.0, wb_top - 33.0), 6, 16))
    # brake booster on the driver side of the firewall, master cylinder with one lid and a bail
    pieces.append(_cylinder("BayTub_Booster", (1480.0, -360.0, 690.0), (xb - WALL_T + 5, -360.0, 690.0), 85, 28))
    pieces.append(_box("BayTub_BoosterBracket", 1490.0, xb - WALL_T + 5, -425.0, -295.0, FLOOR_Z0, 690.0, 0))   # carries its underside
    mc_top = min(790.0, headroom(tree, 1420, 1480, -400, -320) - 30.0)
    pieces.append(_box("BayTub_MasterCyl", 1415.0, 1485.0, -400.0, -320.0, 650.0, mc_top, 12))
    pieces.append(_box("BayTub_MCCap", 1418.0, 1482.0, -397.0, -323.0, mc_top - 3, mc_top + 9, 10))
    pieces.append(tube("BayTub_MCBail", F.chaikin([(1424.0, -360.0, mc_top + 4), (1428.0, -360.0, mc_top + 12),
                                                   (1450.0, -360.0, mc_top + 15), (1472.0, -360.0, mc_top + 12),
                                                   (1476.0, -360.0, mc_top + 4)], 2), 3.5, 8))
    pieces.append(tube("BayTub_BrakeLine", [(1420.0, -340.0, 690.0), (1360.0, -420.0, 640.0),
                                            (1180.0, wall_in - 3, 620.0)], 8, 8))   # lowest end buried in the apron
    # heater core fittings on the passenger side of the firewall (the heater hoses end at them)
    for k, (y, z) in enumerate(HEATER_CORE):
        pieces.append(_cylinder(f"BayTub_HeaterFitting{k}", (xb - WALL_T - HEATER_FITTING, y, z), (xb - WALL_T + 5, y, z), 14))
    # socket for the prop rod's lower end
    bx, by = PROP_BASE
    pieces.append(_box("BayTub_PropSocket", xa, bx + 42, by - 32, by + 32, support_top - 40, support_top, 6))   # latch bracket
    cuts.append(_cylinder("BayTub_PropHole", (bx + 10, by, support_top - 25), (bx + 10, by, support_top + 10),
                          1.0 / SCALE))                                # roomy: the rod leans
    # brace bushings on the shock-tower tops (red on the car), beside the brace feet
    for s in (-1, 1):
        pieces.append(_cylinder(f"BayTub_Bushing{s}", (950.0, s * 470.0, level - 5), (950.0, s * 470.0, level + 22), 25))
    # voltage regulator on the driver-side apron, the wiring harness clipped along it (its centre
    # line just inside the wall, so its lowest point grows out of the wall rather than floating)
    pieces.append(_box("BayTub_Regulator", 720.0, 795.0, wall_in, wall_in + 30, 640.0, 700.0, 6))
    pieces.append(_wall_gusset("BayTub_RegulatorGusset", 725.0, 790.0, wall_in, 30.0, 640.0))
    pieces.append(tube("BayTub_Harness", [(650.0, wall_in - 3, 720.0), (880.0, wall_in - 3, 735.0),
                                          (1500.0, wall_in - 3, 735.0)], 12, 8))
    return liner, pieces, cuts, level


def brace_part(level):
    """Black V brace from the shock-tower tops to the firewall centre (separate, glued last)."""
    w = 30.0
    pts_l = [(1020.0, -440.0), (1585.0, 0.0)]
    pts_r = [(1020.0, 440.0), (1585.0, 0.0)]
    outline_l = line_band(pts_l[0], pts_l[1], w)
    outline_r = line_band(pts_r[0], pts_r[1], w)
    top = (level + BRACE_T) * SCALE
    brace = F.prism_cutter("Brace", "+Z", outline_l, level * SCALE, top)
    other = F.prism_cutter("Brace_Right", "+Z", outline_r, level * SCALE, top)
    feet = [F.prism_cutter(f"Brace_Foot{k}", "+Z", F.circle(x, y, 34.0, 24), level * SCALE, top)
            for k, (x, y) in enumerate([(1020.0, -440.0), (1020.0, 440.0), (1585.0, 0.0)])]
    return brace, [other] + feet


# ---------------------------------------------------------------- detail helpers

def _hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def belt(name, pulleys, x0, x1, thick=12.0):
    """Drive belt (y-z plane) wrapped around [(y, z, r), ...] pulleys, extruded x0..x1 (real mm)."""
    def ring(extra):
        return _hull([(y + (r + extra) * math.cos(a), z + (r + extra) * math.sin(a))
                      for y, z, r in pulleys for a in (2 * math.pi * k / 48 for k in range(48))])
    outer = F.prism_cutter(name, "+X", ring(thick), x0 * SCALE, x1 * SCALE)
    inner = F.prism_cutter(f"{name}_Inner", "+X", ring(-3.0), (x0 - 5) * SCALE, (x1 + 5) * SCALE)   # bites into the pulleys
    return outer, inner


def pleated_outline(outline, depth, pitch):
    """Outline with alternating in/out notches every `pitch` (real mm): a pleated filter band."""
    pts = F.resample(outline, pitch)
    n = len(pts)
    out = []
    for i, p in enumerate(pts):
        a, b = Vector(pts[i - 1]), Vector(pts[(i + 1) % n])
        t = (b - a).normalized()
        normal = Vector((t.y, -t.x))
        out.append(tuple(Vector(p) + normal * (depth if i % 2 else -depth)))
    return out


# ---------------------------------------------------------------- engine

DIST = (718.0, 0.0)                      # Ford small-block: distributor at the front of the engine
PLUG_X = {-1: (800.0, 910.0, 1020.0, 1130.0), 1: (780.0, 890.0, 1000.0, 1110.0)}   # front to rear
WIRE_R, WIRE_GAP = 5.0, 0.8              # plug wires, side by side in a loose loom under each valve cover
BOOT_R, BOOT_OUT = 9.0, 28.0             # the distributor cap's right-angle boots: radius, reach out from the tower
LOOM_X0, LOOM_Y0, LOOM_Z = 708.0, 330.0, 696.0   # the loom: start (ahead of the valve cover), innermost wire (|y|), height
WIRE_SAG = (5.0, 8.0, 4.0, 7.0)          # each wire droops its own amount between the separators
WIRE_SEPARATORS = (790.0, 905.0)        # each holds the wires still running back past it
THERMOSTAT = (722.0, 780.0, 150.0)      # thermostat elbow on the intake's water crossover, passenger side (x0, x1, y)
CROSSOVER_X = 790.0                      # water crossover along the intake's front
COIL = (660.0, -195.0)                   # ignition coil, strapped to the driver-side head ahead of the block (x, y)
HOSE_R, CLAMP_R, CLAMP_W, CLAMP_IN = 24.0, 27.0, 13.0, 12.0   # upper hose; worm clamps 12 mm in from its ends
AC_OVAL = (790.0, -155.0, 1270.0, 155.0)  # air cleaner footprint (x0, y0, x1, y1)
AC_LINES = (6.0, 18.0, 30.0, 42.0, 54.0)  # |y| of the lid's fine raised lines
AC_BOSS_R = 30.0                         # ring boss round the centre nut
AC_TEXT = (895.0, 140.0)                 # COBRA on the lid: centre x, length
COBRA_FONT = "/System/Library/Fonts/Supplemental/SuperClarendon.ttc"   # wide, heavy slab serif


def oval(x0, y0, x1, y1, inset=0.0, steps=24):
    """Stadium in plan (straight sides, semicircular ends) filling x0..x1, y0..y1, inset by `inset`;
    always 2 * (steps + 1) points, so insets of it loft together."""
    h = (y1 - y0) / 2
    r, yc = h - inset, (y0 + y1) / 2
    pts = []
    for cx, a0 in ((x1 - h, -math.pi / 2), (x0 + h, math.pi / 2)):
        pts += [(cx + r * math.cos(a0 + math.pi * k / steps), yc + r * math.sin(a0 + math.pi * k / steps)) for k in range(steps + 1)]
    return pts


def _along(path, dist):
    """Point and unit tangent `dist` (real mm) along a polyline from its start."""
    pts = [Vector(p) for p in path]
    for a, b in zip(pts[:-1], pts[1:]):
        seg = (b - a).length
        if dist <= seg:
            return a.lerp(b, dist / seg), (b - a).normalized()
        dist -= seg
    return pts[-1], (pts[-1] - pts[-2]).normalized()


def _clamp(name, c, t, r=CLAMP_R):
    """Worm-drive hose clamp of radius r round a hose at c (axis t): the band and its screw housing on top."""
    up = (Vector((0, 0, 1)) - t * t.z).normalized()
    band = _cylinder(name, c - t * CLAMP_W / 2, c + t * CLAMP_W / 2, r, 24)
    house = _cylinder(f"{name}_Screw", c + up * (r - 2) - t * 6, c + up * (r - 2) + t * 6, 6.5, 10)
    return [band, house]


def _cover_geometry(tree, s):
    """Valve cover cross-section for bank s: (a, b, top_a, top_b, d, n, f, m) in (y, z) real mm: the
    base edge a (outer) -> b (inner) on the head, the top face top_a -> top_b, d along the base, n up
    from it, f up the outer side face and m outward from that face."""
    a, b = Vector((s * 300.0, 690.0)), Vector((s * 240.0, 750.0))
    d = (b - a).normalized()
    n = Vector((-d.y, d.x)) if s > 0 else Vector((d.y, -d.x))
    if n.y < 0:
        n = -n
    a, b = a + n * 2.4, b + n * 2.4                            # 0.1 mm off the head deck (glue gap)
    limit = headroom(tree, 720, 1320, min(s * 230, s * 360), max(s * 230, s * 360))
    tall = max(35.0, min(70.0, (limit - b.y) / n.y - 8.0 - 20.0))     # room for lettering and caps
    top_a, top_b = a + n * tall - d * 8, b + n * tall + d * 8
    f = (top_a - a).normalized()
    m = Vector((f.y, -f.x)) if Vector((f.y, -f.x)).dot(d) < 0 else Vector((-f.y, f.x))
    return a, b, top_a, top_b, d, n, f, m


def engine_parts(tree):
    """(block, union pieces, hollowed [(piece, cutter)], valve covers [(part, unions)],
    air cleaner (part, unions)). Factory 289 layout: alternator and upper hose on the
    passenger side, coil, fuel pump, oil filter and the distributor's vacuum advance on the driver's."""
    # V8 block with heads: front-to-back extrusion of the V profile
    v_profile = [(-200, 420), (200, 420), (200, 560), (300, 690), (240, 750), (95, 690), (-95, 690),
                 (-240, 750), (-300, 690), (-200, 560)]
    block = F.prism_cutter("EngineBlock", "+X", [(y, z) for y, z in v_profile], 690 * SCALE, 1350 * SCALE)
    hollowed = []
    # cast aluminium intake: a low valley floor whose flanges run up the heads' inner faces (no bare
    # block shows between it and the valve covers), a plenum under the carburettor, a water
    # crossover along its front carrying the thermostat elbow, and an arched runner to each port
    # (kept under the air cleaner's rim where they pass beneath it)
    intake = F.rounded_poly([(236, 742), (236, 756), (190, 740), (150, 726), (-150, 726), (-190, 740), (-236, 756), (-236, 742),
                             (-95, 683), (95, 683)], [0, 4, 15, 15, 15, 15, 4, 0, 0, 0])
    bell = [(rect(-150, 445, 150, 600, 40), 1345.0), (rect(-170, 430, 170, 610, 60), 1584.0)]
    pieces = [
        _box("Engine_OilPan", 760, 1300, -165, 165, 400, 430, 30),
        F.prism_cutter("Engine_Intake", "+X", intake, 735 * SCALE, 1340 * SCALE),
        _box("Engine_IntakePlenum", 900, 1160, -105, 105, 720, 758, 30),
        _box("Engine_IntakePad", 940, 1120, -112, 112, 755, 767, 25),
        _box("Engine_Carb", 978, 1082, -92, 92, 760, 772, 10),
        tube("Engine_IntakeCrossover", [(CROSSOVER_X, -150.0, 738.0), (CROSSOVER_X, 175.0, 740.0)], 15, 16),   # sits on the valley floor
        F.loft_solid("Engine_Bellhousing", "+X", [(o, x * SCALE) for o, x in bell]),
        _box("Engine_FuelPump", 700, 760, -250, -195, 440, 520, 10),
        _cylinder("Engine_OilFilter", (950, -195, 480), (950, -300, 435), 45),
    ]
    for s in (-1, 1):
        for x in PLUG_X[s]:
            arch = [(x + 50, s * 95, 730), (x + 50, s * 150, 748), (x + 50, s * 185, 756), (x + 50, s * 226, 744)]
            pieces.append(tube(f"Engine_IntakeRunner{s}{int(x)}", F.chaikin(arch, 2), 18, 16))
        y0, y1 = sorted((s * 195.0, s * 270.0))
        pieces.append(_box(f"Engine_Mount{s}", 920, 990, y0, y1, FLOOR_Z1, 470, 0))
    # front of the engine: shaped timing cover, water pump with its arms and the lower hose's inlet
    timing = F.rounded_poly([(-125, 450), (125, 450), (130, 540), (108, 615), (65, 650), (-65, 650), (-108, 615), (-130, 540)], 22)
    pieces += [F.prism_cutter("Engine_Timing", "+X", timing, 640 * SCALE, 694 * SCALE),
               _cylinder("Engine_WaterPump", (624, 0, FAN_Z), (650, 0, FAN_Z), 50, 32),
               F.prism_cutter("Engine_WaterPumpArms", "+X", line_band((-112, 598), (112, 598), 44), 628 * SCALE, 650 * SCALE),
               _cylinder("Engine_PumpInlet", (640, -40, 578), (640, -128, 543), 21),
               _cylinder("Engine_CrankPulley", (612, 0, 470), (642, 0, 470), 75, 40),
               _cylinder("Engine_PumpPulley", (612, 0, FAN_Z), (642, 0, FAN_Z), 55, 32),
               _cylinder("Engine_FanHub", (596, 0, FAN_Z), (614, 0, FAN_Z), 40, 24)]
    # alternator (passenger side): satin aluminium with cooling slots round its front housing
    alt = _cylinder("Engine_Alternator", (640, 240, 560), (735, 240, 560), 62, 40)
    pieces += [alt, _cylinder("Engine_AltPulley", (615, 240, 560), (642, 240, 560), 32, 24),
               _box("Engine_AltBracket", 650, 700, 120, 240, 530, 590, 0)]
    for k in range(10):
        a = 2 * math.pi * (k + 0.5) / 10
        c, sn = math.cos(a), math.sin(a)
        slot = line_band((240 + 36 * c, 560 + 36 * sn), (240 + 55 * c, 560 + 55 * sn), 8)
        hollowed.append((alt, F.prism_cutter(f"Engine_AltSlot{k}", "+X", slot, 630 * SCALE, 652 * SCALE)))
    belt_obj, belt_cut = belt("Engine_Belt", [(0.0, 470.0, 75.0), (0.0, FAN_Z, 55.0), (240.0, 560.0, 32.0)], 620.0, 636.0)
    pieces.append(belt_obj)
    hollowed.append((belt_obj, belt_cut))            # outer hull minus the pulley hull
    pieces += _ignition(tree)
    pieces += _cooling(tree)
    # steel fuel line from the pump, tucked against the front of the engine, into the carburettor
    pieces.append(tube("Engine_FuelLine", F.chaikin([(730.0, -222.0, 515.0), (742.0, -218.0, 600.0), (765.0, -185.0, 668.0),
                                                     (800.0, -112.0, 730.0), (860.0, -70.0, 750.0), (980.0, -45.0, 759.0)], 2), 9, 8))
    # tube headers (grey ceramic coated): a primary from each port, down and back into a collector
    for s in (-1, 1):
        for j, px in enumerate(PLUG_X[s]):
            xp = px + 12.0
            pts = [(xp, s * 226.0, 602.0), (xp, s * 270.0, 600.0), (xp + 10.0, s * 305.0, 576.0), (xp + 32.0, s * 318.0, 532.0),
                   (1232.0 - 6.0 * j, s * (318.0 + 2.0 * j), 492.0)]
            pieces.append(tube(f"Engine_Header{s}{j}", F.chaikin(pts, 2), 18, 14))
        pieces.append(_cylinder(f"Engine_HeaderCollector{s}", (1222.0, s * 320.0, 500.0), (1315.0, s * 318.0, 440.0), 30, 24))
    # four-blade fan in front of the water pump: pitched blades widening to rounded tips on a spider
    pieces.append(_cylinder("Engine_FanSpider", (599, 0, FAN_Z), (611, 0, FAN_Z), 60, 24))
    for k in range(4):
        pieces.append(_fan_blade(f"Engine_Fan{k}", math.pi / 4 + k * math.pi / 2))
    return block, pieces, hollowed, _valve_covers(tree), _air_cleaner(tree)


def _fan_blade(name, angle, x=605.0, pitch=math.radians(32), t=8.0):
    """One fan blade: a thin plate twisted `pitch` about its own radial axis, 40 mm wide at the hub
    widening to 75 mm, its tip rounded; turned `angle` round the fan's (x) axis."""
    bm = bmesh.new()
    sections = [(40.0, 40.0), (100.0, 62.0), (150.0, 75.0), (162.0, 66.0), (168.0, 44.0)]   # (radius, width)
    rot = Matrix.Rotation(angle, 3, 'X')
    c, s = math.cos(pitch), math.sin(pitch)
    rings = []
    for r, w in sections:
        ring = []
        for dx, dz in ((-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)):
            p = Vector((dx * c - dz * s, r, dx * s + dz * c))
            ring.append(bm.verts.new((rot @ p + Vector((x, 0.0, FAN_Z))) * SCALE))
        rings.append(ring)
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _ignition(tree):
    """Distributor (tall cap, a right-angle rubber boot on each tower pointing out toward its bank,
    polished vacuum advance reaching forward on the driver's side), the coil strapped ahead of the
    driver-side head, and the plug wires: they fall away from the boot ends into a flat bundle
    beside the cap for each bank, which drops across the front of the head (the passenger's under
    the upper hose, the driver's over the coil) and turns back along the valve cover's outer edge,
    held by two separators and drooping between them, each wire peeling off to its plug in turn."""
    pieces = []
    dx, dy = DIST
    cap_top = min(790.0, headroom(tree, dx - 70, dx + 70, -70, 70) - 50.0)
    elbow = cap_top + 14.0                                           # the boots' outward run
    cx, cy = COIL

    def boot(name, tx, ty, u):
        """Right-angle boot on a tower at (tx, ty): up out of it, then out along u."""
        return tube(name, F.chaikin([(tx, ty, cap_top - 4.0), (tx, ty, elbow - 6.0), (tx + u.x * 10.0, ty + u.y * 10.0, elbow),
                                     (tx + u.x * BOOT_OUT, ty + u.y * BOOT_OUT, elbow)], 2), BOOT_R, 16)

    to_coil = Vector((cx - dx, cy - dy)).normalized()
    coil_end = Vector((dx, dy)) + to_coil * BOOT_OUT
    pieces += [_cylinder("Engine_DistBody", (dx, dy, 640), (dx, dy, 735), 38, 24),
               _cylinder("Engine_DistCap", (dx, dy, 728), (dx, dy, 746), 54, 32),
               _cylinder("Engine_DistCapTop", (dx, dy, 744), (dx, dy, cap_top - 12), 47, 32),
               _cylinder("Engine_DistTowerC", (dx, dy, cap_top - 16), (dx, dy, cap_top + 2), 9),
               boot("Engine_BootCapC", dx, dy, to_coil),
               _cylinder("Engine_DistVacuum", (dx - 22, -16, 706), (dx - 58, -42, 706), 11),
               _cylinder("Engine_DistVacuumCan", (dx - 54, -39, 706), (dx - 74, -54, 706), 29, 32),
               _cylinder("Engine_Coil", (cx, cy, 600), (cx, cy, 740), 29, 24),
               _cylinder("Engine_CoilTower", (cx, cy, 736), (cx, cy, 756), 12, 16),
               _cylinder("Engine_BootCoil", (cx, cy, 750), (cx, cy, 774), 11, 12),
               _box("Engine_CoilBracket", cx + 20, 700, cy - 14, cy + 14, 640, 700, 0),            # strap to the head's front
               tube("Engine_WireCoil", F.chaikin([tuple(coil_end - to_coil * 8.0) + (elbow,), tuple(coil_end) + (elbow,),
                                                  (cx + 20, cy + 60, 792), (cx, cy, 788), (cx, cy, 768)], 2), WIRE_R, 16),
               tube("Engine_CoilLead", F.chaikin([(cx + 10, cy + 27, 720), (cx + 40, cy + 90, 712), (dx - 18, -30, 700)], 2), 3, 8)]
    towers = {-1: [], 1: []}
    for k in range(8):
        a = math.pi / 8 + k * math.pi / 4
        tx, ty = dx + 36 * math.cos(a), dy + 36 * math.sin(a)
        s = 1 if ty > 0 else -1
        u = Vector((math.cos(a), math.sin(a) + 1.5 * s)).normalized()          # out, and toward the tower's own bank
        pieces.append(_cylinder(f"Engine_DistTower{k}", (tx, ty, cap_top - 16), (tx, ty, cap_top), 8))
        pieces.append(boot(f"Engine_BootCap{k}", tx, ty, u))
        towers[s].append((tx, ty, u))
    pitch = 2 * WIRE_R + WIRE_GAP
    for s in (-1, 1):
        # Wire 0, for the front plug, comes from the rearmost tower: it runs on the inside of the
        # bundle's turn, so it is innermost in the loom and peels off first.
        cross_x, cross_y, cross_z = (690.0, 130.0, 726.0) if s > 0 else (692.0, 225.0, 792.0)
        for j, (px, (tx, ty, u)) in enumerate(zip(PLUG_X[s], sorted(towers[s], key=lambda t: -t[0]))):
            yj = s * (LOOM_Y0 + pitch * j)
            sag = WIRE_SAG[j]
            lane = (1.5 - j) * pitch * 0.9                         # across the bundle, rear to front
            ex, ey = tx + u.x * BOOT_OUT, ty + u.y * BOOT_OUT       # the boot's end
            pts = [(ex - u.x * 8.0, ey - u.y * 8.0, elbow), (ex, ey, elbow), (ex + u.x * 14.0, ey + u.y * 14.0, elbow - 6.0),
                   (dx + lane, s * 104.0, elbow - 24.0), (cross_x + lane, s * cross_y, cross_z + (sag - 6.0)),
                   (LOOM_X0 - 18.0, yj, LOOM_Z + 2.0), (LOOM_X0, yj, LOOM_Z + 1.0)]
            prev, x_off = LOOM_X0, px - 55.0
            if x_off > 750.0:                                       # the front plug's wire drops straight to it
                for x in [x for x in WIRE_SEPARATORS if x < x_off - 30.0] + [x_off]:
                    pts += [((prev + x) / 2, yj, LOOM_Z - sag), (x, yj, LOOM_Z)]
                    prev = x
            pts += [(px - 20.0, (yj + s * 318.0) / 2, LOOM_Z - 6.0), (px - 4.0, s * 318.0, 685.0), (px, s * 306.0, 676.0),
                    (px, s * 299.0, 671.0)]
            pieces.append(tube(f"Engine_Wire{s}{j}", F.chaikin(pts, 2), WIRE_R, 16))
            pieces.append(_cylinder(f"Engine_Boot{s}{j}", (px, s * 268.0, 648.0), (px, s * 306.0, 676.0), 13))
        for k, x in enumerate(WIRE_SEPARATORS):
            held = [j for j, px in enumerate(PLUG_X[s]) if x < px - 85.0]
            y0, y1 = sorted((s * (LOOM_Y0 + pitch * min(held) - WIRE_R - 3.0), s * (LOOM_Y0 + pitch * max(held) + WIRE_R + 3.0)))
            pieces.append(_box(f"Engine_WireSep{s}{k}", x - 7.0, x + 7.0, y0, y1, LOOM_Z - 9.0, LOOM_Z + 9.0, 3))
    return pieces


def _cooling(tree):
    """Thermostat elbow standing up off the intake's water crossover, the smooth upper hose
    leaving its neck forward and up, then dropping in an S to the radiator's passenger-side inlet,
    a chrome worm clamp at each end; the lower hose from the water pump to the driver-side outlet;
    the heater hoses to the passenger side of the firewall (one between the air cleaner and the
    valve cover, one low beside the headers and the shock tower)."""
    tx0, tx1, ty = THERMOSTAT
    inlet_z = rad_top(tree) - TANK_H / 2                          # the liner's radiator inlet height
    neck0, neck1 = Vector((tx0 + 20.0, ty, 772.0)), Vector((tx0 - 8.0, ty, 804.0))
    lid = headroom(tree, 560, 700, 120, 230) - 30.0
    route = [tuple(neck1 - (neck1 - neck0).normalized() * 8.0), (700.0, ty + 6.0, min(lid, 810.0)), (672.0, 168.0, min(lid, 802.0)),
             (648.0, 182.0, 768.0), (575.0, 204.0, inlet_z + 12.0), (505.0, UPPER_HOSE_Y, inlet_z),
             (RAD_INLET_X1 + 4.0, UPPER_HOSE_Y, inlet_z)]
    path = F.chaikin(route, 3)
    hx = (tx0 + tx1) / 2                         # the housing: a cast drum on the crossover with two bolt ears
    pieces = [_cylinder("Engine_Thermostat", (hx, ty, 738.0), (hx, ty, 780.0), 30, 32),
              _cylinder("Engine_ThermostatEar0", (hx, ty - 36.0, 738.0), (hx, ty - 36.0, 760.0), 9, 16),
              _cylinder("Engine_ThermostatEar1", (hx, ty + 36.0, 738.0), (hx, ty + 36.0, 760.0), 9, 16),
              _cylinder("Engine_ThermoNeck", neck0, neck1, 19),
              tube("Engine_HoseUpper", path, HOSE_R, 24)]
    for k, (c, t) in enumerate((_along(path, CLAMP_IN), _along(list(reversed(path)), CLAMP_IN))):
        pieces += _clamp(f"Engine_HoseClamp{k}", c, t)
    hx, hy, hz = LOWER_HOSE_END                                  # square onto the outlet neck at the end
    pieces.append(tube("Engine_HoseLower", F.chaikin([(640.0, -120.0, 546.0), (612.0, -160.0, 500.0), (575.0, -200.0, 405.0),
                                                      (540.0, -225.0, hz + 2.0), (hx + 30.0, hy, hz), (hx, hy, hz)], 2), 20, 16))
    end_x = BAY_X1 - LINER_FIT - WALL_T - HEATER_FITTING - 5.0
    (y0, z0), (y1, z1) = HEATER_CORE
    # the heater supply leaves a nipple on the intake between the first two runners, sagging a
    # little between its supports on the way back; a clamp at each end of both heater hoses
    pieces.append(_cylinder("Engine_HeaterNeck", (885.0, 190.0, 734.0), (885.0, 190.0, 792.0), 12))
    heater = [F.chaikin([(885.0, 190.0, 780.0), (885.0, 190.0, 796.0), (905.0, 200.0, 806.0), (1000.0, 210.0, 798.0),
                         (1200.0, 214.0, 786.0), (1340.0, 225.0, 786.0), (1460.0, 265.0, z1 + 4.0), (end_x - 30.0, y1, z1),
                         (end_x, y1, z1)], 2),
              F.chaikin([(660.0, 100.0, 625.0), (760.0, 200.0, 664.0), (880.0, y0, 642.0), (end_x - 30.0, y0, z0), (end_x, y0, z0)], 2)]
    for k, path in enumerate(heater):
        pieces.append(tube(f"Engine_HoseHeater{k}", path, 18, 20))
        for e, (c, t) in enumerate((_along(path, CLAMP_IN), _along(list(reversed(path)), CLAMP_IN))):
            pieces += _clamp(f"Engine_HoseClamp{k + 2}{e}", c, t, 21.0)
    return pieces


def _valve_covers(tree):
    """Black valve covers, [(part, unions)]: rounded ends, fine polished fins along the whole top
    round a raised strip in the middle carrying COBRA over POWERED BY FORD, a few fins along the
    outer side; the oil filler cap with a blue Ford oval at the passenger cover's rear end, a
    breather at the driver cover's front."""
    covers = []
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        a, b, top_a, top_b, d, n, f, m = _cover_geometry(tree, s)
        prof = [a, b, top_b, top_a]
        base = (a + b) / 2                       # ends shrink toward the base's middle, so they stay on the deck

        def section(k):
            return [tuple(base + (p - base) * k) for p in prof]
        ends = [(0.0, 0.8), (5.0, 0.9), (13.0, 0.965), (25.0, 1.0)]      # (mm from the end, scale): rounded ends
        sections = [(section(k), (720.0 + e) * SCALE) for e, k in ends]
        sections += [(section(k), (1320.0 - e) * SCALE) for e, k in reversed(ends)]
        cover = F.loft_solid(f"ValveCover_{tag}", "+X", sections)
        unions = []
        mid = (top_a + top_b) / 2
        across = (top_b - top_a).normalized()                     # across the top face, outer -> inner
        half = (top_b - top_a).length / 2
        n3, d3 = Vector((0, n.x, n.y)), Vector((0, across.x, across.y))
        x_dir = (-1.0, 0.0, 0.0) if s > 0 else (1.0, 0.0, 0.0)        # reads from that side of the car
        # fins along the whole cover either side of the lettering strip, and before and after it
        panel_x0, panel_x1 = 905.0, 1215.0
        ph = 0.55 * half                                              # the strip's half width
        k = 0
        off = -half + 6.0
        while off <= half - 6.0:
            c = mid + across * off
            fin = [tuple(c - across * 1.4 - n * 1.0), tuple(c + across * 1.4 - n * 1.0),
                   tuple(c + across * 1.4 + n * 5.0), tuple(c - across * 1.4 + n * 5.0)]
            runs = ((745.0, 1295.0),) if abs(off) > ph + 2.0 else ((745.0, panel_x0), (panel_x1, 1295.0))
            for x0, x1 in runs:
                unions.append(F.prism_cutter(f"Letters_VCRib{tag}{k}", "+X", fin, x0 * SCALE, x1 * SCALE))
                k += 1
            off += 6.0
        panel = [tuple(mid - across * ph - n * 1.0), tuple(mid + across * ph - n * 1.0),
                 tuple(mid + across * (ph - 2.0) + n * 3.0), tuple(mid - across * (ph - 2.0) + n * 3.0)]
        unions.append(F.prism_cutter(f"ValveCover_{tag}_Panel", "+X", panel, panel_x0 * SCALE, panel_x1 * SCALE))
        for t in (38.0, 50.0, 62.0):                                  # side fins, high above the plug wires
            c = a + f * t
            fin = [tuple(c - f * 1.6 - m * 1.0), tuple(c + f * 1.6 - m * 1.0), tuple(c + f * 1.6 + m * 4.0), tuple(c - f * 1.6 + m * 4.0)]
            unions.append(F.prism_cutter(f"Letters_VCSide{tag}{int(t)}", "+X", fin, 745 * SCALE, 1295 * SCALE))
        top = mid + n * 3.0
        xc = (panel_x0 + panel_x1) / 2
        for name, text, cap, off, w in (("COBRA", "COBRA", 30.0, 8.0, 250.0), ("Powered", "POWERED BY FORD", 9.0, -22.0, 200.0)):
            o = top + across * off
            unions.append(text_solid(f"Letters_VC{name}{tag}", text, cap, 0.25, (xc, o.x, o.y), x_dir, d3, font=COBRA_FONT,
                                     width=w, bold=0.015, center=True))
        if s > 0:                                                     # oil filler cap at the rear end
            cbase = Vector((1258.0, mid.x, mid.y))
            unions += [_cylinder(f"ValveCover_{tag}_Cap", cbase - n3 * 5, cbase + n3 * 18, 30, 32),
                       _cylinder(f"ValveCover_{tag}_CapTop", cbase + n3 * 16, cbase + n3 * 25, 22, 32),
                       _cylinder(f"ValveCover_{tag}_Logo", cbase + n3 * 24, cbase + n3 * 27, 14, 24)]
        else:                                                         # breather at the front
            cbase = Vector((785.0, mid.x, mid.y))
            unions += [_cylinder(f"ValveCover_{tag}_Breather", cbase - n3 * 5, cbase + n3 * 20, 26, 24),
                       _cylinder(f"ValveCover_{tag}_BreatherTop", cbase + n3 * 18, cbase + n3 * 24, 18, 24)]
        covers.append((cover, unions))
    return covers


def _gaps(x0, x1, holes):
    """The parts of x0..x1 outside the (a, b) intervals in `holes`."""
    out, cur = [], x0
    for a, b in sorted(holes):
        if b <= cur or a >= x1:
            continue
        if a > cur:
            out.append((cur, a))
        cur = max(cur, b)
    if cur < x1:
        out.append((cur, x1))
    return out


def _air_cleaner(tree):
    """Oval air cleaner (black), (part, unions): base pan, a bronze mesh filter band showing under
    the lid, the lid with a rounded edge and a polished bead round its flat top, a band of fine
    raised lines down the middle broken by the ring boss round the centre nut and by COBRA on the
    front third (read from the passenger side, as in the photos)."""
    x0, y0, x1, y1 = AC_OVAL
    ac_top = headroom(tree, x0, x1, y0, y1)
    lid_top = ac_top - 8.0
    xc, h = (x0 + x1) / 2, (y1 - y0) / 2
    cleaner = F.prism_cutter("AirCleaner", "+Z", oval(x0, y0, x1, y1), 772 * SCALE, 788 * SCALE)
    unions = [F.prism_cutter("AirCleaner_Filter", "+Z", pleated_outline(oval(x0, y0, x1, y1, 2.0), 0.9, 4.0), 784 * SCALE, 818 * SCALE),
              F.loft_solid("AirCleaner_Lid", "+Z", [(oval(x0, y0, x1, y1), 814 * SCALE), (oval(x0, y0, x1, y1), 822 * SCALE),
                                                    (oval(x0, y0, x1, y1, 5.0), (lid_top - 6) * SCALE),
                                                    (oval(x0, y0, x1, y1, 14.0), lid_top * SCALE)]),
              tube("Letters_ACRim", [(x, y, lid_top - 1.0) for x, y in oval(x0, y0, x1, y1, 16.0)], 3.0, 8, closed=True),
              _cylinder("AirCleaner_Boss", (xc, 0.0, lid_top - 2), (xc, 0.0, lid_top + 4), AC_BOSS_R, 32),
              _cylinder("AirCleaner_Nut", (xc, 0.0, lid_top + 3), (xc, 0.0, ac_top), 12, 6)]
    tx, tw = AC_TEXT
    r_in = h - 22.0                                                   # the lines stay on the flat top
    for y in AC_LINES:
        reach = math.sqrt(r_in ** 2 - y ** 2)
        holes = [(xc - math.sqrt((AC_BOSS_R + 34.0) ** 2 - y ** 2), xc + math.sqrt((AC_BOSS_R + 34.0) ** 2 - y ** 2))]
        if y < 24.0:
            holes.append((tx - tw / 2 - 10.0, tx + tw / 2 + 10.0))
        for k, (u0, u1) in enumerate(_gaps(x0 + h - reach, x1 - h + reach, holes)):
            for sy in (-1, 1):
                unions.append(F.prism_cutter(f"Letters_ACRib{int(sy * y)}_{k}", "+Z", rect(u0, sy * y - 2.5, u1, sy * y + 2.5, 2.4),
                                             (lid_top - 2) * SCALE, (lid_top + 2.5) * SCALE))
    unions.append(text_solid("Letters_AC", "COBRA", 38.0, 6.0 * SCALE, (tx, 0.0, lid_top), (-1, 0, 0), (0, -1, 0),
                             font=COBRA_FONT, width=tw, bold=0.015, center=True))
    return cleaner, unions


def prop_rod(P, tree):
    """Black prop rod, in its working position with the hood open HOOD_OPEN_DEG."""
    bx, by = PROP_BASE
    base = Vector((bx + 10, by, front_top(tree) - 14))
    px, py = PROP_HOOD_POINT
    cup = Vector((px, py, surface_z(tree, px, py) - (HOOD_T + RIB_DEPTH + 0.9) / SCALE))
    top = open_angle_point(P, cup, HOOD_OPEN_DEG)
    axis = top - base
    # modelled along local +X so it exports lying flat; placed in its working position
    rod = _cylinder("HoodProp", (0, 0, 0), (axis.length, 0, 0), 0.6 / SCALE, 16)
    rod.matrix_world = Matrix.Translation(base * SCALE) @ axis.to_track_quat('X', 'Z').to_matrix().to_4x4()
    return rod
