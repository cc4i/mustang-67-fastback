"""Print-readiness checks on the evaluated (post-modifier) meshes."""
import math
import re

import bmesh
import bpy

PRINT_COLLECTIONS = ("Body", "Wheels", "Parts")


def evaluated_bmesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(ob, dg)
    bm.transform(ob.matrix_world)
    return bm


def mesh_report(ob):
    bm = evaluated_bmesh(ob)
    non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
    boundary_edges = sum(1 for e in bm.edges if e.is_boundary)
    bad_verts = sum(1 for v in bm.verts if not v.is_manifold)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    volume = bm.calc_volume(signed=True)
    shells = _shell_count(bm)
    bm.free()
    return {
        "non_manifold_edges": non_manifold_edges,
        "boundary_edges": boundary_edges,
        "non_manifold_verts": bad_verts,
        "degenerate_faces": degenerate,
        "volume_mm3": round(volume, 2),
        "shells": shells,
    }


def _shell_count(bm):
    seen = set()
    shells = 0
    for f in bm.faces:
        if f.index in seen:
            continue
        shells += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    return shells


def print_objects():
    obs = []
    for name in PRINT_COLLECTIONS:
        col = bpy.data.collections.get(name)
        if col:
            obs += [o for o in col.objects if o.type == 'MESH']
    return obs


def overlap_volume(a, b):
    """Volume of the intersection of two evaluated objects (mm^3), via a manifold boolean."""
    dg = bpy.context.evaluated_depsgraph_get()
    me_a = bpy.data.meshes.new_from_object(a.evaluated_get(dg))
    me_b = bpy.data.meshes.new_from_object(b.evaluated_get(dg))
    me_a.transform(a.matrix_world)
    me_b.transform(b.matrix_world)
    oa = bpy.data.objects.new("_ov_a", me_a)
    ob_ = bpy.data.objects.new("_ov_b", me_b)
    bpy.context.scene.collection.objects.link(oa)
    bpy.context.scene.collection.objects.link(ob_)
    ob_.hide_set(True)
    mod = oa.modifiers.new("x", 'BOOLEAN')
    mod.operation = 'INTERSECT'
    mod.solver = 'MANIFOLD'
    mod.object = ob_
    bm = evaluated_bmesh(oa)
    vol = abs(bm.calc_volume(signed=True)) if len(bm.faces) else 0.0
    bm.free()
    for o, m in ((oa, me_a), (ob_, me_b)):
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(m)
    return round(vol, 3)


# left/right pairs that differ on purpose (oil filler cap one side, breather the other), and parts
# that exist on one side only (the car has a driver's mirror only)
ASYMMETRIC_PAIRS = ("ValveCover",)
ONE_SIDED = ("Mirror", "DoorMirrorSlot", "Axle", "Bumper")      # (Axle_R, Bumper_R: R for rear)
# parts that are meant to interpenetrate: the octagonal axle and knuckle stub corners bite into the rim hubs
PRESS_FITS = (("Axle", "Rim"), ("Knuckle", "Rim"))


def mirror_mismatches(tol=0.05):
    """Left/right part pairs (Name_L*, Name_R*) whose world bounding boxes are not mirror images
    across the centre line, sides with no partner, and Blender duplicate names (Name.001): e.g. a
    side's parts built in the wrong place, twice, or not at all."""
    obs = {ob.name: ob for ob in print_objects()}
    bad = {name: "duplicate" for name in obs if re.search(r"\.\d{3}$", name)}
    sides = {}
    for name in obs:
        m = re.match(r"^(.*)_([LR])(\d*)$", name)
        if m:
            sides.setdefault((m.group(1), m.group(3)), {})[m.group(2)] = obs[name]
    for (base, num), pair in sides.items():
        if base.startswith(ASYMMETRIC_PAIRS):
            continue
        if len(pair) == 1:
            if not base.startswith(ONE_SIDED):
                bad[f"{base}_{next(iter(pair))}{num}"] = "no partner"
            continue
        (lx0, ly0, lz0), (lx1, ly1, lz1) = _world_bounds(pair["L"])
        (rx0, ry0, rz0), (rx1, ry1, rz1) = _world_bounds(pair["R"])
        err = max(abs(lx0 - rx0), abs(lx1 - rx1), abs(lz0 - rz0), abs(lz1 - rz1), abs(ly0 + ry1), abs(ly1 + ry0))
        if err > tol:
            bad[f"{base}_L{num}"] = round(err, 3)
    return bad


