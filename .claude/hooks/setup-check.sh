#!/usr/bin/env bash
# .claude/hooks/setup-check.sh — runs when a Claude Code session starts in this folder.
# If brand-kit.md still has <<placeholders>>, the editor isn't anyone's yet: say so, loudly, before any job.
# Prints nothing once setup is done, so it never nags a finished install.
[ -f brand-kit.md ] || exit 0
n=$(grep -c '<<' brand-kit.md 2>/dev/null); n=${n:-0}
[ "${n:-0}" -gt 0 ] || exit 0
cat <<MSG
FIRST RUN — this editor is not set up yet: brand-kit.md still has $n <<placeholder>> fields.
Do NOT start an edit job. Do this first, in order (CLAUDE.md > "First run"):
  1. ./check-setup.sh — install what it lists, re-run until clean; then: npx hyperframes@0.7.3 doctor
  2. Fill brand-kit.md Part A with the owner (their handle, voice, colors, fonts, intro/outro, thumbnail look).
  3. "apply my brand kit" — Part B — then render the 10-second brand check and look at it together.
Setup is done when brand-kit.md has no <<...>> left.
MSG
