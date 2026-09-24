#!/usr/bin/env python3
"""
build_beat.py — composite ONE reading-mode beat segment.

Layers (bottom to top):
  1. Blurred b-roll background (full frame, boxblur)
  2. Particle loop, colorkey+overlay (NEVER `blend` - see generate_particles.py)
  3. Facecam inset - cropped from the ORIGINAL (un-zoomed) reaction footage at this
     beat's own timerange, using the same crop region zoom-crop.json measured for the
     punch-in (so the framing is consistent everywhere the face appears), scaled down,
     corner-positioned.
  4. Article-card text (generate_card.py)

Output is VIDEO-ONLY (no audio) - the base cut's own continuous audio plays underneath
in the final assembly; this segment only replaces the picture.

Usage:
  build_beat.py --broll <path> --broll-in <sec> --duration <sec> \
                 --facecam-source <path> --facecam-start <sec> \
                 --crop <w:h:x:y> --card-text "<text>" --out <out.mp4>
"""
import argparse, os, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARTICLES = f"{REPO}/presets/reading-mode/assets/particles-loop.mp4"
GEN_CARD = f"{REPO}/presets/reading-mode/generate_card.py"

INSET_W, INSET_H = 620, 349
INSET_MARGIN = 40


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
    ap.add_argument("--facecam-source", required=True)
    ap.add_argument("--facecam-start", type=float, required=True)
    ap.add_argument("--crop", default="1064:600:1496:353")
    ap.add_argument("--card-text", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cw, ch, cx, cy = args.crop.split(":")

    with tempfile.TemporaryDirectory() as tmp:
        card_png = os.path.join(tmp, "card.png")
        run(["python3", GEN_CARD, args.card_text, card_png])

        filter_complex = (
            f"[0:v]scale=2560:1440,boxblur=8:3,setsar=1[bg];"
            f"[1:v]colorkey=0x000000:0.15:0.1,format=yuva420p[particles];"
            f"[bg][particles]overlay=format=auto[bgp];"
            f"[2:v]crop={cw}:{ch}:{cx}:{cy},scale={INSET_W}:{INSET_H}[face];"
            f"[bgp][face]overlay=x=2560-{INSET_W}-{INSET_MARGIN}:y={INSET_MARGIN}[withface];"
            f"[withface][3:v]overlay=0:0[out]"
        )

        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(args.broll_in), "-t", str(args.duration), "-i", args.broll,
            "-stream_loop", "-1", "-t", str(args.duration), "-i", PARTICLES,
            "-ss", str(args.facecam_start), "-t", str(args.duration), "-i", args.facecam_source,
            "-loop", "1", "-t", str(args.duration), "-i", card_png,
            "-filter_complex", filter_complex,
            "-map", "[out]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            args.out,
        ]
        run(cmd)
        print(f"[build_beat] wrote {args.out}")


if __name__ == "__main__":
    main()
