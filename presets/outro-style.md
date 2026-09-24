# Outro — your LOCKED preset (every video, every format)

The standard sign-off tail appended to **every finished video**, short or long form.
Locked 2026-08-23 (`division2-lore-reaction` build). Apply verbatim every time.

Builder: [`presets/outro/apply-outro.sh`](outro/apply-outro.sh)

---

## 🔒 THE ASSET — locked

Source file: `<your outro video>` (any 16:9 clip; the step dissolves into it and plays it to the end
in WSL) — 20.78s, 4K (3840×2160), 60fps.

**Its own audio track is silent** (confirmed by measurement — true digital silence throughout, not just quiet).
The outro always needs a **separate music track laid under it** — it does not ship pre-scored.

## 🔒 THE TRANSITION — locked DaVinci preset, ported to ffmpeg

- **Video:** Additive Dissolve, 0.3s / 18 frames (at 60fps), centered alignment.
  - ffmpeg has no native "Additive Dissolve" transition — the closest built-in is `xfade=transition=fade`
    (a standard alpha crossfade). That's what the builder uses; flagged here as a known, accepted
    approximation, not exact optical-additive fidelity.
  - **Centered alignment**, ported correctly: `xfade`'s `offset` is where the transition *starts* in the
    first clip's timeline, and the transition consumes `offset → offset+duration` of input 1 plus
    `0 → duration` of input 2. For a transition that's centered on the cut (uses the last half of the
    transition-duration from clip 1's tail and the first half from clip 2's head, shortening total runtime
    by exactly the transition duration — the standard NLE crossfade-at-a-cut result), set
    **`offset = D1 - duration`** (NOT `D1 - duration/2` — that offset variant produces `offset + D2` as the
    total output length instead, which is a different, longer result). `D1` = the main video's duration.
  - Final duration = `D1 + D2 - 0.3`.
- **Audio:** Cross Fade 0dB, same 0.3s duration, same alignment → ffmpeg `acrossfade=d=0.3:c1=tri:c2=tri`
  (linear/triangular curve — "0dB" means no equal-power compensation bump at the crossover, just a plain
  linear ramp — `tri` is ffmpeg's linear curve and the correct match). `acrossfade` is inherently centered
  on the join (overlaps clip 1's tail with clip 2's head), no offset math needed on the audio side.
- Both inputs must match resolution/fps/pix_fmt before `xfade` — the outro is 4K/60fps source, main videos
  in this project are 2560×1440/60fps, so the outro gets scaled down (`scale=2560:1440:flags=lanczos,setsar=1`)
  before the splice, never the other way around (never upscale the main content).
- **Known gotcha (found on `division2-pvp-experience`, ffmpeg 8.0.1): `xfade` silently truncates the
  output when fed the full main video directly as input 1 once it's long (~400s+ reproduced).** It
  drops input 2 (the outro) entirely and outputs exactly input 1's own duration — exit code 0, with
  a correct-looking container duration despite the outro never landing in the file. Not a disk-space
  issue — confirmed via decode-level bisection that short/seeked clips of the same source always
  worked; only the untouched full-length file at an offset near its own true end failed. The builder
  works around this by splitting the main video into an untouched HEAD and a short (~1–2s) TAIL —
  both freshly transcoded (not stream-copied) so the seam is frame-exact — running `xfade` only on
  the short TAIL (proven reliable at that length), then concatenating HEAD + transitioned-TAIL via
  stream copy. `acrossfade` (audio) does not have this bug and still runs on the full-length audio
  in one pass.
- **Second gotcha, found 2026-09-08 on `gpt-astra-6-reaction` AND `dlss-5-reaction` (both shipped
  with it): the tail slice was cut with a single INPUT seek ~2s before the file's own end
  (`-ss $HEAD_DUR -i $VIDEO`), and on long re-encoded cuts that came back as ONE frame held for
  the whole tail — the creator freezes for ~2s right before the outro, container duration correct,
  exit code 0.** Fixed at the source (v2 of the builder): the tail is cut with a two-stage seek
  (fast input seek ~20s earlier, then an accurate output seek to the exact frame), the tail is ≥6s
  instead of 2s so the seam sits clear of the file's end, and the script now **verifies** the tail
  actually moves (frame-difference check) and that head + tail add back up to the input before it
  splices — a frozen tail aborts instead of shipping. `workflows/verify-final.py` re-checks the
  seam on the delivered file, and `finalize.sh` runs that gate before promoting.

## 🔒 THE OUTRO MUSIC — locked envelope

Reverse-engineered from the "Bass Windu and Obi Dawg" video's outro (measured via RMS-over-time on the
tail, confirmed the pattern below):

- **No fade-in.** The track starts at full/flat level exactly when the outro visual starts — any softness
  at the very edit point comes only from the 0.3s audio crossfade above, never an *additional* separate
  fade-in on the outro track itself.
- **Flat/steady** for the full outro duration — no ducking, no swell, no envelope movement.
- **Tail fade only** — fade out over the **final 1.2–1.5s** of the whole video (i.e. the last 1.2–1.5s of
  the outro clip, since the outro is always last). `afade=t=out:st=<outro_dur - 1.3>:d=1.3` is the builder's
  exact implementation (1.3s, mid-range of the locked 1.2–1.5s window).
- Track is **trimmed to exactly the outro's own duration** (~20.78s) before the fade is applied — it is not
  looped or extended.

## 🎵 Where the outro music track comes from

Generate fresh per job (or reuse one if you want a consistent outro sting across videos — not required).
**`npx hyperframes bgm` referenced in the `hyperframes-media`/`background-music` skill docs does not
actually exist** — checked 0.7.3 (pinned), 0.7.108, and latest 0.8.12, no `bgm` subcommand in any of them.
Generate directly via the `google-genai` SDK instead:

- Needs `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) set, and the `google-genai` pip package (lightweight,
  unlike the MusicGen CPU fallback — no need for that heavy path if a Gemini key is available).
- Model: **`models/lyria-3-clip-preview`** via `client.models.generate_content(model=..., contents=<mood prompt>)`
  — returns an ~30s MP3 in `resp.candidates[0].content.parts[0].inline_data.data`. (The longer
  `models/lyria-3-pro-preview` variant, ~150s, is what the *main-body background bed* uses instead —
  see `background-music` skill for that; the outro only needs the short clip model.)
- Mood: match the video's sign-off energy — upbeat/triumphant is the house default per the brand kit's
  hype/gamer-casual tone, but ask if a given job wants something different (e.g. a chill wind-down outro).

## Run it

```bash
presets/outro/apply-outro.sh \
  <input-video.mp4> \
  <outro-music.mp3> \
  <output-video.mp4>
```

Non-destructive — writes to whatever output path you give it, never overwrites the input. Run this as
the last step before `finalize.sh`, on the fully graphics/captions/music-mixed cut.
