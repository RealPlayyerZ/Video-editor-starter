#!/usr/bin/env python3
"""
gags_wide.py — the comedy layer (presets/shorts/gags.py) over a LONG-FORM 16:9 gameplay cut.

Runs gags.run_gags on the zoom-applied base with the 16:9 canvas, the "gameplay" style (inset
reaction clips bottom-left, flash + shake, no automatic text pops), long-form density, and — for a
cold open — the chat cards from chat_cards.py popping in with the creator's popping sound.
First used on division2-legendary-mission (2026-09-13).

Usage:
  gags_wide.py <job> [--in outputs/<job>.zoomed.mp4] [--out outputs/<job>.gagged.mp4]
               [--cards assemble_work/cards/cards.json] [--intensity medium] [--style gameplay]
               [--sfx-trim -3] [--no-memes] [--freeze t[:hold]] [--plan-only]
"""
import argparse, json, os, random, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "presets", "shorts"))
import gags  # noqa: E402


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", path], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    return int(j["streams"][0]["width"]), int(j["streams"][0]["height"]), float(j["format"]["duration"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--in", dest="inp", default=None); ap.add_argument("--out", default=None)
    ap.add_argument("--cards", default=None)
    ap.add_argument("--intensity", choices=["light", "medium", "heavy"], default="medium")
    ap.add_argument("--style", choices=list(gags.STYLE), default="gameplay")
    ap.add_argument("--sfx-trim", type=float, default=-3.0)
    ap.add_argument("--no-memes", action="store_true")
    ap.add_argument("--seed", default=None)
    ap.add_argument("--freeze", action="append", default=[], metavar="t[:hold]", help="authored freeze-frame + record scratch (clip time)")
    ap.add_argument("--sfx", default="", metavar="tag@t,tag@t", help="authored sounds by tag (assets/sfx), clip time")
    ap.add_argument("--text", action="append", default=[], metavar="TEXT@t[:dur]", help="authored engine text pop")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    J = os.path.join(REPO, "projects", a.job)
    inp = a.inp or os.path.join(J, "outputs", f"{a.job}.zoomed.mp4")
    out = a.out or os.path.join(J, "outputs", f"{a.job}.gagged.mp4")
    w, h, dur = probe(inp)
    gags.canvas(w, h)
    tj = json.load(open(os.path.join(J, "outputs", f"{a.job}.transcript.json")))
    words = [x for x in tj["words"] if x.get("type", "word") == "word" and x.get("text", "").strip()]
    punchins = json.load(open(os.path.join(J, "punchins.json"))) if os.path.isfile(os.path.join(J, "punchins.json")) else []
    overlays, extra = [], []
    fixed = gags.authored_gags((), a.text, a.freeze)
    authored_sfx = gags.parse_sfx(a.sfx)
    if a.cards:
        c = json.load(open(a.cards))
        overlays = [tuple(o) for o in c["overlays"]]
        extra = [("popping", float(t)) for t in c["pops"]]
    extra += authored_sfx
    print(f"[gags-wide] {a.job}: {w}x{h} {dur:.0f}s, {len(words)} words, {len(punchins)} punch-ins, {len(overlays)} cards, "
          f"style={a.style} intensity={a.intensity}")
    if a.plan_only:
        work = os.path.join(J, "assemble_work", "gags")
        env = gags.audio_envelope(inp, work)
        beats, med, bed = gags.detect_beats(words, env, dur)
        sfx, memes = gags.sfx_library(), ([] if a.no_memes else gags.meme_library())
        g, ex = gags.plan_gags(beats, punchins, dur, a.intensity, sfx, memes, "wide", random.Random(a.seed or a.job), words, a.style,
                               None, fixed, bed, blocked=[t for _, t in extra])
        print(f"BEATS: {len(beats)} (speech median {med:.0f} dB{', game-audio bed' if bed else ''})")
        print(gags.describe(g, ex + extra))
        return
    meta = gags.run_gags(J, inp, out, words, "wide", punchins, a.intensity, dur, seed=a.seed, style=a.style,
                         no_memes=a.no_memes, extra_sfx=extra, fixed_gags=fixed, loudness=None, sfx_trim=a.sfx_trim, overlays=overlays)
    print(f"[gags-wide] → {out} ({meta['duration']:.1f}s, {len(meta['gags'])} gags)")


if __name__ == "__main__":
    main()
