#!/usr/bin/env python3
"""
restore_cuts.py — apply the creator's answer to build_cuts.py's numbered cut list.

  --keep 1,5,6,7      keep ONLY these cuts; every other gap is restored (silence put back)
  --restore 9,10,13   the inverse: restore exactly these cuts, keep all others
  --narrow 9=4:09-4:15
                      restore cut #9 but re-cut a NARROWER window inside it (timestamps in the
                      recording's own time, exactly as the cut list printed them) — the
                      "restore cut #9 but make it 4:09 to 4:15 instead of 4:01 to 4:20" case

Cut numbers refer to the CURRENT transcript/cuts.json numbering (the list build_cuts.py printed,
or the list this script prints after it runs). Re-run splice.sh afterwards.

Reads   projects/<job>/transcript/cuts.json
Writes  /tmp/video-editor/<job>/cuts.json  and  projects/<job>/transcript/cuts.json

Usage:  presets/reaction/restore_cuts.py <job> (--keep N,N,… | --restore N,N,…) [--narrow N=start-end …]
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from build_cuts import mmss, write_cuts, report_cuts  # noqa: E402


def parse_ts(s):
    s = s.strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    sys.exit(f"[restore_cuts] bad timestamp {s!r}")


def parse_nums(s):
    return {int(x) for x in re.split(r"[,\s]+", s.strip()) if x}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--keep", help="cut numbers to KEEP; all others restored")
    g.add_argument("--restore", help="cut numbers to RESTORE; all others kept")
    ap.add_argument("--narrow", nargs="*", default=[], metavar="N=start-end",
                    help="restore cut N but re-cut only start-end inside it")
    args = ap.parse_args()

    path = os.path.join(REPO, "projects", args.job, "transcript", "cuts.json")
    if not os.path.isfile(path):
        sys.exit(f"[restore_cuts] no {path} — run build_cuts.py first")
    cur = json.load(open(path))["segments"]

    narrow = {}
    for spec in args.narrow:
        m = re.fullmatch(r"(\d+)=([^-]+)-(.+)", spec)
        if not m:
            sys.exit(f"[restore_cuts] bad --narrow {spec!r} (want N=start-end)")
        narrow[int(m.group(1))] = (parse_ts(m.group(2)), parse_ts(m.group(3)))

    total_cuts = sum(1 for a, b in zip(cur, cur[1:]) if a["clip"] == b["clip"])
    if args.keep is not None:
        keep = parse_nums(args.keep)
    else:
        keep = set(range(1, total_cuts + 1)) - parse_nums(args.restore)
    keep -= set(narrow)   # a narrowed cut is handled explicitly below
    bad = [n for n in keep | set(narrow) if not 1 <= n <= total_cuts]
    if bad:
        sys.exit(f"[restore_cuts] cut number(s) out of range 1..{total_cuts}: {sorted(bad)}")

    merged = [dict(cur[0])]
    cut_num = 0
    for prev, seg in zip(cur, cur[1:]):
        if prev["clip"] != seg["clip"]:
            merged.append(dict(seg))           # clip switch — never a "cut", always a hard boundary
            continue
        cut_num += 1
        if cut_num in narrow:
            n0, n1 = narrow[cut_num]
            if not (prev["end"] - 0.5 <= n0 < n1 <= seg["start"] + 0.5):
                sys.exit(f"[restore_cuts] --narrow {cut_num}: {mmss(n0)}-{mmss(n1)} is not inside the original "
                         f"cut {mmss(prev['end'])}-{mmss(seg['start'])}")
            merged[-1]["end"] = round(n0, 3)   # speech up to the narrower cut is restored
            new = dict(seg); new["start"] = round(n1, 3)
            merged.append(new)                 # and resumes right after it
        elif cut_num in keep:
            merged.append(dict(seg))           # keep this cut — new segment
        else:
            merged[-1]["end"] = seg["end"]     # restore — extend the current segment across the gap
            merged[-1]["transcript"] += " " + seg["transcript"]

    durable = write_cuts(args.job, merged)
    kept = sum(s["end"] - s["start"] for s in merged)
    print(f"[restore_cuts] {len(merged)} segments (was {len(cur)}), new total {kept:.2f}s ({kept / 60:.2f} min) -> {durable}")
    report_cuts(merged)
    print("\nNext: re-splice ->  bash presets/gameplay/splice_segments.py projects/" + args.job)


if __name__ == "__main__":
    main()
