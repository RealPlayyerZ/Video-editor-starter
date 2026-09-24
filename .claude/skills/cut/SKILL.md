---
name: cut
description: Step 2 of every job. Transcribe once (WhisperX word timestamps), decide the cut from the transcript, splice it frame-exact, and hand back the cut plus the transcript on the cut's timeline. Triggers — edit this, cut this, rough cut, trim this, chop this up, tighten this.
---

# Cut — the transcript decides, ffmpeg obeys

The raw clip goes in. A tight cut and the finished transcript come out. Everything downstream — graphics,
captions, music, verify — reads that transcript, so this step is the one that has to be right.

## The three commands

```bash
.claude/skills/cut/scripts/transcribe.sh projects/<job>            # once per job; reused forever
python3 .claude/skills/cut/scripts/scan-transcript.py projects/<job>   # what did it mishear?
python3 presets/gameplay/splice_segments.py <job> [--amp 10]      # cuts.json -> outputs/<job>.mp4 + transcript
```

## How to do it

**1. Transcribe.** Run `transcribe.sh`. First run builds its own Python environment (minutes). It writes
`projects/<job>/transcript/words.json` — every word with a start, an end, and how sure the recogniser was.
If that file exists, it's reused. Never transcribe twice; if the footage really changed, `--force`.

**2. Read it, then scan it.** Read `words.json`. Run `scan-transcript.py` and judge each suspect in context —
a real mishear of a name or brand goes into `presets/caption-corrections.json` (`auto`, single word, so it can
never shift a timestamp); a one-off for this video goes in `projects/<job>/corrections.local.json`; a correct
proper noun gets skipped. Corrections are applied when the transcript is exported, so they reach every
later step automatically.

**3. Decide the cut.** Write `projects/<job>/transcript/cuts.json`:

```json
{"segments": [
  {"clip": "clip.mp4", "start": 1.21, "end": 4.66, "transcript": "the line you kept"},
  {"clip": "clip.mp4", "start": 9.02, "end": 15.40, "transcript": "the next line"}
]}
```

Order is the final order. Segments can come from any clip in any order. Start a segment about 0.05 s before
the first word you want and end it about 0.08 s after the last one; never cut inside a word.

Cut without being asked:

| Cut | Because |
|---|---|
| filler — um, uh, like, you know, basically — when it carries nothing | dead weight |
| false starts and stutters | breaks the flow |
| a line said more than once | keep the **last** take, drop the rest — the owner doesn't need to be asked |
| silence longer than 0.4 s | dead air |
| "okay let me start over", throat clears, the preamble before the first real line | production noise |
| a tangent that doesn't serve the video's point | the viewer's time |

Keep the owner's rhythm. Not every "like" is filler; some are how they talk. That's a taste call — make it,
and say so in the report.

**4. Splice.** `splice_segments.py` cuts each segment frame-exact (it counts frames, it doesn't trust
seconds), carries the audio through whole, applies a fixed gain and a hard limiter once on the assembled
track, and writes `outputs/<job>.mp4` plus `outputs/<job>.transcript.json` — the kept words on the cut's clock,
corrections applied. Default gain is +10 dB; on a recording that's already hot (peak near 0 dB) use `--amp 0` —
gain into a limiter on hot audio lifts the room noise between words and reads as echo.

**5. Report.** Like this, and nothing longer:

```
CUT DONE — 12:40 → 8:15 (35% cut)
projects/<job>/outputs/<job>.mp4

1. [clip @ 1.21–4.66]   "the line you kept"
2. [clip @ 9.02–15.40]  "the next line"
…
⚠ segment 7 is borderline — say the word and it's gone.
```

## Rules

- The raw file is never modified. Ever.
- `words.json` is transcribed once. `cuts.json` is the edit; change the edit, re-splice, never re-transcribe.
- Corrections are single whole-word swaps. If a fix needs two words to become one, flag it for the owner
  instead — merging words changes the count and breaks the timing.
- Long-form has no length target: cut for pace, keep the substance. Short-form aims for the shortest cut
  that still lands the point.

## Then

Hand off to step 3, **graphics-plan**, with `outputs/<job>.transcript.json`. Captions (step 5) and the
graphics plan both read that file — nothing downstream ever runs the recogniser again.
