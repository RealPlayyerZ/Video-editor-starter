#!/usr/bin/env python3
"""
gags.py — the comedy layer for Shorts: find the beats, plan the gags, render them in ONE ffmpeg pass.

Sits between the 9:16 reframe and the captions in presets/shorts/clipper.py
(--gags off|light|medium|heavy, default medium). Standalone on a clip job:

  presets/shorts/gags.py projects/<clip> --plan-only                 # beats + plan, renders nothing
  presets/shorts/gags.py projects/<clip> --intensity heavy           # re-render from outputs/<clip>.reframed.mp4

WHAT IT LISTENS FOR (beats) — the clip's transcript slice + an RMS envelope of its audio:
  * trigger words / phrases ("wait", "what", "no way", "bro", "nah", "nightmare", "insane", …) → a sentiment
  * loud NON-speech (a laugh, a shout): energy where no word is active. Long non-speech = the embedded
    video playing → the first word after it is the reaction beat
  * the pause after a punchline (a sentence end + ≥0.7 s of air)
  * the button (last word); anything in the first 3 s gets a hook bonus

WHAT IT DOES WITH THEM (gags):
  boom      sub-bass hit + 0.35 s camera shake + red flash + a text pop     the shock / fear line
  hit       impact + short shake + text pop                                  the hype line
  freeze    0.45 s freeze-frame + record scratch                             "wait… what?" (one per Short)
  meme      a tagged image / GIF / MP4 cut in for ~1 s (+ pop)              the laugh, the deadpan
  text      a big Inter Black word pop ("NAH.", "???", "YIKES")             whenever no meme fits
  womp      sad trombone + "WOMP WOMP"                                      a disappointment landing
  crickets  a dead pause                                                    a landing with ≥1.2 s of air
  bass      0.6 s bass-boost / crush on a scream                            only on a genuinely loud beat
  button    impact + shake on the last word
  whoosh    under every punch-in (not counted as a gag)

COMEDIC-TIMING RULES (medium): a gag inside the first 3 s if there is a beat there, one on the button,
≤1 gag per 3.5 s, never the same type twice running, ≤ round(dur/5) gags (3–8), gag screen-time ≤ 25 %.
"This clip carries itself → nothing" is a legitimate result when there are no beats.

Sounds: assets/sfx/ (yours) beat assets/sfx/synth/ (generated) by tag — assets/sfx/README.md.
Memes: assets/memes/ by tag — assets/memes/README.md. A missing tag degrades to a text pop, never fails.
A freeze inserts time: the returned time_map [(t, hold), …] is applied to the transcript by the clipper.
"""
import argparse, json, math, os, random, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SFX_DIR = os.path.join(REPO, "assets", "sfx")
SYNTH_DIR = os.path.join(SFX_DIR, "synth")
MEME_DIR = os.path.join(REPO, "assets", "memes")
FONT = os.path.join(REPO, "assets", "fonts", "Inter-Black.otf")
FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]
AFMT = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
W, H = 1080, 1920
TEXT_SCALE = 1.0          # text pops are designed for a 1080-wide Short; canvas() scales them for 16:9


def canvas(w, h):
    """Long-form (2026-09-13): retarget the frame geography to a 16:9 canvas. Layout "wide" = the
    gameplay composite (facecam bottom-right): text pops at 2/3 height, inset cut-ins bottom-left."""
    global W, H, TEXT_SCALE
    W, H = int(w), int(h)
    TEXT_SCALE = W / 1080 if W > H else 1.0
    TEXT_CY["wide"] = int(H * 0.66)
    mw = int(W * 0.34)
    MEME_REGION["wide"] = (int(W * 0.03), int(H * 0.50), mw, int(mw * 9 / 16))

# frame geography per layout. STACKED = face box y0–768, content below: text straddles the seam,
# a meme replaces the content box. FACE = a 3.2×-face crop, so the head fills y≈240–1100 and the
# only free real estate is his chest (measured on the Astra test): text at 1320, memes 1200–1720
# (the locked captions at y1500 burn on top of a meme, which is fine).
TEXT_CY = {"stacked": 680, "face": 1320, "intercut": 1320}
MEME_REGION = {"stacked": (0, 768, 1080, 1152), "face": (60, 1200, 960, 520), "intercut": (60, 1200, 960, 520)}

TEXT_DUR, MEME_DUR, FREEZE_HOLD, SHAKE_DUR, FLASH_DUR, BASS_DUR = 0.75, 2.0, 0.45, 0.35, 0.07, 0.6
MEME_MAX, TAIL_MIN, TAIL_MAX, PIN_UNTIL = 3.0, 1.5, 3.0, 3.0
TWO_PASS_OVER = 120.0     # inputs longer than this mix their sounds in a separate audio pass (see render())
FONT_BOLD = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


INTENSITY = {
    "light":  dict(max_gags=lambda d: 1, gap=6.0, memes=False, freeze=False, shake=False, bass=False, flash=False, screen=0.12),
    "medium": dict(max_gags=lambda d: _clamp(round(d / 5.0), 3, 8), gap=3.5, memes=True, freeze=True, shake=True, bass=True, flash=True, screen=0.35),
    "heavy":  dict(max_gags=lambda d: _clamp(round(d / 2.5), 5, 16), gap=2.0, memes=True, freeze=True, shake=True, bass=True, flash=True, screen=0.50),
}
# STYLE = whose Shorts we are imitating. "reference" (default) comes from the 17-Short study of
# 2026-09-09 (workflows/reference-channel-study.md): full-frame reaction-clip cut-ins, the Short ENDS on a
# clip with a fade to black, no text pops, no flashes/shakes. "tiktok" is the louder text-pop /
# flash / shake flavour with inset memes.
STYLE = {
    "reference": dict(text_pops=False, flash=False, shake=False, meme_full=True, meme_tail=True),
    "tiktok":    dict(text_pops=True, flash=True, shake=True, meme_full=False, meme_tail=False),
    # "punchy": the editor authors the moments (--sfx / --text / --freeze / --content-zoom / --face-zoom);
    # the planner still lands impacts on trigger words, with flash + shake, but no automatic text pops
    "punchy":    dict(text_pops=False, flash=True, shake=True, meme_full=True, meme_tail=False),
    # "gameplay" (2026-09-13, long-form 16:9): the footage is the joke — reaction clips INSET bottom-left
    # (never covering the game), flash + shake on impacts, no automatic text pops, no clip ending
    "gameplay":  dict(text_pops=False, flash=True, shake=True, meme_full=False, meme_tail=False),
}

# word → (score, sentiment). Score ≥ 0.7 makes a beat on its own; loudness and the hook add to it.
TRIGGERS = {
    "what": (1.0, "shock"), "wait": (1.0, "shock"), "huh": (0.9, "shock"), "wow": (0.9, "shock"), "holy": (1.0, "shock"),
    "seriously": (0.9, "shock"), "kidding": (1.0, "shock"), "unbelievable": (1.1, "shock"), "jesus": (0.9, "shock"),
    "excuse": (0.8, "shock"), "why": (0.5, "shock"), "hello": (0.5, "shock"), "really": (0.3, "shock"),
    "nightmare": (1.2, "fear"), "terrifying": (1.0, "fear"), "disgusting": (1.0, "fear"), "gross": (0.8, "fear"),
    "yikes": (1.0, "fear"), "awful": (0.9, "fear"), "horrible": (0.9, "fear"), "worst": (0.9, "fear"), "ugly": (0.8, "fear"),
    "cringe": (1.0, "fear"), "creepy": (1.0, "fear"), "scary": (0.9, "fear"), "hell": (0.6, "fear"), "damn": (0.7, "fear"),
    "shit": (0.8, "fear"), "fuck": (0.9, "fear"), "god": (0.6, "fear"), "wrong": (0.6, "fear"), "broken": (0.8, "fear"),
    "dead": (0.9, "dead"), "bro": (0.9, "dead"), "bruh": (1.2, "dead"), "nah": (1.0, "dead"), "stop": (0.6, "dead"),
    "cooked": (1.0, "dead"), "rip": (0.9, "dead"), "oof": (1.0, "dead"), "lmao": (1.0, "dead"), "lol": (0.8, "dead"),
    "clown": (1.0, "dead"), "cope": (0.9, "dead"), "ratio": (0.8, "dead"), "delusional": (0.9, "dead"), "please": (0.4, "dead"),
    "insane": (1.2, "hype"), "crazy": (0.9, "hype"), "banger": (0.9, "hype"), "fire": (0.5, "hype"), "goat": (0.9, "hype"),
    "best": (0.6, "hype"), "incredible": (0.9, "hype"), "amazing": (0.8, "hype"), "beautiful": (0.6, "hype"), "peak": (0.8, "hype"),
    "sad": (0.8, "sad"), "pain": (0.8, "sad"), "disappointed": (0.9, "sad"), "disappointing": (0.9, "sad"), "unfortunately": (0.6, "sad"),
    "brutal": (0.8, "sad"), "tragic": (0.9, "sad"), "embarrassing": (0.9, "sad"), "rough": (0.5, "sad"),
    "trash": (0.9, "dead"), "garbage": (0.9, "dead"), "mid": (0.8, "dead"), "washed": (0.9, "dead"), "fraud": (0.9, "dead"),
    "scam": (0.9, "dead"), "bug": (0.8, "fear"), "bugged": (0.9, "fear"), "glitch": (0.8, "fear"), "glitched": (0.9, "fear"),
    "crash": (0.8, "fear"), "crashed": (0.9, "fear"), "error": (0.8, "fear"), "lag": (0.7, "fear"), "laggy": (0.8, "fear"),
}
PHRASES = {
    "no way": (1.3, "shock"), "oh my god": (1.3, "shock"), "what the": (1.2, "shock"), "hold on": (1.0, "shock"),
    "are you kidding": (1.3, "shock"), "are you serious": (1.3, "shock"), "what is that": (1.1, "shock"),
    "what is this": (1.1, "shock"), "excuse me": (1.1, "shock"), "wait what": (1.4, "shock"), "hold up": (1.0, "shock"),
    "nightmare fuel": (1.4, "fear"), "oh no": (1.0, "fear"), "no no no": (1.2, "fear"), "get out": (0.8, "fear"),
    "shut up": (0.9, "dead"), "i'm dead": (1.2, "dead"), "i am dead": (1.2, "dead"), "i can't": (0.8, "dead"),
    "that's crazy": (1.0, "hype"), "that is crazy": (1.0, "hype"), "let's go": (1.1, "hype"), "lets go": (1.1, "hype"),
    "womp womp": (1.3, "sad"), "it is what it is": (0.9, "sad"),
}
SHOUTABLE = {"what", "wait", "bro", "bruh", "nah", "insane", "nightmare", "yikes", "dead", "cooked", "huh", "wow", "stop",
             "why", "crazy", "clown", "cope", "ratio", "hello", "excuse", "no way", "oh no", "wait what", "hold on", "hold up",
             "excuse me", "let's go", "lets go", "womp womp", "i'm dead", "shut up", "get out", "nightmare fuel", "oh my god"}
