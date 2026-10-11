# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["cadquery-ocp==8.0.1.1"]
# ///
"""STEP solids for CAD tools such as Shapr3D, which imports STL meshes only as references it cannot
measure or edit. Every part listed in output/stl_assembled/manifest.json (export.run_assembled)
becomes a closed solid in its place on the car, in print millimetres: each triangle a planar face,
exactly coplanar neighbours merged, so curved surfaces stay faceted at the full mesh detail.
Writes one file per part into output/step/ (plus report.json) and the whole car as one assembly
of named, coloured parts, output/mustang_67_fastback.step.

Runs outside Blender on OpenCascade from PyPI, which uv fetches:
  uv run mustang/make_step.py [STL_DIR [OUT_DIR]]
Exits 1 unless every part is a valid closed solid with the volume of its mesh.
"""
import json
import os
import sys
import time

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShapeOnMesh, BRepBuilderAPI_MakeSolid
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.Message import Message, Message_Gravity
from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
from OCP.RWStl import RWStl
from OCP.ShapeFix import ShapeFix_Shape
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shell
from OCP.UnitsMethods import UnitsMethods_LengthUnit_Millimeter
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSEMBLY = "mustang_67_fastback"
# faces merge only when their planes agree this closely (radians, mm), so every merged face stays
# exactly flat; the boolean output's flat regions agree to ~1e-9 rad
FLAT_ANGLE, FLAT_DIST = 1e-9, 1e-6
VOLUME_TOL = 1e-4     # relative change allowed from merging and healing


def faces(shape):
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        yield ex.Current()
        ex.Next()


def volume(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def solid_from_stl(path):
    """The mesh in `path` as a solid of planar faces with coplanar neighbours merged, and a report."""
    mesh = RWStl.ReadFile_s(path)                 # coincident vertices welded
    built = BRepBuilderAPI_MakeShapeOnMesh(mesh)  # a face per triangle, edges shared by construction
    built.Build()
    shell, builder = TopoDS_Shell(), BRep_Builder()
    builder.MakeShell(shell)
    for face in faces(built.Shape()):
        builder.Add(shell, face)
    closed = BRep_Tool.IsClosed_s(shell)
    shell.Closed(closed)
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    mesh_volume = volume(solid)
    unify = ShapeUpgrade_UnifySameDomain(solid, True, True, False)
    unify.SetAngularTolerance(FLAT_ANGLE)
    unify.SetLinearTolerance(FLAT_DIST)
    unify.Build()
    solid = unify.Shape()
    healed = not BRepCheck_Analyzer(solid).IsValid()
    if healed:
        fix = ShapeFix_Shape(solid)
        fix.Perform()
        solid = fix.Shape()
    v = volume(solid)
    return solid, {
        "triangles": mesh.NbTriangles(), "faces": sum(1 for _ in faces(solid)), "closed": closed,
        "valid": BRepCheck_Analyzer(solid).IsValid(), "healed": healed, "volume_mm3": round(v, 3),
        "volume_change": abs(v - mesh_volume) / abs(mesh_volume) if mesh_volume else 1.0,
    }


def write_step(path, parts, assembly=None):
    """Write (name, solid, colour hex) parts as named, coloured STEP products in millimetres:
    free-standing, or as the components of one assembly named `assembly`."""
    doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    XCAFApp_Application.GetApplication_s().InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1.0, UnitsMethods_LengthUnit_Millimeter)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colours = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    top = shapes.NewShape() if assembly else None
    if assembly:
        TDataStd_Name.Set_s(top, TCollection_ExtendedString(assembly))
    for name, solid, colour in parts:
        label = shapes.AddShape(solid, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        colours.SetColor(label, Quantity_Color(r, g, b, Quantity_TOC_sRGB), XCAFDoc_ColorSurf)
        if assembly:
            TDataStd_Name.Set_s(shapes.AddComponent(top, label, TopLoc_Location()), TCollection_ExtendedString(name))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()              # first: creating the first writer resets the statics
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 0)    # planar faces need no pcurves; halves the file
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    return writer.Transfer(doc, STEPControl_AsIs) and writer.Write(path) == IFSelect_RetDone


def main(stl_dir, out_dir):
    printers = Message.DefaultMessenger_s().Printers()     # the STEP writer's progress chatter
    for i in range(1, printers.Length() + 1):
        printers.Value(i).SetTraceLevel(Message_Gravity.Message_Fail)
    with open(os.path.join(stl_dir, "manifest.json")) as f:
        manifest = json.load(f)
    step_dir = os.path.join(out_dir, "step")
    os.makedirs(step_dir, exist_ok=True)
    parts, report = [], {}
    for entry in manifest:
        start = time.time()
        solid, info = solid_from_stl(os.path.join(stl_dir, entry["file"]))
        fname = os.path.splitext(entry["file"])[0] + ".step"
        info["written"] = write_step(os.path.join(step_dir, fname), [(entry["object"], solid, entry["colour"])])
        info["seconds"] = round(time.time() - start, 1)
        report[fname] = info
        parts.append((entry["object"], solid, entry["colour"]))
        print(f"{fname}: {info['triangles']} triangles -> {info['faces']} faces in {info['seconds']} s", flush=True)
    for name in os.listdir(step_dir):            # parts renamed or dropped since
        if name.endswith(".step") and name not in report:
            os.remove(os.path.join(step_dir, name))
    with open(os.path.join(step_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    start = time.time()
    assembled = write_step(os.path.join(out_dir, f"{ASSEMBLY}.step"), parts, ASSEMBLY)
    print(f"{ASSEMBLY}.step: {len(parts)} parts in {time.time() - start:.0f} s, written: {assembled}")
    problems = {name: info for name, info in report.items()
                if not (info["closed"] and info["valid"] and info["written"] and info["volume_mm3"] > 0
                        and info["volume_change"] <= VOLUME_TOL)}
    for name, info in problems.items():
        print(f"PROBLEM {name}: {info}")
    return assembled and not problems


if __name__ == "__main__":
    args = sys.argv[1:] + [None, None]
    sys.exit(0 if main(args[0] or os.path.join(ROOT, "output", "stl_assembled"),
                       args[1] or os.path.join(ROOT, "output")) else 1)
