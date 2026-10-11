"""Showroom preview render: glossy studio cove, soft area lights, cameras matching the reference photos."""
import math
import os

import bmesh
import bpy
from mathutils import Vector

STUDIO = "Studio"
# what setup() makes; the collection also holds hand-placed cameras (photo matches) that it keeps
OWNED = ("Floor", "KeyLight", "FillLight", "TopLight", "Cam_Front34", "Cam_Rear34", "Cam_Side")


def _col(clear=False):
    col = bpy.data.collections.get(STUDIO)
    if col is None:
        col = bpy.data.collections.new(STUDIO)
        bpy.context.scene.collection.children.link(col)
    for name in OWNED if clear else ():
        ob = bpy.data.objects.get(name)
        if ob:
            data, kind = ob.data, ob.type
            bpy.data.objects.remove(ob, do_unlink=True)
            if data is not None and data.users == 0:
                getattr(bpy.data, {"MESH": "meshes", "LIGHT": "lights", "CAMERA": "cameras"}[kind]).remove(data)
    return col


COVE = (700.0, 500.0, 1500.0)    # studio cove: flat floor radius, sweep radius, wall height (print mm)


def cove(col=None):
    """Seamless studio cove round the car: a round floor sweeping up into a wall, so no camera sees
    a horizon or the floor's edge against the backdrop. Rebuilds the Floor object's mesh in place."""
    r0, rc, h = COVE
    profile = [(0.0, 0.0), (r0, 0.0)]
    profile += [(r0 + rc * math.sin(a), rc * (1 - math.cos(a))) for a in (math.pi / 2 * k / 16 for k in range(1, 17))]
    profile.append((r0 + rc, h))
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [bm.edges.new(pair) for pair in zip(verts[:-1], verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, axis=(0, 0, 1), cent=(0, 0, 0), angle=2 * math.pi, steps=128, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    centre = min(bm.faces, key=lambda f: f.calc_center_median().length)
    if centre.normal.z < 0:                       # face the car
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Floor")
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    floor = bpy.data.objects.get("Floor")
    if floor is None:
        floor = bpy.data.objects.new("Floor", me)
        (col or _col()).objects.link(floor)
    else:
        old, floor.data = floor.data, me
        if old.users == 0:
            bpy.data.meshes.remove(old)
    floor.location = (96, 0, 0)
    floor.rotation_euler = (0, 0, 0)
    floor.scale = (1, 1, 1)
    floor.visible_shadow = False         # the HDRI's sun would otherwise cast the open-topped wall onto itself
    mat = bpy.data.materials.get("ShowroomFloor") or bpy.data.materials.new("ShowroomFloor")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.82, 0.80, 0.77, 1)
    # satin, not mirror-gloss: a glossier cove mirrors the HDRI's dark skyline band as a fake horizon
    bsdf.inputs["Roughness"].default_value = 0.45
    floor.data.materials.clear()
    floor.data.materials.append(mat)
    return floor


def _area(col, name, loc, energy, size):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.size = size
    ob = bpy.data.objects.new(name, data)
    ob.location = loc
    ob.rotation_euler = (Vector((96, 0, 20)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    col.objects.link(ob)


HDRI = ("studiolights/world", "city.exr")     # bundled with Blender
BACKDROP = (0.32, 0.30, 0.28, 1)
GROUND = (0.9, 0.88, 0.85, 1)       # the lit cove floor, as reflections should see it
CEILING = 0.25                      # the HDRI's brightness from ~17 degrees up, relative to its horizon
# how much of each softbox shows as a reflection: the big overhead one would otherwise lay a white
# sheet over the roof and hood (it still lights them)
SPECULAR = {"KeyLight": 0.5, "FillLight": 0.5, "TopLight": 0.15}


def _hdri():
    """The HDRI, packed into the .blend so it renders the same after a Blender upgrade or elsewhere."""
    img = bpy.data.images.get(HDRI[1])
    if img is None:
        path = os.path.join(bpy.utils.system_resource('DATAFILES', path=HDRI[0]) or "", HDRI[1])   # (only folders resolve)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"studio HDRI not found: {path}")
        img = bpy.data.images.load(path)
    if img.packed_file is None:
        img.pack()
    return img


def world(scene):
    """Plain warm-grey backdrop as seen by the camera, but an HDRI for everything else, so chrome
    and paint have a sky and a horizon to reflect instead of a flat grey. Below the horizon the
    HDRI's ground gives way to the cove floor's colour: EEVEE reflects the world, not the floor,
    so downward faces (bumper undersides, rocker trim) would otherwise mirror a brown street."""
    w = scene.world or bpy.data.worlds.new("World")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = _hdri()
    lit = nt.nodes.new("ShaderNodeBackground")
    lit.inputs["Strength"].default_value = 0.45
    plain = nt.nodes.new("ShaderNodeBackground")
    plain.inputs["Color"].default_value = BACKDROP
    plain.inputs["Strength"].default_value = 0.6
    ray = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    xyz = nt.nodes.new("ShaderNodeSeparateXYZ")
    horizon = nt.nodes.new("ShaderNodeMapRange")          # 0 looking down, 1 at and above the horizon
    horizon.inputs["From Min"].default_value, horizon.inputs["From Max"].default_value = -0.12, 0.0
    ground = nt.nodes.new("ShaderNodeMix")
    ground.data_type = 'RGBA'
    sock = {k.identifier: k for k in list(ground.inputs) + list(ground.outputs)}   # names repeat per data type
    sock["A_Color"].default_value = GROUND
    ceiling = nt.nodes.new("ShaderNodeMapRange")          # a showroom ceiling, not open sky: dim toward the zenith,
    ceiling.inputs["From Min"].default_value, ceiling.inputs["From Max"].default_value = 0.0, 0.3   # so roofs and hoods
    ceiling.inputs["To Min"].default_value, ceiling.inputs["To Max"].default_value = 1.0, CEILING  # keep their colour
    dim = nt.nodes.new("ShaderNodeVectorMath")
    dim.operation = 'SCALE'
    nt.links.new(coord.outputs["Generated"], xyz.inputs["Vector"])
    nt.links.new(xyz.outputs["Z"], horizon.inputs["Value"])
    nt.links.new(xyz.outputs["Z"], ceiling.inputs["Value"])
    nt.links.new(horizon.outputs["Result"], sock["Factor_Float"])
    nt.links.new(env.outputs["Color"], dim.inputs[0])
    nt.links.new(ceiling.outputs["Result"], dim.inputs["Scale"])
    nt.links.new(dim.outputs["Vector"], sock["B_Color"])
    nt.links.new(sock["Result_Color"], lit.inputs["Color"])
    nt.links.new(ray.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(lit.outputs["Background"], mix.inputs[1])
    nt.links.new(plain.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return w


def _camera(col, name, elev, azim, dist, target=(94, 0, 22), lens=60):
    e, a = math.radians(elev), math.radians(azim)
    t = Vector(target)
    d = Vector((-math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start, data.clip_end = 1, 5000
    ob = bpy.data.objects.new(name, data)
    ob.location = t + d * dist
    ob.rotation_euler = (t - ob.location).to_track_quat('-Z', 'Y').to_euler()
    col.objects.link(ob)
    return ob


def look(scene):
    """The studio look, applied without adding or moving cameras or lights: HDRI world, the cove,
    the softboxes' reflection strength, every camera seeing the whole cove, and shadows sampled
    finely enough that the big soft area lights leave no grain in their reflections."""
    _hdri()                                       # fail before changing anything
    world(scene)
    cove()
    for name, factor in SPECULAR.items():
        light = bpy.data.objects.get(name)
        if light:
            light.data.specular_factor = factor
    reach = 2 * (COVE[0] + COVE[1]) + COVE[2]      # the far side of the cove from anywhere inside it
    for cam in bpy.data.cameras:
        cam.clip_end = max(cam.clip_end, reach)
    scene.eevee.shadow_ray_count = 4
    scene.eevee.shadow_step_count = 16


def setup():
    scene = bpy.context.scene
    _hdri()
    col = _col(clear=True)
    for name in ("Camera", "Light"):
        ob = bpy.data.objects.get(name)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    _area(col, "KeyLight", (40, -180, 220), 9.0e5, 260)
    _area(col, "FillLight", (240, 160, 180), 4.0e5, 260)
    _area(col, "TopLight", (96, 0, 300), 6.0e5, 400)
    cams = {
        "Cam_Front34": _camera(col, "Cam_Front34", 10, -42, 520),
        "Cam_Rear34": _camera(col, "Cam_Rear34", 12, 215, 520),
        "Cam_Side": _camera(col, "Cam_Side", 2, -90, 600, lens=70),
    }
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    look(scene)
    scene.camera = cams["Cam_Front34"]
    return cams


def render(cam_name, path):
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[cam_name]
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
