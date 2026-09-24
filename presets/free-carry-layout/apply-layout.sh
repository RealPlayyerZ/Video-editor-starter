#!/usr/bin/env bash
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# apply-layout.sh — lay the locked SUBSCRIBE-bug over a finished cut.
#   apply-layout.sh <in.mp4> <out.mp4> [at_seconds=22]
# The bug is version F (2026-09-21, his pick): logo from assets/logos/logo.png (see extract_logo.py for lifting one out of a video),
# fire embers on the raised arc. Placement is the house standard — top-left, the LINE's own top-left corner
# landing at (95,108), which is where the reference channel's sits and keeps the ghost word clear of the frame edge.
# The strip is bigger than the line (it carries the ghost word and the ember margin), so the overlay offset is
# the anchor MINUS the line's position inside the strip; that comes from the sidecar, never hardcoded.
set -euo pipefail
cd "$(dirname "$0")/../.."
B=presets/free-carry-layout
IN="${1:?in}"; OUT="${2:?out}"
AT="${3:-$(python3 -c 'import json;print(json.load(open("presets/brand.json")).get("ask_at") or 22)' 2>/dev/null || echo 22)}"
[ -f "$B/free-carry-layout.mov" ] || { echo "[bug] no locked overlay — run run_test.sh F first" >&2; exit 1; }
OX=$(python3 -c "import json;d=json.load(open('$B/free-carry-layout.json'));print(95-d['line_x'])")
OY=$(python3 -c "import json;d=json.load(open('$B/free-carry-layout.json'));print(108-d['line_y'])")
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1:nk=1 "$IN" </dev/null)
echo "[bug] overlay at ($OX,$OY), appearing at ${AT}s, source fps $FPS"
# -reinit_filter 0: the base is a stitched cut and a colour-tag flip mid-file would otherwise rebuild the
# graph and restart the overlay's pts at 0 (the frozen-tail bug, 2026-09-15).
ffmpeg -nostdin -hide_banner -loglevel error -y -reinit_filter 0 \
  -i "$IN" -i "$B/free-carry-layout.mov" \
  -filter_complex "[1:v]format=rgba,setpts=PTS-STARTPTS+$AT/TB[bug];[0:v][bug]overlay=$OX:$OY:eof_action=pass:format=auto[v]" \
  -map "[v]" -map 0:a -r "$FPS" -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -c:a copy \
  -movflags +faststart "$OUT"
D1=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$IN" </dev/null)
D2=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT" </dev/null)
python3 - "$D1" "$D2" <<'PY'
import sys
a, b = float(sys.argv[1]), float(sys.argv[2])
if abs(a - b) > 0.15:
    raise SystemExit("[bug] ABORT: length changed %.3f -> %.3f" % (a, b))
print("[bug] OK  %.3f s in, %.3f s out" % (a, b))
PY
