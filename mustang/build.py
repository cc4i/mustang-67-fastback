"""Build the whole 1:20 printable Mustang into the open Blender scene.

Run inside Blender:  import build; build.main()
"""
import importlib
import math

import bmesh
import bpy

import body
import bumpers
import details
import doors
import engine_bay
import features
import interior
import materials
import printcheck
import wheels

for _m in (body, features, wheels, bumpers, details, interior, doors, engine_bay, materials, printcheck):
    importlib.reload(_m)

S = body.SCALE
K = S / (1.0 / 24.0)
AXLE_Z = body.WHEEL_RADIUS * S
AXLE_XS = (body.FRONT_AXLE_X * S, body.REAR_AXLE_X * S)
WHEEL_Y = 31.3 * K                # rear wheel centre plane offset from the centre line
FRONT_WHEEL_Y = 32.2 * K          # front wheel centre plane offset (clears steering sweep)
ARCH_R = details.FRONT_ARCH * S   # wheel arch opening radius (front; the rear is larger)
REAR_ARCH_R = details.REAR_ARCH * S
WELL_INNER_Y = 25.6 * K           # depth of the rear wheel well (inner wall plane)
FRONT_WELL_INNER_Y = 23.4 * K     # depth of the front wheel well (steered tire sweep clearance)
SUBDIV_LEVELS = 3

COLLECTIONS = ["Body", "Wheels", "Parts", "Accessories", "Cutters"]


def collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_build():
    for name in COLLECTIONS:
        col = bpy.data.collections.get(name)
        if col:
            for ob in list(col.objects):
                me = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                if me and me.users == 0:
                    bpy.data.meshes.remove(me)
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH' and not ob.users_collection:   # orphans left by earlier runs
            bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def link(ob, col_name):
    collection(col_name).objects.link(ob)
    return ob


def apply_subdiv(me, levels):
    """Bake Catmull-Clark subdivision into the mesh data."""
    tmp = bpy.data.objects.new("_tmp", me)
    bpy.context.scene.collection.objects.link(tmp)
    mod = tmp.modifiers.new("sub", 'SUBSURF')
    mod.levels = levels
    mod.boundary_smooth = 'PRESERVE_CORNERS'
    dg = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    return baked


