#!/usr/bin/env python3
"""
mix-music-ducked.py — lay a background music bed under a VOICE-ONLY cut, ducking it out
(fade → silent → fade back) across windows where an embedded clip plays its own audio.
Rotates through several tracks so a long video doesn't loop one bed the whole way.

Standing rules baked in (every one learned the hard way on gpt-astra-6-reaction and
dlss-5-reaction, 2026-09-08 — see workflows/reaction-video.md):

  1. THE INPUT MUST BE THE VOICE-ONLY CUT (voice + SFX, no music). Layering a ducked bed on
     top of a file that already carries a flat bed leaves the OLD bed playing straight
     through every duck window, unducked — and it looks fine in the build log. This script
     measures the input's quietest gaps and warns when it looks like a bed is already there.
  2. ffmpeg's `afade=t=in:st=X` silences EVERYTHING before X, not just the ramp. So the
     timeline is split into chunks bounded exactly at every fade edge and each fade is applied
     chunk-locally with st=0. Never one long filter chain.
  3. Every intermediate is PCM (.wav). AAC is encoded exactly once, at the final mux. Encoding
     each chunk to AAC and concatenating clicks at every boundary and drifts on long files.
  4. Verification runs on the DELIVERED file, not the log: every duck-window midpoint must
     match the voice-only input (bed truly silent), and a natural silence gap outside the
     windows must be clearly louder than the input (bed truly present).

Usage:
  mix-music-ducked.py <voice-only.mp4> <out.mp4> --tracks a.mp3 [b.mp3 ...]
      [--duck 1:34-2:10 3:02-3:34 ...] [--bed-db -24] [--fade 2.0]
      [--max-chunk 150] [--work DIR] [--force]

  --duck windows accept "m:ss", "h:mm:ss" or plain seconds, written as start-end. Give the
  timestamps exactly as the creator calls them out on a watch-through — that's the input this
  step is designed around. No --duck = a flat bed with track rotation only.

Run it on the near-final cut BEFORE the outro (CLAUDE.md step 6, before step 7): the outro
step's own audio crossfade then blends this bed into the outro track. Non-destructive.
"""
import argparse, os, re, subprocess, sys

FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


def log(msg):
    print(f"[mix-ducked] {msg}", flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"[mix-ducked] command failed: {' '.join(cmd)}")
    return r


def ffprobe_dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def parse_ts(s):
    s = s.strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise SystemExit(f"[mix-ducked] bad timestamp: {s!r} (want m:ss, h:mm:ss or seconds)")
    parts = [float(p) for p in parts]
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]


def parse_window(s):
    if "-" not in s:
        raise SystemExit(f"[mix-ducked] bad window: {s!r} (want start-end)")
    a, b = s.rsplit("-", 1)
    st, en = parse_ts(a), parse_ts(b)
    if en <= st:
        raise SystemExit(f"[mix-ducked] window end must be after start: {s!r}")
    return st, en


