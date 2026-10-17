"""1967 Mustang Fastback body shell for 1:20 printing.

Profiles are authored in real-car millimetres (x: front -> rear, y: left/right,
z: up from the ground) and scaled by SCALE when the mesh is built, so the
Blender scene is in print millimetres (1 BU = 1 mm).
"""
import bisect
import math

import bmesh
import bpy

SCALE = 1.0 / 20.0

# Real-car reference dimensions (mm)
WHEELBASE = 2743.0
FRONT_AXLE_X = 792.0
REAR_AXLE_X = FRONT_AXLE_X + WHEELBASE
WHEEL_RADIUS = 330.0
Z_BOTTOM = 290.0  # flat underside of the body = rocker bottom (print bed); the chassis hangs below
X_NOSE = 60.0     # front face of the body (bumper sits ahead of this)
X_TAIL = 4520.0   # rear face of the body


def lerp_table(table, x):
    """Piecewise-linear lookup in a sorted [(x, value), ...] table."""
    xs = [p[0] for p in table]
    if x <= xs[0]:
        return table[0][1]
    if x >= xs[-1]:
        return table[-1][1]
    i = bisect.bisect_right(xs, x)
    x0, v0 = table[i - 1]
    x1, v1 = table[i]
    t = (x - x0) / (x1 - x0)
    return v0 + (v1 - v0) * t


