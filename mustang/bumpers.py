"""Wrap-around blade bumpers swept along the body contour (print millimetres).

The path is found by casting rays outward from a point inside the body at bumper
height, so the bumper follows the nose (or tail) and wraps back toward the wheel
arches. At every station the back face is ray-cast onto the body at each profile
height, so it hugs the raked valance with a constant gap. A bumper without a rise
has a flat top strip and prints upside down on it, guards up, with no supports (the
front one); the rear one sweeps up round the corners and prints upright on supports.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from body import SCALE

GAP = 0.16
# (height fraction 0 = bottom .. 1 = top, forward thickness mm), top first
PROFILE = [(1.0, 1.0), (0.93, 1.85), (0.80, 2.4), (0.50, 2.25), (0.18, 1.6), (0.0, 1.0)]
MIN_T = 1.0
END_FADE = 0.05     # fraction of the path over which the ends round off
TWIST = math.radians(6.0)   # quads folding more than this either way are split along their flatter diagonal
# a curling end fills the rows above the deepest out to its face from the bottom up; above the filled ones the
# face rolls back to the section's own over this fraction of them, so the top edge reads as a rolled lip (fully
# curled, the roll stays on the top rows: the lip never squares off)
CURL_ROLL = 0.4
# where the back has to stand off further (cast_dir) the rows thin, but never below their floor: the floor and the
# end's recede meet in smooth maxima over this width (print mm) rather than kinks, which shade as creases; and over
# the curl the face above the deepest row is relaxed across the rows (CURL_RELAX passes) so the rows pinned to their
# floor on the quarter extension's foot blend into the rolled face instead of standing out of it as a ridge
SOFT_FLOOR, CURL_RELAX = 0.12, 8
# the curl's rows above the deepest stand as a wall (on the quarter extension's foot they are all floor): no
# thinner than this (print mm) once fully curled, the top row's own 0.25 being an edge, not a wall
CURL_T = 0.36
# the curl's face is crowned (_crown) in over this much of its growth
CURL_CROWN = 0.25
# round the corner the body faces partly outboard by the ends, and a back following it would meet the flat end cap in
# an acute edge, a sliver of wall too thin to print; over this much of the path (print mm) the back stands off a
# little more towards the tip, so it meets the cap square (fully up to the deepest row, less and less over this many
# rows above it)
END_SQUARE, END_SQUARE_ROWS = 0.5, 4


def _smax(a, b, w):
    """Smooth maximum of a and b over width w (never below either)."""
    return (a + b + math.sqrt((a - b) * (a - b) + w * w)) / 2


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _refine_ends(path, length, step):
    """Where to put extra stations over `length` (print mm) at both ends of the path, every `step` at most: a rounded
    end turns within a few stations of the base step, which then show as facets. [(i, t)]: each station of the finer
    path lies t of the way from station i to station i + 1 of this one."""
    along = [0.0]
    for a, b in zip(path[:-1], path[1:]):
        along.append(along[-1] + (b - a).length)
    out = [(0, 0.0)]
    for i in range(1, len(path)):
        a, b = path[i - 1], path[i]
        if along[i - 1] < length or along[-1] - along[i] < length:
            k = max(1, math.ceil((b - a).length / step))
            out += [(i - 1, j / k) for j in range(1, k)]
        out.append((i, 0.0))
    return out


def _spline(seq, spots):
    """seq (points or numbers per station) at the finer stations `spots` (_refine_ends), on a Catmull-Rom spline."""
    n = len(seq)
    out = []
    for i, t in spots:
        if t == 0.0:
            out.append(seq[i])
            continue
        p0, p1, p2, p3 = seq[max(0, i - 1)], seq[i], seq[i + 1], seq[min(n - 1, i + 2)]
        t2, t3 = t * t, t * t * t
        out.append(p1 * (1 + (-3 * t2 + 2 * t3)) + p2 * (3 * t2 - 2 * t3) +
                   (p2 - p0) * (0.5 * (t - 2 * t2 + t3)) + (p3 - p1) * (0.5 * (t3 - t2)))
    return out


def _standoff(tree, s, n, gap):
    """How far along n to stand off the body point s so that the body is `gap` away along its own normal: standing
    off along a fixed direction, the gap closes to gap * cos where the body turns away from it (under a quarter
    extension's foot, round a corner turning to the side)."""
    g = gap
    for _ in range(8):
        _, nrm, _, d = tree.find_nearest(s + n * g)
        if d is None or d >= gap - 1e-4:
            break
        g += (gap - d) / max(0.2, abs(nrm.dot(n)))
    return g


def _soften(field, reach=3, passes=4):
    """A [station][row] field spread to the largest value within `reach` stations and a row either way, then
    smoothed: stand-offs found point by point on a faceted body are noisy, and the faces would show it."""
    n, m = len(field), len(field[0])
    out = [[max(field[a][b] for a in range(max(0, i - reach), min(n, i + reach + 1)) for b in range(max(0, r - 1), min(m, r + 2)))
            for r in range(m)] for i in range(n)]
    for _ in range(passes):
        out = [[(out[max(0, i - 1)][r] + out[min(n - 1, i + 1)][r] + out[i][max(0, r - 1)] + out[i][min(m - 1, r + 1)] + 4 * out[i][r]) / 8
                for r in range(m)] for i in range(n)]
    return out


def _crown(z, x):
    """x over the rising heights z raised to its least concave majorant: the section only ever bulges. Where rows
    pinned to their floors high up stand out past a face that has already rolled back below them, the face
    between runs straight across instead of dipping into a groove (which shades as lumps along the end)."""
    h = []
    for k in range(len(z)):
        while len(h) >= 2 and (z[h[-1]] - z[h[-2]]) * (x[k] - x[h[-2]]) >= (x[h[-1]] - x[h[-2]]) * (z[k] - z[h[-2]]):
            h.pop()
        h.append(k)
    out = []
    for a, b in zip(h[:-1], h[1:]):
        out += [x[a] + (x[b] - x[a]) * (z[k] - z[a]) / (z[b] - z[a]) for k in range(a, b)]
    return out + [x[h[-1]]]


def _fold(p, q, r, s):
    """Angle between the triangles (p, q, r) and (p, r, s) of the quad pqrs split along p-r."""
    return (q - p).cross(r - p).angle((r - p).cross(s - p), 0.0)


def contour(tree, center, z, theta0, theta1, samples=480, step=0.4):
    """Body contour at height z between two ray angles (radians, XY plane) around `center`."""
    pts = []
    for k in range(samples + 1):
        t = theta0 + (theta1 - theta0) * k / samples
        d = Vector((math.cos(t), math.sin(t), 0))
        hit, *_ = tree.ray_cast(Vector((center.x, center.y, z)), d, 200.0)
        if hit is not None:
            pts.append(hit)
    # resample by arc length, the step evened out so that both ends land where the rays stop (a symmetric
    # range gives a symmetric path)
    total = sum((b - a).length for a, b in zip(pts[:-1], pts[1:]))
    step = total / max(1, round(total / step))
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        seg = (b - a).length
        while acc + seg >= step:
            r = (step - acc) / seg
            a = a.lerp(b, r)
            seg = (b - a).length
            acc = 0.0
            out.append(a.copy())
        acc += seg
    if (out[-1] - pts[-1]).length > step / 2:   # rounding can stop the walk one step short of the end
        out.append(pts[-1].copy())
    return out


def sweep(name, tree, center, z0, z1, theta0, theta1, rise=None, profile=PROFILE, end_fade=END_FADE, end_height=0.35,
          min_t=MIN_T, smooth=6, bottom=None, end_gap=0.15, side_thin=False, step=0.4, path_smooth=0, side_ramp=None,
          cast_dir=None, curl=None, end_round=0.0, end_step=None, clear=None, face_rise=None):
    """Swept bumper solid. Returns (object, path, normals) so callers can attach guards.

    rise(p) (print mm, p = the path point) lifts the top edge, e.g. ends that sweep up round the
    corners; face_rise(p), if given, lifts the face (the rows up to the crease, the one above the thickest) only
    that much (no more than rise), the top above the crease taking up the rest: the crease can run on level and
    turn up late while the top already climbs. Over the last `end_fade` of the path the ends round off:
    thinner (no thinner than min_t) and shorter from below, down to `end_height` of the full height at the tips (the top
    edge stays put); with end_fade 0 the full section runs out to flat end faces. The points where the back
    face meets the body are smoothed along the path (`smooth` passes): where the body's plan shape
    changes with height, as round the tail corners, raw per-height hits twist the blade.
    bottom(p) raises the bottom edge (a rounded lower corner); end_gap stands the ends off the
    flank a little more; side_thin keeps the blade at min_t where it runs along a side, so the
    wrapped ends sit nearly flush with the quarter panels. path_smooth passes of smoothing on the plan
    path round a tight body corner into a radius, so the blade turns it instead of folding (the
    back face is still cast onto the body, so it keeps hugging it). With side_ramp (print mm) the
    side thinning starts where the path leaves the corner and ramps over that much of the side run,
    instead of following the normal's direction (which crowds it into a tight corner). With `cast_dir` (a
    unit vector) every row is cast onto the body and stands off it along that one direction instead of
    the path normal: round a corner the blade then keeps the body's plan shape pushed straight back,
    as the quarter extensions above it are, so its ends stay flush with them and with the flanks; the back
    then stands off further along it wherever the body turns away from it, keeping GAP along the body's normal
    from `clear` (the finished skin, if it moved after `tree` was taken; default tree).
    curl(p) (0..1) fills the rows above the deepest one out to its face, from the bottom up as it grows,
    with the face rolling back over CURL_ROLL of them above the filled ones: the face climbs, as at an end
    curling up, with a rounded lip on top instead of the face falling back into a hollow under it.
    end_round (print mm) rounds blunt ends off in plan on that radius, the whole section receding
    together so the face keeps its shape (a proportional fade would shift the rows against each other);
    over three times that length (reaching past where it begins, so the change of spacing sits on plain face) the
    stations come every end_step (default a quarter of step)."""
    zm = (z0 + z1) / 2
    path = contour(tree, center, zm, theta0, theta1, step=step)
    for _ in range(path_smooth):
        path = [path[0]] + [(path[i - 1] + path[i] * 2 + path[i + 1]) / 4 for i in range(1, len(path) - 1)] + [path[-1]]

    def plan_normals(path):
        out = []
        for i in range(len(path)):
            a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
            t = (b - a).normalized()
            n = Vector((t.y, -t.x, 0))
            out.append(-n if n.dot(path[i] - Vector((center.x, center.y, zm))) < 0 else n)
        return out
    n_st = len(path)
    normals = plan_normals(path)
    dirs = [cast_dir] * n_st if cast_dir is not None else normals

    rows = list(reversed(profile))              # bottom -> top
    deepest = max(range(len(rows)), key=lambda r: rows[r][1])
    fc = rows[deepest + 1][0] if face_rise else 1.0
    hits, fades = [], []
    for i, (p, n) in enumerate(zip(path, dirs)):
        frac = i / (n_st - 1)
        fade = min(1.0, frac / end_fade, (1 - frac) / end_fade) ** 0.5 if end_fade else 1.0
        top = z1 + (rise(p) if rise else 0.0)
        bot = min(top - 0.5, z0 + (bottom(p) if bottom else 0.0))
        squash = end_height + (1 - end_height) * fade
        edge = top if face_rise is None else min(top, z1 + face_rise(p))
        zc = edge - (edge - bot) * (1 - fc) * squash
        st = []
        for f, d in rows:
            z = edge - (edge - bot) * (1 - f) * squash if f <= fc else zc + (top - zc) * (f - fc) / (1 - fc)
            origin = Vector((p.x, p.y, z)) + n * 8.0
            hit, *_ = tree.ray_cast(origin, -n, 20.0)
            st.append(hit if hit is not None else Vector((p.x, p.y, z)))
        hits.append(st)
        fades.append(fade)
    for _ in range(smooth):                      # Laplacian smoothing along the path, ends fixed
        hits = [hits[0]] + [[(hits[i - 1][r] + hits[i][r] * 2 + hits[i + 1][r]) / 4 for r in range(len(rows))]
                            for i in range(1, n_st - 1)] + [hits[-1]]
    for st, n in zip(hits, dirs):                # smoothing shrinks convex corners: never end up inside the body
        for r, s_ in enumerate(st):
            hit, *_ = tree.ray_cast(s_ + n * 8.0, -n, 20.0)
            if hit is not None:
                st[r] = s_ + n * max(0.0, (hit - s_).dot(n))

    gaps = [[GAP + end_gap * (1 - fade)] * len(rows) for fade in fades]   # ends wrap onto the curving flank: stand a little further off
    if cast_dir is not None:
        gaps = _soften([[_standoff(clear or tree, s_, n, g) for s_, g in zip(st, gs)] for st, n, gs in zip(hits, dirs, gaps)])
    if end_round:
        # the finer end stations come after the body is sampled and smoothed: they follow its smoothed shape, not
        # its facets, which the base step's smoothing would no longer reach
        spots = _refine_ends(path, 3 * end_round, end_step or step / 4)
        path = [path[i].lerp(path[i + 1], t) if t else path[i] for i, t in spots]
        hits = [list(st) for st in zip(*[_spline(row, spots) for row in zip(*hits)])]
        gaps = [list(gs) for gs in zip(*[_spline(row, spots) for row in zip(*gaps)])]
        fades = _spline(fades, spots)
        n_st = len(path)
        normals = plan_normals(path)
        dirs = [cast_dir] * n_st if cast_dir is not None else normals
    along = [0.0]
    for a, b in zip(path[:-1], path[1:]):
        along.append(along[-1] + (b - a).length)
    front = [i for i, n in enumerate(normals) if abs(n.y) < 0.9] or [0, n_st - 1]
    ia, ib = front[0], front[-1]

    def side_f(i):                               # 0 round the front and corners, 1 a ramp's length down a side
        d = along[ia] - along[i] if i < ia else along[i] - along[ib] if i > ib else 0.0
        return min(1.0, max(0.0, d / side_ramp))

    # the extra stand-off squaring the back to the end cap: its slope grows to cancel the back's at the tip (taken over
    # the last 0.1 print mm: the body turns away fastest there, and an average would leave a wedge), quickly at first
    # (a parabola's grows evenly and leaves part of the wedge just short of the tip)
    square = [[0.0] * len(rows) for _ in range(n_st)]
    if end_round and cast_dir is not None:
        for tip, inner in ((0, next(i for i in range(n_st) if along[i] >= 0.1)),
                           (n_st - 1, next(i for i in reversed(range(n_st)) if along[-1] - along[i] >= 0.1))):
            for r in range(len(rows)):
                k = max(0.0, ((hits[inner][r] - hits[tip][r]).dot(dirs[tip]) + gaps[inner][r] - gaps[tip][r]) /
                        abs(along[inner] - along[tip]))
                for i in range(n_st):
                    w = END_SQUARE - abs(along[i] - along[tip])
                    if w > 0:
                        square[i][r] = k * END_SQUARE * ((w / END_SQUARE) ** 2 - (w / END_SQUARE) ** 3 / 3)
    bm = bmesh.new()
    rings = []
    for i, (st, n, fade) in enumerate(zip(hits, dirs, fades)):
        back, front = [], []
        u = end_round - min(along[i], along[-1] - along[i])
        recede = end_round - math.sqrt(end_round * end_round - u * u) if u > 0 else 0.0
        mx = max if cast_dir is None else (lambda a, b: _smax(a, b, SOFT_FLOOR))
        c = curl(path[i]) if curl else 0.0
        floor = []
        for r, (s_, (f, d), g) in enumerate(zip(st, rows, gaps[i])):
            lo = min(min_t, d)                   # the fade never thins a row below min_t (or its own value)
            if r > deepest:
                lo = max(lo, CURL_T * c)
            thick = mx(lo, d * fade - recede)
            if side_thin and side_ramp:
                thick = min(thick, d - (d - lo) * side_f(i))
            elif side_thin and abs(normals[i].y) > 0.7:
                thick = min(thick, lo + (d - lo) * max(0.0, (0.95 - abs(normals[i].y)) / 0.25))
            # squared to the end cap up to the deepest row, the curl's rows above taking less and less of it: they are
            # thin, all floor, and their face would follow the back out into a spike at the top of the end
            g += square[i][r] * max(0.0, min(1.0, 1 - (r - deepest) / END_SQUARE_ROWS))
            # the face stays put where the back has to stand further off; the row only thins (to lo at most)
            back.append(s_ + n * g)
            front.append(s_ + n * mx(GAP + end_gap * (1 - fade) + thick, g + lo))
            floor.append((s_ + n * (g + lo)).dot(n))
        if c > 0.0:
            fd = rows[deepest][0]
            # the rows up to this fraction above the deepest are filled
            lift = min(1.0 - CURL_ROLL, c * (1 + CURL_ROLL) - CURL_ROLL)
            for r in range(deepest + 1, len(rows)):
                fill = 1.0 - _smooth(((rows[r][0] - fd) / (1 - fd) - lift) / CURL_ROLL)
                front[r] = front[r] + n * (fill * max(0.0, (front[deepest] - front[r]).dot(n)))
            # relaxed and crowned from the row above the deepest, which keeps the crease on it (moved off it, the
            # crease would hop a row where the curl begins); crowned in as it starts to curl, too: the section's own
            # top falls back past its crease more steeply than above it, so crowning it at once would leave a line
            k = deepest + 1
            x = [p.dot(n) for p in front]
            for _ in range(CURL_RELAX):
                x = x[:k + 1] + [max(floor[r], (1 - c) * x[r] + c * (x[r - 1] + x[r + 1]) / 2)
                                 for r in range(k + 1, len(rows) - 1)] + x[-1:]
            w = _smooth(c / CURL_CROWN)
            x = x[:k] + [a + w * (b - a) for a, b in zip(x[k:], _crown([s_.z for s_ in st[k:]], x[k:]))]
            front = [p + n * (a - p.dot(n)) for p, a in zip(front, x)]
        rings.append([bm.verts.new(v) for v in back] + [bm.verts.new(v) for v in reversed(front)])
    m = len(rings[0])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(m):
            j = (k + 1) % m
            q = (a[k], a[j], b[j], b[k])
            # where the rows shift against each other (round the rising ends) a quad twists, and shades as
            # a dark scribble if the renderer splits it the wrong way: split it along its flatter diagonal
            co = [v.co for v in q]
            f02, f13 = _fold(co[0], co[1], co[2], co[3]), _fold(co[1], co[2], co[3], co[0])
            if max(f02, f13) < TWIST:
                bm.faces.new(q)
            elif f02 <= f13:
                bm.faces.new((q[0], q[1], q[2]))
                bm.faces.new((q[0], q[2], q[3]))
            else:
                bm.faces.new((q[1], q[2], q[3]))
                bm.faces.new((q[1], q[3], q[0]))
    for ring in (rings[0], rings[-1]):
        # the ends closed in strips across the section, each row's back to its front, not as one n-gon: where an end
        # turns round its face meets the cap nearly flush and shades smooth into it, and an n-gon's fan of long
        # triangles would carry those leaning normals across the cap in dark bands
        for r in range(m // 2 - 1):
            bm.faces.new((ring[r], ring[r + 1], ring[m - 2 - r], ring[m - 1 - r]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    return bpy.data.objects.new(name, me), path, normals


def guard(name, path, normals, y_real, z_top, drop, half_w=0.65, rounded=False, tree=None, clear=None):
    """Bumper guard hanging below the bumper and following the valance down: with the body's tree,
    every row of it stands off the body surface at its own height (its back face GAP-ish off it),
    so a guard under a raked apron curves back with it and rests against it, as on the car. With
    `clear` (a tree of the finished skin) a row whose back would come nearer it than GAP along its
    normal stands off further: the apron is raked, so a back the same distance out along n is nearer.

    rounded: a capsule outline (half-ellipse top, slight taper, round bottom) with a crowned rear
    face, like the rubber-faced rear guards; otherwise a plain tapered block."""
    y = y_real * SCALE
    i = min(range(len(path)), key=lambda k: abs(path[k].y - y))
    p, n = path[i], normals[i]
    t = Vector((-n.y, n.x, 0))

    def base_at(z):                              # the body surface behind the guard at height z
        b = Vector((p.x, p.y, z))
        hit = tree.ray_cast(b + n * 8.0, -n, 30.0)[0] if tree else None
        return hit if hit is not None else b
    bm = bmesh.new()
    if rounded:
        # (height below the top as a fraction of drop, half width fraction, back d, front d)
        rows = []
        cap = min(0.2, 28.0 * SCALE / drop)
        for k in range(7):                               # a dome: the top cap shrinks in depth as much as in width
            a = math.pi / 2 * (1 - k / 6)
            c = max(0.15, math.cos(a))
            rows.append((cap * (1 - math.sin(a)), c, 1.425 - 0.975 * c, 1.425 + 0.975 * c))
        for f, w, db, df in ((0.45, 1.0, 0.35, 2.2), (0.7, 0.92, 0.25, 1.9), (0.82, 0.84, 0.18, 1.6)):
            rows.append((f, w, db, df))
        for k in range(1, 7):                            # round bottom
            a = math.pi / 2 * k / 6
            rows.append((0.82 + 0.18 * math.sin(a), 0.84 * max(0.2, math.cos(a)), 0.15, 1.5 - 0.3 * math.sin(a)))
        segs = 12
        rings = []
        for f, w, db, df in rows:
            base = base_at(z_top - drop * f)
            if clear:
                base = base + n * max(0.0, _standoff(clear, base, n, GAP) - db)
            mid, hd, hw = (db + df) / 2, (df - db) / 2, half_w * w
            ring = []
            for k in range(segs):                        # superellipse: flat-ish sides, crowned rear face
                a = 2 * math.pi * k / segs
                c, s_ = math.cos(a), math.sin(a)
                ex = 0.6
                ring.append(base + n * (mid + hd * math.copysign(abs(c) ** ex, c)) + t * (hw * math.copysign(abs(s_) ** ex, s_)))
            rings.append([bm.verts.new(v) for v in ring])
    else:
        # sections from top (inside the bumper) down to the tip: (z, back d, front d)
        sections = [(z_top, 0.5, 2.5), (z_top - 2.0, 0.4, 2.3), (z_top - drop * 0.7, 0.2, 1.8), (z_top - drop, 0.1, 1.2)]
        rings = []
        for z, db, df in sections:
            base = base_at(z)
            if clear:
                base = base + n * max(0.0, _standoff(clear, base, n, GAP) - db)
            ring = [base + n * db - t * half_w, base + n * df - t * half_w,
                    base + n * df + t * half_w, base + n * db + t * half_w]
            rings.append([bm.verts.new(v) for v in ring])
    m = len(rings[0])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(m):
            j = (k + 1) % m
            bm.faces.new((a[k], a[j], b[j], b[k]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bm.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)
