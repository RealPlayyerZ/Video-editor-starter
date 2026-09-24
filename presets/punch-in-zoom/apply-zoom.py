#!/usr/bin/env python3
"""
apply-zoom.py — burn in the LOCKED punch-in zoom (see presets/punch-in-zoom-style.md).

GOTCHA this script exists to avoid: a single ffmpeg `crop` filter with BOTH width and
height driven by time-varying expressions across one continuous timeline produced
corrupted output when first tried (see the style doc's "FFMPEG GOTCHA" section). The fix
— proven out here the same way apply-outro.sh works around its own xfade bug — is to
never build one dynamic crop expression. Instead: split the video into segments at every
zoom-in/out boundary, apply a STATIC crop to each zoomed segment individually, re-encode
every segment with matching params, then concat. Hard cuts at every boundary (no
crossfade) — that's a locked stylistic choice, not just a side effect of this approach.

Usage:
  apply-zoom.py <input-video.mp4> <zoom-plan.json> <zoom-crop.json> <output-video.mp4>

zoom-plan.json   — from the `zoom-plan` skill: {"windows": [{"start":..,"end":..}, ...]}
zoom-crop.json   — from workflows/zoom-crop.py: {"crop": {"w":..,"h":..,"x":..,"y":..}}

Audio is untouched — a single continuous pass copied straight from the input, since the
zoom is video-only. Non-destructive: writes to the given output path, never overwrites
the input.
"""
import json, os, subprocess, sys, tempfile

CRF = "16"
PRESET = "medium"


def log(msg):
    print(f"[apply-zoom] {msg}", file=sys.stderr)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def probe_wh(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def build_segments(duration, windows):
    """Turn a list of zoomed windows into a full ordered list of {start,end,zoomed}
    segments covering [0, duration], filling the gaps with normal (non-zoomed) pieces."""
    windows = sorted(windows, key=lambda w: w["start"])
    segments = []
    cursor = 0.0
    for w in windows:
        s, e = max(0.0, w["start"]), min(duration, w["end"])
        if s > cursor + 0.01:
            segments.append({"start": cursor, "end": s, "zoomed": False})
        segments.append({"start": s, "end": e, "zoomed": True})
        cursor = e
    if cursor < duration - 0.01:
        segments.append({"start": cursor, "end": duration, "zoomed": False})
    return [s for s in segments if s["end"] - s["start"] > 0.02]


def main():
    if len(sys.argv) != 5:
        sys.exit("usage: apply-zoom.py <input-video> <zoom-plan.json> <zoom-crop.json> <output>")
    video, plan_path, crop_path, out_path = sys.argv[1:5]

    with open(plan_path) as f:
        plan = json.load(f)
    with open(crop_path) as f:
        crop_data = json.load(f)
    crop = crop_data["crop"]

    duration = probe_duration(video)
    w, h = probe_wh(video)
    log(f"input: {video}  {w}x{h}  {duration:.2f}s")
    log(f"crop window: {crop['w']}x{crop['h']} at ({crop['x']},{crop['y']}), scaled back to {w}x{h}")

    segments = build_segments(duration, plan["windows"])
    n_zoomed = sum(1 for s in segments if s["zoomed"])
    zoomed_secs = sum(s["end"] - s["start"] for s in segments if s["zoomed"])
    log(f"{len(segments)} segments ({n_zoomed} zoomed, {zoomed_secs:.1f}s / {duration:.1f}s total)")

    tmpdir = tempfile.mkdtemp(prefix="punch-in-zoom-")
    try:
        piece_paths = []
        for i, seg in enumerate(segments):
            piece = os.path.join(tmpdir, f"seg{i:03d}.mp4")
            dur = seg["end"] - seg["start"]
            if seg["zoomed"]:
                vf = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']},scale={w}:{h}:flags=lanczos"
                log(f"  seg{i:03d} [{seg['start']:.2f}-{seg['end']:.2f}] ZOOMED  vf={vf}")
                run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                     "-ss", str(seg["start"]), "-i", video, "-t", str(dur),
                     "-vf", vf, "-an",
                     "-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                     piece])
            else:
                log(f"  seg{i:03d} [{seg['start']:.2f}-{seg['end']:.2f}] normal")
                run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                     "-ss", str(seg["start"]), "-i", video, "-t", str(dur),
                     "-an",
                     "-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                     piece])
            piece_paths.append(piece)

        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for p in piece_paths:
                f.write(f"file '{p}'\n")

        video_only = os.path.join(tmpdir, "video_only.mp4")
        log("concatenating segments (hard cuts, stream-copy — all pieces share matching params)")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", video_only])

        log("muxing back the untouched original audio (single continuous pass, zoom is video-only)")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", video_only, "-i", video,
             "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "copy",
             "-movflags", "+faststart",
             out_path])

        out_dur = probe_duration(out_path)
        log(f"wrote {out_path}  ({out_dur:.2f}s, input was {duration:.2f}s)")
        if abs(out_dur - duration) > 0.5:
            log(f"⚠ output duration drifted {abs(out_dur - duration):.2f}s from input — "
                f"check segment boundaries before trusting this render")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
