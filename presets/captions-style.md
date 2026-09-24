# Captions — the locked short-form preset

Captions are for short-form only. Long-form gets none burned in — YouTube's own captions do that job.

## The look (what never changes)

- **One phrase at a time**, on a solid dark box that cuts on and off. The box never moves, never animates.
- **Words pop in on their own timestamps** — a 0.12-second rise and fade, one word at a time, so the caption
  reads with the voice instead of ahead of it. That's the whole feel; don't add anything to it.
- **The box is pre-sized to the whole phrase**, so it doesn't grow as words appear.
- **Inside the safe box.** Nothing above 200 px or below 1620 px on a 1080×1920 frame. Platform UI lives in
  those bands and will cover anything you put there.

## The knobs (what brand-kit.md sets)

| Knob | Comes from | Default |
|---|---|---|
| font | `brand.json → font_caption` | Inter Bold |
| size | `brand.json → caption_px` (at 1080 wide; scales with the frame) | 48 |
| text color | `brand.json → text` | white |
| box color | fixed | black |
| position | `--position center` (the middle seam of a split-frame short) or `--position low` (under a full-frame face) | center |
| phrase length | `--max-chars` | 26 |
| new phrase after a pause of | `--gap` seconds | 0.6 |

## How to run it

```bash
python3 presets/captions/build.py projects/<job>                    # center — split-frame explainer
python3 presets/captions/build.py projects/<job> --position low     # under the face — raw / talking head
python3 presets/captions/build.py projects/<job> --until 20         # a 20-second preview first
```

Input is `outputs/<job>.transcript.json` — the words on the cut's clock, corrections already applied. It is
never re-transcribed here. Output is `outputs/<job>.captioned.mp4`, the same length as the cut to the frame.

## Why it's built this way

This ffmpeg has no text renderer, so the words are drawn with Pillow. Rather than hundreds of PNG overlays,
every frame of the caption layer is drawn and streamed into ffmpeg as one transparent video, then composited
in a single pass. Faster, deterministic, and the layer can't drift against the cut because both are driven by
the same frame rate and the same transcript.

## Timing rule

Captions are built from the transcript **of the cut that ships**. If the cut changes, re-run the splice (which
rewrites the transcript) and then re-run captions. Never hand-nudge a timestamp — fix the cut.
