# the reference channel Shorts — the study (2026-09-09)

Reference set: the 15 highest-viewed of his newest 40 Shorts plus 3 of the weakest (one failed to
fetch → 17 analysed). Method, all offline: `yt-dlp` into a folder outside the repo (deleted after)
→ pass 1 mechanical (ffprobe, `select=gt(scene,0.3)` cut count, `ebur128`, contact sheets at 1 fps
+ the first/last 2 s at 6 fps) → pass 2 visual (every sheet read frame by frame) → pass 3 WhisperX
large-v3 transcript + RMS envelope (pace, first line, pauses, loud non-speech bursts, cut alignment).
The clipper's defaults were recalibrated from this — see **What changed** at the end.

## Per Short

| Views | Title | s | cuts/10s | Hook | Layout | Cut-ins | Ending |
|---:|---|---:|---:|---|---|---|---|
| 464k | D3 Announced | 18.9 | 5.3 | bold denial, mid-sentence | full-frame facecam over the X page | 4 silent reaction clips (hoodie hacker, surveillance eye, monkey puppet, Vader) 1–2 s each | extreme punch-in on his laugh |
| 410k | Cross knows something… | 35.6 | 2.8 | "No, I don't think we're going to play Marathon" | full-frame facecam | Tyrese ×3, Bale ×1, 2–4 s, with their lines | **ends on the Tyrese-in-car clip, 4 s, fade to black** |
| 335k | The Best Drip | 26.1 | 3.4 | **pinned chat** read aloud ("I sent you my drip") | facecam over the game stat page | full-frame screenshot of the character (3 s), a "Download" UI beat, one extreme close-up | face |
| 325k | You can't fool us Cross… | 37.5 | 2.7 | "I don't know, man" | full-frame facecam | Tyrese ×2 (3 s), a pinned chat over the game UI mid-clip | extreme close-up 4 s, then Tyrese 1 s |
| 276k | Missing old DLCs | 19.1 | 2.1 | "this may blow your mind" | **stacked** (face top / gameplay below) — the only one | full-frame location cards (6 s) | face over gameplay |
| 226k | Cross new haircut | 17.0 | 2.4 | "I'll put it to you like this" | full-frame facecam | **bespoke photoshop** of him with a bowl cut, 6 s | face looking down |
| 209k | GET BACK HERE | 18.8 | 5.9 | **pinned chat** ("My bad I lost the checkpoint") | full-frame facecam | game UI "PLAYER LEFT" full-frame 2 s; 4 punch-ins on the rant | game UI "PLAYER JOINED YOU" = the punchline |
| 206k | Cross Mcdonald's | 21.8 | 4.6 | **pinned chat** ("put the fries in the bag") | full-frame facecam | **bespoke AI video** of him at McDonald's, 8 s | face |
| 155k | Can't Hear Cross | 19.1 | 5.8 | "Hello? Can you hear me?" | full-frame facecam | the audio-settings UI (the evidence) ×2 | face fiddling with the headset |
| 154k | Both Games Dead | 17.0 | 2.3 | **pinned chat** ("Bullshit!! You hate us") | full-frame facecam | extreme punch-in 5 s | **ends on a gravestone image, 6 s** |
| 121k | Sony Doesn't Like Destiny | 36.2 | 2.5 | "dude if Sony was to come out right now" | full-frame facecam | PlayStation slide 4 s, a designed SteamCharts stat card 4 s, punch-ins | face |
| 121k | Don't think about it Sony | 23.6 | 1.7 | "can I just say this" | facecam over game settings | "Project Sunrise" title card 5 s, his settings UI | a small stream-layout screenshot |
| 102k | Cross Politics | 31.4 | 1.3 | his own tweet, revealed line by line for 25 s | tweet card → stream | none (the tweet IS the piece) | bait-and-switch: "THE REAL AZTECROSS" is someone else |
| 99k | Evil Cross | 19.3 | 3.6 | **pinned chat** ("kill the disciples cross") | **full-frame gameplay ↔ full-frame face, intercut** | 3 gameplay beats, 2 shocked extreme close-ups | face, calm |
| 95k | Stop Teasing Cross | 32.0 | 1.9 | **pinned chat** ("Is Marathon S3 gonna be something you play?") | full-frame facecam | Tyrese ×3 back to back (9 s) | face talking, 13 s uncut |
| 26k LOW | Cross Throwing | 20.0 | 4.0 | gameplay with a burned subtitle ("here we go") | gameplay ↔ face intercut | game timer UI | face laughing |
| 10k LOW | Cross Charity | 20.0 | 3.0 | face → **pinned chat** ("of course cross is gonna defend this crap") | full-frame facecam | GoFundMe screenshot 2 s | extreme close-up of his mouth |

## The aggregate

