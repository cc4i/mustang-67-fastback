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


def _cylinder(name, p0, p1, r, segments=20):
    """Cylinder between two points (real mm)."""
    a, b = Vector(p0) * SCALE, Vector(p1) * SCALE
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r * SCALE, radius2=r * SCALE, depth=d.length)
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
DASH_HOODS = (360.0, 250.0)          # twin cowls over the dash: centre |y|, half width
REAR_SEAT = (3110.0, 3360.0, 535.0, 560.0)        # x0, x1, half width, cushion top
REAR_BACK_PROFILE = [(3300.0, 520.0), (3395.0, 520.0), (3405.0, 900.0), (3360.0, 905.0)]


def ceiling_edge(x0, x1, y, z_max, samples=10, gap=15.0):
    """[(x, z)] top edge for an interior part at lateral y: z_max, lowered to stay `gap` under the
    cabin ceiling where the greenhouse curves in (around the windshield base)."""
    pts = []
    for k in range(samples + 1):
        x = x0 + (x1 - x0) * k / samples
        pts.append((x, min(z_max, cabin_ceiling(x, y) - gap)))
    return pts


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
    # firewall + dashboard (side profile: sloped face, knee chamfer at ~45 deg so it prints)
    dash_half = CABIN_HALF - i - PANEL_T + 5
    dash_top = ceiling_edge(DASH_X0, 1925, dash_half, DASH_TOP, samples=6)
    dash = [(DASH_X0, FLOOR_Z0), (DASH_X0 + 90, FLOOR_Z0), (DASH_X0 + 90, 470), (DASH_FACE_X, 620), (DASH_FACE_X, 760)]
    dash += list(reversed(dash_top))
    pieces.append(_side_profile("Tub_Dash", dash, -dash_half, dash_half))
    # a chrome strip across the dash face, and the 1967 twin cowls: a padded visor over the gauges and
    # its twin over the glovebox, closed by cheeks at their ends, with a padded roll on the dash top
    # between them
    pieces.append(_box("Tub_DashTrim", DASH_FACE_X - 3.0, DASH_FACE_X + 3.0, -dash_half + 40.0, dash_half - 40.0, 748.0, 758.0, 0))
    hy, hw = DASH_HOODS
    roll_z = min(DASH_TOP, min(cabin_ceiling(1950.0, y) for y in (-hy + hw, 0.0, hy - hw)) - 30.0) - 16.0
    pieces.append(F.tube("Tub_DashPad", [(1935.0, y, roll_z) for y in (-(hy - hw) - 5.0, 0.0, hy - hw + 5.0)], 20.0, 16))
    for s in (-1, 1):
        y0, y1 = sorted((s * (hy - hw), s * (hy + hw)))
        pt = min(DASH_TOP + 30.0, min(cabin_ceiling(x, y) for x in (1990.0, 2030.0) for y in (y0, (y0 + y1) / 2, y1)) - 15.0)
        lip = (2026.0, pt - 36.0)                     # the visor's lip, its underside rising back to the dash face
        hood = F.rounded_poly([(1925.0, dash_top[-1][1] - 10.0), (1995.0, pt), (2018.0, pt - 4.0), (2028.0, pt - 18.0), lip,
                               (1975.0, 868.0), (1940.0, 868.0)], [0, 20, 8, 6, 6, 8, 0])
        pieces.append(_side_profile(f"Tub_DashHood{s}", hood, y0, y1))
        cheek = [(1960.0, 740.0), (lip[0] - 6.0, 780.0), (lip[0] - 6.0, lip[1] + 2.0), (1930.0, 860.0)]   # rooted in the dash
        for k, (c0, c1) in enumerate(((y0, y0 + 15.0), (y1 - 15.0, y1))):
            pieces.append(_side_profile(f"Tub_DashCheek{s}{k}", cheek, c0, c1))
    # five round gauge pods in front of the driver, recessed square to the sloped dash face
    face_a, face_b = Vector((DASH_FACE_X, 760.0)), Vector((1925.0, DASH_TOP))
    tan = (face_b - face_a).normalized()
    normal = Vector((-tan.y, tan.x)) if -tan.y > 0 else Vector((tan.y, -tan.x))     # points into the cabin (+x)
    gauge_z = 800.0
    face_x = face_a.x + (gauge_z - face_a.y) / tan.y * tan.x
    depth = 0.35 / SCALE
    for k, (dy, r) in enumerate(zip((-190, -95, 0, 95, 190), (32, 36, 52, 36, 32))):
        c = Vector((face_x, DRIVER_Y + dy, gauge_z))
        n3 = Vector((normal.x, 0.0, normal.y))
        pieces.append(_cylinder(f"Tub_GaugeBezel{k}", c - n3 * 3.0, c + n3 * 4.0, r + 7.0, 24))   # the pod's cut leaves a chrome ring
        cuts.append(_cylinder(f"Tub_Gauge{k}", c - n3 * depth, c + n3 * 40.0, r, 24))
    # steering column socket (the column belongs to the steering-wheel part)
    axis = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).normalized()
    cuts.append(_cylinder("Tub_ColumnSocket", Vector(COLUMN_BASE) - axis * 95, Vector(COLUMN_BASE) + axis * 60, COLUMN_R + 0.15 / SCALE))
    # transmission tunnel, console and T-handle shifter
    pieces.append(_box("Tub_Tunnel", CAB_X0 + 60, 3000, -140, 140, FLOOR_Z0, 440, 40))
    pieces.append(_box("Tub_Console", 1960, 2620, -105, 105, FLOOR_Z0, 500, 30))
    pieces.append(_box("Tub_ConsoleTrim", 1957, 2623, -108, 108, 488, 497, 31))
    pieces.append(_cylinder("Tub_Shifter", (2300, 0, 490), (2300, 0, 610), 14))
    pieces.append(_sphere("Tub_ShifterKnob", (2300, 0, 615), 28, twist=11.25))     # meridians between the shaft's 20 edges
    # front bucket seats: cushion with a padded front roll, reclined back with rounded top corners and
    # chrome side trim, pleats
    for tag, yc in (("Driver", DRIVER_Y), ("Passenger", PASSENGER_Y)):
        y0, y1 = yc - SEAT_W / 2, yc + SEAT_W / 2
        # the cushion slab on a riser set in at the front and sides, a 45 deg chamfer under its overhang
        slab_z0 = SEAT_TOP - SEAT_SLAB
        riser = rect(SEAT_X0 + SEAT_INSET, y0 + SEAT_INSET, SEAT_X1, y1 - SEAT_INSET, 20)
        slab = rect(SEAT_X0, y0, SEAT_X1, y1, 45)
        pieces.append(F.loft_solid(f"Tub_Seat{tag}", "+Z", [(riser, FLOOR_Z0 * SCALE), (riser, (slab_z0 - SEAT_INSET) * SCALE),
                                                            (slab, slab_z0 * SCALE), (slab, SEAT_TOP * SCALE)]))
        roll = [(SEAT_X0 + 30.0, y, SEAT_TOP - 26.0) for y in (y0 + 22.0, y0 + 45.0, yc, y1 - 45.0, y1 - 22.0)]
        pieces.append(F.tube(f"Tub_SeatRoll{tag}", roll, [16.0, 26.0, 28.0, 26.0, 16.0], 16))
        # backrest height: stay clear of the cabin ceiling at its outer top corner
        y_corner = max(abs(y0 + 15), abs(y1 - 15))
        top = min(BACK_PROFILE[3][1], min(cabin_ceiling(x, y_corner) for x in (2745.0, 2775.0, 2810.0, 2840.0)) - 15.0)
        drop = BACK_PROFILE[3][1] - top
        back = [BACK_PROFILE[0], BACK_PROFILE[1], (BACK_PROFILE[2][0], BACK_PROFILE[2][1] - drop),
                (BACK_PROFILE[3][0], top), (BACK_PROFILE[4][0], top)]
        pieces.append(_side_profile(f"Tub_SeatBack{tag}", F.rounded_poly(back, [0.0, 0.0, 25.0, 25.0, 18.0]), y0 + 15, y1 - 15))
        a, b = Vector(back[0]), Vector(back[-1])                      # front face of the backrest
        d = (b - a).normalized()
        n = Vector((-d.y, d.x))                                       # points toward the dash (-x)
        trim = details.line_band(tuple(a + d * 40 - n * 30), tuple(b - d * 45 - n * 30), 16.0)
        for side_y in (y0 + 15, y1 - 15):
            pieces.append(_side_profile(f"Tub_SeatTrim{tag}{int(side_y)}", trim, side_y - 3.0, side_y + 3.0))
        for k in range(4):                       # pleats along the cushion and up the backrest
            yy = y0 + 70 + k * (SEAT_W - 140) / 3
            cuts.append(_box(f"Tub_Pleat{tag}{k}", SEAT_X0 + 40, SEAT_X1 - 80, yy - 7, yy + 7, SEAT_TOP - 12, SEAT_TOP + 20))
            p0, p1 = a + d * 90, b - d * 60
            groove = [tuple(p0 - n * 12), tuple(p1 - n * 12), tuple(p1 + n * 30), tuple(p0 + n * 30)]
            cuts.append(_side_profile(f"Tub_BackPleat{tag}{k}", groove, yy - 7, yy + 7))
    # fold-down rear seat between the wheelhouses
    x0, x1, hw, top = REAR_SEAT
    pieces.append(_box("Tub_RearSeat", x0, x1, -hw, hw, FLOOR_Z0, top, 40))
    pieces.append(_side_profile("Tub_RearSeatBack", REAR_BACK_PROFILE, -hw, hw))
    return tub, pieces, cuts


