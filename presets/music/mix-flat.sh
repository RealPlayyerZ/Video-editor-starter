#!/usr/bin/env bash
# mix-flat.sh — a constant music bed under the voice. No ducking, no fade-in, a short fade-out at the end.
#
#   usage: presets/music/mix-flat.sh <video.mp4> <music.mp3|wav|m4a> <out.mp4> [bed_db=-18] [tail_fade=2.0]
#
# The bed is looped to the video's length, set to bed_db (relative to the track's own level, so a quiet
# track stays quiet), mixed under the untouched voice, and faded out over the last tail_fade seconds. The
# video stream is copied, not re-encoded. When the footage carries its own audio that the bed must dip
# under, use the ducked mixer in .claude/skills/background-music/ instead.
set -euo pipefail
IN="${1:?video}"; MUSIC="${2:?music}"; OUT="${3:?out}"; DB="${4:--18}"; TAIL="${5:-2.0}"
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$IN" </dev/null)
FADE_AT=$(python3 -c "print(max(0.0, $DUR - $TAIL))")
ffmpeg -nostdin -v error -y -i "$IN" -stream_loop -1 -i "$MUSIC" \
  -filter_complex "[1:a]atrim=0:${DUR},asetpts=PTS-STARTPTS,volume=${DB}dB,afade=t=out:st=${FADE_AT}:d=${TAIL}[bed];[0:a][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 256k -movflags +faststart "$OUT"
OUTDUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT" </dev/null)
python3 - "$DUR" "$OUTDUR" <<'PY'
import sys
a, b = float(sys.argv[1]), float(sys.argv[2])
if abs(a - b) > 0.1:
    raise SystemExit("[mix-flat] ABORT: length changed %.3f -> %.3f" % (a, b))
print("[mix-flat] OK  %.2fs" % b)
PY
