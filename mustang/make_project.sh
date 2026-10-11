#!/bin/bash
# Build the native Bambu Studio project (X2D, 0.12 mm) from the exported STLs:
# one group per filament colour, each arranged by Bambu Studio itself so every part sits
# inside the 256 x 256 mm bed (a group that doesn't fit spills onto extra plates). The body,
# hood, doors and rear bumper get plates of their own: their supports crowd neighbours. The
# body carries its black window glass as extra parts of the same object.
set -euo pipefail

BAMBU=/Applications/BambuStudio.app/Contents/MacOS/BambuStudio
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
STL="$ROOT/output/stl"
OUT="${1:-$ROOT/output/mustang_67_fastback_1-24.3mf}"
WORK="$(mktemp -d /tmp/mustang_project.XXXXXX)"
trap 'echo "make_project: failed (work dir $WORK)" >&2' ERR

# The CLI ignores preset inheritance, so feed it flattened copies of the system presets,
# plus one filament copy per colour: 1 burgundy body, 2 black, 3 silver/chrome, 4 red lenses, 5 engine blue.
python3 "$HERE/bambu_presets.py" "$WORK/presets" > /dev/null
FILS=""
i=0
for colour in "#6B0F1A" "#1A1A1A" "#C8C8CC" "#B01010" "#2B59C3"; do
  i=$((i + 1))
  python3 - "$WORK/presets/filament.json" "$WORK/presets/filament_$i.json" "$colour" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["default_filament_colour"] = [sys.argv[3]]
d["filament_colour"] = [sys.argv[3]]
json.dump(d, open(sys.argv[2], "w"), indent=1)
PY
  FILS="$FILS${FILS:+;}$WORK/presets/filament_$i.json"
done

USED="$WORK/used.txt"
# name filament [--assemble] "file:count[:filament]" ...
# --assemble merges the files into one object, one part per file, each keeping its exported
# coordinates and its own filament (an inlay printed in another colour inside its host).
build_group() {
  local name=$1 fil=$2
  shift 2
  local mode=() group=-
  if [[ $1 == --assemble ]]; then mode=(--assemble); group=$name; shift; fi
  local files=() ids=() spec f n sf k
  for spec in "$@"; do
    IFS=: read -r f n sf <<< "$spec"
    sf=${sf:-$fil}
    echo "$f $n $sf $group" >> "$USED"
    for ((k = 0; k < n; k++)); do files+=("$STL/$f"); ids+=("$sf"); done
  done
  if ! "$BAMBU" --debug 2 \
    --load-settings "$WORK/presets/machine.json;$WORK/presets/process.json" \
    --load-filaments "$FILS" \
    --load-filament-ids "$(IFS=,; echo "${ids[*]}")" \
    ${mode[@]+"${mode[@]}"} --arrange 1 --outputdir "$WORK" --export-3mf "$name.3mf" \
    "${files[@]}" > "$WORK/$name.log" 2>&1; then
    echo "make_project: Bambu Studio failed on group $name:" >&2
    tail -n 20 "$WORK/$name.log" >&2
    return 1
  fi
}

build_group 1_body 1 --assemble body.stl:1 windshield.stl:1:2 rear_glass.stl:1:2    # black glass inlays
build_group 1_hood 1 hood.stl:1            # own plate: its supports collide with neighbours' paths (body, doors)
build_group 1_doors 1 door_l.stl:1 door_r.stl:1
build_group 2_black 2 chassis.stl:1 tire_x4.stl:4 grille.stl:1 axle_x2.stl:2 interior_tub.stl:1 steering_wheel.stl:1 \
  bay_tub.stl:1 valve_cover_r.stl:1 valve_cover_l.stl:1 air_cleaner.stl:1 brace.stl:1 hood_prop.stl:1 door_card_l.stl:1 door_card_r.stl:1 diff_cover.stl:1
build_group 3_silver 3 rim_x4.stl:4 grille_surround.stl:1 corral_emblem.stl:1 fog_lamp_x2.stl:2 headlight_x2.stl:2 park_light_x2.stl:2 \
  taillight_bezel_r_x3.stl:3 taillight_bezel_l_x3.stl:3 gas_cap.stl:1 bumper_front.stl:1 mirror.stl:1 exhaust_x2.stl:2 backup_light_x2.stl:2 vent_window_r.stl:1 vent_window_l.stl:1
