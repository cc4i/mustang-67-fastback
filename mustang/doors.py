"""Opening doors.

Each door is cut out of the body shell: the body material between the outer skin and the flat
plane of the cabin's side wall, inside the door outline (the old shut lines, run up to the window
sill). It is built as a block intersected with the body's own skin mesh, so its outer surface is
exactly the body's, and it carries everything that sat on that part of the skin: the side-scoop
sculpting, the door handle and lock, and the mirror socket. The black door card (trim panel with
armrest, pull handle and window crank) glues to its flat inner face; it used to be part of the
interior tub, where it would have stood in the open doorway.

Real-car millimetres unless noted; SCALE converts to print mm.
"""
import math

import bpy
from mathutils import Matrix, Vector

import details
import features as F
import interior
from body import SCALE

SIDES = (-1, 1)
GAP = 6.0                       # visible gap round the door (0.25 mm print: printable clearance)
INNER_Y = 696.0                 # the door's flat inner face (the cabin side wall is at 690)
CUT_INNER_Y = 684.0             # the body opening reaches 6 mm into the cabin hollow: it crosses the curving
                                # greenhouse wall cleanly (closer, the two meet at a grazing angle and leave slivers)
BOTTOM_Z = 405.0                # top of the rocker moulding
TOP_OVERLAP = 3.0               # the opening's top edge runs 3 mm into the window opening above it
OPEN_DEG = 65.0                 # how far the doors swing open (renders, animation, collision sweep)
# Hinge: a vertical axis just inside the door's front end, ~50 mm under the skin. A piece of 1.75 mm
# filament glued into a blind hole in the sill is the pin; the door slides down onto it (a blind
# hole up its front end) and rides on a small bearing boss round it, which holds the door at its
# modelled height clear of the sill. It lifts off, and the pin length is not critical.
# With the axis this close under the skin the door's outer front corner hardly moves forward as it
# opens: a slightly wider front gap clears it. Its inner front corner is rounded about the axis so
# it clears the hinge pillar and the hood-hinge area as it swings in behind the fender.
HINGE_AXIS = (1660.0, 795.0)    # (x, |y|)
GAP_FRONT = 21.0                # the front shut line (0.88 mm print): >= 0.24 mm clearance through the swing
PIN_HOLE_R, DOOR_HOLE_R = 22.0, 24.0       # 1.83 mm glue fit in the sill, 2.0 mm running fit in the door
PIN_Z0, DOOR_HOLE_TOP = 320.0, 850.0       # the sill hole stays inside the rocker, above its roll-under
BOSS_R = 40.0                   # bearing boss round the pin on the sill, GAP high
SCUFF_Y1, SCUFF_DEPTH = 790.0, 2.5              # sill scuff plate: outer edge (the sill runs out to ~840), depth
REAR_RELIEF = 9.0               # the inner rear edge is bevelled this much: it swings back ~4.5 mm early on
CORNER_R = 99.0                 # door material stays within this radius of the axis where it swings inboard

CARD_T = 30.0                   # door card thickness (y 666..696)
CARD_X0 = details.BELTLINE_X0 + 6.0   # the card stays inside the cabin and the cleared beltline
CARD_Z0, CARD_TOP_GAP = BOTTOM_Z + 20.0, 2.5    # the card runs right up to the door's top window sill (top trim +1.0 caps at -1.5)
CARD_BAYS_X = ((1835.0, 2082.0), (2118.0, 2382.0), (2418.0, 2675.0))   # 3x2 mortise-and-tenon registration grid (x spans)
CARD_BAYS_Z = ((455.0, 652.0), (688.0, 860.0))                         # 2 rows separated by horizontal locating rail
BAY_Y_DOOR, PAD_Y_CARD = 712.5, 710.5   # mortise bay floor in Door (0.825 mm deep) and mating tenon pad on DoorCard (0.725 mm proud)
VENT_FRAME, VENT_T, VENT_PANE = 18.0, 1.25, 0.65  # vent window: chrome frame width (real), thickness, pane (print mm)
VENT_Z_IN, VENT_Z_OUT = -0.75, 0.50               # local z range in glass plane (print mm), centred on the door sill
TENON_DEPTH, TENON_CLEAR = 24.0, 2.4              # vent window bottom mounting tenon depth (1.20 mm print) and slot clearance
VENT_RAIL = 0.85                                  # print mm: the narrowest frame rail left over the door top (two nozzle lines)
VENT_POST, VENT_POST_W = (1970.0, 2090.0), 20.0   # the vent window's rear post: x at the door top and under the rail
                                                  # (it leans back ~25 deg), and its width
ARMREST = (2330.0, 2640.0, 640.0, 690.0, 70.0)    # x0, x1, z0, z1, depth inboard of the card
LATCH_Z = 700.0                 # the door latch's rotor, and the striker on the body's jamb facing it
ROLL, PLEAT = (60.0, 20.0), (40.0, 12.0)        # card padding: (height, proud) of the top roll and of each pleat
PLEATS, PLEAT_GROOVE = 2, 5.0
CRANK = ((2560.0, 728.0), (2480.0, 712.0))      # window crank: boss and knob (x, z)


