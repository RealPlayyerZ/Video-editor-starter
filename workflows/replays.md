# Replays — Stream Deck → shortlist → Shorts (the creator's Shorts pipeline, 2026-09-11)

The creator streams. When something happens he presses **one Stream Deck key** and OBS saves the
**last 180 s** into the recording folder as `Replay YYYY-MM-DD hh-mm-ss.mp4`. After the stream he
says "scan last night" and gets a ranked shortlist of moments to pick from; each pick becomes a
finished Short through [`shorts-clipper.md`](shorts-clipper.md). Twitch clips are no longer the
source — they were the compressed composite; replays are full quality and, once Source Record is
on, come with a full-res camera file ([`obs-webcam-recording.md`](obs-webcam-recording.md)).

## OBS side (once)

- Settings ▸ Output ▸ Recording: path `<your recording folder>`, format **Hybrid MP4**,
  encoder **NVIDIA NVENC** (never x264 — the one setting that can lag a stream), CQP 18. OBS has ONE
  recording path: the Record button (his long-form videos) and the replays share it; OBS prefixes
  replays with `Replay` (Settings ▸ Advanced ▸ Recording ▸ Replay Buffer Filename Prefix), which is
  how the scanner tells them apart. Nothing else needs moving or renaming.
- Settings ▸ Output ▸ Replay Buffer: on, **180 s** (≈1 GB of RAM at 1440p60; the PC has 31 GB).
- Settings ▸ General: **start the replay buffer automatically when streaming**.
- Stream Deck: the Elgato **OBS Studio** plugin's *Replay Buffer → Save Replay* action on a key
  (fallback: OBS hotkey *Save Replay* = F9, a Stream Deck *Hotkey* action sending F9).
- Test: a 10-minute stream, press the key, a file appears; OBS Stats dock "Rendering/Encoding
  lagged frames" stays near zero. (The PC already runs two encodes — Twitch + YouTube multistream —
  on the RTX 5090's NVENC engines; a recording is a third of the same kind.)
- The Record button is unchanged: it still records the long-form video he wants edited. If a whole
  session is ever wanted for Shorts, OBS 32's *Add Chapter Marker* hotkey fences the long-form part.

## Editor side

```bash
presets/shorts/scan-replays.py scan "<your recording folder>"     # newest night's new replays
presets/shorts/scan-replays.py scan <folder> --date 2026-09-12 | all
presets/shorts/scan-replays.py status
```

`scan` reads only `Replay*` files, groups them by date, and for each NEW file (a ledger remembers
path + size + mtime): makes a light job `projects/replay-YYYYMMDD-hhmmss/` whose `raw/` and
`outputs/<job>.mp4` are **symlinks** to the source (nothing copied), transcribes every new replay of
the night in **one WhisperX pass** (one model load; ~40 s for two on the 5090), derives the canonical
transcript, measures the face (`zoom-crop.py`), then scores windows (15–45 s, target 25) inside the
replay: reaction beats from the comedy layer (laugh ×1.5, shouts, trigger words, the pause after a
line) + motion bursts in the game + a recency bonus toward the press (the moment is usually in the
last minute) − long silent stretches − windows with no speech and no event, on pause/sentence
boundaries; top two non-overlapping windows per replay. Output: `projects/replays/<date>/shortlist.md`
(rank · replay · window · why · the line · the exact build command) and a 1-fps timestamped strip
per candidate in `review/`. The build command is the creator's preferred toolkit:
`--layout intercut --style punchy --no-memes --loudness -14 --sfx-trim -6 --name <title>`
(`--name` names the clip job after its content instead of `<job>-short-NN`).

## The camera twin (2026-09-12)

With the Source Record filter on the camera (see [`obs-webcam-recording.md`](obs-webcam-recording.md)),
every press also saves `Cam <ts>.mp4`. `scan` pairs it automatically (`camsync.py`: save-time +
duration → audio cross-correlation, 10 ms), measures the face in it, writes `projects/<job>/cam.json`,
and the build command's default `--face-source auto` uses it for every face segment — the sharp
face. A replay without a twin (a press on a scene whose camera has no filter, or before the plugin
existed) simply builds from the composite as before. `status` shows `+cam`; `done`/`sweep` delete
both files together.

## Storage policy (the creator's, 2026-09-11)

A source file stays until the video made from it is **posted**, then it is deleted to free the
drive — unless it is marked as a reference worth keeping. Deletion is never automatic:

```bash
presets/shorts/scan-replays.py done <replay-job | Short job | long-form job> [--apply]   # posted → source goes
presets/shorts/scan-replays.py keep <replay-job> --why "the Sony reaction — reuse as a callback"
presets/shorts/scan-replays.py sweep [--apply]          # everything done + not kept
presets/shorts/scan-replays.py done <long-form job> --source "D:\...\2026-09-12 20-03-11.mp4" --apply
```

`done` on a replay (or a Short built from it) deletes the replay source; on a long-form job it
deletes the raw copies in `projects/<job>/raw/` (+ the named original) and keeps the base cut,
transcript and final. `status` shows what is on disk and what is reclaimable. Dry run by default.
Kept references are noted in the editor's memory when a new video could use them.

## First real result (stand-in test, 2026-09-11)

Two Twitch clips renamed as replays: the scanner picked 0:07–0:41 of the Leap of Faith replay
("laugh, loud, says wait / oh no, 3 motion bursts, right before the press") and 0:24–1:00 of the
Exodus one ("i'm dead / oh my god / bro") — the same windows chosen by hand the day before.
