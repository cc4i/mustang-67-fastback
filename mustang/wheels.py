"""Printable 5-spoke rims and tires (print millimetres, axis along Y).

Assembly: a printed octagonal axle (2.3 mm across flats) presses into the rim hub and
spins freely in the chassis boss; the tire presses over the rim.
"""
import math

import bmesh
import bpy

from body import SCALE, WHEEL_RADIUS

TIRE_R = WHEEL_RADIUS * SCALE          # 13.75
TIRE_W = 9.0                           # wide radials, filling the arches as on the car
TIRE_OFFSET = -0.45                    # tire sits inboard of the rim lip
RIM_R = 8.0                            # rim seat radius
RIM_LIP_R = 8.9                        # chrome lip, seated in the tire's outer bead
RIM_W = 3.85                           # rim half width
RIM_LIP_START = RIM_W - 1.0            # rim-local y where the tire seat ends and the lip flares out
FIT_GAP = 0.1                          # tire bore clearance over the rim
AXLE_FLATS = 2.3                       # printed octagonal axle, across flats
HUB_HOLE_R = 2.45 / 2                  # octagon corners (2.49) bite into this: press fit
SPOKES = 5


def _revolve(profile, name, segments=96):
    """Revolve a closed (r, y) profile around the Y axis into a mesh."""
    bm = bmesh.new()
    rings = []
    for k in range(segments):
        a = 2 * math.pi * k / segments
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * ca, y, r * sa)) for (r, y) in profile])
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
    R = TIRE_R
    # The tire is wider than the rim: its outer bead is a pocket the rim's flared lip seats in (the
    # bore steps out to the lip radius before the lip starts), so it slides on from the inboard side
    # and the lip sits flush in the sidewall. Outer face +Y; a flat tread with three narrow, crisp
    # grooves and tight shoulders, so it reads as a flat radial, not a stack of rounded ribs.
    bead = RIM_LIP_R + FIT_GAP
    lip_start = RIM_LIP_START - 0.1 - o            # tire-local y where the lip begins to flare, less a margin
    pts = [
        (ri, -w + 0.6), (ri, lip_start),        # bore on the rim seat
        (bead, lip_start), (bead, w - 0.25),    # bead pocket round the lip
        (bead + 0.5, w), (R - 0.9, w),          # outer sidewall
        (R, w - 0.7),
        (R, 1.75), (R - 0.3, 1.65), (R - 0.3, 1.35), (R, 1.25),
        (R, 0.25), (R - 0.3, 0.15), (R - 0.3, -0.15), (R, -0.25),
        (R, -1.25), (R - 0.3, -1.35), (R - 0.3, -1.65), (R, -1.75),
        (R, -w + 0.7), (R - 0.9, -w),
        (ri + 0.9, -w),
    ]
    pts = [(r, y + o) for (r, y) in pts]
    return _revolve(_rounded(pts, 0.12, 3), name)


def rim_blank_mesh(name="Rim"):
    w = RIM_W
    # +Y is the outer face. Lip proud of the tire, dished face, hub boss.
    pts = [
        (HUB_HOLE_R, -w + 0.6),
        (HUB_HOLE_R, w - 0.3),
        (2.2, w - 0.3),                 # hub cap face
        (2.6, w - 0.9),
        (3.2, w - 1.4),                 # dish
        (RIM_R - 1.0, w - 1.4),
        (RIM_R - 0.5, w - 0.4),
        (RIM_LIP_R - 0.3, w + 0.2),     # lip edge, flush with the tire's outer face
        (RIM_LIP_R, w - 0.3),
        (RIM_LIP_R, w - 0.8),
        (RIM_R, RIM_LIP_START),         # tire seat
        (RIM_R, -w + 0.5),
        (RIM_R - 0.8, -w),
        (3.0, -w),                      # back face
        (2.0, -w + 0.6),
    ]
    return _revolve(_rounded(pts, 0.25, 3), name)


def spoke_cutter_mesh(name="RimCutter"):
    """Five window prisms between the spokes, extruded along Y through the dish."""
    bm = bmesh.new()
    r_in, r_out = 3.4, RIM_R - 1.25
    half_gap = math.radians(36 - 13.0)  # spokes ~26 deg wide, broad like the car's
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
        top = [bm.verts.new((x, 5.0, z)) for (x, z) in outline]
        bot = [bm.verts.new((x, -1.0, z)) for (x, z) in outline]
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
    """Octagonal axle along Y, flats top and bottom so it prints lying down with 45 degree sides."""
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
