#!/usr/bin/env python3
"""
vod_chat.py — Twitch VOD chat replay → the edited cut's timeline → ranked picks → chat_cards.py input.
"fetch <job> <vod> [chat_downloader flags]" downloads the replay through presets/gameplay/fetch_chat.py (the wrapper
that fixes chat_downloader 0.2.8's retired Twitch GQL hash + stdin-polling retry; the stock CLI fails on every Twitch
VOD) → projects/<job>/chat/vod-<id>.json. Times are VOD seconds — the raw recording IS the VOD download, so raw time
== VOD time — but WHOLE seconds, so a message within 1 s of a cut boundary can land on either side; and Twitch only
attaches chat once the VOD exists, so the first ~10-25 s of chat are usually missing (rush-hour's starts at 0:23).
A file that is not valid JSON (truncated download, saved error page) dies instead of passing as an empty chat.
"map <job>" walks every message through projects/<job>/transcript/cuts.json: a raw instant t inside kept segment k
lands at (sum of the durations of segments 0..k-1) + (t - start_k), searching only the segments cut from the VOD's
own recording (a list that also cuts a second file needs --clip, else map dies — the other clip's 0..N window would
capture dropped VOD seconds). A message in a dropped region is kept, flagged "cut" and snapped to the output start of
the next kept segment; past the last one, or past the end of the delivered base cut, it is dropped — outputs/<job>.mp4
is ffprobed and its real length is the out_duration recorded (a splice can ship shorter than the cut list sums to;
rush-hour's is 6 s short). Result: projects/<job>/chat/mapped.json.
"pick <job>" ranks the messages (streamer mentions outside links, ALL-CAPS, !/?, favoured users, card-readable
length, same-user bursts; emote/link/one-character spam penalised; channel bots and Twitch's own gift/sub notices,
which arrive as text_message with the gifter as author, sink to the bottom) next to the transcript words spoken in
the 4 s around each output time, so the editor chooses by ear; ~ marks the cut-snapped (--kept-only hides them).
"cards <job> --ids 12,40,41" writes messages.json in chat_cards.py's exact format (display name, Twitch colour or a
stable palette colour keyed by user, badges mapped to sub/verified/mod/vip from the replay — or --badges verified,sub
to force the shipped look; channel collectibles such as "princessdonutbrown" are not sub badges and stay unmapped)
plus timing.json (each card's output start = the mapped time, end = start + --hold) for the card-pass runner. Cards
only get what chat_cards.py can draw: characters Inter-Bold has no glyph for (emoji, CJK… — PIL draws a notdef box;
the font's cmap is read) are dropped with a warning and a non-Latin display name falls back to the login; a text over
--max-chars, or a token wider than its line (estimated from measured Inter-Bold widths at --font-px/--canvas — the
renderer can't break a token or clamp the card's height, so it would run off the frame), is refused unless --truncate.
"""
import argparse, glob, json, os, re, shutil, struct, subprocess, sys, zlib

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FONT = os.path.join(REPO, "assets", "fonts", "Inter-Bold.otf")            # the one font chat_cards.py draws with
TEXT_TYPES = {"text_message", "highlighted_message", "send_message_in_subscriber_only_mode"}
PALETTE = ["#FF0000", "#0000FF", "#008000", "#B22222", "#FF7F50", "#9ACD32", "#FF4500", "#2E8B57",
           "#DAA520", "#D2691E", "#5F9EA0", "#1E90FF", "#FF69B4", "#8A2BE2", "#00FF7F"]   # Twitch default name colours
BADGE_MAP = (("moderator", "mod"), ("vip", "vip"), ("partner", "verified"), ("verified", "verified"), ("subscribe", "sub"), ("founder", "sub"))   # "subscribe" also hits name=subscriber + clickAction=SUBSCRIBE
BOTS = {"nightbot", "streamelements", "moobot", "fossabot", "streamlabs", "wizebot", "botrix"}
EMOTES = {"lul", "lulw", "kappa", "pogchamp", "pog", "poggers", "kekw", "omegalul", "monkas", "ez", "clap", "sadge",
          "pepelaugh", "weirdchamp", "trihard", "komodohype", "notlikethis", "biblethump", "pepehands", "gg", "f", "w", "l"}
