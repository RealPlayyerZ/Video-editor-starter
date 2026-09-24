#!/usr/bin/env python3
"""Patch 4 (2026-09-15): `-reinit_filter 0` on the base input of the gags render.

A base made of stitched segments (apply-zoom's zoom re-encodes over splice_segments.py's per-segment
encodes) carried DIFFERENT colour tags per segment (unknown vs tv/bt709). When the tag flips mid-stream,
ffmpeg rebuilds the whole filter graph; the rebuilt trim/setpts/concat splice restarts its clock at 0, every
later frame is dropped as "in the past" (verbose log: "*** dropping frame N at ts 0, 1, 2…"), and the
never-ending overlay inputs pad the output with the last frame until -t (division2-legendary-mission:
frozen from 1601 s to the end, rc 0). -reinit_filter 0 keeps the graph; the encoder takes the first frame's
tags. Proven on a 300 s excerpt: 0 drops, 0 reconfigures, full frame count. Idempotent."""
import os, shutil, sys

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts", "gags.py")
s = open(p).read()
if '"-reinit_filter", "0"' in s:
    print("already patched"); sys.exit(0)
shutil.copy(p, p + ".bak-20260915b")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (old[:70], s.count(old))
    s = s.replace(old, new)


rep('''    inputs, fc, nin = ["-i", video_in], [], 1''',
    '''    # -reinit_filter 0 (patch 4): a stitched base whose colour tags flip between segments must NOT rebuild the
    # graph mid-stream — the rebuilt trim/concat splice restarts at pts 0 and everything after is dropped
    inputs, fc, nin = ["-reinit_filter", "0", "-i", video_in], [], 1''')
rep('''        ainputs, afc, n2, alabels = ["-i", video_in], list(afc_base), 1, []''',
    '''        ainputs, afc, n2, alabels = ["-reinit_filter", "0", "-i", video_in], list(afc_base), 1, []''')
open(p, "w").write(s)
print("gags.py reinit patch applied (backup gags.py.bak-20260915b)")