def tag(side):
    return "L" if side < 0 else "R"


def axis(side):
    return "+Y" if side > 0 else "-Y"


def _edge_x(edge, z):
    """x on a shut line ((x0, z0), (x1, z1)) at height z (the line extended past its ends)."""
    (x0, z0), (x1, z1) = edge
    return x0 + (x1 - x0) * (z - z0) / (z1 - z0)


def top_z(x):
    """Top of the door opening: the window sill line (plus the overlap into the window opening)."""
    return details.greenhouse_band(x)[0] + TOP_OVERLAP


def _top_corner(edge):
    """Where a shut line meets the sill line (real mm)."""
    z = top_z(_edge_x(edge, 900.0))
    for _ in range(8):
        z = top_z(_edge_x(edge, z))
    return _edge_x(edge, z), z


def outline(inset=0.0, front_extra=0.0):
    """Side-view door outline (x, z), inset by `inset` real mm (the door part is inset by GAP),
    its front edge a further `front_extra` back (the wider front gap)."""
    front = tuple((x + front_extra, z) for x, z in details.DOOR_FRONT)
    xf_top, zf_top = _top_corner(front)
    xr_top, zr_top = _top_corner(details.DOOR_REAR)
    pts = [(_edge_x(front, BOTTOM_Z), BOTTOM_Z), (_edge_x(details.DOOR_REAR, BOTTOM_Z), BOTTOM_Z), (xr_top, zr_top)]
    n = 24
    top = [(xr_top + (xf_top - xr_top) * k / n, top_z(xr_top + (xf_top - xr_top) * k / n)) for k in range(1, n)]
    pts += top + [(xf_top, zf_top)]
    radii = [25.0, 25.0, 12.0] + [0.0] * len(top) + [12.0]
    if inset:                     # offset the sharp outline, then round it: exact inner corners
        pts = F.offset_closed(pts, -inset)
        radii = [max(3.0, r - inset) if r else 0.0 for r in radii]
    return F.rounded_poly(pts, radii)


def body_parts():
    """Body booleans for the doors, in order: (opening and scuff-plate cuts, bearing-boss unions, pin-hole cuts)."""
    x, y = HINGE_AXIS
    openings, bosses, pins = [], [], []
    for s in SIDES:
        t = tag(s)
        openings.append(F.prism_cutter(f"Cut_DoorOpen_{t}", axis(s), outline(), CUT_INNER_Y * SCALE, 1000.0 * SCALE))
        # chrome striker let into the rear jamb, facing the latch's rotor
        xs = _edge_x(details.DOOR_REAR, LATCH_Z)
        openings.append(F.prism_cutter(f"Cut_Striker_{t}", "+Z", details.rect(xs - 10.0, s * 708.0, xs + 3.0, s * 742.0, 4),
                                       (LATCH_Z - 20.0) * SCALE, (LATCH_Z + 20.0) * SCALE))
        # aluminium scuff plate let into the sill under the door, behind the hinge boss
        x0, x1 = x + BOSS_R + 15.0, _edge_x(details.DOOR_REAR, BOTTOM_Z) - 15.0
        openings.append(F.prism_cutter(f"Cut_ScuffPlate_{t}", "+Z", details.rect(x0, s * (CUT_INNER_Y - 5.0), x1, s * SCUFF_Y1, 0),
                                       (BOTTOM_Z - SCUFF_DEPTH) * SCALE, (BOTTOM_Z + 20.0) * SCALE))
        bosses.append(F.prism_cutter(f"DoorBoss_{t}", "+Z", F.circle(x, s * y, BOSS_R, 32), (BOTTOM_Z - 5.0) * SCALE,
                                     (BOTTOM_Z + GAP) * SCALE))
        pins.append(F.prism_cutter(f"Cut_DoorPin_{t}", "+Z", F.circle(x, s * y, PIN_HOLE_R, 24), PIN_Z0 * SCALE,
                                   (BOTTOM_Z + GAP + 5.0) * SCALE))
    return openings, bosses, pins


def _corner_trim(side):
    """Top-view outline of the door material to remove at its inner front corner: everything beyond
    CORNER_R from the axis over the directions that swing inboard (forward round to inboard)."""
    x, y = HINGE_AXIS
    cy = side * y
    arc = [math.radians(a) for a in [180.0 + 95.0 * k / 16 for k in range(17)]]
    inner = [(x + CORNER_R * math.cos(a), cy + side * CORNER_R * math.sin(a)) for a in arc]
    outer = [(x + 300.0 * math.cos(a), cy + side * 300.0 * math.sin(a)) for a in reversed(arc)]
    return inner + outer