STREAMER = None   # set from --streamer: a regex for how chat refers to YOU, e.g. "\\bmyname\\b"
LINK = re.compile(r"https?://|www\.|\w\.[a-z]{2,}/", re.I)          # a token that is, or carries, a link
NOTICE = re.compile(r"\b(?:is gifting \d+|gifted a |subscribed (?:with|at|for)|is continuing the gift|converted from|paying forward)\b", re.I)


def die(msg): print(f"vod_chat: {msg}", file=sys.stderr); sys.exit(1)
def warn(msg): print(f"vod_chat: warning: {msg}", file=sys.stderr)
def P(job, *parts): return os.path.join(REPO, "projects", job, *parts)
def rel(p): r = os.path.relpath(p, REPO); return p if r.startswith("..") else r
def mmss(t): d = round(t * 10); return f"{d // 600:02d}:{d % 600 / 10:04.1f}"   # tenths first, so 59.96 → 01:00.0 not 00:60.0
def clip(s, n): return s if len(s) <= n else s[:n - 1] + "…"
def need(path, hint=""): return path if os.path.exists(path) else die(f"missing {rel(path)}" + (f" — {hint}" if hint else ""))
def est(s, px): return sum(px * (0.70 if c.isupper() else 0.56 if c.isalpha() else 0.62 if c.isdigit() else 0.51) for c in s)   # Inter-Bold advance widths, measured (em)

def parse_time_text(s):
    if not isinstance(s, str) or not s.strip(): return None
    s = s.strip(); neg = s.startswith("-")
    try: v = sum(float(p) * 60 ** i for i, p in enumerate(reversed(s.lstrip("-").split(":"))))
    except ValueError: return None
    return -v if neg else v

def load_chat(path):
    """chat-downloader output: a JSON array, or one JSON object per line. Text messages only, sorted by VOD time.
    Anything else (a truncated download, a saved error page) dies — it must never pass as an empty chat."""
    text = open(need(path, "run fetch first"), encoding="utf-8").read()
    try:
        data = json.loads(text)
        if isinstance(data, dict): data = data.get("messages") or [data]
    except json.JSONDecodeError:
        data, bad = [], []
        for ln in (l.strip().rstrip(",") for l in text.splitlines() if l.strip()):
            try: data.append(json.loads(ln))
            except json.JSONDecodeError: bad.append(ln)
        if bad or not data: die(f"{rel(path)} is not valid JSON (neither an array nor one object per line" + (f"; first bad line {clip(bad[0], 40)!r}" if bad else "")
                                + ") — truncated download or an error page? re-run fetch")
    if not isinstance(data, list): die(f"{rel(path)} holds a {type(data).__name__}, not a message array")
    msgs = []
    for m in data:
        if not isinstance(m, dict): continue
        mt, body = m.get("message_type"), m.get("message")
        if (mt is not None and mt not in TEXT_TYPES) or not isinstance(body, str) or not body.strip(): continue
        t = m.get("time_in_seconds")
        t = float(t) if isinstance(t, (int, float)) else parse_time_text(m.get("time_text"))
        if t is None: continue
        a = m.get("author"); a = a if isinstance(a, dict) else {}
        login = a.get("name") or a.get("display_name") or a.get("id") or "unknown"
        badges = [{"name": b.get("name") or "", "title": b.get("title") or "", "action": b.get("clickAction") or ""}
                  for b in (a.get("badges") or []) if isinstance(b, dict) and (b.get("name") or b.get("title"))]
        emotes = [e.get("name") for e in (m.get("emotes") or []) if isinstance(e, dict) and e.get("name")]
        msgs.append({"message_id": m.get("message_id"), "raw": round(t, 3), "login": login, "user": a.get("display_name") or login,
                     "text": " ".join(body.split()), "colour": a.get("colour") or a.get("color"), "badges": badges, "emotes": emotes})
    msgs.sort(key=lambda x: x["raw"])
    if not msgs: warn(f"{rel(path)} holds no text messages ({len(data)} records)")
    return msgs

def load_segments(job):
    """Every segment of cuts.json in output order with its clip and output offset; the total is the whole edit's length."""
    d = json.load(open(need(P(job, "transcript", "cuts.json"), "run rough-cut first")))
    segs, off = [], 0.0
    for k, s in enumerate(d.get("segments") or []):
        st, en = float(s["start"]), float(s["end"])
        segs.append({"k": k, "clip": str(s.get("clip") or ""), "start": st, "end": en, "off": off}); off += en - st
    if not segs: die("cuts.json has no segments")
    return segs, off

