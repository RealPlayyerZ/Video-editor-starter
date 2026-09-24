# Punch-in zoom — your LOCKED preset (reaction & combat-gameplay content)

The standard facecam punch-in, applied per `content-classification.json`'s `zoom_trigger_style` —
`pause-then-resume` for reaction videos, `exclamation-highlight` for combat-gameplay. Locked
2026-08-26, generalizing the recipe that was hand-tuned across three real jobs the night before
(`be98-pro-router-review`, `division2-lore-reaction`, `division2-pvp-experience`) into a reusable
standard instead of re-deriving crop numbers and trigger timing from scratch every time.

Timing decided by: [`zoom-plan` skill](../.claude/skills/zoom-plan/SKILL.md) → `zoom-plan.json`
Crop position measured by: [`workflows/zoom-crop.py`](../workflows/zoom-crop.py) → `zoom-crop.json`
Rendered by: [`presets/punch-in-zoom/apply-zoom.py`](punch-in-zoom/apply-zoom.py)

---

## 🔒 THE MAGNITUDE — locked as a METHOD, not a number

**Adaptive — the zoom ratio is a computed output, never a fixed input.** `workflows/zoom-crop.py`
finds the tightest crop (matching the source's own aspect ratio) that comfortably contains the
facecam, headphones, and breathing room, then whatever magnification that implies IS the zoom for
that video. Validated at **2.55-2.60x** on `division2-lore-reaction`'s actual layout — a different
video with a different facecam size/position will get a different number, and that's correct
behavior, not drift to fix.

**This wasn't the first version.** An earlier pass locked a flat **2.0x on every video** (echoing the
original DaVinci-sourced parameters from the very first hand-tuned jobs). A direct side-by-side
comparison rendered on real footage (`division2-lore-reaction`, 2026-08-26) showed exactly why that
was wrong: this video's facecam is a fairly large window against a plain background, not a small
dense corner-bubble, so a flat 2.0x left a lot of dead space around the face instead of reading as an
actual punch-in. Three real options were rendered and compared before picking: fixed 2.0x (too
loose), this adaptive fit (**chosen**), and an even tighter face-only crop at 4.34x that read as a
genuine dramatic punch-in but clipped a follower-notification overlay out of frame (rejected —
keeping the overlay fully visible was worth the extra dead space). If a future job's comparison ever
favors the tighter/clipping variant instead, that's a legitimate per-video call, not a preset change.

## 🔒 THE CROP POSITION — measured per video, never reused

**The single most important rule in this preset.** A real bug shipped once already: the lore video's
exact crop coordinates were reused directly on the PVP video, and it clipped the face and a
follower-notification overlay — the facecam position isn't identical video-to-video (recording
resolution, OBS scene state, or webcam position can all drift slightly). **Always run
`workflows/zoom-crop.py` fresh on the job's own base cut** — never copy a previous job's numbers.

## 🔒 THE TRANSITION — hard cuts, locked

Snap directly to the zoomed crop and back — **no eased eye-catching to open/close**. This was a
deliberate choice weighed directly against a smoother alternative (see the ffmpeg gotcha below for
part of *why*), but it's also a legitimate stylistic call on its own: hard-cut punch-ins are a
standard, recognizable reaction-content technique, not a compromise.

## 🔴 THE FFMPEG GOTCHA — why this MUST be segment-based static crops, never one dynamic expression

**Root cause, reconstructed from the original debugging session** (the project-memory note that
first captured this didn't survive — it was written to `/tmp` mid-session and lost to the same
volatility that once wiped the sweep-intro preview files; this write-up is a from-scratch
reconstruction of what was actually diagnosed, not a recovered artifact):

ffmpeg's `crop` filter breaks when **both width and height are driven by dynamic (time-varying)
expressions simultaneously** across a single continuous filter spanning the whole video timeline —
attempting one `crop=w='...(t)...':h='...(t)...':x=...:y=...` expression to animate in and out of the
zoom at multiple points in one pass produced corrupted/incorrect output. The fix that actually shipped
correctly: **never build one dynamic crop expression across the whole timeline.** Instead:

