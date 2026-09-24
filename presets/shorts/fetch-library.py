#!/usr/bin/env python3
"""
fetch-library.py — grow the Shorts comedy libraries from the creator's two APPROVED sources:

  sounds  → myinstants.com   (sound buttons; every button's mp3 is served at /media/sounds/<file>.mp3)
  memes   → vlipsy.com       (short reaction VIDEO clips with sound; free tier = Vlipsy watermark, Pro removes it)

  presets/shorts/fetch-library.py sfx  "vine boom"  --as vine-boom          # → assets/sfx/vine-boom.mp3
  presets/shorts/fetch-library.py meme "wait what"  --as shock-wait-what    # → assets/memes/shock-wait-what.mp4
  presets/shorts/fetch-library.py sfx  "bruh" --list                        # top results only, nothing saved
  presets/shorts/fetch-library.py meme "no way" --as shock-no-way --pick 3  # the 3rd result instead of the 1st

The file NAME is the tag the planner (gags.py) matches on — see assets/sfx/README.md and
assets/memes/README.md for the tag vocabulary. One request per second, browser identity, nothing
else touched. Only these two hosts: the creator chose them (2026-09-09); add a source here only if
they add it to the approved list in CLAUDE.md.
"""
import argparse, html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SFX_DIR = os.path.join(REPO, "assets", "sfx")
MEME_DIR = os.path.join(REPO, "assets", "memes")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
APPROVED = {"www.myinstants.com", "myinstants.com", "vlipsy.com", "cdn.vlipsy.com"}
MAX_BYTES = 25 * 1024 * 1024
_last = [0.0]

# SAFETY (the creator's standing concern): nothing fetched is ever executed. Only HTTPS from the two
# approved hosts; a saved file must carry a media content-type AND media magic bytes AND decode in
# ffprobe, is capped at 25 MB, and is then RE-ENCODED into a fresh container with metadata stripped —
# what lives in the library is our own ffmpeg output, never the original bytes.


def get(url, binary=False):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.netloc not in APPROVED:
        raise SystemExit(f"[fetch] refused: {url} (only https on {', '.join(sorted(APPROVED))})")
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        ctype = r.headers.get("Content-Type", "").lower()
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit(f"[fetch] refused: {url} is over {MAX_BYTES // 1024 // 1024} MB")
    return (data, ctype) if binary else data.decode("utf-8", "replace")


def looks_like_media(data, kind):
    """Magic bytes: an mp3/wav/ogg/m4a for sounds, an mp4/mov/webm for clips — never an exe, zip, or html."""
    if data[:2] == b"MZ" or data[:4] == b"PK\x03\x04" or data[:1] == b"<" or data[:5].lower() == b"<!doc":
        return False
    if kind == "sfx":
        return (data[:3] == b"ID3" or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
                or data[:4] == b"RIFF" or data[:4] == b"OggS" or data[4:8] == b"ftyp")
    return data[4:8] == b"ftyp" or data[:4] == b"\x1a\x45\xdf\xa3"


# ----------------------------------------------------------------------------- myinstants
def search_sfx(query, n=6):
    page = get("https://www.myinstants.com/en/search/?name=" + urllib.parse.quote(query))
    out, seen = [], set()
    for m in re.finditer(r"play\('(/media/sounds/[^']+)',\s*'[^']*',\s*'([^']+)'\)", page):
        path, slug = m.group(1), m.group(2)
        if path in seen:
            continue
        seen.add(path)
        t = re.search(r'href="/en/instant/%s/"[^>]*>([^<]+)<' % re.escape(slug), page)
        out.append({"title": html.unescape(t.group(1).strip()) if t else slug, "url": "https://www.myinstants.com" + path,
                    "page": f"https://www.myinstants.com/en/instant/{slug}/"})
        if len(out) >= n:
            break
    return out


