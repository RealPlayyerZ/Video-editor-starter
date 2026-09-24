#!/usr/bin/env bash
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# EXAMPLE — this is the original author's style. Replace the look; keep the mechanism.
# apply-outro.sh — append the LOCKED outro (see presets/outro-style.md). v2 (2026-09-08): frozen-tail bug fixed at the source.
#
# Identical to apply-outro.sh (the LOCKED look: Additive-Dissolve-as-xfade 0.3s, acrossfade 0dB,
# outro music trimmed/flat/1.3s tail fade — see presets/outro-style.md) EXCEPT for how the short
# TAIL slice is cut out of the main video before it goes through xfade:
#
#   BUG (found 2026-09-08 on gpt-astra-6-reaction AND dlss-5-reaction, shipped in both): the old
#   tail extraction was `-ss $HEAD_DUR -i $VIDEO` — an INPUT seek landing ~2s before the file's own
#   end. On long re-encoded cuts that came back as ONE frame held for the whole ~2s tail, which then
#   got baked into the final via the head+tail concat: the creator freezes for two seconds right
#   before the outro. The script reported success and the container duration was right.
#
#   FIX: (1) cut the tail with a two-stage seek — a fast INPUT seek to a keyframe ~20s earlier, then
#   an accurate OUTPUT seek (`-i … -ss …`) that decodes forward to the exact frame — so it never
#   starts on the last GOP's edge; (2) make the tail longer (≥6s, was 2s) so the seam sits well
#   clear of the file's end; (3) VERIFY the tail actually moves (frame-difference check; abort if
#   frozen) and that head+tail add back up to the input duration, before anything is concatenated;
#   (4) verify the final duration is D1 + D2 - T. A tail that fails verification stops the script —
#   it never ships a freeze quietly again.
#
# Usage (unchanged):
#   apply-outro.sh <input-video.mp4> <outro-music.mp3> <output-video.mp4> \
#     [outro-source.mp4] [transition_duration] [music_gain_db] [outro_fadein_duration] [audio_crossfade_duration]
#
#   outro-source defaults to the locked brand asset:
#   <your outro video> - set Outro video in brand-kit.md, or pass it as the 4th argument
#   transition_duration defaults to the LOCKED 0.3s — pass a different value only to experiment.
#   music_gain_db defaults to 0 (track plays at its own native level) — pass e.g. -12 or +8.2 to
#   attenuate/boost the outro music without re-exporting the source file.
#   outro_fadein_duration defaults to 0 (outro music starts instantly at full volume) — pass a value
#   to fade the outro track in from silence. NOTE: combining this with a long
#   audio_crossfade_duration is usually wrong — a fade-OUT (body bed) landing on a fade-IN (outro
#   track) both bottoming out near the same instant produces an audible silent trough. Use ONE of
#   fade-in or a longer crossfade, not both, unless you've listened to the result.
#   audio_crossfade_duration defaults to transition_duration (same 0.3s as the locked video
#   dissolve) — pass a longer value (e.g. 1.5) to blend the body's own background-music bed into
#   the outro track over more time, independent of the locked 0.3s VIDEO dissolve. A real crossfade
#   sums both curves through the overlap, so it doesn't create the silent-trough problem above.
#   The final mux uses -shortest because acrossfade's output length doesn't automatically match
#   the video xfade's (they reconstruct their inputs differently).
set -euo pipefail

VIDEO="${1:?usage: apply-outro.sh <input-video> <outro-music> <output> [outro-source] [transition_duration] [music_gain_db] [outro_fadein_duration] [audio_crossfade_duration]}"
# Defaults come from brand-kit.md via presets/brand.json (outro video, outro music). Pass args to override.
brand() { python3 -c 'import json,sys; d=json.load(open("presets/brand.json")); v=d.get(sys.argv[1]); print(v or "")' "$1" 2>/dev/null; }
MUSIC="${2:-$(brand outro_music)}"; : "${MUSIC:?need an outro music track}"
OUT="${3:?need an output path}"
OUTRO_SRC="${4:-$(brand outro)}"
[ -n "$OUTRO_SRC" ] || { echo "[apply-outro] no outro video: pass one as the 4th argument or set 'Outro video' in brand-kit.md" >&2; exit 1; }
T="${5:-0.3}"
MUSIC_GAIN_DB="${6:-0}"
OUTRO_FADEIN="${7:-0}"
AUDIO_T="${8:-$T}"

