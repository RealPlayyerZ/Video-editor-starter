#!/usr/bin/env python3
"""segment-script.py — split the cut's transcript into beats, so the graphics plan has something to point at.

  usage: segment-script.py <job_dir | transcript.json> [out.json]

Input   outputs/<job>.transcript.json  — words on the cut's clock ({"words":[{"text","start","end"}]})
Output  <job>/graphics-plan.beats.json —
        {"beats":[{"i":1,"start":0.21,"end":4.80,"text":"...","words":17,"pause_after":0.62}], "duration":…}

A beat is a stretch of speech that a viewer hears as one thought: it ends at a sentence-ending word (. ! ?)
or at a pause longer than 0.55 s, and it is never longer than ~9 s (a long run is split at its widest pause).
Beats are what the plan assigns graphics to. This script makes no creative decision — it only draws the lines.
"""
import json, os, sys

PAUSE = 0.55
MAX_BEAT = 9.0
ENDERS = (".", "!", "?")


def load(job_or_file):
    if job_or_file.endswith(".json"):
        return job_or_file
    job = os.path.abspath(job_or_file.rstrip("/"))
    name = os.path.basename(job)
    p = os.path.join(job, "outputs", f"{name}.transcript.json")
    if os.path.isfile(p):
        return p
    for f in os.listdir(os.path.join(job, "outputs")) if os.path.isdir(os.path.join(job, "outputs")) else []:
        if f.endswith(".transcript.json"):
            return os.path.join(job, "outputs", f)
    sys.exit(f"[beats] no transcript under {job}/outputs — run the cut step first")


def split_long(words):
    """split a run longer than MAX_BEAT at its widest internal pause"""
    if not words or words[-1]["end"] - words[0]["start"] <= MAX_BEAT or len(words) < 4:
        return [words]
    gaps = [(words[i + 1]["start"] - words[i]["end"], i) for i in range(len(words) - 1)]
    g, i = max(gaps)
    return split_long(words[: i + 1]) + split_long(words[i + 1:])


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tpath = load(sys.argv[1])
    d = json.load(open(tpath, encoding="utf-8"))
    words = d["words"]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(tpath)), "graphics-plan.beats.json")

    runs, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends_sentence = w["text"].rstrip("\"'’”)").endswith(ENDERS)
        paused = nxt is not None and nxt["start"] - w["end"] > PAUSE
        if ends_sentence or paused or nxt is None:
            runs.append(cur); cur = []
    beats = []
    for run in runs:
        for piece in split_long(run):
            beats.append(piece)

    result = []
    for k, b in enumerate(beats):
        nxt_start = beats[k + 1][0]["start"] if k + 1 < len(beats) else b[-1]["end"]
        result.append({"i": k + 1, "start": round(b[0]["start"], 3), "end": round(b[-1]["end"], 3),
                       "text": " ".join(w["text"] for w in b), "words": len(b),
                       "pause_after": round(max(0.0, nxt_start - b[-1]["end"]), 2)})
    json.dump({"beats": result, "duration": d.get("duration", words[-1]["end"] if words else 0)},
              open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"[beats] {len(result)} beats over {result[-1]['end'] if result else 0:.1f}s -> {out}")
    for b in result[:6]:
        print(f"   {b['i']:>3}  {b['start']:7.2f}-{b['end']:7.2f}  {b['text'][:70]}")
    if len(result) > 6:
        print(f"   ... {len(result) - 6} more")


if __name__ == "__main__":
    main()