TEXT_POOL = {
    "shock": ["WHAT.", "???", "HUH?", "NO WAY", "WAIT."],
    "fear": ["YIKES", "NOPE.", "OH NO", "DEAD.", "PAIN"],
    "dead": ["NAH.", "BRO.", "LMAO", "BRUH", "I'M DEAD"],
    "hype": ["INSANE", "W", "LET'S GO", "BANGER"],
    "sad": ["WOMP WOMP", "L", "PAIN", "RIP"],
    "question": ["???", "HUH?"],
}
MEME_TAGS = {
    "shock": ["shock", "surprised", "what", "wtf", "huh", "confused", "math", "pikachu"],
    "fear": ["scared", "fear", "nightmare", "yikes", "nope", "disgust", "disgusted", "sweating", "panik"],
    "dead": ["laugh", "laughing", "lol", "lmao", "dead", "bruh", "nah", "facepalm", "cope", "clown"],
    "hype": ["hype", "letsgo", "lets-go", "win", "w", "goat", "fire", "chad", "based"],
    "sad": ["sad", "pain", "l", "loss", "cry", "womp", "disappointed", "rip"],
    "question": ["confused", "huh", "math", "what", "thinking"],
}
SFX_ALIASES = {
    "boom": ["boom", "vine"], "scratch": ["scratch", "record"], "laugh": ["laugh", "laughing", "lmao", "laughtrack"],
    "crickets": ["crickets", "cricket"], "hit": ["hit", "impact"], "whoosh": ["whoosh", "swoosh", "swish"],
    "womp": ["womp", "trombone", "sad"], "airhorn": ["airhorn", "horn"], "bassdrop": ["bassdrop", "drop"],
    "ding": ["ding", "bell"], "buzz": ["buzz", "error", "wrong"], "pop": ["pop", "click"], "riser": ["riser", "rise"],
    "glitch": ["glitch"], "boing": ["boing", "spring"], "bruh": ["bruh"], "damage": ["damage", "emotional", "emotionaldamage"],
    "ohno": ["ohno", "ohnonono", "ohnono", "nonono"], "fah": ["fah", "fahh", "fahhh"], "shutter": ["shutter", "camera"],
    "pipe": ["pipe", "metalpipe"], "tick": ["tick"], "heartbeat": ["heartbeat", "heart"],
    "goofy": ["goofy", "yell"], "whistle": ["whistle", "slidewhistle"], "falling": ["falling", "cartoonfalling"],
    "popping": ["popping", "poppingnoise"],
    "countdown": ["countdown"],                   # The Final Countdown riff (myinstants, 2026-09-19) — authored only (--sfx countdown@t)
    "kazoo": ["kazoo"],                           # its kazoo cover — the lower-claim-risk alternative
       # the creator's chat-message pop (D:/Videos/Youtube/Popping Sounds)
}
# mix level per tag, dB relative to a -3 dBFS-peak file (voice stays untouched; alimiter guards the ceiling)
SFX_GAIN = {"boom": -5, "hit": -7, "whoosh": -13, "ding": -12, "pop": -11, "riser": -14, "glitch": -11, "buzz": -9,
            "bassdrop": -6, "scratch": -8, "crickets": -15, "shutter": -13, "boing": -11, "womp": -9, "airhorn": -8,
            "laugh": -11, "bruh": -7, "damage": -6, "ohno": -9, "fah": -7, "pipe": -6, "tick": -12, "heartbeat": -7,
            "goofy": -6, "whistle": -8, "falling": -8, "popping": -4,
            "countdown": -14, "kazoo": -13}
# the character sounds the creator pulled from myinstants (2026-09-09) and where they land
BURN = {"cooked", "clown", "ratio", "delusional", "cope", "embarrassing", "trash", "garbage", "mid", "washed", "fraud", "scam"}
BROKEN = {"wrong", "broken", "bug", "bugged", "glitch", "glitched", "crash", "crashed", "error", "lag", "laggy"}
OHNO = {"oh no", "no no no", "disgusting", "horrible", "worst", "awful", "gross", "ugly", "creepy", "nightmare fuel"}
CHAT = {"chat", "comment", "comments", "message", "messages", "dm", "dms", "tweet", "post", "reply", "replies"}


def log(msg):
    print(f"[gags] {msg}", flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"[gags] command failed: {' '.join(str(c) for c in cmd)}")
    return r


def clean(t):
    return t.lower().strip(".,?!;:\"'…")


def ffprobe_dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                                capture_output=True, text=True, check=True).stdout)


def ffprobe_fps(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True).stdout.strip()
    a, b = (r.split("/") + ["1"])[:2]
    return float(a) / float(b or 1)


# ----------------------------------------------------------------------------- libraries
def _tags(stem):
    """'oh-no-no-no' → {oh, no, ohnonono}: the split words plus the joined stem, so multi-word names match."""
    words = {t for t in re.split(r"[-_ .]+", stem.lower()) if t}
    return words | {re.sub(r"[-_ .]+", "", stem.lower())}


