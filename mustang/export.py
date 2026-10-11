"""Export print-ready parts: one binary STL per unique part, in print orientation, centred and
resting on Z=0, into output/stl. make_project.sh then builds the Bambu Studio project from them.
"""
import json
import math
import os
import struct

import bmesh
import bpy
from mathutils import Matrix, Vector

import paths
import printcheck

# unique part -> (source object, print rotation, quantity, colour hex)
RY_UP_FROM_NEG_X = Matrix.Rotation(math.pi / 2, 4, 'Y')    # -X facing part -> faces +Z
RY_UP_FROM_POS_X = Matrix.Rotation(-math.pi / 2, 4, 'Y')   # +X facing part -> faces +Z
RX_UP_FROM_POS_Y = Matrix.Rotation(math.pi / 2, 4, "X")   # +Y facing part -> faces +Z
RX_UP_FROM_NEG_Y = Matrix.Rotation(-math.pi / 2, 4, "X")  # -Y facing part -> faces +Z
IDENTITY = Matrix.Identity(4)
UPSIDE_DOWN = Matrix.Rotation(math.pi, 4, 'X')               # flat face down (front bumper, diff cover)

PARTS = [
    ("body", "Body", IDENTITY, 1, "#6B0F1A"),
    ("rim", "Rim_FR", RX_UP_FROM_POS_Y, 4, "#C8C8CC"),
    ("tire", "Tire_FR", RX_UP_FROM_POS_Y, 4, "#1A1A1A"),
    ("grille", "Grille", RY_UP_FROM_NEG_X, 1, "#1A1A1A"),
    ("grille_surround", "GrilleSurround", RY_UP_FROM_NEG_X, 1, "#C8C8CC"),
    ("corral_emblem", "Corral", RY_UP_FROM_NEG_X, 1, "#C8C8CC"),
    ("fog_lamp", "FogLamp_R", RY_UP_FROM_NEG_X, 2, "#C8C8CC"),
    ("headlight", "Headlight_R", RY_UP_FROM_NEG_X, 2, "#C8C8CC"),
    ("park_light", "ParkLight_R", "LOCAL", 2, "#C8C8CC"),               # modelled lens up in its own frame
    # the lamps curve toward the centre line, so the two sides are mirror images: three of each
    ("taillight_lens_r", "Taillight_R0", RY_UP_FROM_POS_X, 3, "#B01010"),
    ("taillight_lens_l", "Taillight_L0", RY_UP_FROM_POS_X, 3, "#B01010"),
    ("taillight_bezel_r", "TailBezel_R0", RY_UP_FROM_POS_X, 3, "#C8C8CC"),
    ("taillight_bezel_l", "TailBezel_L0", RY_UP_FROM_POS_X, 3, "#C8C8CC"),
    ("gas_cap", "GasCap", RY_UP_FROM_POS_X, 1, "#C8C8CC"),
    ("bumper_front", "Bumper_F", UPSIDE_DOWN, 1, "#C8C8CC"),
    ("bumper_rear", "Bumper_R", IDENTITY, 1, "#C8C8CC"),      # swept-up ends: upright, supported from below
    ("chassis", "Chassis", IDENTITY, 1, "#1A1A1A"),
    ("diff_cover", "DiffCover", UPSIDE_DOWN, 1, "#1A1A1A"),             # flat side down
    ("exhaust", "Exhaust_R", RY_UP_FROM_POS_X, 2, "#C8C8CC"),
    ("backup_light", "BackupLight_R", RY_UP_FROM_POS_X, 2, "#C8C8CC"),        # stands on its back, face up
    ("axle", "Axle_F", IDENTITY, 2, "#1A1A1A"),
    ("mirror", "Mirror_L", RY_UP_FROM_NEG_X, 1, "#C8C8CC"),             # flat rear face down, domed back up
    ("interior_tub", "InteriorTub", IDENTITY, 1, "#1A1A1A"),
    ("steering_wheel", "SteeringWheel", "LOCAL_Y_UP", 1, "#1A1A1A"),
    ("hood", "Hood", IDENTITY, 1, "#6B0F1A"),
    # doors lie on their flat inner face, skin up; the cards lie on their back, armrest up
    ("door_r", "Door_R", RX_UP_FROM_POS_Y, 1, "#6B0F1A"),
    ("door_l", "Door_L", RX_UP_FROM_NEG_Y, 1, "#6B0F1A"),
    ("door_card_r", "DoorCard_R", RX_UP_FROM_NEG_Y, 1, "#1A1A1A"),
    ("door_card_l", "DoorCard_L", RX_UP_FROM_POS_Y, 1, "#1A1A1A"),
    ("vent_window_r", "DoorVent_R", "LOCAL", 1, "#C8C8CC"),             # flat frames, modelled in their own planes
    ("vent_window_l", "DoorVent_L", "LOCAL", 1, "#C8C8CC"),             # (mirror images: the feet bevel to the door top)
    ("bay_tub", "BayTub", IDENTITY, 1, "#1A1A1A"),
    ("engine_block", "EngineBlock", IDENTITY, 1, "#2B59C3"),
    ("valve_cover_r", "ValveCover_R", Matrix.Rotation(math.pi / 4, 4, "X"), 1, "#1A1A1A"),     # the oil filler cap's side
    ("valve_cover_l", "ValveCover_L", Matrix.Rotation(-math.pi / 4, 4, "X"), 1, "#1A1A1A"),    # the breather's side
    ("air_cleaner", "AirCleaner", IDENTITY, 1, "#1A1A1A"),
    ("brace", "Brace", IDENTITY, 1, "#1A1A1A"),
    ("hood_prop", "HoodProp", "LOCAL", 1, "#1A1A1A"),
]
# extra parts of another part's print object (its unique part key), in another colour: the tinted
# glass inlays print in black inside the body. Exported in the host's print frame, so they land in place.
INLAYS = [
    ("windshield", "Glass_Windshield", "body", "#1A1A1A"),
    ("rear_glass", "Glass_Rear", "body", "#1A1A1A"),
]