def smooth_table(table, x):
    """Like lerp_table, but a monotone cubic through the knots, so it has no kinks; level (zero
    slope) at both ends, where it is held."""
    xs, vs = [p[0] for p in table], [p[1] for p in table]
    if x <= xs[0]:
        return vs[0]
    if x >= xs[-1]:
        return vs[-1]
    h = [b - a for a, b in zip(xs, xs[1:])]
    d = [(b - a) / w for a, b, w in zip(vs, vs[1:], h)]
    m = [0.0] * len(xs)
    for i in range(1, len(xs) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    i = bisect.bisect_right(xs, x) - 1
    t = (x - xs[i]) / h[i]
    return (vs[i] * (2 * t ** 3 - 3 * t * t + 1) + h[i] * m[i] * (t ** 3 - 2 * t * t + t) +
            vs[i + 1] * (3 * t * t - 2 * t ** 3) + h[i] * m[i + 1] * (t ** 3 - t * t))


# Centre-line roof/hood height
Z_CENTER = [
    (60, 850), (140, 870), (400, 900), (1000, 925), (1450, 942),
    (1650, 960), (2060, 1285), (2450, 1310), (2700, 1305), (3000, 1272),
    (3500, 1185), (4000, 1092), (4300, 1035), (4440, 1012), (4520, 998),
]
# Shoulder (top of fender / beltline) height
Z_SHOULDER = [
    (60, 835), (150, 850), (900, 872), (1700, 900), (2400, 902),
    (2750, 915), (2890, 943), (2950, 973), (3000, 989), (3060, 997), (3350, 997), (3600, 997),
    (3800, 995), (4000, 991), (4150, 987), (4300, 982), (4440, 975), (4520, 970),
]
# Half width at the shoulder
W_BELT = [
    (60, 845), (300, 852), (900, 852), (1500, 846), (2300, 842),
    (2800, 850), (3250, 874), (3700, 878), (4100, 868), (4400, 870),
    (4520, 870),          # the tail stays full width out to the quarter extensions (the end cap pulls it in ~17)
]
# Half width where the greenhouse meets the beltline
W_GH_BASE = [
    (60, 620), (1720, 715), (2300, 735), (3000, 745), (3600, 720),
    (4100, 690), (4520, 680),
]
# Half width of the roof crown edge (on the hood this is just crown shaping)
W_ROOF = [
    (60, 330), (1620, 420), (2060, 560), (2600, 590), (3200, 560),
    (3800, 545), (4300, 600), (4520, 620),
]

STATIONS = [
    60, 100, 200, 350, 500, 650, 792, 950, 1100, 1250, 1450, 1650, 1850, 2060,
    2250, 2450, 2650, 2850, 2950, 3050, 3150, 3250, 3400, 3535, 3700, 3850, 4000, 4200, 4350,
    4450, 4520,
]


# The quarter extensions rise into small rounded fins at the tail corners, standing ~50 mm above
# the deck lid between them: (inboard distance from the body side, lift) real mm, faded in
# over FIN_X0..FIN_X1.
FIN_X0, FIN_X1 = 4250.0, 4480.0
FIN_PROFILE = [(0.0, 73.0), (40.0, 76.0), (150.0, 67.0), (190.0, 39.0), (230.0, 13.0), (260.0, 0.0)]


def fin_lift(x, d):
    t = max(0.0, min(1.0, (x - FIN_X0) / (FIN_X1 - FIN_X0)))
    return lerp_table(FIN_PROFILE, d) * t * t * (3 - 2 * t)


# From just behind the door the quarter crest stands up off the shoulder line, runs level back over
# the wheel (as in the side photo) and only at the tail rises gently into the fins, with no saddle
# in front of them: lift (real mm) along x, weighted by |y| across the crest.
HIP_RISE = [(2890.0, 0.0), (2990.0, 12.0), (3060.0, 20.0), (3600.0, 22.0), (3900.0, 27.0), (4150.0, 33.0), (4250.0, 36.0),
            (4330.0, 31.0), (4400.0, 18.0), (4450.0, 6.0), (4490.0, 0.0)]
HIP_ACROSS = [(660.0, 0.0), (708.0, 0.6), (732.0, 1.0), (845.0, 1.0), (888.0, 0.0)]
# The fins' outer sides lean in toward the top (tumblehome) over the last ~150 mm: inset (real mm)
# by height.
FIN_TUCK = [(863.0, 0.0), (890.0, 6.0), (914.0, 12.0), (928.0, 18.0), (945.0, 24.0), (959.0, 30.0), (976.0, 44.0),
            (993.0, 58.0), (1010.0, 66.0), (1024.0, 70.0)]
# ...but the crown's inboard edge (point 8) keeps the gentler tuck, so it stays outboard of the deck gutter
FIN_TUCK_INNER = [(863.0, 0.0), (890.0, 6.0), (914.0, 12.0), (928.0, 18.0), (945.0, 22.0), (959.0, 26.0), (976.0, 35.0),
                  (993.0, 41.0), (1010.0, 44.0), (1024.0, 46.0)]
FIN_TUCK_X0, FIN_TUCK_X1 = 4280.0, 4430.0


# The quarter extensions stand proud of the taillight panel: on the subdivided shell, from
# CORNER_EXT_X0 back, everything outboard of the lamps (|y| past CORNER_EXT_Y) is pushed rearward by
# CORNER_EXT (real mm, by height): full depth from where the extension stands on the bumper's curled-up
# end (details.REAR_BUMPER_Z + REAR_BUMPER_RISE; the bumper's top rows ride up its foot, so the two
# faces are flush), then tipping forward more and more as it rises; over the fins (|y| past
# FIN_ROLL_Y: the crown inboard of the extension as well) the top-rear corner rolls forward with it
# (negative), from just above the tail trim (details.tail_trim_path, z ~956-970 out there), so the
# chrome strip stays on an upright face: tipped up, it would mirror the dim ceiling, not the floor, and
# read black. From the side the tail is one convex roll from the top down onto a near-upright face
# over the bumper, and the cap reads as a rounded column instead of a horn.
CORNER_EXT = [(760.0, 0.0), (777.0, 36.0), (792.0, 60.0), (840.0, 52.0), (880.0, 41.0), (920.0, 25.0), (960.0, 8.0),
              (990.0, 0.0)]
FIN_ROLL = [(972.0, 0.0), (990.0, -8.0), (1008.0, -24.0), (1032.0, -41.0), (1060.0, -55.0)]   # smooth_table
FIN_ROLL_Y = (640.0, 700.0)
CORNER_EXT_Y = (760.0, 810.0)
CORNER_EXT_X0 = 4380.0


def _smooth01(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def corner_ext(x, y, z):
    """Rearward push (real mm) of the shell at (x, y, z) into the quarter extensions."""
    if x <= CORNER_EXT_X0:
        return 0.0
    wx = _smooth01((x - CORNER_EXT_X0) / (X_TAIL - CORNER_EXT_X0))
    wy = _smooth01((abs(y) - CORNER_EXT_Y[0]) / (CORNER_EXT_Y[1] - CORNER_EXT_Y[0]))
    wf = _smooth01((abs(y) - FIN_ROLL_Y[0]) / (FIN_ROLL_Y[1] - FIN_ROLL_Y[0]))
    return (lerp_table(CORNER_EXT, z) * wy + smooth_table(FIN_ROLL, z) * wf) * wx


def extend_quarter_corners(me):
    """Push the tail corners of the (subdivided) shell rearward into the quarter extensions."""
    for v in me.vertices:
        x, y, z = (c / SCALE for c in v.co)
        d = corner_ext(x, y, z)
        if d:
            v.co.x += d * SCALE
    me.update()


# The quarters' lower rear corners roll under, out of sight behind the rear tires and round into
# the valance corners (photos 1 and 3): below a crease that rises from the rear wheel arch to behind
# the rear bumper's ends, the skin is drawn in toward the centre line, by nothing at the crease and
# ever faster below it, until one `length` down it runs in at QUARTER_TUCK_SLOPE (mm in per mm down:
# under 45 degrees, so it still prints without support). (x, crease z, length) knots, joined smoothly;
# ahead of the first the crease is under the body, and up to the arch's end it stays inside the arch.
QUARTER_TUCK = [(3860.0, 250.0, 80.0), (3930.0, 490.0, 85.0), (4000.0, 545.0, 88.0), (4100.0, 580.0, 90.0),
                (4200.0, 610.0, 92.0), (4300.0, 650.0, 94.0), (4400.0, 710.0, 96.0), (4500.0, 728.0, 99.0)]
QUARTER_TUCK_SLOPE = 0.72
QUARTER_TUCK_CAP = (165.0, 215.0)    # low down the draw eases off from the first toward the second
# The draw is full outboard of the second |y| and fades out inboard of it, to nothing at the first:
# on the flat tail face it only slides the skin across, rounding the corners in. Fading over this
# span the cap keeps every point outboard of its inboard neighbours, so the shell never folds.
QUARTER_TUCK_Y = (480.0, 860.0)
# A level-3 edge is ~30 mm long, too coarse for the roll (the skin would turn ~25 degrees from one
# edge to the next, faceted in the print): wherever the draw bends the skin, the edges are first
# cut this many times, and once drawn in, the new points are relaxed this many times (each halfway
# to the mean of its neighbours: the cut faces are flat, so the turn would still bunch up on the old
# edges), so it turns under ~5 degrees per edge.
QUARTER_TUCK_CUTS = 4
QUARTER_TUCK_RELAX = 3


def quarter_tuck(x, z):
    """How far (real mm) the quarter's skin is drawn in at station x, height z (QUARTER_TUCK)."""
    if x <= QUARTER_TUCK[0][0]:
        return 0.0
    crease, length = (smooth_table([(r[0], r[k]) for r in QUARTER_TUCK], x) for k in (1, 2))
    t = (crease - z) / length
    if t <= 0.0:
        return 0.0
    d = QUARTER_TUCK_SLOPE * length * (t ** 3 - t ** 4 / 2 if t < 1.0 else t - 0.5)   # C2 at the crease and at t = 1
    k0, k1 = QUARTER_TUCK_CAP
    return d if d <= k0 else k0 + (k1 - k0) * math.tanh((d - k0) / (k1 - k0))


def quarter_draw(x, y, z):
    """quarter_tuck faded in across QUARTER_TUCK_Y."""
    y0, y1 = QUARTER_TUCK_Y
    return quarter_tuck(x, z) * _smooth01((abs(y) - y0) / (y1 - y0))


def tuck_lower_quarters(me):
    """Roll the lower rear corners of the (subdivided, corner-extended) shell under: every point
    moves straight across the car, by quarter_draw. First the edges are cut QUARTER_TUCK_CUTS times
    wherever the draw bends the skin (its second difference over one edge length along x, y or z,
    times how squarely the skin faces sideways, is over 1 mm) and one edge ring beyond, so the finer
    mesh ends where the skin hardly bends; but not up into the tail corners' pushed-out (long, thin)
    faces above the crease, which would only be cut into slivers. Last the cut patch is relaxed
    (QUARTER_TUCK_RELAX)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    h = 30.0
    for v in bm.verts:
        x, y, z = (c / SCALE for c in v.co)
        v.tag = x > QUARTER_TUCK[0][0] - h and abs(y) > QUARTER_TUCK_Y[0] - h and any(
            abs(v.normal.y * (quarter_draw(x + a, y + b, z + c) - 2 * quarter_draw(x, y, z) +
                              quarter_draw(x - a, y - b, z - c))) > 1.0
            for a, b, c in ((h, 0.0, 0.0), (0.0, h, 0.0), (0.0, 0.0, h)))
    for v in [w for v in bm.verts if v.tag for e in v.link_edges for w in e.verts]:
        x, y, z = (c / SCALE for c in v.co)
        v.tag = v.tag or quarter_draw(x, y, z - h) > 0.0
    old = {v.co.to_tuple() for v in bm.verts}
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.verts[0].tag and e.verts[1].tag],
                              cuts=QUARTER_TUCK_CUTS, use_grid_fill=True)
    bm.verts.index_update()
    new = [v.co.to_tuple() not in old for v in bm.verts]    # the cuts' points (they come out tagged too)
    for v in bm.verts:
        x, y, z = (c / SCALE for c in v.co)
        d = quarter_draw(x, y, z)
        if d:
            v.co.y -= math.copysign(d, y) * SCALE
    # relax the cut patch's points (new and old alike: pinning the old ones would only gather the turn
    # on them) but not its rim, which joins the uncut faces, nor next to the shell's real edges (the
    # floor's rim), which would be rounded off
    bm.normal_update()
    edge = [False] * len(bm.verts)
    for e in bm.edges:
        if not e.is_contiguous or e.calc_face_angle() > math.radians(20.0):
            for w in (w for v in e.verts for f in v.link_faces for w in f.verts):
                edge[w.index] = True
    inner = [v for v in bm.verts if v.tag and not edge[v.index] and
             all(new[w.index] or w.tag for e in v.link_edges for w in e.verts)]
    for _ in range(QUARTER_TUCK_RELAX):
        bmesh.ops.smooth_vert(bm, verts=inner, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(me)
    bm.free()
    me.update()


# section point index -> subdivision crease weight (mirrored on both sides)
CREASES = {2: 0.5, 6: 0.65}


def crease_fade(x, k):
    """The fender crest is crisp up front and over the doors, soft over the rear hips."""
    if k != 6:
        return 1.0
    return max(0.25, min(1.0, (3300 - x) / 500.0))


def section(x):
    """Right-half cross-section points (y, z) from the underside to the centre line."""
    zb = Z_BOTTOM
    zs = lerp_table(Z_SHOULDER, x)
    zc = max(lerp_table(Z_CENTER, x), zs + 30)
    wb = lerp_table(W_BELT, x)
    wg = min(lerp_table(W_GH_BASE, x), wb - 30)
    wr = min(lerp_table(W_ROOF, x), wg - 20)
    # Greenhouse rise above the shoulder; on the hood and tail deck it is just crown.
    gh = zc - zs
    cabin = max(0.0, min(1.0, (gh - 40) / 200))   # 0 on hood/deck, 1 under the roof
    base = zs + 6 + 18 * cabin                     # window sill height
    rise = zc - base
    # centre ridge along the hood (ahead of the windshield only)
    ridge = 9.0 * max(0.0, min(1.0, (1650 - x) / 150.0)) * max(0.0, min(1.0, (x - 120) / 150.0))
    fin = max(0.0, min(1.0, (x - FIN_X0) / (FIN_X1 - FIN_X0)))   # the fin corner is squarer than the hips
    pts = [
        (wb - 40, zb),
        (wb - 14, zb + 26),     # <45 degree roll-under: prints without support
        (wb - 7, zb + 42),      # rocker edge (chrome strip sits just above)
        (wb - 4, zb + 130),
        (wb + 4, (zb + zs) / 2 + 70),
        (wb, zs - 75),
        (wb - 9 + 4 * fin, zs - 30),
        (wb - 38 + 14 * fin, zs - 2),
        ((wb - 38 + wg) / 2, zs + 3 + 5 * cabin),
        (wg + 6, base - 10 * cabin),
        (wg, base),
        (wg - (wg - wr) * 0.5, base + rise * 0.55),
        (wr + 22, base + rise * (0.86 + 0.04 * (1 - cabin))),
        (wr + 6, base + rise * 0.95),
        (wr * 0.6, zc - rise * 0.02 - ridge * 0.8),
        (wr * 0.25, zc - rise * 0.004 - ridge),
        (0.0, zc),
    ]
    if fin:
        pts = [(y, z + fin_lift(x, wb - y)) if k >= 5 else (y, z) for k, (y, z) in enumerate(pts)]
    rise = lerp_table(HIP_RISE, x) if HIP_RISE[0][0] < x < HIP_RISE[-1][0] else 0.0
    if rise:
        pts = [(y, z + rise * lerp_table(HIP_ACROSS, y)) if k >= 5 else (y, z) for k, (y, z) in enumerate(pts)]
    tuck = max(0.0, min(1.0, (x - FIN_TUCK_X0) / (FIN_TUCK_X1 - FIN_TUCK_X0)))
    if tuck:
        tuck = tuck * tuck * (3 - 2 * tuck)
        pts = [(y - tuck * lerp_table(FIN_TUCK if k < 8 else FIN_TUCK_INNER, z), z) if 5 <= k <= 8 else (y, z)
               for k, (y, z) in enumerate(pts)]
    return pts


def rake(x, z, y=0.0):
    """Lean the nose and tail faces: the grille recedes, the valances tuck under the bumpers.

    The shift fades out over several stations so rings stay ordered along X.
    """
    if x < 500:
        w = max(0.0, min(1.0, (500 - x) / 400.0))
        w_tip = _smooth01((280.0 - x) / 220.0)
        ay = abs(y)
        # 1967 shark-nose plan-view V-prow + swept-back front fender nose outside the grille
        v_prow = 18.0 * min(1.0, ay / 550.0) ** 1.4
        fender_setback = 42.0 * _smooth01((ay - 550.0) / 260.0) * _smooth01((z - 555.0) / 70.0)
        # shark-nose brow overhang at the nose tip, grille lean, valance tuck under the bumper, then ~45 deg roll-under
        push = (0.12 * max(0.0, 900 - z) + 0.11 * max(0.0, 825 - z) * w_tip +
                0.45 * max(0.0, 520 - z) + 0.45 * max(0.0, 450 - z))
        return x + push * w + (v_prow + fender_setback) * w_tip
    if x > 4100:
        w = max(0.0, min(1.0, (x - 4100) / 350.0))
        # tail panel lean, valance tuck, then a ~45 degree roll-under so the tail stands clear of the ground
        push = 0.05 * max(0.0, 990 - z) + 0.35 * max(0.0, 620 - z) + 0.65 * max(0.0, 500 - z)
        return x - push * w
    return x


def full_section(x):
    right = section(x)
    left = [(-y, z) for (y, z) in reversed(right[:-1])]
    return right + left


def end_cap_rings(x_end, direction, prof, steps):
    """Rings that close an end by shrinking the profile toward the underside centre."""
    rings = []
    for dx, s in steps:
        x = x_end + direction * dx
        rings.append([(x, y * s, Z_BOTTOM + (z - Z_BOTTOM) * s) for (y, z) in prof])
    return rings


def build_base_mesh(name="Body"):
    rings = []
    front_prof = full_section(STATIONS[0])
    rear_prof = full_section(STATIONS[-1])
    rings += list(reversed(end_cap_rings(X_NOSE, -1, front_prof, ((5, 0.97), (8.5, 0.88), (10, 0.4), (10.5, 0.08)))))
    for x in STATIONS:
        rings.append([(x, y, z) for (y, z) in full_section(x)])
    rings += end_cap_rings(X_TAIL, +1, rear_prof, ((6, 0.96), (10, 0.82), (12, 0.3), (12.5, 0.08)))

    bm = bmesh.new()
    vrings = [[bm.verts.new((rake(x, z, y) * SCALE, y * SCALE, z * SCALE)) for (x, y, z) in r] for r in rings]
    n = len(vrings[0])
    crease = bm.edges.layers.float.new("crease_edge")
    for a, b in zip(vrings[:-1], vrings[1:]):
        for i in range(n - 1):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
        # flat underside strip, creased so subdivision keeps it flat and sharp
        bm.faces.new((a[n - 1], a[0], b[0], b[n - 1]))
        for i in (0, n - 1):
            bm.edges.get((a[i], b[i]))[crease] = 1.0
        # crisp fender crest and rocker edge, as on the real sheet metal
        for k, w in CREASES.items():
            for i in (k, n - 1 - k):
                bm.edges.get((a[i], b[i]))[crease] = w * crease_fade(a[i].co.x / SCALE, k)
    # close the two tiny end rings
    bm.faces.new(vrings[0])
    bm.faces.new(list(reversed(vrings[-1])))
    for ring in (vrings[0], vrings[-1]):
        for i in range(n):
            bm.edges.get((ring[i], ring[(i + 1) % n]))[crease] = 1.0 if i == n - 1 else 0.0
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me
