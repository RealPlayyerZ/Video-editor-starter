---
name: background-music
description: "Lays a background music bed UNDER the voice on a near-final cut — a FLAT constant bed by default (no ducking, no fade-in, −18 dB, short tail fade-out only). Ducking + fade-in are opt-in. OPTIONAL, format-agnostic (any short or long video). Runs after captions, before final render. Triggers: add background music, add a music bed, lay music under, BGM, add a soundtrack, put music behind this."
---

# Background Music — Flat Bed Under the Voice

Optional step **6**. Takes a near-final cut and lays a music bed under the voice.

**The default is a FLAT bed:** the music sits at **one constant level for the whole video** — no sidechain ducking, no fade-in — with only a short tail fade-out at the end. The voice arrives peak-limited at −6 dBFS (≈ −21 dB mean) from the static rough-cut chain, so a quiet fixed bed (−18 dB) rides cleanly under it. A peak limiter guards the sum; there is **no loudnorm** on the flat path (single-pass loudnorm on a finished mix pumps and re-introduces the very level variation we're avoiding).

> **Why flat is the house default:** ducking (music dipping under the voice and swelling back up in the gaps) made past mixes get audibly *louder and quieter in parts*. A flat bed has a measured loudness range of **0.0 LU** — it does not move. That's the default. Ducking and fade-in are **opt-in only.**

Most useful on **short-form explainers**, but works on any format. It's opt-in — skip it unless asked.

## When to run
After **Captions (5)**, before **Final render (7)**. Long-form skips captions, so for long-form it runs right after the graphics/second-pass cut. Always operate on the **latest rendered cut**, never on raw.

## Where the music comes from
Drop a track into `projects/<job>/audio/`. Two ways to get one:
1. **Your own / licensed track** — drop an `.mp3`/`.wav`/`.m4a` into `audio/`. Use the newest file there.
2. **Generate one** (royalty-free, no copyright strikes — on brand) via the vendored HyperFrames media tool: `npx hyperframes bgm` (see `hyperframes-media`). Prompt the mood to match the reel, write the result into `audio/`.

If `audio/` is empty and no track is pointed at, ask one line: *"Drop a music track in `audio/` or want me to generate one — what vibe?"*

## Run it
```bash
.claude/skills/background-music/scripts/mix-music.sh \
  <near-final-video.mp4> \
  projects/<job>/audio/<track>.mp3 \
  projects/<job>/outputs/<job>-music.mp4 \
  [bed_db] [duck] [fadein]
```
- Output is non-destructive — `<job>-music.mp4`, never clobbering the no-music cut. That music-mixed file is what **Final render (7)** exports as the deliverable.
- `bed_db` — music gain. **Default −18 (quiet, clearly background).** More negative = quieter: `-24` ≈ barely-there, `-16` ≈ noticeable, `-12` ≈ prominent. Stay negative — this is a bed, not a duet. Balance is taste; re-run with a different `bed_db` to tune.
- `duck` — **`off` (default) = FLAT constant bed, no ducking.** `on` = opt-in sidechain auto-duck (music dips under voice, swells in the gaps) **and** re-normalizes the whole mix to −14 LUFS. Only turn it on when you specifically want the bed to breathe with the talking.
- `fadein` — music fade-in seconds at the start. **Default `0` = no fade-in (the bed is just there).** Pass e.g. `2` for a 2-second fade-in. Opt-in.

**Default (flat) is just three args past the output** — no flags needed:
```bash
mix-music.sh cut.mp4 audio/track.mp3 out-music.mp4
```

## Ducked bed with track rotation — for reaction videos (added 2026-09-08)

When the video plays embedded clips that carry their **own** audio (a trailer, someone else's
video, gameplay), the flat bed fights that audio. For those jobs use the ducked mixer instead of
`mix-music.sh`. It fades the bed out before each clip, holds silence through it, fades back in
after — and rotates through several generated beds so a long video never loops one track.

```bash
# 1) generate a few distinct beds (Lyria; house mood for reactions is energetic-dark, not "happy")
.claude/skills/background-music/scripts/gen-lyria-bed.py projects/<job>/audio/ai-bgm --mood energetic-dark --count 3

# 2) mix them under the VOICE-ONLY cut, ducking across the creator's own timestamps
.claude/skills/background-music/scripts/mix-music-ducked.py \
  projects/<job>/outputs/<job>.sweep.mp4  projects/<job>/outputs/<job>.music.mp4 \
  --tracks projects/<job>/audio/ai-bgm-v1.mp3 projects/<job>/audio/ai-bgm-v2.mp3 projects/<job>/audio/ai-bgm-v3.mp3 \
  --duck 1:34-2:10 3:02-3:34 4:36-5:45 --bed-db -24
```

**Rules this mode enforces — every one was a shipped bug on 2026-09-08 (see
`workflows/reaction-video.md`):**
- **The input must be the voice-only cut** (voice + SFX, no music yet). Ducking layered on top of a
  file that already has a flat bed leaves the old bed playing straight through every window — and
  the build log looks fine. The script warns when the input has no quiet pauses at all.
- **Duck windows come from the creator's watch-through timestamps** (`m:ss-m:ss`), not from guessing
  off the transcript. Ask for them; apply them verbatim.
- Fades are built per-segment, chunk-locally (ffmpeg's `afade=t=in:st=X` silences *everything*
  before X, so one long filter chain is never used); all intermediates are PCM; AAC is encoded once.
- It **verifies its own output**: every window midpoint must match the voice-only input (bed truly
  silent) and a natural pause outside the windows must be clearly louder (bed truly present). A
  failing result is renamed `*.FAILED.mp4` and the script exits non-zero — it does not ship quietly.
- Run it **before** the outro (the outro's audio crossfade blends this bed into the outro track).
  `-24 dB` is the house level for reactions after the creator's "music exceeds my voice" note.

## Tuning notes
- The script loops the track to cover the full video and fades the tail out over the last ~1.2s (always on — a clean ending, not a level move).
- Voice intelligibility is the priority. If the bed feels too present, drop `bed_db` further (e.g. −22). If it's buried and you want it more felt, raise toward −16. Keep it flat — don't reach for ducking just to make it louder; lower the bed or raise it as a whole.
- **Don't default to ducking.** It's there for the rare case you want the bed to swell in the gaps. The flat bed is the house sound.
- Verify after: play it, or `ffprobe`/`ebur128` the output. On the flat path the bed sits at a constant level (the mix's loudness range tracks the *voice*, not the music); on the duck path the mix is re-normalized to −14 LUFS.
