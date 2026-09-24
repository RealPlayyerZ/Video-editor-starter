#!/usr/bin/env python3
"""
build_cuts.py — the REACTION-cadence cut list (see workflows/reaction-video.md, step 2).

Instead of rough-cut's default filler-kill, a reaction video keeps the creator's natural
pauses (thinking, laughing, watching the screen) and only hard-cuts genuine dead air:

  * consecutive words are merged into one kept segment across any gap <= --gap-keep (3.0s)
  * any gap longer than that is CUT (the silence is dropped entirely)

Then it prints the numbered CUT LIST in m:ss so the creator can answer "restore cuts 9, 10,
13" — some of that "dead air" is an embedded clip playing with its own audio, and only they
know which. Feed their answer to restore_cuts.py.

Reads   projects/<job>/transcript/words.json   (canonical, from rough-cut's transcribe.sh)
Writes  /tmp/video-editor/<job>/cuts.json       (what rough-cut's splice.sh reads)
        projects/<job>/transcript/cuts.json     (durable copy; splice.sh re-persists it too)

Usage:  presets/reaction/build_cuts.py <job> [--gap-keep 3.0] [--pad-start 0.05] [--pad-end 0.08]
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def mmss(t):
    total = int(round(t))            # round ONCE, then split — avoids the 0:00:54 -> "0:00" carry bug
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_cuts(job, segments):
    tmp_dir = f"/tmp/video-editor/{job}"
    os.makedirs(tmp_dir, exist_ok=True)
    durable = os.path.join(REPO, "projects", job, "transcript", "cuts.json")
    for path in (os.path.join(tmp_dir, "cuts.json"), durable):
        with open(path, "w") as f:
            json.dump({"segments": segments}, f, indent=2)
    return durable


def report_cuts(segments):
    """Number every inter-segment gap within a clip, in order — the numbers the creator answers with."""
    print("\nCUT LIST (numbered gaps dropped from the recording — say which to RESTORE):")
    n = 0
    for prev, seg in zip(segments, segments[1:]):
        if prev["clip"] != seg["clip"]:
            continue
        n += 1
        gap = seg["start"] - prev["end"]
        print(f"  cut #{n:2d}  {mmss(prev['end'])} -> {mmss(seg['start'])}  ({gap:5.1f}s)   "
              f"…{prev['transcript'][-40:]} | {seg['transcript'][:40]}…")
    print(f"  {n} cuts total")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--gap-keep", type=float, default=3.0, help="keep pauses up to this many seconds")
    ap.add_argument("--pad-start", type=float, default=0.05)
    ap.add_argument("--pad-end", type=float, default=0.08)
    args = ap.parse_args()

    words_path = os.path.join(REPO, "projects", args.job, "transcript", "words.json")
    if not os.path.isfile(words_path):
        sys.exit(f"[build_cuts] no transcript at {words_path} — run rough-cut's transcribe.sh first")
    d = json.load(open(words_path))

    segments = []
    for clip in d["clips"]:
        words, name = clip["words"], clip["clip"]
        run_start = 0
        for i in range(1, len(words) + 1):
            gap = (words[i]["start"] - words[i - 1]["end"]) if i < len(words) else None
            if gap is None or gap > args.gap_keep:
                run = words[run_start:i]
                segments.append({
                    "clip": name,
                    "start": round(max(0.0, run[0]["start"] - args.pad_start), 3),
                    "end": round(run[-1]["end"] + args.pad_end, 3),
                    "transcript": " ".join(w["w"] for w in run),
                })
                run_start = i

    durable = write_cuts(args.job, segments)
    kept = sum(s["end"] - s["start"] for s in segments)
    raw = sum(c.get("duration", 0) for c in d["clips"]) or max(s["end"] for s in segments)
    print(f"[build_cuts] {len(segments)} segments, kept {kept:.1f}s of {raw:.1f}s ({kept / raw * 100:.1f}%) -> {durable}")
    report_cuts(segments)


if __name__ == "__main__":
    main()