- **Length** median 20 s (17–37.5). The two 36–37 s ones are multi-beat with several reaction clips.
- **Base frame: full-frame facecam in 16/17**, composited big over the stream page. His facecam is
  a separate full-resolution source. Stacked appears once (gameplay as the subject). Gameplay is
  more often **intercut full-frame** (cut to the game 2–4 s, cut back to the face).
- **Hook: a pinned chat message in 8/17**, boxed at the top (≈y 420–510 in a 1080×1920 frame,
  dark box, orange name, white text) for 2–3 s — and the transcript shows him **reading it aloud**
  as the first line in 6 of those. The other hooks: a bold denial / promise ("No no no no…", "I'll
  put it to you like this…", "This may blow your mind"). Always a cold open — no card, no title.
- **Reaction clips, full-frame, 1–4 s, 0–5 per Short (median 2).** Movie moments used as
  reaction shots right after his line: Tyrese (*Fast & Furious*) is a recurring character — 6
  appearances across the set — plus Bale, the monkey puppet, the hoodie hacker, Vader. Most are
  **silent under his continuing voice** (pass 3 found bursts only where a clip has its own line).
  The signature: **the Short ends on the clip**, held 2–4 s, **fade to black** (Cross knows
  something, Both Games Dead, You can't fool us).
- **Evidence cut-ins full-frame 2–5 s**: screenshots, game UI ("PLAYER LEFT" as the punchline), a
  designed stat card, location cards, the drip, the GoFundMe page.
- **Bespoke gags in 4/17**: photoshop bowl cut, AI McDonald's video, gravestone, tweet reveal.
  Human-made, and among the best performers.
- **Punch-ins go extreme** — face fills the frame, sometimes only the mouth — 2–4 per Short, on
  the reaction; hard cut in, hard cut out.
- **Zero text pops in 17. Zero burned captions in 16** (one 2 s subtitle on a low performer).
- **No added music, no whooshes/flashes/shakes detectable, no CTA, no outro.** Stream alerts
  (Subscriber / Donation / Cheer) ride along untouched.
- **Cuts** median 2.8 per 10 s; rants 5–6. First cut 1.6–5.5 s (except the 25 s tweet read).
  Rants cut *on words* (mid-sentence punch-ins); calmer ones cut *in pauses* (the reaction clip
  after the line).
- **Sound** −18.7 LUFS throughout (LRA 4–9 for voice, 23 when gameplay audio is in). Pace 2.6
  words/s median (1.5–3.9). Pauses ≥0.6 s: 0–7 per Short — his editor *leaves* the reaction beat
  and fills it with a clip.
- **Low performers are structurally identical** — the topic sank them. The single worst (10k) is
  also the only one with **no pauses and no cut-ins**: wall-to-wall talking.

## What changed in the clipper because of this

| | the reference channel | Before | Now (`--style reference`, default) |
|---|---|---|---|
| Text pops | none | on every gag | **off** (`--style tiktok` or `--text-pops on` brings them back) |
| Reaction clips | full-frame, 1.5–3 s, several | inset box, 1 s | **full-frame on a blurred cover-crop, 2 s (up to 3 with their own line), screen-time cap 35 %** |
| Ending | on a clip + fade to black | impact hit on the last word | **`tail`: the Short ends on a fitting clip (1.5–3 s) with a 0.4 s fade; the hit is dropped** |
| Hook | pinned chat 8/17 | cold open | **`--pin "name: message"`** — his chat-pin look for the first 3 s |
| Bespoke gag | 4/17 | — | **`--insert t:file[:dur]`** — a creator-placed full-frame image/GIF/MP4 cut-in |
| Flash / shake | none | on booms | **off** in this style |
| SFX | none detectable | boom / hit / bruh / … | kept — the creator wants them; levels unchanged |
| Length | 17–37 s | target 20, ≤60 | unchanged |

**Still open, in order of impact:**
1. **The facecam.** 16/17 are a crisp full-frame camera. Ours is a small window inside a
   2560×1440 screen capture, upscaled ~3×. Nothing in software closes that gap: **record the webcam
   as its own full-res file** (OBS second output / source record), and the clipper gets a
   `--face-source` to use it.
2. **`--layout intercut`**: full-frame face ↔ full-frame content (the motion-ROI window when the
   embedded video plays), instead of stacked. His default for gameplay/evidence.
3. **Extreme punch-in** (face fills the frame) once per Short on the strongest beat — worth it only
   after (1), it would be mush from the screen-capture facecam.
4. A **recurring character**: pick 2–3 reaction clips that become *his* (the Tyrese role) and
   weight them. `assets/memes/` naming already supports it — the planner rotates within a tag.
5. **Pinned-chat automation**: today `--pin` is typed by hand; the chat overlay is in the screen
   capture, so a crop-and-OCR of the chat box at the moment is the eventual route.
