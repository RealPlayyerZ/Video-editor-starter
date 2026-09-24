#!/usr/bin/env python3
"""apply the LOCKED sweep intro (see presets/sweep-intro-style.md) to the front of a finished cut.

the reference channel-style fast motion-blur/zoom-warp sweep: brand-colored horizontal streak lines +
radial zoom-blur trail + asymmetric brightness flash, settling into sharp focus on the real
opening content. Total duration 0.4s. A whoosh SFX is mixed in, synced so its attack lands at
the flash's hold-start (PEAK_T=0.30s).

Two zoom modes:
  - Generic (default): self-relative "punch" - starts at the input's own frame 0 (whatever
    framing that already is), zooms 32% in through the blur, eases back to the same starting
    framing by settle. Use when the video has no separate punch-in/zoom effect already baked
    into its opening seconds - the sweep has nowhere "wider" to zoom in from.
  - Target-crop (--frame-source + --target-crop): for videos whose own pipeline already
    punches in on the opening (this project's zoom effect, see workflows/short-form.md /
    the punch-in crop plan) - starts at the WIDE/native framing (from --frame-source, e.g.
    the pre-zoom rough cut) and monotonically zooms/warps IN to land exactly on the
    already-established target crop by settle, so the cut into the continuing (already
    zoomed) footage is seamless. --target-crop is x,y,w,h in the frame-source's native pixel
    space (same convention as the project's own IN crop).

Usage:
    build.py <input-video.mp4> <output-video.mp4> [--sfx sfx.mp3]
             [--frame-source wide-video.mp4] [--target-crop x,y,w,h]

sfx-source defaults to the locked brand asset:
    assets/sfx/synth/whoosh.wav (synthesized; or the 'whoosh' path in brand.json)

Replaces the first DURATION seconds of <input-video> with the generated sweep (does not
extend total runtime).
"""
import argparse
import json, os
import random
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageChops, ImageFilter

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FPS = 60
DURATION = 0.4
N_FRAMES = int(round(DURATION * FPS))  # 24
PEAK_T = 0.30
HOLD_END = 0.34
OVERSHOOT = 1.15  # target-crop mode only: how far past the target the zoom punches in before settling back

RY = (255, 60, 172)   # brand pink/magenta
PE = (123, 47, 247)   # brand purple
WH = (255, 255, 255)  # white
COLORS = [RY, PE, WH]

N_STREAKS = 30  # LOCKED (v6) - settled here after a V4(46)/V5(30) side-by-side on density

