#!/usr/bin/env python3
"""build_layout.py — render the top-left SUBSCRIBE bug as a transparent overlay (.mov, qtrle RGBA).

v3 (2026-09-20): geometry measured off the creator's reference screenshot (the reference channel "HAMMER THAT SUB BUTTON")
and matched in units of the line's cap height C:

    ghost cap height   = 2.77 C          ghost is OUTLINE ONLY, light grey
    ghost left edge    = 0.67 C left of the line's left edge   (offset, NOT centred)
    line centre        = 0.22 C below the ghost's centre
    the line runs PAST the ghost's right end, icon at the far right, centred on the line
    the line itself has NO hard outline — flat white + accent, with a soft shadow for legibility

Font: the reference face is a wide heavy grotesque (width/char/cap = 0.72). Inter-Black measures 0.81, so it is
the match; Coolvetica Hv Comp measures 0.35 and is far too condensed for this look.

PIL frames + ffmpeg (this ffmpeg has no freetype). Renders only the graphic's own strip and writes a sidecar
JSON with the line's position inside it, so the overlay step anchors on the LINE and lets the ghost overflow
off the frame edge the way the reference does.

Usage: build_layout.py [--out free-carry-layout.mov] [--text "SUBSCRIBE FOR A "] [--accent-text "FREE CARRY"]
                    [--accent 255,60,105] [--size 72] [--seconds 8.0] [--ghost-alpha 85] [--embers 110]
"""
import argparse, json, math, os, random, shutil, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FACE = os.path.join(REPO, "assets", "fonts", "Inter-Black.otf")
FPS = 60
IN_T, OUT_T = 0.95, 0.45
IMPACT = 0.68

# ratios measured off the reference screenshot, in units of the line's cap height
GHOST_CAP, GHOST_DX, GHOST_DY = 2.77, -0.67, -0.22


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_back(x):
    return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2