# ---------------------------------------------------------------- steering wheel

def steering_wheel():
    """Separate part: wheel rim, three spokes, hub and column, built with its axis along +Y
    (prints face down on the rim with the column pointing up). The driver's side of the rim, hub
    and spokes is flattened at y = FLAT so the first layer is a 0.85 mm band, not a sliver of tube
    the slicer would drop. Returns (object, pieces, axis_matrix)."""
    S = SCALE
    from wheels import _revolve
    R, tube, flat = WHEEL_R * S, 0.55, 0.35
    ring = [(R + tube * math.cos(a), min(flat, tube * math.sin(a))) for a in (2 * math.pi * k / 16 for k in range(16))]
    rim = bpy.data.objects.new("SteeringWheel", _revolve(ring, "SteeringWheel", 64))
    pieces = []
    for k in range(3):
        a = math.pi / 2 + 2 * math.pi * k / 3 + math.pi
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(R - 0.3, 0.8, 0.9), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(R / 2, flat - 0.4, 0), verts=bm.verts)       # face flush with the rim's flat
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, 'Y'), verts=bm.verts)
        me = bpy.data.meshes.new(f"SteeringWheel_Spoke{k}")
        bm.to_mesh(me)
        bm.free()
        pieces.append(bpy.data.objects.new(f"SteeringWheel_Spoke{k}", me))
    column_len = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).length + 80.0     # reaches into the dash socket
    pieces.append(_cylinder("SteeringWheel_Hub", (0, -0.6 / S, 0), (0, flat / S, 0), 1.6 / S, 32))
    pieces.append(_cylinder("SteeringWheel_Column", (0, -column_len, 0), (0, 0.3 / S, 0), COLUMN_R, 24))
    # orientation in the car: local +Y points from the column base toward the driver
    axis = (Vector(WHEEL_CENTRE) - Vector(COLUMN_BASE)).normalized()
    rot = axis.to_track_quat('Y', 'Z').to_matrix().to_4x4()
    placement = Matrix.Translation(Vector(WHEEL_CENTRE) * S) @ rot
    return rim, pieces, placement
