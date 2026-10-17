"""Cabin: the hollow in the body and the interior that fills it.

The cabin is open at the bottom: the black interior tub (floor, trim behind the doorways, seats,
console, dashboard) slides up into it before the chassis is glued on, and the steering wheel plugs
into the dash. The door cards ride on the opening doors (doors.py); the window openings are cut in
details.py. Dimensions are real-car millimetres unless noted; SCALE converts to print mm.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import body
import details
import features as F
from body import SCALE
from details import rect

T_WALL = 2.2 / SCALE            # greenhouse/roof wall left around the cabin (2.2 mm print)
CAB_X0, CAB_X1 = 1745.0, 3415.0  # firewall .. behind the rear seat
CABIN_HALF = 690.0              # cabin side-wall plane (the doors' inner faces stand just outside it)
REAR_HALF = 560.0               # between the rear wheelhouses
REAR_NARROW_X0, REAR_NARROW_X1 = 3040.0, 3100.0
WHEELHOUSE_Z = 780.0
Z_CUT = body.Z_BOTTOM - 60.0    # the cabin opens through the body's underside
FIT = 0.2 / SCALE               # interior-to-cabin clearance
CABIN_STATIONS = 80
RAIL_CLEAR = 20.0               # the side wall runs on this far above the side window opening's top
T_MIN = 1.5 / SCALE             # thinnest wall allowed where it does

# Left-hand drive: the driver sits on the car's left (-Y).
DRIVER_Y = -360.0
PASSENGER_Y = 360.0


# ---------------------------------------------------------------- cabin hollow

def cabin_half_widths(x):
    """(lower half width below the wheelhouse line, upper half width) at station x."""
    t = max(0.0, min(1.0, (x - REAR_NARROW_X0) / (REAR_NARROW_X1 - REAR_NARROW_X0)))
    return CABIN_HALF + (REAR_HALF - CABIN_HALF) * t, CABIN_HALF


_BODY_TREE = None


def set_body_surface(tree):
    """Measure cabin walls against the real (subdivided) body surface rather than its outline."""
    global _BODY_TREE
    _BODY_TREE = tree


def _wall_to_skin(x, q, outer):
    if _BODY_TREE is not None:
        hit = _BODY_TREE.find_nearest(Vector((x * SCALE, q.x * SCALE, q.y * SCALE)))
        return hit[3] / SCALE
    return _dist_to_polyline(q, outer[3:])


def _dist_to_polyline(p, poly):
    best = 1e18
    for a, b in zip(poly[:-1], poly[1:]):
        a, b = Vector(a), Vector(b)
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
        best = min(best, (p - (a + ab * t)).length)
    return best


def cabin_profile(x):
    """Closed cabin cross-section (y, z) at station x: vertical door-panel walls, then the
    greenhouse and roof offset inward by at least the wall thickness."""
    outer = body.section(x)
    seq = outer[6:]
    tans = []
    for i in range(len(seq)):
        a, b = Vector(seq[max(0, i - 1)]), Vector(seq[min(len(seq) - 1, i + 1)])
        tans.append((b - a).normalized())
    inner = []
    for p, tan in zip(seq, tans):
        normal = Vector((-tan.y, tan.x))                 # left of travel = into the body
        q = Vector(p) + normal * T_WALL
        for _ in range(60):                              # tight roof-edge curvature: keep pushing in
            if _wall_to_skin(x, q, outer) >= T_WALL * 0.98:
                break
            q += normal * (T_WALL * 0.05)
        inner.append(q)
    # remove crossings by moving points inward only: y may only shrink going up the side,
    # and on the roof a point may only drop below the next one toward the centre
    for i in range(1, len(inner)):
        inner[i].x = min(inner[i].x, inner[i - 1].x - 0.5)
    for i in range(len(inner) - 2, -1, -1):
        inner[i].y = min(inner[i].y, inner[i + 1].y - 0.5)
    _raise_knee(x, inner, outer)
    lower, upper = cabin_half_widths(x)
    right = [(min(q.x, upper - 1.0), q.y) for q in inner]
    right[-1] = (0.0, right[-1][1])
    right = [(lower, Z_CUT), (lower, WHEELHOUSE_Z), (upper, WHEELHOUSE_Z + 20.0)] + right
    left = [(-y, z) for y, z in reversed(right[:-1])]
    return right + left


def _raise_knee(x, inner, outer):
    """Under the roof rail, run the side wall straight on up past the side window opening's top
    before it turns into the ceiling, so the opening's level top face meets a steep wall in a clean edge
    instead of grazing the nearly level ceiling (which leaves a ragged sliver). `inner` is the
    profile from body section point 6 up; its point 6 sits under the roof edge (section point 12)."""
    h = (CAB_X1 - CAB_X0) / CABIN_STATIONS
    want = max(details.rail_over(x + d) for d in (-h, 0.0, h)) + RAIL_CLEAR
    knee = 12 - 6
    a, b = inner[knee - 1], inner[knee]
    if b.y >= want or b.y - a.y < 1.0:
        return

    def along(z):                       # on the wall segment's line, at height z
        return a + (b - a) * ((z - a.y) / (b.y - a.y))

    if _wall_to_skin(x, along(want), outer) < T_MIN:
        lo, hi = b.y, want
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _wall_to_skin(x, along(mid), outer) >= T_MIN else (lo, mid)
        want = lo
    w = along(want)
    inner[knee] = w
    for j in range(knee + 1, len(inner)):         # the ceiling starts above and inboard of it
        k = j - knee
        inner[j] = Vector((min(inner[j].x, w.x - 0.5 * k), max(inner[j].y, w.y + 0.5 * k)))


def cabin_ceiling(x, y):
    """Lowest cabin ceiling z above lateral position y at station x (for fitting the interior)."""
    prof = cabin_profile(x)
    best = 1e9
    for (y0, z0), (y1, z1) in zip(prof, prof[1:] + prof[:1]):
        if min(y0, y1) <= y <= max(y0, y1) and abs(y1 - y0) > 1e-6 and min(z0, z1) > WHEELHOUSE_Z:
            best = min(best, z0 + (z1 - z0) * (y - y0) / (y1 - y0))
    return best


def _loft(name, stations):
    """Closed solid through [(x, [(y, z), ...]), ...] cross-sections (equal point counts)."""
    bm = bmesh.new()
    rings = [[bm.verts.new((x * SCALE, y * SCALE, z * SCALE)) for (y, z) in prof] for x, prof in stations]
    n = len(rings[0])
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def cabin_cutter():
    xs = [CAB_X0 + (CAB_X1 - CAB_X0) * k / CABIN_STATIONS for k in range(CABIN_STATIONS + 1)]
    xs = sorted(set(xs + [REAR_NARROW_X0, REAR_NARROW_X1, details.OPEN_CORNER_X]))
    return _loft("Cut_Cabin", [(x, cabin_profile(x)) for x in xs])


# ---------------------------------------------------------------- interior tub

def _box(name, x0, x1, y0, y1, z0, z1, r=0.0):
    """Box (real mm), optionally with rounded vertical edges of radius r."""
    return F.prism_cutter(name, "+Z", rect(x0, y0, x1, y1, r), z0 * SCALE, z1 * SCALE)


def _side_profile(name, profile_xz, y0, y1):
    """Profile in the side view (x, z real mm) extruded across y0..y1 (real mm)."""
    return F.prism_cutter(name, "+Y", profile_xz, y0 * SCALE, y1 * SCALE)


def _cylinder(name, p0, p1, r, segments=20, r2=None):
    """Cylinder or tapered cone between two points (real mm)."""
    a, b = Vector(p0) * SCALE, Vector(p1) * SCALE
    d = b - a
    r_end = r if r2 is None else r2
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r * SCALE, radius2=r_end * SCALE, depth=d.length)
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((a + b) / 2) @ rot, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _sphere(name, c, r, twist=0.0):
    """UV sphere (real mm); `twist` (degrees) turns its meridians about Z, e.g. off the vertex planes of
    a cylinder it is unioned with (edge-on-edge contact leaves the boolean two touching sheets)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r * SCALE)
    if twist:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(twist), 3, 'Z'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(c) * SCALE)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


