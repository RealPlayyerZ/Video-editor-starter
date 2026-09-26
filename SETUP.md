# SETUP.md — from zero to "edit this"

Everything here is Linux tooling. On a Mac or a Linux machine you can start at step 2. **On Windows, do step 1
first** — the editor runs inside WSL2, which is a real Ubuntu that Windows installs for you.

## 0. The honest cost line

- **Paid:** Claude Code needs a Claude subscription. The higher tier gives the most hours; a heavy editing week
  can hit its weekly limit. A lower tier works — you just get fewer hours. Decide this before anything else.
- **Free:** every other tool below.
- **Hardware:** any machine with 16 GB of RAM works. An NVIDIA GPU makes transcription fast (seconds); without
  one it runs on the CPU and takes minutes per ten minutes of footage. That's fine — it runs once per video.

## 1. Windows only — install WSL2

Open PowerShell **as Administrator** and run:

```
wsl --install
```

Reboot if it asks. You now have an "Ubuntu" app in the Start menu — that's your Linux terminal. Open it, make
a username and password when it asks, and **do every remaining step inside that window**.

Put the editor folder inside Ubuntu, not on the Windows side (Windows paths are slow from Linux and break the
script permissions):

```bash
cd ~
unzip /mnt/c/Users/<you>/Downloads/video-editor-starter.zip
cd video-editor
```

## 2. The tools

```bash
./check-setup.sh
```

It prints exactly what's missing and the install line for your OS. Run that line, then run `./check-setup.sh`
again. Repeat until every core item is ✓. For the record, the tools are:

| Tool | Why |
|---|---|
| ffmpeg / ffprobe | every cut, mix, and render |
| python3 + Pillow | the caption and layout builders draw with it |
| uv | builds the transcriber's private Python environment on first run |
| node 22+ / npx | the graphics renderer |
| WhisperX | installs itself the first time you transcribe (a few minutes, once) |

Then, once:

```bash
npx hyperframes@0.7.3 doctor
npx hyperframes@0.7.3 browser ensure   # downloads the headless browser the renderer uses (~150 MB, once)
```

That downloads the headless browser the graphics renderer uses.

## 3. Claude Code

Install it from Anthropic's instructions for your platform, sign in with your subscription, then from inside
the editor folder:

```bash
cd ~/video-editor
claude
```

It will read `CLAUDE.md`, see that `brand-kit.md` isn't filled in, and tell you so. That's correct.

## 4. Make it yours

Open `brand-kit.md`. Fill in Part A — your handle, how you talk, three colors, your fonts, your intro and outro
if you have them, one paragraph on your thumbnail look, and any names the transcriber keeps getting wrong.
Then tell Claude:

> apply my brand kit

It writes the settings the tools read and renders a ten-second brand check. Watch it. If that's not your
color and your font, fix Part A and apply again. When `brand-kit.md` has no `<<placeholders>>` left, the
editor is yours.

## 5. First job

```bash
mkdir -p projects/first-video/raw
cp /mnt/c/Users/<you>/Videos/clip.mp4 projects/first-video/raw/      # copy — never move your original
```

Then, in Claude:

> edit projects/first-video

It transcribes, cuts, shows you the cut sheet, and asks what you want next. Give feedback with timestamps —
"at 1:24 cut that pause", "zoom in on me at 3:10" — and it iterates. Review excerpts, not full renders, until
you're happy; then let it build the whole thing and run its checks.

## If something breaks

- `./check-setup.sh` again — it's usually a tool that isn't on the PATH in a new terminal.
- Transcription hangs on first run? It's downloading the model (about 3 GB). Give it time once.
- "permission denied" on a `.sh` file — you unzipped on the Windows side. Re-unzip inside Ubuntu (step 1).
- Anything else: tell Claude what you saw, with the exact error text. Diagnosing this is part of its job.