def _world_bounds(ob):
    bm = evaluated_bmesh(ob)
    lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
    hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
    bm.free()
    return lo, hi


def part_overlaps(min_volume=0.05):
    """{"A|B": mm^3} for every pair of printed parts (other than the body, checked on its own) that
    interpenetrate, apart from intended press fits: two parts meant to sit side by side that can't
    both be fitted. (Contact slivers under min_volume, a fraction of one extrusion, are ignored.)"""
    obs = [ob for ob in print_objects() if ob.name != "Body"]
    bounds = {ob.name: _world_bounds(ob) for ob in obs}
    out = {}
    for i, a in enumerate(obs):
        (a0, a1) = bounds[a.name]
        for b in obs[i + 1:]:
            (b0, b1) = bounds[b.name]
            if any(a1[k] <= b0[k] or b1[k] <= a0[k] for k in range(3)):
                continue
            if any((a.name.startswith(p) and b.name.startswith(q)) or (a.name.startswith(q) and b.name.startswith(p))
                   for p, q in PRESS_FITS):
                continue
            v = overlap_volume(a, b)
            if v > min_volume:
                out[f"{a.name}|{b.name}"] = v
    return out


def run():
    reports = {ob.name: mesh_report(ob) for ob in print_objects()}
    problems = {k: v for k, v in reports.items()
                if v["non_manifold_edges"] or v["boundary_edges"] or v["non_manifold_verts"]
                or v["volume_mm3"] <= 0 or v["shells"] != 1}
    body = bpy.data.objects["Body"]
    overlaps = {}
    for ob in print_objects():
        if ob is body:
            continue
        overlaps[ob.name] = overlap_volume(body, ob)
    return {"parts": len(reports), "problems": problems,
            "overlaps_with_body": {k: v for k, v in overlaps.items() if v > 0.001},
            "mirror_mismatches": mirror_mismatches(),
            "part_overlaps": part_overlaps(),
            "body": reports["Body"]}


def _seg_dist_2d(p, a, b):
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = p[0] - a[0], p[1] - a[1]
    d2 = abx * abx + aby * aby
    t = 0.0 if d2 < 1e-12 else max(0.0, min(1.0, (apx * abx + apy * aby) / d2))
    return math.hypot(apx - t * abx, apy - t * aby)


