---
name: graphics-plan
description: Step 3a. Read the cut's transcript and decide, beat by beat, whether a line gets a graphic, what kind, and where. Writes projects/<job>/graphics-plan.json + .md. Never renders anything. Triggers — plan the graphics, where do graphics go, what visuals for this, graphic direction.
---

# Graphics plan — decide before you build

The cut is done and the transcript is on the cut's clock. Before a single graphic is made, decide what the
video needs. This step writes the plan; step 3b builds it; step 4 (the owner's second pass) edits it.

## Run

```bash
python3 .claude/skills/graphics-plan/scripts/segment-script.py projects/<job>
```

That splits the transcript into **beats** — one thought each, ended by a sentence or a pause, never longer than
about nine seconds — and writes `graphics-plan.beats.json`. Read it. Then write the plan.

## Decide, per beat

For every beat ask, in this order:

1. **Does the viewer need to see something to get this line?** A number, a name, a list, a thing on a screen,
   a comparison. If the words carry it on their own — and most do — the answer is **none**. A talking head
   with nothing on screen is not a problem to fix. Over-decorating is.
2. **If yes, what's the smallest thing that does it?**

| Kind | Use it for | Not for |
|---|---|---|
| `title` | the one line that names what this video is about, once, near the top | every section |
| `stat` | one number the owner says out loud, big | a paragraph of numbers |
| `list` | three-to-five items said in sequence | two items (just say them) |
| `quote` | someone else's exact words, attributed | paraphrases |
| `screenshot` | a real thing the owner is reacting to — an article, a post, a screen | a stock image standing in for it |
| `zoom` | a punch-in on the owner for emphasis; the cheapest graphic there is | more than once a minute |
| `card` | long-form only: a reading card while the owner reads a passage aloud | short-form |

3. **Where, exactly?** Start on the first word that makes it relevant, end when the thought ends — usually the
   beat's own boundaries. Two graphics never overlap. Leave the beat before and after clean so it can land.

## Write the plan

`projects/<job>/graphics-plan.json`:

```json
{"graphics": [
  {"beat": 3, "start": 12.40, "end": 17.85, "kind": "stat", "content": "$765M", "note": "the loss figure, as he says it"},
  {"beat": 9, "start": 41.10, "end": 44.00, "kind": "zoom", "content": "", "note": "punch in on 'they knew'"}
]}
```

and `graphics-plan.md` — the same plan as a readable list the owner can scan in thirty seconds: beat, time,
kind, what it says, and one line of why. If a beat got **none**, it isn't listed; the default is nothing.

## Format rules

- **Short-form** (9:16): graphics live in the top half; the owner's face is the bottom half. Everything stays
  inside the safe box — nothing above 200 px or below 1620 px. Captions sit on the middle seam, so a graphic
  never crosses y 880–1080.
- **Long-form** (16:9): graphics are panels beside or over the owner, plus zooms. No burned captions.
- **Gameplay**: the plan is mostly punch-ins on reactions and the comedy layer; see `workflows/gameplay-comedy.md`.

## What this step is not

It doesn't render. It doesn't pick fonts or colors — those come from `brand-kit.md`. It doesn't decide the
cut — that was step 2, and if the plan makes a cut look wrong, say so instead of planning around it.

## Report

```
GRAPHICS PLAN — 14 beats, 5 graphics (1 title, 2 stats, 1 screenshot, 1 zoom), 9 beats clean
projects/<job>/graphics-plan.md
```

Then step 3b builds them, and the owner reviews excerpts.
