> **Example.** This documents the original author's own look. It is here to show the shape of a style file — write yours in `brand-kit.md`.

# Sweep intro — your LOCKED preset (every video, every format)

The standard opening flourish applied to the **front** of every finished cut — the mirror of the
outro at the back. Locked 2026-08-24 (`division2-lore-reaction` build, tuned across a V4/V5/V6
side-by-side against a set of the reference channel reference clips). Apply verbatim every time.

Builder: [`presets/sweep-intro/build.py`](sweep-intro/build.py)

---

## 🔒 THE EFFECT — locked

An the reference channel-style fast motion-blur/zoom-warp sweep: brand-colored horizontal streak lines +
a radial zoom-blur trail + an asymmetric brightness flash, landing in sharp focus on the video's
real opening content. **Total duration 0.4s** (24 frames @ 60fps) — fast and punchy, not a slow
reveal. A whoosh SFX is mixed in underneath, timed so its sharp attack lands at the flash's
hold-start.

Replaces the **first 0.4s** of the finished cut (does not extend total runtime) — the sweep
frames are synthetic, generated from the video's own opening frame(s), so the cut into the real
continuing footage at t=0.4s is seamless.

## 🔒 THE ZOOM/WARP CURVE — two modes, locked

- **Target-crop mode** (`--frame-source` + `--target-crop`) — use when the video's own pipeline
  already punches in on its opening seconds (this project's zoom effect — see
  `workflows/short-form.md` / `workflows/long-form.md` for how that crop plan gets built). The
  sweep starts at the **wide/native framing** (pulled from `--frame-source`, e.g. the pre-zoom
  rough cut) and monotonically zooms/warps **in** toward the already-established target crop,
  overshooting it slightly at the hold (`OVERSHOOT = 1.15`) for extra punch, then eases back to
  land **exactly** on the target crop by settle — so the handoff into the continuing (already
  zoomed) footage is invisible. `--target-crop` is `x,y,w,h` in the frame-source's native pixel
  space, same convention as the project's own IN crop.
- **Generic mode** (default, no `--target-crop`) — for videos with no punch-in baked into their
  opening. There's no "wider" framing to zoom in from, so this is a **self-relative punch**:
  starts at the input's own frame 0 (whatever that framing already is), zooms 32% in through the
  blur, eases back to that same starting framing by settle.

Both modes share the same timing envelope:

```
PEAK_T    = 0.30   # ease-in cubic from start -> peak zoom/warp
HOLD_END  = 0.34   # hold at peak (target-crop mode: OVERSHOOT = 1.15x the target)
DURATION  = 0.40   # ease-out cubic back down to the settle framing
```

**Never scale below 1.0 relative to the frame being shown** — the composited frame must stay
fully filled edge-to-edge with no black borders at every point in the sweep, including frame 0.

## 🔒 THE STREAKS — locked (v6)

Brand-colored horizontal motion-blur bars, swept left-to-right with a fading tail. Tuned through
a direct side-by-side: V4 (denser/thicker) read too heavy, V5 (thinner/sparser) read too light —
**v6 is the midpoint, and is the final locked recipe.**

| Parameter | Locked value | Note |
|---|---|---|
| Streak count | 30 | down from V4's 46, same as V5 |
| Thickness | `triangular(14, 98, 32)` px | midpoint of V4 (20–140/45) and V5 (8–55/18) |
| Length (tail) | `uniform(0.22, 0.5)` × frame width | |
| Onset timing (phase) | `uniform(-0.7, -0.1)` | first appearances cluster ~0.1–0.15s into the sweep, spreading to ~0.35s — matches the measured onset spread in the reference footage |
| Sweep speed | `uniform(0.75, 1.6)` | relative multiplier |
| Color | random pick, brand palette | `RY (255,60,172)` pink/magenta, `PE (123,47,247)` purple, `WH (255,255,255)` white |
| RNG seed | `7` | deterministic — same seed every build |
| Blur radius | 3px | kept low so lines read as bold/solid rather than softened into faintness — an earlier 6px radius was diagnosed (via a direct crop-for-crop visual comparison against the reference) as the reason a first attempt measured "thick enough" on paper but still looked thin on screen |

## 🔒 THE FLASH — locked

```
coverage(t)    = build/hold/crash envelope (same PEAK_T/HOLD_END/DURATION as the zoom curve)
flash_alpha(t) = min(1, coverage(t) * 1.15) ** 1.4
frame          = blend(frame, white, flash_alpha * 0.22)
```

The `0.22` blend multiplier is calibrated to land peak frame brightness in the **~120–150/255**
range (mean luminance), matching a set of the reference channel reference clips measured directly (peaks
ranged 97–151/255 across repeats of the same real effect — it isn't perfectly constant even in
the reference). An earlier `0.72` multiplier read as a "flashbang" (peaked ~190–200/255); a
`0.35` multiplier was correct for the original (thinner) streak recipe but had to come down to
`0.22` once the denser/thicker v6 streaks started contributing their own brightness to the frame
mean — **if the streak recipe ever changes again, recheck peak brightness and retune this
multiplier**, don't assume it's independent.

