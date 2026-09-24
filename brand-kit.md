# brand-kit.md — make this editor yours

This is the one file that turns a generic editor into *your* editor. Everything else in this folder is
machinery; this is taste. Fill in Part A once, then tell Claude **"apply my brand kit"** and it does Part B.

Until every `<<placeholder>>` below is gone, Claude will refuse to start an edit — on purpose. Nobody should
ship a video carrying someone else's colors, handle, or hook. Not even mine.

---

# Part A — fill this in

## 1. Who you are

- **Name / handle:** <<HANDLE>>
- **Channel(s):** <<YOUTUBE_URL>> · <<TWITCH_URL_OR_NONE>> · <<OTHER_OR_NONE>>
- **What the channel is, in one line:** <<ONE_LINE>>
- **What you make most:** <<FORMATS — long-form reactions? article breakdowns? gameplay edits? Shorts? talking-head explainers?>>

## 2. How you sound

Captions, on-screen text, and any hook copy Claude writes should sound like you, not like a template.

- **Voice, in three words:** <<e.g. direct, hype, honest>>
- **Words you actually say:** <<e.g. "Guardians", "chat", "let's go", "we're so back">>
- **Words you never say:** <<e.g. corporate stuff, "content", "engage">>
- **What your audience calls themselves, if anything:** <<AUDIENCE_NAME_OR_NONE>>

## 3. Your colors

Three is enough. Hex codes. If you only have one, put it as the hero and let Claude propose the rest.

- **Hero** (your signature — the strip, the highlight, the thing people recognise): `<<#HEX>>`
- **Accent** (a second color for emphasis words and glows): `<<#HEX>>`
- **Background / dark** (cards, boxes, the base of your graphics): `<<#HEX>>`
- **Text on dark:** `#FFFFFF` unless you want otherwise: `<<#HEX_OR_LEAVE>>`

## 4. Your fonts

Put the font files in `assets/fonts/`. Only use fonts you're allowed to redistribute if you ever share this
folder — Inter (included, open license) is a safe default for everything.

- **Headline / impact font file:** `assets/fonts/<<FILE_OR_Inter-Black.otf>>`
- **Caption font file:** `assets/fonts/<<FILE_OR_Inter-Bold.otf>>`
- **Caption size at 1080 wide:** <<e.g. 48>> px

## 5. Your intro and outro (optional — leave "none" and Claude skips the step)

- **Intro treatment:** <<none | "sweep intro" (the included example) | a clip: assets/<<file>>>>
- **Outro video:** <<none | assets/<<file>> (a 16:9 clip; the outro step dissolves into it and plays it to the end)>>
- **Outro music:** <<none | assets/<<file>>>>
- **Background-music bed (default):** <<none | assets/<<file>>>> at <<−18>> dB

## 6. Your on-screen ask (optional)

The included layout example is a top-left "SUBSCRIBE FOR A …" strip with a logo and embers. If you want one:

- **Line:** <<e.g. SUBSCRIBE FOR MORE>>
- **Accent words:** <<how many words at the END of the line get the accent color, e.g. 2>>
- **Logo file:** `assets/logos/<<logo.png>>` (transparent PNG, roughly square)
- **When it appears:** <<e.g. 22>> seconds in, for 8 seconds

## 7. Your thumbnail look (one paragraph, in your words)

<<e.g. "Me large on the right, head and shoulders, one bold white line on a solid red strip bottom-left,
the subject on the left, dark cinematic background. Glasses on. No headset in video thumbnails; headset ON
for live-stream thumbnails."  Claude will turn this into an image-model prompt in the same shape every time.>>

- **Face reference photos:** put 4–8 in `assets/face-refs/` (only used for thumbnails; skip if you never want your face in one)

## 8. Words the transcriber gets wrong

WhisperX mishears names and brands. List them here and every transcript, caption, and graphic gets them right.

```
<<what_it_hears>> → <<what_it_should_be>>
<<what_it_hears>> → <<what_it_should_be>>
```

---

# Part B — what "apply my brand kit" does (so you can check it, or do it by hand)

1. Reads Part A and writes **`presets/brand.json`** — a plain file every builder reads:
   `{"handle","hero","accent","dark","text","font_headline","font_caption","caption_px","intro","outro",
   "outro_music","bed","bed_db","ask_line","ask_accent_words","logo","ask_at","thumbnail_look","corrections":{…}}`
2. Writes the corrections from section 8 into **`presets/caption-corrections.json`** (`auto` entries — silent
   single-word swaps; add anything you'd rather eyeball to `flag`).
3. Copies your intro/outro/music/logo paths into the example presets' defaults so `apply-outro.sh`, the sweep
   intro, and the layout builder pick them up without flags.
4. Renders **`projects/_brandcheck/outputs/brandcheck.mp4`** — ten seconds of a color card with your hero color,
   a caption in your caption font, and your ask line if you set one. Watch it. If it's not you, fix Part A and
   apply again.
5. Confirms there are no `<<placeholders>>` left in this file. That's the signal setup is done.

Nothing in Part B edits `CLAUDE.md`. Your identity there is written by you, once, in your words.
