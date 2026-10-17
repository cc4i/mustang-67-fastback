"""Cutters that follow the curved body surface (window recesses, scoops, louvers)
and simple prism cutters (grille, lamps, peg holes).

Outlines are authored in real-car millimetres in a projection plane and scaled
by SCALE. A surface cutter is a thin solid hugging the body: the outline is
ray-cast onto the body along the projection axis, then offset `out` outside
and `depth` inside the surface.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from body import SCALE

# projection axis -> (axis vector pointing INTO the body, function (u, v, w) -> xyz)
AXES = {
    # side views, u = x, v = z
    "+Y": (Vector((0, -1, 0)), lambda u, v, w: Vector((u, w, v))),   # right side (y > 0)
    "-Y": (Vector((0, 1, 0)), lambda u, v, w: Vector((u, -w, v))),   # left side (y < 0)
    # top view, u = x, v = y
    "+Z": (Vector((0, 0, -1)), lambda u, v, w: Vector((u, v, w))),
    # front / rear views, u = y, v = z
    "-X": (Vector((1, 0, 0)), lambda u, v, w: Vector((-w, u, v))),
    "+X": (Vector((-1, 0, 0)), lambda u, v, w: Vector((w, u, v))),
}


def resample(outline, step):
    """Densify a closed polyline so no segment is longer than `step`."""
    out = []
    n = len(outline)
    for i in range(n):
        a, b = outline[i], outline[(i + 1) % n]
        seg = math.dist(a, b)
        k = max(1, int(math.ceil(seg / step)))
        for s in range(k):
            t = s / k
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def rounded_poly(points, radius, steps=6):
    """Fillet the corners of a closed polygon (real mm)."""
    out = []
    n = len(points)
    for i in range(n):
        p0, p1, p2 = Vector(points[i - 1]), Vector(points[i]), Vector(points[(i + 1) % n])
        r = radius[i] if isinstance(radius, (list, tuple)) else radius
        if r <= 0:
            out.append(tuple(p1))
            continue
        d0, d2 = (p0 - p1), (p2 - p1)
        rr = min(r, d0.length * 0.49, d2.length * 0.49)
        a = p1 + d0.normalized() * rr
        b = p1 + d2.normalized() * rr
        for s in range(steps + 1):
            t = s / steps
            q = (1 - t) ** 2 * a + 2 * (1 - t) * t * p1 + t * t * b
            out.append((q.x, q.y))
    return out


def _bvh(target_mesh):
    bm = bmesh.new()
    bm.from_mesh(target_mesh)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def surface_cutter(name, target_mesh, axis, outline_real, depth, out=1.0, rings=6,
                   depth_fn=None, tree=None):
    """Recess cutter hugging the target surface inside `outline_real`.

    depth_fn(u_real, v_real) -> depth multiplier (0..1) lets a recess fade out.
    """
    def lo(u, v):
        return -depth * (depth_fn(u, v) if depth_fn else 1.0)
    return surface_solid(name, target_mesh, axis, outline_real, lo, lambda u, v: out, rings, tree)


def surface_solid(name, target_mesh, axis, outline_real, lo_fn, hi_fn, rings=6, tree=None, step=0.5):
    """Solid between two offsets of the target surface inside `outline_real`.

    lo_fn/hi_fn(u_real, v_real) give print-mm offsets along the outward surface direction
    (negative = inside the body). Used for recess cutters and for parts that sit on the body.
    """
    tree = tree or _bvh(target_mesh)
    into, to3d = AXES[axis]
    pts = resample([(u * SCALE, v * SCALE) for (u, v) in outline_real], step)
    cu = sum(p[0] for p in pts) / len(pts)
    cv = sum(p[1] for p in pts) / len(pts)
    far = 300.0

    def project(u, v):
        origin = to3d(u, v, far)
        hit, *_ = tree.ray_cast(origin, into, 2 * far)
        if hit is None:
            raise ValueError(f"{name}: outline point ({u / SCALE:.0f}, {v / SCALE:.0f}) misses the body")
        ur, vr = u / SCALE, v / SCALE
        return hit - into * hi_fn(ur, vr), hit - into * lo_fn(ur, vr)

    bm = bmesh.new()
    grid = []  # rings from centre (k=1) to outline (k=rings)
    for k in range(1, rings + 1):
        t = k / rings
        grid.append([(cu + (u - cu) * t, cv + (v - cv) * t) for (u, v) in pts])
    top_c, bot_c = project(cu, cv)
    vt_c, vb_c = bm.verts.new(top_c), bm.verts.new(bot_c)
    top, bot = [], []
    for ring in grid:
        tr, br = [], []
        for (u, v) in ring:
            a, b = project(u, v)
            tr.append(bm.verts.new(a))
            br.append(bm.verts.new(b))
        top.append(tr)
        bot.append(br)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vt_c, top[0][i], top[0][j]))
        bm.faces.new((vb_c, bot[0][j], bot[0][i]))
        for k in range(rings - 1):
            bm.faces.new((top[k][i], top[k + 1][i], top[k + 1][j], top[k][j]))
            bm.faces.new((bot[k][j], bot[k + 1][j], bot[k + 1][i], bot[k][i]))
        bm.faces.new((top[-1][i], bot[-1][i], bot[-1][j], top[-1][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def prism_cutter(name, axis, outline_real, w0, w1):
    """Straight extrusion of an outline along the projection axis between depths w0..w1 (print mm,
    measured as the coordinate along the axis's outward direction)."""
    return loft_solid(name, axis, [(outline_real, w0), (outline_real, w1)])


def loft_solid(name, axis, sections):
    """Solid lofted through [(outline_real, w), ...] sections (equal point counts) along an axis.

    Lets a pocket flare, e.g. a headlight bucket wider at the body face than at its floor."""
    _, to3d = AXES[axis]
    bm = bmesh.new()
    rings = [[bm.verts.new(to3d(u * SCALE, v * SCALE, w)) for (u, v) in outline] for outline, w in sections]
    n = len(rings[0])
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def circle(cx, cy, r, steps=32):
    return [(cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


# ---------------------------------------------------------------- lettering and tubes

LETTER_FONT = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"   # heavy flared serif, like the Cobra script


def text_solid(name, text, cap_height, raise_mm, origin, x_dir, y_dir, embed=0.15, font=LETTER_FONT, width=None,
               bold=0.0, center=False):
    """Raised lettering as a watertight solid (real-mm placement, print-mm relief).

    The text runs along x_dir with letter tops toward y_dir; it stands raise_mm proud of the
    surface through `origin` (normal = x_dir x y_dir) and sinks `embed` mm into it. Optionally
    stretch it to `width` real mm, thicken its strokes (`bold`, a fraction of the letter size) and
    centre its outline on `origin` (otherwise the font's own alignment point is used)."""
    cu = bpy.data.curves.new(f"{name}_curve", 'FONT')
    cu.body, cu.font, cu.size, cu.extrude = text, bpy.data.fonts.load(font, check_existing=True), 1.0, 0.5
    cu.align_x, cu.align_y, cu.resolution_u = 'CENTER', 'CENTER', 4
    tmp = bpy.data.objects.new(f"{name}_tmp", cu)
    bpy.context.scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    if bold:
        me = _dilate(me, bold)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)        # glyph faces arrive unwelded
    xs, ys = [v.co.x for v in bm.verts], [v.co.y for v in bm.verts]
    k = cap_height * SCALE / (max(ys) - min(ys))
    kx = width * SCALE / (max(xs) - min(xs)) if width else k
    cx, cy = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) if center else (0.0, 0.0)
    X, Y = Vector(x_dir).normalized(), Vector(y_dir).normalized()
    Z = X.cross(Y)
    o = Vector(origin) * SCALE
    for v in bm.verts:
        lx, ly, lz = (v.co.x - cx) * kx, (v.co.y - cy) * k, (v.co.z + 0.5) * (raise_mm + embed) - embed
        v.co = o + X * lx + Y * ly + Z * lz
    outward(bm)
    out = bpy.data.meshes.new(name)
    bm.to_mesh(out)
    bm.free()
    return bpy.data.objects.new(name, out)


def _dilate(me, d):
    """Thicken glyph strokes by d (in the glyph plane): the union of the glyphs with copies shifted
    round a small octagon. (The font's own outline offset overlaps contours and is not manifold.)"""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    base = bpy.data.objects.new("_dilate", me)
    bpy.context.scene.collection.objects.link(base)
    temps = []
    for k in range(8):
        a = 2 * math.pi * k / 8
        sh = me.copy()
        sh.transform(Matrix.Translation((d * math.cos(a), d * math.sin(a), 0.0)))
        ob = bpy.data.objects.new("_dilate_k", sh)
        bpy.context.scene.collection.objects.link(ob)
        mod = base.modifiers.new(f"u{k}", 'BOOLEAN')
        mod.operation, mod.solver, mod.object = 'UNION', 'MANIFOLD', ob
        temps.append(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    for ob in temps + [base]:
        m = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(m)
    return out


def tube(name, points, r, segments=10, closed=False):
    """Watertight tube along a polyline (real mm), mitred at the bends, capped at the ends.

    The section frame is carried along by parallel transport, so the tube never twists, and at a
    bend only the direction in the bend plane is stretched (by 1 / cos of the half angle), as in a
    true mitre. r is one radius, or one per point (e.g. the ribs of a corrugated hose). A `closed`
    polyline is a loop (its first point not repeated): the tube joins up on itself, with no caps."""
    pts = [Vector(p) * SCALE for p in points]
    radii = [(r[i] if isinstance(r, (list, tuple)) else r) * SCALE for i in range(len(pts))]
    n = len(pts)
    dirs = [(pts[(i + 1) % n] - pts[i]).normalized() for i in range(n if closed else n - 1)]

    def tangent(i):
        """(direction, bend direction or None, mitre stretch) at point i."""
        if not closed and (i == 0 or i == n - 1):
            return (dirs[0] if i == 0 else dirs[-1]), None, 1.0
        t0, t1 = dirs[i - 1], dirs[i]
        t_new = (t0 + t1).normalized()
        if (t1 - t0).length > 1e-9:
            return t_new, (t1 - t0).normalized(), 1.0 / max(0.5, t_new.dot(t1))
        return t_new, None, 1.0

    t = tangent(0)[0]
    u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized()
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        t_new, bend, scale = tangent(i)
        u = t.rotation_difference(t_new) @ u
        u = (u - t_new * u.dot(t_new)).normalized()
        t = t_new
        w = t.cross(u)
        ring = []
        for k in range(segments):
            a = 2 * math.pi * k / segments
            o = (u * math.cos(a) + w * math.sin(a)) * radii[i]
            if bend is not None:
                o += bend * o.dot(bend) * (scale - 1.0)
            ring.append(bm.verts.new(p + o))
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(segments):
            j = (k + 1) % segments
            bm.faces.new((a[k], a[j], b[j], b[k]))
    if closed:          # the transported frame may come back rolled: join the last ring at the best match
        a, b = rings[-1], rings[0]
        off = min(range(segments), key=lambda o: sum((a[k].co - b[(k + o) % segments].co).length for k in range(segments)))
        for k in range(segments):
            j = (k + 1) % segments
            bm.faces.new((a[k], a[j], b[(j + off) % segments], b[(k + off) % segments]))
    else:
        bm.faces.new(rings[0])
        bm.faces.new(list(reversed(rings[-1])))
    outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def outward(bm):
    """Consistent, outward-facing normals: recalc can pick the inside-out orientation for
    mirrored placements, so check the signed volume and flip if needed."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bm.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)


def surface_strip(name, tree, axis, centerline, width, lo, hi, closed=False, square=False):
    """Band of constant width (real mm) along a polyline drawn in the axis's projection plane,
    hugging the surface between lo..hi print-mm offsets along the outward axis (negative =
    inside). Unlike surface_solid it handles any shape of path (a U, a closed loop), since it is
    swept rather than filled from a centre point. With square, where the band runs along u (level,
    in the side and rear views) its face is laid square to the axis across the band, the edge on
    the lower-lying skin raised to the other's height, fading out as the band turns to run along v:
    over a skin that rolls away it keeps an upright face instead of tipping with it."""
    into, to3d = AXES[axis]
    pts = [Vector(p) for p in centerline]
    n = len(pts)
    bm = bmesh.new()
    rings = []
    for i in range(n):
        a, b = (pts[i - 1], pts[(i + 1) % n]) if closed else (pts[max(0, i - 1)], pts[min(n - 1, i + 1)])
        t = (b - a).normalized()
        side_dir = Vector((-t.y, t.x)) * (width / 2)
        hits = []
        for q in (pts[i] + side_dir, pts[i] - side_dir):
            hit, *_ = tree.ray_cast(to3d(q.x * SCALE, q.y * SCALE, 300.0), into, 600.0)
            if hit is None:
                raise ValueError(f"{name}: strip point ({q.x:.0f}, {q.y:.0f}) misses the body")
            hits.append(hit)
        top = max(-h.dot(into) for h in hits)
        lift = [(top + h.dot(into)) * t.x ** 2 if square else 0.0 for h in hits]
        (a_top, a_bot), (b_top, b_bot) = [(h - into * (hi + dl), h - into * lo) for h, dl in zip(hits, lift)]
        rings.append([bm.verts.new(v) for v in (a_top, b_top, b_bot, a_bot)])
    for i in range(n if closed else n - 1):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    if not closed:
        bm.faces.new(rings[0])
        bm.faces.new(list(reversed(rings[-1])))
    outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def surface_ribbon(name, tree, path, lo, hi):
    """Band along a path [((x, y, z), (dx, dy, dz), width)] of real-mm points at the surface, each with
    its own outward cast direction and width (real mm), hugging the surface between lo..hi print-mm
    offsets along that direction (negative = inside). Like surface_strip, but the cast direction may
    turn along the path, so one band can run along a top, over a roll and on down a face, each section
    laid square to the surface where it is."""
    def cast(p, d):
        hit, *_ = tree.ray_cast(p + d * 4.0, -d, 8.0)
        if hit is None:
            q = p / SCALE
            raise ValueError(f"{name}: ribbon point ({q.x:.0f}, {q.y:.0f}, {q.z:.0f}) misses the body")
        return hit

    pts = [(cast(Vector(p) * SCALE, Vector(d).normalized()), Vector(d).normalized(), w) for p, d, w in path]
    n = len(pts)
    bm = bmesh.new()
    rings = []
    for i, (c, d, w) in enumerate(pts):
        t = (pts[min(n - 1, i + 1)][0] - pts[max(0, i - 1)][0]).normalized()
        side_dir = t.cross(d).normalized() * (w * SCALE / 2)
        ends = []
        for q in (c + side_dir, c - side_dir):
            hit = cast(q, d)
            ends.append((hit + d * hi, hit + d * lo))
        (a_top, a_bot), (b_top, b_bot) = ends
        rings.append([bm.verts.new(v) for v in (a_top, b_top, b_bot, a_bot)])
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def chaikin(points, iterations=2):
    """Corner-cutting smoothing of an open polyline; the end points stay put."""
    pts = [Vector(p) for p in points]
    for _ in range(iterations):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        out.append(pts[-1])
        pts = out
    return [tuple(p) for p in pts]


def offset_closed(outline, d):
    """Offset a closed polygon outward by d (inward if negative), mitring every vertex along the
    bisector of its two edges, so rounded corners next to long edges stay true arcs."""
    pts = [Vector(p) for i, p in enumerate(outline) if (Vector(p) - Vector(outline[i - 1])).length > 1e-9]
    area = sum(a.x * b.y - b.x * a.y for a, b in zip(pts, pts[1:] + pts[:1]))
    sign = 1.0 if area < 0 else -1.0          # clockwise: the left normal points outward
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        t0, t1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((-t0.y, t0.x)) * sign, Vector((-t1.y, t1.x)) * sign
        m = n0 + n1
        if m.length < 1e-6:                   # a hairpin: just push along the first edge's normal
            out.append(tuple(p1 + n0 * d))
            continue
        m.normalize()
        out.append(tuple(p1 + m * (d / max(0.25, m.dot(n0)))))
    return out