def vod_segments(segs, clip):
    """Only the segments cut from the VOD's recording — another clip's raw window must never capture a VOD second."""
    clips = sorted({s["clip"] for s in segs})
    if clip: clip = next((c for c in clips if c == clip or os.path.basename(c) == clip), None) or die(f"--clip is none of {clips}")
    elif len(clips) > 1: die(f"cuts.json cuts {len(clips)} clips {clips} — name the VOD's recording with --clip")
    return [s for s in segs if s["clip"] == (clip or clips[0])], clip or clips[0]

def map_time(t, segs):
    """raw → (out, cut, segment index); None when the message is past the last kept segment."""
    for s in segs:
        if s["start"] <= t <= s["end"]: return round(s["off"] + t - s["start"], 3), False, s["k"]
    s = min((s for s in segs if s["start"] > t), key=lambda x: x["start"], default=None)
    return None if s is None else (round(s["off"], 3), True, s["k"])

def probe_duration(path):                                       # seconds of a delivered file via ffprobe; None when it (or ffprobe) is not there
    if not os.path.exists(path) or not shutil.which("ffprobe"): return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: warn(f"ffprobe could not read {rel(path)}; trusting the cut list"); return None

def find_downloader():
    """The wrapper first (stock chat_downloader dies on Twitch VODs: retired GQL hash); the bare CLI only as a fallback."""
    wrap = os.path.join(REPO, "presets", "gameplay", "fetch_chat.py")
    if os.path.exists(wrap): return [sys.executable or "python3", wrap]
    for p in (os.path.expanduser("~/.local/bin/chat_downloader"), os.path.expanduser("~/.cache/video-editor/chat-venv/bin/chat_downloader"), shutil.which("chat_downloader")):
        if p and os.path.exists(p): return [p]
    die("chat_downloader not found (~/.local/bin, ~/.cache/video-editor/chat-venv/bin, PATH) — uv tool install chat-downloader")

def cmd_fetch(a):
    need(P(a.job), "no such job folder")
    vid = (re.search(r"(\d{6,})", a.vod) or die(f"no VOD id in {a.vod!r}")).group(1); url = a.vod if a.vod.startswith("http") else f"https://www.twitch.tv/videos/{vid}"
    out = P(a.job, "chat", f"vod-{vid}.json"); os.makedirs(os.path.dirname(out), exist_ok=True)
    extra = [x for x in (a.extra or []) if x != "--"]           # pass-through, e.g. --end_time 3:00 --max_attempts 5
    cmd = find_downloader() + [url, "--output", out, "--quiet", *extra]
    print(f"fetching {url} → {rel(out)}  ({' '.join(cmd[:len(cmd) - len(extra) - 4])})")
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL)          # never let the downloader's retry prompt touch stdin
    if r.returncode != 0 or not os.path.exists(out): die(f"chat_downloader exited {r.returncode}; no chat file written")
    print(f"{len(load_chat(out))} text messages → {rel(out)}")

def cmd_map(a):
    files = sorted(glob.glob(P(a.job, "chat", "vod-*.json")), key=os.path.getmtime)
    chat = a.chat or (files[-1] if files else die(f"no {rel(P(a.job, 'chat'))}/vod-*.json — run fetch first (or pass --chat FILE)"))
    msgs = load_chat(chat)
    if not msgs: die(f"nothing to map — {rel(chat)} has no text messages")
    segs, total = load_segments(a.job); vod, clipname = vod_segments(segs, a.clip)
    base = P(a.job, "outputs", f"{a.job}.mp4"); real = probe_duration(base); end = total if real is None else real
    if real is not None and abs(real - total) > 0.5: warn(f"cuts.json sums to {total:.3f} s but the delivered {rel(base)} is {real:.3f} s — trusting the file: out_duration = {real:.3f}, messages mapped past it are dropped")
    out, kept, cut, gone = [], 0, 0, 0
    for m in msgs:
        r = map_time(m["raw"], vod)
        if r is None or r[0] >= end: gone += 1; continue
        m["out"], m["cut"], m["seg"] = r
        kept += not m["cut"]; cut += m["cut"]
        out.append({"id": len(out) + 1, **m})
    dst = P(a.job, "chat", "mapped.json"); os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump({"job": a.job, "chat": rel(chat), "cuts": rel(P(a.job, "transcript", "cuts.json")), "clip": clipname, "segments": len(segs), "vod_segments": len(vod),
               "out_duration": round(end, 3), "cut_duration": round(total, 3), "base": rel(base) if real is not None else None, "messages": out},
              open(dst, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(msgs)} text messages → {kept} kept, {cut} cut (snapped to the next kept segment), {gone} past the end"
          f" | cut = {len(vod)} segments of {clipname}, {mmss(end)} out → {rel(dst)}")

