#!/usr/bin/env python3
"""
assemble_final.py — final assembly for marathon-reaction-article with whoosh transitions
at EVERY paragraph change and EVERY camera-cut, per the the reference channel-reference feedback round.

Why not just call build_transition.py 51 times on the growing output? That script fully
re-encodes everything from 0 to the cut point on every call (fine for a one-off transition,
disastrous for ~51 of them on a 12-minute video - the cost compounds every call). Instead:
build each of the 52 segments (7 zoom windows + 45 paragraphs) as its own trimmed clip,
generate each of the 51 junctions as its own standalone 0.4s transition clip (reusing the
SAME locked streak/flash primitives build_transition.py uses, imported not copied), then
one single concat + one single audio mix. O(N) work done once, not O(N^2).

Small natural speech pauses between sentences (up to a couple seconds) are closed by
extending each segment's `end` to the next segment's `start` - the reading-mode composite
just holds the current paragraph/card a little longer through the pause rather than
flashing back to plain footage for a beat.

Usage: assemble_final.py
"""
import glob, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(REPO, "presets", "sweep-intro"))
from build import (
    FPS, DURATION, N_FRAMES, PEAK_T, HOLD_END,
    make_streaks, coverage_at, composite_frame, scale_frame,
    DEFAULT_SFX, SFX_ATTACK_T,
)
from PIL import Image

HALF = DURATION / 2  # 0.2s

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JOB = f"{REPO}/projects/marathon-reaction-article"
ZOOMED_BASE = f"{JOB}/outputs/marathon-reaction-article.zoomed.mp4"
PARA_DIR = f"{JOB}/paragraphs"
WORK = f"{JOB}/assemble_work"


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


def extract_frame(video, t, out_path):
    # Accurate (post-input) seek, not fast/keyframe seek - a real bug earlier in this same
    # project (b-roll trimming) came from exactly this mistake landing on the wrong frame.
    # Retries progressively earlier if the requested t lands past the last real frame
    # (floating-point-close-to-EOF genuinely produces zero output frames from ffmpeg with
    # exit code 0 - no error, just a file that never gets written) - and does NOT raise on
    # a nonzero exit either, since that's also a legitimate case to just retry earlier
    # (e.g. asking past a corrupt/truncated source's real content).
    last_err = None
    for backoff in (0.0, 0.1, 0.3, 0.6, 1.0):
        tt = max(0.0, t - backoff)
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                             "-i", video, "-ss", str(tt), "-frames:v", "1", out_path],
                            capture_output=True, text=True)
        if r.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            return
        last_err = r.stderr
    raise SystemExit(f"extract_frame: never got a frame from {video} near t={t}\n{last_err}")


def extract_frame_sequence(video, t_start, n, tmp_dir, prefix):
    """Extract up to n real consecutive frames starting at t_start (accurate seek). Used
    instead of a single still so the transition shows genuine motion underneath the streak
    effect - a real bug (user-reported "screen freezes when the transition happens"): the
    original version held ONE still image for up to 21 of 24 transition frames (0.35s),
    which reads as a freeze no matter how much streak/blur is drawn on top of it."""
    pattern = os.path.join(tmp_dir, f"{prefix}%03d.png")
    frames = []
    for attempt in range(3):
        for p in glob.glob(os.path.join(tmp_dir, f"{prefix}*.png")):
            os.remove(p)
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                             "-i", video, "-ss", str(max(0.0, t_start)), "-frames:v", str(n),
                             "-start_number", "0",  # image2 muxer defaults to starting at 1, not
                             # 0 - the real bug here: 24 real frames were written every time as
                             # b001..b024, but the read-back loop below starts at b000 and never
                             # existed, so it always saw "zero frames" despite ffmpeg succeeding
                             pattern], capture_output=True, text=True)
        frames = []
        i = 0
        while True:
            p = os.path.join(tmp_dir, f"{prefix}{i:03d}.png")
            if not os.path.isfile(p):
                break
            frames.append(Image.open(p).convert("RGB"))
            i += 1
        if frames:
            return frames
        print(f"[extract_frame_sequence] attempt {attempt+1} got 0 frames from {video} @ {t_start} "
              f"(rc={r.returncode}); retrying", file=sys.stderr)
    raise SystemExit(f"extract_frame_sequence: never got a frame from {video} @ {t_start}")


