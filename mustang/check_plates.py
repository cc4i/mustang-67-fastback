"""Check every object in a Bambu project lies inside its plate's printable area."""
import math
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

BED, STRIDE = 256.0, 256.0 * 1.2
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
      "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"}


def columns(count):
    value = math.sqrt(count)
    r = round(value)
    return r + 1 if value > r else r


def main(path, margin=1.0):
    z = zipfile.ZipFile(path)
    model = ET.fromstring(z.read("3D/3dmodel.model"))
    settings = ET.fromstring(z.read("Metadata/model_settings.config"))
    names = {o.get("id"): {m.get("key"): m.get("value") for m in o.findall("metadata")}.get("name") for o in settings.findall("object")}
    comps = {}             # object id -> [(model file, mesh id, transform)], one per part
    for obj in model.find("m:resources", NS).findall("m:object", NS):
        comps[obj.get("id")] = [(c.get("{%s}path" % NS["p"]).lstrip("/"), c.get("objectid"), [float(t) for t in c.get("transform").split()])
                                for c in obj.findall("m:components/m:component", NS)]
    items = {i.get("objectid"): [float(t) for t in i.get("transform").split()] for i in model.find("m:build", NS).findall("m:item", NS)}
    plates = settings.findall("plate")
    cols = columns(len(plates))
    ok = True
    for idx, plate in enumerate(plates):
        ox, oy = (idx % cols) * STRIDE, -(idx // cols) * STRIDE
        for mi in plate.findall("model_instance"):
            oid = {m.get("key"): m.get("value") for m in mi.findall("metadata")}["object_id"]
            it = items[oid]
            xs, ys = [], []
            for fpath, mesh_id, ct in comps[oid]:
                xml = z.read(fpath).decode()
                mesh = re.search(r'<object id="%s"[^>]*>(.*?)</object>' % mesh_id, xml, re.S)[1]
                for vx, vy, vz in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', mesh):
                    x, y, zz = float(vx), float(vy), float(vz)
                    # component transform then item transform (3x3 rotation + translation, row-major 3MF order)
                    x1 = ct[0] * x + ct[3] * y + ct[6] * zz + ct[9]
                    y1 = ct[1] * x + ct[4] * y + ct[7] * zz + ct[10]
                    z1 = ct[2] * x + ct[5] * y + ct[8] * zz + ct[11]
                    xs.append(it[0] * x1 + it[3] * y1 + it[6] * z1 + it[9] - ox)
                    ys.append(it[1] * x1 + it[4] * y1 + it[7] * z1 + it[10] - oy)
            inside = min(xs) >= margin and min(ys) >= margin and max(xs) <= BED - margin and max(ys) <= BED - margin
            ok &= inside
            print(f"plate {idx + 1} {names[oid]:<28} x {min(xs):6.1f}..{max(xs):6.1f}  y {min(ys):6.1f}..{max(ys):6.1f}  "
                  f"{'OK' if inside else 'OUTSIDE'}")
    print("ALL INSIDE" if ok else "SOME OUTSIDE")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) else 1)