# ----------------------------------------------------------------------------- vlipsy
def search_meme(query, n=6):
    page = get("https://vlipsy.com/search/" + urllib.parse.quote(query.strip().replace(" ", "-")))
    out, seen = [], set()
    for m in re.finditer(r"clips/([A-Za-z0-9_-]{6,12})/480p-watermark\.mp4", page):
        cid = m.group(1)
        if cid in seen or cid == "meta":
            continue
        seen.add(cid)
        # the title sits in the same JSON record; look a little way back for it
        window = page[max(0, m.start() - 2500):m.start()]
        t = list(re.finditer(r'\\?"title\\?":\\?"([^"\\]{2,120})', window))
        slug = list(re.finditer(r"/clips/([a-z0-9-]+)-%s" % re.escape(cid), page))
        title = html.unescape(t[-1].group(1)) if t else (slug[0].group(1).replace("-", " ") if slug else cid)
        out.append({"title": title, "id": cid, "url": f"https://cdn.vlipsy.com/clips/meta/{cid}/480p-watermark.mp4",
                    "page": f"https://vlipsy.com/clips/{slug[0].group(1) + '-' if slug else ''}{cid}"})
        if len(out) >= n:
            break
    return out


# ----------------------------------------------------------------------------- save
def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        return float(j["format"]["duration"]), [s["codec_type"] for s in j.get("streams", [])]
    except Exception:
        return None, []


def save(kind, item, name):
    d = SFX_DIR if kind == "sfx" else MEME_DIR
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    data, ctype = get(item["url"], binary=True)
    if not (ctype.startswith(("audio/", "video/", "application/octet-stream")) and looks_like_media(data, kind)):
        raise SystemExit(f"[fetch] refused: {item['url']} is not a media file (content-type {ctype!r}, "
                         f"header {data[:8]!r}) — nothing saved")
    os.makedirs(d, exist_ok=True)
    raw = os.path.join(d, f".dl-{name}.bin")
    with open(raw, "wb") as f:
        f.write(data)
    try:
        dur, streams = probe(raw)
        if dur is None or dur > 30 or (kind == "sfx" and "audio" not in streams) or (kind == "meme" and "video" not in streams):
            raise SystemExit(f"[fetch] refused: {item['url']} did not decode as a usable {kind} file (≤30 s) — nothing saved")
        # sanitize: decode → our own clean file, metadata stripped
        if kind == "sfx":
            path = os.path.join(d, name + ".wav")
            cmd = ["-vn", "-map_metadata", "-1", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", path]
        else:
            path = os.path.join(d, name + ".mp4")
            cmd = ["-map_metadata", "-1", "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", path]
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", raw, *cmd],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(path):
            raise SystemExit(f"[fetch] refused: could not re-encode {item['url']} cleanly — nothing saved\n{r.stderr}")
    finally:
        if os.path.isfile(raw):
            os.remove(raw)
    print(f"[fetch] {kind:4s} {os.path.basename(path):32s} {os.path.getsize(path) / 1024:6.0f} KB  {dur:5.2f}s  "
          f"← \"{item['title']}\"  {item['page']}")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["sfx", "meme"])
    ap.add_argument("query")
    ap.add_argument("--as", dest="name", help="file name = the tag the planner matches (e.g. vine-boom, shock-no-way)")
    ap.add_argument("--pick", type=int, default=1, help="which result to save (1 = first)")
    ap.add_argument("--list", action="store_true", help="show results only")
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args()
    results = (search_sfx if args.kind == "sfx" else search_meme)(args.query, args.top)
    if not results:
        raise SystemExit(f"[fetch] no results for {args.query!r}")
    for i, r in enumerate(results, 1):
        mark = "→" if (not args.list and i == args.pick) else " "
        print(f"  {mark} {i}. {r['title'][:60]:60s}  {r['page']}")
    if args.list:
        return
    if not args.name:
        raise SystemExit("[fetch] --as <tag-name> is required to save (the name IS the tag)")
    if args.pick < 1 or args.pick > len(results):
        raise SystemExit(f"[fetch] --pick {args.pick} out of range (1–{len(results)})")
    save(args.kind, results[args.pick - 1], args.name)


if __name__ == "__main__":
    main()
