#!/usr/bin/env python3
"""
build_cuts.py — the GAMEPLAY-comedy cut list (first used on division2-legendary-mission, 2026-09-13).

A long gameplay session (30–90 min) → a highlight edit that keeps every stretch where the creator is
talking or reacting, with enough gameplay around it to read, and drops the silent traversal:

  * speech runs = words closer than --gap-keep (3.0 s), like the reaction cadence
  * every run gets a lead-in (--lead 1.2 s of gameplay before the first word) and a tail (--tail 0.8 s)
  * runs closer than --bridge (4 s) after padding are merged — the gameplay between them stays
  * an ISOLATED micro-run of filler ("Alright.", "Here we go.", "Oh yeah.") is dropped: ≤ --filler-words
    words, shorter than --filler-sec, no trigger word (gags.py's TRIGGERS/PHRASES), nothing kept
    within --bridge of it
  * --keep a-b (repeatable, raw seconds or m:ss) forces a span in whole; --drop a-b removes one
  * the head (before the first kept word) is trimmed; the tail after the last kept word too

Writes  projects/<job>/transcript/cuts.json  +  /tmp/video-editor/<job>/cuts.json  (what splice.sh reads)
Prints  the kept list in m:ss with the reason each dropped run was dropped when --verbose.

Usage:  presets/gameplay/build_cuts.py <job> [--gap-keep 3.0] [--lead 1.2] [--tail 0.8] [--bridge 4.0]
            [--filler-words 3] [--filler-sec 1.6] [--keep 0:00-2:15 ...] [--drop 49:00-51:05 ...] [--verbose]
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "presets", "shorts"))
from gags import TRIGGERS, PHRASES, clean   # noqa: E402

def ts(s):
    s = s.strip()
    if re.fullmatch(r"\d+(\.\d+)?", s): return float(s)
    p = [float(x) for x in s.split(":")]
    return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]

def mmss(t):
    t = int(round(t)); return f"{t // 60}:{t % 60:02d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job"); ap.add_argument("--gap-keep", type=float, default=3.0)
    ap.add_argument("--lead", type=float, default=1.2); ap.add_argument("--tail", type=float, default=0.8)
    ap.add_argument("--bridge", type=float, default=4.0)
    ap.add_argument("--filler-words", type=int, default=3); ap.add_argument("--filler-sec", type=float, default=1.6)
    ap.add_argument("--keep", action="append", default=[]); ap.add_argument("--drop", action="append", default=[])
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    J = os.path.join(REPO, "projects", a.job)
    d = json.load(open(os.path.join(J, "transcript", "words.json")))
    clip = d["clips"][0]; ws = clip["words"]; name = clip["clip"]; total = clip.get("duration") or ws[-1]["end"]
    keeps = [tuple(ts(x) for x in k.split("-")) for k in a.keep]
    drops = [tuple(ts(x) for x in k.split("-")) for k in a.drop]

    runs, s = [], 0
    for i in range(1, len(ws) + 1):
        gap = (ws[i]["start"] - ws[i - 1]["end"]) if i < len(ws) else None
        if gap is None or gap > a.gap_keep:
            r = ws[s:i]; runs.append({"a": r[0]["start"], "b": r[-1]["end"], "words": [w["w"] for w in r]}); s = i

    def has_trigger(words):
        toks = [clean(w) for w in words]; text = " ".join(toks)
        return any(TRIGGERS.get(t, (0,))[0] >= 0.7 for t in toks) or any(p in text for p in PHRASES)

    # 1. filler pruning (isolation judged against the raw runs, before padding)
    kept, dropped = [], []
    for i, r in enumerate(runs):
        dur, n = r["b"] - r["a"], len(r["words"])
        near = ((i > 0 and r["a"] - runs[i - 1]["b"] <= a.bridge + a.lead + a.tail) or
                (i + 1 < len(runs) and runs[i + 1]["a"] - r["b"] <= a.bridge + a.lead + a.tail))
        in_keep = any(k0 <= r["a"] <= k1 for k0, k1 in keeps)
        if not in_keep and n <= a.filler_words and dur < a.filler_sec and not has_trigger(r["words"]) and not near:
            dropped.append((r, "isolated filler")); continue
        kept.append(r)
    # 2. pad + bridge
    segs = []
    for r in kept:
        s0, s1 = max(0.0, r["a"] - a.lead), min(total, r["b"] + a.tail)
        if segs and s0 - segs[-1][1] <= a.bridge:
            segs[-1][1] = s1; segs[-1][2] += " " + " ".join(r["words"])
        else:
            segs.append([s0, s1, " ".join(r["words"])])
    # 3. forced keeps, then drops
    for k0, k1 in keeps:
        segs.append([k0, k1, f"[keep {mmss(k0)}-{mmss(k1)}]"])
    segs.sort(key=lambda x: x[0])
    merged = []
    for s0, s1, t in segs:
        if merged and s0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s1); merged[-1][2] += " " + t
        else:
            merged.append([s0, s1, t])
    out = []
    for s0, s1, t in merged:
        pieces = [[s0, s1, t]]
        for d0, d1 in drops:
            nxt = []
            for p0, p1, pt in pieces:
                if d1 <= p0 or d0 >= p1: nxt.append([p0, p1, pt]); continue
                if p0 < d0: nxt.append([p0, d0, pt + " [cut at drop]"])
                if d1 < p1: nxt.append([d1, p1, pt + " [resumes after drop]"])
            pieces = nxt
        out += [p for p in pieces if p[1] - p[0] > 0.3]
    segments = [{"clip": name, "start": round(s0, 3), "end": round(s1, 3), "transcript": t[:400]} for s0, s1, t in out]
    tmp = f"/tmp/video-editor/{a.job}"; os.makedirs(tmp, exist_ok=True)
    for p in (os.path.join(J, "transcript", "cuts.json"), os.path.join(tmp, "cuts.json")):
        json.dump({"segments": segments}, open(p, "w"), indent=2)
    kept_s = sum(s["end"] - s["start"] for s in segments)
    print(f"[gameplay-cuts] {len(runs)} speech runs → {len(segments)} segments, kept {kept_s:.0f}s = {mmss(kept_s)} of {mmss(total)} "
          f"({kept_s / total * 100:.0f}%), {len(dropped)} filler runs dropped")
    if a.verbose:
        for s in segments:
            print(f"  {mmss(s['start']):>6}-{mmss(s['end']):<6} ({s['end'] - s['start']:5.1f}s)  {s['transcript'][:80]}")
        print("dropped filler:")
        for r, why in dropped:
            print(f"  {mmss(r['a'])}  {' '.join(r['words'])[:50]!r}  ({why})")

if __name__ == "__main__":
    main()
