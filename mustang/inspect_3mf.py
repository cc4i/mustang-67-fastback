"""Summarise a Bambu project 3MF: settings, filaments, plates and what sits on each."""
import json
import sys
import xml.etree.ElementTree as ET
import zipfile


def main(path):
    z = zipfile.ZipFile(path)
    cfg = json.loads(z.read("Metadata/project_settings.config"))
    keys = ("printer_settings_id", "print_settings_id", "layer_height", "filament_colour", "filament_map")
    print({k: cfg.get(k) for k in keys})
    root = ET.fromstring(z.read("Metadata/model_settings.config"))
    objs = {}
    for o in root.findall("object"):
        meta = {m.get("key"): m.get("value") for m in o.findall("metadata")}
        parts = [{m.get("key"): m.get("value") for m in part.findall("metadata")} for part in o.findall("part")]
        if len(parts) > 1:               # an assembly: each part's own filament (Bambu also sets an object default)
            fils = "+".join(p.get("extruder") or meta.get("extruder", "?") for p in parts)
        else:
            fils = meta.get("extruder") or (parts[0].get("extruder", "?") if parts else "?")
        objs[o.get("id")] = f"{meta.get('name')}[f{fils}]"
    for p in root.findall("plate"):
        meta = {m.get("key"): m.get("value") for m in p.findall("metadata")}
        names = []
        for mi in p.findall("model_instance"):
            oid = {m.get("key"): m.get("value") for m in mi.findall("metadata")}.get("object_id")
            names.append(objs.get(oid, oid))
        print("plate", meta.get("plater_id"), len(names), sorted(names))


if __name__ == "__main__":
    main(sys.argv[1])
