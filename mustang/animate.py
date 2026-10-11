"""Showcase animation: the hood opens on its hinge, the camera takes a look into the engine
bay and the hood closes again; then both doors swing open for a look into the cabin and close.

The live build objects carry dozens of boolean modifiers, far too slow to re-evaluate every
frame, so the animation uses baked copies in a "Showcase" collection; the build collections are
only hidden (still evaluated, so exports keep working).

Run inside Blender:  import animate; animate.setup(); animate.play()   (or animate.render())

To render without blocking the UI, save the .blend after setup() and render it headless from the
project root (frames go to tmp/anim_frames):
  blender -b output/mustang_67_fastback.blend --python-expr "import sys; sys.path[:0] = ['mustang']; import animate; animate.render()"
"""
import math
import os

import bpy
from mathutils import Vector

import doors
import engine_bay
import paths

SHOWCASE = "Showcase"
BUILD_COLLECTIONS = ("Body", "Wheels", "Parts", "Accessories")
FPS = 24
# (frame, hood degrees)
HOOD_KEYS = [(1, 0.0), (24, 0.0), (84, engine_bay.HOOD_OPEN_DEG), (160, engine_bay.HOOD_OPEN_DEG), (216, 0.0), (240, 0.0)]
PROP_SHOWN = (84, 160)           # prop rod in place while the hood is up
# (frame, door degrees): both doors swing open after the hood has closed
DOOR_KEYS = [(1, 0.0), (262, 0.0), (310, doors.OPEN_DEG), (372, doors.OPEN_DEG), (420, 0.0)]
# camera: (frame, elevation deg, azimuth deg, distance mm, target xyz mm)
CAMERA_KEYS = [
    (1, 12, -40, 330, (90, 0, 22)),
    (24, 14, -36, 310, (88, 0, 24)),
    (84, 24, -28, 230, (60, 0, 30)),
    (110, 55, -10, 150, (45, 0, 30)),      # looking down into the bay, like the photo
    (135, 45, 30, 160, (45, 0, 30)),       # around to the other side
    (160, 24, 20, 230, (60, 0, 30)),
    (216, 14, -36, 310, (88, 0, 24)),
    (240, 12, -40, 330, (90, 0, 22)),
    (255, 12, 10, 330, (95, 0, 22)),       # round the nose to the right-hand side
    (275, 14, 60, 320, (100, 0, 22)),
    (310, 18, 80, 290, (100, 8, 24)),
    (345, 26, 118, 230, (98, 18, 26)),     # from behind the open right door, into the cabin
    (372, 22, 100, 270, (98, 6, 25)),
    (420, 12, 62, 330, (100, 0, 22)),
    (440, 12, 45, 340, (100, 0, 22)),
]
END = 440


def _collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _layer_collection(name, lc=None):
    lc = lc or bpy.context.view_layer.layer_collection
    if lc.collection.name == name:
        return lc
    for child in lc.children:
        found = _layer_collection(name, child)
        if found:
            return found
    return None


def bake_showcase():
    """Baked (modifier-applied) copies of every visible part; returns {original name: copy}."""
    col = _collection(SHOWCASE)
    for ob in list(col.objects):
        if ob.type != 'MESH':
            continue                      # the camera and its target are kept and re-keyed by setup()
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for name in BUILD_COLLECTIONS:
        lc = _layer_collection(name)
        if lc:
            lc.hide_viewport = False
    bpy.data.objects["Hood"].rotation_euler = (0, 0, 0)
    for side in doors.SIDES:
        bpy.data.objects[f"Door_{doors.tag(side)}"].rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    copies = {}
    for name in BUILD_COLLECTIONS:
        for src in bpy.data.collections[name].objects:
            if src.type != 'MESH':
                continue
            me = bpy.data.meshes.new_from_object(src.evaluated_get(dg))
            me.name = f"SC_{src.name}"
            ob = bpy.data.objects.new(f"SC_{src.name}", me)
            ob.matrix_world = src.matrix_world.copy()
            col.objects.link(ob)
            for poly in me.polygons:
                poly.use_smooth = True
            copies[src.name] = ob
    # crisp edges on the baked body (smooth shading across boolean cuts looks smeared)
    for ob in copies.values():
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
            bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    for name in BUILD_COLLECTIONS:
        _layer_collection(name).hide_viewport = True
        bpy.data.collections[name].hide_render = True
    bpy.data.collections["Cutters"].hide_render = True
    _layer_collection(SHOWCASE).hide_viewport = False      # may have been hidden for stills of the live build
    col.hide_render = False
    return copies


