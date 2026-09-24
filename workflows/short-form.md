# Short-form — Reels, TikTok, Shorts

Vertical, 1080×1920. Two treatments; pick one at step 3 (Graphics), not before — the cut is the same either way.

## The safe box — never break this

Phone apps draw their own UI over the top and bottom of a vertical video: the caption, the username, the
like/share column, the progress bar. Anything you put there gets covered.

| Zone | Pixels (of 1920 tall) | What goes there |
|---|---|---|
| top band | 0–200 | background only |
| **safe box** | **200–1620** | the face, every graphic, the captions |
| bottom band | 1620–1920 | background only |

Horizontally keep key elements 60 px off either edge. That's it. Every preset in this folder already obeys it.

## Treatment A — split-frame explainer

The screen is two halves. The owner's face fills the **bottom half** (y 960–1920, framed so the top of the
hair sits a little below the seam — measure it, don't eyeball it). Graphics live in the **top half**
(y 200–880). The captions sit **on the seam**, centered — `presets/captions/build.py --position center`.

Use it when the video explains something: the graphics carry numbers, lists, screenshots; the face carries
the delivery. Most graphics are on screen for one beat and gone.

## Treatment B — raw

The owner's face fills the frame. No split, no top-half graphics — at most a hook card for the first few
seconds and a punch-in zoom or two. Captions sit **low, under the face** — `--position low`.

Use it when the delivery *is* the content: a reaction, a story, a rant. Don't decorate it.

## Length

The shortest cut that still lands the point. One to two minutes is the ceiling for an explainer; a raw clip
can be twenty seconds if that's all it needs. The cut step already removed dead air — if it still feels long,
the problem is a tangent, not the pace.

## The 9:16 reframe

Most footage is shot 16:9. At the top of step 3, crop it to 9:16 around the owner's face, at full height.
`workflows/zoom-crop.py` finds the face and prints the crop; for a split-frame video, that crop is what fills
the bottom half.

## Captions

Always, the whole video, from the cut's transcript, never re-transcribed. The hook card (Treatment B) sits on
top of the captions; it never replaces them.

## Order of operations

cut → reframe → graphics plan → build graphics → owner reviews excerpts → captions → music (optional) →
verify → final. Captions go on **after** graphics are approved, because they're built from the transcript of
the cut that ships — change the cut and you rebuild both.