def clean_triangulate(bm, ngon_method, weld, dissolve=True):
    """Triangulate boolean output robustly: weld numerically-split vertices, then collapse
    degenerate faces, drop loose geometry and re-triangulate until stable. With dissolve=False
    the mesh is only triangulated (some parts come out cleaner untouched)."""
    if weld:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
    if not dissolve:
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method=ngon_method)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return
    # a vertex on only two edges sits on a seam shared by just two faces; triangulated, both faces can
    # cut the same corner off across it, making an edge of four triangles. Dissolving it moves the
    # seam by no more than its (tiny) deviation from straight.
    bmesh.ops.dissolve_verts(bm, verts=[v for v in bm.verts if len(v.link_edges) == 2])
    for _ in range(6):
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
        loose_e = [e for e in bm.edges if not e.link_faces]
        if loose_e:
            bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
        loose_v = [v for v in bm.verts if not v.link_edges]
        if loose_v:
            bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3],
                              quad_method='BEAUTY', ngon_method=ngon_method)
        if not any(f.calc_area() < 1e-9 for f in bm.faces):
            break
    drop_coincident_faces(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def _key(co):
    return (round(co.x, 6), round(co.y, 6), round(co.z, 6))


def drop_coincident_faces(bm):
    """Delete triangles that share all three corner positions with another (a zero-volume fin of
    two back-to-back faces on separate vertices, which topology alone can't see but every STL
    reader, welding by position, does)."""
    seen = {}
    for f in bm.faces:
        seen.setdefault(tuple(sorted(_key(v.co) for v in f.verts)), []).append(f)
    doomed = [f for group in seen.values() if len(group) > 1 for f in group]
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context='FACES_ONLY')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')


