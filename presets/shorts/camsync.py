#!/usr/bin/env python3
"""
camsync.py — pair a Stream Deck `Replay <ts>.mp4` with its `Cam <ts>.mp4` twin and align them.

Both files are "the last N seconds before the press", saved a fraction of a second apart by the
one Stream Deck key (main replay buffer → F9, then the Source Record filter's buffer → F10). So:
    replay t = 0   ↔   cam t = (cam_dur - replay_dur) - (cam_saved - replay_saved)      (coarse)
then the exact offset comes from cross-correlating the two audio envelopes (both carry OBS audio
track 3): 10 ms RMS envelopes, ±6 s search around the coarse value, 10 ms precision. On the first
real pair (2026-09-12) the coarse estimate was 99.88 s, the audio said 100.00 s, ncc 0.995.

  camsync.py pair "<Replay file>"            # find + align the twin, print the offset
  camsync.py align "<Replay>" "<Cam>"        # align two given files
"""
import glob, json, math, os, re, subprocess, sys

FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
PAIR_WINDOW = (-3.0, 20.0)      # a Cam file saved this long after the Replay is its twin


def ffprobe_dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout or 0)


def ffprobe_wh(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip().split(",")
    return int(o[0]), int(o[1])


def name_ts(p):
    """Seconds-of-day from 'YYYY-MM-DD hh-mm-ss' in the file name (None if absent)."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ _T](\d{2})-(\d{2})-(\d{2})", os.path.basename(p))
    if not m:
        return None
    d = int(m.group(3)) * 86400
    return d + int(m.group(4)) * 3600 + int(m.group(5)) * 60 + int(m.group(6))


def envelope(p, hop=0.01):
    """Linear-amplitude RMS envelope, one value per `hop` seconds (0 = digital silence)."""
    n = int(48000 * hop)
    meta = f"/tmp/camsync-env-{abs(hash(os.path.abspath(p)))}.txt"
    subprocess.run(FFMPEG + ["-i", p, "-vn", "-af",
                             f"aformat=channel_layouts=mono:sample_rates=48000,asetnsamples=n={n},astats=metadata=1:reset=1,"
                             f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file={meta}", "-f", "null", "-"])
    out = []
    for line in open(meta):
        m = re.search(r"RMS_level=(-?[\d.]+|-inf|inf|nan)", line)
        if m:
            v = m.group(1)
            out.append(0.0 if v in ("-inf", "inf", "nan") else 10 ** (float(v) / 20))
    os.remove(meta)
    return out


def _ncc(a, b, lag):
    xs, ys = [], []
    for i in range(len(a)):
        j = i + lag
        if 0 <= j < len(b):
            xs.append(a[i]); ys.append(b[j])
    if len(xs) < 500:
        return -1.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)); dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else -1.0


def align(replay, cam, search=6.0):
    """→ dict(offset, coarse, ncc, runner_up, trusted). offset: replay t=0 sits at cam t=offset."""
    rd, cd = ffprobe_dur(replay), ffprobe_dur(cam)
    rt, ct = name_ts(replay), name_ts(cam)
    coarse = (cd - rd) - ((ct - rt) if rt is not None and ct is not None else 0.0)
    er, ec = envelope(replay), envelope(cam)
    c0 = int(round(coarse * 100))
    if max(er) == 0.0 or max(ec) == 0.0:
        return {"offset": round(coarse, 3), "coarse": round(coarse, 3), "ncc": 0.0, "runner_up": 0.0, "trusted": False,
                "note": "one file is silent — offset from timestamps + durations only"}
    span = int(search * 100)
    best = max(((_ncc(er, ec, l), l) for l in range(c0 - span, c0 + span + 1, 5)), key=lambda t: t[0])
    fine = max(((_ncc(er, ec, l), l) for l in range(best[1] - 6, best[1] + 7)), key=lambda t: t[0])
    others = sorted((_ncc(er, ec, l) for l in range(c0 - span, c0 + span + 1, 25) if abs(l - fine[1]) > 50), reverse=True)
    runner = others[0] if others else -1.0
    trusted = fine[0] >= 0.6 and fine[0] - runner >= 0.25
    return {"offset": round(fine[1] / 100, 3) if trusted else round(coarse, 3), "coarse": round(coarse, 3),
            "ncc": round(fine[0], 3), "runner_up": round(runner, 3), "trusted": trusted,
            "audio_offset": round(fine[1] / 100, 3)}


def find_twin(replay):
    """The Cam file saved right after this Replay, in the same folder."""
    rt = name_ts(replay)
    if rt is None:
        return None
    folder = os.path.dirname(os.path.abspath(replay))
    cands = []
    for p in glob.glob(os.path.join(folder, "Cam*")):
        if os.path.splitext(p)[1].lower() not in (".mp4", ".mkv", ".mov"):
            continue
        ct = name_ts(p)
        if ct is not None and PAIR_WINDOW[0] <= ct - rt <= PAIR_WINDOW[1]:
            cands.append((abs(ct - rt), p))
    return min(cands)[1] if cands else None


def pair(replay):
    cam = find_twin(replay)
    if not cam:
        return None
    a = align(replay, cam)
    w, h = ffprobe_wh(cam)
    return {"path": os.path.abspath(cam), "w": w, "h": h, "dur": round(ffprobe_dur(cam), 3), **a}


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "pair":
        r = pair(sys.argv[2])
        print(json.dumps(r, indent=1) if r else "no Cam twin found")
    elif len(sys.argv) >= 4 and sys.argv[1] == "align":
        print(json.dumps(align(sys.argv[2], sys.argv[3]), indent=1))
    else:
        print(__doc__)
