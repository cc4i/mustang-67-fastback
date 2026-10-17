"""Printable 5-spoke rims and tires (print millimetres, axis along Y).

Assembly: a printed octagonal axle (2.3 mm across flats) presses into the rim hub and
spins freely in the chassis boss; the tire presses over the rim.
"""
import math

import bmesh
import bpy

from body import SCALE, WHEEL_RADIUS

K = SCALE / (1.0 / 24.0)               # scale factor relative to original 1:24 print-mm constants (1.2 at 1:20)
TIRE_R = WHEEL_RADIUS * SCALE          # 16.50 at 1:20
TIRE_W = 9.0 * K                       # wide radials, filling the arches as on the car
TIRE_OFFSET = -0.45 * K                # tire sits inboard of the rim lip
RIM_R = 8.0 * K                        # rim seat radius (9.60 mm)
RIM_BEAD_R = 8.38 * K                  # mid-barrel circumferential bead-lock & spline crown (10.056 mm)
RIM_LIP_R = 8.9 * K                    # chrome lip, seated in the tire's outer bead (10.68 mm)
RIM_W = 3.85 * K                       # rim half width (4.62 mm)
RIM_LIP_START = RIM_W - 1.0 * K        # rim-local y where the tire seat ends and the lip flares out
FIT_GAP = 0.08                         # precision tire bore clearance over the rim (print mm)
AXLE_FLATS = 2.70 * K                  # heavy-duty octagonal axle & stub across flats (3.24 mm; Ø 3.51 mm corners)
HUB_HOLE_R = 1.365 * K                 # rim hub bore radius (1.638 mm): strong 8-corner press fit
HUB_CAP_BORE_R = 1.05 * K              # stepped outer counterbore radius (1.26 mm): positive axial stop shoulder
TIRE_SPLINES = 12                      # longitudinal anti-slip drive splines around the mid-barrel bead seat
TIRE_SPLINE_AMP = 0.24 * K             # radial spline tooth amplitude (±0.288 mm)
SPOKES = 5


def _bead_spline_dr(r, y, a):
    """Radial modulation for the 12 longitudinal anti-slip drive splines on the mid-barrel bead crown."""
    if r < 8.15 * K or r > 8.65 * K:
        return 0.0
    y0, y1, y2, y3 = -1.40 * K, -1.00 * K, 0.35 * K, 0.75 * K
    if y <= y0 or y >= y3:
        return 0.0
    if y < y1:
        wy = (y - y0) / (y1 - y0)
    elif y > y2:
        wy = (y3 - y) / (y3 - y2)
    else:
        wy = 1.0
    return TIRE_SPLINE_AMP * wy * math.cos(TIRE_SPLINES * a)