def _overhang_hazards(bm, layer=0.12, bed_tol=0.20):
    """Scan downward-facing horizontal patches above the bed for (thin_necks, cantilevers):
    - thin_necks: islands >= 0.50 mm^2 whose only downward support squeezes through a sub-nozzle
      (< 0.20 mm minor-axis width) sliver that Arachne drops during slicing ("floating regions").
    - cantilevers: open perimeter overhangs extending > 1.5 mm horizontally from anchored walls
      with >= 30 mm^2 of unbridged area ("floating cantilever")."""
    if not bm.verts or not bm.faces:
        return [], []
    tris = []
    for f in bm.faces:
        vs = [ (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5)) for v in f.verts ]
        for k in range(1, len(vs) - 1):
            p0, p1, p2 = vs[0], vs[k], vs[k + 1]
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            area2 = math.sqrt(nx * nx + ny * ny + nz * nz)
            if area2 > 2e-7:
                tris.append((p0, p1, p2, nz / area2, 0.5 * area2))
    if not tris:
        return [], []
    zmin = min(min(t[0][2], t[1][2], t[2][2]) for t in tris)
    edge_tris = {}
    for i, (p0, p1, p2, _, _) in enumerate(tris):
        for a, b in ((p0, p1), (p1, p2), (p2, p0)):
            e = (a, b) if a < b else (b, a)
            edge_tris.setdefault(e, []).append(i)
    down = {
        i for i, (p0, p1, p2, nz, _) in enumerate(tris)
        if nz < -0.90 and (p0[2] + p1[2] + p2[2]) / 3.0 > zmin + bed_tol
    }
    seen = set()
    thin_necks, cantilevers = [], []
    for i0 in down:
        if i0 in seen:
            continue
        patch, stack = [], [i0]
        seen.add(i0)
        while stack:
            cur = stack.pop()
            patch.append(cur)
            p0, p1, p2, _, _ = tris[cur]
            zc = (p0[2] + p1[2] + p2[2]) / 3.0
            for a, b in ((p0, p1), (p1, p2), (p2, p0)):
                e = (a, b) if a < b else (b, a)
                for j in edge_tris[e]:
                    if j in down and j not in seen:
                        q0, q1, q2, _, _ = tris[j]
                        if abs((q0[2] + q1[2] + q2[2]) / 3.0 - zc) < 0.15:
                            seen.add(j)
                            stack.append(j)
        area = sum(tris[i][4] for i in patch)
        if area < 0.50:
            continue
        pset = set(patch)
        exit_pts = set()

        def edge_reaches_below(e0, z_ref):
            st = [j for j in edge_tris[e0] if j not in pset]
            seen_f = set(st)
            reached = False
            while st:
                f_idx = st.pop()
                q0, q1, q2, _, _ = tris[f_idx]
                if min(q0[2], q1[2], q2[2]) < z_ref - 0.04:
                    reached = True
                    for q in (q0, q1, q2):
                        if q[2] <= z_ref + 1e-3:
                            exit_pts.add((q[0], q[1]))
                    continue
                if min(q0[2], q1[2], q2[2]) <= z_ref + layer:
                    for a, b in ((q0, q1), (q1, q2), (q2, q0)):
                        ek = (a, b) if a < b else (b, a)
                        for g_idx in edge_tris[ek]:
                            if g_idx not in pset and g_idx not in seen_f:
                                seen_f.add(g_idx)
                                st.append(g_idx)
            return reached

        anchors, frees = [], []
        for i in patch:
            p0, p1, p2, _, _ = tris[i]
            for a, b in ((p0, p1), (p1, p2), (p2, p0)):
                e = (a, b) if a < b else (b, a)
                if all(j in pset for j in edge_tris[e]):
                    continue
                if edge_reaches_below(e, min(a[2], b[2])):
                    anchors.append((a, b))
                else:
                    frees.append((a, b))
        cx = sum((tris[i][0][0] + tris[i][1][0] + tris[i][2][0]) / 3.0 * tris[i][4] for i in patch) / area
        cy = sum((tris[i][0][1] + tris[i][1][1] + tris[i][2][1]) / 3.0 * tris[i][4] for i in patch) / area
        cz = sum((tris[i][0][2] + tris[i][1][2] + tris[i][2][2]) / 3.0 * tris[i][4] for i in patch) / area
        pt = [round(cx, 2), round(cy, 2), round(cz, 2)]
        if not anchors:
            thin_necks.append(pt)
            continue
        if exit_pts:
            pts = list(exit_pts)
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            cxx = sum((p[0] - mx) ** 2 for p in pts) / len(pts)
            cyy = sum((p[1] - my) ** 2 for p in pts) / len(pts)
            cxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / len(pts)
            tr = cxx + cyy
            det = max(0.0, cxx * cyy - cxy * cxy)
            lam_min = max(0.0, 0.5 * (tr - math.sqrt(max(0.0, tr * tr - 4.0 * det))))
            span_max = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in pts)
            if 3.464 * math.sqrt(lam_min) < 0.20 and span_max < 1.20:
                thin_necks.append(pt)
                continue
        if frees:
            unanchored_area = 0.0
            for i in patch:
                p0, p1, p2, _, fa = tris[i]
                m = ((p0[0] + p1[0] + p2[0]) / 3.0, (p0[1] + p1[1] + p2[1]) / 3.0)
                da = min(_seg_dist_2d(m, s0, s1) for s0, s1 in anchors)
                df = min(_seg_dist_2d(m, s0, s1) for s0, s1 in frees)
                if da > 1.5 and df < da:
                    unanchored_area += fa
            if unanchored_area >= 30.0:
                cantilevers.append(pt)
    return thin_necks, cantilevers


