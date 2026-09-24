#!/usr/bin/env python3
"""export-transcript.py — put the kept words onto the cut's timeline.

  usage: export-transcript.py <words.json> <cuts.json> <out.json> [corrections.json]

Inputs
  words.json   what transcribe.sh wrote: {"clips":[{"file","words":[{"w","start","end","prob"}]}]}
  cuts.json    the edit decision list: {"segments":[{"clip":"file.mp4","start":1.24,"end":4.60,"transcript":"..."}]}
               Segments play in order. Their order IS the output timeline.

Output  <out.json>  {"text": "...", "words":[{"text","start","end"}], "segments":[{"clip","in","out","start","end"}]}
  A word is kept when its midpoint falls inside a kept segment. Its timestamps move by
  (where that segment starts in the output) - (where it started in the source). Pure arithmetic — nothing
  is transcribed again, so the words are exactly the ones the transcriber heard, on the cut's clock.

Corrections  (optional 4th argument; default: presets/caption-corrections.json two folders above the job)
  {"auto": {"hears": "Should Be"}, "flag": {"cloud": "why it might be wrong"}}
  auto  — swapped silently, whole word, case-insensitive; trailing punctuation is kept; timestamps untouched.
  flag  — printed with context for a human to look at; never changed.
  A job-local file <job>/corrections.local.json (same shape) is merged on top if present.
  Only single-word swaps are supported on purpose: a swap can never change the word count, so it can never
  shift a timestamp or break a cut.
"""
import json, os, re, sys

PUNCT = ".,!?;:\"'’”)"


def die(msg):
    sys.exit("[export-transcript] " + msg)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_corrections(out_path, explicit):
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    out = os.path.abspath(out_path)
    # <repo>/projects/<job>/outputs/<job>.transcript.json  ->  <repo>/presets/caption-corrections.json
    for up in (3, 4):
        parts = out.split(os.sep)
        if len(parts) > up:
            cand = os.path.join(os.sep.join(parts[:-up]), "presets", "caption-corrections.json")
            if os.path.isfile(cand):
                return cand
    return None


def load_corrections(out_path, explicit):
    auto, flag = {}, {}
    path = find_corrections(out_path, explicit)
    if path:
        d = load(path)
        auto.update({k.lower(): v for k, v in d.get("auto", {}).items()})
        flag.update({k.lower(): v for k, v in d.get("flag", {}).items()})
        print(f"[export-transcript] corrections: {path}")
    job_local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(out_path))), "corrections.local.json")
    if os.path.isfile(job_local):
        d = load(job_local)
        auto.update({k.lower(): v for k, v in d.get("auto", {}).items()})
        flag.update({k.lower(): v for k, v in d.get("flag", {}).items()})
        print(f"[export-transcript] job-local corrections: {job_local}")
    return auto, flag


def split_punct(token):
    core = token.rstrip(PUNCT)
    return core, token[len(core):]


def main():
    if len(sys.argv) < 4:
        die(__doc__)
    words_path, cuts_path, out_path = sys.argv[1:4]
    explicit = sys.argv[4] if len(sys.argv) > 4 else None

    by_clip = {c["file"]: c["words"] for c in load(words_path)["clips"]}
    segments = load(cuts_path)["segments"]
    auto, flag = load_corrections(out_path, explicit)

    out_words, out_segs = [], []
    t_out = 0.0
    fixed, flagged = 0, []
    for seg in segments:
        clip = seg["clip"]
        if clip not in by_clip:
            die(f"cuts.json names clip {clip!r} but words.json has no such clip (have: {list(by_clip)})")
        a, b = float(seg["start"]), float(seg["end"])
        if b <= a:
            die(f"segment {clip} {a}-{b} has no length")
        shift = t_out - a
        for w in by_clip[clip]:
            mid = (w["start"] + w["end"]) / 2.0
            if a <= mid < b:
                text = w["w"]
                core, tail = split_punct(text)
                key = core.lower()
                if key in auto:
                    text = auto[key] + tail
                    fixed += 1
                elif key in flag:
                    flagged.append((text, round(w["start"] + shift, 2), flag[key]))
                out_words.append({"text": text,
                                  "start": round(max(t_out, w["start"] + shift), 3),
                                  "end": round(min(t_out + (b - a), w["end"] + shift), 3)})
        out_segs.append({"clip": clip, "in": a, "out": b, "start": round(t_out, 3), "end": round(t_out + (b - a), 3)})
        t_out += b - a

    text = " ".join(w["text"] for w in out_words)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"text": text, "words": out_words, "segments": out_segs, "duration": round(t_out, 3)},
                  f, indent=1, ensure_ascii=False)

    print(f"[export-transcript] {len(out_words)} words on a {t_out:.2f}s timeline -> {out_path}")
    if fixed:
        print(f"[export-transcript] auto-fixed {fixed} word(s) from the corrections list")
    for tok, at, why in flagged:
        print(f"[export-transcript] REVIEW  {at:7.2f}s  {tok!r}  — {why}")


if __name__ == "__main__":
    main()
