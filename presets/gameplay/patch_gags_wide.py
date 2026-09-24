#!/usr/bin/env python3
"""One-shot patch (2026-09-13): teach presets/shorts/gags.py a 16:9 long-form mode. Idempotent — exits
if the canvas() helper is already there. Backup written next to the file."""
import os, shutil, sys

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts", "gags.py")
s = open(p).read()
if "def canvas(" in s:
    print("gags.py already patched"); sys.exit(0)
shutil.copy(p, p + ".bak-20260913")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (old[:70], s.count(old))
    s = s.replace(old, new)


# 1. canvas + wide layout
rep('''W, H = 1080, 1920
''', '''W, H = 1080, 1920
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
''')
# 2. gameplay style (inset cut-ins, no tail, no auto text)
rep('''    "punchy":    dict(text_pops=False, flash=True, shake=True, meme_full=True, meme_tail=False),
}''', '''    "punchy":    dict(text_pops=False, flash=True, shake=True, meme_full=True, meme_tail=False),
    # "gameplay" (2026-09-13, long-form 16:9): the footage is the joke — reaction clips INSET bottom-left
    # (never covering the game), flash + shake on impacts, no automatic text pops, no clip ending
    "gameplay":  dict(text_pops=False, flash=True, shake=True, meme_full=False, meme_tail=False),
}''')
# 3. the creator's popping noise as its own tag (louder than the generic pop)
rep('''    "goofy": ["goofy", "yell"], "whistle": ["whistle", "slidewhistle"], "falling": ["falling", "cartoonfalling"],
}''', '''    "goofy": ["goofy", "yell"], "whistle": ["whistle", "slidewhistle"], "falling": ["falling", "cartoonfalling"],
    "popping": ["popping", "poppingnoise"],       # the creator's chat-message pop (D:/Videos/Youtube/Popping Sounds)
}''')
rep('''            "goofy": -6, "whistle": -8, "falling": -8}''', '''            "goofy": -6, "whistle": -8, "falling": -8, "popping": -4}''')
# 4. long-form density + several freezes/bass drops
rep('''    text_on = st["text_pops"] if text_pops is None else text_pops
    max_g = cfg["max_gags"](dur)''', '''    if dur > 120:
        # long-form (2026-09-13): the Shorts caps (8 gags, 3.5 s apart) make no sense over 20 minutes —
        # aim for one gag every ~25 s at medium, keep them well apart, overlays under 10 % of screen time
        per = {"light": 60.0, "medium": 25.0, "heavy": 14.0}[intensity]
        cfg["max_gags"] = lambda d, per=per: _clamp(round(d / per), 8, 120)
        cfg["gap"] = max(cfg["gap"], 6.0)
        cfg["screen"] = min(cfg["screen"], 0.10)
    once_max = 4 if dur > 120 else 1          # freeze-frames / bass drops: once per Short, a few per long-form
    text_on = st["text_pops"] if text_pops is None else text_pops
    max_g = cfg["max_gags"](dur)''')
rep('''    freeze_used = bass_used = False
''', '''    freeze_n = bass_n = 0
''')
rep('''            elif cfg["freeze"] and not freeze_used and sent == "shock" and "scratch" in sfx and b["t"] >= 1.5 and \\''',
    '''            elif cfg["freeze"] and freeze_n < once_max and sent == "shock" and "scratch" in sfx and b["t"] >= 1.5 and \\''')
rep('''            elif cfg["bass"] and not bass_used and b.get("very_loud"):''',
    '''            elif cfg["bass"] and bass_n < once_max and b.get("very_loud"):''')
rep('''        if gtype == "freeze":
            freeze_used = True
        if gtype == "bass":
            bass_used = True''', '''        if gtype == "freeze":
            freeze_n += 1
        if gtype == "bass":
            bass_n += 1''')
# 5. text scale for 16:9
rep('''    size = int((170 if len(text) <= 6 else 130 if len(text) <= 10 else 96) * scale)''',
    '''    size = int((170 if len(text) <= 6 else 130 if len(text) <= 10 else 96) * scale * TEXT_SCALE)''')
rep('''    if probe.textlength(text, font=font) > 1000 and " " in text:''',
    '''    if probe.textlength(text, font=font) > 1000 * TEXT_SCALE and " " in text:''')
# 6. shake scaled to the canvas
rep('''        fc.append(f"[{last}]split[sa][sb];[sb]scale={W + 54}:{H + 96}[sz];"
                  f"[sa][sz]overlay=x='-27+13*sin(t*83)':y='-48+11*sin(t*97)':enable='{en}'[vs]")''',
    '''        sx, sy = int(W * 0.05), int(H * 0.05)
        fc.append(f"[{last}]split[sa][sb];[sb]scale={W + sx}:{H + sy}[sz];"
                  f"[sa][sz]overlay=x='-{sx // 2}+{sx // 4}*sin(t*83)':y='-{sy // 2}+{sy // 4}*sin(t*97)':enable='{en}'[vs]")''')
# 7. generic positioned overlays (the chat cards of the cold open) + the render/run_gags plumbing
rep('''def render(video_in, out, gags, extras, layout, dur, work, sfx, style="reference", pin=None, loudness=None, gain_db=None,
           sfx_trim=0.0):''', '''def render(video_in, out, gags, extras, layout, dur, work, sfx, style="reference", pin=None, loudness=None, gain_db=None,
           sfx_trim=0.0, overlays=()):''')
rep('''    # ---- meme cut-ins: stills as PNG overlays; GIF/MP4 shifted with setpts and looped. A clip''',
    '''    # ---- authored positioned overlays: (png, x, y, t0, t1) in clip time — the chat cards of a cold open
    for k, (png, ox, oy, a, b) in enumerate(overlays):
        inputs += ["-loop", "1", "-i", png]
        fc.append(f"[{last}][{nin}:v]overlay={int(ox)}:{int(oy)}:enable='between(t,{to_out(a):.3f},{to_out(b):.3f})'[vo{k}]")
        last, nin = f"vo{k}", nin + 1

    # ---- meme cut-ins: stills as PNG overlays; GIF/MP4 shifted with setpts and looped. A clip''')
rep('''def run_gags(clip_dir, video_in, video_out, words, layout, punchins, intensity, dur, seed=None,
             style="reference", text_pops=None, pin=None, fixed_gags=(), no_memes=False, extra_sfx=(), loudness=None,
             sfx_trim=0.0):''', '''def run_gags(clip_dir, video_in, video_out, words, layout, punchins, intensity, dur, seed=None,
             style="reference", text_pops=None, pin=None, fixed_gags=(), no_memes=False, extra_sfx=(), loudness=None,
             sfx_trim=0.0, overlays=()):''')
rep('''        new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, None, sfx_trim)''',
    '''        new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, None, sfx_trim, overlays)''')
rep('''                new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, corrected, sfx_trim)''',
    '''                new_dur, time_map = render(video_in, video_out, gags, extras, layout, dur, work, sfx, style, pin, loudness, corrected, sfx_trim, overlays)''')
rep('''    if not gags and not extras and not pin and loudness is None:''',
    '''    if not gags and not extras and not pin and not overlays and loudness is None:''')
open(p, "w").write(s)
print("gags.py patched (backup: gags.py.bak-20260913)")
