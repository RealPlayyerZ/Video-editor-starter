#!/usr/bin/env python3
"""
splice_segments.py — the rough-cut splice for LONG cut lists (division2-legendary-mission, 2026-09-14/15).

rough-cut's splice.sh builds ONE ffmpeg graph that fans the source's audio and video out once per kept
segment (trim/atrim → concat). At 91 segments that graph's internal buffers saturate ~2 s in and ffmpeg
stamps ~96 audio packets with a single timestamp (rc 0, clean log) — the audio then runs 2 s behind the
video for the whole cut. Jobs with 1–10 segments are unaffected.

This script produces the SAME output contract (outputs/<job>.mp4 with the static +amp dB → hard-limiter
audio chain, and the derived outputs/<job>.transcript.json) with a construction that is exact by design:

  * every segment is rounded DOWN to whole 60 fps frames; the EDL on disk is rewritten to those lengths
    so export-transcript / zoom_plan / gags / synccheck all describe the file that exists
  * AUDIO: the source's audio is dumped ONCE to raw PCM and each segment is sliced by SAMPLE OFFSET in
    Python (exact; ffmpeg's seek-relative atrim landed ~3 ms late per segment, pts-absolute atrim dropped
    the last partial packet — both accumulate across 91 joins)
  * VIDEO: each segment is cut from the source with an accurate input seek (-ss before -i decodes from the
    previous keyframe and drops the frames before the cut) capped at the exact frame count with -frames:v
    (libx264 veryfast crf 18, like splice.sh)
  * each segment = one QuickTime file (video + PCM), joined with the concat demuxer (-c copy), then ONE
    pass applies the audio chain and encodes AAC once

Usage: splice_segments.py <job> [--amp 10] [--jobs 4] [--source FILE]
Reads projects/<job>/transcript/cuts.json (raw-timeline EDL), writes outputs/<job>.mp4 + .transcript.json
"""
import argparse, json, math, os, struct, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FF = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
SR, CH, BPS = 48000, 2, 2                       # 48 kHz stereo s16le
FPS = 60


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"[splice-seg] failed: {' '.join(cmd[:14])}…\n{r.stderr[-800:]}")


def probe_dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                                capture_output=True, text=True).stdout.strip())


def nb_frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else -1


