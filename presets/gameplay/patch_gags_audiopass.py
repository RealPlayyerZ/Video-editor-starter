#!/usr/bin/env python3
"""Patch 3 (2026-09-15): in the two-pass (long-form) render, pass 1 is VIDEO ONLY and pass 2 builds the whole
audio track from the INPUT — the freeze-hold splice (asplit/atrim/anullsrc/concat) included.

Patch 2 left the audio splice inside pass 1's video graph and had pass 2 read that PCM track back from
pass1_video.mp4. On the full 30-min division2-legendary-mission render that came out as 1551 s of audio under
1785 s of video (ffmpeg rc 0, clean log) — the same "audio branch inside the big video graph silently loses
data" class that patch 2 fixed for the sounds. The standalone audio graph from the input is the path that
shipped on 9/13 and produced the full length. Shorts (single pass) are byte-identical to before. Idempotent."""
import os, shutil, sys

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts", "gags.py")
s = open(p).read()
if "afc_base" in s:
    print("already patched"); sys.exit(0)
shutil.copy(p, p + ".bak-20260915")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (old[:70], s.count(old))
    s = s.replace(old, new)


rep('''    if len(pieces) == 1:
        fc.append("[0:v]setpts=PTS-STARTPTS[vc]")
        fc.append(f"[0:a]{AFMT},asetpts=PTS-STARTPTS[ac]")''',
'''    afc_base = []      # the audio side of the splice: Shorts → into the single graph; long-form → pass 2 (patch 3)
    A = afc_base.append if dur > TWO_PASS_OVER else fc.append
    if len(pieces) == 1:
        fc.append("[0:v]setpts=PTS-STARTPTS[vc]")
        A(f"[0:a]{AFMT},asetpts=PTS-STARTPTS[ac]")''')
rep('''        fc.append(f"[0:a]{AFMT},asplit={nn}" + "".join(f"[a{i}]" for i in range(nn)))''',
    '''        A(f"[0:a]{AFMT},asplit={nn}" + "".join(f"[a{i}]" for i in range(nn)))''')
rep('''                fc.append(f"[a{ai}]atrim=start={p[1]:.3f}:end={p[2]:.3f},asetpts=PTS-STARTPTS[q{i}]")''',
    '''                A(f"[a{ai}]atrim=start={p[1]:.3f}:end={p[2]:.3f},asetpts=PTS-STARTPTS[q{i}]")''')
rep('''                fc.append(f"anullsrc=r=48000:cl=stereo,{AFMT},atrim=duration={p[2]:.3f}[q{i}]")''',
    '''                A(f"anullsrc=r=48000:cl=stereo,{AFMT},atrim=duration={p[2]:.3f}[q{i}]")''')
rep('''        fc.append("".join(al) + f"concat=n={len(pieces)}:v=0:a=1[ac]")''',
    '''        A("".join(al) + f"concat=n={len(pieces)}:v=0:a=1[ac]")''')
rep('''    if two_pass and not chain:
        # pass 1 carries the spliced base audio as-is (PCM keeps it exact for pass 2)
        fc[-1] = f"[{am}]anull[aout]"
    video_pass = os.path.join(work, "pass1_video.mp4") if two_pass else out
    cmd = FFMPEG + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[aout]",
                             "-t", f"{new_dur:.3f}", "-r", f"{fps:g}", *ENC,
                             *(["-c:a", "pcm_s16le"] if two_pass else ["-c:a", "aac", "-b:a", "256k"]),
                             "-movflags", "+faststart", video_pass]''',
'''    if two_pass:
        # pass 1 is VIDEO ONLY (patch 3, 2026-09-15): with the audio splice inside this graph a 30-min render came
        # out with 1551 s of audio under 1785 s of video, rc 0. The audio is built in pass 2 from the input.
        assert fc[-1].endswith("[aout]"), fc[-1]
        fc.pop()
    video_pass = os.path.join(work, "pass1_video.mp4") if two_pass else out
    cmd = FFMPEG + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]",
                             *([] if two_pass else ["-map", "[aout]"]),
                             "-t", f"{new_dur:.3f}", "-r", f"{fps:g}", *ENC,
                             *(["-an"] if two_pass else ["-c:a", "aac", "-b:a", "256k"]),
                             "-movflags", "+faststart", video_pass]''')
rep('''        # pass 2: the same sound treatment as the single pass, on the pass-1 audio alone, then a stream-copy mux
        ainputs, afc, n2, alabels = ["-i", video_pass], [f"[0:a]{AFMT}[ac]"], 1, []''',
'''        # pass 2: the whole audio track from the INPUT — freeze splice + sounds + reaction-clip audio + chain —
        # exactly the standalone graph that shipped 9/13; then a stream-copy mux onto the pass-1 video
        ainputs, afc, n2, alabels = ["-i", video_in], list(afc_base), 1, []''')
open(p, "w").write(s)
print("gags.py audio-pass patch applied (backup gags.py.bak-20260915)")
