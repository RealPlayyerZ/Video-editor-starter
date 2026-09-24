# Long-form — YouTube

Landscape, the footage's own size (1920×1080 or 2560×1440). No reframe, no burned captions — YouTube's own
captions do that job — and no length target: cut for pace and keep the substance.

## Graphics (step 3)

Long-form graphics sit **beside or over** the owner rather than in a separate half:

- **Punch-in zooms** — the cheapest and most-used graphic. A crop onto the owner's face for a line that
  deserves it. `presets/punch-in-zoom/` does this from a zoom plan; `workflows/zoom-crop.py` measures the crop
  once per job so every zoom lands on the same framing.
- **Reading cards** — when the owner reads a passage aloud (an article, a post), the passage appears as a card
  over blurred b-roll so the viewer can read along. `presets/reading-mode/` builds them from the transcript;
  see `workflows/article-reaction.md` for the whole recipe.
- **Panels** — a screenshot or clip beside the owner while they react to it. `workflows/reaction-video.md`.
- **The comedy layer** — for gameplay: freeze-frames, sound hits, on-screen text, reaction cut-ins.
  `workflows/gameplay-comedy.md`.

## Safe zones (16:9)

YouTube's player draws over the bottom ~10% (the scrub bar and controls) and the duration/LIVE badge in the
bottom-right corner. Keep text and key graphics out of the bottom 10% and the bottom-right corner. Everything
else is yours.

## Intro / outro

If `brand-kit.md` names an intro treatment, it goes on after assembly; if it names an outro video, the outro
step dissolves into it and plays it to the end. Both are optional; the examples in `presets/` show the
mechanism with the original author's own look — replace the look, keep the script.

## Music

A flat bed under the voice by default. When the footage carries its own audio — a trailer, a clip being
reacted to — the bed is **ducked** under it, and the duck is verified by measuring a silent gap, not assumed.
`.claude/skills/background-music/`.

## Thumbnail

Always, for long-form. The owner's paragraph in `brand-kit.md` section 7 becomes an image-model prompt in the
same shape every time; face references live in `assets/face-refs/`. The pipeline can also burn a title strip
onto a clean generated image if the image model keeps misspelling it.

## Shorts from the long video

Once a long-form video ships, `presets/shorts/clipper.py` ranks its moments and builds the picks as their own
9:16 jobs — `workflows/shorts-clipper.md`. Nothing is re-transcribed; the Short's captions come from the same
words the long cut was built on.

## Order of operations

cut → zoom plan → graphics plan → build (cards / panels / zooms) → assemble with transitions → owner reviews
excerpts → intro → music → outro → verify on the file that ships → final → thumbnail alongside.
