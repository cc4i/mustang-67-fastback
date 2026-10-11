"""Flatten Bambu Studio system presets (resolve their `inherits` chains and `include` templates).

The Bambu Studio CLI does not resolve inheritance when presets are loaded from files, so
e.g. "0.12mm High Quality @BBL X2D" silently falls back to 0.2 mm layers. Nor does it apply
the templates a preset includes, which hold e.g. the X2D's own start / filament-change G-code
and the filament values for its second (Bowden) extruder. This writes self-contained copies
that keep the system names, so projects built from them open in the GUI as ordinary,
unmodified system presets.

usage: python3 bambu_presets.py OUT_DIR
"""
import json
import os
import sys

PROFILES = "/Applications/BambuStudio.app/Contents/Resources/profiles/BBL"
PRESETS = {
    "machine": "Bambu Lab X2D 0.4 nozzle",
    "process": "0.12mm High Quality @BBL X2D",
    "filament": "Bambu PLA Basic @BBL X2D 0.4 nozzle",
}


IDENTITY_KEYS = ("name", "type", "from", "instantiation", "inherits", "include", "setting_id")


def resolve(category, name):
    """The preset's settings as Bambu Studio loads them: the parent chain first, then each
    included template, then the preset's own keys."""
    path = os.path.join(PROFILES, category, name + ".json")
    with open(path) as f:
        data = json.load(f)
    parent = data.get("inherits")
    merged = resolve(category, parent) if parent else {}
    for template in data.get("include", []):
        merged.update({k: v for k, v in resolve(category, template).items() if k not in IDENTITY_KEYS})
    merged.update(data)
    return merged


def flatten(category, name):
    data = resolve(category, name)
    data.pop("inherits", None)
    data.pop("include", None)
    data["name"] = name
    data["from"] = "system"
    data["instantiation"] = "true"
    return data


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for category, name in PRESETS.items():
        data = flatten(category, name)
        with open(os.path.join(out_dir, f"{category}.json"), "w") as f:
            json.dump(data, f, indent=1)
        print(category, name, len(data), "keys", "layer_height=" + str(data.get("layer_height", "-")))


if __name__ == "__main__":
    main(sys.argv[1])
