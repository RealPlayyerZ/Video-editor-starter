# Article-reaction jobs — full recipe

Formalized 2026-08-30 off `projects/marathon-reaction-article/` (the reference example — read
that job's own files alongside this doc if anything here is ambiguous). This is the recipe for
a video where the creator reads a real article on camera, reacting to it, with gameplay/trailer
b-roll behind the reading and the creator's own face returning for reaction beats.

This sits inside the normal pipeline (CLAUDE.md) as a variant of steps 3-4 (Graphics / second
pass) for long-form content that `content-classifier` flags as an article-reaction (see its
`note` field — article-reactions get this custom composite UNDER the punch-in zoom, not
instead of it; don't skip straight to zoom-only).

## Pipeline

1. **Intake + rough-cut** — normal (CLAUDE.md steps 1-2). Produces `outputs/<job>.mp4` (the
   rough cut, filler removed) and the canonical `outputs/<job>.transcript.json` (kept-words,
   already brand-corrected — this is what everything below aligns against, never re-transcribe).
2. **content-classifier** — run normally. If it's an article-reaction, it should flag that in
   its `note` field (see marathon's `content-classification.json` for the exact wording this
   produces).
3. **Gather the real article text.** Copy the article's paragraphs VERBATIM from the source
   page (not the creator's out-loud paraphrase) into a plain text file, one real paragraph per
   line. This is the single most important manual input — the on-screen card shows this text,
   not a transcript-derived guess.
4. **`presets/reading-mode/match_paragraphs.py`** — aligns the real paragraphs against
   `outputs/<job>.transcript.json` to recover each paragraph's real start/end timestamps:
   ```bash
   python3 presets/reading-mode/match_paragraphs.py \
     --transcript projects/<job>/outputs/<job>.transcript.json \
     --article projects/<job>/article-paragraphs.txt \
     --job <job> --out projects/<job>/paragraph-plan.json
   ```
   Uses one global `difflib` alignment over the whole article vs. the whole transcript (NOT a
   per-paragraph greedy search with an advancing cursor — an early version of this tool did
   that and it drifted catastrophically, losing the back third of a 46-paragraph video to a
   single early bad match). Clusters matched words by real-time proximity per paragraph and
   keeps only the largest cluster, since real articles repeat short phrases across sections
   (e.g. "Marathon Season 3" opens nearly every paragraph) and a naive min/max let one
   far-away stray match blow a paragraph's end out by 50+ seconds.
   **Validated accuracy** (against marathon's hand-verified plan): 0/46 paragraphs flagged
   low-confidence, all sequential/non-overlapping, worst single-paragraph boundary error
   ~13s, most within 2-4s. Good enough to build from, **but do a quick spot-check** of a few
   paragraph boundaries against the actual audio before committing to a full build — the
   `score` printed per paragraph (matched-word fraction) is your signal for which ones to
   check first; anything under ~0.5 or marked `low_confidence` needs a manual look, and the
   tool leaves `start`/`end` as `null` rather than guessing when it finds nothing to match at
   all. Does **not** assign `broll_clip`/`broll_in` — that's a thematic judgment call, next.
5. **Assign b-roll per paragraph.** For each paragraph, pick whichever trailer/gameplay clip
   thematically matches what's being discussed (marathon's convention: literal visual matches
   where possible — a vault/locker shot for "Vault Breaker", a boss-fight clip for a boss
   reveal, etc. — see `reading-mode-plan.json`'s `reason` fields for the actual worked
   reasoning on each pick). Same clip can span multiple consecutive paragraphs (advance
   `broll_in` to wherever the previous paragraph's usage left off). If b-roll is raw trailer
   footage (not the creator's own gameplay), clean it first — `cropdetect` for baked-in
   letterboxing (varies per clip), scan for rating-cards/name-cards mid-clip (not just at
   boundaries), `blackdetect` for dead time, then scale-to-cover + center-crop back to the
   full canvas so every clip is uniform. Keep a durable cleaned copy in
   `assets/broll/<game>/` (shared/reusable across future jobs on the same game), with a
   job-local copy in `projects/<job>/broll/`.
6. **zoom-plan** (skill) — decide the punch-in windows: every moment the creator is on-camera
   reacting (not reading) gets `pause-then-resume` trigger style. Listen for actual reaction
   beats in the audio — pauses, "oh wow", laughter, tangents — not just silence. The opening
   hook (before reading starts) and the closing direct-address (after reading ends) are always
   zoom windows. **New override (2026-08-30):** if a reaction beat is showing something the
   audience needs to actually SEE (a leaked skin, a screenshot, etc.), punching in crops that
   out of frame — keep that beat OUT of zoom-plan.json's windows entirely so it stays wide; see
   `presets/reading-mode/assemble_final.py`'s `wide`-segment list for how marathon's own skin
   reveal was handled after first shipping it zoomed by default. Same override applies to any
   moment where the creator finishes reading on-camera before their reaction actually starts —
   don't punch in until the reaction itself begins.
7. **`workflows/zoom-crop.py`** — measure the punch-in crop ONCE (`uv run workflows/zoom-crop.py
   projects/<job>/outputs/<job>.mp4`) → `zoom-crop.json`. One crop is reused for every zoom
   window in the job (apply-zoom.py applies it uniformly) — verified this is the existing,
   correct, locked behavior, not a limitation to work around.
8. **`presets/punch-in-zoom/apply-zoom.py`** — burns the punch-in into a `<job>.zoomed.mp4`
   base (`apply-zoom.py <job>.mp4 zoom-plan.json zoom-crop.json <job>.zoomed.mp4`). This is
   regenerable — delete and rebuild anytime zoom-plan.json changes, `<job>.mp4` (the rough cut)
   is the only durable input.
9. **Build each paragraph card** — `presets/reading-mode/build_paragraph.py` per paragraph
   (broll clip + in-point + duration + real card text → a standalone video-only clip in
   `projects/<job>/paragraphs/paraNN.mp4`). Anti-shake fix (2026-08-30, locked): the card
   layer's zoompan runs at 2x supersample + lanczos downscale — without it, the text box
   visibly shakes on the push-in (ffmpeg's zoompan rounds its crop rect to whole pixels every
   frame, invisible on blurred b-roll but very visible on sharp text edges). This is baked
   into the shared script now, not a per-job thing to remember. A simple driver loop (see
   marathon's `projects/marathon-reaction-article/rebuild_paragraphs.py` for the pattern) can
   batch all paragraphs from `paragraph-plan.json` in one pass, skipping any whose output is
   already newer than the build script (safe to re-run after a kill/interrupt).
10. **`presets/reading-mode/assemble_final.py`** — orchestrates the rest: builds every zoom
    window + paragraph + any explicit `wide` override as its own trimmed segment, generates a
    real sweep-style whoosh transition at every junction (reusing the locked sweep-intro
    streak/flash primitives, imported not copied), concats, and mixes audio — the ORIGINAL
    continuous voice track plus the sweep-intro whoosh at every camera-mode junction plus
    `assets/paragraph-transition-whoosh.mp3` at every paragraph-to-paragraph junction. This is
    job-specific right now (marathon's copy has marathon's exact paths/segment list hardcoded)
    — **copy it into the new job and adjust the constants at the top** (`JOB`, `ZOOMED_BASE`,
    any explicit `wide` overrides) rather than trying to genericize it blind; the segment-
    building logic itself (zoom+para+wide, sorted, gap-closed) is the part to keep verbatim.
    Watch for the real A/V-length bug fixed here: the 53-ish transitions each trim/insert
    fractional seconds and can drift the concatenated video a few hundred ms longer than the
    audio mix's nominal length — the fix (pad the audio to the video's real measured length
    before the final mux, already in marathon's copy) must carry over or a later `-shortest`
    mix step (background-music) will silently truncate the tail.
11. **Background music, sweep intro, outro, finalize, prune** — normal CLAUDE.md steps 6-7,
    unchanged. Sweep-intro runs in `--frame-source`/`--target-crop` mode using the SAME crop
    from `zoom-crop.json` (the video already punches in from t=0 the same way marathon's did,
    assuming the opening hook is also a zoom window — if not, use generic mode instead).

## Sanity checks before calling it done

- `ffprobe` both streams of the final file — video/audio duration should match to well under
  a second. If they don't, something upstream (see step 10's A/V-drift note) needs the fix.
- `volumedetect` a few spot points — mean should sit near the voice's own flat level
  (~-21dB is what rough-cut's static chain produces), peaks should stay clear of the
  limiter ceiling (-1dB) everywhere, including right at the outro splice.
- Pull actual frames at a couple of zoom-window transitions to confirm framing lands where
  intended — cheaper and more trustworthy than reasoning about crop math from timestamps alone.

## Screenshot/image overlays (tweets, article images, etc.)

If a job composites real screenshots onto the footage (not a paragraph card — a genuine tweet
or image the creator is reacting to, dropped in at a specific timestamp), **size them
generously from the first pass** — noticeably bigger than feels necessary, easily filling a
real quarter of the frame rather than a small inset. `destiny-leaks-reaction`'s first pass sized
a 3-screenshot cluster at ~0.66x native resolution and the user's first reaction on watch-back
was "these look so tiny." Fixing it after the fact is expensive: by the time a job ships,
`finalize.sh` has deleted every intermediate, so a real fix means redoing the whole chain from
`ZOOMED_BASE` forward (assemble → music → sweep-intro → outro, roughly an hour). The workable
fast-path patch — overlay bigger images directly on the shipped final, painting a black
rectangle first to fully erase the old small ones underneath — works but leaves a visible dark
backing/border in the gaps between images (acceptable on dark-mode Twitter screenshots, since it
blends with their own black background, but not a clean "images floating with nothing behind
them" look). Getting the size right on the first render avoids both problems.

## Hybrid: trailer reaction + article read (added 2026-09-13, `starcraft-dominion-reaction`)

When the creator watches a trailer on camera first and reads the article after, the same recipe
applies with three changes (worked example: `projects/starcraft-dominion-reaction/SUMMARY.md`):

1. **The creator's watch-through timestamps ARE the zoom plan** (`zoom_trigger_style: manual`,
   typed `zoom`/`wide` windows, as in `workflows/reaction-video.md`). Keep the cut to head/tail
   only unless a real silence ≥3 s exists — every long word gap is the trailer playing — so the
   timestamps map by one constant offset. End a window a beat after the sentence, never mid-word.
2. **Find where the trailer's audio plays from the recording itself:** the OBS mix is stereo
   desktop audio + a centred mono mic, so a 0.25 s mid/side RMS envelope separates them —
   side > −45 dB = trailer playing. Those spans are the `--duck` windows for
   `mix-music-ducked.py` verbatim ("fade out where the trailer plays, back in when I talk").
   `projects/starcraft-dominion-reaction/build-scripts/midside.py`.
3. **A screen-recorded trailer used as b-roll has no audio and carries YouTube UI for its first
   ~4 s** plus logo/rating/end cards — in-point after the overlay fades, drop black act breaks,
   stop before the logo; the letterbox recipe above still applies (2.4:1 inside 16:9 here).
   If the paragraph cards need less footage than the trailer has, play it chronologically A→B
   with advancing in-points instead of repeating a span.