def print_mesh(ob_name, rot, shift=None):
    """Evaluated mesh of an object, rotated into print orientation, cleaned, centred on Z=0;
    returns (bmesh, the centring shift). With `shift` given it is moved by that instead (an inlay
    placed in its host's print frame).

    Only the object's rotation/scale is applied (not its placement on the car). Boolean output
    contains numerically-split vertices and self-touching n-gons that no single triangulation
    handles, so a few weld tolerances (all far below print resolution) and triangulation methods
    are tried and the cleanest result is kept: manifold first, then fewest zero-area triangles."""
    ob = bpy.data.objects[ob_name]
    dg = bpy.context.evaluated_depsgraph_get()
    loc, q, scale = ob.matrix_world.decompose()
    if rot == "LOCAL":               # print in the part's own modelling frame, ignoring placement and parents
        rot, q = Matrix.Identity(4), q.copy()
        q.identity()
    elif rot == "LOCAL_Y_UP":        # modelled around its own +Y axis: lay that axis vertical, ignore placement
        rot, q = Matrix.Rotation(-math.pi / 2, 4, "X"), q.copy()   # rim on the bed, column up
        q.identity()
    best = None
    candidates = [(0.0, m, False) for m in ('BEAUTY', 'EAR_CLIP')]
    candidates += [(w, m, True) for w in (0.0, 1e-5, 3e-5, 1e-4) for m in ('BEAUTY', 'EAR_CLIP')]
    for weld, ngon_method, dissolve in candidates:
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(rot @ Matrix.LocRotScale(None, q, scale))
        clean_triangulate(bm, ngon_method, weld, dissolve)
        c = check(bm)
        score = (c["non_manifold"], c["degenerate"])
        if best is None or score < best[0]:
            if best:
                best[1].free()
            best = (score, bm)
        else:
            bm.free()
        if best[0] == (0, 0):
            break
    bm = best[1]
    if shift is None:
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        shift = Vector((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs)))
    bmesh.ops.translate(bm, verts=bm.verts, vec=shift)
    return bm, shift


def check(bm):
    """Mesh health as an STL reader sees it: vertices welded by position, every edge in exactly two
    triangles and no triangle repeated (a seam of separate vertices at the same positions, open in
    the bmesh, is closed in the STL), plus zero-area triangles."""
    edges, tris = {}, set()
    dup = 0
    for f in bm.faces:
        ks = [_key(v.co) for v in f.verts]
        t = tuple(sorted(ks))
        dup += t in tris
        tris.add(t)
        for a, b in zip(ks, ks[1:] + ks[:1]):
            e = (a, b) if a < b else (b, a)
            edges[e] = edges.get(e, 0) + 1
    return {
        "non_manifold": sum(1 for n in edges.values() if n != 2) + dup,
        "degenerate": sum(1 for f in bm.faces if f.calc_area() < 1e-9),
        "volume": round(bm.calc_volume(signed=True), 1),
    }


def size(bm):
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def write_stl(bm, path, name):
    with open(path, "wb") as f:
        f.write(name.encode("ascii")[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(bm.faces)))
        for face in bm.faces:
            n = face.normal
            f.write(struct.pack("<3f", n.x, n.y, n.z))
            for v in face.verts:
                f.write(struct.pack("<3f", *v.co))
            f.write(b"\0\0")


HINGED = ("Hood", "Door_L", "Door_R")


def run(out_dir=paths.OUTPUT):
    """Write one print-oriented STL per unique part and inlay into out_dir/stl, plus manifest.json
    (file, quantity, colour, and for inlays the host file) that make_project.sh checks its plate
    groups against. Parts are taken in their closed, modelled pose (the hood and doors carry their
    riders' print rotation)."""
    stl_dir = os.path.join(out_dir, "stl")
    os.makedirs(stl_dir, exist_ok=True)
    poses = {n: bpy.data.objects[n].rotation_euler.copy() for n in HINGED}
    try:
        return _write_parts(stl_dir, poses)
    finally:                                     # put any opened hood / doors back as they were
        for n, pose in poses.items():
            bpy.data.objects[n].rotation_euler = pose
        bpy.context.view_layer.update()