def nframes(start, end):
    """whole 60 fps frames in [start, end): floor, with a 1e-3-frame tolerance so an EDL already rewritten to
    6-decimal frame-exact ends does not lose a frame to float noise (it did: 16 of 91 segments, 2026-09-15)"""
    return int(math.floor((end - start) * FPS + 1e-3))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--amp", type=float, default=10.0); ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--source", default=None, help="cut from this file instead of raw/<clip>")
    a = ap.parse_args()
    J = os.path.join(REPO, "projects", a.job); out_dir = os.path.join(J, "outputs"); work = os.path.join(J, "assemble_work", "splice_seg")
    os.makedirs(out_dir, exist_ok=True); os.makedirs(work, exist_ok=True)
    cuts = os.path.join(J, "transcript", "cuts.json"); segs = json.load(open(cuts))["segments"]
    # frame-exact EDL, written back so every downstream tool works on the real timeline
    for x in segs:
        x["end"] = round(float(x["start"]) + nframes(float(x["start"]), float(x["end"])) / FPS, 6)
    json.dump({"segments": segs}, open(cuts, "w"), indent=2)
    src_of = lambda clip: a.source if a.source else (clip if os.path.isabs(clip) else os.path.join(J, "raw", clip))
    sources = sorted({src_of(s["clip"]) for s in segs})

    # ---- audio: one PCM dump per source, then exact slices
    pcm = {}
    for src in sources:
        p = os.path.join(work, f"audio{sources.index(src)}.pcm")
        if not (os.path.isfile(p) and os.path.getsize(p) > 0):
            print(f"[splice-seg] dumping audio of {os.path.basename(src)} to PCM", flush=True)
            run(FF + ["-i", src, "-vn", "-ac", str(CH), "-ar", str(SR), "-f", "s16le", "-c:a", "pcm_s16le", p])
        pcm[src] = p
    frame_bytes = CH * BPS
    # colour tags of the source, passed EXPLICITLY to every segment encode (2026-09-15): per-segment libx264 runs
    # came out with mixed tags (unknown vs tv/bt709) and the stitched base then made a downstream filter graph
    # (gags) rebuild mid-stream and drop every later frame. One uniform tag set + square pixels on all segments.
    tags = []
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=color_range,color_space,color_primaries,color_transfer", "-of", "default=nw=1", sources[0]],
                        capture_output=True, text=True).stdout
    for line in pr.split():
        k, _, v = line.partition("=")
        if v and v not in ("unknown", "N/A"):
            tags += {"color_range": ["-color_range", v], "color_space": ["-colorspace", v],
                     "color_primaries": ["-color_primaries", v], "color_transfer": ["-color_trc", v]}[k]
    if not tags:
        tags = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    print(f"[splice-seg] colour tags for every segment: {' '.join(tags)}", flush=True)

    def cut_one(i_seg):
        i, s = i_seg; src = src_of(s["clip"]); X = float(s["start"])
        N = nframes(X, float(s["end"])); dur = N / FPS
        vseg, wseg, seg = (os.path.join(work, f"seg{i:03d}.{ext}") for ext in ("v.mov", "wav", "mov"))
        if os.path.isfile(seg) and os.path.getsize(seg) > 0:
            have = nb_frames(seg)
            if have == N:
                return seg
            print(f"[splice-seg] seg{i:03d}: existing file has {have} frames, wanted {N} — recutting", flush=True)
            os.remove(seg)
        # audio slice by sample offset
        s0 = int(round(X * SR)); n = int(round(dur * SR))
        with open(pcm[src], "rb") as f:
            f.seek(s0 * frame_bytes); data = f.read(n * frame_bytes)
        if len(data) < n * frame_bytes:
            data += b"\x00" * (n * frame_bytes - len(data))
        with wave.open(wseg, "wb") as w:
            w.setnchannels(CH); w.setsampwidth(BPS); w.setframerate(SR); w.writeframes(data)
        # video: accurate input seek to the cut point (frames before X are decoded and dropped), exactly N frames.
        # (a -copyts + absolute-pts trim variant silently lost the first GOP of segment 0 — 115 frames — so no copyts)
        run(FF + ["-ss", f"{X:.4f}", "-i", src, "-t", f"{dur:.4f}", "-frames:v", str(N), "-an",
                  "-vf", "setsar=1", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", *tags,
                  "-r", str(FPS), "-video_track_timescale", str(FPS), vseg])
        run(FF + ["-i", vseg, "-i", wseg, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", seg])
        nv = nb_frames(seg)
        if nv != N:
            raise SystemExit(f"[splice-seg] seg{i:03d}: {nv} frames, wanted {N} (raw {X:.3f}, {dur:.4f}s)")
        os.remove(vseg); os.remove(wseg)
        return seg

    print(f"[splice-seg] {len(segs)} segments, {a.jobs} in parallel", flush=True)
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        files = list(ex.map(cut_one, enumerate(segs)))
    lst = os.path.join(work, "concat.txt")
    with open(lst, "w") as f:
        for p in files: f.write(f"file '{os.path.abspath(p)}'\n")
    joined = os.path.join(work, "joined.mov")
    run(FF + ["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    out = os.path.join(out_dir, f"{a.job}.mp4")
    run(FF + ["-i", joined, "-map", "0:v", "-map", "0:a", "-c:v", "copy",
              "-af", f"volume={a.amp}dB,alimiter=level_in=1:level_out=1:limit=0.2512:attack=5:release=50:level=disabled",
              "-c:a", "aac", "-b:a", "256k", "-ar", str(SR), "-ac", str(CH), "-video_track_timescale", "90000", "-movflags", "+faststart", out])
    d = probe_dur(out); expect = sum(float(x["end"]) - float(x["start"]) for x in segs)
    print(f"[splice-seg] wrote {out} ({d:.3f}s; the cut list adds up to {expect:.3f}s)", flush=True)
    if abs(d - expect) > 0.25:
        raise SystemExit(f"[splice-seg] duration off by {d - expect:+.2f}s")
    words = os.path.join(J, "transcript", "words.json")
    run(["python3", os.path.join(REPO, ".claude", "skills", "cut", "scripts", "export-transcript.py"), words, cuts, os.path.join(out_dir, f"{a.job}.transcript.json")])
    print(f"[splice-seg] derived transcript → outputs/{a.job}.transcript.json", flush=True)
    for p in files: os.remove(p)
    os.remove(joined)
    for p in pcm.values(): os.remove(p)


if __name__ == "__main__":
    main()
