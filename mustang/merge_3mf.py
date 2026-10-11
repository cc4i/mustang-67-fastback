"""Merge single-colour Bambu Studio projects into one multi-plate project.

Each input is a project exported by the Bambu Studio CLI (already arranged and valid). Its
plates become consecutive plates of the output, laid out on Bambu's plate grid (2 columns
for up to 4 plates, stride = bed size * 1.2). Settings come from the first input, so all
inputs must be built with the same printer/process/filament list.

usage: python3 merge_3mf.py OUT.3mf IN1.3mf [IN2.3mf ...]
"""
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

BED = 256.0
STRIDE = BED * 1.2          # PartPlateList: plate size * (1 + LOGICAL_PART_PLATE_GAP)
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
      "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"}
P_PATH = "{%s}path" % NS["p"]
P_UUID = "{%s}UUID" % NS["p"]


# applied to every object: Arachne walls print features down to ~0.1 mm (widening them to a printable
# bead) where the classic generator silently drops anything narrower than one 0.42 mm line, and a
# 1:24 model is full of such details (plug wires, fan blades, lettering, lamp rims)
ALL_OBJECT_SETTINGS = {"wall_generator": "arachne"}
# per-object overrides (Bambu stores them as object metadata); the print profile itself stays stock
OBJECT_SETTINGS = {
    # the cabin roof overhangs inside the hollow body: tree supports grow up through the open
    # underside and pull out through it; in the body colour, not the glass inlays' black (the default
    # would pick any of the object's filaments)
    "body.stl": {"enable_support": "1", "support_type": "tree(auto)", "support_on_build_plate_only": "1",
                 "support_filament": "1", "support_interface_filament": "1"},
    # the hood prints skin-up with its bracing underneath; the engine has pulleys and an alternator
    # hanging out sideways
    "hood.stl": {"enable_support": "1", "support_type": "tree(auto)", "support_on_build_plate_only": "1"},
    "engine_block.stl": {"enable_support": "1", "support_type": "tree(auto)", "support_on_build_plate_only": "1"},
    # the rear blade's ends sweep up, so it has no flat top to stand on: upright, supported under
    # its (hidden) lower edge and the guards
    "bumper_rear.stl": {"enable_support": "1", "support_type": "tree(auto)", "support_on_build_plate_only": "1"},
}


def columns(count):
    """PartPlateList::compute_colum_count."""
    value = math.sqrt(count)
    r = round(value)
    return r + 1 if value > r else r