def sfx_library():
    """tag → file. Files the creator dropped into assets/sfx/ win over assets/sfx/synth/."""
    lib = {}
    for d, prio in ((SYNTH_DIR, 0), (SFX_DIR, 1)):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            stem, ext = os.path.splitext(f)
            if ext.lower() not in (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac"):
                continue
            words = _tags(stem)
            for tag, aliases in SFX_ALIASES.items():
                if words & set(aliases) and (tag not in lib or lib[tag][1] < prio):
                    lib[tag] = (os.path.join(d, f), prio)
    return {k: v[0] for k, v in lib.items()}


def sfx_peak_db(path):
    """Peak of a file, measured once and cached next to the library."""
    cache_p = os.path.join(SFX_DIR, ".cache.json")
    cache = json.load(open(cache_p)) if os.path.isfile(cache_p) else {}
    key, mt = os.path.abspath(path), os.path.getmtime(path)
    if key in cache and abs(cache[key]["mtime"] - mt) < 1e-6:
        return cache[key]["peak_db"]
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    peak = float(m.group(1)) if m else -3.0
    cache[key] = {"mtime": mt, "peak_db": peak}
    try:
        json.dump(cache, open(cache_p, "w"), indent=1)
    except OSError:
        pass
    return peak


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return "audio" in r.stdout


def meme_library():
    out = []
    if not os.path.isdir(MEME_DIR):
        return out
    for f in sorted(os.listdir(MEME_DIR)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm"):
            animated = ext.lower() in (".gif", ".mp4", ".mov", ".webm")
            # a vlip / reaction clip carries its own line ("NOOO!") — that audio IS the joke, so it rides along
            out.append({"path": os.path.join(MEME_DIR, f), "tags": _tags(stem), "animated": animated,
                        "audio": animated and ext.lower() != ".gif" and has_audio(os.path.join(MEME_DIR, f)),
                        "dur": ffprobe_dur(os.path.join(MEME_DIR, f)) if animated else None})
    return out


def pick_meme(memes, sentiment, used, rng):
    want = set(MEME_TAGS.get(sentiment or "dead", []))
    pool = [m for m in memes if m["tags"] & want and m["path"] not in used]
    if not pool:
        return None
    m = rng.choice(pool)
    used.add(m["path"])
    return m


def pick_text(sentiment, token, used):
    """The creator's own trigger word is the best text pop ("UNBELIEVABLE", "NO WAY"); the pool is the fallback."""
    if token and (token in TRIGGERS or token in PHRASES) and len(token) <= 14 and not token.startswith("("):
        t = token.upper()
        t += "?" if token in ("what", "huh", "why", "hello", "excuse me", "wait what", "seriously") else ("." if " " not in t else "")
        if t not in used:
            used.add(t)
            return t
    for t in TEXT_POOL.get(sentiment or "dead", TEXT_POOL["dead"]) + TEXT_POOL["dead"] + TEXT_POOL["shock"]:
        if t not in used:
            used.add(t)
            return t
    return "???"


# ----------------------------------------------------------------------------- listening
def audio_envelope(path, work, hop=0.05):
    """[(t, rms_dB)] every `hop` seconds, mono — ffmpeg astats, no numpy."""
    os.makedirs(work, exist_ok=True)
    meta = os.path.join(work, "env.txt")
    n = int(48000 * hop)
    run(FFMPEG + ["-i", path, "-vn", "-af",
                  f"aformat=channel_layouts=mono:sample_rates=48000,asetnsamples=n={n},astats=metadata=1:reset=1,"
                  f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file={meta}", "-f", "null", "-"])
    env, t = [], None
    for line in open(meta):
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"RMS_level=(-?[\d.]+|-inf|inf|nan)", line)
        if m and t is not None:
            v = m.group(1)
            env.append((t, -90.0 if v in ("-inf", "inf", "nan") else float(v)))
    return env


def _sentence_sentiment(ws):
    best, sent = 0.0, None
    toks = [clean(w["text"]) for w in ws]
    for k, tok in enumerate(toks):
        sc, s = TRIGGERS.get(tok, (0.0, None))
        for ph, (psc, ps) in PHRASES.items():
            if " ".join(toks[k:k + len(ph.split())]) == ph and psc > sc:
                sc, s = psc, ps
        if sc > best:
            best, sent = sc, s
    return sent or "dead"


def detect_beats(words, env, dur, hop=0.05):
    if not words:
        return [], -25.0
    starts = [w["start"] for w in words]
    def speech_at(t):
        # any word active within ±0.1 s (words are sorted by start)
        for w in words:
            if w["start"] - 0.1 <= t <= w["end"] + 0.1:
                return True
            if w["start"] - 0.1 > t:
                break
        return False
    speech = [speech_at(t) for t, _ in env]
    sp_vals = sorted(v for (t, v), a in zip(env, speech) if a and v > -80)
    med = sp_vals[len(sp_vals) // 2] if sp_vals else -25.0

    def rms_at(t):
        vals = [v for (tt, v) in env if t - 0.1 <= tt <= t + 0.25]
        return max(vals) if vals else -90.0

    beats = []
    toks = [clean(w["text"]) for w in words]
    for k, w in enumerate(words):
        sc, sent, text = TRIGGERS.get(toks[k], (0.0, None))[0], TRIGGERS.get(toks[k], (0.0, None))[1], toks[k]
        end = w["end"]
        for ph, (psc, psent) in PHRASES.items():
            n = len(ph.split())
            if " ".join(toks[k:k + n]) == ph and psc > sc:
                sc, sent, text, end = psc, psent, ph, words[k + n - 1]["end"]     # the beat ends with the whole phrase
        if w["text"].strip().endswith("?") and sc < 0.6:
            # a plain question only becomes a beat with help (the hook bonus, or loud delivery) —
            # mid-clip "???" on an ordinary question read as random in the first example set
            sc, sent, text = 0.6, sent or "question", "(question)"
        if sc < 0.7:
            continue
        r = rms_at(w["start"])
        # the rough cut's limiter keeps his range tight (~±4 dB around the median) — small deltas ARE emphasis
        loud, very = r >= med + 3.5, r >= med + 6.5
        sc += (0.5 if loud else 0.0) + (0.6 if w["start"] < 3.0 else 0.0)
        beats.append(dict(t=round(w["start"], 3), end=round(end, 3), kind="word", score=round(sc, 2), sentiment=sent,
                          text=text, loud=loud, very_loud=very, rms=round(r, 1)))

    # loud non-speech: short = a laugh / a shout; long = the embedded content playing. On GAMEPLAY
    # footage the non-speech floor is high (a bed of game sound — gunfire, explosions) and every
    # burst would read as a laugh, so with a bed a burst only counts when it is louder than his own
    # speech AND lands right after one of his lines (a reaction sound), and long bursts are ignored.
    nonsp = sorted(v for (t, v), a in zip(env, speech) if not a)
    floor = nonsp[len(nonsp) // 10] if nonsp else -90.0
    bed = floor > -45.0
    thr, regions, cur = ((med + 2.0) if bed else (med - 4.0)), [], None
    for (t, v), a in zip(env, speech):
        if not a and v >= thr:
            if cur and t - cur[1] <= 0.16:
                cur[1] = t + hop
            else:
                if cur:
                    regions.append(cur)
                cur = [t, t + hop]
    if cur:
        regions.append(cur)
    for a, b in regions:
        L = b - a
        peak = max(v for (t, v) in env if a <= t <= b)
        after_line = any(0.0 <= a - w["end"] <= 1.2 for w in words)
        if 0.25 <= L <= (1.5 if bed else 2.2) and a > 0.2 and (after_line or not bed):
            beats.append(dict(t=round(a, 3), end=round(b, 3), kind="laugh", sentiment="dead", text="(non-speech %.1fs)" % L,
                              score=round((0.9 if bed else 1.0) + (0.4 if peak >= med + 3 else 0.0) + (0.6 if a < 3.0 else 0.0), 2),
                              loud=peak >= med + 3, very_loud=peak >= med + 8, rms=round(peak, 1)))
        elif L > 2.5 and not bed:
            nxt = next((w for w in words if w["start"] >= b - 0.05), None)
            if nxt and nxt["start"] - b <= 1.2 and not any(abs(x["t"] - nxt["start"]) < 0.3 for x in beats):
                sent = TRIGGERS.get(clean(nxt["text"]), (0, None))[1] or "shock"
                beats.append(dict(t=round(nxt["start"], 3), end=round(nxt["end"], 3), kind="reaction", score=1.0, sentiment=sent,
                                  text=clean(nxt["text"]), loud=False, very_loud=False, rms=round(rms_at(nxt["start"]), 1)))

    # the pause after a punchline. A long pause on reaction footage is usually him WATCHING the
    # content, not dead air — so a landing only counts for 0.7–2.5 s, scores low (fills in when
    # nothing stronger is near), and the planner decides whether anything fits it at all.
    for k in range(1, len(words)):
        gap = words[k]["start"] - words[k - 1]["end"]
        punct = words[k - 1]["text"].strip().endswith(("?", "!"))
        if 0.7 <= gap <= 2.5 and (gap >= 1.0 or words[k - 1]["text"].strip().endswith((".", "?", "!"))):
            t = words[k - 1]["end"] + 0.08
            beats.append(dict(t=round(t, 3), end=round(words[k]["start"], 3), kind="landing", gap=round(gap, 2), punct=punct,
                              score=round(0.6 + min(0.3, gap - 0.7), 2), sentiment=_sentence_sentiment(words[max(0, k - 8):k]),
                              text="(pause %.1fs)" % gap, loud=False, very_loud=False, rms=round(rms_at(t), 1)))

    # the button: on the last word, but never so late the sound gets cut off by the end of the clip
    last = words[-1]
    if last["end"] > 1.0:
        beats.append(dict(t=round(max(0.3, min(last["end"] - 0.05, dur - 0.45)), 3), end=round(dur, 3), kind="button", score=0.9,
                          sentiment=_sentence_sentiment(words[-8:]), text=clean(last["text"]), loud=False, very_loud=False,
                          rms=round(rms_at(last["start"]), 1)))

    # dedupe within 0.3 s → keep the strongest; the button always survives (the last word is often
    # a trigger itself — "…that's crazy." — and the ending must not lose to it)
    beats.sort(key=lambda b: (b["t"], -b["score"]))
    out = []
    for b in beats:
        if out and abs(b["t"] - out[-1]["t"]) < 0.3:
            if b["score"] > out[-1]["score"] or (b["kind"] == "button" and out[-1]["kind"] != "button"):
                out[-1] = b
            continue
        out.append(b)
    return out, med, bed


# ----------------------------------------------------------------------------- planning
def fixed_insert(t, m, d):
    """A creator-placed full-frame cut-in (image / GIF / MP4) — see insert_item()."""
    return dict(t=round(t, 3), type="insert", beat="authored", sentiment="-", why="creator", sfx=[], text=None,
                meme=(m, round(t, 3), round(t + d, 3)))


def fixed_text(text, t, d):
    """An authored text pop, regardless of the style's automatic text setting."""
    return dict(t=round(t, 3), type="text", beat="authored", sentiment="-", why="creator", sfx=[],
                text=(text, round(t, 3), round(t + d, 3)), meme=None)


def fixed_freeze(t, hold=FREEZE_HOLD):
    """An authored freeze-frame + record scratch at clip-time t (captions are shifted by the clipper)."""
    return dict(t=round(t, 3), type="freeze", beat="authored", sentiment="-", why="creator",
                sfx=[("scratch", round(t, 3))], text=None, meme=None, hold=hold)


def plan_gags(beats, punchins, dur, intensity, sfx, memes, layout, rng, words=None, style="reference", text_pops=None,
              fixed_gags=(), bed=False, blocked=()):
    st = STYLE[style]
    cfg = {**INTENSITY[intensity]}
    cfg["shake"] = cfg["shake"] and st["shake"]
    cfg["flash"] = cfg["flash"] and st["flash"]
    if bed:
        # gameplay: the footage IS the joke — clips cover it, so fewer of them and further apart
        # (his gameplay Shorts run one or two cut-ins, not five)
        cfg["screen"] = min(cfg["screen"], 0.15)
        cfg["gap"] = max(cfg["gap"], 5.0)
    if dur > 120:
        # long-form (2026-09-13): the Shorts caps (8 gags, 3.5 s apart) make no sense over 20 minutes —
        # aim for one gag every ~25 s at medium, keep them well apart, overlays under 10 % of screen time
        per = {"light": 60.0, "medium": 25.0, "heavy": 14.0}[intensity]
        cfg["max_gags"] = lambda d, per=per: _clamp(round(d / per), 8, 120)
        cfg["gap"] = max(cfg["gap"], 6.0)
        cfg["screen"] = min(cfg["screen"], 0.10)
    once_max = 4 if dur > 120 else 1          # freeze-frames / bass drops: once per Short, a few per long-form
    text_on = st["text_pops"] if text_pops is None else text_pops
    max_g = cfg["max_gags"](dur)
    # authored gags (--insert / --text / --freeze) are fixed first; everything automatic keeps its distance
    fixed = [dict(g) for g in fixed_gags]
    for g in fixed:
        g["sfx"] = [(tag, t) for tag, t in g["sfx"] if tag in sfx]

    def landing_fits(b):
        # a pause only gets a gag when something specific fits it: sad trombone on a let-down, a
        # laugh track when a joke lands, crickets after a question left hanging, or a reaction meme
        if b["sentiment"] == "sad" and "womp" in sfx:
            return True
        if b.get("punct") and 1.0 <= b.get("gap", 0) <= 2.5 and (("laugh" in sfx and b["sentiment"] in ("dead", "hype"))
                                                              or "crickets" in sfx):
            return True
        want = set(MEME_TAGS.get(b["sentiment"] or "dead", []))
        return cfg["memes"] and any(m["tags"] & want for m in memes)

    cands = sorted((b for b in beats if b["kind"] != "landing" or landing_fits(b)), key=lambda b: -b["score"])
    chosen = []

    def ok(b):
        return all(abs(b["t"] - c["t"]) >= cfg["gap"] for c in chosen) and 0.3 <= b["t"] <= dur - 0.05 \
            and all(abs(b["t"] - f["t"]) >= cfg["gap"] for f in fixed) \
            and all(abs(b["t"] - t) >= 2.5 for t in blocked)          # the editor placed a sound here — step aside

    hook = next((b for b in sorted(cands, key=lambda b: b["t"]) if b["t"] < 3.0), None)
    button = next((b for b in cands if b["kind"] == "button"), None)
    for b in (hook, button):
        if b and ok(b) and len(chosen) < max_g:
            chosen.append(b)
    for b in cands:
        if len(chosen) >= max_g:
            break
        if b not in chosen and ok(b):
            chosen.append(b)
    chosen.sort(key=lambda b: b["t"])

    gags, used_text, used_memes, last_type = list(fixed), set(), set(), None
    freeze_n = bass_n = 0
    screen = 0.0
    for b in chosen:
        sent, tok = b["sentiment"] or "shock", b["text"]
        if b["kind"] == "button":
            # the reference channel's signature ending: cut to a reaction clip and let it play out, fading to black
            gtype = "button"
            if st["meme_tail"] and cfg["memes"]:
                tail = pick_meme(memes, sent, used_memes, rng) or pick_meme(memes, "dead", used_memes, rng) \
                    or pick_meme(memes, "shock", used_memes, rng)
                if tail:
                    gtype = "tail"
        elif b["kind"] == "landing":
            if sent == "sad" and "womp" in sfx:
                gtype = "womp"
            elif b.get("punct") and 1.0 <= b.get("gap", 0) <= 2.5 and "laugh" in sfx and sent in ("dead", "hype"):
                gtype = "laughtrack"
            elif b.get("punct") and 1.2 <= b.get("gap", 0) <= 2.5 and "crickets" in sfx:
                gtype = "crickets"
            else:
                gtype = "meme"
        elif b["kind"] == "laugh":
            gtype = "meme" if cfg["memes"] else "text"
        else:
            if tok in BURN and "damage" in sfx:
                gtype = "damage"
            elif tok in BROKEN and "buzz" in sfx:
                gtype = "buzz"
            elif cfg["freeze"] and freeze_n < once_max and sent == "shock" and "scratch" in sfx and b["t"] >= 1.5 and \
                    tok in ("wait", "what", "huh", "hold on", "hold up", "wait what", "excuse me", "excuse"):
                gtype = "freeze"
            elif cfg["bass"] and bass_n < once_max and b.get("very_loud"):
                gtype = "bass"
            elif tok in OHNO and "ohno" in sfx and intensity != "light":
                gtype = "ohno"
            elif sent in ("shock", "fear", "question"):
                gtype = "boom"
            elif sent == "hype":
                gtype = "airhorn" if (b["loud"] and "airhorn" in sfx and intensity != "light") else "hit"
            elif sent == "sad":
                gtype = "womp" if "womp" in sfx else "text"
            else:
                gtype = "meme" if cfg["memes"] else "text"
        if last_type == gtype and gtype not in ("button", "tail"):
            # never the same move twice running — an impact can follow an impact only as a different sound
            gtype = {"boom": "hit", "hit": "boom", "meme": "text", "text": "meme" if cfg["memes"] else "hit", "womp": "text",
                     "freeze": "boom", "bass": "boom", "crickets": "text", "damage": "text", "buzz": "text", "ohno": "boom",
                     "airhorn": "hit", "laughtrack": "text"}[gtype]
        if gtype == "text" and not text_on:
            # no text pops in this style: a reaction clip if one fits, else just the deadpan sound, else nothing
            if cfg["memes"] and pick_meme(memes, sent, set(used_memes), random.Random(0)):
                gtype = "meme"
            elif sent == "dead" and "bruh" in sfx:
                gtype = "bruh"
            else:
                continue
        meme = None
        if gtype == "meme":
            meme = pick_meme(memes, sent, used_memes, rng)
            if meme is None:
                if b["kind"] == "landing" or not text_on:
                    continue            # nothing fits this pause after all → leave it alone
                gtype = "text"
        if gtype == "freeze":
            freeze_n += 1
        if gtype == "bass":
            bass_n += 1

        g = dict(t=b["t"], type=gtype, beat=b["kind"], sentiment=sent, why=tok, sfx=[], text=None, meme=None)
        if gtype == "boom":
            g["sfx"] = [("boom", b["t"] - 0.04)]
            g["shake"] = SHAKE_DUR if cfg["shake"] else 0
            g["flash"] = cfg["flash"]
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "hit":
            g["sfx"] = [("hit", b["t"] - 0.03)]
            g["shake"] = 0.25 if cfg["shake"] else 0
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "freeze":
            tf = b["end"] if tok in ("wait", "hold on", "hold up") else b["t"] + 0.08
            g.update(t=round(tf, 3), hold=FREEZE_HOLD)
            g["sfx"] = [("scratch", tf)]
        elif gtype == "bass":
            g["bass"] = (b["t"], b["t"] + BASS_DUR)
            g["shake"] = 0.5 if cfg["shake"] else 0
            if "fah" in sfx:
                g["sfx"] = [("fah", b["t"])]
        elif gtype == "meme":
            t0 = b["t"] if b["kind"] in ("laugh", "landing") else b["end"]      # the reaction comes AFTER the line
            # a clip with its own line plays out its own length (capped) instead of the flat 2 s
            d = min(max(MEME_DUR, meme["dur"] or 0), MEME_MAX) if meme.get("audio") else MEME_DUR
            d = min(d, max(0.8, dur - 0.3 - t0))
            g["meme"] = (meme, t0, round(t0 + d, 3))
            g["sfx"] = [] if (meme.get("audio") or st["meme_full"]) else [("pop", t0)]
        elif gtype == "tail":
            d = _clamp(tail["dur"] or 2.0, TAIL_MIN, TAIL_MAX)
            g["tail"] = (tail, round(d, 3))
            g["meme"] = None
        elif gtype == "bruh":
            g["sfx"] = [("bruh", b["t"])]
        elif gtype == "text":
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
            g["sfx"] = [("bruh" if sent == "dead" and "bruh" in sfx else "pop", b["t"])]
        elif gtype == "womp":
            g["sfx"] = [("womp", b["t"])]
            g["text"] = ("WOMP WOMP", b["t"] + 0.1, b["t"] + 1.3)
            used_text.add("WOMP WOMP")
        elif gtype == "crickets":
            g["sfx"] = [("crickets", b["t"])]
            g["text"] = ("...", b["t"] + 0.2, b["t"] + min(b.get("gap", 1.5), 1.6))
        elif gtype == "laughtrack":
            g["sfx"] = [("laugh", b["t"] - 0.05)]
        elif gtype == "damage":                       # "EMOTIONAL DAMAGE" — the sound says it, the word stays his
            g["sfx"] = [("damage", b["t"] - 0.03)]
            g["shake"] = 0.4 if cfg["shake"] else 0
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "buzz":                         # the Windows error on "broken / bugged / wrong"
            g["sfx"] = [("buzz", b["t"] - 0.02)]
            g["flash"] = cfg["flash"]
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "ohno":                         # the "oh no no no" laugh, right after the line
            g["sfx"] = [("ohno", b["end"])]
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "airhorn":
            g["sfx"] = [("airhorn", b["t"] - 0.03)]
            g["shake"] = 0.3 if cfg["shake"] else 0
            g["text"] = (pick_text(sent, tok, used_text), b["t"], b["t"] + TEXT_DUR)
        elif gtype == "button":
            # the metal pipe as an occasional button — funny once, not every Short
            snd = "pipe" if ("pipe" in sfx and intensity != "light" and rng.random() < 0.35) else "hit"
            g["sfx"] = [(snd, b["t"] - 0.03)]
            g["shake"] = 0.3 if cfg["shake"] else 0
            if intensity == "heavy" and "bassdrop" in sfx:
                g["sfx"].append(("bassdrop", max(0.0, dur - 1.8)))
        if not text_on:
            g["text"] = None
        # screen-time cap: overlays go first, sounds stay (the tail is appended time, not counted)
        ov = (g["text"][2] - g["text"][1] if g.get("text") else 0) + (g["meme"][2] - g["meme"][1] if g.get("meme") else 0)
        if screen + ov > cfg["screen"] * dur:
            g["text"], g["meme"] = None, None
        else:
            screen += ov
        g["sfx"] = [(tag, round(max(0.0, t), 3)) for tag, t in g["sfx"] if tag in sfx]
        if not (g["sfx"] or g.get("text") or g.get("meme") or g.get("tail") or g.get("hold") or g.get("bass")):
            continue                                        # nothing survived — not a gag
        gags.append(g)
        last_type = gtype
    gags.sort(key=lambda g: g["t"])

    # whooshes under punch-ins, unless a gag sound is already landing there
    sfx_times = [t for g in gags for _, t in g["sfx"]]
    whooshes = []
    if "whoosh" in sfx:
        for s, *_ in punchins:
            if s >= 0.3 and all(abs(s - t) > 0.25 for t in sfx_times):
                whooshes.append(round(max(0.0, s - 0.05), 3))
    # a notification ding when he reads chat / a comment — free, like the whooshes, at most two
    dings = []
    if "ding" in sfx and words and intensity != "light":
        for w in words:
            t = w["start"]
            if clean(w["text"]) in CHAT and 0.3 <= t <= dur - 0.5 and all(abs(t - x) > 0.5 for x in sfx_times) \
                    and all(t - d >= 4.0 for d in dings):
                dings.append(round(t - 0.1, 3))
                if len(dings) >= 2:
                    break
    # "extras" = free sounds that are not gags: (tag, t)
    return gags, [("whoosh", t) for t in whooshes] + [("ding", t) for t in dings]


# ----------------------------------------------------------------------------- rendering
def text_png(text, path, scale=1.0, rot=0.0):
    size = int((170 if len(text) <= 6 else 130 if len(text) <= 10 else 96) * scale * TEXT_SCALE)
    stroke = max(6, int(size * 0.075))
    font = ImageFont.truetype(FONT, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    # a long authored line wraps onto two centered lines rather than running off the frame
    if probe.textlength(text, font=font) > 1000 * TEXT_SCALE and " " in text:
        words = text.split()
        best = min(range(1, len(words)), key=lambda k: abs(probe.textlength(" ".join(words[:k]), font=font)
                                                            - probe.textlength(" ".join(words[k:]), font=font)))
        text = " ".join(words[:best]) + "\n" + " ".join(words[best:])
    bb = [int(round(v)) for v in probe.multiline_textbbox((0, 0), text, font=font, stroke_width=stroke, align="center")]
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad = 24
    img = Image.new("RGBA", (tw + 2 * pad + 12, th + 2 * pad + 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ox, oy = pad - bb[0], pad - bb[1]
    d.multiline_text((ox + 7, oy + 10), text, font=font, fill=(0, 0, 0, 150), stroke_width=stroke, stroke_fill=(0, 0, 0, 150), align="center")
    d.multiline_text((ox, oy), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255), align="center")
    if rot:
        img = img.rotate(rot, expand=True, resample=Image.BICUBIC)
    img.save(path)
    return img.size


def meme_png(src, region, path):
    """A still, centered on a blurred + darkened cover-crop of itself (same look as the clip cut-ins)."""
    from PIL import ImageFilter, ImageEnhance
    rx, ry, rw, rh = region
    im = Image.open(src).convert("RGBA")
    scale = max(rw / im.width, rh / im.height)
    bg = im.resize((max(rw, int(im.width * scale)), max(rh, int(im.height * scale))), Image.LANCZOS)
    bg = bg.crop(((bg.width - rw) // 2, (bg.height - rh) // 2, (bg.width - rw) // 2 + rw, (bg.height - rh) // 2 + rh))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(24))).enhance(0.6)
    canvas = Image.new("RGBA", (rw, rh), (0, 0, 0, 255))
    canvas.paste(bg, (0, 0))
    im.thumbnail((rw - 40, rh - 40), Image.LANCZOS)
    canvas.paste(im, ((rw - im.width) // 2, (rh - im.height) // 2), im)
    canvas.save(path)


def flash_png(path):
    Image.new("RGBA", (W, H), (255, 30, 30, 78)).save(path)


def pin_png(text, path):
    """The pinned-chat hook: 'name: message' in a dark rounded box, name in orange — the look of the
    chat pin his editor puts at the top for the first ~3 s (8 of 17 studied Shorts open on one)."""
    name, _, msg = text.partition(":")
    name, msg = name.strip(), msg.strip()
    font = ImageFont.truetype(FONT_BOLD, 34)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    # wrap the message to ~880 px
    words, lines, cur = msg.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if probe.textlength(t, font=font) > 880 - probe.textlength(name + ": ", font=font) * (0 if lines else 1):
            lines.append(cur); cur = w
        else:
            cur = t
    lines.append(cur)
    pad, lh = 22, 44
    tw = max(probe.textlength((name + ": " if i == 0 else "") + ln, font=font) for i, ln in enumerate(lines))
    img = Image.new("RGBA", (int(tw) + 2 * pad, lh * len(lines) + 2 * pad - 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=14, fill=(12, 12, 14, 215))
    for i, ln in enumerate(lines):
        x, y = pad, pad - 4 + i * lh
        if i == 0:
            d.text((x, y), name + ":", font=font, fill=(255, 140, 0, 255))
            x += probe.textlength(name + ": ", font=font)
        d.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
    img.save(path)
    return img.size


def render_tail(meme, D, fps, path):
    """Pre-render the ending clip: full-frame on a blurred cover-crop of itself, its own audio at −6 dB
    (silence if it has none), both fading out over the last 0.4 s."""
    has_a = bool(meme.get("audio"))
    src = ["-stream_loop", "-1", "-i", meme["path"]] if meme["animated"] else ["-loop", "1", "-i", meme["path"]]
    st = max(0.0, D - 0.4)
    fc = (f"[0:v]format=rgba,split[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,"
          f"eq=brightness=-0.18[b];[fg]scale={W - 40}:{H - 40}:force_original_aspect_ratio=decrease[f];"
          f"[b][f]overlay=(W-w)/2:(H-h)/2,fps={fps:g},format=yuv420p,setsar=1,fade=t=out:st={st:.3f}:d=0.4[v];"
          f"[{'0' if has_a else '1'}:a]{AFMT},volume=-6dB,afade=t=out:st={st:.3f}:d=0.4[a]")
    run(FFMPEG + src + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-t", f"{D:.3f}", *ENC, "-c:a", "aac", "-b:a", "256k", path])
    return path


def measure_lufs(path):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-vn", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    return float(m[-1]) if m else None


def render(video_in, out, gags, extras, layout, dur, work, sfx, style="reference", pin=None, loudness=None, gain_db=None,
           sfx_trim=0.0, overlays=()):
    os.makedirs(work, exist_ok=True)
    fps = ffprobe_fps(video_in)
    freezes = sorted((g["t"], g["hold"]) for g in gags if g["type"] == "freeze")
    tail = next((g["tail"] for g in gags if g.get("tail")), None)

    def to_out(t):                      # original clip time → output time (after inserted holds)
        return t + sum(D for tf, D in freezes if tf < t - 1e-3)

    new_dur = dur + sum(D for _, D in freezes)
    # -reinit_filter 0 (patch 4): a stitched base whose colour tags flip between segments must NOT rebuild the
    # graph mid-stream — the rebuilt trim/concat splice restarts at pts 0 and everything after is dropped
    inputs, fc, nin = ["-reinit_filter", "0", "-i", video_in], [], 1

    # ---- video + audio base, with freeze holds spliced in (video: loop the frame; audio: silence)
    pieces, cur = [], 0.0
    for tf, D in freezes:
        pieces += [("n", cur, tf), ("h", tf, D)]
        cur = tf
    pieces.append(("n", cur, dur))
    pieces = [p for p in pieces if p[0] == "h" or p[2] - p[1] > 0.01]
    afc_base = []      # the audio side of the splice: Shorts → into the single graph; long-form → pass 2 (patch 3)
    A = afc_base.append if dur > TWO_PASS_OVER else fc.append
    if len(pieces) == 1:
        fc.append("[0:v]setpts=PTS-STARTPTS[vc]")
        A(f"[0:a]{AFMT},asetpts=PTS-STARTPTS[ac]")
    else:
        nn = sum(1 for p in pieces if p[0] == "n")
        fc.append(f"[0:v]split={len(pieces)}" + "".join(f"[v{i}]" for i in range(len(pieces))))
        A(f"[0:a]{AFMT},asplit={nn}" + "".join(f"[a{i}]" for i in range(nn)))
        ai, vl, al = 0, [], []
        for i, p in enumerate(pieces):
            if p[0] == "n":
                fc.append(f"[v{i}]trim=start={p[1]:.3f}:end={p[2]:.3f},setpts=PTS-STARTPTS[p{i}]")
                A(f"[a{ai}]atrim=start={p[1]:.3f}:end={p[2]:.3f},asetpts=PTS-STARTPTS[q{i}]")
                ai += 1
            else:
                n = int(math.ceil(p[2] * fps)) + 5
                fc.append(f"[v{i}]trim=start={p[1]:.3f}:end={p[1] + 0.1:.3f},setpts=PTS-STARTPTS,"
                          f"loop=loop={n}:size=1:start=0,trim=duration={p[2]:.3f},setpts=PTS-STARTPTS[p{i}]")
                A(f"anullsrc=r=48000:cl=stereo,{AFMT},atrim=duration={p[2]:.3f}[q{i}]")
            vl.append(f"[p{i}]")
            al.append(f"[q{i}]")
        fc.append("".join(vl) + f"concat=n={len(pieces)}:v=1:a=0[vc]")
        A("".join(al) + f"concat=n={len(pieces)}:v=0:a=1[ac]")
    last = "vc"

    # ---- camera shake: a 5 % oversized copy jittered over the frame inside the windows
    shakes = [(to_out(g["t"]), to_out(g["t"]) + g["shake"]) for g in gags if g.get("shake")]
    if shakes:
        en = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in shakes)
        sx, sy = int(W * 0.05), int(H * 0.05)
        fc.append(f"[{last}]split[sa][sb];[sb]scale={W + sx}:{H + sy}[sz];"
                  f"[sa][sz]overlay=x='-{sx // 2}+{sx // 4}*sin(t*83)':y='-{sy // 2}+{sy // 4}*sin(t*97)':enable='{en}'[vs]")
        last = "vs"

    # ---- red flash on booms (one shared PNG, all windows in one enable)
    flashes = [to_out(g["t"]) for g in gags if g.get("flash")]
    if flashes:
        fp = os.path.join(work, "flash.png")
        flash_png(fp)
        inputs += ["-loop", "1", "-i", fp]
        en = "+".join(f"between(t,{a:.3f},{a + FLASH_DUR:.3f})" for a in flashes)
        fc.append(f"[{last}][{nin}:v]overlay=0:0:enable='{en}'[vfl]")
        last, nin = "vfl", nin + 1

    # ---- text pops: two frames big (the pop), then normal
    k = 0
    for g in gags:
        if not g.get("text"):
            continue
        text, a, b = g["text"]
        a, b = to_out(a), to_out(b)
        rot = (-3.0, 2.5, -2.0, 3.0)[k % 4]
        cy = TEXT_CY[layout]
        for j, (scale, wa, wb) in enumerate(((1.14, a, a + 0.05), (1.0, a + 0.05, b))):
            p = os.path.join(work, f"text{k:02d}_{j}.png")
            tw, th = text_png(text, p, scale, rot)
            inputs += ["-loop", "1", "-i", p]
            fc.append(f"[{last}][{nin}:v]overlay={W // 2 - tw // 2}:{cy - th // 2}:enable='between(t,{wa:.3f},{wb:.3f})'[vt{k}{j}]")
            last, nin = f"vt{k}{j}", nin + 1
        k += 1

    # ---- the pinned-chat hook (first PIN_UNTIL seconds), above everything else
    if pin:
        pp = os.path.join(work, "pin.png")
        pin_png(pin, pp)
        inputs += ["-loop", "1", "-i", pp]
        fc.append(f"[{last}][{nin}:v]overlay=30:430:enable='between(t,0,{PIN_UNTIL:.2f})'[vpin]")
        last, nin = "vpin", nin + 1

    # ---- authored positioned overlays: (png, x, y, t0, t1) in clip time — the chat cards of a cold open
    for k, (png, ox, oy, a, b) in enumerate(overlays):
        inputs += ["-loop", "1", "-i", png]
        fc.append(f"[{last}][{nin}:v]overlay={int(ox)}:{int(oy)}:enable='between(t,{to_out(a):.3f},{to_out(b):.3f})'[vo{k}]")
        last, nin = f"vo{k}", nin + 1

    # ---- meme cut-ins: stills as PNG overlays; GIF/MP4 shifted with setpts and looped. A clip
    #      with its own audio (a vlip) brings that audio into the mix for the length of the cut-in.
    #      the reference channel style = full-frame (cut away to the clip); tiktok style = inset in a box.
    rx, ry, rw, rh = (0, 0, W, H) if STYLE[style]["meme_full"] else MEME_REGION[layout]
    meme_audio = []                      # (input index, t_out, duration)
    for k, g in enumerate(gags):
        if not g.get("meme"):
            continue
        m, a, b = g["meme"]
        a, b = to_out(a), to_out(b)
        if m["animated"]:
            inputs += ["-stream_loop", "-1", "-i", m["path"]]
            # a 16:9 clip in a near-square box: fill the box with a blurred, darkened copy of itself
            # (the standard vertical-video treatment) and center the clip on top — no dead black bars
            fc.append(f"[{nin}:v]format=rgba,split[mbg{k}][mfg{k}];"
                      f"[mbg{k}]scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},boxblur=24:2,"
                      f"eq=brightness=-0.18[mb{k}];"
                      f"[mfg{k}]scale={rw - 40}:{rh - 40}:force_original_aspect_ratio=decrease[mf{k}];"
                      f"[mb{k}][mf{k}]overlay=(W-w)/2:(H-h)/2,setpts=PTS-STARTPTS+{a:.3f}/TB[mm{k}]")
            fc.append(f"[{last}][mm{k}]overlay={rx}:{ry}:eof_action=pass:enable='between(t,{a:.3f},{b:.3f})'[vm{k}]")
            if m.get("audio"):
                meme_audio.append((nin, a, b - a))
        else:
            p = os.path.join(work, f"meme{k:02d}.png")
            meme_png(m["path"], (rx, ry, rw, rh), p)
            inputs += ["-loop", "1", "-i", p]
            fc.append(f"[{last}][{nin}:v]overlay={rx}:{ry}:enable='between(t,{a:.3f},{b:.3f})'[vm{k}]")
        last, nin = f"vm{k}", nin + 1

    # ---- sounds: each file → level → delay → one amix (normalize=0 keeps the voice untouched)
    sounds = [(tag, t) for g in gags for tag, t in g["sfx"]] + list(extras)
    two_pass = dur > TWO_PASS_OVER
    if two_pass:
        # LONG-FORM (2026-09-13): mixing 40+ delayed sound inputs inside the video graph silently lost every
        # sound after the first few seconds (ffmpeg rc 0). The sounds go into their own audio pass below;
        # this pass carries the spliced base audio untouched. Reaction-clip audio is remembered by path.
        meme_audio_spec = []
        for (idx, a, d) in meme_audio:
            # the input list is [..., "-stream_loop", "-1", "-i", path, ...]; find the path for input idx
            k = 0; path = None
            it = iter(range(len(inputs)))
            for i in it:
                if inputs[i] == "-i":
                    if k == idx:
                        path = inputs[i + 1]
                    k += 1
            meme_audio_spec.append((path, a, d))
        labels = []
    else:
        labels = []
        for k, (tag, t) in enumerate(sounds):
            path = sfx[tag]
            gain = (-3.0 - sfx_peak_db(path)) + SFX_GAIN.get(tag, -9) + sfx_trim      # sfx_trim = the global level the creator sets
            inputs += ["-i", path]
            fc.append(f"[{nin}:a]{AFMT},volume={gain:.1f}dB,adelay=delays={int(round(to_out(t) * 1000))}:all=1[s{k}]")
            labels.append(f"[s{k}]")
            nin += 1
        for k, (idx, a, d) in enumerate(meme_audio):
            # the clip's own sound, for exactly the cut-in window, with a 60 ms fade out so it never clicks
            fc.append(f"[{idx}:a]{AFMT},atrim=0:{d:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, d - 0.06):.3f}:d=0.06,"
                      f"volume=-6dB,adelay=delays={int(round(a * 1000))}:all=1[ma{k}]")
            labels.append(f"[ma{k}]")
    am = "ac"
    if labels:
        fc.append(f"[ac]{''.join(labels)}amix=inputs={len(labels) + 1}:normalize=0:duration=first:dropout_transition=0[am]")
        am = "am"
    chain = []
    for g in gags:
        if g.get("bass"):
            a, b = to_out(g["bass"][0]), to_out(g["bass"][1])
            win = f"enable='between(t,{a:.3f},{b:.3f})'"
            chain += [f"bass=g=12:f=100:w=0.6:{win}", f"acrusher=bits=6:mode=log:mix=0.5:{win}", f"volume=5dB:{win}"]
    if loudness is not None:
        # Shorts live around -14 LUFS; the base cut sits near -21. A STATIC gain to the target and the
        # true-peak limiter below — no dynamic loudnorm, which pumps. The first pass estimates the gain
        # from the input; run_gags measures the delivered file and re-renders once with the corrected
        # gain (the sounds add energy the input measurement cannot see).
        if gain_db is None:
            lufs_in = measure_lufs(video_in)
            gain_db = (loudness - lufs_in) if lufs_in is not None else 0.0
            log(f"  loudness: input {lufs_in:.1f} LUFS → target {loudness:.0f} LUFS ({gain_db:+.1f} dB, limiter at -1 dBTP)")
        chain.append(f"volume={gain_db:.1f}dB")
    render.gain_db = gain_db                      # what this pass applied (run_gags corrects on the second pass)
    if two_pass:
        chain = []          # the whole audio treatment (bass, gain, limiter) happens in pass 2
    else:
        chain.append("alimiter=limit=0.891:level=0:attack=2:release=60:latency=1")
    if tail and two_pass:
        log("  two-pass render: the reaction-clip ending is a Shorts feature, skipped on a long input")
        tail = None
    if tail:
        # ---- the ending: append the pre-rendered reaction clip after everything else
        meme, D = tail
        tp = render_tail(meme, D, fps, os.path.join(work, "tail.mp4"))
        inputs += ["-i", tp]
        fc.append(f"[{am}]{','.join(chain)}[apre]")
        # concat demands identical geometry AND sample aspect ratio — the crop/scale chains leave
        # near-1:1 SARs (944:945 vs 76480:76433 on the first try) that it rejects, so pin both to 1:1
        fc.append(f"[{last}]format=yuv420p,setsar=1[vmain];[{nin}:v]format=yuv420p,setsar=1[vtail];"
                  f"[vmain][vtail]concat=n=2:v=1:a=0[vout]")
        fc.append(f"[{nin}:a]{AFMT}[atail];[apre][atail]concat=n=2:v=0:a=1[aout]")
        last, nin = "vout", nin + 1
        new_dur += D
    else:
        fc.append(f"[{am}]{','.join(chain)}[aout]")

    if two_pass:
        # pass 1 is VIDEO ONLY (patch 3, 2026-09-15): with the audio splice inside this graph a 30-min render came
        # out with 1551 s of audio under 1785 s of video, rc 0. The audio is built in pass 2 from the input.
        assert fc[-1].endswith("[aout]"), fc[-1]
        fc.pop()
    video_pass = os.path.join(work, "pass1_video.mp4") if two_pass else out
    cmd = FFMPEG + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]",
                             *([] if two_pass else ["-map", "[aout]"]),
                             "-t", f"{new_dur:.3f}", "-r", f"{fps:g}", *ENC,
                             *(["-an"] if two_pass else ["-c:a", "aac", "-b:a", "256k"]),
                             "-movflags", "+faststart", video_pass]
    with open(os.path.join(work, "ffmpeg-cmd.txt"), "w") as f:
        f.write(" ".join(f"'{c}'" if " " in str(c) or ";" in str(c) else str(c) for c in cmd))
    json.dump(cmd, open(os.path.join(work, "ffmpeg-cmd.json"), "w"))
    run(cmd)
    if two_pass:
        # pass 2: the whole audio track from the INPUT — freeze splice + sounds + reaction-clip audio + chain —
        # exactly the standalone graph that shipped 9/13; then a stream-copy mux onto the pass-1 video
        ainputs, afc, n2, alabels = ["-reinit_filter", "0", "-i", video_in], list(afc_base), 1, []
        for k, (tag, t) in enumerate(sounds):
            path = sfx[tag]
            gain = (-3.0 - sfx_peak_db(path)) + SFX_GAIN.get(tag, -9) + sfx_trim
            ainputs += ["-i", path]
            afc.append(f"[{n2}:a]{AFMT},volume={gain:.1f}dB,adelay=delays={int(round(to_out(t) * 1000))}:all=1[s{k}]")
            alabels.append(f"[s{k}]"); n2 += 1
        for k, (path, a, d) in enumerate(meme_audio_spec):
            ainputs += ["-stream_loop", "-1", "-i", path]
            afc.append(f"[{n2}:a]{AFMT},atrim=0:{d:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, d - 0.06):.3f}:d=0.06,"
                       f"volume=-6dB,adelay=delays={int(round(a * 1000))}:all=1[ma{k}]")
            alabels.append(f"[ma{k}]"); n2 += 1
        a_last = "ac"
        if alabels:
            afc.append(f"[ac]{''.join(alabels)}amix=inputs={len(alabels) + 1}:normalize=0:duration=first:dropout_transition=0[am]")
            a_last = "am"
        achain = []
        for g in gags:
            if g.get("bass"):
                a, b = to_out(g["bass"][0]), to_out(g["bass"][1])
                win = f"enable='between(t,{a:.3f},{b:.3f})'"
                achain += [f"bass=g=12:f=100:w=0.6:{win}", f"acrusher=bits=6:mode=log:mix=0.5:{win}", f"volume=5dB:{win}"]
        if gain_db is not None and loudness is not None:
            achain.append(f"volume={gain_db:.1f}dB")
        achain.append("alimiter=limit=0.891:level=0:attack=2:release=60:latency=1")
        afc.append(f"[{a_last}]{','.join(achain)}[aout]")
        awav = os.path.join(work, "pass2_audio.wav")
        acmd = FFMPEG + ainputs + ["-filter_complex", ";".join(afc), "-map", "[aout]", "-t", f"{new_dur:.3f}", "-c:a", "pcm_s16le", awav]
        json.dump(acmd, open(os.path.join(work, "ffmpeg-cmd-pass2.json"), "w"))
        run(acmd)
        run(FFMPEG + ["-i", video_pass, "-i", awav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                      "-t", f"{new_dur:.3f}", "-movflags", "+faststart", out])
        os.remove(video_pass)
    return new_dur, [(tf, D) for tf, D in freezes]


# ----------------------------------------------------------------------------- driver
def describe(gags, extras):
    lines = []
    for g in gags:
        bits = [g["type"]]
        if g.get("text"):
            bits.append(f'"{g["text"][0]}"')
        if g.get("meme"):
            bits.append(f"{os.path.basename(g['meme'][0]['path'])} {g['meme'][2] - g['meme'][1]:.1f}s")
        if g.get("tail"):
            bits.append(f"ends on {os.path.basename(g['tail'][0]['path'])} {g['tail'][1]:.1f}s + fade")
        if g.get("hold"):
            bits.append(f"hold {g['hold']}s")
        if g["sfx"]:
            bits.append("sfx:" + "+".join(t for t, _ in g["sfx"]))
        lines.append(f"    {g['t']:6.2f}s  {' '.join(bits):48s} ← {g['beat']} {g['sentiment']} ({g['why']})")
    for tag in sorted({x for x, _ in extras}, key=lambda x: (x not in ("whoosh", "ding"), x)):
        ts = [t for x, t in extras if x == tag]
        lines.append(f"    {tag} at {', '.join(f'{t:.1f}' for t in ts)}"
                     + {"whoosh": " (under punch-ins)", "ding": " (reading chat)"}.get(tag, " (authored)"))
    return "\n".join(lines) if lines else "    (nothing — the clip carries itself)"


def shift_words(words, time_map):
    """Push transcript words past each inserted hold so captions stay on-beat."""
    out = []
    for w in words:
        s, e = w["start"], w["end"]
        ds = sum(D for tf, D in time_map if tf < s - 1e-3)
        de = sum(D for tf, D in time_map if tf < e - 1e-3)
        out.append({**w, "start": round(s + ds, 3), "end": round(e + de, 3)})
    return out


def insert_item(spec):
    """'12.5:path/to/file[:2.5]' → (t, meme-dict, dur) for a creator-placed full-frame cut-in."""
    parts = spec.split(":")
    t = float(parts[0])
    path = ":".join(parts[1:-1]) if len(parts) > 2 and re.fullmatch(r"[\d.]+", parts[-1]) else ":".join(parts[1:])
    d = float(parts[-1]) if len(parts) > 2 and re.fullmatch(r"[\d.]+", parts[-1]) else 2.5
    if not os.path.isfile(path):
        raise SystemExit(f"[gags] --insert: no such file {path}")
    ext = os.path.splitext(path)[1].lower()
    animated = ext in (".gif", ".mp4", ".mov", ".webm")
    return t, {"path": path, "tags": {"insert"}, "animated": animated,
               "audio": animated and ext != ".gif" and has_audio(path), "dur": ffprobe_dur(path) if animated else None}, d


def authored_gags(inserts=(), texts=(), freezes=()):
    """CLI specs → fixed gag dicts. inserts 't:file[:dur]', texts 'TEXT@t[:dur]', freezes 't[:hold]'."""
    out = [fixed_insert(*insert_item(s)) for s in inserts]
    for s in texts:
        text, _, rest = s.rpartition("@")
        t, _, d = rest.partition(":")
        out.append(fixed_text(text, float(t), float(d) if d else TEXT_DUR))
    for s in freezes:
        t, _, h = s.partition(":")
        out.append(fixed_freeze(float(t), float(h) if h else FREEZE_HOLD))
    return out


def parse_sfx(spec):
    """'tick@5.0,tick@6.0,pipe@12' → [(tag, t), …]"""
    out = []
    for item in [x.strip() for x in spec.split(",") if x.strip()]:
        tag, _, t = item.partition("@")
        out.append((tag.strip(), float(t)))
    return out


def run_gags(clip_dir, video_in, video_out, words, layout, punchins, intensity, dur, seed=None,
             style="reference", text_pops=None, pin=None, fixed_gags=(), no_memes=False, extra_sfx=(), loudness=None,
             sfx_trim=0.0, overlays=()):
    """Plan + render. Returns meta: gags, extras, time_map, duration (may be longer than `dur`).
    fixed_gags = authored gags (fixed_insert / fixed_text / fixed_freeze); extra_sfx = authored (tag, t) sounds."""
    work = os.path.join(clip_dir, "assemble_work", "gags")
    os.makedirs(work, exist_ok=True)
    sfx, memes = sfx_library(), ([] if no_memes else meme_library())
    rng = random.Random(seed or os.path.basename(clip_dir.rstrip("/")))
    env = audio_envelope(video_in, work)
    beats, med, bed = detect_beats(words, env, dur)
    if intensity == "off":
        gags, extras = list(fixed_gags), []
        for g in gags:
            g["sfx"] = [(tag, t) for tag, t in g["sfx"] if tag in sfx]
    else:
        gags, extras = plan_gags(beats, punchins, dur, intensity, sfx, memes, layout, rng, words, style, text_pops, fixed_gags, bed,
                                 blocked=[float(t) for _, t in extra_sfx])
    for tag, t in extra_sfx:
        if tag in sfx:
            extras.append((tag, round(float(t), 3)))
        else:
            log(f"  --sfx: no sound tagged {tag!r} in assets/sfx (have: {', '.join(sorted(sfx))})")
    log(f"{len(beats)} beats (speech median {med:.0f} dB{', game-audio bed' if bed else ''}), {len(sfx)} sounds, "
        f"{len(memes)} memes → {len(gags)} gags [{intensity}, {style}{', pinned chat' if pin else ''}"
        f"{', ' + str(len(fixed_gags)) + ' authored' if fixed_gags else ''}]")
    print(describe(gags, extras))
    if not gags and not extras and not pin and not overlays and loudness is None:
        # nothing to do: pass the reframe through untouched (stream copy)
        run(FFMPEG + ["-i", video_in, "-c", "copy", "-movflags", "+faststart", video_out])
        new_dur, time_map = dur, []
    else:
        new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, None, sfx_trim, overlays)
        if loudness is not None:
            got = measure_lufs(video_out)
            if got is not None and abs(got - loudness) > 0.5 and render.gain_db is not None:
                # second pass with the gain corrected by what the first one actually delivered
                corrected = render.gain_db + (loudness - got)
                log(f"  loudness: first pass delivered {got:.1f} LUFS → re-rendering at {corrected:+.1f} dB")
                new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, corrected, sfx_trim, overlays)
                got = measure_lufs(video_out)
            if got is not None:
                log(f"  loudness: delivered {got:.1f} LUFS")
    meta = {"intensity": intensity, "style": style, "pin": pin or "", "speech_median_db": round(med, 1), "beats": beats,
            "gags": [{k: (v if k not in ("meme", "tail") or v is None else
                          ((v[0]["path"], v[1], v[2]) if k == "meme" else (v[0]["path"], v[1]))) for k, v in g.items()} for g in gags],
            "extras": extras, "time_map": time_map, "duration": round(new_dur, 3)}
    json.dump(meta, open(os.path.join(clip_dir, "gags.json"), "w"), indent=1)
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip_dir")
    ap.add_argument("--intensity", choices=["off", "light", "medium", "heavy"], default="medium")
    ap.add_argument("--style", choices=list(STYLE), default="reference")
    ap.add_argument("--text-pops", choices=["on", "off"], default=None, help="override the style's text-pop setting")
    ap.add_argument("--pin", default=None, help='pinned-chat hook for the first 3 s: "name: message"')
    ap.add_argument("--insert", action="append", default=[], metavar="t:file[:dur]", help="creator-placed full-frame cut-in")
    ap.add_argument("--text", action="append", default=[], metavar="TEXT@t[:dur]", help="authored text pop")
    ap.add_argument("--freeze", action="append", default=[], metavar="t[:hold]", help="authored freeze-frame + record scratch")
    ap.add_argument("--sfx", default="", metavar="tag@t,tag@t", help="authored sounds by tag (assets/sfx)")
    ap.add_argument("--no-memes", action="store_true", help="no clip cut-ins and no clip ending")
    ap.add_argument("--in", dest="inp", default=None, help="default outputs/<clip>.reframed.mp4 (else outputs/<clip>.mp4)")
    ap.add_argument("--out", default=None, help="default outputs/<clip>.mp4")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    text_pops = None if args.text_pops is None else args.text_pops == "on"
    fixed = authored_gags(args.insert, args.text, args.freeze)
    extra_sfx = parse_sfx(args.sfx)
    cdir = os.path.abspath(args.clip_dir)
    clip = os.path.basename(cdir)
    meta = json.load(open(os.path.join(cdir, "clip.json")))
    tj = json.load(open(os.path.join(cdir, "outputs", f"{clip}.transcript.json")))
    words = [w for w in tj["words"] if w.get("type", "word") == "word" and w.get("text", "").strip()]
    reframed = os.path.join(cdir, "outputs", f"{clip}.reframed.mp4")
    if args.inp:
        inp = args.inp
    elif os.path.isfile(reframed):
        inp = reframed
    elif meta.get("gags", "off") != "off" and not args.plan_only:
        # finalize.sh retires the .reframed.mp4 draft; outputs/<clip>.mp4 already carries the gags
        raise SystemExit(f"[gags] {reframed} is gone (finalized) and outputs/{clip}.mp4 is already gagged — "
                         f"re-run the clipper for this window instead of gagging twice")
    else:
        inp = os.path.join(cdir, "outputs", f"{clip}.mp4")
    dur = ffprobe_dur(inp)
    if args.plan_only:
        if inp.endswith(f"{clip}.mp4") and meta.get("gags", "off") != "off":
            print(f"NOTE: analyzing outputs/{clip}.mp4, which already carries this clip's gags — its sounds inflate "
                  f"the loudness beats; a real rebuild starts from a clean reframe.")
        work = os.path.join(cdir, "assemble_work", "gags")
        env = audio_envelope(inp, work)
        beats, med, bed = detect_beats(words, env, dur)
        print(f"BEATS (speech median {med:.0f} dB{', game-audio bed' if bed else ''}):")
        for b in beats:
            print(f"    {b['t']:6.2f}s  {b['kind']:8s} {b['score']:4.1f}  {b['sentiment'] or '-':8s} {b['text']}  rms {b['rms']}"
                  + ("  LOUD" if b['loud'] else ""))
        sfx, memes = sfx_library(), meme_library()
        memes = [] if args.no_memes else memes
        gags, extras = plan_gags(beats, meta.get("punch_ins", []), dur, args.intensity, sfx, memes, meta["layout"],
                                 random.Random(clip), words, args.style, text_pops, fixed, bed)
        print(f"PLAN [{args.intensity}, {args.style}] ({len(sfx)} sounds, {len(memes)} memes):")
        print(describe(gags, extras + [(t, x) for t, x in extra_sfx if t in sfx]))
        return
    out = args.out or os.path.join(cdir, "outputs", f"{clip}.mp4")
    if os.path.abspath(out) == os.path.abspath(inp):
        raise SystemExit("[gags] --in and --out are the same file; keep the reframe as outputs/<clip>.reframed.mp4")
    run_gags(cdir, inp, out, words, meta["layout"], meta.get("punch_ins", []), args.intensity, dur,
             style=args.style, text_pops=text_pops, pin=args.pin, fixed_gags=fixed, no_memes=args.no_memes, extra_sfx=extra_sfx)
    print(f"[gags] → {out}")


if __name__ == "__main__":
    main()
