#!/usr/bin/env python3
"""
scan-replays.py — the night's Stream Deck replays → a ranked shortlist of Shorts moments.

The creator streams; when something happens he presses one Stream Deck key and OBS saves the last
180 s ("Replay YYYY-MM-DD hh-mm-ss.mp4") into the recording folder. After the stream this tool reads
ONLY those files, finds the best 15–45 s inside each one, and prints a shortlist he picks from.
Nothing is copied: each replay becomes a light job folder (projects/replay-YYYYMMDD-hhmmss/) whose
raw/ and outputs/<job>.mp4 are symlinks to the source, with its own transcript and face measurement,
so the normal clipper can build from it.

  scan-replays.py scan "D:\\Videos\\Youtube\\Local Recordings"            # newest night's unscanned replays
  scan-replays.py scan <folder> --date 2026-09-12 | all
  scan-replays.py status                                                # every replay: job, status, Shorts, space held
  scan-replays.py done <replay-job | short-job | long-form job> [--apply]   # posted → its source may be deleted
  scan-replays.py keep <replay-job> --why "..."                          # a reference: never deleted
  scan-replays.py sweep [--apply]                                        # delete the sources of everything done + not kept

Storage policy (the creator's, 2026-09-11): a source file stays until the video made from it is
posted, then it is deleted to free the drive — unless it is marked as a reference worth keeping.
Deletion is never automatic: `done`/`sweep` print what would go and need --apply.

Scoring inside a replay (the press is at the END of the file, so the moment is usually in the last
minute): reaction beats from the comedy layer (his laugh, shouts, trigger words, the pause after a
line), motion bursts in the game (falls, deaths), a recency bonus toward the press, a penalty for
long silent stretches (watching) and for windows without speech or events. Windows start and end on
pause / sentence boundaries; the top two non-overlapping windows per replay are kept.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import gags as gagmod
import clipper as clipmod
import camsync

LEDGER = os.path.join(REPO, "projects", "replays", "ledger.json")
NIGHTS = os.path.join(REPO, "projects", "replays")
TRANSCRIBE = os.path.join(REPO, ".claude", "skills", "cut", "scripts", "transcribe.sh")
EXPORT = os.path.join(REPO, ".claude", "skills", "cut", "scripts", "export-transcript.py")
UV = os.path.expanduser("~/.local/bin/uv")
EXTS = (".mp4", ".mkv", ".mov")
BUILD = ("presets/shorts/clipper.py {job} --window {a:.1f}-{b:.1f} --captions off --layout intercut "
         "--style punchy --no-memes --loudness -14 --sfx-trim -6 --name <title>")


def log(msg):
    print(f"[replays] {msg}", flush=True)


def to_wsl(p):
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if m:
        return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")
    return p


def human(nbytes):
    return f"{nbytes / 1e9:.1f} GB" if nbytes >= 1e9 else f"{nbytes / 1e6:.0f} MB"


def parse_name(path):
    """'Replay 2026-09-12 21-14-03.mp4' → ('2026-09-12', '21-14-03'); falls back to the file's mtime."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})[ _T](\d{2}-\d{2}-\d{2})", os.path.basename(path))
    if m:
        return m.group(1), m.group(2)
    t = time.localtime(os.path.getmtime(path))
    return time.strftime("%Y-%m-%d", t), time.strftime("%H-%M-%S", t)


def load_ledger():
    return json.load(open(LEDGER)) if os.path.isfile(LEDGER) else {}


def save_ledger(led):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(led, open(LEDGER, "w"), indent=1)


def mmss(t):
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def ffprobe_dur(path):
    return clipmod.ffprobe_dur(path)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout[-2000:], file=sys.stderr)
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"[replays] command failed: {' '.join(str(c) for c in cmd)}")
    return r


# ----------------------------------------------------------------------------- jobs
def job_name(date, tm):
    return f"replay-{date.replace('-', '')}-{tm.replace('-', '')}"


def make_job(src, job):
    """A light job folder around a replay: symlinks to the source, nothing copied."""
    jd = os.path.join(REPO, "projects", job)
    ext = os.path.splitext(src)[1].lower()
    for sub in ("raw", "outputs", "transcript", "assemble_work"):
        os.makedirs(os.path.join(jd, sub), exist_ok=True)
    raw = os.path.join(jd, "raw", f"{job}{ext}")
    base = os.path.join(jd, "outputs", f"{job}.mp4")
    for link in (raw, base):
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(src, link)
    with open(os.path.join(jd, "intent.md"), "w") as f:
        f.write(f"# {job}\n\nStream Deck replay saved {parse_name(src)[0]} {parse_name(src)[1].replace('-', ':')} — "
                f"source: {src}\nThe last ~3 minutes before the press; the moment is inside. See shortlist.\n")
    return jd, raw, base


