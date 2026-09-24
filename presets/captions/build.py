#!/usr/bin/env python3
"""build.py — burn captions from the cut's transcript, in the owner's font and colors.

  usage: python3 presets/captions/build.py <job_dir> [--position center|low] [--base <video>] [--out <mp4>]
                                                    [--max-chars 26] [--gap 0.6] [--pop 0.12] [--until SEC]

Reads   <job>/outputs/<job>.transcript.json   (words on the cut's clock — never re-transcribes)
        presets/brand.json                     (font_caption, caption_px, text, dark)
Writes  <job>/outputs/<job>.captioned.mp4

How it works — and why it's one pass
  Words are grouped into short phrases (a line of at most --max-chars characters, broken where the speaker
  paused more than --gap seconds). Each phrase gets a solid box pre-sized to the whole phrase; the box cuts on
  and off, and the WORDS pop in one by one on their own timestamps (a --pop-second rise and fade). That's the
  on-beat "karaoke" feel without anything ever moving the box.

  Every frame of the caption layer is drawn with Pillow and streamed straight into ffmpeg as a transparent
  video (qtrle .mov), which is then overlaid on the cut in ONE ffmpeg pass. This ffmpeg build has no text
  renderer of its own, and stacking hundreds of PNG overlays gets slow and fragile — one overlay stream is
  faster, deterministic, and can't drift.

Positions
  center — the box sits on the vertical middle of the frame (the seam between a top graphic and a bottom
           face on a split-frame short). Default.
  low    — the box sits at 78% of the height, under a face that fills the frame. Both stay inside the 9:16 safe
           box (nothing above 200 px or below 1620 px of a 1920-tall frame — platform UI lives there).
"""
import argparse, json, math, os, subprocess, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def die(m):
    sys.exit("[captions] " + m)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", path],
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    st = d["streams"][0]
    n, den = st["r_frame_rate"].split("/")
    return int(st["width"]), int(st["height"]), float(n) / float(den), float(d["format"]["duration"])


def load_brand():
    p = os.path.join(REPO, "presets", "brand.json")
    if not os.path.isfile(p):
        die("presets/brand.json not found — fill brand-kit.md and run 'apply my brand kit' first")
    return json.load(open(p, encoding="utf-8"))


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def phrases(words, max_chars, gap):
    """group consecutive words into on-screen lines"""
    out, cur = [], []
    for w in words:
        if cur:
            length = len(" ".join(x["text"] for x in cur)) + 1 + len(w["text"])
            paused = w["start"] - cur[-1]["end"] > gap
            if length > max_chars or paused:
                out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--position", choices=("center", "low"), default="center")
    ap.add_argument("--base"); ap.add_argument("--out")
    ap.add_argument("--max-chars", type=int, default=26)
    ap.add_argument("--gap", type=float, default=0.6)
    ap.add_argument("--pop", type=float, default=0.12)
    ap.add_argument("--until", type=float, default=None, help="preview only this many seconds")
    a = ap.parse_args()

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        die("Pillow is required: pip install pillow")

    job = os.path.abspath(a.job_dir.rstrip("/"))
    name = os.path.basename(job)
    base = a.base or os.path.join(job, "outputs", f"{name}.mp4")
    tpath = os.path.join(job, "outputs", f"{name}.transcript.json")
    out = a.out or os.path.join(job, "outputs", f"{name}.captioned.mp4")
    for p in (base, tpath):
        if not os.path.isfile(p):
            die(f"missing {p}")
    brand = load_brand()
    W, H, fps, dur = probe(base)
    if a.until:
        dur = min(dur, a.until)

    scale = W / 1080.0
    px = int(round(brand.get("caption_px", 48) * scale))
    fpath = brand.get("font_caption") or "assets/fonts/Inter-Bold.otf"
    if not os.path.isabs(fpath):
        fpath = os.path.join(REPO, fpath)
    try:
        font = ImageFont.truetype(fpath, px)
    except Exception:
        die(f"caption font not found: {fpath}")
    text_col = rgb(brand.get("text", "#FFFFFF"))
    box_col = (0, 0, 0)
    pad_x, pad_y, radius = int(24 * scale), int(14 * scale), int(14 * scale)

    words = json.load(open(tpath, encoding="utf-8"))["words"]
    words = [w for w in words if w["start"] < dur]
    lines = phrases(words, a.max_chars, a.gap)

    # measure every phrase once
    probe_img = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    plan = []
    for ph in lines:
        text = " ".join(w["text"] for w in ph)
        tw = probe_img.textlength(text, font=font)
        bw, bh = int(tw + 2 * pad_x), int(line_h + 2 * pad_y)
        cy = int(H * (0.5 if a.position == "center" else 0.78))
        y_safe_top, y_safe_bot = int(H * 200 / 1920), int(H * 1620 / 1920)
        cy = max(y_safe_top + bh // 2, min(y_safe_bot - bh // 2, cy))
        x0, y0 = W // 2 - bw // 2, cy - bh // 2
        # x of each word inside the box
        xs, cursor = [], x0 + pad_x
        for w in ph:
            xs.append(cursor)
            cursor += probe_img.textlength(w["text"] + " ", font=font)
        plan.append({"t0": ph[0]["start"], "t1": ph[-1]["end"] + 0.15, "box": (x0, y0, x0 + bw, y0 + bh),
                     "words": [(w["text"], w["start"], x) for w, x in zip(ph, xs)], "ty": y0 + pad_y})
    # a phrase never overlaps the next one
    for p, q in zip(plan, plan[1:]):
        p["t1"] = min(p["t1"], q["t0"])

    n_frames = int(math.ceil(dur * fps))
    layer = os.path.join(job, "outputs", f"{name}.captions.mov")
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                            "-s", f"{W}x{H}", "-r", f"{fps:.6f}", "-i", "-",
                            "-c:v", "qtrle", "-pix_fmt", "argb", layer], stdin=subprocess.PIPE)
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    idx = 0
    for f in range(n_frames):
        t = f / fps
        while idx < len(plan) and plan[idx]["t1"] <= t:
            idx += 1
        if idx >= len(plan) or t < plan[idx]["t0"]:
            enc.stdin.write(blank.tobytes()); continue
        p = plan[idx]
        im = blank.copy(); d = ImageDraw.Draw(im)
        d.rounded_rectangle(p["box"], radius=radius, fill=box_col + (255,))
        for text, ws, x in p["words"]:
            if t < ws:
                continue
            k = min(1.0, (t - ws) / a.pop) if a.pop > 0 else 1.0
            ease = 1 - (1 - k) ** 3
            rise = int((1 - ease) * 6 * scale)
            d.text((x, p["ty"] + rise), text, font=font, fill=text_col + (int(255 * ease),))
        enc.stdin.write(im.tobytes())
    enc.stdin.close(); enc.wait()
    if enc.returncode != 0:
        die("caption layer encode failed")

    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", base, "-i", layer,
           "-filter_complex", "[1:v]format=rgba[c];[0:v][c]overlay=0:0:format=auto[v]",
           "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}", "-r", f"{fps:.6f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy",
           "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    os.remove(layer)
    print(f"[captions] {len(plan)} phrases, {len(words)} words, {a.position}, {px}px {os.path.basename(fpath)} -> {out}")


if __name__ == "__main__":
    main()