def is_bot(m): return m["login"].lower() in BOTS or any("bot" in re.findall("[a-z]+", str(b).lower()) for b in m.get("badges") or [])

def score(m, users, burst):
    t = m["text"]; tl = t.lower(); s = 0; toks = t.split()
    if is_bot(m) or (NOTICE.search(tl) and tl.startswith((m["user"].lower(), m["login"].lower()))): return -9   # channel bots + Twitch's own gift/sub notices (text_message, gifter as author, text starts with their name): never card material
    plain = " ".join(w for w in toks if not LINK.search(w))        # a handle inside a donation link is no mention
    if STREAMER.search(plain): s += 3
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters): s += 2
    s += min(3, t.count("!") + t.count("?"))
    if m["login"].lower() in users or m["user"].lower() in users: s += 2
    if 3 <= len(toks) <= 12: s += 1
    emotes = {e.lower() for e in m.get("emotes") or []} | EMOTES
    if len(t.strip()) == 1 or not plain.strip() or all(w.strip(".,!?").lower() in emotes for w in toks): s -= 3
    return s + (1 if burst else 0)

def load_words(job):
    d = json.load(open(need(P(job, "outputs", f"{job}.transcript.json"), "canonical transcript (splice.sh) not found"))); ws = d.get("words") if isinstance(d, dict) else d
    return [w for w in ws or [] if isinstance(w, dict) and isinstance(w.get("start"), (int, float)) and w.get("text")]

def cmd_pick(a):
    mapped = json.load(open(need(P(a.job, "chat", "mapped.json"), "run map first"), encoding="utf-8")); msgs = mapped["messages"]
    last, burst = {}, set()                       # walking backwards, last[] holds each user's NEXT message time
    for m in reversed(msgs):
        nxt = last.get(m["login"])
        if nxt is not None and nxt - m["raw"] <= 5: burst.add(m["id"])
        last[m["login"]] = m["raw"]
    users = {u.lower() for u in a.user or []}
    rx = re.compile(a.grep, re.I) if a.grep else None
    rows = []
    for m in msgs:
        if (a.kept_only and m["cut"]) or (a.from_s is not None and m["out"] < a.from_s) or (a.to_s is not None and m["out"] > a.to_s): continue
        if rx and not rx.search(m["text"]): continue
        rows.append((score(m, users, m["id"] in burst), m))
    rows.sort(key=lambda r: (-r[0], r[1]["out"]))
    words = [w for w in load_words(a.job) if w["start"] < mapped.get("out_duration", 1e9)]   # the transcript can outrun a short-shipped cut
    print(f"{'id':>5} {'sc':>3} {'out':>8} {'raw':>7}  {'user':<18} {'text':<48}  spoken ±2 s (output time; ~ = cut, snapped)")
    for s, m in rows[:a.top]:
        ctx = " ".join(w["text"] for w in words if m["out"] - 2 <= w["start"] <= m["out"] + 2)
        print(f"{m['id']:>5} {s:>3} {('~' if m['cut'] else '') + mmss(m['out']):>8} {mmss(m['raw']):>7}  {clip(m['user'], 18):<18} {clip(m['text'], 48):<48}  {clip(ctx, 70)}")
    ncut = sum(1 for _, m in rows if m["cut"])
    print(f"{len(rows)} candidates ({len(rows) - ncut} kept, {ncut} cut→snapped){' after filters' if (rx or a.from_s is not None or a.to_s is not None) else ''}; "
          f"showing top {min(a.top, len(rows))}  (id → cards {a.job} --ids ...)")

