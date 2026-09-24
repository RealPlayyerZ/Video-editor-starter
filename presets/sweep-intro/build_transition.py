#!/usr/bin/env python3
"""build_transition.py — the LOCKED mid-video sweep transition (see presets/sweep-intro-style.md
§ Mid-video transition). Same brand streak/flash recipe as the intro (imported directly from
build.py, never duplicated), applied as a BLUR CUT between two real pieces of content instead of
a synthetic zoom-from-one-still-frame like the intro uses.

Measured from real reference footage (the reference channel, 2026-08-26, article-reading -> reacting mode
switch): a real cut at a content boundary shows one clean frame, then ~0.3-0.5s later a heavily
motion-blurred frame, then a clean frame of the NEW content — the content swap itself is hidden
inside the blur peak. That's the same DURATION/PEAK_T/HOLD_END envelope already locked for the
intro (0.4s total), so this reuses it unchanged rather than measuring a new one from scratch.

Does NOT touch the intro (build.py, sweep-intro-style.md's locked intro section) at all — this
is a sibling script for a different point in the timeline, sharing only the streak/flash
compositing code.

Mechanism: replace the last (DURATION/2) of "before" with a zoom-blurring-in sequence on
that segment's own last frame, swap to the "after" segment's first frame exactly at peak
coverage (fully hidden by blur+streaks+flash), then zoom-blurring-out of that for the first
(DURATION/2) of "after". Net runtime is unchanged (0.4s of real footage is consumed to make
room for the 0.4s synthetic transition), matching the intro's own non-extending behavior.

Usage:
    build_transition.py <input-video.mp4> <cut-timestamp-seconds> <output-video.mp4> [--sfx sfx.mp3]

Splits <input-video> in two at <cut-timestamp>, generates the transition from the real
frames on either side of that exact point, and re-assembles. Segment-based (never one
dynamic-expression filter across the join) - same pattern presets/punch-in-zoom/apply-zoom.py
already uses for its own unrelated reason, and apply-outro.sh uses for its xfade bug.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import (   # noqa: E402  (shared, LOCKED recipe - imported, never copied)
    FPS, DURATION, N_FRAMES, PEAK_T, HOLD_END,
    make_streaks, coverage_at, composite_frame,
    scale_frame, DEFAULT_SFX, SFX_ATTACK_T,
)
from PIL import Image

HALF = DURATION / 2  # 0.2s consumed from each side of the cut


def run(cmd):
    subprocess.run(cmd, check=True)


def ffprobe(args, path):
    out = subprocess.run(["ffprobe", "-v", "error", *args, path], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def extract_frame(video, t, out_path):
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", str(max(0.0, t)), "-i", video, "-frames:v", "1", out_path])


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    in_video, cut_t, out_video = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    sfx_src = DEFAULT_SFX
    if "--sfx" in sys.argv:
        sfx_src = sys.argv[sys.argv.index("--sfx") + 1]

    if not os.path.isfile(in_video):
        print(f"[sweep-transition] no input video: {in_video}", file=sys.stderr)
        sys.exit(1)

    dur = float(ffprobe(["-show_entries", "format=duration", "-of", "default=nw=1:nk=1"], in_video))
    if cut_t <= HALF or cut_t >= dur - HALF:
        print(f"[sweep-transition] cut point {cut_t}s too close to an edge "
              f"(needs >={HALF}s of real footage on each side) — skipping", file=sys.stderr)
        sys.exit(1)

    w = int(ffprobe(["-select_streams", "v:0", "-show_entries", "stream=width", "-of", "default=nw=1:nk=1"], in_video))
    h = int(ffprobe(["-select_streams", "v:0", "-show_entries", "stream=height", "-of", "default=nw=1:nk=1"], in_video))
    print(f"[sweep-transition] input {w}x{h}, cut at {cut_t:.2f}s (consuming {HALF}s each side)", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        before_path = os.path.join(tmp, "before.png")
        after_path = os.path.join(tmp, "after.png")
        extract_frame(in_video, cut_t - HALF, before_path)
        extract_frame(in_video, cut_t + HALF, after_path)
        before_img = Image.open(before_path).convert("RGB")
        after_img = Image.open(after_path).convert("RGB")

        streaks = make_streaks()  # same seed=7 default as the intro - same brand look
        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        for i in range(N_FRAMES):
            t = i / FPS
            coverage = coverage_at(t)
            # Blurring INTO peak on "before"'s own last frame, swap at the hold (fully
            # hidden by max coverage), blur back OUT on "after"'s first frame. Reuses the
            # intro's own self-relative zoom math (scale_frame) for a little life in the
            # held frames rather than a completely static hold.
            base = before_img if t <= HOLD_END else after_img
            scale = 1.0 + 0.12 * min(1.0, coverage)  # gentler than the intro's 1.32x - this
            # frame isn't the "hero" reveal, just bridging two real moments
            primary = scale_frame(base, w, h, scale)
            frame = composite_frame(primary, primary, streaks, w, h, coverage)
            frame.save(os.path.join(frames_dir, f"f{i:03d}.png"))

        transition_clip = os.path.join(tmp, "transition.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%03d.png"),
             "-t", str(DURATION), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", transition_clip])

        head_clip = os.path.join(tmp, "head.mp4")
        tail_clip = os.path.join(tmp, "tail.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", in_video, "-t", str(cut_t - HALF), "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", head_clip])
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", str(cut_t + HALF), "-i", in_video, "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", tail_clip])

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w") as f:
            for clip in (head_clip, transition_clip, tail_clip):
                f.write(f"file '{clip}'\n")
        video_only = os.path.join(tmp, "video_only.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", video_only])

        # Audio: keep the original track continuous (untouched) EXCEPT mix in the whoosh
        # right at the cut point, attack aligned the same way the intro syncs it.
        audio_only = os.path.join(tmp, "audio_only.m4a")
        if os.path.isfile(sfx_src):
            sfx_start = max(0.0, cut_t - HALF + PEAK_T - SFX_ATTACK_T)
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", in_video, "-i", sfx_src,
                 "-filter_complex",
                 f"[1:a]adelay={int(sfx_start * 1000)}|{int(sfx_start * 1000)}[sfx];"
                 f"[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                 "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", audio_only])
        else:
            print(f"[sweep-transition] ⚠ sfx not found at {sfx_src}, no whoosh mixed in", file=sys.stderr)
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", in_video, "-vn", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", audio_only])

        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", video_only, "-i", audio_only,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
             "-movflags", "+faststart", out_video])

    out_dur = float(ffprobe(["-show_entries", "format=duration", "-of", "default=nw=1:nk=1"], out_video))
    print(f"[sweep-transition] wrote {out_video}  ({out_dur:.2f}s, input was {dur:.2f}s)", file=sys.stderr)
    if abs(out_dur - dur) > 0.3:
        print(f"⚠ duration drifted {abs(out_dur - dur):.2f}s from input — check the cut point", file=sys.stderr)


if __name__ == "__main__":
    main()
