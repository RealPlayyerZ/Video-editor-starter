#!/usr/bin/env python3
"""
chat_cards.py — Twitch-style chat message cards for a cold open (division2-legendary-mission, 2026-09-13).

The creator sends his chat's messages as tiny screenshots (~230 px wide); blown up to a 1440p frame
they turn to mush, so the cards are RE-DRAWN at full size: dark rounded box, the username in its
Twitch colour, the message in white, optional badge squares. One PNG per message + a plan JSON the
gags renderer overlays (pop in one by one, each with the creator's popping sound).

Usage:
  chat_cards.py <out-dir> --canvas 2560x1440 --messages messages.json [--font-px 72] [--x 110] [--y 380]
                [--start 1.2] [--step 1.4] [--until 18.0]
messages.json: [{"name": "silent3killer99", "color": "#00FF7F", "text": "Real you will be one shot ...",
                 "badges": ["sub", "verified"]}, ...]
Writes <out-dir>/card01.png … and <out-dir>/cards.json = {"overlays": [[png, x, y, t0, t1], ...], "pops": [t0, ...]}
"""
import argparse, json, os
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FONT_B = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")
FONT_R = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")
BADGE = {"sub": ((145, 70, 255), "★"), "verified": ((0, 200, 120), "✓"), "mod": ((0, 173, 3), "⚔"), "vip": ((224, 5, 185), "◆")}


def card(msg, px, max_w):
    fb, fr = ImageFont.truetype(FONT_B, px), ImageFont.truetype(FONT_R, px)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    pad, lh, gap = int(px * 0.55), int(px * 1.32), int(px * 0.28)
    badge_w = (px + gap) * len(msg.get("badges", []))
    name = msg["name"] + ":"
    name_w = probe.textlength(name, font=fb)
    # wrap the message after the name on the first line
    words, lines, cur, first_w = msg["text"].split(), [], "", badge_w + name_w + gap
    for w in words:
        t = (cur + " " + w).strip()
        avail = max_w - 2 * pad - (first_w if not lines else 0)
        if probe.textlength(t, font=fr) > avail and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    lines.append(cur)
    width = int(min(max_w, max(first_w + probe.textlength(lines[0], font=fr), *(probe.textlength(l, font=fr) for l in lines[1:] or [""])) + 2 * pad))
    height = lh * len(lines) + 2 * pad - int(px * 0.2)
    img = Image.new("RGBA", (width + 16, height + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 12, width + 6, height + 12), radius=int(px * 0.35), fill=(0, 0, 0, 110))        # drop shadow
    d.rounded_rectangle((4, 4, width + 4, height + 4), radius=int(px * 0.35), fill=(24, 24, 27, 236), outline=(60, 60, 66, 255), width=3)
    x, y = 4 + pad, 4 + pad - int(px * 0.1)
    for b in msg.get("badges", []):
        col, glyph = BADGE.get(b, ((120, 120, 120), "•"))
        d.rounded_rectangle((x, y + int(px * 0.12), x + px * 0.92, y + int(px * 0.12) + px * 0.92), radius=int(px * 0.16), fill=col)
        gf = ImageFont.truetype(FONT_B, int(px * 0.6))
        gw = probe.textlength(glyph, font=gf)
        d.text((x + px * 0.46 - gw / 2, y + int(px * 0.2)), glyph, font=gf, fill=(255, 255, 255, 255))
        x += px + gap
    col = tuple(int(msg["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    d.text((x, y), name, font=fb, fill=col + (255,))
    x += name_w + gap
    for i, ln in enumerate(lines):
        d.text((x if i == 0 else 4 + pad, y + i * lh), ln, font=fr, fill=(255, 255, 255, 255))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--canvas", default="2560x1440"); ap.add_argument("--messages", required=True)
    ap.add_argument("--font-px", type=int, default=72); ap.add_argument("--x", type=int, default=110); ap.add_argument("--y", type=int, default=380)
    ap.add_argument("--start", type=float, default=1.2); ap.add_argument("--step", type=float, default=1.4); ap.add_argument("--until", type=float, default=18.0)
    a = ap.parse_args()
    W, H = (int(v) for v in a.canvas.split("x"))
    os.makedirs(a.out, exist_ok=True)
    msgs = json.load(open(a.messages))
    overlays, pops, y = [], [], a.y
    for i, m in enumerate(msgs, 1):
        img = card(m, a.font_px, int(W * 0.62))
        p = os.path.join(a.out, f"card{i:02d}.png"); img.save(p)
        t0 = round(a.start + (i - 1) * a.step, 3)
        overlays.append([p, a.x, y, t0, a.until]); pops.append(t0)
        y += img.height - 2
    json.dump({"overlays": overlays, "pops": pops}, open(os.path.join(a.out, "cards.json"), "w"), indent=1)
    print(f"{len(msgs)} cards → {a.out} (stack ends at y={y}, canvas {W}x{H})")


if __name__ == "__main__":
    main()
