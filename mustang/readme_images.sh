#!/bin/bash
# The README's photo-vs-model pairs: each dealer photo from origin_images/ beside a matching frame of
# the showcase animation (tmp/anim_frames, see animate.py), cropped to the photo's 3:2 and joined into
# one JPEG in docs/images/, the one folder of generated files that is tracked (GitHub shows it).
# Re-run after re-rendering the animation.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PHOTOS="$ROOT/origin_images"
FRAMES="$ROOT/tmp/anim_frames"
OUT="$ROOT/docs/images"
H=600         # height of each half
FRAME_W=1080  # a 1280x720 frame cropped to the photos' 3:2

# output name | photo | animation frame | left edge of the crop in the frame (px)
PAIRS=(
  "front34_driver|1967-ford-mustang-fastback.jpeg|1|60"
  "hood_open|1967-ford-mustang-fastback (11).jpeg|181|100"
  "engine_bay|1967-ford-mustang-fastback (13).jpeg|110|100"
  "front34_passenger|1967-ford-mustang-fastback (21).jpeg|440|170"
  "door_open|1967-ford-mustang-fastback (8).jpeg|372|200"
)

mkdir -p "$OUT"
for pair in "${PAIRS[@]}"; do
  IFS='|' read -r name photo frame x <<< "$pair"
  ffmpeg -v error -y -i "$PHOTOS/$photo" -i "$FRAMES/$(printf 'frame_%04d.png' "$frame")" -filter_complex \
    "[0]scale=-2:$H:flags=lanczos[p];[1]crop=$FRAME_W:720:$x:0,scale=-2:$H:flags=lanczos[m];[p][m]hstack" \
    -q:v 2 "$OUT/$name.jpg"
  echo "$OUT/$name.jpg"
done
