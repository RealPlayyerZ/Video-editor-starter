#!/usr/bin/env python3
"""
zoom_plan.py — exclamation-highlight punch-in windows for a GAMEPLAY job (zoom-plan skill, style 2),
computed from the cut transcript instead of by hand (first used on division2-legendary-mission, 2026-09-13).

A window (~2.4 s, hard cuts) on each genuine exclamation: a trigger word/phrase from gags.py's tables
with score >= --min-score, at least --spacing seconds from the previous window, never inside --skip
spans (the cold-open chat cards), capped at --max windows (highest scores win, then time order).
Optional --first t: an explicit opening punch-in.

Writes projects/<job>/zoom-plan.json (typed windows, all "zoom"), zoom-plan-zoomonly.json and
punchins.json ([start, end, 1.35] triples for the comedy layer's whoosh placement).

Usage: zoom_plan.py <job> [--min-score 0.9] [--spacing 20] [--max 36] [--len 2.4] [--skip 0-19] [--first 20.05]
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "presets", "shorts"))
from gags import TRIGGERS, PHRASES, clean   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--min-score", type=float, default=0.9)
    ap.add_argument("--spacing", type=float, default=20.0)
    ap.add_argument("--max", type=int, default=36)
    ap.add_argument("--len", type=float, default=2.4)
    ap.add_argument("--skip", action="append", default=[], help="a-b span (cut seconds) with no windows")
    ap.add_argument("--first", type=float, default=None, help="explicit opening punch-in start")
    a = ap.parse_args()
    J = os.path.join(REPO, "projects", a.job)
    tj = json.load(open(os.path.join(J, "outputs", f"{a.job}.transcript.json")))
    words = [w for w in tj["words"] if w.get("type", "word") == "word" and w.get("text", "").strip()]
    total = max(w["end"] for w in words)
    skips = [tuple(float(x) for x in s.split("-")) for s in a.skip]
    toks = [clean(w["text"]) for w in words]
    cands = []
    for i, w in enumerate(words):
        sc, tok = TRIGGERS.get(toks[i], (0.0, None))[0], toks[i]
        for ph, (psc, _) in PHRASES.items():
            n = len(ph.split())
            if " ".join(toks[i:i + n]) == ph and psc > sc:
                sc, tok = psc, ph
        if sc >= a.min_score:
            cands.append((sc, w["start"], tok))
    chosen = []
    if a.first is not None:
        chosen.append((9.0, a.first, "opening"))
    for sc, t, tok in sorted(cands, key=lambda c: -c[0]):
        if len(chosen) >= a.max:
            break
        s = t - 0.15
        if s < 0.3 or s + a.len > total - 1.0:
            continue
        if any(x0 <= s <= x1 or x0 <= s + a.len <= x1 for x0, x1 in skips):
            continue
        if all(abs(s - c[1]) >= a.spacing for c in chosen):
            chosen.append((sc, s, tok))
    chosen.sort(key=lambda c: c[1])
    wins = [{"start": round(s, 3), "end": round(s + a.len, 3), "type": "zoom", "reason": f"exclamation: {tok!r}"} for _, s, tok in chosen]
    plan = {"job": a.job, "zoom_trigger_style": "exclamation-highlight",
            "note": f"{len(wins)} punch-ins of {a.len}s on trigger words (score >= {a.min_score}, >= {a.spacing}s apart), hard cuts.",
            "windows": wins}
    json.dump(plan, open(os.path.join(J, "zoom-plan.json"), "w"), indent=2)
    json.dump({"job": a.job, "windows": wins}, open(os.path.join(J, "zoom-plan-zoomonly.json"), "w"), indent=2)
    json.dump([[w["start"], w["end"], 1.35] for w in wins], open(os.path.join(J, "punchins.json"), "w"))
    print(f"[zoom-plan] {len(wins)} windows over {total:.0f}s")
    for w in wins:
        print(f"  {int(w['start'] // 60)}:{w['start'] % 60:04.1f}  {w['reason']}")


if __name__ == "__main__":
    main()
