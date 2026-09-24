#!/usr/bin/env python3
"""Patch 2 (2026-09-13): long-form renders mix the sounds in a SEPARATE audio pass.

Found on division2-legendary-mission: in the single ffmpeg graph (video overlays + freeze splice +
49 delayed sound inputs into one amix), every sound after the first ~6 s silently never reached the
mix — ffmpeg exits 0, the log is clean. The identical audio graph run on its own (no video branch)
mixes every sound. So for long inputs render() now does: pass 1 = the video graph with the spliced
base audio only; pass 2 = the audio graph (spliced base + sounds + reaction-clip audio + bass chain +
limiter) on its own; then a stream-copy mux. Shorts (dur <= 120 s) keep the proven single pass.
Idempotent."""
import os, shutil, sys

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts", "gags.py")
s = open(p).read()
if "TWO_PASS_OVER" in s:
    print("already patched"); sys.exit(0)
shutil.copy(p, p + ".bak-20260913b")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (old[:70], s.count(old))
    s = s.replace(old, new)


rep('''MEME_MAX, TAIL_MIN, TAIL_MAX, PIN_UNTIL = 3.0, 1.5, 3.0, 3.0
''', '''MEME_MAX, TAIL_MIN, TAIL_MAX, PIN_UNTIL = 3.0, 1.5, 3.0, 3.0
TWO_PASS_OVER = 120.0     # inputs longer than this mix their sounds in a separate audio pass (see render())
''')

# In render(): split the sound mixing off into a function of the audio chain, and route long inputs
# through two passes. The single-pass code is kept verbatim for Shorts.
rep('''    # ---- sounds: each file → level → delay → one amix (normalize=0 keeps the voice untouched)
    sounds = [(tag, t) for g in gags for tag, t in g["sfx"]] + list(extras)
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
    if loudness is not None:''', '''    # ---- sounds: each file → level → delay → one amix (normalize=0 keeps the voice untouched)
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
    if loudness is not None:''')

rep('''    render.gain_db = gain_db                      # what this pass applied (run_gags corrects on the second pass)
    chain.append("alimiter=limit=0.891:level=0:attack=2:release=60:latency=1")''',
    '''    render.gain_db = gain_db                      # what this pass applied (run_gags corrects on the second pass)
    if two_pass:
        chain = []          # the whole audio treatment (bass, gain, limiter) happens in pass 2
    else:
        chain.append("alimiter=limit=0.891:level=0:attack=2:release=60:latency=1")''')

rep('''    cmd = FFMPEG + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[aout]",
                             "-t", f"{new_dur:.3f}", "-r", f"{fps:g}", *ENC, "-c:a", "aac", "-b:a", "256k",
                             "-movflags", "+faststart", out]
    with open(os.path.join(work, "ffmpeg-cmd.txt"), "w") as f:
        f.write(" ".join(f"'{c}'" if " " in str(c) or ";" in str(c) else str(c) for c in cmd))
    run(cmd)
    return new_dur, [(tf, D) for tf, D in freezes]''',
    '''    if two_pass and not chain:
        # pass 1 carries the spliced base audio as-is (PCM keeps it exact for pass 2)
        fc[-1] = f"[{am}]anull[aout]"
    video_pass = os.path.join(work, "pass1_video.mp4") if two_pass else out
    cmd = FFMPEG + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[aout]",
                             "-t", f"{new_dur:.3f}", "-r", f"{fps:g}", *ENC,
                             *(["-c:a", "pcm_s16le"] if two_pass else ["-c:a", "aac", "-b:a", "256k"]),
                             "-movflags", "+faststart", video_pass]
    with open(os.path.join(work, "ffmpeg-cmd.txt"), "w") as f:
        f.write(" ".join(f"'{c}'" if " " in str(c) or ";" in str(c) else str(c) for c in cmd))
    json.dump(cmd, open(os.path.join(work, "ffmpeg-cmd.json"), "w"))
    run(cmd)
    if two_pass:
        # pass 2: the same sound treatment as the single pass, on the pass-1 audio alone, then a stream-copy mux
        ainputs, afc, n2, alabels = ["-i", video_pass], [f"[0:a]{AFMT}[ac]"], 1, []
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
    return new_dur, [(tf, D) for tf, D in freezes]''')

# the tail (the reference channel ending clip) path appends video+audio inside the single graph — it is a Shorts feature;
# keep long-form from combining the two (a tail on a 30-min video is not a thing this style produces)
rep('''    if tail:
        # ---- the ending: append the pre-rendered reaction clip after everything else''',
    '''    if tail and two_pass:
        log("  two-pass render: the reaction-clip ending is a Shorts feature, skipped on a long input")
        tail = None
    if tail:
        # ---- the ending: append the pre-rendered reaction clip after everything else''')
open(p, "w").write(s)
print("gags.py two-pass patch applied (backup gags.py.bak-20260913b)")