## 🔒 THE RADIAL ZOOM-BLUR TRAIL — locked

5 ghost copies of the frame at trailing (less-zoomed / less-progressed) positions along the same
zoom trajectory, `ImageChops.screen()`-blended together, then blended onto the primary (on-curve)
frame at `trail_alpha = min(1, coverage(t) * 0.6)`. `screen()` blending only ever brightens —
never use a plain weighted average across multiple differently-scaled/cropped copies, since
misaligned edges between them will crush brightness instead of cancelling out.

## 🔒 THE SFX — locked

Default asset: `assets/sfx/synth/whoosh.wav` (synthesized; or set whoosh in brand.json to your own)

Its sharp attack was measured (RMS-over-time) at **t=0.300s** — synced to land exactly at
`PEAK_T`/the hold-start of the flash and zoom curves. Mixed under the video's own existing audio
(not replacing it) via a straight `amix`, no ducking.

## Run it

```bash
# Generic (no punch-in effect on the opening):
presets/sweep-intro/build.py <input-video.mp4> <output-video.mp4>

# Target-crop (video's own pipeline already punches in on the opening — most projects
# following this pipeline's zoom-effect pattern):
presets/sweep-intro/build.py <input-video.mp4> <output-video.mp4> \
  --frame-source <pre-zoom-rough-cut.mp4> \
  --target-crop <x,y,w,h>   # native pixel space, matches the project's own established IN crop
```

`--sfx` overrides the default whoosh asset if a job wants something different — ask before
swapping it, since the sync timing (`SFX_ATTACK_T = 0.300`) is measured off the default file
specifically; a different SFX asset needs its own attack-timing measurement first.

Non-destructive — writes to whatever output path you give it, never overwrites the input. Run
this on the fully graphics/captions/music-mixed cut, at the same stage as the outro (step 7,
Export) — sweep intro on the front, outro on the back.

## 🔒 MID-VIDEO TRANSITION — a sibling effect, the intro above is untouched

Added 2026-08-26, reusing this exact streak/flash recipe (imported directly from
[`build.py`](sweep-intro/build.py), never duplicated) for **mid-video content-mode switches** —
e.g. the reference channel's article-reading ↔ reacting-mode cuts. **The intro section above did not change at
all** — this is a separate script, [`build_transition.py`](sweep-intro/build_transition.py), for a
different point in the timeline.

**Measured from real reference footage** (the reference channel, 2026-08-26, an article-reading → reacting-mode
cut): a real cut shows one sharp frame, then ~0.3-0.5s later a heavily motion-blurred frame, then a
sharp frame of the new content — the actual content swap is hidden inside the blur peak. That span
matches the intro's own locked 0.4s `DURATION` closely enough that this reuses it unchanged rather
than re-measuring a new envelope from scratch.

**Mechanism**: a "blur cut," not a synthetic zoom-from-one-still like the intro. Extract the real
last frame of the outgoing segment and the real first frame of the incoming segment, then run the
same `coverage_at`/streak/flash compositing across `N_FRAMES`: blur/streak up while holding (a
gently self-zoomed) frame of the *outgoing* content through `HOLD_END`, swap to the *incoming*
content's frame exactly at peak coverage (fully hidden by the blur+streaks+flash), then blur/streak
back down on the incoming content. Net runtime unchanged — 0.2s is consumed from each side of the
cut point to make room for the 0.4s synthetic transition, mirroring the intro's own
non-runtime-extending behavior.

**Validated so far**: the rendering mechanism itself — correct streak build-up/peak/resolve, correct
duration (tested 20.01s output against 20.00s input), correct splice/concat, audio preserved with
the whoosh mixed in at the cut. **Not yet validated**: how it reads across a *genuine* content swap
(the smoke test used an arbitrary mid-static-beat point, so before/after were the same footage) —
that needs a real job with an actual wide-view ↔ zoomed-view boundary to confirm against, the same
way every other locked preset here got hardened against real usage before being trusted blind.

```bash
presets/sweep-intro/build_transition.py <input-video.mp4> <cut-timestamp-seconds> <output-video.mp4>
```

## Measurement caveats — read before "improving" this further

This recipe was reverse-engineered from real reference footage of the the reference channel effect (three
short reference clips + one looped repeat) via frame-by-frame color-mask and brightness analysis,
**not** from source code or an original project file. Two hard limits worth remembering if this
gets revisited:

- **Individual streak trajectories are not reliably recoverable from compressed output-only
  footage.** Automated color-distance masking across a 24-frame clip only gave 3–4 frames of
  visibility per streak before it swept off-frame — not enough samples to fit a clean per-streak
  path, and one fitted "speed" came out physically negative (a tell of measurement noise, not
  signal). The locked recipe above is calibrated to the **aggregate** statistics (thickness
  range/median, color mix, onset timing spread), not literal per-streak ground truth.
- **A strict color-distance threshold undermeasures true visual thickness.** The first thickness
  pass (4–45px) only caught each streak's high-confidence core before its blurred edges fell
  outside the match tolerance — it read thin on screen despite "matching" the measurement. Final
  calibration for thickness/density used direct visual side-by-side crops against the reference
  frames instead of trusting the automated number in isolation.
