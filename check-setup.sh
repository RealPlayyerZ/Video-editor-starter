#!/usr/bin/env bash
# check-setup.sh — tells you what this machine is missing. It installs NOTHING.
#
# Run it, read the ✗ lines, run the install line it prints, run it again. Repeat until every core item is ✓.
# On Windows, this must run inside WSL2 (Ubuntu) — the whole editor is Linux tooling. See SETUP.md.
set -u
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"   # uv installs here; new shells may not have it yet

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      echo "This editor runs on macOS or Linux (on Windows: inside WSL2 Ubuntu). Open an Ubuntu terminal and run it there."; exit 1 ;;
esac

core_missing=0
BREW=(); APT=()
say() { printf "  %s %-9s %s\n" "$1" "$2" "$3"; }

# --- core tools ---------------------------------------------------------------------------------------
probe() {  # label  command  brew-pkg  apt-line
  if command -v "$2" >/dev/null 2>&1; then
    say "✓" "$1" "$(command -v "$2")"
  else
    say "✗" "$1" "missing"; core_missing=1
    [ -n "$3" ] && BREW+=("$3"); [ -n "$4" ] && APT+=("$4")
  fi
}
echo "Core:"
probe ffmpeg  ffmpeg  "ffmpeg" "ffmpeg"
probe ffprobe ffprobe ""       ""
probe python3 python3 "python" "python3 python3-pip python3-venv"
probe uv      uv      "uv"     "UV"
probe node    node    "node"   "NODE"
probe npx     npx     ""       ""
# On WSL, a Node installed on Windows leaks onto the Linux PATH (/mnt/c/...). The renderer needs the Linux one.
for t in node npx npm; do
  case "$(command -v $t 2>/dev/null)" in /mnt/*) say "!" "$t" "found only the WINDOWS copy ($(command -v $t)) — install Node inside Ubuntu (command below)"; core_missing=1; APT+=("NODE");; esac
done

# node must be 22+ for the graphics renderer
if command -v node >/dev/null 2>&1; then
  v=$(node -v | sed 's/^v//' | cut -d. -f1)
  if [ "${v:-0}" -lt 22 ]; then say "!" "node" "is v$v — need 22 or newer"; core_missing=1; [ "$OS" = mac ] && BREW+=("node") || APT+=("NODE"); fi
fi

# --- nice to have ---------------------------------------------------------------------------------------
echo "Optional:"
if command -v nvidia-smi >/dev/null 2>&1; then say "✓" "gpu" "NVIDIA GPU visible — WhisperX transcribes fast"
else say "·" "gpu" "no NVIDIA GPU — transcription still works on CPU, just slower (minutes per 10 min of footage)"; fi
if python3 -c "import PIL" 2>/dev/null; then say "✓" "pillow" "python imaging present"
else say "·" "pillow" "python imaging missing — installs with: pip install pillow  (captions and layouts need it)"; fi

# --- the install line for THIS machine -----------------------------------------------------------------
if [ "$core_missing" -eq 1 ]; then
  echo
  echo "Install what's missing, then run ./check-setup.sh again:"
  if [ "$OS" = mac ]; then
    command -v brew >/dev/null 2>&1 || echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    pk=$(printf "%s " "${BREW[@]}" | sed 's/ $//')
    [ -n "$pk" ] && echo "  brew install $pk"
  else
    plain=$(printf "%s " "${APT[@]}" | sed 's/UV//; s/NODE//; s/  */ /g; s/^ //; s/ $//')
    [ -n "$plain" ] && echo "  sudo apt update && sudo apt install -y $plain"
    printf "%s" "${APT[*]}" | grep -q NODE && echo "  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
    printf "%s" "${APT[*]}" | grep -q UV   && echo "  curl -LsSf https://astral.sh/uv/install.sh | sh    # then open a new terminal"
  fi
  echo
  echo "Then, once: npx hyperframes@0.7.3 doctor && npx hyperframes@0.7.3 browser ensure    (checks the renderer, then downloads its headless browser)"
  exit 1
fi

echo
echo "All core tools present. Next (once): npx hyperframes@0.7.3 doctor && npx hyperframes@0.7.3 browser ensure — then fill in brand-kit.md."
exit 0
