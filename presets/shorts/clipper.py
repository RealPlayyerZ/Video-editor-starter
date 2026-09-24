#!/usr/bin/env python3
"""
clipper.py — turn a finished long-form job into ready-to-post 9:16 Shorts.

The "second entry" node from the Video Editor Map: a finished long-form re-enters the pipeline
as several short-form jobs. This tool does the parts that are new — picking the moments, cutting
them into standard job folders, reframing to 9:16 with punch-in zooms — then hands each clip to
the LOCKED short-form machinery that already exists (TikTok/raw captions, the sweep intro,
verify-final, finalize).

  1. RANK   presets/shorts/clipper.py <job>                             # numbered list of candidate moments
  2. PICK   presets/shorts/clipper.py <job> --pick 1,3 --captions on|off # builds + finishes those clips
     or     presets/shorts/clipper.py <job> --window 8:05-8:25 --captions on [--layout face|stacked] [--hook-text "..."]

STYLE (studied 2026-09-08 on six of the reference channel's Shorts — see workflows/shorts-clipper.md):
  * 12–35 s, cold open (no title/hook card — the first frame is the hook), a punchy 2–4 word title
  * the creator big in frame, with hard-cut PUNCH-IN zooms on reaction beats every few seconds
  * gameplay / screen content → STACKED: facecam on TOP, content BELOW
  * captions are a per-video call (his run none; muted viewers favour them) → --captions is REQUIRED
  * no brand outro on Shorts (creator's call: a third of the runtime)

Ranking (from outputs/<job>.transcript.json, never re-transcribed): windows start and end on
natural pause boundaries; score = hook strength in the first seconds + speech density (a
low-density stretch = he's watching, not talking) − long silences + a clean ending. Written to
projects/<job>/shorts-candidates.json and printed — taste stays with the creator.

Each pick becomes projects/<job>-short-NN/ :
  raw/<clip>.mp4                  16:9 slice of the clean base cut (outputs/<job>.mp4)
  outputs/<clip>.mp4              9:16 1080x1920 reframed base with punch-ins (what the caption builder reads)
  outputs/<clip>.transcript.json  the source transcript's words inside the window, rebased to 0
  intent.md, clip.json            hook, title suggestion, provenance, the exact framing used

Framing (--layout auto): window inside a `zoom`-type window of the source zoom-plan.json → FACE
(9:16 crop centered on the measured face); otherwise → STACKED. Face position comes from the
source job's zoom-crop.json. NOTE: a facecam that is a small window inside a screen capture gets
upscaled ~3x in FACE layout — record the webcam as its own full-res file to get the crisp
full-frame look (see the doc). STACKED stays crisp either way.
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import gags as gagmod          # the comedy layer (presets/shorts/gags.py) — runs between the reframe and the captions
import camsync                 # Replay ↔ Cam pairing + audio alignment (presets/shorts/camsync.py)

CAM_FACE_MULT, CAM_MIN_CROP_H = 3.4, 760      # face crop from the camera file: ≈3.4× face height, never tighter than 760 px

MAX_SHORT = 60.0               # the creator's ceiling for a Short
FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]

OUT_W, OUT_H = 1080, 1920
STACK_FACE_H = 768            # facecam on top (40%), content below (60%) — the reference layout
STACK_CONTENT_H = OUT_H - STACK_FACE_H
PUNCH = 1.35                  # punch-in zoom factor on reaction beats
PUNCH_MIN, PUNCH_MAX = 1.4, 3.5
PUNCH_GAP = 2.0               # min seconds between punch-ins

HOOK_WORDS = {
    "insane": 2.0, "crazy": 1.6, "unbelievable": 2.0, "nightmare": 1.8, "terrifying": 1.8,
    "wow": 1.2, "holy": 1.4, "damn": 1.0, "wild": 1.4, "changer": 1.6, "future": 1.0,
    "guys": 0.8, "look": 1.2, "check": 1.2, "listen": 1.0, "wait": 1.2, "never": 0.8,
    "nobody": 1.2, "everyone": 0.8, "million": 1.4, "billion": 1.6, "free": 1.0, "secret": 1.4,
    "leaked": 1.8, "leak": 1.6, "banned": 1.6, "dead": 1.2, "broke": 1.2, "why": 0.8,
    "how": 0.6, "real": 0.8, "actually": 0.6, "literally": 0.8, "fuel": 1.0, "impressions": 1.0,
}
# "look at this" / "check this out" are the creator's verbal tics — worth something as a hook,
# but weighted low so they don't tie every window (and never make a title on their own).
HOOK_PHRASES = {"look at this": 0.9, "check this out": 0.9, "we need to talk": 2.5, "you need to": 1.6,
                "if you don't": 1.4, "nobody is talking": 2.4, "this is not clickbait": 2.5,
                "the future is": 1.6, "game changer": 1.8, "let me show you": 1.6, "nightmare fuel": 2.2}
TIC_WORDS = {"check", "look", "this", "out", "that", "guys", "then", "here", "at", "really", "think", "know", "how", "mean",
             "still", "just", "and", "but", "because", "actually", "literally", "like"}
HOOK_ADJ = {"insane", "crazy", "unbelievable", "wild", "wow", "holy", "damn", "terrifying", "pure", "complete"}
FILLER = {"um", "uh", "like", "so", "yeah", "okay", "ok", "alright", "all", "right", "anyways", "anyway",
          "i", "mean", "and", "but", "the", "a", "to", "of", "that", "this", "is", "it", "its", "it's"}


def log(msg):
    print(f"[clipper] {msg}", flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"[clipper] command failed: {' '.join(str(c) for c in cmd)}")
    return r


def ffprobe_dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True).stdout)


def ffprobe_wh(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def mmss(t):
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def parse_ts(s):
    s = s.strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    p = [float(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def clean(t):
    return t.lower().strip(".,?!;:\"'")


# ----------------------------------------------------------------------------- ranking
def load_words(job_dir, job):
    tj = os.path.join(job_dir, "outputs", f"{job}.transcript.json")
    if not os.path.isfile(tj):
        raise SystemExit(f"[clipper] no canonical transcript at {tj}")
    d = json.load(open(tj))
    return d, [w for w in d["words"] if w.get("type", "word") == "word" and w.get("text", "").strip()]


def boundaries(words, min_gap=0.45):
    idx = [0]
    for i in range(1, len(words)):
        if words[i]["start"] - words[i - 1]["end"] >= min_gap or words[i - 1]["text"].strip().endswith((".", "?", "!")):
            idx.append(i)
    return idx


def hook_strength(words):
    text = " ".join(clean(w["text"]) for w in words)
    s = sum(HOOK_WORDS.get(t, 0.0) for t in text.split())
    s += sum(v for ph, v in HOOK_PHRASES.items() if ph in text)
    if "?" in " ".join(w["text"] for w in words):
        s += 1.0
    if re.search(r"\b\d[\d,.]*\b|\$", text):
        s += 0.8
    return s


def score_window(words, i0, i1, target):
    ws = words[i0:i1]
    t0, t1 = ws[0]["start"], ws[-1]["end"]
    dur = t1 - t0
    hook = hook_strength([w for w in ws if w["start"] - t0 <= 4.0])
    density = len(ws) / max(dur, 1e-6)
    long_gaps = sum(1 for k in range(1, len(ws)) if ws[k]["start"] - ws[k - 1]["end"] >= 3.0)
    clean_end = (i1 >= len(words)) or (words[i1]["start"] - ws[-1]["end"] >= 0.6) or ws[-1]["text"].strip().endswith((".", "?", "!"))
    strong_start = (i0 == 0) or (words[i0]["start"] - words[i0 - 1]["end"] >= 0.6) or words[i0 - 1]["text"].strip().endswith((".", "?", "!"))
    s = hook + (1.5 if clean_end else 0.0) + (0.8 if strong_start else 0.0)
    if density < 1.6:
        s -= 3.0 * (1.6 - density)
    elif density > 2.2:
        s += 0.6
    s -= 1.5 * long_gaps
    s -= abs(dur - target) / 12.0
    return s, {"hook": round(hook, 2), "density": round(density, 2), "long_gaps": long_gaps, "clean_end": clean_end}


def rank(words, min_len, max_len, target, top):
    b = boundaries(words)
    cands = []
    for i0 in b:
        t0 = words[i0]["start"]
        best = None
        for i1 in [i for i in b if i > i0] + [len(words)]:
            dur = words[i1 - 1]["end"] - t0
            if dur < min_len:
                continue
            if dur > max_len:
                break
            s, det = score_window(words, i0, i1, target)
            if best is None or s > best[0]:
                best = (s, i0, i1, det)
        if best:
            cands.append(best)
    cands.sort(key=lambda c: -c[0])
    picked = []
    for s, i0, i1, det in cands:
        t0, t1 = words[i0]["start"], words[i1 - 1]["end"]
        if any(max(0.0, min(t1, p["end"]) - max(t0, p["start"])) > 0.4 * min(t1 - t0, p["end"] - p["start"]) for p in picked):
            continue
        picked.append({"rank": len(picked) + 1, "start": round(max(0.0, t0 - 0.05), 3), "end": round(t1 + 0.35, 3),
                       "score": round(s, 2), **det,
                       "hook_line": " ".join(w["text"] for w in words[i0:min(i1, i0 + 12)]),
                       "title_suggestion": suggest_title(words[i0:i1])})
        if len(picked) >= top:
            break
    return picked


def suggest_title(words):
    """A 2–4 word punch from the strongest stretch of the first ~8 s, Title Cased."""
    head = [clean(w["text"]) for w in words if w["start"] - words[0]["start"] <= 8.0]
    toks = [t for t in head if t]
    if not toks:
        return ""
    # 1) a signature phrase wins outright, with one modifier in front if there is one
    #    ("pure nightmare fuel", "complete game changer")
    head_text = " ".join(toks)
    for ph in ("nightmare fuel", "game changer", "we need to talk", "this is not clickbait", "nobody is talking"):
        k = head_text.find(ph)
        if k >= 0:
            before = head_text[:k].split()
            mod = before[-1] if before and before[-1] not in FILLER | TIC_WORDS else None   # "pure", "complete"
            return " ".join(w.capitalize() for w in ([mod] if mod else []) + ph.split())
    # 2) otherwise the best 2–4 word window: must carry a CONTENT word (not a tic/filler/bare
    #    adjective), must not start or end on a tic/filler, no repeats
    best, best_s = None, -9.0
    for n in (3, 4, 2):
        for i in range(0, max(1, len(toks) - n + 1)):
            win = toks[i:i + n]
            if len(set(win)) < len(win):
                continue
            if win[0] in FILLER | TIC_WORDS - {"nobody", "why", "how"} or win[-1] in FILLER | TIC_WORDS:
                continue
            content = [t for t in win if t not in FILLER and t not in TIC_WORDS and t not in HOOK_ADJ]
            if not content:
                continue
            s = sum(HOOK_WORDS.get(t, 0.0) for t in win) + 0.6 * len(content)
            s -= 0.4 * sum(1 for t in win if t in FILLER) + 0.5 * sum(1 for t in win if t in TIC_WORDS)
            if s > best_s + (0.15 if n == 3 else 0.0):
                best_s, best = s, win
    if best is None:
        strong = [t for t in toks if t not in FILLER and t not in TIC_WORDS]
        best = strong[:3] or toks[:3]
    return " ".join(w.upper() if re.fullmatch(r"[a-z]{1,4}\d*", w) and w in ("ai", "gta", "dlss", "gpu", "ps5") else w.capitalize() for w in best)


# ----------------------------------------------------------------------------- framing
def load_face(job_dir):
    zc = os.path.join(job_dir, "zoom-crop.json")
    if os.path.isfile(zc):
        f = json.load(open(zc)).get("face", {})
        if "cx" in f:
            return {"cx": f["cx"], "cy": f["cy"], "w": f.get("w", 150), "h": f.get("h", 200)}
    return None


def layout_for(job_dir, t_mid, requested):
    if requested in ("face", "stacked", "intercut"):
        return requested
    zp = os.path.join(job_dir, "zoom-plan.json")
    if os.path.isfile(zp):
        for w in json.load(open(zp)).get("windows", []):
            if w.get("start", 0) <= t_mid <= w.get("end", 0):
                return "face" if w.get("type", "zoom") == "zoom" else "stacked"
    return "face"


def _clamp(v, lo, hi):
    return int(min(max(v, lo), hi))


GAME_ASPECT = 1.2             # intercut layout: the game is shown as a 6:5 window (not the tight 9:16 column —
                              # "the gun looked too zoomed in") on a blurred cover of itself


def default_content_rect(src_w, src_h, face, aspect=None):
    """Widest content crop at the given aspect (default: the stacked content box's), nudged away
    from the facecam overlay."""
    cx = face["cx"] if face else src_w // 2
    fw = face["w"] if face else 150
    cont_w = min(src_w, int(round(src_h * (aspect or OUT_W / STACK_CONTENT_H))))
    tx = (src_w - cont_w) // 2
    est_l, est_r = cx - 2 * fw, cx + 2 * fw
    if tx < est_r and tx + cont_w > est_l:
        tx = _clamp(est_l - cont_w, 0, src_w - cont_w) if cx > src_w / 2 else _clamp(est_r, 0, src_w - cont_w)
    return (tx, 0, cont_w, src_h)


def detect_content_roi(raw, src_w, src_h, face, work):
    """The region of the screen that actually MOVES during the clip — on a reaction video that is the
    embedded video the creator is watching. Frame-differences ~10 low-res samples with the facecam
    masked out, takes the motion bounding box, fits it to the content box's aspect. None = nothing
    moves (a static page) → caller falls back to the wide default."""
    from PIL import Image
    lw, lh = 256, 144
    dur = ffprobe_dur(raw)
    os.makedirs(work, exist_ok=True)
    frames = []
    for i in range(10):
        t = dur * (i + 0.5) / 10
        p = os.path.join(work, f"roi_{i}.png")
        subprocess.run(FFMPEG + ["-ss", f"{t:.3f}", "-i", raw, "-frames:v", "1",
                                 "-vf", f"scale={lw}:{lh},format=gray", p], capture_output=True)
        if os.path.isfile(p):
            img = Image.open(p)
            g = getattr(img, "get_flattened_data", None) or img.getdata
            frames.append(list(g()))
    if len(frames) < 3:
        return None
    sx, sy = lw / src_w, lh / src_h
    if face:
        mx0, mx1 = int((face["cx"] - 3 * face["w"]) * sx), int((face["cx"] + 3 * face["w"]) * sx)
        my0, my1 = int((face["cy"] - 2 * face["h"]) * sy), int((face["cy"] + 4 * face["h"]) * sy)
    else:
        mx0 = mx1 = my0 = my1 = -1
    motion = [0] * (lw * lh)
    for a, b in zip(frames, frames[1:]):
        for k in range(lw * lh):
            d = abs(a[k] - b[k])
            if d > 12:
                motion[k] += 1
    # A playing video changes in nearly EVERY frame pair; a page scroll changes everything in a
    # FEW pairs. So first look for SUSTAINED motion (≥60% of pairs) — that is the embedded player.
    # Only if nothing is sustained fall back to "any motion at all".
    n_pairs = len(frames) - 1
    def spans_for(threshold):
        cols, rows = [0] * lw, [0] * lh
        total = 0
        for y in range(lh):
            for x in range(lw):
                if mx0 <= x <= mx1 and my0 <= y <= my1:
                    continue
                v = motion[y * lw + x]
                if v >= threshold:
                    cols[x] += 1; rows[y] += 1; total += 1
        return cols, rows, total
    cols, rows, total = spans_for(max(2, int(0.6 * n_pairs)))
    if total < 0.002 * lw * lh:
        cols, rows, total = spans_for(1)
        if total < 0.004 * lw * lh:
            return None                                # effectively static
    def span(arr):
        m = max(arr)
        idx = [i for i, v in enumerate(arr) if v >= 0.25 * m]
        return (min(idx), max(idx)) if idx else (0, len(arr) - 1)
    (x0, x1), (y0, y1) = span(cols), span(rows)
    # back to source pixels, with a margin, then a minimum size so a tiny player never becomes a wall
    X0, X1 = x0 / sx, (x1 + 1) / sx
    Y0, Y1 = y0 / sy, (y1 + 1) / sy
    w, h = X1 - X0, Y1 - Y0
    cxr, cyr = (X0 + X1) / 2, (Y0 + Y1) / 2
    w, h = max(w * 1.12, 0.38 * src_w), max(h * 1.12, 0.38 * src_h)
    aspect = OUT_W / STACK_CONTENT_H
    if w / h > aspect:
        h = w / aspect
    else:
        w = h * aspect
    w, h = min(w, src_w), min(h, src_h)
    if w / h > aspect:
        w = h * aspect
    else:
        h = w / aspect
    x = _clamp(cxr - w / 2, 0, src_w - w)
    y = _clamp(cyr - h / 2, 0, src_h - h)
    return (int(x), int(y), int(w), int(h))


def cam_bg_key(cam):
    """What the Source Record filter painted behind the keyed-out creator: sampled from a corner of the
    first cam frame. Green (#00FF00) keys cleanly; black is keyed only very tightly (his headset and
    dark shirt are near-black) and is best left as a look."""
    if "bg" in cam:
        return cam["bg"]
    r = subprocess.run(FFMPEG + ["-i", cam["path"], "-frames:v", "1", "-vf", "crop=40:40:8:8,scale=1:1", "-f", "rawvideo",
                                 "-pix_fmt", "rgb24", "-"], capture_output=True)
    px = r.stdout[:3] if len(r.stdout) >= 3 else b"\x00\x00\x00"
    R, G, B = px[0], px[1], px[2]
    if G > 150 and R < 100 and B < 100:
        cam["bg"] = ("green", "chromakey=0x00FF00:similarity=0.18:blend=0.06")
    elif max(R, G, B) < 24:
        cam["bg"] = ("black", "colorkey=0x000000:similarity=0.06:blend=0.04")
    else:
        cam["bg"] = ("none", "")
    return cam["bg"]


def cam_face_filter(cam, zoom=1.0, bg="keep"):
    """FACE segment from the camera file (--face-source): a 9:16 crop of the untouched camera frame
    around the measured face — every pixel native — scaled to 1080×1920. zoom > 1 = a punch-in (a
    tighter crop of the same frame). bg="keep": the background as recorded (black or green paint);
    bg="game": key the paint out and put the composite's game frame, blurred and darkened, behind him
    (needs the second input [1:v] = the composite at the same instant)."""
    f = cam["face"]
    ch = int(round(_clamp(f["h"] * CAM_FACE_MULT, CAM_MIN_CROP_H, cam["h"]) / zoom))
    cw = int(round(ch * 9 / 16))
    x = _clamp(f["cx"] - cw // 2, 0, cam["w"] - cw)
    y = _clamp(f["cy"] - int(0.42 * ch), 0, cam["h"] - ch)
    crop = f"crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos"
    if bg != "game":
        return crop
    kind, key = cam_bg_key(cam)
    if not key:
        return crop
    # [0:v] = cam, [1:v] = composite (game). Blurred cover of the game, the keyed creator on top.
    return (f"[1:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
            f"boxblur=28:2,eq=brightness=-0.22:saturation=0.85[bg];"
            f"[0:v]{crop},format=rgba,{key}[fg];[bg][fg]overlay=0:0")


def load_cam(job_dir, face_source, t0, offset_override=None):
    """The camera twin for this clip: auto = the source job's cam.json (written by scan-replays /
    camsync), none = off, or an explicit file. Returns dict(path, w, h, dur, face, t0) where t0 maps
    clip time 0 onto the cam file, or None."""
    if face_source == "none":
        return None
    cam = None
    cj = os.path.join(job_dir, "cam.json")
    if face_source == "auto":
        if os.path.isfile(cj):
            cam = json.load(open(cj))
    else:
        cam = {"path": os.path.abspath(face_source)}
        cam["w"], cam["h"] = ffprobe_wh(cam["path"])
        cam["dur"] = ffprobe_dur(cam["path"])
        if os.path.isfile(cj) and json.load(open(cj)).get("path") == cam["path"]:
            cam.update({k: v for k, v in json.load(open(cj)).items() if k in ("offset", "face")})
    if not cam or not os.path.isfile(cam.get("path", "")):
        return None
    if offset_override is not None:
        cam["offset"] = offset_override
    if "offset" not in cam:
        base = os.path.join(job_dir, "outputs", os.path.basename(job_dir.rstrip("/")) + ".mp4")
        cam.update(camsync.align(base, cam["path"]))
    if "face" not in cam:
        cam["face"] = measure_cam_face(job_dir, cam["path"])
    cam["t0"] = cam["offset"] + t0
    return cam


def measure_cam_face(job_dir, cam_path):
    """zoom-crop.py writes <parent of the video's folder>/zoom-crop.json — so the cam is measured through
    projects/<job>/cam/outputs/<name> and the result lands in projects/<job>/cam/zoom-crop.json."""
    cdir = os.path.join(job_dir, "cam", "outputs")
    os.makedirs(cdir, exist_ok=True)
    link = os.path.join(cdir, os.path.basename(job_dir.rstrip("/")) + "-cam.mp4")
    if os.path.islink(link) or os.path.exists(link):
        os.remove(link)
    os.symlink(cam_path, link)
    subprocess.run([os.path.expanduser("~/.local/bin/uv"), "run", os.path.join(REPO, "workflows", "zoom-crop.py"), link],
                   capture_output=True, text=True, cwd=REPO)
    zc = os.path.join(job_dir, "cam", "zoom-crop.json")
    if os.path.isfile(zc):
        f = json.load(open(zc)).get("face", {})
        if "cx" in f:
            return {"cx": f["cx"], "cy": f["cy"], "w": f.get("w", 200), "h": f.get("h", 260)}
    w, h = ffprobe_wh(cam_path)
    log("  cam face not found — centring the camera frame")
    return {"cx": w // 2, "cy": h // 2, "w": 200, "h": 260}


def game_filter(src_w, src_h, rect, czoom=None):
    """INTERCUT layout, game segment: a 6:5 window of the game (rect) centred on a blurred, darkened
    cover-crop of the same frame — the whole game view at a sane size, no gun-in-your-face column.
    czoom = an authored zoom into the window (a countdown), as a sub-rect."""
    tx, ty, cw_, ch_ = rect
    if czoom and czoom.get("f", 1.0) > 1.0:
        f = czoom["f"]
        zw, zh = int(round(cw_ / f)), int(round(ch_ / f))
        zx = _clamp(tx + int(czoom.get("cx", 0.5) * cw_) - zw // 2, tx, tx + cw_ - zw)
        zy = _clamp(ty + int(czoom.get("cy", 0.5) * ch_) - zh // 2, ty, ty + ch_ - zh)
        tx, ty, cw_, ch_ = zx, zy, zw, zh
    fh = int(round(OUT_W * ch_ / cw_ / 2)) * 2
    bw = int(round(src_h * OUT_W / OUT_H))
    bx = _clamp(tx + cw_ // 2 - bw // 2, 0, src_w - bw)
    return (f"split=2[bg][fg];"
            f"[bg]crop={bw}:{src_h}:{bx}:0,scale={OUT_W}:{OUT_H}:flags=bicubic,boxblur=24:2,eq=brightness=-0.2[b];"
            f"[fg]crop={cw_}:{ch_}:{tx}:{ty},scale={OUT_W}:{fh}:flags=lanczos[f];"
            f"[b][f]overlay=0:{(OUT_H - fh) // 2}")


def reframe_filter(layout, src_w, src_h, face, zoom=1.0, content_rect=None, czoom=None, mode="face"):
    if layout == "intercut":
        if mode == "game":
            return game_filter(src_w, src_h, content_rect or default_content_rect(src_w, src_h, face, GAME_ASPECT), czoom)
        layout = "face"                 # a face segment of the intercut = the full-frame face crop
    """ffmpeg filter for one segment. zoom>1 = punch-in on the face (the content box never zooms).
    Framing is deliberately TIGHT — the reference look is the creator filling the frame — even
    though a facecam that is a small window inside a screen capture gets upscaled for it."""
    cx = face["cx"] if face else src_w // 2
    cy = face["cy"] if face else src_h // 2
    fh = face["h"] if face else 200
    if layout == "face":
        ch = int(round(_clamp(fh * 3.2, 540, src_h) / zoom))    # face ≈ 30% of frame height
        cw = int(round(ch * 9 / 16))
        x = _clamp(cx - cw // 2, 0, src_w - cw)
        y = _clamp(cy - int(0.42 * ch), 0, src_h - ch)
        return f"crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos"
    # STACKED — facecam on top, screen content below (the reference layout)
    fh_box = int(round(_clamp(fh * 2.0, 320, src_h) / zoom))    # face ≈ 50% of its box
    fw_box = min(src_w, int(round(fh_box * OUT_W / STACK_FACE_H)))
    fx = _clamp(cx - fw_box // 2, 0, src_w - fw_box)
    fy = _clamp(cy - int(0.45 * fh_box), 0, src_h - fh_box)
    tx, ty, cw_, ch_ = content_rect or default_content_rect(src_w, src_h, face)
    if czoom and czoom.get("f", 1.0) > 1.0:
        # an authored zoom INTO the content box (a countdown, a kill feed): a sub-rect of the content
        # crop, centred at (cx, cy) as fractions of the box, kept inside it
        f = czoom["f"]
        zw, zh = int(round(cw_ / f)), int(round(ch_ / f))
        zx = _clamp(tx + int(czoom.get("cx", 0.5) * cw_) - zw // 2, tx, tx + cw_ - zw)
        zy = _clamp(ty + int(czoom.get("cy", 0.5) * ch_) - zh // 2, ty, ty + ch_ - zh)
        tx, ty, cw_, ch_ = zx, zy, zw, zh
    return (f"split=2[f][c];"
            f"[f]crop={fw_box}:{fh_box}:{fx}:{fy},scale={OUT_W}:{STACK_FACE_H}:flags=lanczos[face];"
            f"[c]crop={cw_}:{ch_}:{tx}:{ty},scale={OUT_W}:{STACK_CONTENT_H}:flags=lanczos[content];"
            f"[face][content]vstack")


def motion_events(raw, dur, face=None, max_events=3, min_gap=3.0):
    """Bursts of violent motion in the GAME region — a fall, a death, an explosion — as
    [(start, end, peak)]. ffmpeg's scene score never fires on a first-person camera whip (a real fall
    measured 0.2), but the mean frame-to-frame difference does: gameplay idles at ~10–20 on a 96×54
    grey thumbnail, a fall runs 40–60 for a second or more, lying dead reads ~1. A burst = the
    series above max(2×median, median+15, 25) for ≥0.75 s (single-sample dips allowed). These are
    the moments the GAME must be on screen even while he is talking."""
    sw, sh = ffprobe_wh(raw)
    # keep the facecam out of the measurement: cut the frame at the cam's inner edge
    if face and face["cx"] > sw / 2:
        crop = f"crop={max(200, int(face['cx'] - 2.2 * face['w']))}:{sh}:0:0"
    elif face:
        x0 = min(sw - 200, int(face["cx"] + 2.2 * face["w"]))
        crop = f"crop={sw - x0}:{sh}:{x0}:0"
    else:
        crop = f"crop={sw}:{sh}:0:0"
    fps = 4
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", raw, "-vf",
                        f"{crop},fps={fps},scale=96:54,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = 96 * 54
    frames = [r[i * n:(i + 1) * n] for i in range(len(r) // n)]
    if len(frames) < 8:
        return []
    diffs = [sum(abs(a - b) for a, b in zip(frames[i], frames[i - 1])) / n for i in range(1, len(frames))]
    med = sorted(diffs)[len(diffs) // 2]
    thr = max(2.0 * med, med + 15.0, 25.0)
    bursts, i = [], 0
    while i < len(diffs):
        if diffs[i] >= thr:
            j, dip = i, 0
            while j + 1 < len(diffs) and (diffs[j + 1] >= thr or dip == 0):
                dip = 0 if diffs[j + 1] >= thr else dip + 1
                j += 1
            end_i = j if diffs[j] >= thr else j - 1
            if (end_i - i + 1) / fps >= 0.75:
                # rank by ENERGY (motion × time): a fall is sustained, a camera whip is one spike —
                # by peak alone three whips outscored the actual fall on the first real clip
                bursts.append(((i + 1) / fps, (end_i + 2) / fps, sum(diffs[i:end_i + 1]), max(diffs[i:end_i + 1])))
            i = j + 1
        else:
            i += 1
    # bursts less than 1.5 s apart are one event (looking over the edge, then the drop) — on the first
    # real clip the 3 s spacing rule let the look-down block the fall that followed it
    merged = []
    for a, b, energy, pk in sorted(bursts):
        if merged and a - merged[-1][1] < 1.5:
            pa, pb, pe, pp = merged[-1]
            merged[-1] = (pa, b, pe + energy, max(pp, pk))
        else:
            merged.append((a, b, energy, pk))
    picked = []
    for a, b, energy, pk in sorted(merged, key=lambda x: -x[2]):
        if 1.0 <= a <= dur - 1.0 and all(a >= p[1] + min_gap or b <= p[0] - min_gap for p in picked):
            picked.append((round(a, 3), round(min(b, dur), 3), round(energy, 0)))
        if len(picked) >= max_events:
            break
    return sorted(picked)


def auto_game_windows(words, dur, events=()):
    """INTERCUT layout, automatic: the game is full-frame while he is watching / playing (no speech),
    the face is full-frame while he reacts. Built from the transcript: words closer than 0.8 s form a
    speech run; a run gets the face from 0.15 s before its first word to 0.4 s after its last (at least
    1.2 s), tiny mumbles under 0.5 s with nothing in them stay on the game; a game gap shorter than
    1.0 s between two face runs is absorbed into the face (no flicker). After the last word the face
    stays (the reaction / the walk-off is on camera). A motion EVENT (see motion_events — a fall, a
    death) carves a game window out of a face run: 0.3 s before the burst to 0.8 s after it ends, so
    the thing that happened is on screen and the face comes back for the reaction. Returns [(a, b)]."""
    if not words:
        return [(0.0, dur)]
    runs, cur = [], [words[0]]
    for w in words[1:]:
        if w["start"] - cur[-1]["end"] < 0.8:
            cur.append(w)
        else:
            runs.append(cur)
            cur = [w]
    runs.append(cur)
    face = []
    for r in runs:
        a, b = r[0]["start"], r[-1]["end"]
        strong = any(gagmod.TRIGGERS.get(clean(w["text"]), (0, None))[0] >= 0.7 or w["text"].strip().endswith(("?", "!"))
                     for w in r)
        if b - a < 0.5 and not strong and len(r) <= 2:
            continue                                         # "uh" / "yeah" while playing → stay on the game
        a, b = max(0.0, a - 0.15), min(dur, b + 0.4)
        if b - a < 1.2:
            b = min(dur, a + 1.2)
        if face and a - face[-1][1] < 1.0:
            face[-1] = (face[-1][0], b)                      # absorb a sub-1 s game gap
        else:
            face.append((a, b))
    if face:
        face[-1] = (face[-1][0], dur)                        # the reaction after the last line stays on camera
    # motion events carve the game back out of a face run — the fall must be seen, the reaction follows
    for ev in events:
        ga, gb = max(0.0, ev[0] - 0.3), min(dur, ev[1] + 0.8)
        if gb - ga < 1.2:
            gb = min(dur, ga + 1.2)
        carved = []
        for a, b in face:
            if b <= ga or a >= gb:
                carved.append((a, b))
                continue
            if ga - a >= 0.8:
                carved.append((a, ga))
            if b - gb >= 0.8:
                carved.append((gb, b))
        face = carved
    game, t = [], 0.0
    for a, b in face:
        if a - t >= 0.6:
            game.append((round(t, 3), round(a, 3)))
        t = b
    if dur - t >= 0.6:
        game.append((round(t, 3), round(dur, 3)))
    return game


def plan_punchins(words, dur):
    """Reaction-beat punch-ins (clip-local seconds): start on a hook word or a fresh sentence
    after a pause, hold to the next pause (1.4–3.5 s), at least 2 s apart, ≤ ~45% of the clip."""
    beats = []
    for k, w in enumerate(words):
        t = w["start"]
        if t < 0.6 or t > dur - PUNCH_MIN:
            continue
        pause = k > 0 and (t - words[k - 1]["end"] >= 0.6)
        strong = HOOK_WORDS.get(clean(w["text"]), 0.0) >= 1.2
        if not (pause or strong):
            continue
        if beats and t - beats[-1][1] < PUNCH_GAP:
            continue
        end = t + PUNCH_MAX
        for j in range(k + 1, len(words)):
            if words[j]["start"] - words[j - 1]["end"] >= 0.4 and words[j - 1]["end"] - t >= PUNCH_MIN:
                end = min(end, words[j - 1]["end"] + 0.15)
                break
        end = min(end, dur)
        if end - t >= PUNCH_MIN:
            beats.append((round(t, 3), round(end, 3)))
    while sum(e - s for s, e in beats) > 0.45 * dur and beats:
        beats.pop()
    return beats


def atempo_chain(rate):
    """ffmpeg atempo takes 0.5-100 per stage; chain stages for slower than half speed."""
    parts = []
    while rate < 0.5:
        parts.append("atempo=0.5")
        rate /= 0.5
    parts.append(f"atempo={rate:.4f}")
    return ",".join(parts)


def render_reframed(raw, out, layout, face, punchins, dur, work, content_mode="auto", content_override=None, czooms=(),
                    game_windows=(), slow=(), cam=None, face_bg="keep"):
    """Segment-based render (the punch-in-zoom preset's own pattern): static crop per segment,
    matching encode params, stream-copy concat, original audio muxed back.
    punchins = [(start, end, factor)] face punch-ins; czooms = [{a, b, f, cx, cy}] zooms into the content box;
    game_windows = [(a, b)] — intercut layout: the game is full-frame inside these, the face everywhere else;
    slow = [(a, b, factor)] — slow motion: the video is stretched by factor (setpts) and the audio slowed the same
    (atempo, so the voice drops with it — half the joke); everything downstream is remapped by the caller."""
    sw, sh = ffprobe_wh(raw)
    content_rect = None
    if layout == "stacked":
        if content_override:
            content_rect = content_override
        elif content_mode == "auto":
            content_rect = detect_content_roi(raw, sw, sh, face, os.path.join(work, "roi"))
        log(f"  content box: {'ROI ' + str(content_rect) if content_rect else 'wide default (no motion found / --no-roi)'}")
    elif layout == "intercut":
        content_rect = content_override or default_content_rect(sw, sh, face, GAME_ASPECT)
        log(f"  game window: {content_rect} (6:5 on a blurred cover), face everywhere else; "
            f"game for {', '.join(f'{a:.1f}-{b:.1f}' for a, b in game_windows) or 'nothing (no --cut-to-game)'}")
    edges = sorted({0.0, dur} | {t for s, e, _ in punchins for t in (s, e)} | {t for z in czooms for t in (z["a"], z["b"])}
                   | {t for g in game_windows for t in g} | {t for s in slow for t in (s[0], s[1])})
    segs = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 0.05:
            continue
        fz = next((f for s, e, f in punchins if s <= a < e), 1.0)
        cz = next((z for z in czooms if z["a"] <= a < z["b"]), None)
        mode = "game" if any(s <= a < e for s, e in game_windows) else "face"
        sp = next((f for s, e, f in slow if s <= a < e), 1.0)
        segs.append((a, b, fz, cz, mode, sp))
    os.makedirs(work, exist_ok=True)
    pieces = []
    cam_used = 0
    for i, (a, b, fz, cz, mode, sp) in enumerate(segs):
        src, seek = raw, a
        # a FACE segment comes from the camera file when there is one and it covers this stretch
        extra = []
        if cam and mode == "face" and layout in ("face", "intercut") and cam["t0"] + a >= 0 and cam["t0"] + b <= cam["dur"] + 0.05:
            vf = cam_face_filter(cam, fz, face_bg)
            src, seek = cam["path"], cam["t0"] + a
            if vf.startswith("["):                                 # game behind the face: the composite rides along as [1:v]
                extra = ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", raw]
            cam_used += 1
        else:
            vf = reframe_filter(layout, sw, sh, face, fz, content_rect, cz, mode)
        if sp != 1.0:
            vf += f",setpts={sp:.4f}*PTS"           # slow motion: stretch the timestamps of this segment
        p = os.path.join(work, f"seg{i:03d}.mp4")
        # seek on the INPUT side: output-side -ss compares timestamps AFTER the filter, and a slow-motion
        # setpts doubles them, so a seek to 22 s admitted frames from 11 s (wrong footage inside the fall)
        run(FFMPEG + ["-ss", f"{seek:.3f}", "-t", f"{b - a:.3f}", "-i", src, *extra, "-an",
                      "-filter_complex" if ("split=" in vf or vf.startswith("[")) else "-vf", vf, "-r", "60", *ENC, p])
        pieces.append(p)
    if cam:
        log(f"  face source: {os.path.basename(cam['path'])} for {cam_used} face segment(s) (offset {cam['t0']:.2f}s)"
            + (f", background: {cam_bg_key(cam)[0]} paint keyed → game behind him" if face_bg == "game" else ", background as recorded"))
    lst = os.path.join(work, "concat.txt")
    with open(lst, "w") as f:
        for p in pieces:
            f.write(f"file '{p}'\n")
    vonly = os.path.join(work, "video_only.mp4")
    run(FFMPEG + ["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vonly])
    if slow:
        # the audio follows the slow motion: normal / slowed (atempo) / normal, concatenated once
        fc, labels, t, k = [], [], 0.0, 0
        for a, b, f in sorted(slow):
            if a - t > 0.01:
                fc.append(f"[0:a]atrim=start={t:.3f}:end={a:.3f},asetpts=PTS-STARTPTS[q{k}]"); labels.append(f"[q{k}]"); k += 1
            fc.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{atempo_chain(1.0 / f)}[q{k}]"); labels.append(f"[q{k}]"); k += 1
            t = b
        if dur - t > 0.01:
            fc.append(f"[0:a]atrim=start={t:.3f},asetpts=PTS-STARTPTS[q{k}]"); labels.append(f"[q{k}]"); k += 1
        fc.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
        run(FFMPEG + ["-i", raw, "-i", vonly, "-filter_complex", ";".join(fc), "-map", "1:v", "-map", "[aout]",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out])
    else:
        run(FFMPEG + ["-i", vonly, "-i", raw, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
                      "-shortest", "-movflags", "+faststart", out])
    return reframe_filter(layout, sw, sh, face, 1.0, content_rect), content_rect


def make_remap(slow):
    """Original clip time → time after the slow-motion stretches (for everything placed downstream)."""
    slow = sorted(slow)
    def remap(t):
        shift = 0.0
        for a, b, f in slow:
            if t <= a:
                return round(t + shift, 3)
            if t <= b:
                return round(shift + a + (t - a) * f, 3)
            shift += (f - 1.0) * (b - a)
        return round(t + shift, 3)
    return remap


# ----------------------------------------------------------------------------- building a clip
def build_clip(job, job_dir, tdoc, words, n, t0, t1, layout_req, hook_text, captions, finish, face,
               content_mode="auto", content_override=None, gags_level="medium", style="reference", text_pops=None,
               pin=None, authored=None, name=None, face_source="auto", face_offset=None, face_bg="keep"):
    authored = authored or {}
    clip = name or f"{job}-short-{n:02d}"          # --name: the clip job named after its content
    cdir = os.path.join(REPO, "projects", clip)
    for sub in ("raw", "outputs", "assemble_work"):
        os.makedirs(os.path.join(cdir, sub), exist_ok=True)
    base = os.path.join(job_dir, "outputs", f"{job}.mp4")
    if not os.path.isfile(base):
        raise SystemExit(f"[clipper] no clean base cut at {base}")
    t0, t1 = max(0.0, t0), min(ffprobe_dur(base), t1)
    if t1 - t0 > MAX_SHORT:
        log(f"window {mmss(t0)}–{mmss(t1)} is {t1 - t0:.0f}s — capping at {MAX_SHORT:.0f}s (the ceiling for a Short)")
        t1 = t0 + MAX_SHORT
    dur = t1 - t0

    raw = os.path.join(cdir, "raw", f"{clip}.mp4")
    run(FFMPEG + ["-i", base, "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", *ENC,
                  "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", raw])
    dur = ffprobe_dur(raw)

    in_clip = [w for w in words if w["end"] > t0 + 0.02 and w["start"] < t1 - 0.02]
    rebased = [{**w, "start": round(max(0.0, w["start"] - t0), 3), "end": round(min(dur, w["end"] - t0), 3)} for w in in_clip]
    with open(os.path.join(cdir, "outputs", f"{clip}.transcript.json"), "w") as f:
        json.dump({"text": " ".join(w["text"] for w in in_clip), "language_code": tdoc.get("language_code", "en"),
                   "engine": f"{tdoc.get('engine', 'whisperx')} (sliced {mmss(t0)}-{mmss(t1)} from {job} by clipper)",
                   "words": rebased}, f, indent=1)

    layout = layout_for(job_dir, (t0 + t1) / 2, layout_req)
    # face punch-ins: automatic reaction beats, replaced wherever the editor authored one (--face-zoom)
    fz = [(z["a"], z["b"], z["f"]) for z in authored.get("fzooms", [])]
    punchins = sorted([(s, e, PUNCH) for s, e in plan_punchins(rebased, dur)
                       if not any(s < b and e > a for a, b, _ in fz)] + fz)
    czooms = authored.get("czooms", [])
    if layout == "intercut" and not authored.get("game"):
        events = motion_events(raw, dur, face)
        authored["game"] = auto_game_windows(rebased, dur, events)
        log(f"  motion events: {', '.join(f'{a:.1f}-{b:.1f}s (energy {e:.0f})' for a, b, e in events) or 'none'}")
        log(f"  auto game windows: {', '.join(f'{a:.1f}-{b:.1f}' for a, b in authored['game']) or 'none (he talks throughout)'}")
    out_base = os.path.join(cdir, "outputs", f"{clip}.mp4")
    # with the comedy layer on, the reframe is kept as .reframed.mp4 and outputs/<clip>.mp4 (what the
    # caption builder reads) is the gagged version
    reframed = os.path.join(cdir, "outputs", f"{clip}.reframed.mp4") if gags_level != "off" or authored.get("fixed") else out_base
    slow = authored.get("slow", [])
    cam = load_cam(job_dir, face_source, t0, face_offset) if layout in ("face", "intercut") else None
    base_vf, content_rect = render_reframed(raw, reframed, layout, face, punchins, dur,
                                            os.path.join(cdir, "assemble_work", "reframe"), content_mode, content_override, czooms,
                                            authored.get("game", []), slow, cam, face_bg)
    if slow:
        # the timeline stretched: words, authored gags and sounds all move with it
        rm = make_remap(slow)
        rebased = [{**w, "start": rm(w["start"]), "end": rm(w["end"])} for w in rebased]
        for g in authored.get("fixed", []):
            g["t"] = rm(g["t"])
            if g.get("text"):
                g["text"] = (g["text"][0], rm(g["text"][1]), rm(g["text"][2]))
            if g.get("meme"):
                g["meme"] = (g["meme"][0], rm(g["meme"][1]), rm(g["meme"][2]))
        authored["sfx"] = [(tag, rm(t)) for tag, t in authored.get("sfx", [])]
        dur = ffprobe_dur(reframed)
        with open(os.path.join(cdir, "outputs", f"{clip}.transcript.json"), "w") as f:
            json.dump({"text": " ".join(w["text"] for w in in_clip), "language_code": tdoc.get("language_code", "en"),
                       "engine": f"{tdoc.get('engine', 'whisperx')} (sliced {mmss(t0)}-{mmss(t1)} from {job} by clipper; "
                                 f"{len(slow)} slow-motion window(s))", "words": rebased}, f, indent=1)
        log(f"  slow motion: {', '.join(f'{a:.1f}-{b:.1f} x{f:g}' for a, b, f in slow)} → clip now {dur:.1f}s")
    gmeta = None
    if gags_level != "off" or authored.get("fixed") or authored.get("sfx") or authored.get("loudness") is not None:
        gmeta = gagmod.run_gags(cdir, reframed, out_base, rebased, layout, punchins, gags_level, dur,
                                style=style, text_pops=text_pops, pin=pin, fixed_gags=authored.get("fixed", []),
                                no_memes=authored.get("no_memes", False), extra_sfx=authored.get("sfx", []),
                                loudness=authored.get("loudness"), sfx_trim=authored.get("sfx_trim", 0.0))
        if gmeta["time_map"]:                       # a freeze-frame inserted time → captions must follow
            rebased = gagmod.shift_words(rebased, gmeta["time_map"])
            with open(os.path.join(cdir, "outputs", f"{clip}.transcript.json"), "w") as f:
                json.dump({"text": " ".join(w["text"] for w in in_clip), "language_code": tdoc.get("language_code", "en"),
                           "engine": f"{tdoc.get('engine', 'whisperx')} (sliced {mmss(t0)}-{mmss(t1)} from {job} by clipper; "
                                     f"shifted for {len(gmeta['time_map'])} freeze-frame(s))", "words": rebased}, f, indent=1)
        dur = ffprobe_dur(out_base)

    title = suggest_title(in_clip)
    meta = {"clip": clip, "source_job": job, "start": round(t0, 3), "end": round(t1, 3), "duration": round(dur, 3),
            "layout": layout, "captions": captions, "hook_text": hook_text or "", "title_suggestion": title,
            "punch_ins": punchins, "content_rect": content_rect, "reframe_filter": base_vf,
            "gags": gags_level, "style": style, "pin": pin or "", "authored": authored.get("spec", {}), "content_zooms": czooms,
            "game_windows": authored.get("game", []),
            "face_source": cam["path"] if cam else "", "cam_offset": round(cam["t0"], 3) if cam else None, "face_bg": face_bg,
            "gag_list": [f"{g['t']:.2f}s {g['type']}" + (f' "{g["text"][0]}"' if g.get("text") else "")
                         + (f" {os.path.basename(g['meme'][0])}" if g.get("meme") else "")
                         + (f" ends on {os.path.basename(g['tail'][0])}" if g.get("tail") else "")
                         for g in gmeta["gags"]] if gmeta else [],
            "time_map": gmeta["time_map"] if gmeta else []}
    json.dump(meta, open(os.path.join(cdir, "clip.json"), "w"), indent=2)
    with open(os.path.join(cdir, "intent.md"), "w") as f:
        f.write(f"# {clip}\n\nTitle suggestion: {title}\n\nSource: {job} {mmss(t0)}–{mmss(t1)} ({dur:.1f}s), layout {layout}, "
                f"captions {captions}, {len(punchins)} punch-in(s), gags {gags_level}"
                f"{' (' + str(len(gmeta['gags'])) + ')' if gmeta else ''}.\nCold open — no hook card.\n")
    log(f"{clip}: {mmss(t0)}–{mmss(t1)} ({dur:.1f}s) layout={layout} captions={captions} punch-ins={len(punchins)} "
        f"gags={len(gmeta['gags']) if gmeta else 'off'} title=\"{title}\"")

    if not finish:
        return meta

    stage = out_base
    if captions == "on":
        stage = os.path.join(cdir, "outputs", f"{clip}.captioned.mp4")
        run(["python3", os.path.join(REPO, "presets", "tiktok-raw", "build.py"), cdir,
             "--hook-text", hook_text or "", "--hook-end", "0.01", "--out", stage])
    final = os.path.join(cdir, "outputs", f"{clip}-final.mp4")
    if authored.get("sweep"):
        run(["python3", os.path.join(REPO, "presets", "sweep-intro", "build.py"), stage, final])
    else:
        # no sweep intro on Shorts (the creator, 2026-09-10: its wipe + whoosh read as a fade-in) — a cold open
        run(FFMPEG + ["-i", stage, "-c", "copy", "-movflags", "+faststart", final])
    # a declared held ending: a clip tail the planner added, or the editor's own --static-tail (an empty
    # chair under a laugh) — the freeze gate must still catch everything BEFORE it
    tail_d = next((g["tail"][1] for g in gmeta["gags"] if g.get("tail")), 0.0) if gmeta else 0.0
    static_tail = max(tail_d + 0.5 if tail_d else 0.0, float(authored.get("static_tail", 0.0)))
    v = subprocess.run(["python3", os.path.join(REPO, "workflows", "verify-final.py"), final, "--no-outro",
                        "--expect-duration", f"{dur:.3f}"] + (["--static-tail", f"{static_tail:.2f}"] if static_tail else []),
                       capture_output=True, text=True)
    print("\n".join("    " + l for l in v.stdout.splitlines() if l.startswith(("  [", "RESULT"))))
    if v.returncode != 0:
        raise SystemExit(f"[clipper] {clip}: verify-final FAILED — not finalizing. Inspect {final}")
    fz = subprocess.run(["bash", "finalize.sh", clip, "--apply"], cwd=REPO, capture_output=True, text=True,
                        env={**os.environ, "VE_NO_OUTRO": "1", **({"VE_STATIC_TAIL": f"{static_tail:.2f}"} if static_tail else {})})
    for l in fz.stdout.splitlines():
        if l.strip().startswith(("PROMOTE", "EXPORT", "Done", "✗")):
            print("    " + l.strip())
    if fz.returncode != 0:
        print(fz.stderr, file=sys.stderr)
        raise SystemExit(f"[clipper] {clip}: finalize failed")
    meta["final"] = os.path.join(cdir, "outputs", f"{clip}.final.mp4")
    json.dump(meta, open(os.path.join(cdir, "clip.json"), "w"), indent=2)
    return meta


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min", type=float, default=12.0)
    ap.add_argument("--max", type=float, default=MAX_SHORT, help="longest window the ranker will propose (creator's ceiling: 60 s)")
    ap.add_argument("--target", type=float, default=20.0)
    ap.add_argument("--pick", help="candidate ranks to build, e.g. 1,3,5 (from the printed list)")
    ap.add_argument("--window", action="append", default=[], help="explicit m:ss-m:ss window (repeatable)")
    ap.add_argument("--captions", choices=["on", "off"], default=None,
                    help="REQUIRED when building: burn the locked TikTok/raw captions (on) or leave the frame clean (off)")
    ap.add_argument("--hook-text", default=None, help="opt-in hook card copy (default: cold open, no card)")
    ap.add_argument("--layout", choices=["auto", "face", "stacked", "intercut"], default="auto",
                    help="intercut = the creator full-frame, cutting to the game full-frame inside --cut-to-game windows")
    ap.add_argument("--content-crop", default=None, metavar="x,y,w,h",
                    help="stacked layout: force the screen-content crop (source pixels) instead of auto motion-ROI")
    ap.add_argument("--no-roi", action="store_true", help="stacked layout: skip motion-ROI, use the wide default crop")
    ap.add_argument("--gags", choices=["off", "light", "medium", "heavy"], default="medium",
                    help="the comedy layer (SFX, meme cut-ins, freeze-frames, text pops in tiktok style) — see gags.py")
    ap.add_argument("--style", choices=list(gagmod.STYLE), default="reference",
                    help="reference (default: full-frame reaction clips, ends on a clip + fade, no text pops) | tiktok")
    ap.add_argument("--text-pops", choices=["on", "off"], default=None, help="override the style's text-pop setting")
    ap.add_argument("--pin", default=None, help='pinned-chat hook shown for the first 3 s: "name: message"')
    ap.add_argument("--insert", action="append", default=[], metavar="t:file[:dur]",
                    help="a creator-placed full-frame cut-in (image/GIF/MP4) at clip-time t, default 2.5 s")
    # ---- authoring: the editor places moments by clip-time (seconds) on top of the automatic plan
    ap.add_argument("--no-memes", action="store_true", help="no clip cut-ins and no clip ending (sounds and zooms only)")
    ap.add_argument("--sfx", default="", metavar="tag@t,tag@t", help="authored sounds by tag, e.g. boom@3.5,tick@5,pipe@12")
    ap.add_argument("--text", action="append", default=[], metavar="TEXT@t[:dur]", help='authored text pop, e.g. "he left.@24:2.2"')
    ap.add_argument("--freeze", action="append", default=[], metavar="t[:hold]", help="authored freeze-frame + record scratch")
    ap.add_argument("--face-zoom", action="append", default=[], metavar="a-b[:factor]",
                    help="authored punch-in on the face for a-b seconds (default factor 1.35); replaces automatic ones there")
    ap.add_argument("--content-zoom", action="append", default=[], metavar="a-b:factor[:cx,cy]",
                    help="stacked layout: zoom INTO the content box for a-b seconds, centred at fractions cx,cy (default 0.5,0.5)")
    ap.add_argument("--cut-to-game", action="append", default=[], metavar="a-b",
                    help="intercut layout: show the game full-frame for a-b seconds (repeatable); the face everywhere else. "
                         "Omit to let the transcript decide (game while he is quiet, face while he reacts)")
    ap.add_argument("--loudness", type=float, default=None, metavar="LUFS",
                    help="normalize the mix to this integrated loudness (static gain + true-peak limiter), e.g. -14 for Shorts")
    ap.add_argument("--slowmo", action="append", default=[], metavar="a-b[:factor]",
                    help="slow motion for a-b seconds (default 2x slower); the voice slows with it, everything after shifts")
    ap.add_argument("--sfx-trim", type=float, default=0.0, metavar="dB", help="trim ALL sound effects by this many dB (e.g. -6)")
    ap.add_argument("--sweep", action="store_true", help="add the locked sweep intro (off by default on Shorts)")
    ap.add_argument("--face-source", default="auto", metavar="auto|none|FILE",
                    help="camera file for the FACE segments (auto = the source job's cam.json from scan-replays)")
    ap.add_argument("--face-offset", type=float, default=None, help="override the cam offset (replay t=0 at cam t=OFFSET)")
    ap.add_argument("--face-bg", choices=["keep", "game"], default="keep",
                    help="behind the keyed creator in face segments: keep = as recorded (black/green paint), game = the blurred game")
    ap.add_argument("--static-tail", type=float, default=0.0, metavar="SEC",
                    help="declare the last SEC seconds a deliberate still (an empty chair under a laugh) so the freeze gate allows it")
    ap.add_argument("--no-finish", action="store_true", help="scaffold the clip jobs only")
    ap.add_argument("--start-index", type=int, default=None, help="first NN for <job>-short-NN (default: next free)")
    ap.add_argument("--name", default=None, help="name the clip job after its content (e.g. leap-of-faith) instead of <job>-short-NN")
    args = ap.parse_args()

    job = args.job.rstrip("/").split("/")[-1]
    job_dir = os.path.join(REPO, "projects", job)
    tdoc, words = load_words(job_dir, job)
    face = load_face(job_dir)
    if face is None:
        log("no zoom-crop.json in the source job — framing will center the frame (run workflows/zoom-crop.py first)")

    cand_path = os.path.join(job_dir, "shorts-candidates.json")
    if not args.pick and not args.window:
        picks = rank(words, args.min, args.max, args.target, args.top)
        json.dump({"job": job, "candidates": picks}, open(cand_path, "w"), indent=2)
        print(f"\nSHORTS CANDIDATES for {job} — build with:  clipper.py {job} --pick 1,3 --captions on|off")
        for p in picks:
            print(f"  #{p['rank']}  {mmss(p['start'])}–{mmss(p['end'])}  {p['end'] - p['start']:3.0f}s  score {p['score']:5.2f}"
                  f"   title: \"{p['title_suggestion']}\"\n      \"{p['hook_line']}…\"")
        print(f"\n  written to {cand_path}")
        return

    if args.captions is None and not args.no_finish:
        raise SystemExit("[clipper] --captions on|off is required when building clips (it is a per-video call — "
                         "the reference channel runs none; muted viewers favour them). Add --no-finish to only scaffold.")

    windows = []
    if args.pick:
        if not os.path.isfile(cand_path):
            raise SystemExit("[clipper] run the ranking first (no --pick/--window) to produce shorts-candidates.json")
        by_rank = {c["rank"]: c for c in json.load(open(cand_path))["candidates"]}
        for r in [int(x) for x in re.split(r"[,\s]+", args.pick.strip()) if x]:
            if r not in by_rank:
                raise SystemExit(f"[clipper] no candidate #{r}")
            windows.append((by_rank[r]["start"], by_rank[r]["end"]))
    for w in args.window:
        a, b = w.rsplit("-", 1)
        windows.append((parse_ts(a), parse_ts(b)))

    n = args.start_index
    if n is None:
        n = 1
        while os.path.isdir(os.path.join(REPO, "projects", f"{job}-short-{n:02d}")):
            n += 1
    content_override = tuple(int(v) for v in args.content_crop.split(",")) if args.content_crop else None
    text_pops = None if args.text_pops is None else args.text_pops == "on"

    def zoom_spec(s, with_center):        # "a-b[:factor[:cx,cy]]" in clip seconds
        rng, _, rest = s.partition(":")
        a, b = (float(x) for x in rng.rsplit("-", 1))
        parts = rest.split(":") if rest else []
        z = {"a": a, "b": b, "f": float(parts[0]) if parts and parts[0] else PUNCH}
        if with_center and len(parts) > 1 and parts[1]:
            z["cx"], z["cy"] = (float(v) for v in parts[1].split(","))
        return z

    authored = {"fixed": gagmod.authored_gags(args.insert, args.text, args.freeze), "sfx": gagmod.parse_sfx(args.sfx),
                "no_memes": args.no_memes, "static_tail": args.static_tail, "fzooms": [zoom_spec(s, False) for s in args.face_zoom],
                "czooms": [zoom_spec(s, True) for s in args.content_zoom], "loudness": args.loudness,
                "slow": [(z["a"], z["b"], z["f"] if ":" in s else 2.0) for s, z in ((s, zoom_spec(s, False)) for s in args.slowmo)],
                "sfx_trim": args.sfx_trim, "sweep": args.sweep,
                "game": [tuple(float(x) for x in s.rsplit("-", 1)) for s in args.cut_to_game],
                "spec": {k: v for k, v in (("insert", args.insert), ("text", args.text), ("freeze", args.freeze), ("sfx", args.sfx),
                                           ("face_zoom", args.face_zoom), ("content_zoom", args.content_zoom),
                                           ("cut_to_game", args.cut_to_game), ("loudness", args.loudness),
                                           ("slowmo", args.slowmo), ("sfx_trim", args.sfx_trim), ("sweep", args.sweep),
                                           ("no_memes", args.no_memes)) if v}}
    if args.layout == "intercut" and not args.cut_to_game:
        log("intercut layout: game windows will be chosen automatically from the transcript (override with --cut-to-game)")
    results = []
    for k, (t0, t1) in enumerate(windows):
        nm = None
        if args.name:
            nm = re.sub(r"[^a-z0-9-]+", "-", args.name.lower()).strip("-") + (f"-{k + 1:02d}" if len(windows) > 1 else "")
        results.append(build_clip(job, job_dir, tdoc, words, n, t0, t1, args.layout, args.hook_text,
                                  args.captions or "off", not args.no_finish, face,
                                  "none" if args.no_roi else "auto", content_override, args.gags,
                                  args.style, text_pops, args.pin, authored, nm, args.face_source, args.face_offset, args.face_bg))
        n += 1
    print()
    for m in results:
        print(f"  {m['clip']}: {mmss(m['start'])}–{mmss(m['end'])} {m['layout']:7s} title \"{m['title_suggestion']}\" → {m.get('final', '(scaffolded only)')}")


if __name__ == "__main__":
    main()
