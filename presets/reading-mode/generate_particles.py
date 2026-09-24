#!/usr/bin/env python3
"""
generate_particles.py — the validated reading-mode particle overlay.

~380 multi-directional particles at 70-190px/sec on a pure-black canvas, meant to be
composited over a blurred background via colorkey+overlay (NEVER ffmpeg's `blend` filter
- it mis-handles colorspace and pushes the whole frame magenta even when both layers are
clean, a real bug hit building this recipe).

Renders a LOOPABLE frame sequence (particles wrap around screen edges) so one render can
back any beat duration via `-stream_loop -1 -t <duration>` at composite time.

Usage:
  generate_particles.py <out_dir> [--seconds 60] [--fps 30] [--w 2560] [--h 1440] [--count 380]
"""
import argparse, math, os, random
from PIL import Image, ImageDraw

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=2560)
    ap.add_argument("--h", type=int, default=1440)
    ap.add_argument("--count", type=int, default=380)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    random.seed(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    n_frames = int(args.seconds * args.fps)
    particles = []
    for _ in range(args.count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(70, 190)  # px/sec, locked range
        particles.append({
            "x": random.uniform(0, args.w),
            "y": random.uniform(0, args.h),
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed,
            "r": random.uniform(1.2, 3.2),
            "a": random.randint(120, 220),
        })

    dt = 1.0 / args.fps
    for f in range(n_frames):
        img = Image.new("RGB", (args.w, args.h), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        for p in particles:
            x = (p["x"] + p["vx"] * dt * f) % args.w
            y = (p["y"] + p["vy"] * dt * f) % args.h
            r = p["r"]
            shade = p["a"]
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(shade, shade, shade))
        img.save(os.path.join(args.out_dir, f"f{f:05d}.png"))

    print(f"wrote {n_frames} frames to {args.out_dir}")

if __name__ == "__main__":
    main()
