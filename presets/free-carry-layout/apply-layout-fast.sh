#!/usr/bin/env bash
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# apply-layout-fast.sh — burn the locked "Subscribe for a Free Carry" layout into an ALREADY FINISHED master
# without re-encoding it.   apply-layout-fast.sh <in.mp4> <out.mp4> [at_seconds=22]
#
# The layout is 8 s long. Re-encoding a 27-minute 1440p60 master to add it costs ~40 minutes AND puts a second
# generation of lossy encoding through every frame of a file that is already final. Instead: cut at the
# KEYFRAMES bracketing the layout, re-encode only that window, stream-copy the rest.
#
# AUDIO IS NEVER CUT (2026-09-22). The first version split audio into three pieces and concatenated them. AAC
# frames are 1024 samples (~21 ms), so every concat boundary pads to a frame edge: the delivered file came out
# +0.152 s of audio against +0.033 s of video, i.e. the sound sat ~0.12 s behind the picture for the remaining
# 26 minutes. verify-final.py did NOT catch it -- it checks freezes, durations and peaks, not cross-file sync.
# So: the three parts are cut VIDEO-ONLY, concatenated, and the master's original audio stream is muxed back in
# whole with -c copy. Audio is then bit-identical to the master by construction and cannot drift.
#
# The cut points MUST be real keyframes or the copied parts start mid-GOP and glitch, so they are read off the
# file with ffprobe. The window is cut half a frame short of K2 so the tail's own K2 frame is not duplicated.
set -euo pipefail
cd "$(dirname "$0")/../.."
B=presets/free-carry-layout
IN="${1:?in}"; OUT="${2:?out}"
AT="${3:-$(python3 -c 'import json;print(json.load(open("presets/brand.json")).get("ask_at") or 22)' 2>/dev/null || echo 22)}"
[ -f "$B/free-carry-layout.mov" ] || { echo "[layout] no rendered overlay yet — run: python3 presets/free-carry-layout/build_layout.py   (reads your brand.json; renders free-carry-layout.mov once)" >&2; exit 1; }
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$B/free-carry-layout.mov" </dev/null)
END=$(python3 -c "print($AT + $DUR)")
FPSR=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1:nk=1 "$IN" </dev/null)
FPS=$(python3 -c "n,d='$FPSR'.split('/'); print(float(n)/float(d))")
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

KF=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 \
       -read_intervals "$(python3 -c "print(max(0,$AT-12))")%+$(python3 -c "print(int($DUR)+30)")" "$IN" </dev/null \
     | awk -F, '$2 ~ /K/ {print $1}')
read K1 K2 < <(python3 -c "
ks=[float(x) for x in '''$KF'''.split()]
a=[k for k in ks if k<=$AT]; b=[k for k in ks if k>=$END]
print('%.6f %.6f' % (max(a) if a else 0.0, min(b) if b else -1))")
[ "$K2" = "-1.000000" ] && { echo "[layout] no keyframe after the window" >&2; exit 1; }
TO=$(python3 -c "print('%.6f' % ($K2 - 0.5/$FPS))")
echo "[layout] layout $AT-${END}s; re-encoding only the keyframe window $K1 -> $K2 (video only)"

# --- three VIDEO-ONLY parts. head and tail are untouched bits of the master.
# The head is bounded by FRAME COUNT, not by -t: "-t $K1 -c:v copy" overshoots the keyframe by two frames
# (measured: 1252 frames / 20.867 s for a 20.833 s cut), which then shows up as a 2-frame-longer master.
N1=$(python3 -c "print(int(round($K1 * $FPS)))")
ffmpeg -nostdin -v error -y -i "$IN" -frames:v "$N1" -an -c:v copy -avoid_negative_ts make_zero "$W/a.mp4"
ffmpeg -nostdin -v error -y -ss "$K2" -i "$IN" -an -c:v copy -avoid_negative_ts make_zero "$W/c.mp4"
OX=$(python3 -c "import json;d=json.load(open('$B/free-carry-layout.json'));print(95-d['line_x'])")
OY=$(python3 -c "import json;d=json.load(open('$B/free-carry-layout.json'));print(108-d['line_y'])")
OFF=$(python3 -c "print(round($AT - $K1, 6))")
ffmpeg -nostdin -v error -y -reinit_filter 0 -ss "$K1" -to "$TO" -i "$IN" -i "$B/free-carry-layout.mov" \
  -filter_complex "[1:v]format=rgba,setpts=PTS-STARTPTS+$OFF/TB[l];[0:v][l]overlay=$OX:$OY:eof_action=pass:format=auto[v]" \
  -map "[v]" -an -r "$FPSR" -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p \
  -avoid_negative_ts make_zero "$W/b.mp4"

printf "file '%s/a.mp4'\nfile '%s/b.mp4'\nfile '%s/c.mp4'\n" "$W" "$W" "$W" > "$W/list.txt"
ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$W/list.txt" -c copy "$W/v.mp4"

# --- mux the master's ORIGINAL audio back in, whole and copied
ffmpeg -nostdin -v error -y -i "$W/v.mp4" -i "$IN" -map 0:v:0 -map 1:a:0 -c copy -movflags +faststart "$OUT"

set +e
python3 - "$IN" "$OUT" <<'PY'
import subprocess, sys
def probe(f, s, e):
    return subprocess.run(["ffprobe","-v","error","-select_streams",s,"-show_entries",e,
                           "-of","default=nw=1:nk=1",f], capture_output=True, text=True).stdout.split()
a, b = sys.argv[1], sys.argv[2]
fa, fb = int(probe(a,"v:0","stream=nb_frames")[0]), int(probe(b,"v:0","stream=nb_frames")[0])
aa, ab = float(probe(a,"a:0","stream=duration")[0]), float(probe(b,"a:0","stream=duration")[0])
print("[layout] frames %d -> %d   audio %.3fs -> %.3fs" % (fa, fb, aa, ab))
if fa != fb:      raise SystemExit("[layout] fast path unsafe: frame count changed by %d" % (fb-fa))
if abs(aa-ab) > 0.001: raise SystemExit("[layout] fast path unsafe: audio duration changed by %.3fs" % (ab-aa))
print("[layout] OK — frame count and audio identical to the master")
PY
CHECK=$?; set -e
if [ "$CHECK" -ne 0 ]; then
  # A stream-copied trim (edit lists, pre-roll frames before the first keyframe) can make the keyframe splice
  # inexact. Rather than leave the owner stuck, do the safe thing: one full re-encode with the overlay.
  echo "[layout] falling back to the full re-encode (slower, always exact)"
  rm -f "$OUT"
  exec bash "$(dirname "$0")/apply-layout.sh" "$IN" "$OUT" "$AT"
fi

# Cross-file A/V sync against the master. verify-final.py does NOT check this -- it validates a file against
# itself -- and that is exactly how the 2026-09-22 +0.15 s audio slip shipped past a PASS. Assert it here.
SYNCPY=$HOME/.cache/video-editor/whisperx-venv/bin/python
if [ -x "$SYNCPY" ]; then
  "$SYNCPY" presets/gameplay/synccheck.py offset "$IN" "$OUT" 60,300,900,1500 | tee /tmp/layout-sync.txt
  if grep -q "FAIL" /tmp/layout-sync.txt; then
    echo "[layout] ABORT: A/V drifted against the master"; rm -f "$OUT"; exit 1
  fi
fi
echo "[layout] sync verified against the master"