def pair_cam(src, jd, job):
    """Find the replay's Cam twin, align it by audio, measure the face in it → projects/<job>/cam.json."""
    cam = camsync.pair(src)
    if not cam:
        return None
    cam["face"] = clipmod.measure_cam_face(jd, cam["path"])
    json.dump(cam, open(os.path.join(jd, "cam.json"), "w"), indent=1)
    log(f"  {job}: cam twin {os.path.basename(cam['path'])} — offset {cam['offset']:.2f}s "
        f"({'audio ncc %.2f' % cam['ncc'] if cam.get('trusted') else 'from timestamps; ' + cam.get('note', 'audio match weak')}), "
        f"face {cam['face']['w']}x{cam['face']['h']} at ({cam['face']['cx']},{cam['face']['cy']})")
    return cam


def transcribe_batch(night_dir, items):
    """One WhisperX run (one model load) for every new replay of the night, then split per job."""
    batch = os.path.join(night_dir, f"_batch-{int(time.time())}")
    os.makedirs(os.path.join(batch, "raw"), exist_ok=True)
    for src, job, raw in items:
        os.symlink(src, os.path.join(batch, "raw", os.path.basename(raw)))
    log(f"transcribing {len(items)} replay(s) in one WhisperX pass…")
    r = subprocess.run(["bash", TRANSCRIBE, batch], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit("[replays] transcription failed")
    words = json.load(open(os.path.join(batch, "transcript", "words.json")))
    by_clip = {c["clip"]: c for c in words["clips"]}
    for src, job, raw in items:
        jd = os.path.join(REPO, "projects", job)
        c = dict(by_clip[os.path.basename(raw)])
        c["path"] = raw
        json.dump({"clips": [c]}, open(os.path.join(jd, "transcript", "words.json"), "w"), indent=2)
        dur = float(c.get("duration") or ffprobe_dur(raw))
        cuts = {"segments": [{"clip": os.path.basename(raw), "start": 0.0, "end": round(dur, 3), "transcript": "(whole replay)"}]}
        cpath = os.path.join(jd, "transcript", "cuts.json")
        json.dump(cuts, open(cpath, "w"), indent=1)
        out = os.path.join(jd, "outputs", f"{job}.transcript.json")
        run(["python3", EXPORT, os.path.join(jd, "transcript", "words.json"), cpath, out])
    shutil.rmtree(batch, ignore_errors=True)
    shutil.rmtree(f"/tmp/video-editor/{os.path.basename(batch)}", ignore_errors=True)


def measure_face(jd, base):
    r = subprocess.run([UV, "run", os.path.join(REPO, "workflows", "zoom-crop.py"), base], capture_output=True, text=True, cwd=REPO)
    face = clipmod.load_face(jd)
    if face is None:
        log(f"  no face measured for {os.path.basename(jd)} (cam hidden?) — framing will centre the frame")
    return face


# ----------------------------------------------------------------------------- scoring
def score_replay(jd, job, min_len, max_len, target):
    base = os.path.join(jd, "outputs", f"{job}.mp4")
    tj = os.path.join(jd, "outputs", f"{job}.transcript.json")
    words = [w for w in json.load(open(tj))["words"] if w.get("type", "word") == "word" and w.get("text", "").strip()]
    dur = ffprobe_dur(base)
    face = clipmod.load_face(jd)
    work = os.path.join(jd, "assemble_work", "scan")
    env = gagmod.audio_envelope(base, work)
    beats, med, bed = gagmod.detect_beats(words, env, dur)
    events = clipmod.motion_events(base, dur, face)

    cands = set()
    if words:
        b = clipmod.boundaries(words)
        for i0 in b:
            t0 = max(0.0, words[i0]["start"] - 0.3)
            for i1 in [i for i in b if i > i0] + [len(words)]:
                t1 = min(dur, words[i1 - 1]["end"] + 0.6)
                if t1 - t0 < min_len:
                    continue
                if t1 - t0 > max_len:
                    break
                cands.add((round(t0, 2), round(t1, 2)))
        # windows that run to the press (the end of the file)
        for i0 in b:
            t0 = max(0.0, words[i0]["start"] - 0.3)
            if min_len <= dur - t0 <= max_len:
                cands.add((round(t0, 2), round(dur, 2)))
    for a, b_, e in events:
        for pre, post in ((6.0, 10.0), (12.0, 12.0), (3.0, 18.0)):
            t0, t1 = max(0.0, a - pre), min(dur, b_ + post)
            if min_len <= t1 - t0 <= max_len:
                cands.add((round(t0, 2), round(t1, 2)))
    for L in (target, max_len, min_len):
        if dur >= L:
            cands.add((round(dur - L, 2), round(dur, 2)))
    if not cands:
        cands.add((max(0.0, dur - min(max_len, dur)), dur))

    def score(t0, t1):
        L = t1 - t0
        inside = [x for x in beats if t0 <= x["t"] <= t1]
        s = sum(x["score"] * (1.5 if x["kind"] == "laugh" else 1.0) for x in inside)
        ev = [e for e in events if t0 <= e[0] <= t1]
        s += sum(1.2 + min(2.0, e[2] / 300.0) for e in ev)
        s += 0.5 * sum(1 for x in inside if x["t"] - t0 <= 4.0)                     # a beat in the first 4 s = a hook
        if t1 >= dur - 40:
            s += 1.5                                                                 # right before the press
        elif t1 >= dur - 90:
            s += 0.8
        ws = [w for w in words if t0 <= w["start"] <= t1]
        density = len(ws) / max(L, 1e-6)
        if density < 0.5 and not ev:
            s -= 1.5                                                                 # nothing said, nothing happened
        gaps = sum(1 for k in range(1, len(ws)) if ws[k]["start"] - ws[k - 1]["end"] >= 4.0)
        s -= 0.8 * gaps                                                              # long watching stretches
        s -= abs(L - target) / 15.0
        if t1 >= dur - 0.5 or any(t1 - 1.5 <= x["t"] <= t1 for x in inside) or (ws and t1 - ws[-1]["end"] <= 1.2):
            s += 0.5                                                                 # a clean ending
        why = []
        if any(x["kind"] == "laugh" for x in inside):
            why.append("laugh")
        loud = [x for x in inside if x.get("loud")]
        if loud:
            why.append("loud")
        trig = [x["text"] for x in inside if x["kind"] in ("word", "reaction") and not x["text"].startswith("(")]
        if trig:
            why.append("says " + " / ".join(f'"{t}"' for t in trig[:3]))
        if ev:
            why.append(f"{len(ev)} motion burst{'s' if len(ev) > 1 else ''}")
        if t1 >= dur - 40:
            why.append("right before the press")
        return round(s, 2), why, ws

    scored = []
    for t0, t1 in cands:
        s, why, ws = score(t0, t1)
        scored.append({"start": t0, "end": t1, "dur": round(t1 - t0, 1), "score": s, "why": why,
                       "line": " ".join(w["text"] for w in ws[:14]) + ("…" if len(ws) > 14 else "")})
    scored.sort(key=lambda c: -c["score"])
    picked = []
    for c in scored:
        if any(max(0.0, min(c["end"], p["end"]) - max(c["start"], p["start"])) > 0.4 * min(c["dur"], p["dur"]) for p in picked):
            continue
        picked.append(c)
        if len(picked) >= 2:
            break
    return picked, {"beats": len(beats), "events": [(a, b_, e) for a, b_, e in events], "words": len(words), "dur": round(dur, 2)}


def strip(base, c, out):
    n = int(c["dur"]) + 1
    run(clipmod.FFMPEG + ["-ss", f"{c['start']:.2f}", "-t", f"{c['dur']:.2f}", "-i", base, "-vf",
                          f"fps=1,scale=192:108,drawtext=text='%{{pts\\:hms}}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.6,"
                          f"tile=10x{(n + 9) // 10}", "-frames:v", "1", out])


# ----------------------------------------------------------------------------- commands
def cmd_scan(args):
    folder = to_wsl(args.folder)
    if not os.path.isdir(folder):
        raise SystemExit(f"[replays] no such folder: {folder}")
    files = sorted(p for p in glob.glob(os.path.join(folder, "*")) if os.path.splitext(p)[1].lower() in EXTS
                   and os.path.basename(p).lower().startswith("replay"))
    if not files:
        raise SystemExit(f"[replays] no Replay*.mp4 files in {folder}")
    by_date = {}
    for p in files:
        by_date.setdefault(parse_name(p)[0], []).append(p)
    if args.date == "last":
        dates = [max(by_date)]
    elif args.date == "all":
        dates = sorted(by_date)
    else:
        dates = [args.date]
        if args.date not in by_date:
            raise SystemExit(f"[replays] no replays dated {args.date}; have {', '.join(sorted(by_date))}")
    led = load_ledger()
    for date in dates:
        night = os.path.join(NIGHTS, date)
        os.makedirs(os.path.join(night, "review"), exist_ok=True)
        todo = []
        for src in by_date[date]:
            st = os.stat(src)
            key = os.path.abspath(src)
            ent = led.get(key)
            if ent and ent.get("size") == st.st_size and int(ent.get("mtime", 0)) == int(st.st_mtime) and not args.rescan:
                continue
            d, tm = parse_name(src)
            job = job_name(d, tm)
            jd, raw, base = make_job(src, job)
            led[key] = {"job": job, "date": d, "time": tm.replace("-", ":"), "size": st.st_size, "mtime": int(st.st_mtime),
                        "status": "scanned", "candidates": [], "shorts": []}
            todo.append((src, job, raw, jd, base))
        log(f"{date}: {len(by_date[date])} replay(s), {len(todo)} new")
        if todo:
            transcribe_batch(night, [(s, j, r) for s, j, r, _, _ in todo])
            for src, job, raw, jd, base in todo:
                measure_face(jd, base)
                cam = pair_cam(src, jd, job)
                if cam:
                    led[os.path.abspath(src)]["cam"] = cam["path"]
                    led[os.path.abspath(src)]["cam_size"] = os.path.getsize(cam["path"])
                picks, info = score_replay(jd, job, args.min, args.max, args.target)
                for k, c in enumerate(picks, 1):
                    strip(base, c, os.path.join(night, "review", f"{job}-{k}.png"))
                led[os.path.abspath(src)]["candidates"] = picks
                led[os.path.abspath(src)]["info"] = info
                log(f"  {job}: {info['words']} words, {info['beats']} beats, {len(info['events'])} motion bursts → "
                    + "; ".join(f"{mmss(c['start'])}-{mmss(c['end'])} ({c['score']:.1f})" for c in picks))
            save_ledger(led)
        # the night's shortlist, across every replay of that date (scanned before or now)
        rows = []
        for key, ent in led.items():
            if ent.get("date") != date:
                continue
            for k, c in enumerate(ent.get("candidates", []), 1):
                rows.append((c["score"], ent["job"], ent["time"], k, c))
        rows.sort(key=lambda r: -r[0])
        lines = [f"# Replays {date} — shortlist ({len(rows)} candidates from {sum(1 for e in led.values() if e.get('date') == date)} replays)",
                 "", "Build one:  " + BUILD.replace("{job}", "<job>").replace("{a:.1f}", "<a>").replace("{b:.1f}", "<b>"), "",
                 "| # | replay (press) | window | s | score | why | line |", "|---|---|---|---|---|---|---|"]
        for i, (s, job, tm, k, c) in enumerate(rows, 1):
            lines.append(f"| {i} | {job} ({tm}) | {mmss(c['start'])}–{mmss(c['end'])} | {c['dur']:.0f} | {s:.1f} | "
                         f"{', '.join(c['why']) or '-'} | {c['line'].replace('|', '/')} |")
        lines += ["", "## Build commands", ""]
        for i, (s, job, tm, k, c) in enumerate(rows, 1):
            lines.append(f"{i}. `{BUILD.format(job=job, a=c['start'], b=c['end'])}`   sheet: review/{job}-{k}.png")
        with open(os.path.join(night, "shortlist.md"), "w") as f:
            f.write("\n".join(lines) + "\n")
        print()
        print("\n".join(lines[:6 + min(len(rows), args.top)]))
        print(f"\n  full list + sheets: {night}/")


def shorts_of(job):
    out = []
    for cj in glob.glob(os.path.join(REPO, "projects", "*", "clip.json")):
        try:
            m = json.load(open(cj))
        except Exception:
            continue
        if m.get("source_job") == job:
            out.append(os.path.basename(os.path.dirname(cj)))
    return sorted(out)


def cmd_status(args):
    led = load_ledger()
    if not led:
        print("no replays scanned yet")
        return
    held = reclaim = 0
    for key, ent in sorted(led.items(), key=lambda kv: (kv[1].get("date", ""), kv[1].get("time", ""))):
        exists = os.path.isfile(key)
        sh = shorts_of(ent["job"])
        ent["shorts"] = sh
        st = ent.get("status", "scanned")
        if exists:
            held += ent["size"]
            if st == "done":
                reclaim += ent["size"]
        print(f"  {ent['date']} {ent['time']}  {ent['job']:26s} {st:8s} {human(ent['size'] + ent.get('cam_size', 0)):>7s}"
              f"{' +cam' if ent.get('cam') else '     '}  {'' if exists else '(source gone) '}shorts: {', '.join(sh) or '-'}"
              + (f"  keep: {ent['keep_why']}" if ent.get("keep_why") else ""))
    save_ledger(led)
    print(f"\n  sources on disk: {human(held)}   reclaimable now (done, not kept): {human(reclaim)}")


def _find(led, name):
    for key, ent in led.items():
        if ent["job"] == name or name in ent.get("shorts", []) or name in shorts_of(ent["job"]):
            return key, ent
    return None, None


def _delete(paths, apply):
    total = 0
    for p in paths:
        if os.path.isfile(p) and not os.path.islink(p):
            total += os.path.getsize(p)
            print(f"  {'DELETE' if apply else 'would delete'}  {human(os.path.getsize(p)):>7s}  {p}")
            if apply:
                os.remove(p)
    print(f"  {'freed' if apply else 'would free'} {human(total)}" + ("" if apply else "   (add --apply to delete)"))


def cmd_done(args):
    led = load_ledger()
    key, ent = _find(led, args.name)
    if ent:
        if ent.get("status") == "keep":
            print(f"  {ent['job']} is marked keep ({ent.get('keep_why', '')}) — not deleting; `keep --clear` first")
            return
        ent["status"] = "done"
        save_ledger(led)
        print(f"  {ent['job']} marked done (Shorts: {', '.join(shorts_of(ent['job'])) or '-'})")
        _delete([key] + ([ent["cam"]] if ent.get("cam") else []), args.apply)
        return
    # a long-form job: its raw copies (+ an optional named original)
    jd = os.path.join(REPO, "projects", args.name)
    if not os.path.isdir(jd):
        raise SystemExit(f"[replays] {args.name}: not a replay, a Short built from one, or a job folder")
    paths = [p for p in glob.glob(os.path.join(jd, "raw", "*")) if os.path.isfile(p) and not os.path.islink(p)]
    if args.source:
        paths.append(to_wsl(args.source))
    print(f"  {args.name}: long-form job — the base cut, transcript and final stay; the raw source(s) go")
    _delete(paths, args.apply)


def cmd_keep(args):
    led = load_ledger()
    key, ent = _find(led, args.name)
    if not ent:
        raise SystemExit(f"[replays] unknown replay/Short {args.name}")
    if args.clear:
        ent["status"] = "scanned"
        ent.pop("keep_why", None)
        print(f"  {ent['job']}: keep cleared")
    else:
        ent["status"] = "keep"
        ent["keep_why"] = args.why or "reference"
        print(f"  {ent['job']}: kept — {ent['keep_why']}")
    save_ledger(led)


def cmd_sweep(args):
    led = load_ledger()
    paths = [key for key, ent in led.items() if ent.get("status") == "done" and os.path.isfile(key)]
    paths += [ent["cam"] for key, ent in led.items() if ent.get("status") == "done" and ent.get("cam") and os.path.isfile(ent["cam"])]
    if not paths:
        print("  nothing to sweep (mark posted videos with `done <name>` first)")
        return
    _delete(paths, args.apply)
    if args.apply:
        for key in paths:
            led[key]["status"] = "deleted"
        save_ledger(led)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("folder"); s.add_argument("--date", default="last")
    s.add_argument("--top", type=int, default=12); s.add_argument("--min", type=float, default=15.0)
    s.add_argument("--max", type=float, default=45.0); s.add_argument("--target", type=float, default=25.0)
    s.add_argument("--rescan", action="store_true"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("done"); s.add_argument("name"); s.add_argument("--apply", action="store_true")
    s.add_argument("--source", default=None, help="long-form job: the original recording to delete too"); s.set_defaults(fn=cmd_done)
    s = sub.add_parser("keep"); s.add_argument("name"); s.add_argument("--why", default=None); s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_keep)
    s = sub.add_parser("sweep"); s.add_argument("--apply", action="store_true"); s.set_defaults(fn=cmd_sweep)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
