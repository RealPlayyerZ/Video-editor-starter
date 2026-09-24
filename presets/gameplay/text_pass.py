#!/usr/bin/env python3
"""
text_pass.py — on-screen comedy text for gameplay long-form (experiment, 2026-09-18; reference: SovietWomble-style
punchline subtitles). NOT captions: a handful of authored events, bottom-middle, over the finished comedy layer.

  style "punch": the spoken punchline, ALL CAPS, white with a thick black stroke (the thumbnail-banner look), pops up
                 from below in 0.1 s, optional shake for yelled lines, quick alpha fade-out.
  style "aside": the editor's dry comment, smaller, yellow, sentence case.

Usage: text_pass.py <in.mp4> <out.mp4> --events events.json [--y 1215]
events.json = [{"text": "...", "t0": 25.6, "t1": 27.4, "style": "punch"|"aside", "shake": false}, ...]  (times = input video)
PIL PNG overlays + ffmpeg overlay (this ffmpeg has no freetype); looped PNG inputs are bounded with -t (lab note).
"""
import argparse, json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FONT_PUNCH = os.path.join(REPO, "assets", "fonts", "Inter-Black.otf"); FONT_ASIDE = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")


def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", path],
                                  capture_output=True, text=True, check=True).stdout)
    return int(j["streams"][0]["width"]), int(j["streams"][0]["height"]), float(j["format"]["duration"])


def render(text, style, W, path):
    k = W / 2560
    if style == "punch":
        text, font, fill, stroke = text.upper(), ImageFont.truetype(FONT_PUNCH, int(112 * k)), (255, 255, 255, 255), int(10 * k)
    else:
        font, fill, stroke = ImageFont.truetype(FONT_ASIDE, int(62 * k)), (255, 216, 74, 255), int(6 * k)
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = [text]
    if d.textlength(text, font=font) > 1750 * k and " " in text:          # wrap onto two centred lines at the middle space
        ws = text.split(" "); best = min(range(1, len(ws)), key=lambda i: abs(len(" ".join(ws[:i])) - len(" ".join(ws[i:]))))
        lines = [" ".join(ws[:best]), " ".join(ws[best:])]
    asc, desc = font.getmetrics(); lh = asc + desc + int(6 * k)
    w = int(max(d.textlength(l, font=font) for l in lines)) + 2 * stroke + int(24 * k); h = lh * len(lines) + 2 * stroke + int(12 * k)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        x = (w - dr.textlength(l, font=font)) / 2
        dr.text((x, stroke + int(6 * k) + i * lh), l, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    img.save(path); return w, h


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--events", required=True); ap.add_argument("--y", type=int, default=1215)
    a = ap.parse_args(); W, H, dur = probe(a.inp); ev = json.load(open(a.events)); work = os.path.dirname(os.path.abspath(a.out))
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-reinit_filter", "0", "-i", a.inp]; fc = []; last = "0:v"
    for k, e in enumerate(ev, 1):
        png = os.path.join(work, f"text{k:02d}.png"); w, h = render(e["text"], e.get("style", "punch"), W, png)
        t0, t1 = float(e["t0"]), float(e["t1"]); yc = int(a.y * H / 1440) - h // 2
        cmd += ["-loop", "1", "-framerate", "60", "-t", f"{t1 + 0.3:.3f}", "-i", png]
        fc.append(f"[{k}:v]format=rgba,fade=t=in:st={t0:.3f}:d=0.06:alpha=1,fade=t=out:st={t1 - 0.18:.3f}:d=0.18:alpha=1[tx{k}]")
        x = "(W-w)/2" + (rf"+{int(14 * W / 2560)}*sin(2*PI*17*(t-{t0:.3f}))*max(0\,1-(t-{t0:.3f})/0.55)" if e.get("shake") else "")
        y = rf"{yc}+{int(40 * H / 1440)}*max(0\,1-(t-{t0:.3f})/0.10)"
        fc.append(rf"[{last}][tx{k}]overlay=x='{x}':y='{y}':enable='between(t\,{t0:.3f}\,{t1:.3f})'[v{k}]"); last = f"v{k}"
        print(f"[text-pass] {e.get('style','punch'):5s} {t0:7.2f}-{t1:7.2f} {'~' if e.get('shake') else ' '} {e['text']}")
    cmd += ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "0:a", "-t", f"{dur:.3f}", "-r", "60", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0: sys.exit(f"[text-pass] ffmpeg failed:\n{r.stderr[-1500:]}")
    print(f"[text-pass] wrote {a.out}")


if __name__ == "__main__":
    main()