FLOOR_Z0, FLOOR_Z1 = body.Z_BOTTOM, body.Z_BOTTOM + 40.0
PANEL_T = 30.0                       # side trim panel thickness (rear doorway, quarters)
PANEL_TOP, REAR_PANEL_TOP = 885.0, 760.0
DASH_X0, DASH_TOP = CAB_X0 + 20.0, 905.0
DASH_FACE_X = 1975.0                 # the dash's rear face (its top edge leans forward to 1925)
COLUMN_BASE = (1965.0, DRIVER_Y, 735.0)          # where the column leaves the dash face
WHEEL_CENTRE = (2160.0, DRIVER_Y, 845.0)
COLUMN_R, WHEEL_R = 30.0, 195.0
SEAT_W, SEAT_X0, SEAT_X1, SEAT_TOP = 470.0, 2190.0, 2660.0, 600.0
SEAT_SLAB, SEAT_INSET = 130.0, 50.0  # cushion thickness; its riser is set in this much at the front and sides
BACK_PROFILE = [(2580.0, 560.0), (2675.0, 560.0), (2840.0, 995.0), (2810.0, 1020.0), (2745.0, 1020.0)]   # ~20 deg recline
DASH_HOODS = (355.0, 250.0)          # twin cowls over the dash: centre |y|, half width
REAR_SEAT = (3080.0, 3295.0, 535.0, 560.0)        # x0, x1, half width, cushion top
REAR_BACK_PROFILE = [(3235.0, 520.0), (3310.0, 520.0), (3325.0, 865.0), (3280.0, 870.0)]


def ceiling_edge(x0, x1, y, z_max, samples=10, gap=15.0):
    """[(x, z)] top edge for an interior part at lateral y: z_max, lowered to stay `gap` under the
    cabin ceiling where the greenhouse curves in (around the windshield base)."""
    pts = []
    for k in range(samples + 1):
        x = x0 + (x1 - x0) * k / samples
        pts.append((x, min(z_max, cabin_ceiling(x, y) - gap)))
    return pts