[ -f "$VIDEO" ] || { echo "[apply-outro] no input video: $VIDEO" >&2; exit 1; }
[ -f "$MUSIC" ] || { echo "[apply-outro] no music track: $MUSIC" >&2; exit 1; }
[ -f "$OUTRO_SRC" ] || { echo "[apply-outro] no outro source: $OUTRO_SRC" >&2; exit 1; }

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# 2026-09-15: the outro source lives on the Windows drive (9p/drvfs). ffmpeg decoding it in place hit
# "Error during demuxing: Cannot allocate memory" on two runs (rush-hour-reaction v2, division2 v5) and
# silently produced a 2 s outro VIDEO under a full-length outro AUDIO — the final then carried a
# truncated outro. Copy the source onto the Linux filesystem first (byte-compared, retried) and decode
# the copy; the hard checks below refuse a short outro instead of warning.
for attempt in 1 2 3; do
  if cp "$OUTRO_SRC" "$TMPDIR/outro_src.mp4" 2>/dev/null && cmp -s "$OUTRO_SRC" "$TMPDIR/outro_src.mp4"; then break; fi
  echo "[apply-outro] outro source copy attempt ${attempt} failed (drive bridge) — retrying" >&2; sleep 3
done
cmp -s "$OUTRO_SRC" "$TMPDIR/outro_src.mp4" || { echo "[apply-outro] ABORT: could not copy the outro source intact: $OUTRO_SRC" >&2; exit 2; }
OUTRO_SRC="$TMPDIR/outro_src.mp4"

W="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of default=nw=1:nk=1 "$VIDEO")"
H="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=nw=1:nk=1 "$VIDEO")"
FPS="$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1:nk=1 "$VIDEO")"
FPS_NUM="${FPS%/*}"; FPS_DEN="${FPS#*/}"

OUTRO_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUTRO_SRC")"
FADE_ST="$(awk -v d="$OUTRO_DUR" 'BEGIN{ s=d-1.3; if (s<0) s=0; printf "%.3f", s }')"

echo "[apply-outro] prepping outro at ${W}x${H} @ ${FPS}fps, music tail-fade at ${FADE_ST}s, gain ${MUSIC_GAIN_DB}dB, fade-in ${OUTRO_FADEIN}s" >&2

fadein_filt=""
if awk -v f="$OUTRO_FADEIN" 'BEGIN{exit !(f>0)}'; then
  fadein_filt=",afade=t=in:st=0:d=${OUTRO_FADEIN}"
fi

ffmpeg -nostdin -hide_banner -loglevel error -y \
  -i "$OUTRO_SRC" -i "$MUSIC" \
  -filter_complex "[0:v]scale=${W}:${H}:flags=lanczos,setsar=1,fps=${FPS_NUM}/${FPS_DEN}[outv]; \
                   [1:a]atrim=0:${OUTRO_DUR},asetpts=PTS-STARTPTS,volume=${MUSIC_GAIN_DB}dB,afade=t=out:st=${FADE_ST}:d=1.3${fadein_filt}[outa]" \
  -map "[outv]" -map "[outa]" \
  -c:v libx264 -preset medium -crf 9 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 \
  "$TMPDIR/outro_prepped.mp4"
PREP_V="$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 "$TMPDIR/outro_prepped.mp4")"
if ! awk -v a="$PREP_V" -v b="$OUTRO_DUR" 'BEGIN{ x = a - b; if (x < 0) x = -x; exit !(x <= 0.15) }'; then
  echo "[apply-outro] ABORT: prepped outro video is ${PREP_V}s, source is ${OUTRO_DUR}s — the outro decode was cut short" >&2
  exit 2