def build_transition_clip(before_clip, after_clip, before_t0, after_t0, w, h, out_path):
    """before_clip/after_clip: the already-rendered segment files on either side of the cut.
    before_t0: where in before_clip's OWN timeline the transition's real content starts
    (i.e. DURATION seconds before that segment's trimmed end). after_t0: where in
    after_clip's own timeline the transition's real content starts (its trimmed start)."""
    streaks = make_streaks()
    with tempfile.TemporaryDirectory() as tmp:
        before_frames = extract_frame_sequence(before_clip, before_t0, N_FRAMES, tmp, "b")
        after_frames = extract_frame_sequence(after_clip, after_t0, N_FRAMES, tmp, "a")

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
            frame = composite_frame(primary, primary, streaks, w, h, coverage)
            frame.save(os.path.join(tmp, f"f{i:03d}.png"))
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-framerate", str(FPS), "-i", os.path.join(tmp, "f%03d.png"),
             "-t", str(DURATION), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", out_path])


def extract_segment(seg, t0, t1, out_path, w, h):
    """Extract [t0,t1) (local time within the segment's own source), padding with a
    frozen last frame if the source is shorter than requested (paragraphs whose native
    render was shorter than their gap-closed allotted window)."""
    dur = t1 - t0
    if seg["type"] in ("zoom", "wide"):
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", ZOOMED_BASE, "-ss", str(seg["start"] + t0), "-t", str(dur), "-an",
               "-vf", f"tpad=stop_mode=clone:stop_duration={dur}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", out_path]
    else:
        src = f"{PARA_DIR}/para{seg['idx']:02d}.mp4"
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", src, "-ss", str(t0), "-t", str(dur), "-an",
               "-vf", f"scale={w}:{h},tpad=stop_mode=clone:stop_duration={dur}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", out_path]
    run(cmd)


