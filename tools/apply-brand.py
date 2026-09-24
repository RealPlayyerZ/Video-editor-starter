#!/usr/bin/env python3
"""apply-brand.py — Part B of brand-kit.md. Turns the filled-in form into files the tools read.

  usage: python3 tools/apply-brand.py [--no-render]

What it does
  1. Parses brand-kit.md Part A into presets/brand.json (every builder reads that file).
  2. Writes section 8 (words the transcriber gets wrong) into presets/caption-corrections.json as "auto" entries.
  3. Renders projects/_brandcheck/outputs/brandcheck.mp4 — ten seconds of your hero color, a caption in your
     caption font, and your ask line if you set one — so you can SEE the brand came through.
  4. Refuses if a required field still has a <<placeholder>>, and lists them.

It never edits CLAUDE.md. Who you are, in your words, is yours to write.
"""
import argparse, json, os, re, subprocess, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KIT = os.path.join(REPO, "brand-kit.md")
OUT_JSON = os.path.join(REPO, "presets", "brand.json")
CORR = os.path.join(REPO, "presets", "caption-corrections.json")

# label as it appears in brand-kit.md -> key in brand.json (required fields must not be placeholders)
FIELDS = {
    "Name / handle": ("handle", True),
    "Channel(s)": ("channels", False),
    "What the channel is, in one line": ("about", False),
    "What you make most": ("formats", False),
    "Voice, in three words": ("voice", False),
    "Words you actually say": ("say", False),
    "Words you never say": ("never_say", False),
    "What your audience calls themselves, if anything": ("audience", False),
    "Hero": ("hero", True),
    "Accent": ("accent", True),
    "Background / dark": ("dark", True),
    "Text on dark": ("text", False),
    "Headline / impact font file": ("font_headline", True),
    "Caption font file": ("font_caption", True),
    "Caption size at 1080 wide": ("caption_px", False),
    "Intro treatment": ("intro", False),
    "Outro video": ("outro", False),
    "Outro music": ("outro_music", False),
    "Background-music bed (default)": ("bed", False),
    "Line": ("ask_line", False),
    "Accent words": ("ask_accent_words", False),
    "Logo file": ("logo", False),
    "When it appears": ("ask_at", False),
    "Face reference photos": ("face_refs", False),
}
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def clean(v):
    v = v.strip().strip("`").strip()
    v = re.sub(r"\s*\(.*?\)\s*$", "", v)          # drop trailing "(explanations)"
    return v.strip("`").strip()


def parse(text):
    brand, missing = {}, []
    partA = text.split("# Part B")[0]
    for label, (key, required) in FIELDS.items():
        m = re.search(r"\*\*" + re.escape(label) + r"(?::\*\*|\*\*[^\n:]*:)[ \t]*(.+)", partA)
        if not m:
            continue
        raw = m.group(1).strip()
        if "<<" in raw:
            if required:
                missing.append(label)
            continue
        val = clean(raw)
        if key in ("hero", "accent", "dark", "text"):
            h = HEX.search(val)
            if not h:
                missing.append(label + " (needs a #hex color)"); continue
            val = h.group(0).upper()
        if key == "caption_px":
            n = re.search(r"\d+", val); val = int(n.group(0)) if n else 48
        if key == "ask_accent_words":
            n = re.search(r"\d+", val); val = int(n.group(0)) if n else 2
        if key == "ask_at":
            n = re.search(r"\d+(\.\d+)?", val); val = float(n.group(0)) if n else 22.0
        if key in ("intro", "outro", "outro_music", "bed", "logo") and val.lower().startswith("none"):
            val = None
        brand[key] = val
    # section 7: the thumbnail paragraph is free text between the heading and the next list item
    m = re.search(r"## 7\.[^\n]*\n\n(.+?)\n\n", partA, re.S)
    if m and "<<" not in m.group(1):
        brand["thumbnail_look"] = " ".join(m.group(1).split())
    # section 8: "hears → should be" lines inside the code block
    corr = {}
    m = re.search(r"## 8\..*?```(.*?)```", partA, re.S)
    if m:
        for ln in m.group(1).splitlines():
            if "→" in ln and "<<" not in ln:
                a, b = [x.strip() for x in ln.split("→", 1)]
                if a and b and " " not in a:
                    corr[a] = b
    brand["corrections"] = corr
    brand.setdefault("text", "#FFFFFF")
    brand.setdefault("caption_px", 48)
    return brand, missing


def render_check(brand):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[brand] Pillow not installed (pip install pillow) — skipping the brand check render")
        return
    W, H = 1920, 1080
    job = os.path.join(REPO, "projects", "_brandcheck", "outputs"); os.makedirs(job, exist_ok=True)

    def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

    def font(path, size):
        p = path if os.path.isabs(path) else os.path.join(REPO, path)
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            print(f"[brand] font not found: {p} — using the default font for the check")
            return ImageFont.load_default()

    im = Image.new("RGB", (W, H), rgb(brand["dark"]))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 140), fill=rgb(brand["hero"]))
    fh = font(brand["font_headline"], 72); fc = font(brand["font_caption"], int(brand["caption_px"] * 1.78))
    d.text((60, 30), (brand.get("handle") or "YOUR CHANNEL").upper(), font=fh, fill=rgb(brand["text"]))
    cap = "This is what your captions look like."
    tw = d.textlength(cap, font=fc)
    d.rectangle((W / 2 - tw / 2 - 30, H / 2 - 70, W / 2 + tw / 2 + 30, H / 2 + 70), fill=(0, 0, 0))
    d.text((W / 2 - tw / 2, H / 2 - 48), cap, font=fc, fill=rgb(brand["text"]))
    if brand.get("ask_line"):
        d.text((60, H - 160), brand["ask_line"].upper(), font=fh, fill=rgb(brand["accent"]))
    png = os.path.join(job, "brandcheck.png"); im.save(png)
    mp4 = os.path.join(job, "brandcheck.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-loop", "1", "-t", "10", "-i", png,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", mp4], check=True)
    print(f"[brand] look at it: {mp4}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-render", action="store_true"); a = ap.parse_args()
    if not os.path.isfile(KIT):
        sys.exit("[brand] no brand-kit.md at the repo root")
    text = open(KIT, encoding="utf-8").read()
    brand, missing = parse(text)
    if missing:
        print("[brand] these required fields still have placeholders — fill them in Part A and run again:")
        for m in missing: print("   -", m)
        sys.exit(1)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(brand, f, indent=2, ensure_ascii=False)
    print(f"[brand] wrote {OUT_JSON}")

    corr = {"auto": {}, "flag": {}}
    if os.path.isfile(CORR):
        try:
            corr = json.load(open(CORR, encoding="utf-8"))
        except Exception:
            pass
    corr.setdefault("auto", {}).update(brand["corrections"])
    with open(CORR, "w", encoding="utf-8") as f:
        json.dump(corr, f, indent=2, ensure_ascii=False)
    print(f"[brand] {len(brand['corrections'])} correction(s) merged into {CORR}")

    if not a.no_render:
        render_check(brand)

    left = text.count("<<")
    if left:
        cleared = re.sub(r"<<[^>]*>>", "none", text)
        with open(KIT, "w", encoding="utf-8") as f:
            f.write(cleared)
        print(f"[brand] {left} optional placeholder(s) set to 'none' — brand-kit.md is complete, setup is done.")
    else:
        print("[brand] no placeholders left — setup is done.")


if __name__ == "__main__":
    main()
