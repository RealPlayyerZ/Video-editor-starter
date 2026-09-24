---
name: content-classifier
description: "Classifies a video's content type from its finished-script transcript — the auto-detection step (2.5) between rough-cut and graphics-plan. Reads the transcript (and a few sampled frames) and decides: reaction, combat-gameplay, weapon-breakdown, guide, or hardware-review. That single decision then drives graphics-plan (run full plan, or skip to zoom-only treatment), the zoom-effect trigger style, and the default thumbnail-generator template — so none of those need to be specified by hand each job. Runs automatically, every job, right after rough-cut. Does NOT decide short-form vs long-form (that's still graphics-plan's format question) and does NOT build anything. Triggers: classify this content, what type of video is this, detect content type, auto-classify, what format is this footage."
---

# Content Classifier — auto-detect what kind of video this is

**Step 2.5 of the pipeline.** Runs automatically right after rough-cut, before graphics-plan. Reads
the finished-script transcript rough-cut just produced and decides **what kind of video this actually
is** — a judgment call, the same way `graphics-plan` makes judgment calls, not a mechanical script.

**Why this exists:** every job so far has required you to say up front "this is a reaction video,
skip graphics" or "this is a weapon breakdown, use the gradient-callout template." That's you doing
the AI's job. This skill reads the same transcript `graphics-plan` and `thumbnail-generator` already
read and makes that call itself — write it once, to one file, and every downstream skill reads it
instead of asking you again.

**This skill decides the category. It does not build graphics, apply zoom, or generate a thumbnail.**
Those are still separate steps — this just removes the manual "tell it what kind of video this is"
step in front of them.

---

## Inputs

1. **The job** — reads `projects/<job>/outputs/<job>.transcript.json` (rough-cut's finished script).
   If it doesn't exist, rough-cut hasn't run yet — stop and say so.
   **If the file exists but its `text`/`words` are empty** (confirmed real case: `be98-pro-router-review`
   — a heavily custom multi-clip HyperFrames build that never routed through the standard
   rough-cut→splice transcript path) — don't guess from nothing. Fall back to sampled frames (below) +
   the raw clip filenames/count in `projects/<job>/raw/`, and if that's still not enough to call it
   confidently, ask directly: *"What kind of video is this — reaction, live gameplay, a weapon/build
   breakdown, a guide, or a product review?"*
2. **A handful of sampled frames** (optional but recommended) — pull 4-6 frames spread across the cut
   with `ffmpeg -ss <t> -i outputs/<job>.mp4 -frames:v 1 -q:v 2 <out>.jpg` to visually confirm the
   transcript-based read. Full-screen gameplay with a small facecam bubble in a corner reads very
   differently from a large talking-head with an inset video card, even when the words alone are
   ambiguous.

---

## The five categories

These map 1:1 to `thumbnail-generator`'s five existing templates and to the zoom-trigger styles
`content-classifier` assigns — this skill isn't inventing new buckets, it's automating the pick you've
already been making by hand every job.

| Category | What it sounds/looks like | `graphics_approach` | `zoom_trigger_style` | `thumbnail_template` |
|---|---|---|---|---|
| `reaction` | Reacting to an external video/post/clip — long stretches quoting or paraphrasing someone else's content, phrases like "let's watch this," "let's react to," "he's saying," pausing to comment then resuming. Visually: a video card / other creator's content on screen, or you narrating over paused footage. | `skip` — no liquid-glass panels, punch-in zoom carries it | `pause-then-resume` | `face-cam-reaction` |
| `combat-gameplay` | Live match/session commentary in the moment — kill/death callouts, real-time exclamations ("oh my god," "wait what"), map/loadout selection, a running play-by-play. Visually: full-screen gameplay HUD, small facecam corner bubble. | `skip` — punch-in zoom on reaction beats carries it | `exclamation-highlight` | `combat-composite` |
| `weapon-breakdown` | Analytical testing of one specific item/build — perk names, DPS numbers, "is this the new meta," damage comparisons, a verdict. Visually: weapon inspect screens, stat panels. | `full` — liquid-glass panels for the DPS charts/perk callouts | `none` | `gradient-callout` or `cosmic-hero` (pick by hook energy — verdict/tier claim → cosmic-hero, punchy but no full tier claim → gradient-callout, matching `thumbnail-generator`'s own rule) |
| `guide` | Neutral how-to/unlock/informational walkthrough — "first you do X, then Y," no strong opinion or verdict. | `full` | `none` | `in-game-render` |
| `hardware-review` | Product/gear review — unboxing, specs, setup walkthrough, "is it worth it," a speed test or benchmark. Visually: physical product in frame, a dashboard/settings UI. | `full` for the feature-walkthrough segments, punch-in zoom for direct-to-camera talking segments | `pause-then-resume` (for direct-to-camera segments) | `cosmic-hero` |

**If the transcript genuinely straddles two categories** (e.g. a PVP session with a long analytical
digression on why a specific build won the fight), pick the one that describes **most of the runtime**,
and note the secondary signal in `reasoning` — don't invent a sixth category.

---

## Step 1 — Read and classify

Read `outputs/<job>.transcript.json`. Look for the signal words/patterns in the table above, and weigh
them against a few sampled frames if the transcript alone is ambiguous (e.g. "let's go" reads as
`reaction` or `combat-gameplay` depending on whether it's said over paused external footage or live
gameplay HUD — the frames settle it).

**Confidence matters more than speed here.** If two categories are both plausible and roughly balanced,
don't guess — ask the one-liner: *"Is this a reaction to someone else's content, or live gameplay
commentary?"* (or whichever two categories are competing). Matches the project's existing "ask one
line when it's not obvious" pattern (see `graphics-plan`, `cut`) — don't silently pick wrong and
let a bad thumbnail template or skipped graphics-plan surface three steps later.

## Step 2 — Write the classification

Write **`projects/<job>/content-classification.json`**:

```json
{
  "job": "division2-lore-reaction",
  "content_type": "reaction",
  "graphics_approach": "skip",
  "zoom_trigger_style": "pause-then-resume",
  "thumbnail_template": "face-cam-reaction",
  "confidence": "high",
  "reasoning": "Transcript opens 'we actually have a lore video to watch... we're going to react to it' — explicit reaction framing, then long stretches of the source video's own narration interspersed with the creator's commentary."
}
```

Report back tight: the category picked, the two fields that actually change behavior
(`graphics_approach`, `thumbnail_template`), and the one-line reasoning. If confidence is `low`,
say so plainly and ask before continuing.

---

## Handoff

- **`graphics-plan`** reads `content-classification.json`'s `graphics_approach`. `full` → run the plan
  as normal. `skip` → don't run graphics-plan at all; the video goes straight to the zoom-effect
  treatment (once that skill exists) instead. This replaces you having to say "skip graphics-plan,
  this is just a reaction video" by hand, like on `division2-lore-reaction` and
  `division2-pvp-experience`.
- **The zoom-effect skill** (not yet built — this classifier's `zoom_trigger_style` field is what it
  will consume once it exists) picks its trigger heuristic from here instead of you specifying
  pause-timestamps manually every job.
- **`thumbnail-generator`** reads `content-classification.json`'s `thumbnail_template` as the default
  pick, instead of asking you "reaction or weapon-breakdown?" every time. You can still override it —
  this is a default, not a lock.

This skill does ONE thing: read the transcript and decide the category. It never builds graphics,
applies zoom, or generates images.