def _brand():
    """brand-kit.md -> presets/brand.json: the sweep colour and the whoosh sound come from there."""
    p = os.path.join(REPO, "presets", "brand.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _hex_rgb(h, fallback):
    try:
        h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


_B = _brand()
RY = _hex_rgb(_B.get("hero", ""), RY)                                    # the sweep takes the owner's hero colour
DEFAULT_SFX = _B.get("whoosh") or os.path.join(REPO, "assets", "sfx", "synth", "whoosh.wav")   # a synthesized whoosh ships; set 'whoosh' in brand.json to use your own
SFX_ATTACK_T = 0.300  # measured peak of the whoosh's sharp attack - synced to PEAK_T/HOLD_END


def make_streaks(seed=7):
    random.seed(seed)
    streaks = []
    for _ in range(N_STREAKS):
        streaks.append({
            "y": random.uniform(0, 1),  # fraction of height, scaled to actual H at build time
            # thickness: LOCKED (v6) - the midpoint of a V4(20-140/45)/V5(8-55/18) side-by-side,
            # after V4 read too thick/dense and V5 too thin against the recovered reference.
            "thickness": random.triangular(14, 98, 32),
            "speed": random.uniform(0.75, 1.6),
            # phase: calibrated so first appearance clusters ~0.1-0.15s into the 0.4s sweep,
            # spreading out toward ~0.35s - matches the measured onset frame range (6-22 of 24)
            # from the reference color-mask analysis.
            "phase": random.uniform(-0.7, -0.1),
            "color": random.choice(COLORS),
            # tail_len_frac: lengthened (was 0.086-0.242) so streaks extend further across the
            # frame, matching the reference's longer sweep lines.
            "tail_len_frac": random.uniform(0.22, 0.5),  # fraction of width
        })
    return streaks


def ease_in_cubic(p):
    return p ** 3


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def coverage_at(t):
    if t <= PEAK_T:
        return t / PEAK_T
    elif t <= HOLD_END:
        return 1.0
    else:
        return 1.0 - (t - HOLD_END) / (DURATION - HOLD_END)


# ---------------------------------------------------------------------------
# Generic (self-relative) zoom mode
# ---------------------------------------------------------------------------

def scale_at(t):
    # Never drop below 1.0 - the frame must stay fully filled (no black borders) at all times.
    if t <= PEAK_T:
        p = t / PEAK_T
        return 1.0 + (1.32 - 1.0) * ease_in_cubic(p)
    elif t <= HOLD_END:
        return 1.32
    else:
        p = (t - HOLD_END) / (DURATION - HOLD_END)
        return 1.32 + (1.0 - 1.32) * ease_out_cubic(p)


def scale_frame(base, w, h, scale):
    if scale <= 1.0001:
        return base.copy()
    sw, sh = int(round(w * scale)), int(round(h * scale))
    big = base.resize((sw, sh), Image.LANCZOS)
    left = (sw - w) // 2
    top = (sh - h) // 2
    return big.crop((left, top, left + w, top + h))


def render_generic(base, w, h, t):
    scale = scale_at(t)
    primary = scale_frame(base, w, h, scale)

    n_ghosts = 5
    trail_accum = Image.new("RGB", (w, h), (0, 0, 0))
    for g in range(1, n_ghosts + 1):
        ghost_scale = max(1.0, 1.0 + (scale - 1.0) * (1.0 - g * 0.12))
        ghost = scale_frame(base, w, h, ghost_scale)
        trail_accum = ImageChops.screen(trail_accum, ghost)

    return primary, trail_accum


# ---------------------------------------------------------------------------
# Target-crop (native -> established zoom target) mode
# ---------------------------------------------------------------------------

def crop_progress_at(t):
    """0 at t=0 (native/wide), 1 at the target crop, overshoots past 1 during the hold
    (extra punch-in beyond the target), eases back to exactly 1 by DURATION (seamless
    handoff into the continuing already-zoomed footage)."""
    if t <= PEAK_T:
        return ease_in_cubic(t / PEAK_T)
    elif t <= HOLD_END:
        return OVERSHOOT
    else:
        p2 = (t - HOLD_END) / (DURATION - HOLD_END)
        return OVERSHOOT + (1.0 - OVERSHOOT) * ease_out_cubic(p2)


def crop_box_at(p, native_w, native_h, target_crop):
    tx, ty, tw, th = target_crop
    cw = native_w + (tw - native_w) * p
    ch = native_h + (th - native_h) * p
    p_center = min(p, 1.0)
    native_cx, native_cy = native_w / 2, native_h / 2
    target_cx, target_cy = tx + tw / 2, ty + th / 2
    cx = native_cx + (target_cx - native_cx) * p_center
    cy = native_cy + (target_cy - native_cy) * p_center
    x0 = max(0.0, min(native_w - cw, cx - cw / 2))
    y0 = max(0.0, min(native_h - ch, cy - ch / 2))
    return x0, y0, cw, ch


def crop_and_scale(base, native_w, native_h, out_w, out_h, box):
    x0, y0, cw, ch = box
    cropped = base.crop((int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch))))
    return cropped.resize((out_w, out_h), Image.LANCZOS)


def render_target_crop(base, native_w, native_h, out_w, out_h, target_crop, t):
    p = crop_progress_at(t)
    primary = crop_and_scale(base, native_w, native_h, out_w, out_h, crop_box_at(p, native_w, native_h, target_crop))

    n_ghosts = 5
    trail_accum = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    for g in range(1, n_ghosts + 1):
        # trailing ghosts sit BEHIND (less zoomed than) the primary along the same trajectory
        p_ghost = max(0.0, p - g * 0.12 * max(p, 0.2))
        ghost = crop_and_scale(base, native_w, native_h, out_w, out_h,
                                crop_box_at(p_ghost, native_w, native_h, target_crop))
        trail_accum = ImageChops.screen(trail_accum, ghost)

    return primary, trail_accum


# ---------------------------------------------------------------------------
# Shared compositing: streaks + trail-blend + flash
# ---------------------------------------------------------------------------

def build_streak_layer(streaks, w, h, coverage):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for s in streaks:
        local_t = coverage * s["speed"] + s["phase"]
        local_t = max(0.0, min(1.0, local_t))
        if local_t <= 0:
            continue
        tail_len = s["tail_len_frac"] * w
        y = s["y"] * h
        head_x = local_t * (w + tail_len) - tail_len
        steps = 12
        for i in range(steps):
            frac = i / steps
            seg_x1 = head_x - tail_len * frac
            seg_x2 = head_x - tail_len * (frac - 1.0 / steps)
            # boosted ramp (1.4 -> 2.2) so streaks hit full opacity earlier/read as bolder,
            # matching the reference's solid (not faint) bands.
            alpha = int(255 * (1.0 - frac) * min(1.0, coverage * 2.2))
            if alpha <= 0:
                continue
            r, g, b = s["color"]
            draw.rectangle(
                [seg_x1, y - s["thickness"] / 2, seg_x2, y + s["thickness"] / 2],
                fill=(r, g, b, alpha),
            )
    # reduced blur radius (6 -> 3) so thickness reads closer to its drawn size instead of
    # being softened/thinned out by an oversized blur relative to the line width.
    layer = layer.filter(ImageFilter.GaussianBlur(radius=3))
    return layer


