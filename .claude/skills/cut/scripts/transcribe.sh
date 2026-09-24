#!/usr/bin/env bash
# transcribe.sh — one transcript per job, kept forever.
#
#   usage: .claude/skills/cut/scripts/transcribe.sh <job_dir> [--force] [--diarize]
#
# Reads every clip in <job_dir>/raw/, runs WhisperX (large-v3 speech recognition + wav2vec2 word alignment),
# and writes <job_dir>/transcript/words.json:
#   {"clips":[{"file":"clip.mp4","words":[{"w":"hello","start":1.23,"end":1.51,"prob":0.98}, ...]}, ...]}
#
# It refuses to redo work: if words.json exists it is reused (--force to redo). That file is the single source
# of truth for the whole job — the cut, the captions, the graphics plan all read it. Nothing transcribes twice.
#
# First run builds a private Python environment with uv (WhisperX pulls torch, which is big — minutes, once).
# It lives at ~/.cache/video-editor/whisperx-venv (override with VIDEO_EDITOR_WHISPERX_VENV). An existing
# environment is never deleted; if it is half-built, the missing packages are installed into it.
#
# --diarize adds a "speaker" label to each word. Needs HUGGINGFACE_TOKEN in the environment and the
# pyannote/speaker-diarization-3.1 model terms accepted on Hugging Face.
set -euo pipefail
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

JOB="${1:?usage: transcribe.sh <job_dir> [--force] [--diarize]}"; shift || true
FORCE=0; DIARIZE=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --diarize) DIARIZE=1 ;;
    *) echo "[transcribe] unknown flag: $a" >&2; exit 2 ;;
  esac
done
[ -d "$JOB/raw" ] || { echo "[transcribe] no raw/ folder in $JOB" >&2; exit 1; }
OUT="$JOB/transcript/words.json"

if [ -f "$OUT" ] && [ "$FORCE" -eq 0 ]; then
  echo "[transcribe] reusing $OUT  (pass --force to transcribe again)"
  exit 0
fi

mapfile -t CLIPS < <(find "$JOB/raw" -maxdepth 1 -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.mkv' -o -iname '*.webm' -o -iname '*.m4a' -o -iname '*.wav' -o -iname '*.mp3' \) | sort)
[ "${#CLIPS[@]}" -gt 0 ] || { echo "[transcribe] nothing to transcribe in $JOB/raw" >&2; exit 1; }

# --- the environment ------------------------------------------------------------------------------------
VENV="${VIDEO_EDITOR_WHISPERX_VENV:-$HOME/.cache/video-editor/whisperx-venv}"
PY="$VENV/bin/python"
if [ ! -x "$PY" ]; then
  command -v uv >/dev/null 2>&1 || { echo "[transcribe] uv is not installed — run ./check-setup.sh" >&2; exit 1; }
  echo "[transcribe] first run: creating the WhisperX environment at $VENV" >&2
  mkdir -p "$(dirname "$VENV")"
  uv venv "$VENV" --python 3.11 >&2
fi
if ! "$PY" -c "import whisperx" >/dev/null 2>&1; then
  command -v uv >/dev/null 2>&1 || { echo "[transcribe] uv is not installed — run ./check-setup.sh" >&2; exit 1; }
  echo "[transcribe] installing WhisperX into $VENV (downloads torch — a few minutes, once)" >&2
  uv pip install --python "$PY" whisperx >&2
fi

DEVICE=cpu
command -v nvidia-smi >/dev/null 2>&1 && DEVICE=cuda
mkdir -p "$JOB/transcript"
echo "[transcribe] ${#CLIPS[@]} clip(s) on $DEVICE" >&2

"$PY" - "$OUT" "$DIARIZE" "$DEVICE" "${CLIPS[@]}" <<'PY'
import json, os, sys
out, diarize, device, clips = sys.argv[1], sys.argv[2] == "1", sys.argv[3], sys.argv[4:]
import whisperx

compute = "float16" if device == "cuda" else "int8"
batch = 16 if device == "cuda" else 4
asr = whisperx.load_model("large-v3", device, compute_type=compute)
aligner, align_meta, align_lang = None, None, None
result = []

for path in clips:
    name = os.path.basename(path)
    audio = whisperx.load_audio(path)
    rough = asr.transcribe(audio, batch_size=batch)
    lang = rough.get("language", "en")
    if aligner is None or align_lang != lang:
        aligner, align_meta = whisperx.load_align_model(language_code=lang, device=device)
        align_lang = lang
    aligned = whisperx.align(rough["segments"], aligner, align_meta, audio, device, return_char_alignments=False)
    if diarize:
        token = os.environ.get("HUGGINGFACE_TOKEN")
        if not token:
            sys.exit("[transcribe] --diarize needs HUGGINGFACE_TOKEN in the environment")
        pipeline = whisperx.DiarizationPipeline(use_auth_token=token, device=device)
        aligned = whisperx.assign_word_speakers(pipeline(audio), aligned)
    words = []
    for seg in aligned["segments"]:
        for w in seg.get("words", []):
            if "start" not in w or "end" not in w:
                continue  # a word the aligner could not place (a number, a symbol) — skip rather than guess
            item = {"w": w["word"].strip(), "start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3), "prob": round(float(w.get("score", 0.0)), 3)}
            if diarize and w.get("speaker"):
                item["speaker"] = w["speaker"]
            words.append(item)
    result.append({"file": name, "language": lang, "words": words})
    print(f"[transcribe] {name}: {len(words)} words", file=sys.stderr)

with open(out, "w", encoding="utf-8") as f:
    json.dump({"clips": result}, f, indent=1, ensure_ascii=False)
print(out)
PY
