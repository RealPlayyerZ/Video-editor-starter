#!/usr/bin/env bash
# finalize.sh <job> — the EXPORT step. Make a finished job's outputs/ unambiguous.
#
# When a job is DONE, this promotes the real final render to ONE clear deliverable
# and retires the dead drafts — so there's never confusion about which file ships.
# It also drops a copy in ~/Downloads (the "export") so the finished file is ready to grab/upload.
# It does NOT nuke the job: everything you'd need to come back and re-edit is kept.
#
# The convention it enforces in projects/<job>/outputs/:
#   <job>.final.mp4         <- THE deliverable. Ship this. (promoted from the latest render)
#   <job>.mp4              <- clean base cut (re-edit / re-caption input) — KEPT
#   <job>.transcript.json  <- KEPT
# And it leaves the hf-graphics/ SOURCE (build.py, compositions/, parts.json, PROJECT.md)
# fully intact, so the whole graphics build can be reopened and tweaked later.
#
# It does NOT reclaim the heavy regenerable cache (renders/, work-* scratch). For that,
# run ./prune.sh --apply afterward. Together = a clean, shipped job.
#
# Default is a DRY RUN — it only reports the plan. Add --apply to actually do it.
#   ./finalize.sh <job>            # show the plan
#   ./finalize.sh <job> --apply    # promote the final + delete drafts

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOB="${1:-}"
APPLY=0
[[ "${2:-}" == "--apply" || "${1:-}" == "--apply" ]] && APPLY=1
[[ "$JOB" == "--apply" ]] && JOB=""

[[ -n "$JOB" ]] || { echo "usage: ./finalize.sh <job> [--apply]"; exit 1; }

OUT="$REPO/projects/$JOB/outputs"
[[ -d "$OUT" ]] || { echo "No outputs/ for job '$JOB' at $OUT"; exit 1; }

BASE="$JOB.mp4"
DELIVERABLE="$JOB.final.mp4"
size() { du -h "$1" 2>/dev/null | cut -f1; }

echo "=== finalize: $JOB ==="

DELIV_PATH="$OUT/$DELIVERABLE"
is_final_named() { [[ "$(basename "$1")" == *final* ]]; }   # basename contains "final"
is_draft_named() { [[ "$(basename "$1")" == *draft* ]]; }   # basename contains "draft"
# echo the newest path (by mtime) among the args, "" if none. Portable `-nt` test (bash builtin).
newest_of() { local best="" g; for g in "$@"; do if [[ -z "$best" || "$g" -nt "$best" ]]; then best="$g"; fi; done; printf '%s' "$best"; }

# All render candidates = *.mp4 in outputs/ except the clean base cut and the canonical
# deliverable itself (<job>.final.mp4 is the "incumbent", reconciled below).
# (while-read, not `mapfile` — mapfile is bash 4+, absent in macOS's default /bin/bash 3.2.)
cands=()
while IFS= read -r f; do cands+=("$f"); done < <(find "$OUT" -maxdepth 1 -type f -name '*.mp4' \
  ! -name "$BASE" ! -name "$DELIVERABLE" | sort)

# Candidates eligible to BECOME the deliverable = everything that isn't an explicit *draft*.
# A *graphics* render is NOT special: it's a mid-pipeline (pre-caption) stage that a newer
# captioned/music/-vN render supersedes. The old logic ranked *graphics* above newest-mtime,
# which is exactly what promoted a graphics-only draft over the real captioned+music final
# (and then deleted the music cut). (${arr[@]+"${arr[@]}"} = empty-array-safe expansion.)
pickable=()
for f in ${cands[@]+"${cands[@]}"}; do is_draft_named "$f" || pickable+=("$f"); done

