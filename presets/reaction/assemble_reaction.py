#!/usr/bin/env python3
"""
assemble_reaction.py — final video assembly for a REACTION job (see workflows/reaction-video.md).

Generalized 2026-09-08 from the per-job copies on gpt-astra-6-reaction / dlss-5-reaction (which
were identical except for the job name). No reading-mode paragraph cards: the input is the
zoom-applied base (`outputs/<job>.zoomed.mp4`, from apply-zoom.py) and this script

  1. cuts it into one span per zoom-plan window,
  2. renders the locked sweep-style whoosh transition at every INTERNAL window boundary
     (zoom↔wide switches) — imported from presets/sweep-intro/build.py, never copied,
  3. concatenates spans + transitions into a video-only track,
  4. lays the ORIGINAL continuous voice track under it plus the whoosh SFX at each boundary,
  5. muxes → `outputs/<job>.composited.mp4` (voice + SFX only — music is a LATER step, and
     that ordering is load-bearing: see workflows/reaction-video.md, "standing rules").

Usage:
  presets/reaction/assemble_reaction.py <job> [--zoomed-base PATH] [--plan PATH] [--size 2560x1440]

Resumable: spans and transitions already present in projects/<job>/assemble_work/ are reused.
"""
import argparse, glob, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "presets", "sweep-intro"))
from build import (  # noqa: E402  (the locked sweep primitives)
    FPS, DURATION, N_FRAMES, HOLD_END,
    make_streaks, coverage_at, composite_frame, scale_frame,
    DEFAULT_SFX,
)
from PIL import Image  # noqa: E402

HALF = DURATION / 2  # each side of a boundary gives up half the transition's length


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")


def ffprobe_dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def extract_frame_sequence(video, t_start, n, tmp_dir, prefix):
    pattern = os.path.join(tmp_dir, f"{prefix}%03d.png")
    for attempt in range(3):
        for p in glob.glob(os.path.join(tmp_dir, f"{prefix}*.png")):
            os.remove(p)
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", video, "-ss", str(max(0.0, t_start)), "-frames:v", str(n),
                            "-start_number", "0", pattern], capture_output=True, text=True)
        frames, i = [], 0
        while os.path.isfile(os.path.join(tmp_dir, f"{prefix}{i:03d}.png")):
            frames.append(Image.open(os.path.join(tmp_dir, f"{prefix}{i:03d}.png")).convert("RGB"))
            i += 1
        if frames:
            return frames
        print(f"[extract_frame_sequence] attempt {attempt + 1} got 0 frames from {video} @ {t_start} "
              f"(rc={r.returncode}); retrying", file=sys.stderr)
    raise SystemExit(f"extract_frame_sequence: never got a frame from {video} @ {t_start}")