def composite_frame(primary, trail_accum, streaks, w, h, coverage):
    trail_alpha = min(1.0, coverage * 0.6)
    blended = Image.blend(primary, ImageChops.screen(primary, trail_accum), trail_alpha)

    img = blended.convert("RGBA")
    img = Image.alpha_composite(img, build_streak_layer(streaks, w, h, coverage))

    # brightness flash - blend alpha 0.22 (was 0.72 pre-calibration, read as a "flashbang";
    # 0.35 after the first recalibration; trimmed again to 0.22 once the denser/thicker/longer
    # streak pass on its own pushed peak brightness past the measured reference range - streaks
    # now contribute more of the frame's own brightness, so less flash is needed on top to land
    # in the same measured 97-151/255 peak window).
    flash_alpha = min(1.0, coverage * 1.15) ** 1.4
    if flash_alpha > 0.01:
        rgb_img = img.convert("RGB")
        white = Image.new("RGB", (w, h), (255, 255, 255))
        flashed = Image.blend(rgb_img, white, flash_alpha * 0.22)
        img = flashed.convert("RGBA")

    return img.convert("RGB")


def run(cmd):
    subprocess.run(cmd, check=True)


def ffprobe(args, path):
    out = subprocess.run(["ffprobe", "-v", "error", *args, path], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("in_video")
    ap.add_argument("out_video")
    ap.add_argument("--sfx", default=DEFAULT_SFX)
    ap.add_argument("--frame-source", default=None)
    ap.add_argument("--target-crop", default=None, help="x,y,w,h in frame-source's native pixel space")
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    args = ap.parse_args()

    in_video, out_video, sfx_src = args.in_video, args.out_video, args.sfx
    frame_source = args.frame_source or in_video
    target_crop = tuple(int(v) for v in args.target_crop.split(",")) if args.target_crop else None

    if not os.path.isfile(in_video):
        print(f"[sweep-intro] no input video: {in_video}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(frame_source):
        print(f"[sweep-intro] no frame source: {frame_source}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(sfx_src):
        print(f"[sweep-intro] no sfx source: {sfx_src}", file=sys.stderr)
        sys.exit(1)

    w = int(ffprobe(["-select_streams", "v:0", "-show_entries", "stream=width", "-of", "default=nw=1:nk=1"], in_video))
    h = int(ffprobe(["-select_streams", "v:0", "-show_entries", "stream=height", "-of", "default=nw=1:nk=1"], in_video))
    fps_str = ffprobe(["-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1"], in_video)
    print(f"[sweep-intro] input {w}x{h} @ {fps_str}fps, mode={'target-crop' if target_crop else 'generic'}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        frame0_path = os.path.join(tmp, "frame0.png")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", frame_source, "-frames:v", "1", frame0_path])

        base = Image.open(frame0_path).convert("RGB")
        native_w, native_h = base.size
        streaks = make_streaks()

        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        for i in range(N_FRAMES):
            t = i / FPS
            coverage = coverage_at(t)
            if target_crop:
                primary, trail = render_target_crop(base, native_w, native_h, w, h, target_crop, t)
            else:
                primary, trail = render_generic(base, w, h, t)
            frame = composite_frame(primary, trail, streaks, w, h, coverage)
            frame.save(os.path.join(frames_dir, f"f{i:03d}.png"))

        intro_clip = os.path.join(tmp, "intro.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%03d.png"),
             "-t", str(DURATION), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", intro_clip])

        rest_clip = os.path.join(tmp, "rest.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", str(DURATION), "-i", in_video, "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", rest_clip])

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w") as f:
            f.write(f"file '{intro_clip}'\nfile '{rest_clip}'\n")
        video_only = os.path.join(tmp, "video_only.mp4")
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", video_only])

        audio_only = os.path.join(tmp, "audio_only.m4a")
        sfx_dur = float(ffprobe(["-show_entries", "format=duration", "-of", "default=nw=1:nk=1"], sfx_src))
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", in_video, "-i", sfx_src,
             "-filter_complex",
             f"[1:a]atrim=0:{sfx_dur},asetpts=PTS-STARTPTS[sfx];"
             f"[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]",
             "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", audio_only])

        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", video_only, "-i", audio_only,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
             "-movflags", "+faststart", out_video])

    print(f"[sweep-intro] wrote {out_video}", file=sys.stderr)


if __name__ == "__main__":
    main()