# Pick the best candidate, in order:
#   1. an explicit *final*-named render (newest such), e.g. <job>-final.mp4
#   2. else the NEWEST render in the job-name family (basename starts with <job>) — so a
#      newer -music / -captioned / -vN beats an older -graphics draft, and a stray
#      non-family fragment (e.g. hook-v5.mp4) can never be promoted
#   3. else the newest render overall
pick=""
if [[ ${#pickable[@]} -gt 0 ]]; then
  finalnamed=()
  for f in "${pickable[@]}"; do is_final_named "$f" && finalnamed+=("$f"); done
  if [[ ${#finalnamed[@]} -gt 0 ]]; then
    pick="$(newest_of "${finalnamed[@]}")"
  else
    family=()
    for f in "${pickable[@]}"; do [[ "$(basename "$f")" == "$JOB"* ]] && family+=("$f"); done
    if [[ ${#family[@]} -gt 0 ]]; then pick="$(newest_of "${family[@]}")"
    else pick="$(newest_of "${pickable[@]}")"; fi
  fi
fi

# Reconcile with the incumbent <job>.final.mp4. THE GUARD: never overwrite an existing final
# with an OLDER pick. Only promote when there's no final yet, or the pick is strictly NEWER
# than the current final. (This is what stops a graphics draft clobbering a real deliverable.)
promote=""
if [[ -f "$DELIV_PATH" ]]; then
  if [[ -n "$pick" && "$pick" -nt "$DELIV_PATH" ]]; then
    promote="$pick"
    echo "  PROMOTE $(basename "$pick")  ->  $DELIVERABLE   (newer than current final, $(size "$pick"))"
  else
    echo "  KEEP    $DELIVERABLE   (already the deliverable, $(size "$DELIV_PATH"))"
  fi
elif [[ -n "$pick" ]]; then
  promote="$pick"
  echo "  PROMOTE $(basename "$pick")  ->  $DELIVERABLE   ($(size "$pick"))"
fi

# VERIFY GATE (2026-09-08): check the file that is about to ship — the promoted pick, or the
# incumbent final — with workflows/verify-final.py (streams, durations agree, frame-difference
# sweep at the body→outro seam and across the file, audio peak). Two videos shipped with a ~2s
# frozen frame before this existed, and the build logs looked clean both times. A FAIL blocks
# --apply (dry run just reports). VE_SKIP_VERIFY=1 overrides; VE_NO_OUTRO=1 for a job that
# genuinely has no outro (so its static ending isn't misread as a freeze).
ship="${promote:-}"; [[ -z "$ship" && -f "$DELIV_PATH" ]] && ship="$DELIV_PATH"
if [[ -n "$ship" && "${VE_SKIP_VERIFY:-0}" != "1" ]]; then
  vflags=(); [[ "${VE_NO_OUTRO:-0}" == "1" ]] && vflags+=(--no-outro)
  # VE_STATIC_TAIL=<sec>: a Shorts ending that deliberately holds on a reaction clip (see gags.py "tail")
  [[ -n "${VE_STATIC_TAIL:-}" ]] && vflags+=(--static-tail "$VE_STATIC_TAIL")
  echo "  VERIFY  $(basename "$ship")"
  if ! python3 "$REPO/workflows/verify-final.py" "$ship" ${vflags[@]+"${vflags[@]}"} 2>/dev/null | sed 's/^/          /'; then
    echo "  ✗ verify-final FAILED on $(basename "$ship") — NOT shipping it. Fix the render (see the FAIL line above), or VE_SKIP_VERIFY=1 to override."
    [[ $APPLY -eq 1 ]] && exit 2
  fi
fi
[[ -n "$promote" && $APPLY -eq 1 ]] && mv -f "$promote" "$DELIV_PATH"

# Reference file whose mtime defines "the deliverable" (for the never-delete-newer guard).
# After an --apply promote the pick was moved onto DELIV_PATH (newest); in a dry run, or when
# no final exists, fall back to the pick itself.
ref=""
if [[ -e "$DELIV_PATH" ]]; then ref="$DELIV_PATH"
elif [[ -n "$promote" && -e "$promote" ]]; then ref="$promote"; fi

# Retire the rest. Guards, in order:
#   - skip the promoted pick (it's been moved onto the deliverable)
#   - never delete another *final*-named render (anomalous — let a human decide)
#   - never delete a render NEWER than the deliverable we're shipping (it may be the real final)
#   - everything else (older drafts / superseded renders) is deleted
for f in ${cands[@]+"${cands[@]}"}; do
  [[ -n "$promote" && "$f" == "$promote" ]] && continue
  [[ -e "$f" ]] || continue
  b=$(basename "$f")
  if is_final_named "$f"; then
    echo "  KEEP    $b   (also looks final — NOT deleting; remove by hand if dead)"
    continue
  fi
  if [[ -n "$ref" && "$f" -nt "$ref" ]]; then
    echo "  KEEP    $b   (newer than the deliverable — NOT deleting; promote it by hand if it's the real final)"
    continue
  fi
  if is_draft_named "$f"; then
    echo "  DELETE  $b   (draft, $(size "$f"))"
  else
    echo "  DELETE  $b   (superseded render, $(size "$f"))"
  fi
  [[ $APPLY -eq 1 ]] && rm -f "$f"
done

# Report what's kept for re-editing.
[[ -f "$OUT/$BASE" ]]                 && echo "  KEEP    $BASE   (clean base cut for re-edit, $(size "$OUT/$BASE"))"
[[ -f "$OUT/$JOB.transcript.json" ]]  && echo "  KEEP    $JOB.transcript.json"
[[ -d "$REPO/projects/$JOB/hf-graphics" ]] && echo "  KEEP    hf-graphics/ source (build.py + compositions — reopen to re-edit)"

if [[ -z "$pick" && ! -f "$OUT/$DELIVERABLE" ]]; then
  echo
  echo "  ⚠ No render found to promote. If $BASE itself is the deliverable (e.g. a no-graphics raw cut),"
  echo "    copy it: cp \"$OUT/$BASE\" \"$OUT/$DELIVERABLE\""
fi

# Export copy → Downloads, so the finished file is ready to grab/upload ("exporting").
# Override with VE_EXPORT_DIR. On WSL2 ~/Downloads is the Linux home (invisible in Windows
# Explorer), so default to the Windows user's Downloads when we can resolve it.
DL="${VE_EXPORT_DIR:-$HOME/Downloads}"
if [[ -z "${VE_EXPORT_DIR:-}" ]] && grep -qi microsoft /proc/version 2>/dev/null; then
  WINHOME="$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')" 2>/dev/null || true)"
  [[ -n "$WINHOME" && -d "$WINHOME/Downloads" ]] && DL="$WINHOME/Downloads"
fi
EXPORTED=0
if [[ -f "$DELIV_PATH" || -n "$promote" ]]; then
  if [[ $APPLY -eq 1 ]]; then
    if [[ -d "$DL" ]]; then
      cp -f "$DELIV_PATH" "$DL/$DELIVERABLE" && EXPORTED=1 \
        && echo "  EXPORT  $DELIVERABLE  ->  $DL/$DELIVERABLE   ($(size "$DELIV_PATH"))"
    else
      echo "  ⚠ $DL not found — skipped Downloads export copy"
    fi
  else
    echo "  EXPORT  $DELIVERABLE  ->  $DL/$DELIVERABLE   (Downloads copy)"
  fi
fi

echo
if [[ $APPLY -eq 1 ]]; then
  echo "Done. Deliverable: projects/$JOB/outputs/$DELIVERABLE"
  [[ $EXPORTED -eq 1 ]] && echo "      Exported copy: $DL/$DELIVERABLE"
  echo "Now reclaim the regenerable cache:  ./prune.sh --apply"
else
  echo "DRY RUN — nothing changed. Re-run with --apply to do it."
fi
