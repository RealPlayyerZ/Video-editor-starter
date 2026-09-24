# Gameplay-comedy videos — the recipe (first build: `division2-legendary-mission`, 2026-09-13)

A long gameplay session (a Twitch VOD, 30–90 min) → a highlight edit that is *funny*: the creator's
reactions kept with enough gameplay to read, punch-ins on the exclamations, the comedy layer's sounds /
inset reaction clips / freeze-frames / shakes, a chat-screenshot cold open with the creator's popping
sound, the locked sweep intro, a music bed, the locked outro. Built as the template for every future
gameplay video ("experimental phase — make it so future gameplay can be included easily").
Tools live in `presets/gameplay/`; the comedy layer is `presets/shorts/gags.py` in its 16:9 mode.

## Pipeline (all in `projects/<job>/build-scripts/run_all.sh` on the reference job)

1. **Intake + transcribe** — normal. Twitch VOD downloads come in as `<id>-<id>-<uuid>.mp4`; name the
   job after the content. The VOD is the stream composite (game + facecam corner + overlays).
2. **Cut list — gameplay cadence:** `presets/gameplay/build_cuts.py <job> [--lead 1.0 --tail 0.6
   --filler-words 4 --filler-sec 2.2] --keep a-b … --drop a-b …`. Speech runs (gap ≤ 3 s) padded with
   a gameplay lead-in/tail, bridged when < 4 s apart, isolated filler ("Alright.", "Here we go.")
   dropped, `--keep` for the setup and the ending, `--drop` for the editor's calls (menu fumbling,
   looting apologies, traversal). Print with `--verbose`, read the list, tune. Target: the story
   beats — the decision, first fight, deaths, the carry, the completion — at 40–45 % of the raw
   (70 min → ~28 min on the reference).
3. **Splice** — `cut`'s `splice.sh` (copy `transcript/cuts.json` to `/tmp/video-editor/<job>/`
   first). Base cut `outputs/<job>.mp4` + `outputs/<job>.transcript.json`.