fi
echo "[apply-outro] outro prepped: ${PREP_V}s video ✓" >&2

# Head/tail split — still required to dodge xfade's silent truncation on long first inputs
# (see apply-outro.sh's comment block; that workaround stays). What changed is HOW the tail is cut.
D1="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$VIDEO")"
OFFSET="$(awk -v d="$D1" -v t="$T" 'BEGIN{printf "%.3f", d - t}')"
TAIL_LEN="$(awk -v t="$T" 'BEGIN{ tl = t * 3; if (tl < 6.0) tl = 6.0; printf "%.3f", tl }')"
HEAD_DUR="$(awk -v d="$D1" -v tl="$TAIL_LEN" 'BEGIN{ h = d - tl; if (h < 0) h = 0; printf "%.3f", h }')"

echo "[apply-outro] splicing at offset ${OFFSET}s (main duration ${D1}s, tail-split at ${HEAD_DUR}s, tail ${TAIL_LEN}s)" >&2

# Frame-difference freeze check: N frames spread across a clip must not be near-identical in a
# run of 3+. Uses tiny greyscale frames so encoder noise can't fake a difference.
assert_not_frozen() {  # <clip> <label>
  local clip="$1" label="$2" dur n i t prev cur run worst
  dur="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$clip")"
  n=8; run=1; worst=1; prev=""
  for i in $(seq 0 $((n - 1))); do
    t="$(awk -v d="$dur" -v i="$i" -v n="$n" 'BEGIN{printf "%.3f", d * (i + 0.5) / n}')"
    ffmpeg -nostdin -hide_banner -loglevel error -y -ss "$t" -i "$clip" -frames:v 1 \
      -vf "scale=64:36,format=gray" -f rawvideo "$TMPDIR/probe_$i.raw" 2>/dev/null || true
    cur="$(md5sum "$TMPDIR/probe_$i.raw" 2>/dev/null | cut -c1-32 || true)"
    if [ -n "$prev" ] && [ "$cur" = "$prev" ]; then run=$((run + 1)); [ $run -gt $worst ] && worst=$run; else run=1; fi
    prev="$cur"
  done
  if [ "$worst" -ge 3 ]; then
    echo "[apply-outro] ABORT: $label is FROZEN (${worst} of ${n} sampled frames identical in a row) — refusing to ship a freeze" >&2
    exit 2
  fi
  echo "[apply-outro] $label verified moving (longest identical run ${worst}/${n})" >&2
}

if awk -v h="$HEAD_DUR" 'BEGIN{exit !(h > 0)}'; then
  ffmpeg -nostdin -hide_banner -loglevel error -y \
    -i "$VIDEO" -t "$HEAD_DUR" -an \
    -c:v libx264 -preset medium -crf 9 -pix_fmt yuv420p \
    "$TMPDIR/head.mp4"
  # Two-stage seek: fast input seek to ~20s before the cut, then accurate output seek to the exact
  # frame. This is the standard fast+accurate ffmpeg idiom; the old single near-EOF input seek is
  # what produced the held frame.
  PRE="$(awk -v h="$HEAD_DUR" 'BEGIN{ p = h - 20; if (p < 0) p = 0; printf "%.3f", p }')"
  REL="$(awk -v h="$HEAD_DUR" -v p="$PRE" 'BEGIN{printf "%.3f", h - p}')"
  ffmpeg -nostdin -hide_banner -loglevel error -y \
    -ss "$PRE" -i "$VIDEO" -ss "$REL" -t "$TAIL_LEN" -an \
    -c:v libx264 -preset medium -crf 9 -pix_fmt yuv420p \
    "$TMPDIR/tail.mp4"
  assert_not_frozen "$TMPDIR/tail.mp4" "tail slice"
  HD="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMPDIR/head.mp4")"
  TD="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMPDIR/tail.mp4")"
  if ! awk -v a="$HD" -v b="$TD" -v d="$D1" 'BEGIN{ x = a + b - d; if (x < 0) x = -x; exit !(x <= 0.15) }'; then
    echo "[apply-outro] ABORT: head (${HD}s) + tail (${TD}s) != input (${D1}s) — seam would drift" >&2
    exit 2
  fi
  echo "[apply-outro] head ${HD}s + tail ${TD}s = input ${D1}s ✓" >&2