1. Split the video into segments at every zoom-in/zoom-out boundary from `zoom-plan.json`.
2. Each **zoomed** segment gets its own **static** `crop=W:H:X:Y,scale=SW:SH` filter (fixed numbers
   for that segment only, from `zoom-crop.json` — no time-varying expression at all).
3. Each **normal** segment passes through untouched (or re-encoded plain, no crop filter).
4. Concat every segment back together (hard cut at each boundary, matching the locked transition
   above — there is no crossfade to blend, which is also why the transition choice above isn't purely
   aesthetic).

This mirrors exactly the pattern `apply-outro.sh` already uses for its own unrelated xfade bug (split
into pieces, transcode each piece individually, concat) — segment-and-concat is this project's proven
answer whenever a single-pass ffmpeg filter misbehaves over a long/complex timeline.

## Run it

```bash
# 1. Decide timing (writes projects/<job>/zoom-plan.json) — see the zoom-plan skill.

# 2. Measure the crop position once (writes projects/<job>/zoom-crop.json):
uv run workflows/zoom-crop.py projects/<job>/outputs/<job>.mp4

# 3. Render the punch-ins:
presets/punch-in-zoom/apply-zoom.py \
  projects/<job>/outputs/<job>.mp4 \
  projects/<job>/zoom-plan.json \
  projects/<job>/zoom-crop.json \
  projects/<job>/outputs/<job>.zoomed.mp4

# 4. Verify — must PASS before treating any punch-in as correct:
uv run workflows/zoom-crop.py --verify projects/<job>/outputs/<job>.zoomed.mp4
```

Run this **before** the sweep intro/outro (step 7, Export) — the intro punch-in window overlaps
exactly where the sweep intro also lands, and `presets/sweep-intro/build.py` already has a
`--target-crop` flag built specifically to zoom in *toward* this same crop box (pass
`zoom-crop.json`'s `crop` object as `x,y,w,h` to `--target-crop`, and the pre-zoom cut as
`--frame-source`) — so the sweep and the punch-in land on the identical framing with no visible seam
between them, instead of the sweep settling on one crop and the punch-in jumping to a slightly
different one.

## Category-specific behavior — see `zoom-plan` for the actual timing logic

This preset is the same crop/magnitude/transition mechanics regardless of content type — what
differs is **when** it fires, which `zoom-plan` decides from `content-classification.json`'s
`zoom_trigger_style`:

- **`pause-then-resume`** (reaction) — zoomed during intro + direct-address moments, zoomed out
  during passive external-content playback.
- **`exclamation-highlight`** (combat-gameplay) — brief opening punch-in, then a ~2-2.4s window per
  genuine reaction/highlight beat, zoomed out (full gameplay) the rest of the time.
- **`none`** (weapon-breakdown / guide) — this preset doesn't apply at all; those formats get full
  `graphics-plan` treatment instead.

## Measurement caveats — read before "improving" this further

- **The headphone/overlay padding in `zoom-crop.py` is a generalized heuristic, not per-video ground
  truth.** It was tuned to comfortably cover a face + headphones + a nearby small HUD overlay based
  on how those elements looked across the three validating jobs — a genuinely different OBS layout
  (e.g. a much bigger facecam, or an overlay positioned further from the face than the follower
  widget was) could still need the padding constants adjusted. Always eyeball the `--annotate` output
  once on a new creator/layout before trusting it blind.
- **This preset assumes a fixed facecam position for the whole video.** True on every job measured so
  far (the creator doesn't move their webcam mid-recording), so `zoom-crop.py` measures once from
  samples across the whole cut rather than per-segment. If a future job ever repositions the camera
  mid-video, this assumption breaks and the crop needs measuring per-segment instead.