def cylinder_y(name, r, y0, y1, x, z, segments=64):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r, depth=abs(y1 - y0))
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, 'X'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(x, (y0 + y1) / 2, z))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def add_boolean(target, cutter, name=None):
    cutter.display_type = 'WIRE'
    cutter.hide_render = True
    mod = target.modifiers.new(name or cutter.name, 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'MANIFOLD'
    mod.object = cutter
    return mod


def add_intersect(target, other):
    other.display_type = 'WIRE'
    other.hide_render = True
    mod = target.modifiers.new(other.name, 'BOOLEAN')
    mod.operation = 'INTERSECT'
    mod.solver = 'MANIFOLD'
    mod.object = other
    return mod


def add_union(target, piece):
    piece.display_type = 'WIRE'
    piece.hide_render = True
    mod = target.modifiers.new(piece.name, 'BOOLEAN')
    mod.operation = 'UNION'
    mod.solver = 'MANIFOLD'
    mod.object = piece
    return mod


def build_parts(body_ob, shell):
    """shell: the body's surface before its lower rear corners roll under (build_body)."""
    me = body_ob.data
    tree = features._bvh(me)
    for glass in details.glass_parts(tree, me):       # printed with the body, in black
        link(glass, "Parts")
    plate, pieces, holes = details.grille_parts(tree)
    link(plate, "Parts")
    for p in pieces:
        add_union(plate, link(p, "Cutters"))
    for h in holes:
        add_boolean(plate, link(h, "Cutters"))
    corral, window, pony, fogs = details.grille_chrome_parts(tree)
    link(corral, "Parts")
    add_boolean(corral, link(window, "Cutters"))      # open chrome frame...
    for piece in pony:                                 # ...holding the cut-out running horse
        add_union(corral, link(piece, "Cutters"))
    for fog, pieces, holes in fogs:
        link(fog, "Parts")
        for h in holes:
            add_boolean(fog, link(h, "Cutters"))
        for p in pieces:
            add_union(fog, link(p, "Cutters"))
    ring, cutters = details.grille_surround(tree)
    link(ring, "Parts")
    for c in cutters:
        add_boolean(ring, link(c, "Cutters"))
    for part, pieces, holes in details.lamp_parts(tree):
        link(part, "Parts")
        for h in holes:                         # recesses first, so details raised inside them survive
            add_boolean(part, link(h, "Cutters"))
        for p in pieces:
            add_union(part, link(p, "Cutters"))
    tub, pieces, cuts = interior.tub_parts()
    link(tub, "Parts")
    for p in pieces:
        add_union(tub, link(p, "Cutters"))
    for c in cuts:
        add_boolean(tub, link(c, "Cutters"))
    wheel, pieces, placement = interior.steering_wheel()
    link(wheel, "Parts")
    wheel.matrix_world = placement
    for p in pieces:
        p.parent = wheel                      # pieces are modelled in the wheel's local frame
        add_union(wheel, link(p, "Cutters"))
    for part, pieces in details.mirror_parts(tree):
        link(part, "Parts")
        for p in pieces:
            add_union(part, link(p, "Cutters"))
    link(details.diff_cover(), "Parts")
    plate, unions, cuts = details.chassis_parts()
    link(plate, "Parts")
    for p in unions:
        add_union(plate, link(p, "Cutters"))
    for c in cuts:
        add_boolean(plate, link(c, "Cutters"))
    for pipe, pieces, cuts in details.exhaust_parts():
        link(pipe, "Parts")
        for p in pieces:
            add_union(pipe, link(p, "Cutters"))
        for c in cuts:
            add_boolean(pipe, link(c, "Cutters"))
    for can, unions, cuts in details.backup_light_parts():
        link(can, "Parts")
        for c in cuts:                           # the lens well first: the lens fills it
            add_boolean(can, link(c, "Cutters"))
        for u in unions:
            add_union(can, link(u, "Cutters"))
    for bumper, pieces, cuts in details.bumper_parts(shell, tree):    # the rear one stands over the tuck's top
        link(bumper, "Parts")
        for c in cuts:                           # the plate notch first: the lamp housing hangs in it
            add_boolean(bumper, link(c, "Cutters"))
        for p in pieces:
            add_union(bumper, link(p, "Cutters"))
    build_engine_bay(tree, me)
    build_doors(tree, me, body_ob)
    for col in ("Parts", "Cutters"):             # smooth shading everywhere: smooth_by_angle keeps cut edges crisp
        for ob in collection(col).objects:
            if ob.type == 'MESH':
                for poly in ob.data.polygons:
                    poly.use_smooth = True


def build_doors(tree, me, body_ob):
    """Opening doors cut from the body shell, with their black door cards."""
    for door, skin, pre, unions, post in doors.door_parts(tree, me, body_ob):
        link(door, "Parts")
        add_intersect(door, link(skin, "Cutters"))
        for c in pre:
            add_boolean(door, link(c, "Cutters"))
        for u in unions:
            add_union(door, link(u, "Cutters"))
        for c in post:
            add_boolean(door, link(c, "Cutters"))
    for card, unions, cuts in doors.card_parts(tree):
        link(card, "Parts")
        for u in unions:
            add_union(card, link(u, "Cutters"))
        for c in cuts:
            add_boolean(card, link(c, "Cutters"))
    for frame, panes in doors.vent_parts(tree):
        link(frame, "Parts")
        for p in panes:
            add_boolean(frame, link(p, "Cutters"))
    for side in doors.SIDES:                 # origin on the hinge axis; card, vent, mirror and cutters ride along
        doors.set_pivot(side)


def build_engine_bay(tree, me):
    """Opening hood and trunk lid, black bay liner with N25 cradle, V8 shroud, driveshaft, and rear boot tub."""
    hood, pieces, cuts, pivot = engine_bay.hood_parts(tree, me)
    link(hood, "Parts")
    for p in pieces:
        add_union(hood, link(p, "Cutters"))
    for c in cuts:
        add_boolean(hood, link(c, "Cutters"))
    engine_bay.set_hood_pivot(hood, pieces + cuts, pivot)
    liner, pieces, cuts, level = engine_bay.liner_parts(tree)
    link(liner, "Parts")
    for p in pieces:
        add_union(liner, link(p, "Cutters"))
    for c in cuts:
        add_boolean(liner, link(c, "Cutters"))
    block, pieces, hollowed, covers, cleaner = engine_bay.engine_parts(tree)
    link(block, "Parts")
    for p in pieces:
        add_union(block, link(p, "Cutters"))
    for part, inner in hollowed:                 # fan belt inner cut, alternator slots, and EngineBlock N25 cavity
        add_boolean(part, link(inner, "Cutters"))
    for part, unions in covers + [cleaner]:      # valve covers and air cleaner
        link(part, "Parts")
        for u in unions:
            add_union(part, link(u, "Cutters"))
    brace, pieces = engine_bay.brace_part(level)
    link(brace, "Parts")
    for p in pieces:
        add_union(brace, link(p, "Cutters"))
    shaft, s_cuts = engine_bay.driveshaft_part()
    link(shaft, "Parts")
    for c in s_cuts:
        add_boolean(shaft, link(c, "Cutters"))
    gear, g_cuts = engine_bay.axle_gear_part()
    link(gear, "Parts")
    for c in g_cuts:
        add_boolean(gear, link(c, "Cutters"))
    trunk, t_pieces, t_cuts, t_pivot = engine_bay.trunk_parts(tree, me)
    link(trunk, "Parts")
    for p in t_pieces:
        add_union(trunk, link(p, "Cutters"))
    for c in t_cuts:
        add_boolean(trunk, link(c, "Cutters"))
    engine_bay.set_hood_pivot(trunk, t_pieces + t_cuts, t_pivot)
    boot, b_pieces, b_cuts = engine_bay.boot_tub_parts(tree)
    link(boot, "Parts")
    for c in b_cuts:
        add_boolean(boot, link(c, "Cutters"))
    for p in b_pieces:
        add_union(boot, link(p, "Cutters"))
    prop = link(engine_bay.prop_rod(pivot, tree), "Accessories")
    prop.hide_render = True                  # shown only in open-hood renders


def build_body():
    me = apply_subdiv(body.build_base_mesh("Body"), SUBDIV_LEVELS)
    body.extend_quarter_corners(me)
    shell = features._bvh(me)        # the bumpers hug the skin as it is before the quarters tuck under
    body.tuck_lower_quarters(me)
    for p in me.polygons:
        p.use_smooth = True
    ob = link(bpy.data.objects.new("Body", me), "Body")
    tree = features._bvh(me)
    for name, piece in details.body_unions(tree, me):
        add_union(ob, link(piece, "Cutters"))
    for i, x in enumerate(AXLE_XS):
        well_y = FRONT_WELL_INNER_Y if i == 0 else WELL_INNER_Y
        for side in (-1, 1):
            arch = link(cylinder_y(f"Cut_Arch_{'F' if i == 0 else 'R'}{'L' if side < 0 else 'R'}",
                                   ARCH_R if i == 0 else REAR_ARCH_R, side * well_y, side * 60 * K, x, AXLE_Z, 96), "Cutters")
            add_boolean(ob, arch)
    for name, cutter in details.body_cutters(tree, me):
        add_boolean(ob, link(cutter, "Cutters"), name)
    for name, piece in details.body_late_unions(tree, me):     # stand on the set-back tail panel
        add_union(ob, link(piece, "Cutters"))
    for name, cutter in details.body_late_cuts(tree, me):
        add_boolean(ob, link(cutter, "Cutters"), name)
    for name, cutter in engine_bay.body_cutters(tree, me) + engine_bay.trunk_body_cutters(tree, me):
        add_boolean(ob, link(cutter, "Cutters"), name)
    interior.set_body_surface(tree)
    add_boolean(ob, link(interior.cabin_cutter(), "Cutters"), "Cut_Cabin")
    openings, bosses, pins = doors.body_parts()       # cut the openings, put the pin bosses back, drill them
    for c in openings:
        add_boolean(ob, link(c, "Cutters"))
    for u in bosses:
        add_union(ob, link(u, "Cutters"))
    for c in pins:
        add_boolean(ob, link(c, "Cutters"))
    for name, cutter in details.chassis_slots() + details.exhaust_slots():
        add_boolean(ob, link(cutter, "Cutters"), name)
    return ob, shell


AXLE_LENGTH = 2 * (WHEEL_Y + wheels.RIM_W - 0.3 * K) - 0.3 * K   # flush with the outer hub faces, less a hair


def build_wheels():
    for i, x in enumerate(AXLE_XS):
        wy = FRONT_WHEEL_Y if i == 0 else WHEEL_Y
        if i == 1:
            axle = link(bpy.data.objects.new("Axle_R", wheels.axle_mesh("Axle", AXLE_LENGTH)), "Wheels")
            axle.location = (x, 0, AXLE_Z)
        else:
            tie, t_unions, t_cuts = wheels.steering_link_part()
            link(tie, "Parts")
            for u in t_unions:
                u_ob = link(u, "Cutters")
                u_ob.parent = tie
                add_union(tie, u_ob)
            for c in t_cuts:
                c_ob = link(c, "Cutters")
                c_ob.parent = tie
                add_boolean(tie, c_ob)
        for side in (-1, 1):
            tag = f"{'F' if i == 0 else 'R'}{'L' if side < 0 else 'R'}"
            rim_me = wheels.rim_blank_mesh(f"Rim_{tag}")
            rim = link(bpy.data.objects.new(f"Rim_{tag}", rim_me), "Wheels")
            cutter = link(bpy.data.objects.new(f"Cut_Spokes_{tag}", wheels.spoke_cutter_mesh(f"Cut_Spokes_{tag}")), "Cutters")
            cutter.parent = rim
            add_boolean(rim, cutter)
            tire = link(bpy.data.objects.new(f"Tire_{tag}", wheels.tire_mesh(f"Tire_{tag}")), "Wheels")
            for ob in (rim, tire):
                ob.location = (x, side * wy, AXLE_Z)
                # meshes face +Y outward; mirror the left-hand side
                if side < 0:
                    ob.rotation_euler = (0, 0, math.pi)
            if i == 0:
                knuckle, k_unions, k_cuts, pivot = wheels.knuckle_parts(side)
                link(knuckle, "Parts")
                for u in k_unions:
                    add_union(knuckle, link(u, "Cutters"))
                for c in k_cuts:
                    add_boolean(knuckle, link(c, "Cutters"))
                wheels.set_knuckle_pivot(knuckle, k_unions + k_cuts, pivot, riders=(rim, tire))


def smooth_by_angle(ob, angle_deg=35.0):
    """Render boolean-cut edges crisp (display/render only; exported STLs carry no shading)."""
    ng = bpy.data.node_groups.get("Smooth by Angle")
    if ng is not None:
        mod = ob.modifiers.get("Smooth by Angle") or ob.modifiers.new("Smooth by Angle", 'NODES')
        mod.node_group = ng
        try:
            mod["Input_1"] = math.radians(angle_deg)
        except Exception:
            pass
        return
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))


def main():
    clear_build()
    for name in COLLECTIONS:
        collection(name)
    for lc in bpy.context.view_layer.layer_collection.children:     # animate.setup() hides the build
        if lc.collection.name in COLLECTIONS[:-1]:
            lc.hide_viewport = False
            lc.collection.hide_viewport = False
            lc.collection.hide_render = False
        elif lc.collection.name == "Showcase":
            lc.hide_viewport = True
            lc.collection.hide_viewport = True
            lc.collection.hide_render = True
    old = bpy.data.objects.get("Cube")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    body_ob, shell = build_body()
    build_wheels()
    build_parts(body_ob, shell)
    materials.apply_all()
    smooth_by_angle(body_ob)
    collection("Body").hide_viewport = True
    for ob in collection("Parts").objects:       # round parts (hoses, wires, caps) shade round, cut edges stay crisp
        if ob.type == 'MESH' and not ob.name.startswith(("Hood", "TrunkLid")):
            smooth_by_angle(ob)
    collection("Body").hide_viewport = False
    collection("Cutters").hide_viewport = False
    for ob in collection("Cutters").objects:
        ob.hide_set(True)
    return {"objects": len(bpy.data.objects)}
