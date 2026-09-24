---
name: zoom-plan
description: "Decides WHEN the locked punch-in zoom fires — reads the finished-script transcript plus content-classification.json's zoom_trigger_style and picks the actual timestamp windows: pause-then-resume (reaction videos — zoomed during intro/direct-address, zoomed out during passive external-content playback) or exclamation-highlight (combat-gameplay — brief opening punch-in plus a zoom on each reaction/highlight moment). Outputs zoom-plan.json. Does NOT measure the crop position (workflows/zoom-crop.py) and does NOT render anything (presets/punch-in-zoom/apply-zoom.py). Triggers: plan the zoom, where should the zoom happen, punch-in zoom timing, zoom-in moments."
---

# Zoom Plan — decide WHEN the punch-in zoom fires

**Runs after `content-classifier`, alongside/before `graphics-plan`.** The punch-in zoom itself is a
**locked, permanent treatment** (see [`presets/punch-in-zoom-style.md`](../../../presets/punch-in-zoom-style.md))
applied to essentially every video — this skill's only job is deciding the *timestamps*, the same way
`graphics-plan` decides *where* graphics go without building them.

**This skill decides timing. It does not measure the crop position or render anything.**
`workflows/zoom-crop.py` measures *where* to point the crop (per video, per the Lab Note on why fixed
coordinates broke across videos); `presets/punch-in-zoom/apply-zoom.py` burns the decided windows in
using that measured crop. This skill just produces the list of windows.

---

## Inputs

1. **`projects/<job>/content-classification.json`** — read `zoom_trigger_style`. If it's `"none"`
   (weapon-breakdown / guide content), **stop — this video doesn't get punch-in zoom**, say so, and
   don't write a plan. If the file doesn't exist yet, run `content-classifier` first.
2. **`projects/<job>/outputs/<job>.transcript.json`** — the finished-script transcript.

## The two trigger styles

### `pause-then-resume` (reaction videos)

The pattern locked in on `division2-lore-reaction` after several rounds of correction:

1. **Intro window, zoomed in from 0:00** — while the creator does channel-branding / hook talk,
   before the reacted-to content actually starts playing. Ends the moment the source video's own
   content begins (a phrase like "let's give it a watch," "here it is," "let's watch this," followed
   by the reacted-to video's own narration starting) — **not** a fixed timestamp; find the actual line
   where playback starts and end the intro zoom there, with a little buffer so the line finishes
   before the cut (the exact word getting cut off mid-pronunciation was a real, repeatedly-flagged bug
   — always end the window a beat after the sentence completes, never mid-word).
2. **Zoomed OUT (no window) during passive playback** — stretches where the transcript reads as the
   *source* content's own narration/dialogue, not the creator addressing the audience. This is a
   judgment call, not a mechanical rule: third-person narration about the game/lore/topic = source
   content; first-person direct address ("you guys," "wait," a question, a reaction) = the creator
   talking. When genuinely ambiguous, lean toward NOT zooming — an extra normal-view moment is far
   less noticeable than an incorrectly-held zoom during someone else's content.
3. **Zoomed back IN whenever the creator pauses the source content to talk directly to the audience**
   — open a window at the first clearly-creator line after a stretch of source-content narration,
   close it when source-content narration resumes (or, if it's the final comment before the video
   ends, close at the actual end of speech).
4. **Final outro window** — if there's direct-to-camera wrap-up talk after the reacted-to content
   finishes, that gets a window too (same as any other pause-then-resume moment).

### `exclamation-highlight` (combat-gameplay videos)

The pattern locked in on `division2-pvp-experience` (10 real reaction-zoom windows, each ~2-2.4s):

1. **Brief opening punch-in** — same universal intro zoom as above, but shorter (a few seconds), since
   there's no "waiting for external content to start" — just enough to establish the hook before
   settling to normal gameplay view.
2. **A window at each reaction/highlight moment** — genuine exclamations ("oh my god," "no way,"
   "what," a surprised laugh, a notable callout like a big damage number or a clutch moment), **not**
   every excited-sounding line — the effect loses impact if it fires constantly. Aim for the same
   density as the validated PVP job: roughly one punch-in per genuinely surprising beat, not per
   sentence. Each window ~2-2.4s — long enough to register, short enough to snap back to the actual
   gameplay.
3. Everything else stays zoomed out — full-screen gameplay is the default state for this content type,
   the zoom is a highlight reel on top of it, not the base state.

## Step — Write the plan

Write **`projects/<job>/zoom-plan.json`**:

```json
{
  "job": "division2-lore-reaction",
  "zoom_trigger_style": "pause-then-resume",
  "windows": [
    { "start": 0.0, "end": 31.4, "reason": "intro/channel talk before clicking play" },
    { "start": 148.2, "end": 156.9, "reason": "pauses source video to react: 'wait, monkeypox on the dollar?'" },
    { "start": 812.1, "end": 818.99, "reason": "wrap-up talk after source video ends" }
  ]
}
```

Report back tight: how many windows, total seconds zoomed vs. total runtime, and flag (⚠️) any window
you're genuinely unsure about rather than silently guessing — same discipline as `graphics-plan`'s
`reason` field on every beat.

---

## Handoff

1. Run `uv run workflows/zoom-crop.py projects/<job>/outputs/<job>.mp4` to measure the crop position
   (once per video — the facecam position is constant for the whole video).
2. Run `presets/punch-in-zoom/apply-zoom.py` with this plan + that crop to actually render the
   punch-ins (see `presets/punch-in-zoom-style.md` for the exact recipe and the ffmpeg gotcha that
   makes segment-based static crops non-negotiable).
3. After rendering, `uv run workflows/zoom-crop.py --verify <rendered-output>.mp4` on a sample punch-in
   segment — must print ✓ PASS (face not clipped at any edge) before treating this as done.

This skill does ONE thing: decide the timestamps. It never measures pixels or renders video.