def _rear_relief(side):
    """Loft (top-view sections at the bottom and top of the door) bevelling the door's inner rear
    edge, which swings rearward a little in the first few degrees before moving clear."""
    _x, ay = HINGE_AXIS
    secs = []
    for z in (BOTTOM_Z - 20.0, 1000.0):
        xd = _edge_x(details.DOOR_REAR, z) - GAP
        poly = [(xd - REAR_RELIEF * (ay - y) / (ay - INNER_Y), side * y) for y in (INNER_Y - 10.0, ay)]
        poly += [(xd + 60.0, side * ay), (xd + 60.0, side * (INNER_Y - 10.0))]
        secs.append((poly, z * SCALE))
    return secs


def _vent_plane(tree, side):
    """Return (q1, ux, up, nz, fb, ft, xb, xt) defining the vent window's glass plane on `side`."""
    ax = axis(side)
    door_top = lambda x: top_z(x) - GAP
    rail = lambda x: details.rail_z(x) - GAP
    fb, ft = details.pillar_meets(door_top, GAP), details.pillar_meets(rail, GAP)
    xb, xt = VENT_POST

    def hit(x, z):
        return Vector((x, details.hit_w(tree, ax, x, z) / SCALE * side, z))

    q1, q2, q3 = hit(fb.x + 25.0, fb.y + 20.0), hit(xb - 10.0, fb.y + 20.0), hit(xt - 25.0, ft.y - 20.0)
    nz = (q2 - q1).cross(q3 - q1).normalized()
    if nz.y * side < 0:
        nz = -nz
    up = (Vector((0, 0, 1)) - nz * nz.z).normalized()
    ux = up.cross(nz)
    return q1, ux, up, nz, fb, ft, xb, xt


def _vent_y_bounds(q1, nz, x, z):
    """Return (|y_in|, |y_out|) in real mm of the DoorVent frame at side-view (x, z)."""
    y_mid = abs(q1.y - (nz.x * (x - q1.x) + nz.z * (z - q1.z)) / nz.y)
    return y_mid + (VENT_Z_IN / SCALE) / abs(nz.y), y_mid + (VENT_Z_OUT / SCALE) / abs(nz.y)


