#!/bin/bash
# Build the native Bambu Studio project (X2D, 0.12 mm) for the Independent AI Edition (`v3.0.0`):
# packs all 55 STLs (75 printed pieces, including `waymo_pod.stl` in Burgundy #6B0F1A and
# `gc9a01_bezel.stl` in Silver #C8C8CC) across 9 auto-arranged plates inside the 256 x 256 mm X2D bed.
set -euo pipefail

BAMBU=/Applications/BambuStudio.app/Contents/MacOS/BambuStudio
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
STL="$ROOT/output/ai_edition/stl"
OUT="${1:-$ROOT/output/ai_edition/mustang_67_ai_edition_x2d.3mf}"
WORK="$(mktemp -d /tmp/mustang_ai_project.XXXXXX)"
trap 'echo "make_ai_project: failed (work dir $WORK)" >&2' ERR

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
    echo "make_ai_project: Bambu Studio failed on group $name:" >&2
    tail -n 20 "$WORK/$name.log" >&2
    return 1
  fi
}

build_group 1_body 1 --assemble body.stl:1 windshield.stl:1:2 rear_glass.stl:1:2
build_group 1_hood 1 hood.stl:1 trunk_lid.stl:1
build_group 1_doors 1 door_l.stl:1 door_r.stl:1 waymo_pod.stl:1
build_group 2_black 2 chassis.stl:1 tire_x4.stl:4 grille.stl:1 axle.stl:1 knuckle_l.stl:1 knuckle_r.stl:1 steering_link.stl:1 interior_tub.stl:1 steering_wheel.stl:1 \
  bay_tub.stl:1 boot_tub.stl:1 valve_cover_r.stl:1 valve_cover_l.stl:1 air_cleaner.stl:1 brace.stl:1 hood_prop.stl:1 door_card_l.stl:1 door_card_r.stl:1 diff_cover.stl:1 motor_shim_x2.stl:2
build_group 3_silver 3 rim_x4.stl:4 bumper_front.stl:1 grille_surround.stl:1 driveshaft.stl:1 exhaust_x2.stl:2
build_group 3_silver_small 3 corral_emblem.stl:1 fog_lamp_x2.stl:2 headlight_x2.stl:2 park_light_x2.stl:2 \
  taillight_bezel_r_x3.stl:3 taillight_bezel_l_x3.stl:3 gas_cap.stl:1 mirror.stl:1 backup_light_x2.stl:2 \
  vent_window_r.stl:1 vent_window_l.stl:1 pinion_gear.stl:1 axle_gear.stl:1 \
  motor_coupler_1p0.stl:1 motor_coupler_1p5.stl:1 motor_coupler_tube.stl:1 motor_coupler_n25.stl:1 gc9a01_bezel.stl:1
build_group 3_bumper 3 bumper_rear.stl:1
build_group 4_red 4 taillight_lens_r_x3.stl:3 taillight_lens_l_x3.stl:3
build_group 5_blue 5 engine_block.stl:1

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
    host.setdefault(g, f)
part_of = {m["file"]: m.get("part_of") for m in manifest}
bad = sorted(set(want) ^ set(used)) + [f for f in want if f in used and used[f] != want[f]]
bad += [f for f, k in lines.items() if k > 1]
bad += [f for f, h in part_of.items() if h and (group.get(f, "-") == "-" or host[group[f]] != h)]
bad += [f for f, g in group.items() if g != "-" and f != host[g] and part_of.get(f) != host[g]]
if bad:
    sys.exit(f"plate groups disagree with the AI export manifest: {bad}")
PY

python3 "$HERE/merge_3mf.py" "$WORK/merged.3mf" "$WORK/1_body.3mf" "$WORK/1_hood.3mf" "$WORK/1_doors.3mf" "$WORK/2_black.3mf" "$WORK/3_silver.3mf" "$WORK/3_silver_small.3mf" "$WORK/3_bumper.3mf" "$WORK/4_red.3mf" "$WORK/5_blue.3mf"

if ! "$BAMBU" --debug 2 --arrange 0 --outputdir "$WORK" --export-3mf final.3mf "$WORK/merged.3mf" > "$WORK/final.log" 2>&1; then
  echo "make_ai_project: Bambu Studio failed re-saving the project:" >&2
  tail -n 20 "$WORK/final.log" >&2
  exit 1
fi

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
    sys.exit(f"the AI project's plates disagree with the export manifest (file: placed count): {bad}")
PY

python3 "$HERE/check_plates.py" "$WORK/final.3mf" > "$WORK/check_plates.txt"
mkdir -p "$(dirname "$OUT")"
cp "$WORK/final.3mf" "$OUT"
echo "AI Edition project: $OUT  (work dir $WORK)"