def colour_for(m):
    c = (m.get("colour") or "").strip().upper(); return c if re.fullmatch(r"#[0-9A-F]{6}", c) else PALETTE[zlib.crc32(m["login"].lower().encode()) % len(PALETTE)]

def badges_for(badges):
    """Badge set name / title / clickAction → chat_cards.py tags (custom sub badges only reveal themselves via clickAction)."""
    out = []
    for b in badges:
        key = " ".join(str(v) for v in (b.values() if isinstance(b, dict) else [b])).lower()
        for needle, tag in BADGE_MAP:
            if needle in key and tag not in out: out.append(tag)
    return out

def font_glyphs(path):
    """Code points the card font really has (OpenType cmap, formats 4 + 12): PIL has no fallback, the rest draw as boxes."""
    f = open(need(path, "chat_cards.py's font"), "rb").read(); u = lambda fmt, at: struct.unpack(fmt, f[at:at + struct.calcsize(fmt)])
    off, _ = next(u(">II", 20 + 16 * i) for i in range(u(">H", 4)[0]) if f[12 + 16 * i:16 + 16 * i] == b"cmap"); cps = set()
    for i in range(u(">H", off + 2)[0]):
        so = off + u(">I", off + 8 + 8 * i)[0]; fmt = u(">H", so)[0]
        if fmt == 4:
            n = u(">H", so + 6)[0]; ends, starts = u(f">{n // 2}H", so + 14), u(f">{n // 2}H", so + 16 + n)
            cps.update(c for s, e in zip(starts, ends) if s != 0xFFFF for c in range(s, e + 1))
        elif fmt == 12:
            cps.update(c for g in range(u(">I", so + 12)[0]) for s, e, _ in [u(">III", so + 16 + 12 * g)] for c in range(s, e + 1))
    return cps

def card_text(m, glyphs, nbadges, a):
    """(name, text) chat_cards.py can draw — see the module docstring. Widths mirror chat_cards.py's geometry at --font-px/--canvas."""
    ok = lambda s: "".join(c for c in s if ord(c) in glyphs)
    name = m["user"] if ok(m["user"]) == m["user"] else m["login"]; text = " ".join(ok(m["text"]).split())
    if (name, text) != (m["user"], m["text"]): warn(f"id {m['id']}: dropped characters Inter-Bold has no glyph for → {name}: {text!r}")
    if not text: die(f"id {m['id']}: nothing drawable is left of {m['text']!r}")
    px, gap = a.font_px, int(a.font_px * 0.28); box = int(int(a.canvas.split("x")[0]) * 0.62) - 2 * int(px * 0.55)   # the wrap width
    room = lambda k: box - ((px + gap) * nbadges + est(name + ":", px) + gap) if k == 0 else box               # the first token sits after 'name:'
    ws = text.split(); wide = [(k, w) for k, w in enumerate(ws) if est(w, px) > room(k)]
    if len(text) > a.max_chars or wide:
        why = f"{len(text)} chars (--max-chars {a.max_chars})" if len(text) > a.max_chars else f"token {wide[0][1]!r} ≈ {est(wide[0][1], px):.0f} px wide, {room(wide[0][0]):.0f} px left on its line"
        if not a.truncate: die(f"id {m['id']}: {why} — the card would run off the frame (chat_cards.py neither breaks a token nor clamps the height); pass --truncate to clip it")
        fit = lambda k, w: w[:max((n for n in range(1, len(w)) if est(w[:n] + "…", px) <= room(k)), default=1)] + "…"
        text = clip(" ".join(w if est(w, px) <= room(k) else fit(k, w) for k, w in enumerate(ws)), a.max_chars); warn(f"id {m['id']}: truncated to {text!r}")
    return name, text