def floating_cantilevers(bm, layer=0.12, bed_tol=0.20):
    """Locations [x, y, z] of unanchored horizontal overhangs that trigger slicer 'floating cantilever' warnings."""
    _, cantilevers = _overhang_hazards(bm, layer=layer, bed_tol=bed_tol)
    return cantilevers


def floating_starts(bm, layer=0.12, bed_tol=0.15, tol=1e-4):
    """Places where printing this mesh as oriented (Z up, bed at its lowest point) would start a
    new island in mid-air, i.e. what slicers report as "floating regions" (including islands joined
    to lower layers only through a sub-nozzle < 0.20 mm sliver that Arachne drops).

    Such an island begins at a local minimum of height over the surface: a vertex, or a flat patch
    of vertices at one height (a tube's bottom line, a box's underside), whose every neighbour is
    higher and whose faces all point down (nothing printed lies beneath it). Bottoms joined to lower
    geometry, such as a ledge growing out of a wall, are not minima. A minimum only matters if it
    stays an island for a whole `layer`: walking up the surface from it, one layer's height, without
    reaching geometry that goes lower (the slicer never sees thinner slivers). Anything starting
    within `bed_tol` of the bed prints as part of the first layer. Returns each island's lowest point."""
    bm.verts.index_update()
    bm.normal_update()
    seen = set()
    starts = []
    zmin = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        if v.index in seen or v.co.z < zmin + bed_tol:
            continue
        z0 = v.co.z
        patch, stack = [v], [v]
        seen.add(v.index)
        is_min = True
        while stack:
            cur = stack.pop()
            for e in cur.link_edges:
                n = e.other_vert(cur)
                if abs(n.co.z - z0) <= tol:
                    if n.index not in seen:
                        seen.add(n.index)
                        patch.append(n)
                        stack.append(n)
                elif n.co.z < z0:
                    is_min = False
        if not is_min:
            continue
        normals_z = [f.normal.z for p in patch for f in p.link_faces]
        if max(normals_z) > 0.01 or min(normals_z) > -0.05:     # material below, or only walls around
            continue
        band = {p.index for p in patch}
        stack = list(patch)
        anchored = False
        while stack and not anchored:
            cur = stack.pop()
            for e in cur.link_edges:
                n = e.other_vert(cur)
                if n.co.z < z0 - tol:
                    anchored = True
                    break
                if n.co.z <= z0 + layer and n.index not in band:
                    band.add(n.index)
                    stack.append(n)
        if anchored:
            continue
        c = sum((p.co for p in patch), v.co * 0) / len(patch)
        starts.append([round(c.x, 2), round(c.y, 2), round(c.z, 2)])
    thin_necks, _ = _overhang_hazards(bm, layer=layer, bed_tol=max(bed_tol, 0.20))
    for pt in thin_necks:
        if all(math.hypot(pt[0] - s[0], pt[1] - s[1]) > 0.5 or abs(pt[2] - s[2]) > 0.5 for s in starts):
            starts.append(pt)
    return starts


def thin_spots(ob, limit=0.8, samples=6000):
    """Cast inward from sampled faces; report places thinner than `limit` mm."""
    from mathutils.bvhtree import BVHTree
    bm = evaluated_bmesh(ob)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    tree = BVHTree.FromBMesh(bm)
    faces = [f for f in bm.faces if f.calc_area() > 1e-6]
    step = max(1, len(faces) // samples)
    thin = []
    for f in faces[::step]:
        c = f.calc_center_median()
        n = f.normal
        hit = tree.ray_cast(c - n * 1e-3, -n, limit)
        if hit[0] is not None:
            thin.append([round(v, 2) for v in c] + [round(hit[3], 3)])
    bm.free()
    return thin
