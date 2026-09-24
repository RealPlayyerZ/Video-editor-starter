#!/usr/bin/env python3
"""
build_paragraph.py — composite ONE reading-mode paragraph segment.

Supersedes build_beat.py's per-segment recipe after the the reference channel-reference feedback round:
NO facecam inset anymore (the creator only appears during actual direct-address/punch-in
windows now, not throughout reading) - just blurred b-roll + particles + the FULL paragraph
text as its own card.

Layers (bottom to top):
  1. Blurred b-roll background (full frame, boxblur)
  2. Particle loop, colorkey+overlay (NEVER `blend`)
  3. Full-paragraph article-card text (generate_card.py)

Output is VIDEO-ONLY (no audio) - the base cut's own continuous audio plays underneath in the
final assembly.

Usage:
  build_paragraph.py --broll <path> --broll-in <sec> --duration <sec> \
                      --card-text "<text>" --out <out.mp4>
"""
import argparse, os, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARTICLES = f"{REPO}/presets/reading-mode/assets/particles-loop.mp4"
GEN_CARD = f"{REPO}/presets/reading-mode/generate_card.py"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broll", required=True)
    ap.add_argument("--broll-in", type=float, required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--card-text", required=True)
    ap.add_argument("--label", default="ARTICLE EXCERPT")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        card_png = os.path.join(tmp, "card.png")
        run(["python3", GEN_CARD, args.card_text, card_png, "--label", args.label])

        # Slow dynamic zoom-in on the background AND the card (feedback: in the the reference channel
        # reference, the text box itself slowly gets bigger as the shot pushes in, in sync
        # with the background - not a fixed-size box over a zooming plate).
        #
        # GOTCHA: scale+crop (the first attempt) does NOT work for this - ffmpeg's `crop`
        # filter evaluates its x/y expressions ONCE at init, not per frame, even when they
        # reference "dynamic" variables like in_w. There is no eval=frame option for crop
        # (confirmed: ffmpeg errors "Option not found" if you try). The visible symptom was
        # exactly what got reported: the crop's x offset stayed frozen at its near-zero
        # starting value while the underlying scaled frame kept growing, so the box's LEFT
        # edge stayed put while it grew rightward - a drift toward the right, not a centered
        # zoom. `zoompan` is the correct tool here - built specifically for animated
        # zoom/pan and genuinely re-evaluates its z/x/y expressions per output frame.
        FPS = 60
        n_frames = max(1, round(args.duration * FPS))
        zoom_end = 1.25  # feedback: the push-in read as too subtle - bigger, more noticeable zoom
        # Anti-shake pass (feedback: the text box shakes while zooming, hard to read - and later
        # feedback, 2026-08-31: the gameplay background ALSO reads as shaky/glitchy during the
        # zoom, not just the text). zoompan recomputes and rounds its crop rect to whole pixels
        # every single frame; at native 2560x1440 that rounding jitter was assumed invisible
        # under the bg's own boxblur, but real high-motion/high-detail gameplay footage (vs.
        # marathon's slower stock trailer clips) showed it does NOT fully mask it. Fix applies to
        # BOTH layers now: supersample 2x before zoompan (halves each frame's pixel-rounding
        # error in final-delivery terms), zoom on that bigger canvas, downscale back to
        # 2560x1440 with lanczos, which blends away whatever sub-pixel jitter remains.
        SS = 2

        def supersampled_zoompan():
            return (
                f"scale={2560*SS}:{1440*SS}:flags=lanczos,"
                f"zoompan=z='1+{zoom_end - 1}*in/{n_frames}':d=1:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={2560*SS}x{1440*SS}:fps={FPS},"
                f"scale=2560:1440:flags=lanczos"
            )

        bg_zoompan = supersampled_zoompan()
        card_zoompan = supersampled_zoompan()
        filter_complex = (
            # tpad safety net: if broll_in+duration slightly overruns the source clip's own
            # length (a real bug hit once - a beat's clip assignment overflowed by 18s and
            # produced a near-empty broken output with no error), hold the last real frame
            # instead of the overlay chain just stopping early or, worse, having nothing to
            # composite at all. Does nothing when the source has enough real content.
            f"[0:v]tpad=stop_mode=clone:stop_duration={args.duration},"
            f"{bg_zoompan},boxblur=8:3,setsar=1[bg];"
            f"[1:v]colorkey=0x000000:0.15:0.1,format=yuva420p[particles];"
            f"[bg][particles]overlay=format=auto[bgp];"
            f"[2:v]{card_zoompan}[card];"
            f"[bgp][card]overlay=0:0[out]"
        )

        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(args.broll_in), "-t", str(args.duration), "-i", args.broll,
            "-stream_loop", "-1", "-t", str(args.duration), "-i", PARTICLES,
            "-loop", "1", "-r", "60", "-t", str(args.duration), "-i", card_png,  # force 60fps
            # decode - the image2 demuxer otherwise defaults to 25fps, which under zoompan's
            # d=1 (1 input frame -> 1 output frame) produced way fewer frames than the
            # duration needed at our 60fps output, cutting paragraphs short
            "-filter_complex", filter_complex,
            "-map", "[out]", "-an", "-t", str(args.duration),  # hard cap - the tpad safety
            # net above can otherwise overshoot the intended length when there's no shortfall
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            args.out,
        ]
        run(cmd)
        print(f"[build_paragraph] wrote {args.out}")


if __name__ == "__main__":
    main()