def brand_defaults():
    """brand-kit.md -> presets/brand.json drives every default; CLI flags still override."""
    p = os.path.join(REPO, "presets", "brand.json")
    d = {}
    if os.path.isfile(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            d = {}
    line = (d.get("ask_line") or "SUBSCRIBE FOR MORE").strip()
    n = int(d.get("ask_accent_words") or 2)
    words = line.split()
    text = " ".join(words[:-n]) + " " if len(words) > n else ""
    accent_text = " ".join(words[-n:]) if len(words) > n else line
    hexc = (d.get("accent") or "#FF3C69").lstrip("#")
    rgb = ",".join(str(int(hexc[i:i + 2], 16)) for i in (0, 2, 4))
    logo = d.get("logo") or os.path.join("assets", "logos", "logo.png")
    if not os.path.isabs(logo):
        logo = os.path.join(REPO, logo)
    return dict(text=text, accent_text=accent_text, ghost=words[0] if words else "SUBSCRIBE", accent=rgb, logo=logo)


def main():
    B = brand_defaults()
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "free-carry-layout.mov"))
    ap.add_argument("--text", default=B["text"])
    ap.add_argument("--accent-text", default=B["accent_text"])
    ap.add_argument("--ghost", default=B["ghost"])
    ap.add_argument("--accent", default=B["accent"])
    ap.add_argument("--logo", default=B["logo"])
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--size", type=int, default=72)
    ap.add_argument("--ghost-alpha", type=int, default=85)
    ap.add_argument("--embers", type=int, default=230)
    ap.add_argument("--ember-palette", choices=("fire", "neon", "forge", "fire-visor"), default="fire",
                    help="fire = warm sparks + the accent colour; neon = electric cyan/violet, brighter bloom")
    a = ap.parse_args()

    accent = tuple(int(v) for v in a.accent.split(","))
    f_main = ImageFont.truetype(FACE, a.size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    cap = probe.textbbox((0, 0), "H", font=f_main)
    C = cap[3] - cap[1]                                  # the line's cap height: every ratio is in these units
    K = C / 53.0                                          # animation distances scale with it

    chars = [(c, False) for c in a.text] + [(c, True) for c in a.accent_text]
    widths = [probe.textlength(c, font=f_main) for c, _ in chars]
    text_w = sum(widths)

    logo = Image.open(a.logo).convert("RGBA")
    lh = int(a.size * 2.30)
    logo = logo.resize((max(2, int(logo.width * lh / logo.height)), lh), Image.LANCZOS)
    _rgb = Image.merge("RGB", logo.split()[:3]).filter(ImageFilter.UnsharpMask(radius=1.6, percent=165, threshold=2))
    logo = Image.merge("RGBA", _rgb.split() + (logo.split()[3],))   # sharpen colour only; alpha edge stays clean
    gap = int(0.5 * C)
    line_w = int(text_w) + gap + logo.width

    # ghost: outline only, sized so its cap height is 2.77 x the line's, then offset left and up
    gsz = a.size
    for _ in range(40):
        gc = probe.textbbox((0, 0), "H", font=ImageFont.truetype(FACE, gsz))
        if (gc[3] - gc[1]) >= GHOST_CAP * C:
            break
        gsz = int(gsz * 1.05) + 1
    f_ghost = ImageFont.truetype(FACE, gsz)
    gb = probe.textbbox((0, 0), a.ghost, font=f_ghost, stroke_width=max(2, int(0.065 * C)))
    ghost_w, ghost_h = gb[2] - gb[0], gb[3] - gb[1]

    MARGIN = int(4.2 * C)                                 # room for embers outside the artwork
    TX = MARGIN + max(0, int(-GHOST_DX * C))
    TY = MARGIN + max(0, int((GHOST_CAP - 1) * C / 2 + GHOST_DY * C))
    GX = TX + int(GHOST_DX * C) - gb[0]
    GY = TY + C // 2 + int(GHOST_DY * C) - ghost_h // 2 - gb[1]
    W = max(TX + line_w, GX + gb[0] + ghost_w) + MARGIN
    H = max(TY + int(1.6 * C), GY + gb[1] + ghost_h) + MARGIN
    H = max(H, TY + C // 2 + logo.height // 2 + MARGIN)
    lx = TX + int(text_w) + gap
    ly = TY + C // 2 - logo.height // 2
    print("[bug] face=%s cap=%dpx line=%dpx (text %d + icon %d) ghost=%dx%d -> strip %dx%d, line at (%d,%d)"
          % (os.path.basename(FACE), C, line_w, text_w, logo.width, ghost_w, ghost_h, W, H, TX, TY), flush=True)

    glow = Image.new("RGBA", (logo.width * 2, logo.height * 2), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((logo.width * 0.42, logo.height * 0.42, logo.width * 1.58, logo.height * 1.58),
                                 fill=accent + (150,))
    glow = glow.filter(ImageFilter.GaussianBlur(logo.width * 0.22))

    # fire = the shipped look (warm spark + a lifted version of the strip's accent).
    # neon = electric cyan into violet: it reads as GLOW rather than embers, and it is the one palette that
    # stays legible over Destiny's orange-and-teal gameplay because neither hue is in the strip behind it.
    # forge = sampled from the logo itself. Clustering the lit, chromatic pixels of your logo PNG by hue
    # gives blue 200-240 deg = 66 % (the visor and the cans), violet 240-260 = 7 %, magenta 300-320 = 5 %,
    # amber 40-60 = 5 %. Those three accents ARE the logo, so sparks in them read as thrown off the helmet.
    # Amber still leads the mix: it is what makes a particle read as a spark, and an all-blue swarm over a
    # mostly-blue helmet just flattens into it.
    if a.ember_palette == "neon":
        pal, bloom_w, bloom_t = [((120, 255, 246), 0.55), ((196, 128, 255), 0.45)], 5.2, 1.6
    elif a.ember_palette == "fire-visor":
        # fire, with a WHISPER of the visor. He liked F's yellow-and-pink identity and H's variety, so this
        # keeps F's two colours in their F proportions and spends only 15 % on visor blue -- enough that the
        # logo's own hue appears in the swarm, too little to turn the sparks into confetti.
        pal = [((255, 205, 145), 0.40),
               ((min(255, accent[0] + 20), min(255, accent[1] + 40), min(255, accent[2] + 30)), 0.45),
               ((110, 175, 255), 0.15)]
        bloom_w, bloom_t = 3.8, 1.2
    elif a.ember_palette == "forge":
        pal = [((255, 200, 140), 0.45), ((110, 175, 255), 0.35), ((255, 95, 175), 0.20)]
        bloom_w, bloom_t = 4.2, 1.3
    else:
        pal = [((255, 205, 145), 0.45),
               ((min(255, accent[0] + 20), min(255, accent[1] + 40), min(255, accent[2] + 30)), 0.55)]
        bloom_w, bloom_t = 3.4, 1.1
    pal_cols = [c for c, _ in pal]
    pal_cum = []
    acc = 0.0
    for _, w in pal:
        acc += w; pal_cum.append(acc)

    def pick_col(rr):
        u = rr.random() * acc
        return next(c for c, cum in zip(pal_cols, pal_cum) if u <= cum)

    rng = random.Random(7)
    parts = []
    for i in range(a.embers):
        burst = i < int(a.embers * 0.52)   # more drifters = more embers hanging in the air
        if burst:
            ox, oy = lx + logo.width * 0.5, ly + logo.height * 0.5
            ang = rng.uniform(-math.pi, math.pi)
            spd = rng.uniform(150, 700) * K
            t0 = IMPACT + rng.uniform(0.0, 0.07)
        else:
            ox = TX + rng.uniform(0, text_w)
            oy = TY + rng.uniform(0, C)
            ang = rng.uniform(-math.pi * 0.82, -math.pi * 0.18)
            spd = rng.uniform(165, 440) * K            # "jump up a little higher" (was 50-230)
            t0 = IMPACT + rng.uniform(0.0, 3.4)
        # Gravity is per-particle so the two populations read differently: the impact burst keeps the old
        # scatter, while a drifter is thrown ~2.5x higher AND pulled back ~1.7x harder, so it visibly
        # tops out over the line and falls back down instead of sailing off the top of the frame.
        parts.append(dict(x=ox, y=oy, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd,
                          life=rng.uniform(1.5, 3.8), t0=t0, r=rng.uniform(2.6, 7.4) * K,
                          drag=0.45 if burst else 0.22, grav=(195 if burst else 330) * K,
                          col=pick_col(rng)))

    work = os.path.join(HERE, "work", "frames")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    n = int(round(a.seconds * FPS))
    stag = (IN_T - 0.20) / max(1, len(chars))

    for i in range(n):
        t = i / FPS
        out_k = 0.0 if t < a.seconds - OUT_T else min(1.0, (t - (a.seconds - OUT_T)) / OUT_T)
        g_a = 1 - ease_out(out_k)
        rise = -10 * K * ease_out(out_k)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        gk = max(0.0, min(1.0, (t - 0.10) / 0.55))
        if gk > 0:
            gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(gl).text((GX + 12 * K * (1 - ease_out(gk)), GY + rise), a.ghost, font=f_ghost,
                                    fill=(255, 255, 255, 0), stroke_width=max(2, int(0.065 * C)),
                                    stroke_fill=(238, 238, 244, int(a.ghost_alpha * ease_out(gk) * g_a)))
            im.alpha_composite(gl)

        em = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ed = ImageDraw.Draw(em)
        any_em = False
        for p in parts:
            age = t - p["t0"]
            if age <= 0 or age > p["life"]:
                continue
            any_em = True
            f = age / p["life"]
            x = p["x"] + p["vx"] * age * (1 - p["drag"] * f)
            y = p["y"] + p["vy"] * age * (1 - p["drag"] * f) + p["grav"] * age * age
            al = int(255 * (1 - f) ** 0.95 * g_a)
            r = p["r"] * (1 - 0.35 * f)
            col = p["col"]
            ed.ellipse((x - r, y - r, x + r, y + r), fill=col + (al,))
        if any_em:
            im.alpha_composite(em.filter(ImageFilter.GaussianBlur(bloom_w * K)))   # wide bloom
            im.alpha_composite(em.filter(ImageFilter.GaussianBlur(bloom_t * K)))   # tight bloom
            im.alpha_composite(em)

        fk = (t - IMPACT) / 0.22
        if 0 <= fk <= 1:
            fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            rr = (140 + 300 * fk) * K
            ImageDraw.Draw(fl).ellipse((lx + logo.width / 2 - rr, ly + logo.height / 2 - rr,
                                        lx + logo.width / 2 + rr, ly + logo.height / 2 + rr),
                                       fill=accent + (int(150 * (1 - fk) ** 2 * g_a),))
            im.alpha_composite(fl.filter(ImageFilter.GaussianBlur(26 * K)))

        lk = max(0.0, min(1.0, (t - 0.42) / 0.26))
        if lk > 0:
            sc = ease_back(lk) if lk < 1 else 1.0
            bob = math.sin((t - IMPACT) * 2 * math.pi / 2.3) * 5.5 * K if t > IMPACT else 0.0
            pulse = 0.55 + 0.45 * math.sin((t - IMPACT) * 2 * math.pi / 2.3)
            lw, lhh = max(2, int(logo.width * sc)), max(2, int(logo.height * sc))
            cx = lx + logo.width // 2
            cy = ly + logo.height // 2 + bob + rise
            gsc = glow.resize((lw * 2, lhh * 2), Image.LANCZOS)
            gsc.putalpha(gsc.getchannel("A").point(lambda v, p=pulse, k=lk, ga=g_a: int(v * p * k * ga)))
            im.alpha_composite(gsc, (int(cx - gsc.width / 2), int(cy - gsc.height / 2)))
            ls = logo.resize((lw, lhh), Image.LANCZOS)
            ls.putalpha(ls.getchannel("A").point(lambda v, k=lk, ga=g_a: int(v * min(1.0, k * 1.4) * ga)))
            im.alpha_composite(ls, (int(cx - lw / 2), int(cy - lhh / 2)))

        # the line: flat white + accent like the reference (no hard outline), on a soft shadow so it still
        # reads over bright footage
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        x = TX
        for k, (ch, is_accent) in enumerate(chars):
            ck = max(0.0, min(1.0, (t - 0.12 - k * stag) / 0.18))
            if ck > 0 and ch != " ":
                al = int(255 * ck * g_a)
                dy = 16 * K * (1 - ease_out(ck)) + rise
                ld.text((x, TY + dy - cap[1]), ch, font=f_main,
                        fill=(accent + (al,)) if is_accent else (255, 255, 255, al))
            x += widths[k]
        sh = lay.filter(ImageFilter.GaussianBlur(0.16 * C))
        sh = Image.merge("RGBA", (Image.new("L", (W, H), 6), Image.new("L", (W, H), 5),
                                  Image.new("L", (W, H), 12), sh.getchannel("A").point(lambda v: int(v * 0.72))))
        im.alpha_composite(sh, (0, int(0.05 * C)))
        im.alpha_composite(lay)

        im.save(os.path.join(work, "f%04d.png" % i))

    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
           "-i", os.path.join(work, "f%04d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("[bug] ffmpeg failed:\n" + r.stderr[-1200:])
    shutil.rmtree(work, ignore_errors=True)
    json.dump({"strip_w": W, "strip_h": H, "line_x": TX, "line_y": TY, "line_w": line_w, "cap": C},
              open(os.path.splitext(a.out)[0] + ".json", "w"))
    print("[bug] wrote %s (%d frames, %.2fs, %dx%d RGBA)" % (a.out, n, a.seconds, W, H), flush=True)


if __name__ == "__main__":
    main()
