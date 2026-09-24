#!/usr/bin/env python3
"""synccheck.py — two cheap audio-sync gates (division2-legendary-mission, 2026-09-14).

  packets <file>            the audio stream must hold duration*48000/1024 AAC packets (±20): a Twitch VOD's
                            10 ms gap at a segment boundary made rough-cut's splice stack 97 packets at one
                            timestamp — 2 s of audio behind the video from then on, ffmpeg rc 0.
  offset <ref> <test> t1,t2,…  [--shift f(t) from gags.json]   the test file's audio must match the reference's
                            at each t within ±0.15 s (allowing the freeze-hold shifts of the comedy layer).
Exit 1 on failure — meant to sit inside a runner with set -e."""
import json, subprocess, sys
def probe(path, sel):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-count_packets", "-show_entries",
                        "stream=nb_read_packets,duration,sample_rate", "-of", "json", path], capture_output=True, text=True)
    return json.loads(r.stdout)["streams"][0]
def packets(path):
    s = probe(path, "a:0"); n = int(s["nb_read_packets"]); dur = float(s["duration"]); sr = int(s.get("sample_rate", 48000))
    exp = dur * sr / 1024
    ok = abs(n - exp) <= 20
    print(f"[synccheck] {path}: {n} audio packets, expected {exp:.0f} for {dur:.2f}s → {'OK' if ok else 'FAIL (stacked/duplicated packets)'}")
    return ok
def offset(ref, test, times, shift_fn):
    import numpy as np
    def audio(p, t0, dur):
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", p, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    ok = True
    for t in times:
        exp = shift_fn(t)
        a = audio(ref, t, 6.0); b = audio(test, t + exp - 3.0, 12.0)
        a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
        d = int(np.argmax(np.correlate(b, a, mode="valid"))) / 8000.0 - 3.0
        good = abs(d) <= 0.15; ok &= good
        print(f"[synccheck] t={t}: audio offset vs reference {d:+.2f}s (expected shift {exp:.2f} already applied) → {'OK' if good else 'FAIL'}")
    return ok
def edl_offset(raw, base, cuts, times):
    """base vs raw at cut-timeline times mapped through the EDL — the sync test that survives concat gaps."""
    segs = json.load(open(cuts))["segments"]
    def raw_of(t):
        acc = 0.0
        for s in segs:
            d = float(s["end"]) - float(s["start"])
            if t < acc + d: return float(s["start"]) + (t - acc)
            acc += d
        return None
    import numpy as np
    def audio(p, t0, dur):
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", p, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
        return np.frombuffer(r, dtype=np.int16).astype(np.float32)
    ok = True
    for t in times:
        rt = raw_of(t)
        a = audio(raw, rt, 6.0); b = audio(base, t - 3.0, 12.0)
        a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
        d = int(np.argmax(np.correlate(b, a, mode="valid"))) / 8000.0 - 3.0
        good = abs(d) <= 0.15; ok &= good
        print(f"[synccheck] cut {t} (raw {rt:.2f}): base audio offset {d:+.2f}s → {'OK' if good else 'FAIL'}")
    return ok
if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "edl":
        raw, base, cuts, times = sys.argv[2], sys.argv[3], sys.argv[4], [float(x) for x in sys.argv[5].split(",")]
        sys.exit(0 if edl_offset(raw, base, cuts, times) else 1)
    if mode == "packets":
        sys.exit(0 if packets(sys.argv[2]) else 1)
    if mode == "offset":
        ref, test, times = sys.argv[2], sys.argv[3], [float(x) for x in sys.argv[4].split(",")]
        shift_fn = lambda t: 0.0
        if len(sys.argv) > 5:
            g = json.load(open(sys.argv[5])); fr = sorted((x["t"], x["hold"]) for x in g["gags"] if x["type"] == "freeze")
            shift_fn = lambda t, fr=fr: sum(D for tf, D in fr if tf < t)
        sys.exit(0 if offset(ref, test, times, shift_fn) else 1)