def _key_visibility(ob, shown):
    ob.hide_viewport = ob.hide_render = True
    for frame in (1,):
        ob.keyframe_insert("hide_viewport", frame=frame)
        ob.keyframe_insert("hide_render", frame=frame)
    for frame, hidden in ((shown[0], False), (shown[1], True)):
        ob.hide_viewport = ob.hide_render = hidden
        ob.keyframe_insert("hide_viewport", frame=frame)
        ob.keyframe_insert("hide_render", frame=frame)


def _camera_point(elev, azim, dist, target):
    e, a = math.radians(elev), math.radians(azim)
    d = Vector((-math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    return Vector(target) + d * dist


def setup():
    scene = bpy.context.scene
    copies = bake_showcase()
    hood = copies["Hood"]
    hood.animation_data_clear()
    for frame, deg in HOOD_KEYS:
        hood.rotation_euler = (0, math.radians(deg), 0)
        hood.keyframe_insert("rotation_euler", index=1, frame=frame)
    prop = copies["HoodProp"]
    prop.animation_data_clear()
    _key_visibility(prop, PROP_SHOWN)
    for side in doors.SIDES:                 # door copies keep their hinge-axis origin; card, vent window and mirror (if any) ride along
        t = doors.tag(side)
        door = copies[f"Door_{t}"]
        for rider in [copies[n] for n in (f"DoorCard_{t}", f"DoorVent_{t}", f"Mirror_{t}") if n in copies]:
            m = rider.matrix_world.copy()
            rider.parent = door
            rider.matrix_parent_inverse = door.matrix_world.inverted()
            rider.matrix_world = m
        door.animation_data_clear()
        for frame, deg in DOOR_KEYS:
            door.rotation_euler = (0, 0, math.radians(side * deg))
            door.keyframe_insert("rotation_euler", index=2, frame=frame)

    col = _collection(SHOWCASE)
    target = bpy.data.objects.get("SC_CamTarget")
    if target is None:
        target = bpy.data.objects.new("SC_CamTarget", None)
        col.objects.link(target)
    cam = bpy.data.objects.get("SC_Camera")
    if cam is None:
        cam = bpy.data.objects.new("SC_Camera", bpy.data.cameras.get("SC_Camera") or bpy.data.cameras.new("SC_Camera"))
        col.objects.link(cam)
    cam.data.lens = 50
    cam.data.clip_start, cam.data.clip_end = 1, 5000
    cam.constraints.clear()
    track = cam.constraints.new('TRACK_TO')
    track.target = target
    track.track_axis, track.up_axis = 'TRACK_NEGATIVE_Z', 'UP_Y'
    cam.animation_data_clear()
    target.animation_data_clear()
    for frame, elev, azim, dist, tgt in CAMERA_KEYS:
        cam.location = _camera_point(elev, azim, dist, tgt)
        cam.keyframe_insert("location", frame=frame)
        target.location = tgt
        target.keyframe_insert("location", frame=frame)
    scene.camera = cam
    scene.frame_start, scene.frame_end = 1, END
    scene.render.fps = FPS
    scene.frame_set(1)
    return {"parts": len(copies), "frames": END}


def play():
    """Look through the animation camera in material preview and start playback."""
    scene = bpy.context.scene
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces[0]
                space.shading.type = 'MATERIAL'
                space.overlay.show_overlays = False
                space.region_3d.view_perspective = 'CAMERA'
                region = next(r for r in area.regions if r.type == 'WINDOW')
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_center_camera()
                    scene.frame_set(1)
                    bpy.ops.screen.animation_play()
                return True
    return False


# EEVEE render time is linear in samples. 32 renders 40% faster than 48, and the difference between
# the two (PSNR 56 dB) is far below the error of the H.264 encode (45 dB at crf 18). Denoising,
# the adaptive noise threshold and persistent data are Cycles features; EEVEE ignores them.
def render(out_dir=os.path.join(paths.TMP, "anim_frames"), res=(1280, 720), samples=32):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = out_dir.rstrip("/") + "/frame_"
    bpy.ops.render.render(animation=True)