build_group 3_bumper 3 bumper_rear.stl:1   # own plate: it stands upright on tree supports that crowd its neighbours
build_group 4_red 4 taillight_lens_r_x3.stl:3 taillight_lens_l_x3.stl:3
build_group 5_blue 5 engine_block.stl:1

# every exported part requested once, the right number of times, in its own colour, and every
# inlay assembled into its host's object, host first
python3 - "$STL/manifest.json" "$USED" <<'PY'
import json, sys
colours = ["#6B0F1A", "#1A1A1A", "#C8C8CC", "#B01010", "#2B59C3"]
manifest = json.load(open(sys.argv[1]))
want = {m["file"]: (m["qty"], m["colour"]) for m in manifest}
used, group, host, lines = {}, {}, {}, {}
for line in open(sys.argv[2]):
    f, n, fil, g = line.split()
    used[f] = (int(n), colours[int(fil) - 1])
    group[f] = g
    lines[f] = lines.get(f, 0) + 1
    host.setdefault(g, f)            # an assembly is named after (and takes the settings of) its first part
part_of = {m["file"]: m.get("part_of") for m in manifest}
bad = sorted(set(want) ^ set(used)) + [f for f in want if f in used and used[f] != want[f]]
bad += [f for f, k in lines.items() if k > 1]                    # listed in more than one group: printed twice
bad += [f for f, h in part_of.items() if h and (group.get(f, "-") == "-" or host[group[f]] != h)]
bad += [f for f, g in group.items() if g != "-" and f != host[g] and part_of.get(f) != host[g]]
if bad:
    sys.exit(f"plate groups disagree with the export manifest: {bad}")
PY
python3 "$HERE/merge_3mf.py" "$WORK/merged.3mf" "$WORK/1_body.3mf" "$WORK/1_hood.3mf" "$WORK/1_doors.3mf" "$WORK/2_black.3mf" "$WORK/3_silver.3mf" "$WORK/3_bumper.3mf" "$WORK/4_red.3mf" \
  "$WORK/5_blue.3mf"

# Re-save through Bambu Studio so the final file is written by Bambu itself.
if ! "$BAMBU" --debug 2 --arrange 0 --outputdir "$WORK" --export-3mf final.3mf "$WORK/merged.3mf" > "$WORK/final.log" 2>&1; then
  echo "make_project: Bambu Studio failed re-saving the project:" >&2
  tail -n 20 "$WORK/final.log" >&2
  exit 1
fi

# what Bambu actually produced: every part on a plate the manifest's number of times (an object the
# arranger could not place is left off every plate without an error), and inside its plate
python3 - "$STL/manifest.json" "$WORK/final.3mf" <<'PY'
import json, sys, zipfile
import xml.etree.ElementTree as ET
manifest = json.load(open(sys.argv[1]))
cfg = ET.fromstring(zipfile.ZipFile(sys.argv[2]).read("Metadata/model_settings.config"))
meta = lambda el: {m.get("key"): m.get("value") for m in el.findall("metadata")}
parts = {o.get("id"): [meta(p).get("name") for p in o.findall("part")] or [meta(o).get("name")] for o in cfg.findall("object")}
placed = {}
for plate in cfg.findall("plate"):
    for mi in plate.findall("model_instance"):
        for name in parts[meta(mi)["object_id"]]:
            placed[name] = placed.get(name, 0) + 1
bad = {m["file"]: placed.get(m["file"], 0) for m in manifest if placed.get(m["file"], 0) != m["qty"]}
bad.update({f: n for f, n in placed.items() if f not in {m["file"] for m in manifest}})
if bad:
    sys.exit(f"the project's plates disagree with the export manifest (file: placed count): {bad}")
PY
python3 "$HERE/check_plates.py" "$WORK/final.3mf" > "$WORK/check_plates.txt"
cp "$WORK/final.3mf" "$OUT"
echo "project: $OUT  (work dir $WORK)"