def _dash_brow_loft(dash_half):
    """Continuous sculpted 1967 twin-cowl upper dashboard pad lofted smoothly across Y."""
    hy, hw = DASH_HOODS
    y_max = dash_half - 10.0
    # Uniform dense stations across Y so the twin binnacle arches and center valley loft without sharp creases
    pos_ys = [0.0, 30.0, 60.0, 90.0, 120.0, 155.0, 195.0, 240.0, 295.0, 355.0,
              415.0, 470.0, 515.0, 555.0, 590.0, 620.0, y_max]
    ys = sorted({-y for y in pos_ys} | set(pos_ys))
    sections = []
    for y in ys:
        ay = abs(y)
        u = min(1.0, abs(ay - hy) / hw)
        cowl = 0.5 * (1.0 + math.cos(math.pi * u))
        cowl *= max(0.0, min(1.0, (y_max - ay) / 42.0))
        ceil_z = min(cabin_ceiling(x, y) for x in (1935.0, 1965.0, 1995.0, 2025.0)) - 15.0
        pt_val = min(886.0, ceil_z - 10.0)
        pt_peak = min(DASH_TOP + 24.0, ceil_z)
        pt = pt_val + (pt_peak - pt_val) * cowl
        lx = 1990.0 + 34.0 * cowl
        uz = 838.0 + 24.0 * cowl
        lz = max(uz + 6.0, pt - 26.0)
        pts = [
            (1918.0, min(862.0, ceil_z - 14.0)),
            (1955.0, min(pt - 3.0, ceil_z - 4.0)),
            (1994.0, pt),
            (lx - 5.0, pt - 5.0),
            (lx, lz),
            (1968.0, uz),
            (1918.0, 750.0),
        ]
        prof = F.rounded_poly(pts, [0.0, 18.0, 20.0, 9.0, 8.0, 14.0, 0.0], steps=6)
        sections.append((prof, y * SCALE))
    return F.loft_solid("Tub_DashBrow", "+Y", sections)


def _waterfall_console_parts(pieces, cuts):
    """Full-length 1967 Mustang waterfall center console, radio/tambour fascia, and curved T-handle shifter."""
    # Main console body sweeping continuously from under the dash (Z=758) down to the floor tunnel (Z=522..538)
    base_pts = [
        (1860.0, FLOOR_Z0),
        (2770.0, FLOOR_Z0),
        (2770.0, 512.0),
        (2752.0, 538.0),
        (2550.0, 538.0),
        (2532.0, 522.0),
        (2145.0, 522.0),
        (2095.0, 544.0),
        (2058.0, 608.0),
        (2028.0, 680.0),
        (2004.0, 750.0),
        (1945.0, 758.0),
        (1860.0, 758.0),
    ]
    radii = [0.0, 0.0, 12.0, 16.0, 12.0, 12.0, 28.0, 36.0, 30.0, 22.0, 14.0, 0.0, 0.0]
    prof_mid = F.rounded_poly(base_pts, radii, steps=6)
    bevel_pts = [
        (x - (5.0 if x > 1950.0 else 0.0), z - (5.0 if z > FLOOR_Z0 + 10.0 else 0.0))
        for (x, z) in base_pts
    ]
    prof_edge = F.rounded_poly(bevel_pts, radii, steps=6)
    console_half = 102.0
    pieces.append(F.loft_solid("Tub_Console", "+Y", [
        (prof_edge, -console_half * SCALE),
        (prof_mid, -(console_half - 8.0) * SCALE),
        (prof_mid, (console_half - 8.0) * SCALE),
        (prof_edge, console_half * SCALE),
    ]))

    # Twin chrome waterfall perimeter side rails following the console sweep from dash to rear compartment
    rail_pts = [
        (1945.0, 738.0),
        (2004.0, 738.0),
        (2090.0, 510.0),
        (2756.0, 510.0),
        (2756.0, 526.0),
        (2142.0, 526.0),
        (2098.0, 547.0),
        (2061.0, 610.0),
        (2031.0, 682.0),
        (2007.0, 752.0),
        (1945.0, 757.0),
    ]
    rail_prof = F.rounded_poly(rail_pts, [0.0, 10.0, 24.0, 6.0, 6.0, 28.0, 34.0, 28.0, 20.0, 10.0, 0.0], steps=6)
    for tag, (y0, y1) in (("L", (-98.0, -86.0)), ("R", (86.0, 98.0))):
        pieces.append(_side_profile(f"Tub_ConsoleTrimRail{tag}", rail_prof, y0, y1))

    # Brushed-aluminum waterfall fascia & horizontal shifter deck plate between the chrome side rails
    deck_pts = [
        (1955.0, 734.0),
        (2000.0, 734.0),
        (2088.0, 512.0),
        (2446.0, 512.0),
        (2446.0, 524.5),
        (2143.0, 524.5),
        (2096.0, 545.5),
        (2059.5, 608.5),
        (2029.5, 680.5),
        (2005.5, 748.5),
        (1955.0, 752.0),
    ]
    deck_prof = F.rounded_poly(deck_pts, [0.0, 8.0, 22.0, 4.0, 4.0, 28.0, 34.0, 28.0, 18.0, 8.0, 0.0], steps=6)
    pieces.append(_side_profile("Tub_ConsoleDeckMain", deck_prof, -87.0, 87.0))

    # Flush-angled chrome cross-moldings framing the radio bezel, tambour compartment door, and shifter deck
    def _waterfall_x(z):
        if z >= 680.0:
            return 2029.5 - (z - 680.0) / (748.5 - 680.0) * (2029.5 - 2005.5)
        if z >= 608.0:
            return 2059.5 - (z - 608.0) / (680.0 - 608.0) * (2059.5 - 2029.5)
        return 2096.0 - (z - 545.5) / (608.0 - 545.5) * (2096.0 - 2059.5)

    for tag, z0, z1, out_x in (("RadioTop", 741.0, 749.0, 2.5), ("RadioBot", 674.0, 682.0, 2.5), ("TambourBot", 541.0, 549.0, 2.2)):
        xa, xb = _waterfall_x(z0), _waterfall_x(z1)
        bar_prof = F.rounded_poly([
            (xa - 12.0, z0), (xa + out_x, z0), (xb + out_x, z1), (xb - 12.0, z1)
        ], [0.0, 2.0, 2.0, 0.0], steps=3)
        pieces.append(_side_profile(f"Tub_ConsoleTrim{tag}", bar_prof, -88.0, 88.0))
    pieces.append(_box("Tub_ConsoleTrimShiftRear", 2438.0, 2450.0, -88.0, 88.0, 518.0, 527.0, 3.0))

    # Upper radio dial bar & two round chrome tuning/volume knobs (angled normal to waterfall slope)
    n_radio = Vector((0.94, 0.0, 0.34)).normalized()
    for tag, ky in (("L", -62.0), ("R", 62.0)):
        z_k = 712.0
        c = Vector((_waterfall_x(z_k), ky, z_k))
        pieces.append(_cylinder(f"Tub_ConsoleTrimKnob{tag}", c - n_radio * 10.0, c + n_radio * 7.5, 11.5, 24, r2=9.5))
    z_d0, z_d1 = 706.0, 718.0
    xd0, xd1 = _waterfall_x(z_d0), _waterfall_x(z_d1)
    dial_prof = F.rounded_poly([
        (xd0 - 10.0, z_d0), (xd0 + 3.2, z_d0), (xd1 + 3.2, z_d1), (xd1 - 10.0, z_d1)
    ], [0.0, 2.0, 2.0, 0.0], steps=3)
    pieces.append(_side_profile("Tub_ConsoleTrimDial", dial_prof, -38.0, 38.0))

    # Subtle flush-contoured tambour door horizontal ribs along the curved waterfall face
    for k in range(7):
        t = (k + 0.5) / 7.0
        zc = 665.0 - t * 110.0
        z_lo, z_hi = zc - 3.2, zc + 3.2
        x_lo, x_hi = _waterfall_x(z_lo), _waterfall_x(z_hi)
        rib_prof = F.rounded_poly([
            (x_lo - 8.0, z_lo), (x_lo + 1.8, z_lo), (x_hi + 1.8, z_hi), (x_hi - 8.0, z_hi)
        ], [0.0, 1.4, 1.4, 0.0], steps=3)
        pieces.append(_side_profile(f"Tub_ConsoleTrimRib{k}", rib_prof, -85.0, 85.0))

    # Automatic selector housing bezel, PRND21 indicator strip, and recessed selector gate slot
    pieces.append(_box("Tub_ConsoleTrimGate", 2165.0, 2325.0, -48.0, 48.0, 518.0, 530.0, 14.0))
    pieces.append(_box("Tub_ConsoleDeckPRND", 2180.0, 2310.0, -38.0, -18.0, 524.0, 532.5, 4.0))
    cuts.append(_box("Tub_ShiftSlot", 2182.0, 2305.0, -10.0, 12.0, 514.0, 538.0, 4.0))

    # Twin seatbelt buckle holsters behind the shifter deck + rear compartment chrome latch button
    for k, by in enumerate((-52.0, 52.0)):
        pieces.append(_box(f"Tub_ConsoleTrimBuckle{k}", 2458.0, 2526.0, by - 24.0, by + 24.0, 518.0, 527.5, 8.0))
        cuts.append(_box(f"Tub_BucklePocket{k}", 2466.0, 2518.0, by - 16.0, by + 16.0, 514.0, 532.0, 5.0))
    pieces.append(_box("Tub_ConsoleTrimLatch", 2545.0, 2568.0, -18.0, 18.0, 530.0, 541.5, 4.0))

    # Iconic 1967 Ford Cruise-O-Matic forward-swept chrome T-handle shifter
    pieces.append(_cylinder("Tub_ShifterCollar", (2238.0, 0.0, 508.0), (2228.0, 0.0, 536.0), 14.5, 24, r2=11.0))
    stalk_pts = [(2238.0, 0.0, 508.0), (2225.0, 0.0, 548.0), (2206.0, 0.0, 588.0), (2186.0, 0.0, 624.0)]
    pieces.append(F.tube("Tub_Shifter", stalk_pts, [12.0, 10.0, 9.2, 10.8], 24))
    # Horizontal T-bar sweeps subtly upward from the stalk so every point on its underside drains into the stalk
    t_bar_pts = [
        (2184.0, -46.0, 626.0),
        (2185.0, -18.0, 622.5),
        (2186.0, 0.0, 620.0),
        (2185.0, 18.0, 622.5),
        (2184.0, 46.0, 626.0),
    ]
    pieces.append(F.tube("Tub_ShifterKnob", t_bar_pts, [11.0, 12.8, 14.2, 12.8, 11.0], 24))


