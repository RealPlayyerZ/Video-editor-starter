#!/usr/bin/env python3
"""
verify-final.py — the "did it actually ship right?" gate. Runs on the DELIVERED file.

Why this exists (2026-09-08): two videos went out with a ~2s frozen frame at the body→outro
seam, and a music fix that "passed" its build log twice while the delivered file was still
wrong. Every one of those was catchable by looking at the output file itself instead of the
steps that produced it. finalize.sh runs this before promoting a render; run it by hand any
time a re-render is meant to be the fix.

Checks:
  streams   one video + one audio stream, sane resolution/fps
  durations container / video / audio agree to within 0.5s
  freeze    frame-difference sweep across the body→outro seam (the spot that broke) plus
            evenly spaced samples over the whole file; ≥3 consecutive near-identical
            samples anywhere outside the outro's own static end card = FAIL
  audio     peak clear of the limiter ceiling (no clipping); any ≥4s of near-digital silence
            before the last few seconds is reported (WARN)
  expected  optional --expect-duration within 1.0s

Exit 0 = PASS, 1 = FAIL (WARNs never fail on their own). --json prints a machine-readable report.

Usage:
  verify-final.py <final.mp4> [--outro-duration 20.78] [--no-outro] [--expect-duration S] [--json]
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile

OUTRO_DEFAULT = 20.78   # the locked outro asset (presets/outro-style.md)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate,duration",
                          "-of", "json", path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def frame_at(path, t, tmp, i):
    """Small greyscale frame at t → flat list of pixel values (None if no frame there)."""
    png = os.path.join(tmp, f"f{i:04d}.png")
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{max(0.0, t):.3f}", "-i", path, "-frames:v", "1",
                    "-vf", "scale=160:90,format=gray", png], capture_output=True)
    if not os.path.isfile(png):
        return None
    try:
        from PIL import Image
        img = Image.open(png)
        # Pillow ≥12 renamed getdata → get_flattened_data; support both without the warning.
        getter = getattr(img, "get_flattened_data", None) or img.getdata
        return list(getter())
    except ImportError:
        return hashlib.md5(open(png, "rb").read()).hexdigest()


def mean_abs_diff(a, b):
    if isinstance(a, str) or isinstance(b, str):   # md5 fallback: identical or not
        return 0.0 if a == b else 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def audio_stats(path):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-vn",
                        "-af", "volumedetect,silencedetect=noise=-60dB:d=4", "-f", "null", "-"],
                       capture_output=True, text=True)
    maxv = meanv = None
    silences, start = [], None
    for line in r.stderr.splitlines():
        if "max_volume" in line:
            maxv = float(line.split(":")[1].split()[0])
        elif "mean_volume" in line:
            meanv = float(line.split(":")[1].split()[0])
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    return maxv, meanv, silences


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--outro-duration", type=float, default=OUTRO_DEFAULT,
                    help="length of the outro at the end (its static end card is allowed to be static)")
    ap.add_argument("--no-outro", action="store_true", help="file has no outro: sweep the last 30s instead")
    ap.add_argument("--expect-duration", type=float, default=None)
    # Calibrated 2026-09-08 on real footage: a TRUE duplicate frame (the outro-seam freeze) measures
    # ~0.00 on a 160x90 grey thumbnail; a creator merely holding still measures 0.38-0.69; normal
    # talking is 1-5. 0.15 catches every real freeze and never fires on a still shot.
    ap.add_argument("--freeze-threshold", type=float, default=0.15,
                    help="mean abs pixel diff (0-255) below which two samples count as identical")
    ap.add_argument("--static-tail", type=float, default=0.0,
                    help="with --no-outro: the last N seconds are a DECLARED held ending (a Shorts reaction clip that "
                         "ends on a still, fading out) and may be static; everything before it must still move")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.video):
        sys.exit(f"[verify] no such file: {args.video}")

    report = {"file": args.video, "checks": [], "warnings": [], "pass": True}

    def check(name, ok, detail):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["pass"] = False
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}: {detail}")

    def warn(name, detail):
        report["warnings"].append({"name": name, "detail": detail})
        print(f"  [WARN] {name}: {detail}")

    print(f"=== verify-final: {os.path.basename(args.video)} ===")
    info = probe(args.video)
    fmt_dur = float(info["format"]["duration"])
    v = [s for s in info["streams"] if s["codec_type"] == "video"]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    check("streams", len(v) >= 1 and len(a) >= 1, f"{len(v)} video, {len(a)} audio")
    if not (v and a):
        print(json.dumps(report, indent=2) if args.json else "RESULT: FAIL")
        sys.exit(1)
    vs, as_ = v[0], a[0]
    fps_n, fps_d = (vs.get("r_frame_rate") or "0/1").split("/")
    fps = float(fps_n) / float(fps_d or 1)
    check("geometry", int(vs.get("width", 0)) >= 640 and fps >= 23, f"{vs.get('width')}x{vs.get('height')} @ {fps:.3f}fps")

    v_dur = float(vs.get("duration") or fmt_dur)
    a_dur = float(as_.get("duration") or fmt_dur)
    check("durations agree", abs(v_dur - a_dur) <= 0.5 and abs(fmt_dur - v_dur) <= 0.5,
          f"container {fmt_dur:.3f}s, video {v_dur:.3f}s, audio {a_dur:.3f}s")
    if args.expect_duration is not None:
        check("expected duration", abs(fmt_dur - args.expect_duration) <= 1.0,
              f"{fmt_dur:.3f}s vs expected {args.expect_duration:.3f}s")

    # Freeze sweep. Seam = where the body meets the outro; that is where apply-outro.sh froze.
    outro = 0.0 if args.no_outro else args.outro_duration
    seam = fmt_dur - outro
    if args.no_outro:
        # last 30s (or the whole file if shorter) — never clamp repeated samples onto t=0, which
        # reads as a fake freeze on any file under 30s (bit the Shorts clipper on a 24s clip)
        sweep_start = max(0.0, fmt_dur - 30.0)
        dense = [sweep_start + i * 0.4 for i in range(int((fmt_dur - sweep_start) / 0.4) + 1)]
        static_ok_after = fmt_dur - args.static_tail   # nothing is allowed to be static, except a declared held ending
    else:
        dense = [seam - 8 + i * 0.4 for i in range(int(12 / 0.4) + 1)]   # seam-8 … seam+4
        static_ok_after = fmt_dur - 6.0     # the locked end card holds for the last few seconds
    dense = [t for t in dense if 0.0 <= t < fmt_dur - 0.1]
    coarse = [fmt_dur * (i + 0.5) / 12 for i in range(12)]

    with tempfile.TemporaryDirectory() as tmp:
        for label, times in (("seam", dense), ("global", coarse)):
            frames = [(t, frame_at(args.video, t, tmp, i)) for i, t in enumerate(times)]
            frames = [(t, f) for t, f in frames if f is not None]
            run_len, worst_run, worst_at = 1, 1, None
            for (t0, f0), (t1, f1) in zip(frames, frames[1:]):
                if mean_abs_diff(f0, f1) < args.freeze_threshold and t1 < static_ok_after:
                    run_len += 1
                    if run_len > worst_run:
                        worst_run, worst_at = run_len, t0
                else:
                    run_len = 1
            step = (times[1] - times[0]) if len(times) > 1 else 0
            frozen = worst_run >= 3
            check(f"freeze sweep ({label})", not frozen,
                  f"{len(frames)} samples, longest static run {worst_run}"
                  + (f" (~{(worst_run - 1) * step:.1f}s starting {worst_at:.1f}s)" if frozen else ""))

    maxv, meanv, silences = audio_stats(args.video)
    if maxv is not None:
        check("audio peak", maxv <= -0.3, f"max {maxv:.1f}dB, mean {meanv:.1f}dB (ceiling -1dB, limiter guards it)")
    early = [(s, e) for s, e in silences if e < fmt_dur - 3.0]
    if early:
        warn("audio silence", "; ".join(f"{s:.1f}-{e:.1f}s ({e - s:.1f}s)" for s, e in early[:5])
             + " — ≥4s of near-digital silence before the end; expected only if the source really goes quiet")

    print(f"RESULT: {'PASS' if report['pass'] else 'FAIL'}"
          + (f"  ({len(report['warnings'])} warning(s))" if report["warnings"] else ""))
    if args.json:
        print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