else
  cp "$VIDEO" "$TMPDIR/tail.mp4"  # main video already <= TAIL_LEN, no head split needed
fi

TAIL_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMPDIR/tail.mp4")"
TAIL_OFFSET="$(awk -v d="$TAIL_DUR" -v t="$T" 'BEGIN{printf "%.3f", d - t}')"

ffmpeg -nostdin -hide_banner -loglevel error -y \
  -i "$TMPDIR/tail.mp4" -i "$TMPDIR/outro_prepped.mp4" \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${T}:offset=${TAIL_OFFSET}[outv]" \
  -map "[outv]" -an \
  -c:v libx264 -preset medium -crf 9 -pix_fmt yuv420p \
  "$TMPDIR/tail_transitioned.mp4"
assert_not_frozen "$TMPDIR/tail_transitioned.mp4" "transitioned tail"

if [ -f "$TMPDIR/head.mp4" ]; then
  printf "file '%s'\nfile '%s'\n" "$TMPDIR/head.mp4" "$TMPDIR/tail_transitioned.mp4" > "$TMPDIR/concat.txt"
  ffmpeg -nostdin -hide_banner -loglevel error -y -f concat -safe 0 -i "$TMPDIR/concat.txt" -c copy "$TMPDIR/video_only.mp4"
else
  cp "$TMPDIR/tail_transitioned.mp4" "$TMPDIR/video_only.mp4"
fi

ffmpeg -nostdin -hide_banner -loglevel error -y \
  -i "$VIDEO" -i "$TMPDIR/outro_prepped.mp4" \
  -filter_complex "[0:a][1:a]acrossfade=d=${AUDIO_T}:c1=tri:c2=tri[outa]" \
  -map "[outa]" -c:a aac -b:a 192k -ar 48000 \
  "$TMPDIR/audio_only.m4a"

FINAL_V_DUR="$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 "$TMPDIR/video_only.mp4")"
FINAL_A_DUR="$(ffprobe -v error -select_streams a:0 -show_entries stream=duration -of default=nw=1:nk=1 "$TMPDIR/audio_only.m4a")"
echo "[apply-outro] final mux: video ${FINAL_V_DUR}s, audio ${FINAL_A_DUR}s" >&2

ffmpeg -nostdin -hide_banner -loglevel error -y \
  -i "$TMPDIR/video_only.mp4" -i "$TMPDIR/audio_only.m4a" \
  -map 0:v -map 1:a -c:v copy -c:a copy \
  -shortest \
  -movflags +faststart \
  "$OUT"

OUT_DUR="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT")"
EXPECTED="$(awk -v a="$D1" -v b="$OUTRO_DUR" -v t="$T" -v at="$AUDIO_T" 'BEGIN{ m = t; if (at > m) m = at; printf "%.3f", a + b - m}')"
if ! awk -v o="$OUT_DUR" -v e="$EXPECTED" 'BEGIN{ x = o - e; if (x < 0) x = -x; exit !(x <= 0.5) }'; then
  # 2026-09-15: this used to be a WARNING and a truncated outro shipped twice — now it refuses
  echo "[apply-outro] ABORT: output ${OUT_DUR}s but expected D1+D2-max(T,AUDIO_T) = ${EXPECTED}s — the outro is not complete" >&2
  rm -f "$OUT"
  exit 2
fi
echo "[apply-outro] wrote $OUT (${OUT_DUR}s, expected ${EXPECTED}s)" >&2