def tub_parts():
    """(tub object, union pieces, cut pieces) for the black interior."""
    i = FIT
    xr = REAR_NARROW_X0
    # floor: wide up front, narrow between the rear wheelhouses
    floor_outline = [(CAB_X0 + i, -(CABIN_HALF - i)), (xr, -(CABIN_HALF - i)), (REAR_NARROW_X1, -(REAR_HALF - i)),
                     (CAB_X1 - i, -(REAR_HALF - i)), (CAB_X1 - i, REAR_HALF - i), (REAR_NARROW_X1, REAR_HALF - i),
                     (xr, CABIN_HALF - i), (CAB_X0 + i, CABIN_HALF - i)]
    tub = F.prism_cutter("InteriorTub", "+Z", floor_outline, FLOOR_Z0 * SCALE, FLOOR_Z1 * SCALE)
    pieces, cuts = [], []
    # trim panels behind the doorway (the door cards themselves ride on the opening doors) and the
    # rear quarter trim (up to the wheelhouse top)
    import doors
    for s in (-1, 1):
        y_out = s * (CABIN_HALF - i)
        y_in = s * (CABIN_HALF - i - PANEL_T)
        x_front = lambda z: doors._edge_x(details.DOOR_REAR, z) + doors.GAP
        # up to the window sill where the beltline is cleared, under the ceiling behind the quarter glass
        x0 = x_front(900.0)
        top = [(x, details.greenhouse_band(x)[0] - doors.CARD_TOP_GAP - 6.0) for x in
               [x0 + (details.QUARTER_X1 - 20.0 - x0) * k / 6 for k in range(7)]]
        top += ceiling_edge(details.QUARTER_X1 + 10.0, xr, CABIN_HALF - i, PANEL_TOP, samples=3)
        panel = [(x_front(FLOOR_Z0), FLOOR_Z0), (xr, FLOOR_Z0)] + list(reversed(top))
        pieces.append(_side_profile(f"Tub_DoorRear{s}", panel, min(y_out, y_in), max(y_out, y_in)))
        y_out = s * (REAR_HALF - i)
        y_in = s * (REAR_HALF - i - PANEL_T)
        pieces.append(_box(f"Tub_Quarter{s}", REAR_NARROW_X1, CAB_X1 - i, min(y_out, y_in), max(y_out, y_in), FLOOR_Z0, REAR_PANEL_TOP))

    # firewall + smoothed dashboard profile + continuous twin-cowl upper brow
    dash_half = CABIN_HALF - i - PANEL_T + 5
    dash_top = ceiling_edge(DASH_X0, 1925, dash_half, DASH_TOP, samples=6)
    dash_pts = [(DASH_X0, FLOOR_Z0), (DASH_X0 + 90, FLOOR_Z0), (DASH_X0 + 90, 470),
                (DASH_FACE_X, 620), (DASH_FACE_X, 760)] + list(reversed(dash_top))
    dash_radii = [0.0, 0.0, 28.0, 32.0, 18.0] + [0.0] * len(dash_top)
    pieces.append(_side_profile("Tub_Dash", F.rounded_poly(dash_pts, dash_radii), -dash_half, dash_half))
    pieces.append(_dash_brow_loft(dash_half))

    # Split chrome dash moldings flanking the waterfall console + passenger glovebox bezel & Mustang emblem plaque
    pieces.append(_box("Tub_DashTrimL", DASH_FACE_X - 4.0, DASH_FACE_X + 4.0, -dash_half + 28.0, -96.0, 746.0, 756.0, 3.0))
    pieces.append(_box("Tub_DashTrimR", DASH_FACE_X - 4.0, DASH_FACE_X + 4.0, 96.0, dash_half - 28.0, 746.0, 756.0, 3.0))

    # Sloped dash-face tangent and normal (+X, +Z into the cabin)
    face_a, face_b = Vector((DASH_FACE_X, 760.0)), Vector((1925.0, DASH_TOP))
    tan = (face_b - face_a).normalized()
    normal = Vector((-tan.y, tan.x)) if -tan.y > 0 else Vector((tan.y, -tan.x))
    n3 = Vector((normal.x, 0.0, normal.y))

    # Passenger glovebox brushed-aluminum door & chrome frame set parallel to the sloped dash face
    glove_prof = F.rounded_poly([
        (face_a.x + (768.0 - face_a.y) / tan.y * tan.x - 10.0, 768.0),
        (face_a.x + (768.0 - face_a.y) / tan.y * tan.x + 4.0, 768.0),
        (face_a.x + (830.0 - face_a.y) / tan.y * tan.x + 4.0, 830.0),
        (face_a.x + (830.0 - face_a.y) / tan.y * tan.x - 10.0, 830.0),
    ], [0.0, 3.0, 3.0, 0.0], steps=3)
    pieces.append(_side_profile("Tub_ConsoleDeckGlove", glove_prof, 145.0, 565.0))
    emblem_prof = F.rounded_poly([
        (face_a.x + (788.0 - face_a.y) / tan.y * tan.x - 6.0, 788.0),
        (face_a.x + (788.0 - face_a.y) / tan.y * tan.x + 7.5, 788.0),
        (face_a.x + (810.0 - face_a.y) / tan.y * tan.x + 7.5, 810.0),
        (face_a.x + (810.0 - face_a.y) / tan.y * tan.x - 6.0, 810.0),
    ], [0.0, 2.5, 2.5, 0.0], steps=3)
    pieces.append(_side_profile("Tub_DashTrimEmblem", emblem_prof, 315.0, 395.0))

    # Authentic 1967 5-pod instrument cluster: 2 large deep-hooded main pods flanking 3 upper auxiliary pods
    depth = 0.65 / SCALE
    gauges = [
        (-130.0, 794.0, 44.0, 6.5),   # Left large speedometer pod
        (-56.0,  828.0, 21.5, 5.5),   # Upper-left auxiliary pod
        (0.0,    832.0, 21.5, 5.5),   # Upper-center auxiliary pod
        (56.0,   828.0, 21.5, 5.5),   # Upper-right auxiliary pod
        (130.0,  794.0, 44.0, 6.5),   # Right large tachometer pod
    ]
    for k, (dy, gz, r, rim_w) in enumerate(gauges):
        fx = face_a.x + (gz - face_a.y) / tan.y * tan.x
        c = Vector((fx, DRIVER_Y + dy, gz))
        pieces.append(_cylinder(f"Tub_GaugeBezel{k}", c - n3 * 6.0, c + n3 * 5.5, r + rim_w, 28, r2=r + rim_w - 1.5))
        cuts.append(_cylinder(f"Tub_Gauge{k}", c - n3 * depth, c + n3 * 40.0, r, 28))

    # steering column socket (the column belongs to the steering-wheel part)
    axis = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).normalized()
    cuts.append(_cylinder("Tub_ColumnSocket", Vector(COLUMN_BASE) - axis * 95, Vector(COLUMN_BASE) + axis * 60, COLUMN_R + 0.15 / SCALE))

    # transmission tunnel, sculpted waterfall center console, and forward-swept T-handle shifter
    pieces.append(_box("Tub_Tunnel", CAB_X0 + i, CAB_X1 - i, -168, 168, FLOOR_Z0, 515, 40))
    _waterfall_console_parts(pieces, cuts)

    # front bucket seats: smooth cushion with rounded front nose, lofted horseshoe thigh bolsters, reclined backrest,
    # lofted side bolsters, chrome side trim, and soft comfort-weave pleats
    for tag, yc in (("Driver", DRIVER_Y), ("Passenger", PASSENGER_Y)):
        y0, y1 = yc - SEAT_W / 2, yc + SEAT_W / 2
        slab_z0 = SEAT_TOP - SEAT_SLAB
        riser = rect(SEAT_X0 + SEAT_INSET, y0 + SEAT_INSET, SEAT_X1, y1 - SEAT_INSET, 28)
        slab = rect(SEAT_X0 + 18.0, y0, SEAT_X1, y1, 56)
        pieces.append(F.loft_solid(f"Tub_Seat{tag}", "+Z", [(riser, FLOOR_Z0 * SCALE), (riser, (slab_z0 - SEAT_INSET) * SCALE),
                                                            (slab, slab_z0 * SCALE), (slab, (SEAT_TOP - 8.0) * SCALE)]))
        # Smoothly rounded side-profile cushion insert wrapping around the front cushion nose
        cush_prof = F.rounded_poly([
            (SEAT_X0 + 50.0, slab_z0),
            (SEAT_X1 - 8.0, slab_z0),
            (SEAT_X1 - 8.0, SEAT_TOP),
            (SEAT_X0 + 16.0, SEAT_TOP + 2.0),
            (SEAT_X0 + 2.0, SEAT_TOP - 26.0),
            (SEAT_X0 + 18.0, slab_z0),
        ], [0.0, 0.0, 14.0, 26.0, 22.0, 0.0], steps=6)
        pieces.append(_side_profile(f"Tub_SeatInsert{tag}", cush_prof, y0 + 48.0, y1 - 48.0))
        for b_idx, (by0, by1) in enumerate(((y0 + 4.0, y0 + 76.0), (y1 - 76.0, y1 - 4.0))):
            ym = 0.5 * (by0 + by1)
            bol_sections = []
            for yy, h, x_pad in (
                (by0, 0.0, 24.0),
                (by0 + 8.0, 14.0, 10.0),
                (by0 + 20.0, 21.0, 4.0),
                (ym, 24.0, 0.0),
                (by1 - 20.0, 21.0, 4.0),
                (by1 - 8.0, 14.0, 10.0),
                (by1, 0.0, 24.0),
            ):
                b_pts = [
                    (SEAT_X0 + 26.0 + x_pad, slab_z0 + 8.0),
                    (SEAT_X1 - 10.0, slab_z0 + 8.0),
                    (SEAT_X1 - 16.0, SEAT_TOP + h - 4.0),
                    (SEAT_X0 + 18.0 + x_pad * 0.5, SEAT_TOP + h),
                    (SEAT_X0 + 4.0 + x_pad, SEAT_TOP - 24.0),
                ]
                bol_sections.append((F.rounded_poly(b_pts, [0.0, 0.0, 18.0, 26.0, 18.0], steps=6), yy * SCALE))
            pieces.append(F.loft_solid(f"Tub_SeatBolster{tag}{b_idx}", "+Y", bol_sections))
        # backrest height: stay clear of the cabin ceiling at its outer top corner
        y_corner = max(abs(y0 + 15), abs(y1 - 15))
        top = min(BACK_PROFILE[3][1], min(cabin_ceiling(x, y_corner) for x in (2745.0, 2775.0, 2810.0, 2840.0)) - 15.0)
        drop = BACK_PROFILE[3][1] - top
        back = [BACK_PROFILE[0], BACK_PROFILE[1], (BACK_PROFILE[2][0], BACK_PROFILE[2][1] - drop),
                (BACK_PROFILE[3][0], top), (BACK_PROFILE[4][0], top)]
        pieces.append(_side_profile(f"Tub_SeatBack{tag}", F.rounded_poly(back, [0.0, 0.0, 30.0, 30.0, 24.0]), y0 + 15, y1 - 15))
        a, b = Vector(back[0]), Vector(back[-1])                      # front face of the backrest
        d = (b - a).normalized()
        n = Vector((-d.y, d.x))                                       # points toward the dash (-x)
        for b_idx, (by0, by1) in enumerate(((y0 + 12.0, y0 + 74.0), (y1 - 74.0, y1 - 12.0))):
            ym = 0.5 * (by0 + by1)
            back_bol_sections = []
            for yy, out_n in (
                (by0, 4.0),
                (by0 + 9.0, 18.0),
                (by0 + 20.0, 25.0),
                (ym, 28.0),
                (by1 - 20.0, 25.0),
                (by1 - 9.0, 18.0),
                (by1, 4.0),
            ):
                bp = [
                    tuple(a + d * 12.0 - n * 18.0),
                    tuple(a + d * 12.0 + n * out_n),
                    tuple(b - d * 22.0 + n * (out_n - 2.0)),
                    tuple(b - d * 34.0 - n * 14.0),
                ]
                back_bol_sections.append((F.rounded_poly(bp, [0.0, 14.0, 18.0, 14.0], steps=5), yy * SCALE))
            pieces.append(F.loft_solid(f"Tub_BackBolster{tag}{b_idx}", "+Y", back_bol_sections))
        trim = details.line_band(tuple(a + d * 40 - n * 30), tuple(b - d * 45 - n * 30), 16.0)
        for side_y in (y0 + 15, y1 - 15):
            pieces.append(_side_profile(f"Tub_SeatTrim{tag}{int(side_y)}", trim, side_y - 3.0, side_y + 3.0))
        for k in range(4):                       # subtle comfort-weave pleats along the cushion and backrest
            yy = y0 + 78 + k * (SEAT_W - 156) / 3
            cuts.append(_box(f"Tub_Pleat{tag}{k}", SEAT_X0 + 48, SEAT_X1 - 85, yy - 3.0, yy + 3.0, SEAT_TOP - 3.5, SEAT_TOP + 20, 1.5))
            p0, p1 = a + d * 95, b - d * 68
            groove = [tuple(p0 - n * 5.0), tuple(p1 - n * 5.0), tuple(p1 + n * 30), tuple(p0 + n * 30)]
            cuts.append(_side_profile(f"Tub_BackPleat{tag}{k}", groove, yy - 3.0, yy + 3.0))
    # fold-down rear seat between the wheelhouses + carpeted fastback rear cargo shelf with chrome skid strips
    x0, x1, hw, top = REAR_SEAT
    rear_cush = F.rounded_poly([(x0, FLOOR_Z0), (x1, FLOOR_Z0), (x1, top), (x0 + 12.0, top), (x0, top - 28.0)],
                               [0.0, 0.0, 10.0, 22.0, 18.0], steps=5)
    pieces.append(_side_profile("Tub_RearSeat", rear_cush, -hw, hw))
    pieces.append(_side_profile("Tub_RearSeatBack", F.rounded_poly(REAR_BACK_PROFILE, [0.0, 0.0, 18.0, 18.0], steps=5), -hw, hw))
    pieces.append(_box("Tub_CargoShelf", 3235.0, CAB_X1 - i, -(REAR_HALF - i), REAR_HALF - i, FLOOR_Z0, 710.0, 20))
    for k, sy in enumerate((-360.0, -180.0, 0.0, 180.0, 360.0)):
        pieces.append(_box(f"Tub_SeatTrimCargo{k}", 3315.0, CAB_X1 - i - 8.0, sy - 8.0, sy + 8.0, 706.0, 716.0, 3))
    # self-supporting 45-deg gable-roofed driveshaft tunnel (Y = -50..+50) and partitioned wire conduit (Y = -154..-74)
    cuts.append(F.prism_cutter("Tub_ShaftTunnel", "+X",
                               [(-50.0, 335.0), (50.0, 335.0), (50.0, 445.0), (0.0, 495.0), (-50.0, 445.0)],
                               (CAB_X0 - 15.0) * SCALE, (CAB_X1 + 15.0) * SCALE))

    def _wire_prof(z0):
        return [(-154.0, z0), (-74.0, z0), (-74.0, z0 + 57.0), (-114.0, z0 + 97.0), (-154.0, z0 + 57.0)]

    wire_stations = [
        (CAB_X0 - 15.0, 335.0),
        (3085.0, 335.0),
        (3240.0, 445.0),
        (3395.0, 598.0),
        (CAB_X1 + 15.0, 598.0),
    ]
    cuts.append(F.loft_solid("Tub_WireTunnel", "+X", [(_wire_prof(z0), x * SCALE) for x, z0 in wire_stations]))
    return tub, pieces, cuts