def plate_offset(index, count):
    cols = columns(count)
    return (index % cols) * STRIDE, -(index // cols) * STRIDE


def read_project(path):
    z = zipfile.ZipFile(path)
    model = ET.fromstring(z.read("3D/3dmodel.model"))
    settings = ET.fromstring(z.read("Metadata/model_settings.config"))
    objects = {}
    for obj in model.find("m:resources", NS).findall("m:object", NS):
        comps = obj.findall("m:components/m:component", NS)      # one per part (several for an assembly)
        files = {c.get(P_PATH).lstrip("/") for c in comps}
        assert len(files) == 1, f"{path}: object {obj.get('id')} spans several model files"
        objects[obj.get("id")] = {
            "file": files.pop(),
            "parts": [(c.get("objectid"), c.get("transform")) for c in comps],
        }
    items = {}
    for item in model.find("m:build", NS).findall("m:item", NS):
        items[item.get("objectid")] = (item.get("transform"), item.get(P_UUID), item.get("printable", "1"))
    obj_settings = {o.get("id"): o for o in settings.findall("object")}
    plates = []
    for plate in settings.findall("plate"):
        ids = []
        for mi in plate.findall("model_instance"):
            meta = {m.get("key"): m.get("value") for m in mi.findall("metadata")}
            ids.append(meta["object_id"])
        plates.append(ids)
    return z, model, objects, items, obj_settings, plates


def complete_settings(cfg):
    """Fill what the CLI leaves out of exported (unsliced) projects.

    Without a nozzle inventory a dual-nozzle printer (X2D) fails to slice with "No valid nozzle
    found"; Bambu writes one standard nozzle per extruder when it slices, so do the same."""
    if not cfg.get("extruder_nozzle_stats"):
        volumes = cfg.get("nozzle_volume_type") or cfg.get("default_nozzle_volume_type") or ["Standard"]
        cfg["extruder_nozzle_stats"] = [f"{v}#1" for v in volumes]
    return cfg


def shift_transform(transform, dx, dy):
    v = [float(t) for t in transform.split()]
    v[9] += dx
    v[10] += dy
    return " ".join(f"{t:.9g}" for t in v)


def plate_label(path, q, count):
    """Plate name from the sub-project's file name: "2_black.3mf" -> "black" (then "black 2", ...)."""
    stem = os.path.splitext(os.path.basename(path))[0].split("_", 1)[-1].replace("_", " ")
    return stem if count == 1 else f"{stem} {q + 1}"


def merge(out_path, in_paths):
    projects = [read_project(p) for p in in_paths]
    total_plates = sum(len(p[5]) for p in projects)
    meta_xml = "".join(f' <metadata name="{m.get("name")}">{m.text or ""}</metadata>\n'
                       for m in projects[0][1].findall("m:metadata", NS))

    resources, build, rels, settings_objects, settings_plates = [], [], [], [], []
    files = {}
    g = 0                  # global object counter
    next_id = 0            # resource ids: each object's part meshes, then the object itself (as Bambu numbers them)
    plate_index = 0
    identify = 100
    for path, (z, model, objects, items, obj_settings, plates) in zip(in_paths, projects):
        for q, plate_ids in enumerate(plates):
            sdx, sdy = plate_offset(q, len(plates))
            gdx, gdy = plate_offset(plate_index, total_plates)
            instances = []
            for old_id in plate_ids:
                g += 1
                o = objects[old_id]
                new_ids = {old: str(next_id + k + 1) for k, (old, _) in enumerate(o["parts"])}
                wrap_id = next_id + len(o["parts"]) + 1
                next_id = wrap_id
                src = z.read(o["file"]).decode()
                # Bambu identifies objects by these UUIDs (same scheme as its exporter), so every merged
                # object needs fresh ones: the inputs all number their objects from 1 and would collide.
                # One pass, so a part's new id can't be mistaken for another part's old one.
                part_index = {old: k for k, (old, _) in enumerate(o["parts"])}
                src = re.sub(r'<object id="(\d+)" p:UUID="[^"]*"',
                             lambda m: (f'<object id="{new_ids[m[1]]}" p:UUID="{g:04x}{part_index[m[1]]:04x}'
                                        '-81cb-4c03-9d28-80fed5dfa1dc"'), src)
                files[f"3D/Objects/object_{g}.model"] = src
                rels.append(f' <Relationship Target="/3D/Objects/object_{g}.model" Id="rel-{g}" '
                            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
                components = "".join(
                    f'    <component p:path="/3D/Objects/object_{g}.model" objectid="{new_ids[old]}" '
                    f'p:UUID="{g:04x}{k:04x}-b206-40ff-9872-83e8017abed1" transform="{transform}"/>\n'
                    for k, (old, transform) in enumerate(o["parts"]))
                resources.append(
                    f'  <object id="{wrap_id}" p:UUID="{g:08x}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n   <components>\n'
                    f'{components}   </components>\n  </object>')
                transform, _, printable = items[old_id]
                transform = shift_transform(transform, gdx - sdx, gdy - sdy)
                build.append(f'  <item objectid="{wrap_id}" p:UUID="{wrap_id:08x}-b1ec-4553-aec9-835e5b724bb4" '
                             f'transform="{transform}" printable="{printable}"/>')
                so = obj_settings[old_id]
                so = ET.fromstring(ET.tostring(so))
                so.set("id", str(wrap_id))
                parts = so.findall("part")
                for part in parts:
                    part.set("id", new_ids[part.get("id")])
                name_meta = next(m for m in so.findall("metadata") if m.get("key") == "name")
                if len(parts) > 1:           # an assembly ("Assembly") is its host, the first part, plus inlays
                    name_meta.set("value", next(m.get("value") for m in parts[0].findall("metadata") if m.get("key") == "name"))
                for key, value in {**ALL_OBJECT_SETTINGS, **OBJECT_SETTINGS.get(name_meta.get("value"), {})}.items():
                    ET.SubElement(so, "metadata", {"key": key, "value": value})
                settings_objects.append(ET.tostring(so, encoding="unicode"))
                identify += 11
                instances.append(
                    f'    <model_instance>\n      <metadata key="object_id" value="{wrap_id}"/>\n'
                    f'      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="{identify}"/>\n'
                    '    </model_instance>')
            n = plate_index + 1
            name = plate_label(path, q, len(plates))
            settings_plates.append(
                f'  <plate>\n    <metadata key="plater_id" value="{n}"/>\n    <metadata key="plater_name" value="{name}"/>\n'
                '    <metadata key="locked" value="false"/>\n    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
                '    <metadata key="gcode_file" value=""/>\n'
                f'    <metadata key="thumbnail_file" value="Metadata/plate_{n}.png"/>\n'
                f'    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_{n}.png"/>\n'
                f'    <metadata key="top_file" value="Metadata/top_{n}.png"/>\n'
                f'    <metadata key="pick_file" value="Metadata/pick_{n}.png"/>\n'
                + "\n".join(instances) + "\n  </plate>")
            for src_name, dst_name in ((f"plate_{q + 1}.png", f"plate_{n}.png"), (f"plate_{q + 1}_small.png", f"plate_{n}_small.png"),
                                       (f"plate_no_light_{q + 1}.png", f"plate_no_light_{n}.png"),
                                       (f"top_{q + 1}.png", f"top_{n}.png"), (f"pick_{q + 1}.png", f"pick_{n}.png")):
                try:
                    files["Metadata/" + dst_name] = z.read("Metadata/" + src_name)
                except KeyError:
                    pass
            plate_index += 1

    first = projects[0][0]
    files["3D/3dmodel.model"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">\n'
        + meta_xml + ' <resources>\n' + "\n".join(resources) + '\n </resources>\n <build>\n' + "\n".join(build)
        + '\n </build>\n</model>\n')
    files["3D/_rels/3dmodel.model.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        + "\n".join(rels) + '\n</Relationships>\n')
    files["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "\n".join(settings_objects) + "\n"
        + "\n".join(settings_plates) + '\n  <assemble>\n  </assemble>\n</config>\n')
    files["Metadata/cut_information.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<objects>\n'
        + "".join(f' <object id="{i}">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n' for i in range(1, g + 1))
        + '</objects>\n')
    files["Metadata/filament_sequence.json"] = json.dumps(
        {f"plate_{i}": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []} for i in range(1, total_plates + 1)},
        separators=(",", ":"))
    for name in ("[Content_Types].xml", "_rels/.rels", "Metadata/slice_info.config"):
        files[name] = first.read(name)
    files["Metadata/project_settings.config"] = json.dumps(
        complete_settings(json.loads(first.read("Metadata/project_settings.config"))), indent=4)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out:
        order = ["[Content_Types].xml", "_rels/.rels"] + sorted(k for k in files if k not in ("[Content_Types].xml", "_rels/.rels"))
        for name in order:
            data = files[name]
            out.writestr(name, data if isinstance(data, bytes) else data.encode())
    return total_plates, g


if __name__ == "__main__":
    plates, objs = merge(sys.argv[1], sys.argv[2:])
    print(f"merged {objs} objects onto {plates} plates -> {sys.argv[1]}")