4. **Zoom crop** — `uv run workflows/zoom-crop.py outputs/<job>.mp4` (the facecam corner).
5. **Punch-ins — exclamation-highlight, computed:** `presets/gameplay/zoom_plan.py <job> --skip 0-19
   --first 20.05 --spacing 20 --max 40` → ~2.4 s windows on trigger words (gags.py's tables), hard
   cuts; `--skip` keeps them off the cold open. Writes `zoom-plan.json`, `zoom-plan-zoomonly.json`,
   `punchins.json`. Then `presets/punch-in-zoom/apply-zoom.py` → `outputs/<job>.zoomed.mp4`.
6. **Chat cold open:** put the messages in `chat-screenshots/messages.json` (name, Twitch colour, text,
   badges — transcribe them from the creator's screenshots; tiny screenshots blown up go to mush, so
   the cards are redrawn at full size) → `presets/gameplay/chat_cards.py assemble_work/cards
   --messages … --font-px 72 --x 110 --y 380 --start 1.2 --step 1.4 --until 18.0`. Big by design.
   The creator's pop is `assets/sfx/popping-noise.wav` (tag `popping`, from your own sound folder
   Sounds`).
7. **Comedy layer, 16:9:** `presets/gameplay/gags_wide.py <job> --cards assemble_work/cards/cards.json
   --intensity medium --style gameplay --sfx-trim -3` (`--plan-only` first to read the plan).
   What changed in gags.py for this (2026-09-13, backup `gags.py.bak-20260913`): `canvas(w, h)` +
   layout `wide` (text at 2/3 height, inset cut-in box bottom-left, 34 % wide), style `gameplay`
   (inset clips, flash + shake, no auto text pops, no clip ending), long-form density (one gag per
   ~25 s at medium instead of the Shorts cap of 8, ≥ 6 s apart, overlays ≤ 10 % of screen time, up to
   4 freeze-frames / bass drops), `overlays=` for positioned PNGs, tag `popping`. Shorts behaviour is
   untouched (the canvas defaults to 1080×1920).
8. **Sweep intro** — generic mode (`presets/sweep-intro/build.py in out`), since the video opens wide
   on the game with the cards.
9. **Music** — flat bed at −20 dB via `mix-music.sh` (game audio never pauses, so the ducked mixer's
   pause-based self-check does not apply); verify with a volumedetect A/B against the pre-music file.
10. **Outro, verify, finalize** — locked (`apply-outro.sh … "" 0.3 8.2`, `verify-final.py`,
    `finalize.sh --apply`).

## Rules learned on the reference build
- The cold open needs the messages as TEXT (names + colours), not pixels — ask for them if only
  screenshots arrive; the on-stream chat alert ("DONT DO IT ×20") is also in the footage itself.
- Keep the setup in whole (`--keep 0:00-2:16`): the decision to go legendary IS the premise.
- Run `build_cuts.py --verbose` and read every kept line before splicing — the automatic pass keeps
  menu fumbling and looting talk that reads as dead weight; those are `--drop` calls, not code.
- Everything downstream (zoom plan, gags) is in CUT time; `--keep`/`--drop` are RAW time.

## Two-pass render for long inputs (patch 2, the same night: `TWO_PASS_OVER = 120 s` in gags.py)

In the single ffmpeg graph (video overlays + freeze splice + 49 delayed sound inputs into one amix)
every sound after the first ~6 s silently never reached the mix — ffmpeg exited 0, the log was clean,
and the identical audio graph run on its own mixed everything. Long inputs therefore render the video
with the spliced base audio (PCM) in pass 1, mix sounds + reaction-clip audio + bass + limiter in an
audio-only pass 2 (`assemble_work/gags/ffmpeg-cmd-pass2.json`), then stream-copy mux. Shorts keep the
single pass. Verify a delivered comedy render the way this was caught: a 0.5 s RMS-envelope A/B of the
output against its input at a few sound times — never trust the exit code for a mix.

### 2026-09-15 — two-pass render, patch 3: pass 1 is video-only, pass 2 builds the audio from the input

The 9/13 two-pass patch still ran the freeze-hold audio splice (asplit → atrim → anullsrc → concat) inside
pass 1's video graph and had pass 2 read that PCM track back from `pass1_video.mp4`. On the full 30-min
division2-legendary-mission render that produced **1551 s of audio under 1785 s of video** — ffmpeg rc 0, clean
log, the same "audio branch inside the big video graph silently loses data" failure class as the sounds
drop-out. `presets/gameplay/patch_gags_audiopass.py` (applied; backup `gags.py.bak-20260915`) makes pass 1
`-an` and moves the splice into pass 2, which now reads the ORIGINAL input — the standalone graph that shipped
9/13 at full length. Shorts are unchanged (single pass, same graph as before).

Gates that catch this class: `synccheck.py offset` after the gags stage (it reported +0.42 s at 900 s and no
audio at 1700 s), and a runner "done" check that uses the SHORTEST stream duration, not the container's
(`build-scripts/run_v5_resume.sh` in the job — the resume-capable runner pattern).

### 2026-09-15 — the frozen-tail bug: ffmpeg rebuilds a filter graph when the input's colour tags flip

Symptom: the two-pass gags render came back with the right frame count but one frozen frame from 1601 s to
the end (verify: "freeze sweep (seam) … ~8 s static run"); the previous run's audio had ended at 1551 s.
Cause (found with a `-loglevel verbose` rerun of the exact pass-1 command, `build-scripts/diag_pass1.sh`):
the zoomed base is a stitch of per-segment encodes whose colour tags differ (unknown vs tv/bt709 — the first
segment of `splice_segments.py`'s output was untagged, apply-zoom's re-encodes inherited per segment). When
the tag flips mid-stream ffmpeg logs "Reconfiguring filter graph because video parameters changed" and
REBUILDS the graph: the trim/setpts/concat freeze-splice restarts at pts 0 ("*** dropping frame N at ts 0,
1, 2…"), every later frame is dropped as past, and the `-loop 1` / `-stream_loop -1` overlay inputs pad the
output with the last frame until `-t`. The 9/13 build was fine only because splice.sh is one encode.
Fixes: `presets/gameplay/patch_gags_reinit.py` (applied, `gags.py.bak-20260915b`) puts `-reinit_filter 0`
on the base input of both passes; `splice_segments.py` now passes the source's colour tags + `setsar=1` to
every segment encode. Rule: any pts-resetting graph (trim/concat/setpts) over a stitched base needs
`-reinit_filter 0`, and a stitched base should be probed for per-segment tag flips
(`ffprobe -skip_frame nokey -show_entries frame=pts_time,color_range,color_space`).

## Chat cards from the VOD's chat replay (2026-09-15) — no more screenshots

Twitch stores the full chat replay with every VOD. `presets/gameplay/vod_chat.py` (stdlib only) turns it
into card candidates on the CUT timeline:

```bash
python3 presets/gameplay/vod_chat.py fetch <job> <vod-id-or-url>   # → projects/<job>/chat/vod-<id>.json
python3 presets/gameplay/vod_chat.py map   <job>                   # VOD time → output time through transcript/cuts.json → chat/mapped.json
python3 presets/gameplay/vod_chat.py pick  <job> --top 25 [--user NAME] [--grep REGEX] [--from S --to S] [--kept-only]
python3 presets/gameplay/vod_chat.py cards <job> --ids 3,13,56 [--badges verified,sub] [--hold 4] [--truncate]
```

`pick` prints id, output time (`~` = the message fell in a dropped region and was snapped to the next kept
segment), raw time, user, text, and the transcript words spoken ±2 s at that output moment — that column is
how you find the READ-ALOUD beat, which is where a card belongs (0–13 s after the post time). `cards` writes
`chat/messages.json` in `chat_cards.py`'s format (names, real Twitch colours, badges from the data) plus
`chat/timing.json` (start = mapped time, end = start + hold) for the card pass. Bots and gift/sub notices are
scored −9; a streamer mention inside a donation URL is not a mention.

Facts learned on the first two VODs:
- **Twitch's replay starts ~20 s into the stream** (Rush Hour's first message is at 0:23). Anything said
  in the opening seconds is only recoverable from the creator's screenshots — keep that route for cold opens.
- **Stock chat-downloader 0.2.8 is broken for Twitch VODs** (its `VideoMetadata` persisted-query hash was
  retired → `PersistedQueryNotFound`). `presets/gameplay/fetch_chat.py` wraps it: sends that one query as
  plain GraphQL, replaces the stdin-polling retry prompt with a sleep (it ate the rest of a `bash -s`
  heredoc), then runs the unchanged tool. Installed with `uv tool install chat-downloader`; nothing else.
- `author.name` is the lowercased login; match on `display_name`. Replay times are whole seconds, so a
  message within 1 s of a cut boundary can land on either side.
- Real badges/colours differ from the hand-made cards (ironbanner876 has no badge on Rush Hour, the mods are
  "mod" not "verified", DarkestShadow41 is #FF0000 not #FF4500) — `--badges` overrides for the look.
- `map` probes the delivered base cut and trusts the FILE length over the cut-list sum (Rush Hour's base is
  6.1 s shorter than its list — a splice.sh tail loss; the transcript carries ~40 words past EOF).
