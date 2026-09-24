# The camera as its own file — for crisp full-frame Shorts

**Why.** Every Short so far takes the face out of the stream composite: a ~340–450 px cam window
stretched 2.4–3.5× to fill 1080×1920. A camera file at native size needs ~1.8× at worst (see the
pixel-budget note) and, with tighter camera framing, less. Long-form videos don't need this — the
cam is small in a 16:9 composite anyway — so nothing about the Record button changes.

**Decision (2026-09-12, the creator's, after both routes were researched): Source Record.** It is
one filter on the camera source, records the camera's whole 1920×1080 frame untouched (the editor
chooses the framing in the edit), and has the least for the creator to learn. Aitum Vertical's
Backtrack is the fallback (already installed; sturdier track record on OBS 32 but a second scene
system to learn and a plate cropped at record time). At 1080p both give the same pixels. Known
Source Record quirks on OBS 32 (0.4.8, forum history): can hang OBS on close while its replay
buffer is active (kill OBS; Hybrid MP4 keeps files safe), replay length sometimes short, settings
only apply after the filter is disabled/enabled once.

## The setup the creator follows (in order of value)

1. **Frame the camera tighter** (OBSBOT zoom / AI framing) — zero setup, the biggest single gain.
2. **Main replay buffer 180 s** — Settings ▸ Output ▸ Replay Buffer ▸ Maximum Replay Time 180
   (already on, already auto-starts with the stream).
3. **Stream Deck key** — Elgato OBS Studio plugin action *Replay Buffer Save* ("Save Replay");
   keyboard backup Settings ▸ Hotkeys ▸ Replay Buffer › Save Replay = F9. Streaming can start here.
4. **Install Source Record** — obsproject.com Resources ▸ "Source Record" (Exeldro, 0.4.8) ▸ Windows
   Installer zip ▸ run the installer inside ▸ restart OBS.
5. **The filter** — right-click **Tiny 2 Lite** ▸ Filters ▸ + ▸ Source Record, placed BELOW the
   chroma key (cut-out face on black). Panel: Record Mode `None` · Path `<your recording folder>` · Rec Format
   `hybrid_mp4` · Replay Buffer ✓ Duration `180`, Filename Formatting
   `Cam %CCYY-%MM-%DD %hh-%mm-%ss` · Video Encoder `Hardware (NVENC, H.264)` · Different Audio ✓
   Audio Track `Track 3` (the mic+game mix; the alignment key). Close, then toggle the filter's eye
   off/on once.
6. **Second hotkey + one key for both** — Settings ▸ Hotkeys ▸ entry "Tiny 2 Lite - Source Record"
   ▸ Save Replay = F10. Stream Deck **Multi Action**: OBS Studio › Replay Buffer Save → Delay
   150 ms → System › Hotkey F10.
7. **Test** — stream (or start the replay buffer), press once: `Replay <ts>.mp4` + `Cam <ts>.mp4`
   in your recording folder with the same timestamp; Stats dock lagged frames ≈ 0.

## Background colour: green, not black (the creator asked 2026-09-12)

The Chroma Key filter runs first, so Source Record records the cut-out on TRANSPARENT and fills the
holes with its **Background Color** — black by default. Set it to **#00FF00**: the cam file becomes
the creator on a flat, perfect green (paint, not a screen — no lighting or wrinkle problems), and
the editor keys it (`chromakey=0x00FF00:similarity=0.12:blend=0.05` or `colorkey`) with total
reliability to put the blurred, darkened game behind him in face segments — or keeps black when a
moment suits it. Black can't be keyed safely — PROVEN on the first cam file (2026-09-12): keying the black paint (`colorkey` similarity 0.06) removed the headset band, the glasses frames and the shadow under his hand along with the background (see the magenta key-mask test). `clipper.py --face-bg game` does the game-behind-him composite and auto-detects the paint colour from a corner sample; with black paint it keys tightly and shows those holes, with green it will be clean. Default `--face-bg keep`. Filters
▸ Source Record ▸ Background ▸ Background Color → `#00FF00`, Close, eye off/on. The editor-side
keying (detect the green from a corner sample, composite over the blurred game) is NOT built yet —
it gets built the day the first green cam file arrives; until then face segments are the cut-out as recorded.

## What the machine already has (read from OBS's own config, 2026-09-11)

- Recording: Advanced mode, path `D:/Videos`, Hybrid MP4, NVENC **AV1**, 2560×1440 @ 60, one audio
  track written (**Track 3** — that is where the mic + game mix lives), ~8.5 GB/h ⇒ a 180 s replay
  ≈ 430 MB. WSL's ffmpeg decodes AV1 (libdav1d + av1_cuvid), so the pipeline reads these as is.
- Main Replay Buffer: **already on**, 120 s, auto-starts when streaming. Prefix `Replay`.
- Camera: source **"Tiny 2 Lite"** (OBSBOT) reaching OBS through **NVIDIA Broadcast**'s virtual
  camera, with a **chroma-key filter** (the face is cut out over the game on stream). Scene
  collection `<your scene collection>`, scenes Game / Talk to chat / … / **Vertical Scene** (empty).
- Aitum Vertical: canvas 1080×1920, `backtrack: true`, `backtrack_seconds: 120`,
  `backtrack_path: D:/Videos`, record bitrate 18000, no hotkeys bound.
- Stream Deck with the Elgato OBS Studio plugin (scene keys already work).