# ---------------------------------------------------------------- steering wheel

def _perforated_spoke(name, r0, r1, w0, w1, y_front, y_back_hub, y_back_rim, holes, angle, n_arc=8):
    """Watertight all-quad tapered steering wheel spoke (print mm) with circular lightening holes
    through Y, flush at y = y_front with outer tip tucked inside the round rim cross-section."""
    bm = bmesh.new()

    def w_at(x):
        t = (x - r0) / (r1 - r0)
        return w0 + (w1 - w0) * t

    def yf_at(x):
        # Keep the spoke's driver-side face flat at y_front up to the rim's inner flat footprint (r1 - 0.35),
        # then tuck the outermost tip inside the rim's round tube so no square corner pokes out
        if x <= r1 - 0.35:
            return y_front
        u = (x - (r1 - 0.35)) / 0.35
        return y_front - 0.22 * u

    def yb_at(x):
        t = (x - r0) / (r1 - r0)
        base = y_back_hub + (y_back_rim - y_back_hub) * t
        if x <= r1 - 0.35:
            return base
        u = (x - (r1 - 0.35)) / 0.35
        return base + 0.18 * u

    # Stations: list of (x, h, in_hole_after) where h == 0 is a 3-vert station and h > 0 is a 4-vert station
    stations = [(r0, 0.0, False)]
    for cx, cr in holes:
        for j in range(n_arc):
            theta = math.pi * (1.0 - j / n_arc)
            x = cx + cr * math.cos(theta)
            h = 0.0 if j == 0 else cr * math.sin(theta)
            stations.append((x, h, True))
        stations.append((cx + cr, 0.0, False))
    stations.append((r1 - 0.35, 0.0, False))
    stations.append((r1, 0.0, False))

    rings = []
    for x, h, in_hole in stations:
        w = w_at(x)
        yf = yf_at(x)
        yb = yb_at(x)
        if h <= 1e-6:
            bf = bm.verts.new((x, yf, -w))
            mf = bm.verts.new((x, yf, 0.0))
            tf = bm.verts.new((x, yf, w))
            bb = bm.verts.new((x, yb, -w))
            mb = bm.verts.new((x, yb, 0.0))
            tb = bm.verts.new((x, yb, w))
            rings.append({"kind": 3, "in_hole": in_hole, "bf": bf, "mf": mf, "tf": tf, "bb": bb, "mb": mb, "tb": tb})
        else:
            bf = bm.verts.new((x, yf, -w))
            hbf = bm.verts.new((x, yf, -h))
            htf = bm.verts.new((x, yf, h))
            tf = bm.verts.new((x, yf, w))
            bb = bm.verts.new((x, yb, -w))
            hbb = bm.verts.new((x, yb, -h))
            htb = bm.verts.new((x, yb, h))
            tb = bm.verts.new((x, yb, w))
            rings.append({"kind": 4, "in_hole": in_hole, "bf": bf, "hbf": hbf, "htf": htf, "tf": tf,
                          "bb": bb, "hbb": hbb, "htb": htb, "tb": tb})

    for a, b in zip(rings[:-1], rings[1:]):
        it_af = a["mf"] if a["kind"] == 3 else a["htf"]
        ib_af = a["mf"] if a["kind"] == 3 else a["hbf"]
        it_ab = a["mb"] if a["kind"] == 3 else a["htb"]
        ib_ab = a["mb"] if a["kind"] == 3 else a["hbb"]

        it_bf = b["mf"] if b["kind"] == 3 else b["htf"]
        ib_bf = b["mf"] if b["kind"] == 3 else b["hbf"]
        it_bb = b["mb"] if b["kind"] == 3 else b["htb"]
        ib_bb = b["mb"] if b["kind"] == 3 else b["hbb"]

        # Front cap (y = yf) and back cap (y = yb)
        bm.faces.new((a["tf"], b["tf"], it_bf, it_af))
        bm.faces.new((ib_af, ib_bf, b["bf"], a["bf"]))
        bm.faces.new((it_ab, it_bb, b["tb"], a["tb"]))
        bm.faces.new((a["bb"], b["bb"], ib_bb, ib_ab))

        # Outer side walls (z = +w and z = -w)
        bm.faces.new((a["tb"], b["tb"], b["tf"], a["tf"]))
        bm.faces.new((a["bf"], b["bf"], b["bb"], a["bb"]))

        # Inner cylindrical hole walls when crossing a hole interval
        if a["in_hole"]:
            bm.faces.new((it_af, it_bf, it_bb, it_ab))
            bm.faces.new((ib_ab, ib_bb, ib_bf, ib_af))

    # End caps at x = r0 and x = r1
    s0, s1 = rings[0], rings[-1]
    bm.faces.new((s0["tf"], s0["mf"], s0["mb"], s0["tb"]))
    bm.faces.new((s0["mf"], s0["bf"], s0["bb"], s0["mb"]))
    bm.faces.new((s1["mf"], s1["tf"], s1["tb"], s1["mb"]))
    bm.faces.new((s1["bf"], s1["mf"], s1["mb"], s1["bb"]))

    bmesh.ops.rotate(bm, cent=(0.0, 0.0, 0.0), matrix=Matrix.Rotation(angle, 3, 'Y'), verts=bm.verts)
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def steering_wheel():
    """Separate part: wheel rim, three perforated brushed-chrome spokes in the 1967 Y-layout,
    chrome horn ring, hub, tapered collar and column, built with its axis along +Y (prints face
    down on the rim with the column pointing up). Returns (object, pieces, axis_matrix)."""
    S = SCALE
    from wheels import _revolve
    R, tube, flat = WHEEL_R * S, 0.62, 0.35
    ring = [(R + tube * math.cos(a), min(flat, tube * math.sin(a))) for a in (2 * math.pi * k / 24 for k in range(24))]
    rim = bpy.data.objects.new("SteeringWheel", _revolve(ring, "SteeringWheel", 64))
    pieces = []
    # Authentic 1967 Mustang 3-spoke Y-pattern: 6 o'clock vertical spoke + 2:20 and 9:40 upper-side spokes,
    # each tapered from hub to rim with 3 circular lightening holes and tucked outer tips
    spoke_angles = (math.pi / 2, -math.radians(16.0), math.pi + math.radians(16.0))
    holes = ((3.55, 0.42), (5.45, 0.35), (7.15, 0.28))
    for k, a in enumerate(spoke_angles):
        pieces.append(_perforated_spoke(
            f"SteeringWheel_Spoke{k}",
            r0=1.35, r1=R + 0.05,
            w0=0.96, w1=0.58,
            y_front=flat, y_back_hub=flat - 0.90, y_back_rim=flat - 0.68,
            holes=holes, angle=a,
        ))
    column_len = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).length + 80.0     # reaches into the dash socket
    pieces.append(_cylinder("SteeringWheel_Hub", (0, -0.68 / S, 0), (0, (flat - 0.04) / S, 0), 1.72 / S, 36))
    pieces.append(_cylinder("SteeringWheel_HornRing", (0, -0.45 / S, 0), (0, flat / S, 0), 1.15 / S, 32))
    pieces.append(_cylinder("SteeringWheel_Collar", (0, -2.4 / S, 0), (0, -0.55 / S, 0), COLUMN_R, 28, r2=1.62 / S))
    pieces.append(_cylinder("SteeringWheel_Column", (0, -column_len, 0), (0, 0.3 / S, 0), COLUMN_R, 24))
    # orientation in the car: local +Y points from the column base toward the driver
    axis = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).normalized()
    rot = axis.to_track_quat('Y', 'Z').to_matrix().to_4x4()
    placement = Matrix.Translation(Vector(WHEEL_CENTRE) * S) @ rot
    return rim, pieces, placement
