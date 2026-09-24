# Shorts clipper — long-form → ready-to-post 9:16 clips

Built 2026-09-08 as the Video Editor Map's "second entry" node: a finished long-form job
re-enters the pipeline as several short-form jobs. Tool: [`presets/shorts/clipper.py`](../presets/shorts/clipper.py)
+ the comedy layer [`presets/shorts/gags.py`](../presets/shorts/gags.py) (2026-09-09).
Style reference: **the reference channel's Shorts** — six studied on 2026-09-08 (table below), then **17 on
2026-09-09 with transcripts** → [`reference-channel-study.md`](reference-channel-study.md), which set the defaults.
Ceiling: **60 s** (the creator's call); the ranker aims at ~20 s.

## Run it

```bash
# 1. rank the moments (no rendering) — prints a numbered list + a title suggestion each
presets/shorts/clipper.py <job>

# 2. build the ones the creator picks — --captions is REQUIRED (a per-video call, see below)
presets/shorts/clipper.py <job> --pick 1,3 --captions on
presets/shorts/clipper.py <job> --window 8:05-8:25 --captions off --layout stacked   # explicit moment
presets/shorts/clipper.py <job> --pick 2 --captions on --gags heavy                  # comedy layer: off|light|medium|heavy
presets/shorts/clipper.py <job> --window 4:11-4:33 --captions off --pin "quiver: put the fries in the bag"   # his chat-pin hook
presets/shorts/clipper.py <job> --pick 1 --captions off --insert 12.5:assets/memes/my-photoshop.png:3   # a bespoke cut-in
presets/shorts/clipper.py <job> --pick 1 --captions on --style tiktok                 # text pops / flash / shake flavour

# see what the comedy layer heard and would do, without rendering
presets/shorts/gags.py projects/<clip> --plan-only
```

**Authoring a Short by hand (2026-09-09, `--style punchy`)** — when the editor decides the moments
instead of the planner, all in clip-seconds on top of the automatic plan:
`--sfx boom@3.5,tick@5,tick@6,pipe@12,womp@16.9` (any tag in `assets/sfx`) · `--text "he left.@24:2.2"`
(a text pop regardless of style) · `--freeze 4.62:0.45` (freeze-frame + record scratch; captions shift
with it) · `--face-zoom 3.4-4.8:1.5` (a punch-in, replacing automatic ones in that span) ·
`--content-zoom 5-9:1.5:0.5,0.72` (stacked layout: zoom INTO the content box, centred at fractions of
it — a countdown, a kill feed) · `--no-memes` (sounds and zooms only) · `--static-tail 7` (declare a
deliberately still ending — a results screen, an empty chair under a laugh — so the freeze gate allows
it while still policing everything before it). Measure first: sample the content column at 2 fps
with `drawtext=%{pts\:hms}` so the ticks land on the real counter changes, not on a 1-fps guess.
The worked example is `exodus-crash-wipe-short-01` (`clip.json` → `authored`). Two synthesized
sounds exist for countdowns: `tick` and `heartbeat`.

**`--layout intercut` (2026-09-09, the creator's own call after watching the stacked cut):** the
creator full-frame (the FACE crop), cutting to the **game full-frame** inside `--cut-to-game a-b`
windows and back. The game is shown as a **6:5 window** (`GAME_ASPECT`) centred on a blurred,
darkened cover-crop of itself — the whole view at a sane size — because the 9:16 column of a
first-person game "looked like the gun was too zoomed in". `--content-zoom` still works inside the
game windows (zoom into a counter); `--face-zoom` on the face segments.

**Automatic game windows (default when `--cut-to-game` is omitted):** two signals.
(1) *The transcript* — words closer than 0.8 s form a speech run; a run gets the face from 0.15 s
before its first word to 0.4 s after its last (≥1.2 s); a mumble under 0.5 s with no trigger word
stays on the game; a sub-1 s game gap between two face runs is absorbed; after the last word the
face stays (the reaction is on camera). (2) *Motion events* — the mean frame-to-frame difference of
the game region on a 96×54 grey thumbnail at 4 fps: gameplay idles at ~10–20, a fall or a death
runs 40–60 for a second or more, lying dead reads ~1. A burst above max(2×median, median+15, 25)
for ≥0.75 s is an event; bursts under 1.5 s apart merge (looking over the edge, then the drop);
ranked by **energy** (motion × time — by peak alone three camera whips outscored a real fall);
the top three carve the game back out of a face run from 0.3 s before to 0.8 s after, so the
thing that happened is on screen and the face returns for the reaction. ffmpeg's scene score is
useless here (a first-person fall measured 0.2). First real result (`leap-of-faith-short-01`):
game 0-3.3 · 6-14.4 · 18.3-24.8 (edge → fall) · 27-30.3, face everywhere else — no timestamps typed.

**`--loudness -14`:** Shorts sit around −14 LUFS; the base cut is near −20. A static gain + the
true-peak limiter (never dynamic `loudnorm`), measured on the delivered file and corrected on a
second pass because the added sounds carry energy the input measurement can't see (first pass
overshot by 1.7 dB).

**Slow motion, a global sound level, no sweep (2026-09-10, from the creator watching v1 on his phone):**
`--slowmo a-b[:factor]` stretches the video (setpts) AND slows the audio the same amount (atempo — the
voice drops with it, which is half the joke); everything downstream (words → captions, authored
sounds, text, cut-ins) is remapped through `make_remap()`, so authored times stay in original clip
seconds. Gotcha that bit once: the per-segment `-t` after `-i` is an OUTPUT duration, so a stretched
segment needs `sp x (b - a)` of it or the slow motion is cut in half while the audio runs full length; and OUTPUT-side `-ss` compares timestamps AFTER the filter, so with `setpts=2*PTS` a seek to 22 s admits frames from 11 s — every segment now seeks on the INPUT side (`-ss a -t (b-a) -i raw`). After any timestamp-changing filter, strip the result at 2 fps with timestamps and read it before delivering.
`--sfx-trim -6` trims every sound effect by that many dB (his headphones found the defaults loud).
The sweep intro is now OFF on Shorts (`--sweep` to opt in) — its whoosh and wipe over the first
half-second read as a fade-in. Falling sounds in the library from myinstants: `goofy-yell`
(the one), `cartoon-falling`, `slide-whistle-down`. Worked example: `leap-of-faith-short-01` v2 —
him → face → him at 13–17, the game held until he is at the bottom, the fall at half speed with the
Goofy yell and a zoom on him / the face / him inside it.

**Style presets (`--style`, default `reference`)** — calibrated by the 17-Short study in
[`reference-channel-study.md`](reference-channel-study.md): `reference` = full-frame reaction-clip cut-ins on a
blurred cover of themselves, **the Short ends on a fitting clip with a 0.4 s fade to black**
(his signature), no text pops, no flash/shake; `tiktok` = text pops, red flash + shake on
booms, inset memes, an impact hit as the button. `--text-pops on|off` overrides either.
`--pin "name: message"` draws his pinned-chat box (dark, orange name) for the first 3 s — 8 of 17
of his open on one and he reads it aloud. `--insert t:file[:dur]` places a creator-made
image/GIF/MP4 full-frame at clip-time t (his bowl-cut photoshop, the gravestone).

Each pick becomes a standard job, `projects/<job>-short-NN/`, and is finished end to end:
`raw/` (16:9 slice of the clean base cut) → `outputs/<clip>.reframed.mp4` (9:16 reframe with
punch-ins) → **comedy layer** → `outputs/<clip>.mp4` (the base the caption builder reads) →
locked TikTok/raw captions if `--captions on` → locked sweep intro → `verify-final.py --no-outro`
→ `finalize.sh --apply` → `outputs/<clip>.final.mp4` + Downloads.
`clip.json` records the window, layout, punch-ins, gag list, title suggestion and the exact crop
filter; `gags.json` the beats it heard and the full plan; `intent.md` the title/provenance.
`--no-finish` scaffolds only.

Inputs it relies on from the source job: `outputs/<job>.mp4` (clean base cut — never the final),
`outputs/<job>.transcript.json` (canonical words; sliced and rebased, never re-transcribed),
`zoom-crop.json` (the measured face — run `workflows/zoom-crop.py` if missing) and
`zoom-plan.json` (decides face vs stacked framing in `--layout auto`).

## The style (from the the reference channel study, 2026-09-08)

Six recent Shorts, 12–29 s (one gameplay clip at 60 s), all 1080×1920/60 fps:

| Trait | What his editor does | What the clipper does |
|---|---|---|
| Length | 12–29 s, one 60 s | `--min 12 --max 60 --target 20` (60 s is the hard ceiling) |
| Open | **Cold open** — first frame is him mid-reaction or a striking screenshot; no title card | No hook card (opt-in `--hook-text`) |
| Framing | Creator **big in frame**, full-frame facecam | FACE layout in punched-in moments — crop height ≈ 3.2× the measured face (face ≈ 30 % of frame). Deliberately tight; see the recording note below |
| Emphasis | Hard-cut **punch-in zooms** on reaction beats, every 2–4 s | `plan_punchins`: 1.35× on hook words / fresh sentences, 1.4–3.5 s holds, ≥2 s apart, ≤45 % of the clip |
| Gameplay / screen content | **Stacked: facecam on top, content below** | STACKED layout (face 40 % top at ≈2× face height, content 60 % below) — the content box never zooms |
| Evidence | Full-screen screenshots held ~2 s, scrolling chat, a pinned "someone in chat said X" line; the editor **zooms into the thing itself** | **Motion-ROI**: the content box auto-zooms to the region with *sustained* motion during the clip (pixels changing in ≥60 % of ~10 sampled frame pairs = the embedded video he's watching; page scrolling only moves things in a few pairs and is ignored), facecam masked out, min 38 % of the frame, fitted to the box's aspect. `--content-crop x,y,w,h` to force it, `--no-roi` for the wide page. Pinned-chat / screenshot cut-ins are not automated yet |
| Captions | **None** in 6/6 | **Per-video call, `--captions on|off` is required.** Muted viewers favour captions; his audience doesn't need them |
| Audio | Loud (−13 to −20 LUFS), continuous | Base-cut audio as is (already normalized by rough-cut); no music by default |
| Outro | None | None (creator's call: the 20 s brand outro would be a third of a Short) |
| Title | 2–4 word punch ("Cross Caught Lacking", "Sony will see us") | `title_suggestion` per clip — a starting point, not a decision |
| Description | Template: business email, `#destiny2`, join link, "Check out our Most Recent Video!" | Outside this repo (the channel's own template) |

## The comedy layer (`gags.py`, 2026-09-09)

The creator's brief: *every Short catchy and funny — sound effects, memes, or just the footage
when it carries itself.* The layer runs between the reframe and the captions, in one ffmpeg pass.

**What it listens for** (the clip's transcript slice + an RMS envelope of its audio — no numpy):
trigger words/phrases with a sentiment (shock · fear · dead · hype · sad — "wait", "what", "no way",
"nightmare", "bro", "nah", "insane", "womp womp"…); loud **non-speech** (a laugh, a shout: energy
where no word is active — a *long* stretch of it is the embedded video playing, so the first word
after it becomes the reaction beat); the pause after a punchline; the button (last word). Anything
in the first 3 s gets a hook bonus. His delivery is limited to a tight range, so +3.5 dB over the
speech median already counts as loud.

**What it does** — one move per beat, never the same move twice running:

| Gag | Sound + picture | When |
|---|---|---|
| boom | sub-bass hit · 0.35 s shake · red flash · text pop of *his own word* ("NIGHTMARE FUEL", "UNBELIEVABLE.") | shock / fear line |
| hit | impact · short shake · text pop | hype line; or a second impact after a boom |
| freeze | 0.45 s freeze-frame · record scratch (captions shift with it) | "wait… what?" — once per Short |
| meme | tagged image/GIF/MP4 cut in ~1 s (+pop) — stacked: replaces the content box; face: the band above his head | the laugh, the deadpan, a pause after a line |
| text | big Inter Black word pop, slight tilt, 2-frame pop-in | whenever no meme fits |
| womp | sad trombone + "WOMP WOMP" | a let-down landing |
| crickets | a dead pause | 1.2–2.5 s of air after a "?" or "!" |
| bass | 0.6 s bass-boost/crush | one genuinely loud beat |
| button | impact + shake on the last word | always (if inside the clip) |
| whoosh | quiet, under every punch-in | not counted as a gag |

**Timing rules** — `--gags medium` (default): a gag inside the first 3 s if there is a beat there,
one on the button, ≥3.5 s apart, ≤ round(dur/5) gags (3–8), gag screen-time ≤25 %. `light` =
whooshes + at most one sting, no shake/flash/memes. `heavy` = ≥2 s apart, up to dur/2.5, memes on
every laugh, bass drop on the button. **"Nothing"** is a legitimate plan: a long pause on reaction
footage is usually him *watching*, not dead air — landings only get a gag when something specific
fits (trombone on a let-down, crickets after a hanging question, a matching reaction meme).

**Libraries** — by file-name tag, no manifests to edit:
[`assets/sfx/`](../assets/sfx/README.md) (the creator's files beat `synth/`, the placeholder set
`presets/shorts/make-sfx.py` generates from scratch — no downloads, no rights) and
[`assets/memes/`](../assets/memes/README.md) (a tag with no file degrades to a text pop). Levels:
each file peak-measured once, mixed at a per-tag level under the untouched voice, `alimiter` at
−1 dB; the mix check on the DLSS test read boom +8 dB over the voice, whooshes/pops +0.5–1 dB.

**The two approved sources (creator's list, 2026-09-09) and `fetch-library.py`:**
`presets/shorts/fetch-library.py sfx "vine boom" --as vine-boom` pulls a sound button from
**myinstants.com**; `… meme "wait what" --as shock-wait-what` pulls a reaction clip (with its own
sound) from **vlipsy.com**. `--list` to look, `--pick N` for another result. Every pull is HTTPS
from those two hosts only, content-type + magic-byte checked, ffprobe-decoded, then re-encoded to
a clean WAV/MP4 with metadata stripped (nothing is ever opened in a browser or executed; the
starter set was Defender-scanned clean). The starter set wired these character sounds into the
plan: `vine-boom` (boom), `record-scratch` (freeze), `bruh` (under a deadpan text pop),
`emotional-damage` (a burn: cooked/clown/ratio/cope/mid/washed…), `windows-error-buzz`
(broken/bugged/wrong/crash), `oh-no-no-no` (a disgust line), `airhorn` (a LOUD hype line),
`laugh-track` (a joke lands into a pause), `crickets` (a question left hanging),
`sad-trombone` (a let-down), `discord-ding` (he reads chat — free, ≤2), `metal-pipe` (35 % of
buttons), `fahh` (the bass gag). A vlip's audio rides its cut-in (up to 2.5 s); 16:9 clips and
stills sit on a blurred, darkened cover-crop of themselves instead of black bars. Free-tier
vlips carry a small Vlipsy watermark bottom-left (Pro removes it).

**Standalone / second pass:** `gags.py projects/<clip> --plan-only` prints the beats and the plan;
`--intensity` re-renders from `outputs/<clip>.reframed.mp4` (gone after finalize — re-run the
clipper for that window instead). Tuning knobs at the top of `gags.py`: `INTENSITY`, `TRIGGERS`,
`PHRASES`, `TEXT_POOL`, `SFX_GAIN`, `TEXT_CY`/`MEME_REGION`.

**Opus Clip** (the creator's sponsor) is welcome as the *moment picker* — its ranking is trained on
real engagement data, ours is a heuristic — but it can't do this layer; feed its picks in as
`--window m:ss-m:ss` and finish here. (A `--from-clip <opus-export.mp4>` that finds the window by
audio match is the obvious next convenience.)

## One recording change that matters — setup in [`obs-webcam-recording.md`](obs-webcam-recording.md)

His facecam is a **separate full-resolution source**. Ours is a small window inside a 2560×1440
screen capture, so the FACE layout upscales it ~3× and looks soft; STACKED stays crisp because
the face box is only ~1.4× and the content box is a downscale. **Record the webcam as its own
full-res file alongside the screen capture** (OBS: a second recording output / source record of
the camera scene) and the clipper can take a `--face-source` in a later revision to cut the
crisp full-frame look he has. Until then prefer STACKED for anything that isn't a pure
talking-head beat.

## How the ranking thinks

Windows start and end on natural pause boundaries (≥0.45 s or sentence punctuation). Score =
hook strength in the first 4 s (a weighted vocabulary — "insane", "nightmare", "leaked",
numbers, questions; his tics "check this out" / "look at this" count a little) + speech density
(<1.6 words/s means he is watching a clip, not talking — penalized hard) − long silences + a
clean ending + a strong start − distance from the target length. Overlaps >40 % are dropped.
It is a shortlist, not a verdict: the creator picks.

## Second pass

| Feedback | Change | Cost |
|---|---|---|
| "start it at 1:03 instead" | `--window 1:03-1:22` | one clip, ~2 min |
| "too much / too little zooming" | `PUNCH`, `PUNCH_GAP` at the top of clipper.py | one clip |
| "show the screen, not my face" / vice-versa | `--layout stacked` / `--layout face` | one clip |
| "captions this time" | `--captions on` | one clip |
| "add the hook card" | `--hook-text "..."` | one clip |

Superseded clips: `finalize.sh` keeps `<clip>.final.mp4` as the deliverable; re-running the same
window creates the next `-short-NN`, so nothing is overwritten.