def main():
    os.makedirs(WORK, exist_ok=True)
    zoom_plan = json.load(open(f"{JOB}/zoom-plan.json"))
    para_plan = json.load(open(f"{JOB}/paragraph-plan.json"))

    segments = []
    for w_ in zoom_plan["windows"]:
        segments.append({"type": "zoom", "start": w_["start"], "end": w_["end"]})
    for i, p in enumerate(para_plan["paragraphs"], 1):
        segments.append({"type": "para", "idx": i, "start": p["start"], "end": p["end"]})
    # One-off explicit "wide" segments where a moment that would otherwise be (or was) a
    # zoom-plan.json punch-in needs to stay at native framing. Extracted the same way as a
    # "zoom" segment (straight from ZOOMED_BASE, genuinely un-cropped at these spans since
    # both now sit outside every real zoom-plan.json window), but tagged "wide" (not "zoom")
    # so the type-mismatch junction check below still fires a whoosh at each cut in/out.
    #   - 614.75-625.0 (2026-08-30): the creator finishes reading the article's last line on
    #     camera before punching in 10s later for the actual reaction.
    #   - 569.63-576.9 (2026-08-30 follow-up): reaction to the leaked weapon skin - was a
    #     zoom-plan.json punch-in window, but punching in here crops the skin itself out of
    #     frame. Reverted to wide so the b-roll showing it off stays fully visible.
    for w_start, w_end in ((569.63, 576.9), (614.75, 625.0)):
        segments.append({"type": "wide", "start": w_start, "end": w_end})
    segments.sort(key=lambda s: s["start"])

    total_dur = ffprobe_dur(ZOOMED_BASE)
    # Close natural-pause gaps by extending PARAGRAPH boundaries only - zoom-window
    # start/end values are hand-tuned per exact user feedback and must stay authoritative,
    # never silently overwritten (the old blind "extend to next segment's start" rule was
    # exactly why retiming requests didn't take effect: it always pushed every camera-cut
    # out to match whichever paragraph came next, regardless of what zoom-plan.json said).
    for i in range(len(segments) - 1):
        a, b = segments[i], segments[i + 1]
        gap = b["start"] - a["end"]
        if gap <= 0.05:
            continue
        if a["type"] == "para":
            a["end"] = b["start"]           # paragraph absorbs the pause going forward
        elif b["type"] == "para":
            b["start"] = a["end"]           # paragraph absorbs the pause coming backward
        else:
            a["end"] = b["start"]           # (zoom-to-zoom shouldn't happen, but stay safe)
    segments[-1]["end"] = total_dur

    W, H = 2560, 1440
    n = len(segments)
    print(f"[assemble] {n} segments, {n - 1} transitions, total {total_dur:.1f}s", flush=True)

    def done(p):
        return os.path.isfile(p) and os.path.getsize(p) > 0

    seg_durations = []  # own trimmed length of each segment's rendered file
    for i, seg in enumerate(segments):
        local_end = seg["end"] - seg["start"]
        trim_head = HALF if i > 0 else 0.0
        trim_tail = HALF if i < n - 1 else 0.0
        seg_durations.append(local_end - trim_tail - trim_head)

        seg_out = f"{WORK}/seg{i:03d}.mp4"
        if not done(seg_out):
            extract_segment(seg, trim_head, local_end - trim_tail, seg_out, W, H)
        print(f"  seg{i:03d} [{seg['start']:.2f}-{seg['end']:.2f}] {seg['type']}{seg.get('idx','')}", flush=True)

    # Pass 2: transitions, now that every segment's own trimmed file exists - each pulls real
    # motion frames from the tail of the segment before it and the head of the one after it
    # (not a single still), fixing the reported "screen freezes" bug.
    for i in range(n - 1):
        trans_out = f"{WORK}/trans{i:03d}.mp4"
        if not done(trans_out):
            before_clip = f"{WORK}/seg{i:03d}.mp4"
            after_clip = f"{WORK}/seg{i+1:03d}.mp4"
            before_t0 = max(0.0, seg_durations[i] - DURATION)
            build_transition_clip(before_clip, after_clip, before_t0, 0.0, W, H, trans_out)
        print(f"  trans{i:03d} @ {segments[i]['end']:.2f}s", flush=True)

    concat_entries = []
    for i in range(n):
        concat_entries.append(f"{WORK}/seg{i:03d}.mp4")
        if i < n - 1:
            concat_entries.append(f"{WORK}/trans{i:03d}.mp4")

    concat_list = f"{WORK}/concat.txt"
    with open(concat_list, "w") as f:
        for c in concat_entries:
            f.write(f"file '{os.path.abspath(c)}'\n")

    video_only = f"{JOB}/outputs/marathon-reaction-article.transitioned.video.mp4"
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", video_only])
    print(f"[assemble] video-only concat done: {video_only}", flush=True)

    # BUGFIX (found 2026-08-30): the 53 transitions trim HALF (0.2s) off each side of a cut
    # to make room for their own 0.4s, which should net to zero extra runtime, but small
    # per-boundary rounding accumulates - the real concat came out ~0.35s LONGER than
    # ZOOMED_BASE's nominal duration. The audio mix below is built from ZOOMED_BASE's own
    # (shorter) length, so without accounting for this the final mux would silently carry a
    # video track longer than its audio track - and downstream, mix-music.sh's `amix` (keyed
    # to the audio's length) + `-shortest` would then truncate the delivered file to the
    # SHORTER audio length, quietly dropping the last ~0.35s of picture. Pad the audio to
    # match the real video length here instead, so nothing downstream ever has to guess.
    video_dur = ffprobe_dur(video_only)
    print(f"[assemble] video_only real duration: {video_dur:.3f}s (vs ZOOMED_BASE nominal "
          f"{total_dur:.3f}s) - padding audio to match", flush=True)

    # Audio: original continuous track, two different whoosh sounds layered in depending on
    # junction type. Camera-return junctions (zoom<->reading crossings - the "comes back to
    # me to talk to the audience" moments) keep the ORIGINAL sweep-intro whoosh, unchanged,
    # per explicit instruction. Paragraph-to-paragraph junctions now ALSO get a sound - the
    # user's own provided whoosh sfx - one per paragraph change (all 45 of them).
    #
    # IMPORTANT finding (kept from the last debugging round): the raw base audio is already
    # flat (measured -21.2 to -21.6dB across the whole video) thanks to rough-cut's own
    # static gain/limiter chain. amix's default normalize=1 divides by input count and caused
    # real drift when mixing in sparse sfx - normalize=0 keeps the base track's level
    # completely untouched by the mix, sfx just add on top.
    PARAGRAPH_SFX = os.path.join(REPO, "assets", "sfx", "synth", "whoosh.wav")   # synthesized by presets/shorts/make-sfx.py
    audio_out = f"{WORK}/audio_mixed.m4a"
    camera_junctions = [i for i in range(len(segments) - 1) if segments[i]["type"] != segments[i + 1]["type"]]
    paragraph_junctions = [i for i in range(len(segments) - 1)
                            if segments[i]["type"] == "para" and segments[i + 1]["type"] == "para"]
    filt_chain = "[0:a]anull[abase]"
    sfx_inputs = []
    if (camera_junctions or paragraph_junctions):
        mix_labels = ["abase"]
        parts = ["[0:a]anull[abase]"]
        for idx in camera_junctions:
            if not os.path.isfile(DEFAULT_SFX):
                continue
            sfx_start = max(0.0, segments[idx]["end"] - SFX_ATTACK_T)
            parts.append(f"[{len(sfx_inputs)+1}:a]adelay={int(sfx_start*1000)}|{int(sfx_start*1000)}[sfx{idx}]")
            mix_labels.append(f"sfx{idx}")
            sfx_inputs.append(DEFAULT_SFX)
        for idx in paragraph_junctions:
            if not os.path.isfile(PARAGRAPH_SFX):
                continue
            sfx_start = max(0.0, segments[idx]["end"] - SFX_ATTACK_T)
            parts.append(f"[{len(sfx_inputs)+1}:a]adelay={int(sfx_start*1000)}|{int(sfx_start*1000)}[sfx{idx}]")
            mix_labels.append(f"sfx{idx}")
            sfx_inputs.append(PARAGRAPH_SFX)
        parts.append(f"{''.join(f'[{l}]' for l in mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0,apad,atrim=0:{video_dur}[aout]")
        filt_chain = ";".join(parts)

        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", ZOOMED_BASE]
        for s in sfx_inputs:
            cmd += ["-i", s]
        cmd += ["-filter_complex", filt_chain, "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", audio_out]
        run(cmd)
    else:
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", ZOOMED_BASE, "-vn", "-af", f"apad,atrim=0:{video_dur}",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", audio_out])
    print(f"[assemble] audio mix done: {audio_out}", flush=True)

    final_out = f"{JOB}/outputs/marathon-reaction-article.composited.mp4"
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", video_only, "-i", audio_out,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
         "-shortest",  # safety net now that both tracks are padded/trimmed to match video_dur
         "-movflags", "+faststart", final_out])
    out_dur = ffprobe_dur(final_out)
    print(f"[assemble] DONE -> {final_out} ({out_dur:.2f}s, expected ~{total_dur:.2f}s)", flush=True)


if __name__ == "__main__":
    main()
