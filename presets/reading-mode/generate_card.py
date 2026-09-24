#!/usr/bin/env python3
import os
"""
generate_card.py — article-card text overlay for the reading-mode composite.

PIL PNG (this project's ffmpeg has no freetype/libass, so PIL is the house pattern for any
burned-in text - see presets/tiktok-raw/build.py for the precedent). Dark semi-opaque box,
white Inter Bold text, wrapped to a max width and sized to the wrapped text's own extent
(not a fixed box) - same "size to ink, not font metrics" principle as the locked hook-card.

Renders the FULL paragraph text (not a short paraphrase) per the the reference channel reference
(2026-08-26 clip) - a real multi-sentence article paragraph held on screen while it's read.
No facecam to avoid anymore (that inset was removed per the same feedback round), so this is
centered rather than shoved left.

Usage:
  generate_card.py "<text>" <out.png> [--w 2560] [--h 1440] [--fontsize 46]
"""
import argparse
import textwrap
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_PATH = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")
LABEL_FONT_PATH = os.path.join(REPO, "assets", "fonts", "Inter-Black.otf")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out_png")
    ap.add_argument("--w", type=int, default=2560)
    ap.add_argument("--h", type=int, default=1440)
    ap.add_argument("--fontsize", type=int, default=46)
    ap.add_argument("--max_chars_per_line", type=int, default=52)
    ap.add_argument("--label", default="ARTICLE EXCERPT")
    args = ap.parse_args()

    font = ImageFont.truetype(FONT_PATH, args.fontsize)
    label_font = ImageFont.truetype(LABEL_FONT_PATH, int(args.fontsize * 0.42))

    lines = textwrap.wrap(args.text, width=args.max_chars_per_line)

    canvas = Image.new("RGBA", (args.w, args.h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    label_bbox = draw.textbbox((0, 0), args.label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]

    line_gap = int(args.fontsize * 0.28)
    pad_x, pad_y = 44, 36
    label_gap = 20

    text_block_w = max(line_widths) if line_widths else 0
    text_block_h = sum(line_heights) + line_gap * (len(lines) - 1) if lines else 0

    box_w = max(text_block_w, label_w) + pad_x * 2
    box_h = label_h + label_gap + text_block_h + pad_y * 2

    # Position: dead-centered, both axes (feedback: put it in the middle of the screen).
    box_x = (args.w - box_w) // 2
    box_y = (args.h - box_h) // 2

    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=18,
        fill=(10, 10, 12, 225),
        outline=(255, 209, 0, 255),
        width=3,
    )

    ly = box_y + pad_y
    draw.text((box_x + pad_x, ly), args.label, font=label_font, fill=(255, 209, 0, 255))
    ly += label_h + label_gap

    for line, lh in zip(lines, line_heights):
        draw.text((box_x + pad_x, ly), line, font=font, fill=(255, 255, 255, 255))
        ly += lh + line_gap

    canvas.save(args.out_png)
    print(f"wrote {args.out_png} ({box_w}x{box_h} box @ {box_x},{box_y})")

if __name__ == "__main__":
    main()
