"""Inspection snapshots from fixed angles via an OpenGL render of a helper camera."""
import math

import bpy
from mathutils import Vector

VIEWS = {
    # name: (elevation deg, azimuth deg); azimuth 0 = looking at the nose from ahead (-X)
    "front34": (12, -38),
    "rear34": (14, 222),
    "side": (0, -90),
    "front": (0, 0),
    "rear": (0, 180),
    "top": (89.9, -90),
    "under": (-89.9, -90),
}
TARGET = Vector((96, 0, 22))
CAM_NAME = "InspectCam"


def _camera():
    cam = bpy.data.objects.get(CAM_NAME)
    if cam is None:
        data = bpy.data.cameras.new(CAM_NAME)
        cam = bpy.data.objects.new(CAM_NAME, data)
        bpy.context.scene.collection.objects.link(cam)
    return cam


def snapshot(name, path, ortho=False, distance=420, res=(1400, 800), target=None, ortho_scale=210):
    scene = bpy.context.scene
    elev, azim = VIEWS[name]
    tgt = Vector(target) if target else TARGET
    e, a = math.radians(elev), math.radians(azim)
    direction = Vector((-math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    cam = _camera()
    cam.location = tgt + direction * distance
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    cam.data.ortho_scale = ortho_scale
    cam.data.lens = 70
    cam.data.clip_start = 1
    cam.data.clip_end = 5000
    old_cam = scene.camera
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = 'PNG'
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    shading = scene.display.shading
    shading.type = 'SOLID'
    shading.light = 'STUDIO'
    shading.color_type = 'MATERIAL'
    shading.show_specular_highlight = True
    shading.show_cavity = True
    shading.cavity_type = 'BOTH'
    shading.cavity_valley_factor = 2.0
    shading.curvature_valley_factor = 2.0
    ov = area.spaces[0].overlay
    with bpy.context.temp_override(area=area, region=[r for r in area.regions if r.type == 'WINDOW'][0]):
        ov.show_overlays = False
        bpy.ops.render.opengl(write_still=True, view_context=False)
        ov.show_overlays = True
    scene.camera = old_cam
    return path