def cmd_cards(a):
    by_id = {m["id"]: m for m in json.load(open(need(P(a.job, "chat", "mapped.json"), "run map first"), encoding="utf-8"))["messages"]}
    try: ids = [int(x) for x in a.ids.replace(" ", "").split(",") if x]
    except ValueError: die(f"--ids wants comma-separated integers from pick (e.g. 12,40,41), got {a.ids!r}")
    missing = [i for i in ids if i not in by_id]
    if not ids or missing: die(f"ids not in mapped.json: {missing or 'none given'}")
    out = os.path.abspath(a.out or P(a.job, "chat", "messages.json")); os.makedirs(os.path.dirname(out), exist_ok=True)
    forced = [b for b in (a.badges or "").replace(" ", "").split(",") if b]   # --badges verified,sub → every card
    glyphs = font_glyphs(FONT); cards, timing = [], []
    for n, i in enumerate(ids, 1):
        m = by_id[i]; badges = forced or badges_for(m["badges"]); name, text = card_text(m, glyphs, len(badges), a)
        cards.append({"name": name, "color": colour_for(m), "text": text, "badges": badges})
        timing.append({"card": n, "png": f"card{n:02d}.png", "id": i, "name": name, "text": text,
                       "start": m["out"], "end": round(m["out"] + a.hold, 3), "raw": m["raw"], "cut": m["cut"]})
    with open(out, "w", encoding="utf-8") as f:            # one object per line, exactly like the hand-written messages.json
        f.write("[\n" + ",\n".join(" " + json.dumps(c, ensure_ascii=False) for c in cards) + "\n]\n")
    tpath = os.path.join(os.path.dirname(out), "timing.json")
    json.dump({"job": a.job, "hold": a.hold, "messages": rel(out), "cards": timing}, open(tpath, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    cut = sum(1 for t in timing if t["cut"])
    print(f"{len(cards)} cards → {rel(out)} + {rel(tpath)}" + (f"  ({cut} sat in a cut region; snapped to the next kept segment)" if cut else ""))

def main():
    ap = argparse.ArgumentParser(description="Twitch VOD chat → cut timeline → ranked picks → chat_cards.py messages.json (+ timing.json).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download the VOD chat replay with chat_downloader → chat/vod-<id>.json")
    f.add_argument("job"); f.add_argument("vod", help="Twitch VOD url or id")
    f.add_argument("extra", nargs=argparse.REMAINDER, help="extra chat_downloader flags, e.g. --end_time 3:00"); f.set_defaults(fn=cmd_fetch)
    mp = sub.add_parser("map", help="map every message's VOD time onto the cut timeline → chat/mapped.json")
    mp.add_argument("job"); mp.add_argument("--chat", help="chat file (default: newest chat/vod-*.json)")
    mp.add_argument("--clip", help="which cuts.json clip is the VOD recording (needed only when the cut list mixes clips)"); mp.set_defaults(fn=cmd_map)
    pk = sub.add_parser("pick", help="rank the messages, with the transcript words spoken around each (~ = cut, snapped)")
    pk.add_argument("job"); pk.add_argument("--top", type=int, default=25); pk.add_argument("--kept-only", action="store_true", help="hide messages that sat in a cut region")
    pk.add_argument("--streamer", required=True, help="regex for how chat refers to you, e.g. \"\\bmyname\\b\" (case-insensitive)")
    pk.add_argument("--user", nargs="+", action="extend", help="favour these users (+2)"); pk.add_argument("--grep", help="case-insensitive regex the text must match")
    pk.add_argument("--from", dest="from_s", type=float, help="window start, OUTPUT seconds"); pk.add_argument("--to", dest="to_s", type=float, help="window end, OUTPUT seconds")
    pk.set_defaults(fn=cmd_pick)
    c = sub.add_parser("cards", help="write chat_cards.py messages.json + timing.json for the chosen ids")
    c.add_argument("job"); c.add_argument("--ids", required=True, help="comma-separated ids from pick, in on-screen order")
    c.add_argument("--out", help="default projects/<job>/chat/messages.json (timing.json lands beside it)"); c.add_argument("--hold", type=float, default=4.0, help="seconds each card stays up (end = start + hold)")
    c.add_argument("--badges", help="force this badge list on every card, e.g. verified or verified,sub (default: from the replay)")
    c.add_argument("--font-px", type=int, default=72); c.add_argument("--canvas", default="2560x1440", help="as passed to chat_cards.py (its defaults)")
    c.add_argument("--max-chars", type=int, default=160, help="longest text a card may carry (default 160 ≈ 4 lines)")
    c.add_argument("--truncate", action="store_true", help="clip over-long texts / too-wide tokens instead of refusing them"); c.set_defaults(fn=cmd_cards)
    a = ap.parse_args()
    global STREAMER
    if getattr(a, 'streamer', None): STREAMER = re.compile(a.streamer, re.I); a.fn(a)

if __name__ == "__main__":
    main()
