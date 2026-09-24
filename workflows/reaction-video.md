# Reaction videos — full recipe

Formalized 2026-09-08 off `projects/gpt-astra-6-reaction/` and `projects/dlss-5-reaction/` (the
two reference jobs — read their files alongside this if anything is ambiguous). A **reaction
video** here = the creator on camera reacting to content that plays on their screen (a trailer,
tweets, someone else's video), with the creator's own facecam punched in for the hook and for
personal-take beats, wide the rest of the time. Some of the embedded content carries its **own
audio**, which is what makes the music step different from every other job type.

This is a variant of CLAUDE.md steps 2–7 for long-form content that `content-classifier` flags
as `reaction`. It is **not** an article-reaction (no reading-mode cards — see
`workflows/article-reaction.md` for those).

The single most important idea: **the creator's watch-through timestamps are the input.** Zoom
windows, duck windows, and restored cuts all arrive as "at 8:05 fade the music out, back in at
9:22" — this recipe is built so those land verbatim and get verified on the delivered file.

## Pipeline

1. **Intake** — normal (CLAUDE.md step 1). Copy the raw recording into `projects/<job>/raw/`.
   Name the job after the content (`dlss-5-reaction`, never the camera file).

2. **Rough cut, reaction cadence** — transcribe once (`cut`'s `transcribe.sh`), then build
   the cut list with the reaction rules instead of the default filler-kill:
   ```bash
   cd projects/<job>
   python3 ../../presets/reaction/build_cuts.py            # words.json -> transcript/cuts.json
   ```
   Keeps every natural pause ≤ 3.0 s (reaction cadence — the creator thinking, laughing,
   watching) and hard-cuts dead air longer than that. Then **report the numbered cut list to the
   creator as `m:ss` ranges** and wait: some "dead air" is an embedded clip playing with its own
   audio, and only the creator knows which. They answer with "restore cuts 9, 10, 13…" (and
   sometimes a narrower window: "cut #9 but 4:09–4:15 instead of 4:01–4:20"):
   ```bash
   python3 ../../presets/reaction/restore_cuts.py --keep 1,5,6,7,8,15,16,17   # cuts to KEEP; all others restored
   bash ../../presets/gameplay/splice_segments.py projects/<job>       # re-splice -> outputs/<job>.mp4
   ```
   Output: `outputs/<job>.mp4` (the base cut — the only durable input for everything below) and
   `outputs/<job>.transcript.json`.

3. **content-classifier** — run normally; expect `reaction`.

4. **Zoom windows — from the creator.** Write `projects/<job>/zoom-plan.json` with *typed*
   windows covering the whole duration, straight from their words ("intro zoom to 0:41, back in
   on me 22:04–22:45"):
   ```json
   { "job": "<job>", "zoom_trigger_style": "manual",
     "windows": [
       { "start": 0.0,    "end": 41.0,   "type": "zoom", "reason": "opening hook, punched in" },
       { "start": 41.0,   "end": 1324.0, "type": "wide", "reason": "screen content + facecam" },
       { "start": 1324.0, "end": 1365.0, "type": "zoom", "reason": "closing personal take" },
       { "start": 1365.0, "end": 1676.3, "type": "wide", "reason": "through the true end" } ] }
   ```
   Every `zoom`↔`wide` boundary becomes a sweep transition in step 7. `apply-zoom.py` only wants
   the zoomed windows, so also write `zoom-plan-zoomonly.json` = the `type: "zoom"` entries only.

5. **Measure the punch-in crop once** — `uv run workflows/zoom-crop.py projects/<job>/outputs/<job>.mp4`
   → `zoom-crop.json`. If the webcam might have moved mid-recording, re-measure a specific window
   with `projects/gpt-astra-6-reaction/measure_crop_window.py <video> <t0> <t1> <out.json>` and
   **compare renders, not drawbox previews** — an early "the mid-video zoom is wrong" call on
   gpt-astra-6 was a bad visual read; an exact crop+scale render matched the source pixel-for-pixel.

6. **Apply the zoom** — `presets/punch-in-zoom/apply-zoom.py outputs/<job>.mp4 zoom-plan-zoomonly.json zoom-crop.json outputs/<job>.zoomed.mp4`
   (regenerable; hard cuts at every boundary by design — step 7 replaces those with sweeps).

7. **Assemble with transitions** — `presets/reaction/assemble_reaction.py <job>` → 
   `outputs/<job>.composited.mp4`: one span per window, the locked sweep whoosh at every internal
   boundary (primitives imported from `presets/sweep-intro/build.py`), the untouched voice track
   padded to the video's real length, whoosh SFX at each boundary. **Voice + SFX only — no music
   yet.** That ordering is load-bearing (see rules).

8. **Sweep intro** — the video opens on a zoom window, so use target-crop mode with the crop from
   `zoom-crop.json` (`x,y,w,h`):
   ```bash
   presets/sweep-intro/build.py outputs/<job>.composited.mp4 outputs/<job>.sweep.mp4 \
     --frame-source outputs/<job>.mp4 --target-crop <x>,<y>,<w>,<h>
   ```
   (Generic mode if a job ever opens wide.)

9. **Music — ducked, rotated, on the voice-only cut.** Generate beds, then mix across the
   creator's duck windows:
   ```bash
   .claude/skills/background-music/scripts/gen-lyria-bed.py projects/<job>/audio/ai-bgm --mood energetic-dark --count 3
   .claude/skills/background-music/scripts/mix-music-ducked.py \
     outputs/<job>.sweep.mp4 outputs/<job>.music.mp4 \
     --tracks audio/ai-bgm-v1.mp3 audio/ai-bgm-v2.mp3 audio/ai-bgm-v3.mp3 \
     --duck 0:59-3:54 8:05-9:22 10:08-11:03 --bed-db -24
   ```
   The mixer verifies its own output (window midpoints silent, bed present elsewhere) and refuses
   to hand back a failing file. Full rules in the `background-music` skill.

10. **Outro** — `presets/outro/apply-outro.sh outputs/<job>.music.mp4 audio/outro-music-royaltyfree.m4a outputs/<job>-final.mp4 "" 0.3 8.2`
    (the two reference jobs ran the outro track at +8.2 dB; the outro asset itself is silent).
    The script verifies its own tail is not frozen before splicing — see rules.

11. **Verify the delivered file** — `workflows/verify-final.py outputs/<job>-final.mp4` must print
    `RESULT: PASS`. `finalize.sh` runs this itself before promoting; run it by hand after any
    re-render that is supposed to be "the fix".

12. **Export** — `./finalize.sh <job> --apply` → `outputs/<job>.final.mp4` + the Downloads copy.
    Thumbnail via `thumbnail-generator`. Title/description/social copy are outside this repo.

## The second-pass loop (the creator watches, sends timestamps)

Re-run from the **earliest affected step only**:

| Feedback sounds like | Change | Re-run from |
|---|---|---|
| "restore cut 9 / cut 4:09–4:15 instead" | `restore_cuts.py --keep …` | step 2 (re-splice), then everything |
| "zoom back in on me at 22:04" | `zoom-plan.json` (+ zoomonly) | step 6 |
| "fade the music out at 8:05, back in 9:22" | `--duck` list | step 9 only (cheap — audio-only, seconds) |
| "music is louder than my voice" | `--bed-db` (house: −24) | step 9 only |
| "same music the whole way through" | more `--tracks` (generate `--count 3+`) | step 9 only |
| "I'm frozen right before the outro" | the outro seam — should be impossible now | step 10, then verify |

Keep every superseded final as `outputs/<job>.final.<why>.mp4.bak` (e.g. `.oldbed-still-present`,
`.frozen-tail-v2`) so a regression can be A/B'd, and only update the Downloads copy from
`finalize.sh` once `verify-final.py` passes.

## Standing rules (each one shipped as a bug on 2026-09-08 before it became a rule)

- **Music goes on the voice-only cut, never on top of a file that already has a bed.** The
  "ducked" rebuild on both reference jobs was layered onto the earlier flat-bed final; every duck
  window went silent on the NEW layer while the OLD bed kept playing straight through. Two
  "fixed" deliveries, the build log clean both times. Caught only by A/B'ing a duck-window
  midpoint against the flat-bed file itself (matched to 0.1 dB).
- **`afade=t=in:st=X` silences everything before X** — never one long filter chain; per-segment,
  chunk-local fades only (`mix-music-ducked.py` does this).
- **PCM for every intermediate, one AAC encode at the end.** Per-chunk AAC + concat clicked at
  every boundary and read as "overlap"; on a 28-min file it also drifted the later windows.
- **The outro seam:** `apply-outro.sh`'s original tail cut (`-ss` input-seek ~2 s before the end
  of the file) produced a single frame held for ~2 s on both jobs. Fixed at the source in
  `apply-outro-v2.sh` (two-stage seek, longer tail, frame-difference check, duration check).
- **Verify the DELIVERED file, not the steps.** A first freeze fix passed every component check
  and the delivered file was still frozen (a stream-copied head overshot 2.3 s into the frozen
  zone). Frame-hash the output; measure the output's audio at a real silence gap. Build logs and
  same-timestamp `volumedetect` on a talking section are not evidence — a −24 dB bed barely moves
  aggregate stats under speech but is unmistakable in a pause (voice-only ≈ −80 dB, bed ≈ −37 dB).
- **`-shortest` is not a fix.** If a rebuilt component runs long and `-shortest` trims it, you've
  cut something off the end without looking at it. Compute the target length and trim explicitly.
- **Stream-copy cuts near an existing splice point are unreliable** (`-t <body_end> -c:v copy`
  overshot 2.3 s at a PTS discontinuity). Re-encode, and cut well clear of the seam.
- **Re-check the ground truth before diagnosing** — a version number, a file's real location
  (WSL vs the `D:\` mirror), whether an app auto-updated between two checks.
- **Nothing lives only in `/tmp`.** Scratch goes in `projects/<job>/assemble_work/` (WSL clears
  `/tmp` on restart and it has wiped a build before).