def _write_parts(stl_dir, poses):
    for n in poses:
        bpy.data.objects[n].rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    report, manifest, frames = {}, [], {}
    for key, ob_name, rot, qty, colour in PARTS:
        bm, shift = print_mesh(ob_name, rot)
        frames[key] = (ob_name, rot, shift)
        info = check(bm)
        info["size_mm"] = [round(s, 2) for s in size(bm)]
        info["qty"] = qty
        info["floating"] = printcheck.floating_starts(bm)   # mid-air island starts (slicer "floating regions")
        fname = f"{key}_x{qty}.stl" if qty > 1 else f"{key}.stl"
        write_stl(bm, os.path.join(stl_dir, fname), f"mustang67 {key}")
        report[fname] = info
        manifest.append({"file": fname, "qty": qty, "colour": colour})
        bm.free()
    for key, ob_name, host, colour in INLAYS:
        host_ob, rot, shift = frames[host]
        # print_mesh drops placement, so the inlay must be modelled in the host's frame
        assert bpy.data.objects[ob_name].matrix_world == bpy.data.objects[host_ob].matrix_world, ob_name
        bm, _ = print_mesh(ob_name, rot, shift)
        info = check(bm)
        info["size_mm"] = [round(s, 2) for s in size(bm)]
        info["qty"] = 1
        info["floating"] = []                # it starts on the host, not in mid-air
        fname = f"{key}.stl"
        write_stl(bm, os.path.join(stl_dir, fname), f"mustang67 {key}")
        report[fname] = info
        manifest.append({"file": fname, "qty": 1, "colour": colour, "part_of": f"{host}.stl"})
        bm.free()
    with open(os.path.join(stl_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    remove_stale(stl_dir, report)
    return report


def remove_stale(folder, written):
    """Delete STL files in `folder` this export did not write (parts renamed or dropped since)."""
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if name.endswith(".stl") and name not in written and os.path.isfile(path):
            os.remove(path)


def print_colour(ob_name):
    """The colour an object prints in: its own PARTS / INLAYS entry's, or else that of the one copy
    in PARTS it is printed as (Rim_FL prints as Rim_FR, TailBezel_L1 as TailBezel_L0)."""
    colours = {ob: colour for _, ob, _, _, colour in PARTS} | {ob: colour for _, ob, _, colour in INLAYS}
    if ob_name in colours:
        return colours[ob_name]
    base = ob_name.rsplit("_", 1)[0]
    found = {colour for ob, colour in colours.items() if "_" in ob and ob.rsplit("_", 1)[0] == base}
    assert len(found) == 1, f"no single print colour for {ob_name}: {found}"
    return found.pop()


def run_assembled(out_dir=paths.OUTPUT, collections=("Body", "Wheels", "Parts")):
    """Write every part as its own STL in its assembled position on the car (print millimetres),
    plus one combined file and manifest.json (file, object name, print colour), which
    make_step.py turns into STEP solids for CAD tools such as Shapr3D."""
    folder = os.path.join(out_dir, "stl_assembled")
    os.makedirs(folder, exist_ok=True)
    dg = bpy.context.evaluated_depsgraph_get()
    combined = bmesh.new()
    written, manifest = [], []
    for col_name in collections:
        for ob in sorted(bpy.data.collections[col_name].objects, key=lambda o: o.name):
            if ob.type != 'MESH':
                continue
            bm = bmesh.new()
            bm.from_object(ob, dg)
            bm.transform(ob.matrix_world)
            clean_triangulate(bm, 'BEAUTY', 3e-5)
            name = ob.name.lower()
            write_stl(bm, os.path.join(folder, f"{name}.stl"), f"mustang67 {name}")
            tmp = bpy.data.meshes.new("_tmp_combined")
            bm.to_mesh(tmp)
            combined.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
            written.append(name)
            manifest.append({"file": f"{name}.stl", "object": ob.name, "colour": print_colour(ob.name)})
            bm.free()
    write_stl(combined, os.path.join(folder, "_mustang_assembled_all_parts.stl"), "mustang67 assembled")
    combined.free()
    with open(os.path.join(folder, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    remove_stale(folder, {f"{n}.stl" for n in written} | {"_mustang_assembled_all_parts.stl"})
    return written