def build_transition_clip(before_clip, after_clip, w, h, out_path):
    """The locked mid-video sweep: hold the outgoing frame, streak/flash, land on the incoming one."""
    streaks = make_streaks()
    with tempfile.TemporaryDirectory() as tmp:
        before_frames = extract_frame_sequence(before_clip, 0.0, N_FRAMES, tmp, "b")
        after_frames = extract_frame_sequence(after_clip, 0.0, N_FRAMES, tmp, "a")
        for i in range(N_FRAMES):
            t = i / FPS
            coverage = coverage_at(t)
            if t <= HOLD_END:
                base = before_frames[min(i, len(before_frames) - 1)]
            else:
                after_i = max(0, i - int(round(HOLD_END * FPS)))
                base = after_frames[min(after_i, len(after_frames) - 1)]
            scale = 1.0 + 0.12 * min(1.0, coverage)
            primary = scale_frame(base, w, h, scale)
            composite_frame(primary, primary, streaks, w, h, coverage).save(os.path.join(tmp, f"f{i:03d}.png"))
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-framerate", str(FPS), "-i", os.path.join(tmp, "f%03d.png"),
             "-t", str(DURATION), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", out_path])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--zoomed-base", default=None, help="default projects/<job>/outputs/<job>.zoomed.mp4")
    ap.add_argument("--plan", default=None, help="default projects/<job>/zoom-plan.json")
    ap.add_argument("--size", default="2560x1440", help="output canvas WxH")
    args = ap.parse_args()

    job_dir = os.path.join(REPO, "projects", args.job)
    zoomed = args.zoomed_base or os.path.join(job_dir, "outputs", f"{args.job}.zoomed.mp4")
    plan_path = args.plan or os.path.join(job_dir, "zoom-plan.json")
    work = os.path.join(job_dir, "assemble_work")
    for p in (zoomed, plan_path):
        if not os.path.isfile(p):
            raise SystemExit(f"[assemble] missing: {p}")
    os.makedirs(work, exist_ok=True)
    W, H = (int(x) for x in args.size.lower().split("x"))

    plan = json.load(open(plan_path))
    windows = sorted(plan["windows"], key=lambda w_: w_["start"])
    boundaries = [w_["start"] for w_ in windows[1:]]   # internal boundaries only
    total_dur = ffprobe_dur(zoomed)
    edges = [0.0] + boundaries + [total_dur]
    n = len(edges) - 1
    print(f"[assemble] {args.job}: {n} spans, {n - 1} transitions, total {total_dur:.1f}s", flush=True)

    def done(p):
        return os.path.isfile(p) and os.path.getsize(p) > 0

    span_paths = []
    for i in range(n):
        t0, t1 = edges[i], edges[i + 1]
        trim_head = 0.0 if i == 0 else HALF
        trim_tail = 0.0 if i == n - 1 else HALF
        span_out = os.path.join(work, f"span{i:03d}.mp4")
        if not done(span_out):
            s0, s1 = t0 + trim_head, t1 - trim_tail
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", zoomed, "-ss", str(s0), "-t", str(s1 - s0), "-an",
                 "-vf", f"scale={W}:{H}", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                 "-pix_fmt", "yuv420p", span_out])
        span_paths.append(span_out)
        print(f"  span{i:03d} [{t0:.2f}-{t1:.2f}] {windows[i].get('type', '?')}", flush=True)

    for i in range(n - 1):
        trans_out = os.path.join(work, f"trans{i:03d}.mp4")
        if not done(trans_out):
            # The transition bridges the END of span i and the START of span i+1: sample the
            # outgoing side from the tail of span i, the incoming side from the head of span i+1.
            tail_probe = os.path.join(work, f"span{i:03d}.tail.mp4")
            if not done(tail_probe):
                sd = ffprobe_dur(span_paths[i])
                run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                     "-ss", str(max(0.0, sd - DURATION)), "-i", span_paths[i], "-an",
                     "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", tail_probe])
            build_transition_clip(tail_probe, span_paths[i + 1], W, H, trans_out)
        print(f"  trans{i:03d} @ {boundaries[i]:.2f}s", flush=True)

    concat_entries = []
    for i in range(n):
        concat_entries.append(span_paths[i])
        if i < n - 1:
            concat_entries.append(os.path.join(work, f"trans{i:03d}.mp4"))
    concat_list = os.path.join(work, "concat.txt")
    with open(concat_list, "w") as f:
        for p in concat_entries:
            f.write(f"file '{os.path.abspath(p)}'\n")

    video_only = os.path.join(job_dir, "outputs", f"{args.job}.transitioned.video.mp4")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", concat_list,
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", video_only])
    video_dur = ffprobe_dur(video_only)
    print(f"[assemble] video-only concat: {video_only} ({video_dur:.3f}s vs base {total_dur:.3f}s)", flush=True)

    # Audio: the untouched continuous voice track from the zoomed base (zoom is video-only), padded
    # to the video's REAL length (transitions shave fractional seconds), plus the whoosh at each
    # boundary. Voice + SFX only — music comes later, on top of this file.
    audio_mixed = os.path.join(work, "audio_mixed.wav")
    filter_parts = [f"[0:a]apad,atrim=0:{video_dur:.3f}[base]"]
    inputs = ["-i", zoomed]
    mix_labels = ["[base]"]
    for i, b in enumerate(boundaries):
        inputs += ["-i", DEFAULT_SFX]
        delay_ms = int(round(b * 1000))
        filter_parts.append(f"[{i + 1}:a]adelay={delay_ms}|{delay_ms}[sfx{i}]")
        mix_labels.append(f"[sfx{i}]")
    filter_parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0[outa]")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         *inputs, "-filter_complex", ";".join(filter_parts), "-map", "[outa]",
         "-c:a", "pcm_s16le", audio_mixed])

    out_path = os.path.join(job_dir, "outputs", f"{args.job}.composited.mp4")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", video_only, "-i", audio_mixed,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
         "-shortest", "-movflags", "+faststart", out_path])
    out_dur = ffprobe_dur(out_path)
    print(f"[assemble] DONE -> {out_path} ({out_dur:.2f}s)", flush=True)


if __name__ == "__main__":
    main()