def volumedetect(path, ss, dur):
    r = subprocess.run(["ffmpeg", "-ss", f"{ss:.3f}", "-t", f"{dur:.3f}", "-i", path,
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    mean = maxv = None
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            mean = float(line.split(":")[1].split()[0])
        elif "max_volume" in line:
            maxv = float(line.split(":")[1].split()[0])
    return mean, maxv


def silence_gaps(path, noise_db, min_dur, t0=0.0, t1=None):
    """[(start, end), ...] of stretches quieter than noise_db for at least min_dur seconds."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner"]
    if t0:
        cmd += ["-ss", f"{t0:.3f}"]
    cmd += ["-i", path]
    if t1 is not None:
        cmd += ["-t", f"{max(0.0, t1 - t0):.3f}"]
    cmd += ["-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    gaps, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1)) + t0
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            gaps.append((start, float(m.group(1)) + t0))
            start = None
    return gaps


def build_chunk_edges(total, windows, fade, max_chunk):
    edges = {0.0, total}
    for st, en in windows:
        edges.update([max(0.0, st - fade), st, en, min(total, en + fade)])
    edges = sorted(e for e in edges if 0.0 <= e <= total)
    out = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 0.005:
            continue
        n = max(1, int((b - a) // max_chunk) + 1)
        step = (b - a) / n
        out.extend((a + i * step, a + (i + 1) * step) for i in range(n))
    return out


def fade_for_chunk(c0, c1, windows, fade):
    """The ONE envelope piece this chunk is (out-ramp / silent / in-ramp), else None (flat)."""
    for st, en in windows:
        out_ramp = (max(0.0, st - fade), st)
        in_ramp = (en, en + fade)
        if out_ramp[0] < c1 and out_ramp[1] > c0:
            return f"afade=t=out:st={out_ramp[0] - c0:.3f}:d={fade}"
        if in_ramp[0] < c1 and in_ramp[1] > c0:
            return f"afade=t=in:st={in_ramp[0] - c0:.3f}:d={fade}"
        if st <= c0 and c1 <= en:
            return "volume=0"
    return None


def track_for_chunk(c0, windows, tracks):
    """Switch tracks only across a duck window (while the bed is silent), so the switch is inaudible."""
    seg_idx = sum(1 for (_, en) in windows if en <= c0)
    return tracks[seg_idx % len(tracks)]


def music_slice(track, music_dur, c0, dur, out_wav, work, i):
    """`dur` seconds of `track`, starting at the track position that keeps it looping continuously."""
    loop_pos = c0 % music_dur
    if loop_pos + dur <= music_dur:
        run(FFMPEG + ["-ss", f"{loop_pos:.3f}", "-i", track, "-t", f"{dur:.3f}", "-c:a", "pcm_s16le", out_wav])
        return
    part_a = f"{work}/musicsrc{i:03d}a.wav"
    part_b = f"{work}/musicsrc{i:03d}b.wav"
    run(FFMPEG + ["-ss", f"{loop_pos:.3f}", "-i", track, "-c:a", "pcm_s16le", part_a])
    run(FFMPEG + ["-i", track, "-t", f"{dur - (music_dur - loop_pos):.3f}", "-c:a", "pcm_s16le", part_b])
    plist = f"{work}/musicsrc{i:03d}.txt"
    with open(plist, "w") as f:
        f.write(f"file '{os.path.abspath(part_a)}'\nfile '{os.path.abspath(part_b)}'\n")
    run(FFMPEG + ["-f", "concat", "-safe", "0", "-i", plist, "-c:a", "pcm_s16le", out_wav])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", help="the VOICE-ONLY near-final cut (no music bed in it yet)")
    ap.add_argument("out", help="output .mp4 (video stream copied, audio re-mixed)")
    ap.add_argument("--tracks", nargs="+", required=True, help="one or more music files, rotated per segment")
    ap.add_argument("--duck", nargs="*", default=[], help='windows like 1:34-2:10 (music silent inside, fades at edges)')
    ap.add_argument("--bed-db", type=float, default=-24.0, help="bed gain in dB (house default -24: sits under the voice)")
    ap.add_argument("--fade", type=float, default=2.0, help="fade-out / fade-in seconds at each duck edge")
    ap.add_argument("--max-chunk", type=float, default=150.0, help="max seconds per mix chunk")
    ap.add_argument("--work", default=None, help="scratch dir (default: <out dir>/mix_ducked_work)")
    ap.add_argument("--force", action="store_true", help="proceed even if the input looks like it already has a bed")
    args = ap.parse_args()

    for t in args.tracks:
        if not os.path.isfile(t):
            raise SystemExit(f"[mix-ducked] no such track: {t}")
    if not os.path.isfile(args.video):
        raise SystemExit(f"[mix-ducked] no such video: {args.video}")

    total = ffprobe_dur(args.video)
    windows = sorted(parse_window(w) for w in args.duck)
    for (a0, a1), (b0, b1) in zip(windows, windows[1:]):
        if b0 < a1 + args.fade:
            log(f"note: windows {a0:.1f}-{a1:.1f} and {b0:.1f}-{b1:.1f} are closer than one fade — "
                f"the bed will barely surface between them (that is usually what you want)")
    windows = [(st, min(en, total)) for st, en in windows if st < total]
    work = args.work or os.path.join(os.path.dirname(os.path.abspath(args.out)), "mix_ducked_work")
    os.makedirs(work, exist_ok=True)

    log(f"input {total:.1f}s, {len(windows)} duck window(s), {len(args.tracks)} track(s), bed {args.bed_db:g}dB, fade {args.fade:g}s")

    # Rule 1 guard (heuristic, WARN only): a voice-only cut has quiet pauses between sentences; a
    # file that already carries a bed tends not to drop that low. Measured on real jobs: voice-only
    # pauses peak anywhere from -84dB (clean) to -40dB (room tone); the same pause on a bedded file
    # peaked -47dB. Overlap is real, so this cannot be a hard gate — it only flags the obvious case.
    deep_gaps = silence_gaps(args.video, -60, 0.3)
    if not deep_gaps:
        log("WARNING: input has NO stretch quieter than -60dB. If it already carries a music bed, "
            "STOP — this script must run on the voice-only cut (before any music), or the old bed "
            "keeps playing straight through every duck window. Noisy room tone can also trip this; "
            "if you are sure it is voice-only, carry on.")
    else:
        log(f"input looks voice-only ({len(deep_gaps)} quiet pause(s) found) ✓")

    chunks = build_chunk_edges(total, windows, args.fade, args.max_chunk)
    music_durs = {t: ffprobe_dur(t) for t in args.tracks}
    log(f"{len(chunks)} chunks")

    chunk_files = []
    for i, (c0, c1) in enumerate(chunks):
        dur = c1 - c0
        piece = fade_for_chunk(c0, c1, windows, args.fade)
        music_filter = f"volume={args.bed_db:g}dB" + (f",{piece}" if piece else "")
        track = track_for_chunk(c0, windows, args.tracks)
        src = f"{work}/musicsrc{i:03d}.wav"
        music_slice(track, music_durs[track], c0, dur, src, work, i)
        out_chunk = f"{work}/chunk{i:03d}.wav"
        fc = (f"[0:a]atrim={c0:.3f}:{c1:.3f},asetpts=PTS-STARTPTS[voice];"
              f"[1:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,{music_filter}[music];"
              f"[voice][music]amix=inputs=2:normalize=0[outa]")
        run(FFMPEG + ["-i", args.video, "-i", src, "-filter_complex", fc, "-map", "[outa]",
                      "-t", f"{dur:.3f}", "-c:a", "pcm_s16le", out_chunk])
        chunk_files.append(out_chunk)
        log(f"  chunk{i:03d} [{c0:8.2f}-{c1:8.2f}] {piece or 'flat':<28} {os.path.basename(track)}")

    concat_list = f"{work}/concat.txt"
    with open(concat_list, "w") as f:
        for p in chunk_files:
            f.write(f"file '{os.path.abspath(p)}'\n")
    full_wav = f"{work}/full_audio.wav"
    run(FFMPEG + ["-f", "concat", "-safe", "0", "-i", concat_list, "-c:a", "pcm_s16le", full_wav])

    # The ONE AAC encode.
    run(FFMPEG + ["-i", args.video, "-i", full_wav, "-map", "0:v", "-map", "1:a",
                  "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                  "-shortest", "-movflags", "+faststart", args.out])
    out_dur = ffprobe_dur(args.out)
    log(f"wrote {args.out} ({out_dur:.3f}s, input {total:.3f}s)")

    # Rule 4: verify the delivered file.
    ok = True
    for st, en in windows:
        if en - st < 0.6:
            continue
        mid = (st + en) / 2
        probe = min(2.0, en - st - 0.4)
        m_out, _ = volumedetect(args.out, mid - probe / 2, probe)
        m_in, _ = volumedetect(args.video, mid - probe / 2, probe)
        delta = abs((m_out or -99) - (m_in or -99))
        status = "OK" if delta < 1.5 else "FAIL"
        ok &= status == "OK"
        log(f"  duck [{st:.1f}-{en:.1f}] mid {mid:.1f}s: out {m_out}dB vs voice-only {m_in}dB (Δ{delta:.1f}dB) [{status}]")

    # Bed presence: a natural pause in the voice-only input, outside every window (+fades).
    def outside(t):
        return all(t < st - args.fade - 0.5 or t > en + args.fade + 0.5 for st, en in windows)
    gap = next(((a, b) for a, b in silence_gaps(args.video, -35, 0.5) if outside(a) and outside(b) and b - a >= 0.5), None)
    if gap:
        a, b = gap
        m_out, _ = volumedetect(args.out, a + 0.05, min(1.0, b - a - 0.1))
        m_in, _ = volumedetect(args.video, a + 0.05, min(1.0, b - a - 0.1))
        lift = (m_out or -99) - (m_in or -99)
        status = "OK" if lift >= 4.0 else "FAIL"
        ok &= status == "OK"
        log(f"  bed presence at pause {a:.1f}s: out {m_out}dB vs voice-only {m_in}dB (+{lift:.1f}dB) [{status}]")
    else:
        log("  bed presence: no clean pause outside the duck windows to measure — check by ear")

    if abs(out_dur - total) > 0.5:
        ok = False
        log(f"  duration drifted {abs(out_dur - total):.2f}s [FAIL]")

    if not ok:
        failed = args.out + ".FAILED.mp4"
        os.replace(args.out, failed)
        raise SystemExit(f"[mix-ducked] VERIFICATION FAILED — output kept as {failed} for inspection, do not ship it")
    log("VERIFIED ✓ (duck windows silent, bed present, duration intact)")


if __name__ == "__main__":
    main()