def _revolve(profile, name, segments=96, spline_fn=None):
    """Revolve a closed (r, y) profile around the Y axis into a mesh."""
    bm = bmesh.new()
    rings = []
    for k in range(segments):
        a = 2 * math.pi * k / segments
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for (r, y) in profile:
            rr = r + (spline_fn(r, y, a) if spline_fn is not None else 0.0)
            ring.append(bm.verts.new((rr * ca, y, rr * sa)))
        rings.append(ring)
    m = len(profile)
    for k in range(segments):
        a, b = rings[k], rings[(k + 1) % segments]
        for i in range(m):
            j = (i + 1) % m
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def _rounded(points, radius, steps=4):
    """Fillet each corner of a closed polyline in (r, y)."""
    out = []
    n = len(points)
    for i in range(n):
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        if radius <= 0:
            out.append(p1)
            continue
        v0 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l0, l2 = math.hypot(*v0), math.hypot(*v2)
        rr = min(radius, l0 * 0.45, l2 * 0.45)
        a = (p1[0] + v0[0] / l0 * rr, p1[1] + v0[1] / l0 * rr)
        b = (p1[0] + v2[0] / l2 * rr, p1[1] + v2[1] / l2 * rr)
        for s in range(steps + 1):
            t = s / steps
            # quadratic bezier through the corner
            out.append((
                (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * p1[0] + t * t * b[0],
                (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * p1[1] + t * t * b[1],
            ))
    return out


def tire_mesh(name="Tire"):
    w = TIRE_W / 2
    o = TIRE_OFFSET
    ri = RIM_R + FIT_GAP
    bead_mid = RIM_BEAD_R + FIT_GAP
    bead_lip = RIM_LIP_R + FIT_GAP
    R = TIRE_R
    y_in = -w + o
    y_out = w + o
    lip_start = RIM_LIP_START - 0.10 * K
    # Inner bore features a 45-deg stepped mid-barrel bead-lock pocket + 12 longitudinal anti-slip
    # drive splines and an outer lip pocket, locking the tire both axially and rotationally on the rim.
    pts = [
        (ri + 0.90 * K, y_in),
        (ri, y_in + 0.60 * K),                          # inboard seat (locks behind mid-barrel bead crown)
        (ri, -2.18 * K),
        (bead_mid, -1.62 * K),                          # 45-deg ramp to mid-barrel bead-lock & spline pocket
        (bead_mid, -0.90 * K),
        (bead_mid, -0.35 * K),
        (bead_mid, 0.25 * K),
        (bead_mid, 0.98 * K),
        (ri, 1.54 * K),                                 # 45-deg ramp to outboard seat (locks ahead of crown)
        (ri, lip_start),
        (bead_lip, lip_start),                          # bead pocket round the outer chrome lip
        (bead_lip, y_out - 0.25 * K),
        (bead_lip + 0.50 * K, y_out),                   # outer sidewall
        (R - 0.9 * K, y_out),
        (R, y_out - 0.7 * K),
        (R, 1.75 * K + o), (R - 0.3 * K, 1.65 * K + o), (R - 0.3 * K, 1.35 * K + o), (R, 1.25 * K + o),
        (R, 0.25 * K + o), (R - 0.3 * K, 0.15 * K + o), (R - 0.3 * K, -0.15 * K + o), (R, -0.25 * K + o),
        (R, -1.25 * K + o), (R - 0.3 * K, -1.35 * K + o), (R - 0.3 * K, -1.65 * K + o), (R, -1.75 * K + o),
        (R, y_in + 0.7 * K),
        (R - 0.9 * K, y_in),
    ]
    return _revolve(_rounded(pts, 0.12 * K, 3), name, spline_fn=_bead_spline_dr)


def rim_blank_mesh(name="Rim"):
    w = RIM_W
    # +Y is the outer face. Thickened hub boss with a 45-deg counterbore axial stop shoulder at the
    # outer end of the axle socket, mid-barrel bead-lock crown + 12 drive splines, and Torq-Thrust dish.
    pts = [
        (HUB_HOLE_R, -w + 0.30 * K),
        (HUB_HOLE_R, w - 0.42 * K),                     # heavy-duty octagonal axle press-fit bore
        (HUB_CAP_BORE_R, w - 0.08 * K),                 # 45-deg conical counterbore axial stop shoulder
        (2.15 * K, w - 0.08 * K),                       # stepped center cap face
        (2.60 * K, w - 0.95 * K),                       # conical hub step
        (3.25 * K, w - 1.55 * K),                       # thickened inner spoke root dish
        (5.10 * K, w - 1.15 * K),                       # crowned Torq-Thrust spoke arch crest
        (RIM_R - 1.0 * K, w - 1.50 * K),                # outer dish trough inside barrel
        (RIM_R - 0.5 * K, w - 0.4 * K),
        (RIM_LIP_R - 0.3 * K, w + 0.2 * K),             # lip edge, flush with the tire's outer face
        (RIM_LIP_R, w - 0.3 * K),
        (RIM_LIP_R, w - 0.8 * K),
        (RIM_R, RIM_LIP_START),                         # outboard tire seat
        (RIM_R, 1.35 * K),
        (RIM_BEAD_R, 0.80 * K),                         # 45-deg ramp to mid-barrel bead-lock & spline crown
        (RIM_BEAD_R, 0.25 * K),
        (RIM_BEAD_R, -0.35 * K),
        (RIM_BEAD_R, -0.90 * K),
        (RIM_BEAD_R, -1.45 * K),
        (RIM_R, -2.00 * K),                             # 45-deg ramp to inboard tire seat
        (RIM_R, -w + 0.50 * K),
        (RIM_R - 0.80 * K, -w),
        (3.15 * K, -w),                                 # thickened rear hub boss back face (r = 3.78 mm)
        (2.35 * K, -w + 0.30 * K),
    ]
    return _revolve(_rounded(pts, 0.26 * K, 4), name, spline_fn=_bead_spline_dr)


def spoke_cutter_mesh(name="RimCutter"):
    """Five filleted window prisms between the Torq-Thrust spokes, extruded along Y through the dish."""
    bm = bmesh.new()
    r_in, r_out = 3.35 * K, RIM_R - 1.20 * K
    half_gap = math.radians(36 - 12.0)  # sculpted Torq-Thrust spokes with rounded window corners
    for k in range(SPOKES):
        c = 2 * math.pi * k / SPOKES + math.pi / SPOKES
        outline = []
        steps = 10
        for s in range(steps + 1):  # outer arc
            a = c - half_gap + 2 * half_gap * s / steps
            outline.append((r_out * math.cos(a), r_out * math.sin(a)))
        inner_half = half_gap * 0.55
        for s in range(steps + 1):  # inner arc (narrower: spokes taper outwards)
            a = c + inner_half - 2 * inner_half * s / steps
            outline.append((r_in * math.cos(a), r_in * math.sin(a)))
        outline = _rounded(outline, 0.26 * K, 3)
        top = [bm.verts.new((x, 6.0 * K, z)) for (x, z) in outline]
        bot = [bm.verts.new((x, -1.5 * K, z)) for (x, z) in outline]
        n = len(outline)
        bm.faces.new(top)
        bm.faces.new(list(reversed(bot)))
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((top[i], bot[i], bot[j], top[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def axle_mesh(name, length):
    """Heavy-duty octagonal axle (3.24 mm across flats / Ø 3.51 mm corners) along Y, flats top and bottom
    so it prints lying down with 45 degree sides and 100% bed contact."""
    r = AXLE_FLATS / 2 / math.cos(math.pi / 8)
    ring = [(r * math.cos(math.pi / 8 + k * math.pi / 4), r * math.sin(math.pi / 8 + k * math.pi / 4)) for k in range(8)]
    bm = bmesh.new()
    a = [bm.verts.new((x, -length / 2, z)) for (x, z) in ring]
    b = [bm.verts.new((x, length / 2, z)) for (x, z) in ring]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(8):
        j = (i + 1) % 8
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


# ---------------------------------------------------------------- front RC kingpin steering

KP_X = 792.0        # kingpin X (real mm, matches body.FRONT_AXLE_X)
KP_Y = 596.0        # kingpin |Y| (real mm, inboard of front tire inner sidewall)
ARM_X = 728.0       # steering arm ball/pin X (real mm, ahead of kingpin inside BayTub arch)
ARM_Y = 596.0       # steering arm ball/pin |Y| (real mm, parallel 4-bar linkage with KP_Y)


def _oct_stub(name, x_c, z_c, y0, y1):
    """Heavy-duty octagonal stub axle along Y from y0 to y1 (real mm), centred on (x_c, z_c) (real mm)."""
    r = AXLE_FLATS / 2 / math.cos(math.pi / 8)
    ring = [(x_c * SCALE + r * math.cos(math.pi / 8 + k * math.pi / 4),
             z_c * SCALE + r * math.sin(math.pi / 8 + k * math.pi / 4)) for k in range(8)]
    bm = bmesh.new()
    ya, yb = min(y0, y1) * SCALE, max(y0, y1) * SCALE
    a = [bm.verts.new((x, ya, z)) for (x, z) in ring]
    b = [bm.verts.new((x, yb, z)) for (x, z) in ring]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(8):
        j = (i + 1) % 8
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def knuckle_parts(side):
    """(knuckle, unions, cuts, pivot_world) for side = -1 (L) or +1 (R).
    Flat underside at Z = WHEEL_RADIUS*SCALE - AXLE_FLATS/2 (14.88 mm / 297.6 real mm) so the base,
    thickened kingpin barrel (r = 36.0 real mm), root hub collar (|Y| = 626..676 real mm), and 3.24 mm
    octagonal stub axle are 100% coplanar on the print bed with 0 supports and 0 floating islands."""
    from mathutils import Vector
    import features as F
    tag = "L" if side < 0 else "R"
    s = side
    z_bot = WHEEL_RADIUS * SCALE - AXLE_FLATS / 2
    # Plan outline of the reinforced base plate + forward steering arm + hub root collar
    pts = [
        (KP_X - 36.0, s * (KP_Y + 80.0)),
        (KP_X + 36.0, s * (KP_Y + 80.0)),
        (KP_X + 36.0, s * (KP_Y - 24.0)),
        (ARM_X - 20.0, s * (ARM_Y - 20.0)),
        (ARM_X - 20.0, s * (ARM_Y + 22.0)),
    ]
    poly = F.rounded_poly(pts, [10.0, 10.0, 14.0, 16.0, 16.0], steps=6)
    if s < 0:
        poly = list(reversed(poly))
    base = F.prism_cutter(f"Knuckle_{tag}", "+Z", poly, z_bot, 344.0 * SCALE)
    barrel = F.prism_cutter(f"Knuckle_{tag}_Barrel", "+Z",
                            F.circle(KP_X, s * KP_Y, 36.0, 32), z_bot, 386.0 * SCALE)
    c_ya, c_yb = sorted((s * 626.0, s * 676.0))
    collar_pts = [
        (KP_X - 36.0, c_ya), (KP_X + 36.0, c_ya),
        (KP_X + 36.0, c_yb), (KP_X - 36.0, c_yb),
    ]
    collar = F.prism_cutter(f"Knuckle_{tag}_HubCollar", "+Z",
                            F.rounded_poly(collar_pts, 8.0, steps=4), z_bot, 372.0 * SCALE)
    pin = F.prism_cutter(f"Knuckle_{tag}_Pin", "+Z",
                         F.circle(ARM_X, s * ARM_Y, 12.0, 24), 338.0 * SCALE, 386.0 * SCALE)
    stub = _oct_stub(f"Knuckle_{tag}_Stub", KP_X, WHEEL_RADIUS, s * (KP_Y + 18.0), s * 854.4)
    bore = F.prism_cutter(f"Knuckle_{tag}_Bore", "+Z",
                          F.circle(KP_X, s * KP_Y, 20.5, 32), z_bot - 0.5, 395.0 * SCALE)
    pivot = Vector((KP_X * SCALE, s * KP_Y * SCALE, WHEEL_RADIUS * SCALE))
    return base, [barrel, collar, pin, stub], [bore], pivot


def set_knuckle_pivot(knuckle, pieces, pivot, riders=()):
    """Place the knuckle's origin on its vertical kingpin axis and parent its boolean pieces and wheel/tire riders."""
    from mathutils import Matrix
    knuckle.data.transform(Matrix.Translation(-pivot))
    knuckle.location = pivot
    bpy.context.view_layer.update()
    for p in pieces:
        p.parent = knuckle
        p.matrix_parent_inverse = knuckle.matrix_world.inverted()
    for r in riders:
        m = r.matrix_world.copy()
        r.parent = knuckle
        r.matrix_parent_inverse = knuckle.matrix_world.inverted()
        r.matrix_world = m


def steering_link_part():
    """(link, unions, cuts) for the transverse tie-rod connecting Knuckle_L and Knuckle_R
    to the front micro servo horn at (X = 674..754, Y = 0, Z = 350..386 real mm)."""
    import features as F
    z0, z1 = 350.0 * SCALE, 386.0 * SCALE
    pts = [
        (ARM_X - 26.0, -(ARM_Y + 28.0)),
        (ARM_X - 26.0, -56.0),
        (674.0, -44.0),
        (674.0, 44.0),
        (ARM_X - 26.0, 56.0),
        (ARM_X - 26.0, ARM_Y + 28.0),
        (ARM_X + 26.0, ARM_Y + 28.0),
        (ARM_X + 26.0, -(ARM_Y + 28.0)),
    ]
    poly = F.rounded_poly(pts, [16.0, 10.0, 12.0, 12.0, 10.0, 16.0, 16.0, 16.0], steps=6)
    link = F.prism_cutter("SteeringLink", "+Z", poly, z0, z1)
    cuts = []
    for s, tag in ((-1, "L"), (1, "R")):
        slot = F.rounded_poly([
            (ARM_X - 15.0, s * ARM_Y - 15.5),
            (ARM_X + 17.0, s * ARM_Y - 15.5),
            (ARM_X + 17.0, s * ARM_Y + 15.5),
            (ARM_X - 15.0, s * ARM_Y + 15.5),
        ], 14.5, steps=8)
        cuts.append(F.prism_cutter(f"SteeringLink_Slot{tag}", "+Z", slot, z0 - 0.5, z1 + 0.5))
    horn_slot = F.rounded_poly([
        (688.0, -18.0), (728.0, -18.0), (728.0, 18.0), (688.0, 18.0)
    ], 17.0, steps=8)
    cuts.append(F.prism_cutter("SteeringLink_HornSlot", "+Z", horn_slot, z0 - 0.5, z1 + 0.5))
    return link, [], cuts

