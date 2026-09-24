# An AI video editor you actually own

This is the folder I started from. Point Claude Code at it, fill in one file with who you are, and you have an
editor that cuts your footage, syncs it, builds the graphics, checks the file, and hands you something to
post — in your style, not mine.

**Nothing here is for sale.** No course, no upsell, no folder behind a paywall. The method is in the video,
the starter is this folder, and the questions get answered on the monthly call.

## What "free" honestly means

- **Free:** this folder, the method, and every tool it runs on — ffmpeg, WhisperX, Python, Node, WSL.
- **Not free:** Claude itself. Claude Code needs a paid plan. I use the higher tier and a heavy week can hit its
  limit; a lower tier works with fewer hours. Plan on that cost before you plan on this workflow.
- **Also not free:** your time. The first week is you teaching it your taste through feedback. That's the part
  nobody can download.

## Where this came from

I started with a paid starter kit by another creator — credit to Jason Cooperson (https://www.youtube.com/@jasoncooperson), it's what got me going.
That kit's files aren't mine to give away, so **none of them are in here**. The base in this folder was rebuilt
from scratch, and everything on top of it is what I built over months of real videos. The videos on my channel —
https://www.youtube.com/@RealPlayyerZ — are the production record: each one was edited this way.

## Start here

1. Read `SETUP.md` — install the tools (Windows users: WSL2 first).
2. Open the folder in Claude Code. It will tell you it isn't set up yet — that's the point.
3. Fill in `brand-kit.md` with your handle, colors, fonts, intro/outro, and how you talk. Say "apply my brand kit".
4. Drop a clip into `projects/<name>/raw/` and say "edit this".

`CLAUDE.md` is the note your editor reads every session. It's written in my voice as a starting point — rewrite
any line that isn't how you'd say it. That file is the real product; the scripts just do what it says.

## What's in the box

| | |
|---|---|
| `CLAUDE.md` | how your editor behaves — the seven-step job, the rules, where things live |
| `brand-kit.md` | the one file that makes it yours |
| `presets/` | the reusable pieces: frame-exact cut, punch-in zoom, ducked music, captions, the verify gate, article cards, Shorts clipper, the comedy layer for gameplay |
| `workflows/` | recipes for whole kinds of video — reaction, article breakdown, gameplay edit, Shorts from long-form, stream replays |
| `.claude/skills/` | the skills Claude runs, plus the open-source HyperFrames toolkit that renders graphics |
| `finalize.sh` / `prune.sh` | ship the one final file; reclaim space after |

The intro, outro, and on-screen "subscribe" layout in `presets/` are **examples of my look** — the mechanism is
yours to keep, the look is yours to replace. Their headers say so.

## What this is not

Not a magic button. It's a tool, and taste is still the human's job — mine, and now yours. It will make a bad
cut the first time you don't tell it what you wanted. Tell it. That's the workflow.

## License

MIT — see `LICENSE`. HyperFrames (Apache-2.0), the YuNet face model (Apache-2.0), and the Inter font (OFL)
keep their own licenses, included alongside them.