def _frustum_y(name, side, x0, z0, x1, z1, y0, y1, bevel):
    """8-vertex hexahedral frustum along Y (real mm coordinates scaled by SCALE), tapering inward by `bevel` from y0 to y1."""
    import bmesh
    bm = bmesh.new()
    quad0 = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    quad1 = [(x0 + bevel, z0 + bevel), (x1 - bevel, z0 + bevel),
             (x1 - bevel, z1 - bevel), (x0 + bevel, z1 - bevel)]
    v0 = [bm.verts.new((x * SCALE, side * y0 * SCALE, z * SCALE)) for x, z in quad0]
    v1 = [bm.verts.new((x * SCALE, side * y1 * SCALE, z * SCALE)) for x, z in quad1]
    bm.faces.new(v0)
    bm.faces.new(list(reversed(v1)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _door_vent_slot(name, side, q1, nz, x0, x1, z_drop):
    """Mortise slot cutter in the top sill of Door for the outboard side of DoorVent's tenon,
    with 45-deg lower and end ramps down to INNER_Y so Door prints with zero floating starts."""
    import bmesh
    door_top = lambda x: top_z(x) - GAP
    y_in = INNER_Y - 2.0
    xs = [x0 + (x1 - x0) * k / 8 for k in range(9)]
    bm = bmesh.new()
    rings = []
    for i, x in enumerate(xs):
        zt = door_top(x)
        zb = zt - z_drop
        _, vy_out = _vent_y_bounds(q1, nz, x, zb)
        y_out = max(INNER_Y + 12.0, vy_out + TENON_CLEAR)
        ramp = y_out - y_in
        dx_in = -ramp if i == 0 else (ramp if i == len(xs) - 1 else 0.0)
        pts_in = [((x + dx_in) * SCALE, side * y_in * SCALE, (zb - ramp) * SCALE),
                  ((x + dx_in) * SCALE, side * y_in * SCALE, (zt + 15.0) * SCALE)]
        pts_out = [(x * SCALE, side * y_out * SCALE, zb * SCALE),
                   (x * SCALE, side * y_out * SCALE, (zt + 15.0) * SCALE)]
        ring = [bm.verts.new(pts_in[0]), bm.verts.new(pts_out[0]),
                bm.verts.new(pts_out[1]), bm.verts.new(pts_in[1])]
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(4):
            m = (k + 1) % 4
            bm.faces.new((a[k], a[m], b[m], b[k]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _card_vent_slot(name, side, q1, nz, x0, x1, z_drop):
    """Mortise slot cutter in the top edge of DoorCard for the inboard side of DoorVent's tenon,
    with 45-deg lower and end ramps out to PAD_Y_CARD so DoorCard prints with zero floating starts."""
    import bmesh
    door_top = lambda x: top_z(x) - GAP
    y_out = PAD_Y_CARD + 3.0
    xs = [x0 + (x1 - x0) * k / 8 for k in range(9)]
    bm = bmesh.new()
    rings = []
    for i, x in enumerate(xs):
        zt = door_top(x)
        zb = zt - z_drop
        vy_in_top, _ = _vent_y_bounds(q1, nz, x, zt + 2.0)
        vy_in_bot, _ = _vent_y_bounds(q1, nz, x, zb)
        y_in = min(INNER_Y - 12.0, min(vy_in_top, vy_in_bot) - TENON_CLEAR)
        ramp = y_out - y_in
        dx_out = -ramp if i == 0 else (ramp if i == len(xs) - 1 else 0.0)
        pts_out = [((x + dx_out) * SCALE, side * y_out * SCALE, (zb - ramp) * SCALE),
                   ((x + dx_out) * SCALE, side * y_out * SCALE, (zt + 15.0) * SCALE)]
        pts_in = [(x * SCALE, side * y_in * SCALE, zb * SCALE),
                  (x * SCALE, side * y_in * SCALE, (zt + 15.0) * SCALE)]
        ring = [bm.verts.new(pts_in[0]), bm.verts.new(pts_out[0]),
                bm.verts.new(pts_out[1]), bm.verts.new(pts_in[1])]
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(4):
            m = (k + 1) % 4
            bm.faces.new((a[k], a[m], b[m], b[k]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def door_parts(tree, body_mesh, body_ob):
    """[(door, intersect_with, pre_cuts, unions, post_cuts)] for both doors, modelled closed, in
    place. The skin intersect comes first, then the side-scoop sculpting, the handle, lock, and
    window-sill beltline chrome moulding, and last the mirror socket, the hinge (pin hole, rounded
    inner front corner, bevelled rear edge), the 3x2 mortise bays for the door card, the top
    window-sill mortise channel for the vent window tenon, and the shut-face details."""
    out = []
    slots = dict(details.mirror_slots(tree))
    xb0, xb1 = 1785.0, 2784.0
    belt_path = [(x, top_z(x) - GAP - 9.0) for x in (xb0 + (xb1 - xb0) * k / 24 for k in range(25))]
    for s in SIDES:
        t, ax = tag(s), axis(s)
        q1, _ux, _up, nz, fb, _ft, xb, _xt = _vent_plane(tree, s)
        tenon_x0, tenon_x1 = fb.x + 22.0, xb - 6.0
        door = F.prism_cutter(f"Door_{t}", ax, outline(GAP, GAP_FRONT - GAP), INNER_Y * SCALE, 1000.0 * SCALE)
        skin = bpy.data.objects.new(f"Door_{t}_Skin", body_ob.data)    # the body's own skin: exact continuity
        pre = [F.surface_cutter(f"DoorCove_{t}", body_mesh, ax, details.SCOOP_COVE, 1.35, depth_fn=details.cove_fade, tree=tree)]
        x0, z0, x1, z1 = details.DOOR_HANDLE
        unions = [F.surface_solid(f"DoorHandle_{t}", body_mesh, ax, details.rect(x0, z0, x1, z1, 12),
                                  lambda u, v: -0.4, lambda u, v: 0.4, rings=3, tree=tree, step=0.3),
                  F.surface_strip(f"DoorBeltTrim_{t}", tree, ax, belt_path, 17.0, -0.25, 0.25, square=True)]
        lx, lz, lr = details.DOOR_LOCK
        unions.append(F.surface_solid(f"DoorLock_{t}", body_mesh, ax, F.circle(lx, lz, lr, 16),
                                      lambda u, v: -0.4, lambda u, v: 0.3, rings=2, tree=tree, step=0.3))
        slot = slots.get(f"Cut_MirrorSlot_{t}")        # (only the doors that carry a mirror)
        if slot:
            slot.name = slot.data.name = f"DoorMirrorSlot_{t}"
        hx, hy = HINGE_AXIS
        bays = []
        idx = 0
        bevel_door = BAY_Y_DOOR - (INNER_Y - 2.0)
        for bx0, bx1 in CARD_BAYS_X:
            for bz0, bz1 in CARD_BAYS_Z:
                bays.append(_frustum_y(f"Door_{t}_CardBay{idx}", s, bx0, bz0, bx1, bz1,
                                       INNER_Y - 2.0, BAY_Y_DOOR, bevel_door))
                idx += 1
        vent_slot = _door_vent_slot(f"Door_{t}_VentSlot", s, q1, nz, tenon_x0 - 7.0, tenon_x1 + 7.0,
                                    TENON_DEPTH + TENON_CLEAR)
        post = ([slot] if slot else []) + [
                F.prism_cutter(f"DoorHinge_{t}_Hole", "+Z", F.circle(hx, s * hy, DOOR_HOLE_R, 24),
                               (BOTTOM_Z - 20.0) * SCALE, DOOR_HOLE_TOP * SCALE),
                F.prism_cutter(f"DoorHinge_{t}_Corner", "+Z", _corner_trim(s), (BOTTOM_Z - 20.0) * SCALE, 1000.0 * SCALE),
                F.loft_solid(f"DoorHinge_{t}_Rear", "+Z", _rear_relief(s)),
                vent_slot] + bays + shut_face_parts(s, tree)
        out.append((door, skin, pre, unions, post))
    return out


def card_parts(tree=None):
    """[(card, unions, cuts)] black door cards for the doors' inner faces (modelled closed, in place):
    keyed into the door's inner face by a 3x2 grid of 45-deg bevelled rear tenon pads (mating with
    Door_CardBay0..5) and a top window-sill U-channel slot that captures the vent window's tenon."""
    if tree is None:
        tree = F._bvh(bpy.data.objects["Body"].data)
    out = []
    for s in SIDES:
        t, ax = tag(s), axis(s)
        q1, _ux, _up, nz, fb, _ft, xb, _xt = _vent_plane(tree, s)
        tenon_x0, tenon_x1 = fb.x + 22.0, xb - 6.0
        y_out, y_in = INNER_Y - 1.5, INNER_Y - CARD_T
        xr = lambda z: _edge_x(details.DOOR_REAR, z) - GAP - 10.0
        card_top = lambda x: top_z(x) - GAP - CARD_TOP_GAP                   # follows the door's top edge
        xs = [CARD_X0 + (xr(card_top(2600.0)) - CARD_X0) * k / 12 for k in range(13)]
        profile = [(CARD_X0, CARD_Z0), (xr(CARD_Z0), CARD_Z0)] + [(x, card_top(x)) for x in reversed(xs)]
        card = F.prism_cutter(f"DoorCard_{t}", ax, profile, y_in * SCALE, y_out * SCALE)
        # chrome belt moulding along the card's top edge (forms the inner wall of the vent window U-channel)
        trim = [(x, card_top(x) - 18.0) for x in xs] + [(x, card_top(x) + 1.0) for x in reversed(xs)]
        unions = [F.prism_cutter(f"DoorCardTrim_{t}", ax, trim, (y_in - 8.0) * SCALE, (y_out - 0.5) * SCALE)]
        # 6 mating 45-deg bevelled tenon pads on the back of DoorCard
        idx = 0
        bevel_card = PAD_Y_CARD - (y_out - 2.5)
        for bx0, bx1 in CARD_BAYS_X:
            for bz0, bz1 in CARD_BAYS_Z:
                unions.append(_frustum_y(
                    f"DoorCard_{t}_Pad{idx}", s,
                    bx0 + 3.5, bz0 + 3.5, bx1 - 3.5, bz1 - 3.5,
                    y_out - 2.5, PAD_Y_CARD, bevel_card
                ))
                idx += 1
        # padded rolls along the panel behind the dash: the top roll under the moulding, then the pleats
        z_hi = -18.0
        for k, (h, proud) in enumerate([ROLL] + [PLEAT] * PLEATS):
            unions.append(_roll(f"DoorCard_{t}_Roll{k}", s, y_in, lambda x, dz=z_hi - h / 2: card_top(x) + dz, h, proud,
                                interior.DASH_FACE_X + 20.0, xr(card_top(2600.0) + z_hi - h) - 30.0))
            z_hi -= h + PLEAT_GROOVE
        # armrest: a short, fat pad (rounded toward the cabin and at its ends) on a chrome base
        ax0, ax1, az0, az1, depth = ARMREST

        def pad(f):
            yi, yo = s * (y_in - depth * f), s * (y_in + 5.0)
            zc, hh = (az0 + 12.0 + az1) / 2, (az1 - az0 - 12.0) / 2 * (0.55 + 0.45 * f)
            return F.rounded_poly([(yo, zc - hh), (yi, zc - hh), (yi, zc + hh), (yo, zc + hh)], [0.0, 8.0 * f, 25.0 * f, 0.0])
        ends = [(0.0, 0.35), (8.0, 0.7), (20.0, 0.9), (35.0, 1.0)]
        sections = [(pad(f), (ax0 + d) * SCALE) for d, f in ends] + [(pad(f), (ax1 - d) * SCALE) for d, f in reversed(ends)]
        unions.append(F.loft_solid(f"DoorCard_{t}_Armrest", "+X", sections))
        unions.append(F.prism_cutter(f"DoorCardTrim_{t}_Arm", ax, details.rect(ax0 - 15.0, az0, ax1 + 15.0, az0 + 12.5, 6),
                                     (y_in - depth + 3.0) * SCALE, (y_in + 5.0) * SCALE))
        # pull handle: a lever on a base plate
        unions.append(F.prism_cutter(f"DoorCardTrim_{t}_PullBase", ax, details.rect(2170.0, 705.0, 2320.0, 748.0, 12),
                                     (y_in - 5.0) * SCALE, (y_in + 5.0) * SCALE))
        unions.append(F.prism_cutter(f"DoorCardTrim_{t}_Pull", ax, details.line_band((2195.0, 722.0), (2305.0, 730.0), 18.0),
                                     (y_in - 15.0) * SCALE, (y_in - 3.0) * SCALE))
        # window crank: boss, arm lying along the panel, light knob
        (cx, cz), (kx, kz) = CRANK
        unions.append(interior._cylinder(f"DoorCardTrim_{t}_Crank", (cx, s * (y_in + 3.0), cz), (cx, s * (y_in - 16.0), cz), 16.0))
        unions.append(F.prism_cutter(f"DoorCardTrim_{t}_CrankArm", ax, details.line_band((cx, cz), (kx, kz), 12.0),
                                     (y_in - 13.0) * SCALE, (y_in + 3.0) * SCALE))
        unions.append(interior._cylinder(f"DoorCardKnob_{t}", (kx, s * (y_in - 10.0), kz), (kx, s * (y_in - 40.0), kz), 11.0))
        cuts = [_card_vent_slot(f"DoorCard_{t}_VentSlot", s, q1, nz, tenon_x0 - 7.0, tenon_x1 + 7.0,
                                TENON_DEPTH + TENON_CLEAR)]
        out.append((card, unions, cuts))
    return out


def _roll(name, side, y_face, z_mid, h, proud, x0, x1):
    """Padded roll on the card face (y_face, |y| real mm): an elliptical bulge `h` tall standing
    `proud` off the face, centred on z_mid(x), tapering round at both ends."""
    taper = [(0.0, 0.15), (8.0, 0.6), (20.0, 0.9), (40.0, 1.0)]
    stations = taper + [(x1 - x0 - d, f) for d, f in reversed(taper)]
    sections = []
    for d, f in stations:
        x = x0 + d
        hh = h * (0.6 + 0.4 * f) / 2
        arc = [(side * (y_face + 2.0 - (proud * f + 2.0) * math.sin(math.pi * k / 12)), z_mid(x) - hh * math.cos(math.pi * k / 12))
               for k in range(13)]
        sections.append((arc, x * SCALE))
    return F.loft_solid(name, "+X", sections)


def shut_face_parts(side, tree):
    """Details let into the door's rear (shut) face, flush so its gap stays printable: the chrome
    latch plate with two screws and its rotor's slot, the black seal along its inner edge, two rubber
    bumpers and the black glass-channel bracket at the top. Each is a shallow pocket whose floor
    takes the detail's colour (the face is bevelled: see _rear_relief). The striker it closes on
    is in body_parts."""
    t = tag(side)
    ay = HINGE_AXIS[1]
    xf = _edge_x(details.DOOR_REAR, LATCH_Z) - GAP - 2.0
    y_skin = details.hit_w(tree, axis(side), xf, LATCH_Z) / SCALE        # the face runs from INNER_Y out to the skin
    w = y_skin - INNER_Y

    def face_x(y, z):
        return _edge_x(details.DOOR_REAR, z) - GAP - REAR_RELIEF * (ay - min(y, ay)) / (ay - INNER_Y)

    def pocket(name, outline_yz, depth):
        """Prism into the face over a (|y|, z) outline, `depth` real mm deep."""
        import bmesh
        bm = bmesh.new()
        lo = [bm.verts.new(Vector((face_x(y, z) - depth, side * y, z)) * SCALE) for y, z in outline_yz]
        hi = [bm.verts.new(Vector((face_x(y, z) + 30.0, side * y, z)) * SCALE) for y, z in outline_yz]
        n = len(lo)
        bm.faces.new(lo)
        bm.faces.new(list(reversed(hi)))
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        F.outward(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        return bpy.data.objects.new(name, me)

    zl = LATCH_Z
    yl = INNER_Y + 0.25 * w                                     # the latch, clear of the seal along the inner edge
    top = top_z(2780.0) - GAP
    # the latch's rotor: a U-shaped slot open toward the inner edge, where the striker enters
    rotor = [(INNER_Y - 2.0, zl - 13.0)] + [(yl + 13.0 * math.cos(a), zl + 13.0 * math.sin(a))
                                           for a in (math.pi * (k / 10 - 0.5) for k in range(11))] + [(INNER_Y - 2.0, zl + 13.0)]
    parts = [pocket(f"DoorLatch_{t}", details.rect(yl - 24.0, zl - 55.0, yl + 24.0, zl + 35.0, 6), 3.0),
             pocket(f"DoorLatchRotor_{t}", rotor, 8.0),
             pocket(f"DoorSeal_{t}", details.rect(INNER_Y - 5.0, BOTTOM_Z + 25.0, INNER_Y + 9.0, top - 20.0, 0), 3.0),
             pocket(f"DoorBracket_{t}", details.rect(INNER_Y + 12.0, top - 120.0, INNER_Y + 0.45 * w, top - 12.0, 4), 2.5)]
    parts += [pocket(f"DoorLatchScrew_{t}{k}", F.circle(yl, z, 5.0, 12), 4.5) for k, z in enumerate((zl - 42.0, zl + 24.0))]
    for k, z in enumerate((top - 160.0, 470.0)):                # rubber bumpers in the outer third, high and low
        parts.append(pocket(f"DoorBumper_{t}{k}", details.rect(INNER_Y + 0.68 * w, z - 12.0, INNER_Y + 0.84 * w, z + 12.0, 4), 3.0))
    return parts


def riders(side):
    """Objects that swing with a door: its feature cutters, its card and the mirror (with theirs)."""
    t = tag(side)
    prefixes = (f"Door_{t}_", f"DoorCove_{t}", f"DoorHandle_{t}", f"DoorBeltTrim_{t}", f"DoorLock_{t}",
                f"DoorMirrorSlot_{t}", f"DoorCard_{t}", f"DoorCardTrim_{t}", f"DoorCardKnob_{t}", f"Mirror_{t}",
                f"DoorHinge_{t}", f"DoorVent_{t}", f"DoorVentPane_{t}", f"DoorLatch_{t}", f"DoorLatchRotor_{t}",
                f"DoorLatchScrew_{t}", f"DoorSeal_{t}", f"DoorBracket_{t}", f"DoorBumper_{t}")
    return [ob for ob in bpy.data.objects if ob.name.startswith(prefixes)]


def set_pivot(side):
    """Move the door's origin onto its hinge axis and parent everything that swings with it, so
    rotating the door about its local Z opens it (positive angles for the right door). Card and
    vent cutters are parented to DoorCard and DoorVent respectively so moving either sub-assembly
    carries its own boolean modifiers."""
    t = tag(side)
    door = bpy.data.objects[f"Door_{t}"]
    card = bpy.data.objects.get(f"DoorCard_{t}")
    vent = bpy.data.objects.get(f"DoorVent_{t}")
    x, y = HINGE_AXIS
    p = Vector((x, side * y, 0.0)) * SCALE
    door.data.transform(Matrix.Translation(-p))
    door.location = p
    bpy.context.view_layer.update()
    card_prefixes = (f"DoorCard_{t}_", f"DoorCardTrim_{t}", f"DoorCardKnob_{t}")
    vent_prefixes = (f"DoorVent_{t}_", f"DoorVentPane_{t}")
    for ob in riders(side):
        if card and ob != card and ob.name.startswith(card_prefixes):
            parent = card
        elif vent and ob != vent and ob.name.startswith(vent_prefixes):
            parent = vent
        else:
            parent = door
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()


def vent_parts(tree):
    """[(frame, cuts)] the vent windows: a flat chrome frame round a glass pane, standing on the
    front of each door's top edge in the greenhouse plane (so it swings with the door, as on the
    car) and anchored by an integrated full-length bottom mounting tenon that seats into the U-channel
    mortise slot shared by Door and DoorCard. Each is modelled flat in its own frame (local XY = the
    glass plane, +Z outward) and placed on the car, so it prints lying flat."""
    out = []
    door_top = lambda x: top_z(x) - GAP
    rail = lambda x: details.rail_z(x) - GAP
    fb, ft = details.pillar_meets(door_top, GAP), details.pillar_meets(rail, GAP)    # the front edge's ends, GAP behind the pillar
    fb_low = details.pillar_meets(lambda x: door_top(x) - TENON_DEPTH - 16.0, GAP)
    xb, xt = VENT_POST
    post = [Vector((xb, door_top(xb))), Vector((xt, rail(xt)))]
    # everything ahead of and above the opening's outline inset by GAP, from below the door top up
    # the pillar and back along the rail past the post (a simple polygon round the vent's corner)
    upper = [p for p in F.offset_closed(details.WINDOW_OPEN, -GAP)[:details.WINDOW_OPEN_UPPER] if p[0] < xt + 80.0]
    trim = [(upper[0][0] - 40.0, fb.y - 60.0)] + upper + [(xt + 80.0, upper[-1][1]), (xt + 80.0, ft.y + 300.0),
                                                         (fb.x - 400.0, ft.y + 300.0), (fb.x - 400.0, fb.y - 60.0)]
    for s in SIDES:
        t, ax = tag(s), axis(s)
        q1, ux, up, nz, fb, ft, xb, xt = _vent_plane(tree, s)

        def local(p):
            """Side-view point (x, z) carried along y onto the glass plane, in the plane's own (u, v)."""
            x, z = p
            w = Vector((x, q1.y - (nz.x * (x - q1.x) + nz.z * (z - q1.z)) / nz.y, z)) - q1
            return Vector((w.dot(ux) * SCALE, w.dot(up) * SCALE))
        # the outline: a long trapezoid under the rail, its top front corner rounded like the
        # opening's (in the side view), cut off behind by the post; the pane: the same inset by the
        # frame width (in the glass plane)
        corner = details.OPEN_CORNER_T - 2.5
        sharp_xz_pane = [tuple(fb), tuple(ft), tuple(ft + Vector((400.0, 0.0))), tuple(fb + Vector((400.0, 0.0)))]
        sharp_pane = [local(p) for p in sharp_xz_pane]
        sharp_xz_frame = [tuple(fb_low), tuple(ft), tuple(ft + Vector((400.0, 0.0))), tuple(fb_low + Vector((400.0, 0.0)))]
        pb, pt = local(post[0]), local(post[1])
        if (pt - pb).cross(sharp_pane[1] - pb) < 0:      # (the plane's u axis runs the other way on the left side)
            pb, pt = pt, pb                              # keep what lies ahead of the post: the left of pb -> pt
        # (its foot's front corner well rounded: the A-pillar's foot stands just inboard of it)
        outline_uv = _clip([tuple(local(p)) for p in F.rounded_poly(sharp_xz_frame, [18.0, corner, 0.0, 0.0])], pb, pt)
        inner = F.offset_closed([tuple(p) for p in sharp_pane], -VENT_FRAME * SCALE)
        n_post = Vector((pb.y - pt.y, pt.x - pb.x)).normalized() * VENT_POST_W * SCALE      # forward, off the post
        pane = _clip(F.rounded_poly(inner, [12.0 * SCALE, max(3.0, corner - VENT_FRAME * 0.4) * SCALE, 0.0, 0.0]),
                     pb + n_post, pt + n_post)
        # the foot is squared off along the door top below (the seat cut), and the frame leans with the
        # glass, so on its inner face the seat line rides higher by abs(VENT_Z_IN) * tan(lean): keep the pane
        # VENT_RAIL clear of the seat on both faces
        seat_xs = [fb.x - 60.0 + (xb + 60.0 - fb.x + 60.0) * k / 12 for k in range(13)]
        s0, s1 = local((seat_xs[0], door_top(seat_xs[0]))), local((seat_xs[-1], door_top(seat_xs[-1])))
        bulge = max(0.0, max((local((x, door_top(x))) - s0).cross(s1 - s0) / (s1 - s0).length * (1 if (s1 - s0).x < 0 else -1)
                             for x in seat_xs))
        lift = Vector((0.0, max(0.0, abs(VENT_Z_IN) * nz.z / up.z) + VENT_RAIL + bulge))
        sa, sb = s0 + lift, s1 + lift
        centre = sum((Vector(p) for p in pane), Vector((0.0, 0.0))) / len(pane)
        if (sb - sa).cross(centre - sa) < 0:
            sa, sb = sb, sa
        pane = _clip(pane, sa, sb)
        frame = _flat_prism(f"DoorVent_{t}", outline_uv, VENT_Z_IN, VENT_Z_OUT)
        z_mid = (VENT_Z_IN + VENT_Z_OUT) / 2
        r_half = VENT_PANE / 2
        panes = [_flat_prism(f"DoorVentPane_{t}{k}", pane, z0, z1)
                 for k, (z0, z1) in enumerate(((VENT_Z_IN - 1.0, z_mid - r_half), (z_mid + r_half, VENT_Z_OUT + 1.0)))]
        m = Matrix((ux, up, nz)).transposed().to_4x4()
        m.translation = q1 * SCALE
        for ob in [frame] + panes:
            ob.matrix_world = m
        # stepped seat profile with an integrated bottom mounting tenon over [tenon_x0, tenon_x1] that
        # drops into the shared Door + DoorCard window-sill U-channel
        tenon_x0, tenon_x1 = fb.x + 22.0, xb - 6.0
        txs = [tenon_x0 + (tenon_x1 - tenon_x0) * k / 8 for k in range(9)]
        seat_top = (
            [(fb.x - 60.0, door_top(fb.x - 60.0) + 1.0), (tenon_x0 - 3.0, door_top(tenon_x0 - 3.0) + 1.0)]
            + [(x, door_top(x) - TENON_DEPTH) for x in txs]
            + [(tenon_x1 + 3.0, door_top(tenon_x1 + 3.0) + 1.0), (xb + 60.0, door_top(xb + 60.0) + 1.0)]
        )
        seat = list(reversed(seat_top)) + [(fb.x - 60.0, fb.y - 300.0), (xb + 60.0, fb.y - 300.0)]
        panes.append(F.prism_cutter(f"DoorVent_{t}_Seat", ax, seat, 500.0 * SCALE, 1000.0 * SCALE))
        panes.append(F.prism_cutter(f"DoorVent_{t}_Trim", ax, trim, 500.0 * SCALE, 1000.0 * SCALE))
        out.append((frame, panes))
    return out


def _clip(poly, a, b):
    """The part of a closed polygon on the left of the directed line a -> b (Sutherland-Hodgman)."""
    def side(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    out = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(tuple(p))
        if (sp >= 0) != (sq >= 0):
            k = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k))
    return out


def _flat_prism(name, outline_uv, z0, z1):
    """Prism of a local (u, v) outline (print mm) between local z0..z1 (print mm)."""
    import bmesh
    bm = bmesh.new()
    lo = [bm.verts.new((u, v, z0)) for u, v in outline_uv]
    hi = [bm.verts.new((u, v, z1)) for u, v in outline_uv]
    n = len(lo)
    bm.faces.new(lo)
    bm.faces.new(list(reversed(hi)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)