## Fallback route: Aitum Vertical Backtrack (already installed; use if Source Record misbehaves)

1. **Main replay buffer to 180 s** — Settings ▸ Output ▸ Replay Buffer ▸ Maximum Replay Time 180.
   (Backtrack needs the main replay buffer enabled, and the two lengths should match.)
2. **Put the camera on the Vertical Scene** — in the Vertical dock (View ▸ Docks ▸ Aitum Vertical),
   select "Vertical Scene", add a source → *Add Existing* → **Tiny 2 Lite** (reuse it; a second
   capture of the same camera is not possible). Scale it to fill the **height** (1920 tall — the
   sides crop off, the face fills the frame; filling the width leaves empty bands above and below),
   centre it. Add nothing else — the file is a clean camera plate. Docks needed: View ▸ Docks ▸
   **Vertical**, **Vertical Scenes**, **Vertical Sources**. Camera resolution: 4K (the Tiny 2 Lite
   does 4K30 / 1080p60) makes the 9:16 slice 1215×2160 → a slight downscale = 1:1 crisp; 1080p
   gives 608×1080 → 1.78×. NVIDIA Broadcast's camera resolution setting is the gate — if it caps at
   1080p, 4K never reaches OBS. (The chroma key rides along: the cut-out
   face on black, which the editor composites over a blurred game frame.)
3. **Backtrack settings** — Vertical dock gear ▸ Vertical Settings ▸ Recording: Backtrack **on**
   ("Backtrack runs while streaming/recording"), length **180 s**, path `D:/Videos`, filename
   formatting **`Cam %CCYY-%MM-%DD %hh-%mm-%ss`** (so cam files pair with `Replay …` files by
   time), format Hybrid MP4, encoder NVENC (H.264 or AV1), bitrate ~18000, **audio track: the same
   one the main recording writes (Track 3)** — the vertical canvas uses the main audio mix, and the
   editor aligns the two files by that audio, so it must be there.
4. **Hotkeys** — Settings ▸ Hotkeys: *Replay Buffer ▸ Save Replay* = **F9**; *Vertical … Save
   Backtrack* = **F10** (the Vertical hotkeys are also bindable inside Vertical Settings).
5. **Stream Deck: one key, two saves** — a **Multi Action**: *OBS Studio ▸ Save Replay* (a.k.a.
   "Replay Buffer Save") → *Delay 150 ms* → *System ▸ Hotkey F10*. (OBS also allows one key bound
   to both actions, but Elgato documents the Multi Action and the OBS behaviour is "tolerated, may
   change"; Elgato's plugin has no native Backtrack action.)
6. **Test** — a 10-minute stream: press the key once; two files appear in your recording folder with the same
   timestamp, `Replay …` (the composite) and `Cam …` (the camera); OBS Stats dock "Rendering /
   Encoding lagged frames" stays near zero. The main replay buffer already runs an encoder during
   every stream; Backtrack adds one 1080×1920 NVENC session on top of Twitch + YouTube. The 5090 has
   three NVENC engines.

Optional, for long-form: Vertical Settings ▸ Recording ▸ "Start and stop recording when main OBS
starts and stops recording" gives a full-length camera file beside every Record-button recording
(~2 GB/h). Off for now — the creator's call.

## The pixel budget (why camera framing matters)

The camera reaches OBS through NVIDIA Broadcast, which as far as can be told hands over a 1080p
feed (check Broadcast's camera resolution; raise it if it offers more). A 9:16 crop of 1080p is
608×1080 native pixels → 1.78× upscale to 1080×1920. Still far better than today's 2.4–3.5×, and
the lever that closes the rest is **tighter camera framing** (the OBSBOT's zoom / AI framing):
the more of the 1080p frame the face fills, the closer the Short gets to 1:1.

## What the editor does with it (built and proven on the first pair, 2026-09-12)

`presets/shorts/camsync.py` pairs each `Replay <ts>` with the `Cam <ts>` saved within −3…+20 s of
it, computes the coarse offset from the two durations and save times (both files are "the last
N seconds before the press"), then refines it by cross-correlating 10 ms RMS envelopes of the
shared audio track (±6 s search). First real pair: coarse 99.88 s, audio 100.00 s, ncc 0.995 vs
0.16 runner-up — trusted. `scan-replays.py` does this for every new replay and measures the face
in the cam file (`zoom-crop.py` on `projects/<job>/cam/outputs/…` → `cam/zoom-crop.json`) →
`projects/<job>/cam.json`. `clipper.py --face-source auto` (the default) then takes every FACE
segment of the `face`/`intercut` layouts from the cam file: a 9:16 crop around the measured face
(≈3.4× face height, never tighter than 760 px, scaled to 1080×1920 — the cut-out on black), punch-ins
as tighter crops of the same frame; game segments come from the composite as before; slow motion,
gags, captions all unchanged. `--face-source none|<file>`, `--face-offset` to override. `done`/
`sweep` treat the Cam file as part of the same source.

**Camera framing is now the whole quality story.** On the first pair the face measured 451×533 px in
the 1080p cam frame (big — the camera is close) but sat at **75 % down the frame**, so the crop puts
the face low with the chin at the bottom edge. Software can't fix that (padding black below a cut
chin looks worse). The fix is at the OBSBOT: aim it so the face sits at the middle of the frame —
easiest by turning on its **AI tracking / auto-framing**, which keeps the face centred all stream —
and the crop composes itself.
