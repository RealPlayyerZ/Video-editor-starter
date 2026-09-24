#!/usr/bin/env bash
# prune.sh — reclaim space in projects without touching raw footage or finals.
#
# Deletes only regenerable / dead weight:
#   1. raw/archive/**            superseded source-clip versions you already replaced
#   2. work-*/ dirs              HyperFrames render scratch (frame dumps) left behind
#   3. node_modules/             reinstallable deps that leaked into a project
#   4. renders/*draft* + old vN  intermediate render iterations (keeps final/graphics + highest vN)
#   5. hf-graphics/renders/ + *-base.mp4   the incremental-graphics render cache + footage slices
#                                (regenerable from hf-graphics/build.py — see that folder's PROJECT.md)
#   6. SHIPPED jobs only (outputs/<job>.final.mp4 exists):  assemble_work/ and *_work/ scratch
#      (reaction + Shorts builds: body_only, chunks, reframe segments, gag work), and the
#      superseded copies that pile up in outputs/ — *.bak, *superseded*, *backup*, the promoted
#      <job>-final.mp4 render, <job>.captioned/.reframed.mp4. (2026-09-09: these were 55 GB.)
#      An UNSHIPPED job keeps every draft — that may be the creator's latest revision.
#
# ALWAYS KEPT: raw/*.mp4 (source), outputs/<job>.mp4 (base cut) + <job>.final.mp4 + transcripts,
#   audio, assets, broll, thumbnails, paragraphs/beats (article-reaction planning),
#   and the hf-graphics SOURCE (build.py, compositions/, *.sh, parts.json, PROJECT.md) — that's the progress.
#
# Default is a DRY RUN — it only reports. Add --apply to actually delete.
#   ./prune.sh            # show what would be freed
#   ./prune.sh --apply    # delete it

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/projects"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

[[ -d "$ROOT" ]] || { echo "No projects dir at $ROOT"; exit 1; }

freed_kb=0
human() { du -sk "$1" 2>/dev/null | cut -f1; }

act() { # $1 = path to remove, $2 = reason
  local path="$1" reason="$2" kb
  kb=$(human "$path"); kb=${kb:-0}
  freed_kb=$(( freed_kb + kb ))
  printf '  %-7s %s\n' "$(echo "$kb" | awk '{printf "%.0fM", $1/1024}')" "${path#"$ROOT"/}  ($reason)"
  [[ $APPLY -eq 1 ]] && rm -rf "$path"
  return 0
}

echo "=== raw/archive (old clip versions) ==="
while IFS= read -r d; do act "$d" "superseded raw"; done \
  < <(find "$ROOT" -type d -path '*/raw/archive')

echo "=== HyperFrames work-* scratch ==="
while IFS= read -r d; do act "$d" "render scratch"; done \
  < <(find "$ROOT" -type d -name 'work-*' -prune)

echo "=== stray node_modules ==="
while IFS= read -r d; do act "$d" "reinstallable"; done \
  < <(find "$ROOT" -type d -name node_modules -prune)

echo "=== hf-graphics render cache + footage slices (regenerable from build.py) ==="
# The render cache (~hundreds of MB/job) and the cut footage slices rebuild from build.py:
#   ./setup-assets.sh && ./render-all.sh   (see each job's hf-graphics/PROJECT.md)
# The tiny SOURCE next to them (build.py, compositions/, scripts, parts.json, PROJECT.md) is NEVER touched.
while IFS= read -r d; do act "$d" "regenerable render cache"; done \
  < <(find "$ROOT" -type d -path '*/hf-graphics/renders')
while IFS= read -r f; do act "$f" "regenerable footage slice"; done \
  < <(find "$ROOT" -type f -path '*/hf-graphics/assets/*-base.mp4')

echo "=== superseded renders (keep final/graphics + highest vN) ==="
while IFS= read -r rdir; do
  # Build the keep-set for this renders/ dir.
  # (while-read, not `mapfile` — mapfile is bash 4+, absent in macOS's default /bin/bash 3.2.)
  vids=()
  while IFS= read -r f; do vids+=("$f"); done < <(find "$rdir" -maxdepth 1 -type f -name '*.mp4')
  [[ ${#vids[@]} -le 1 ]] && continue          # never thin a dir with one video
  keep=()
  highest_v=""; highest_n=-1
  for f in "${vids[@]}"; do
    b=$(basename "$f")
    [[ "$b" == *final* || "$b" == *graphics* ]] && keep+=("$f")
    if [[ "$b" =~ -v([0-9]+)\.mp4$ ]]; then
      n=${BASH_REMATCH[1]}
      (( n > highest_n )) && { highest_n=$n; highest_v="$f"; }
    fi
  done
  [[ -n "$highest_v" ]] && keep+=("$highest_v")
  [[ ${#keep[@]} -eq 0 ]] && continue           # nothing recognized → leave dir alone
  for f in "${vids[@]}"; do
    skip=0; for k in "${keep[@]}"; do [[ "$f" == "$k" ]] && skip=1; done
    [[ $skip -eq 0 ]] && act "$f" "intermediate render"
  done
done < <(find "$ROOT" -type d -name renders)

echo "=== shipped jobs: build scratch + superseded copies in outputs/ (only where <job>.final.mp4 exists) ==="
for jobdir in "$ROOT"/*/; do
  jobdir=${jobdir%/}; job=$(basename "$jobdir"); final="$jobdir/outputs/$job.final.mp4"
  [[ -f "$final" ]] || continue                    # unshipped → every draft stays
  while IFS= read -r d; do
    if [[ -f "$d/.keep" ]]; then echo "  keep    ${d#"$ROOT"/}  (.keep marker)"; continue; fi   # touch <dir>/.keep to protect a job's scratch
    act "$d" "build scratch, job shipped"
  done < <(find "$jobdir" -maxdepth 1 -type d \( -name assemble_work -o -name '*_work' \))
  while IFS= read -r f; do
    b=$(basename "$f")
    if [[ "$b" == "$job.mp4" || "$b" == "$job.final.mp4" ]]; then continue; fi
    case "$b" in
      *.bak|*superseded*|*backup*|"$job.captioned.mp4"|"$job.reframed.mp4")
        act "$f" "superseded by $job.final.mp4" ;;
      "$job-final.mp4")
        if [[ "$final" -nt "$f" ]]; then act "$f" "promoted copy, final is newer"; fi ;;
    esac
  done < <(find "$jobdir/outputs" -maxdepth 1 -type f \( -name '*.mp4' -o -name '*.bak' \) 2>/dev/null)
done

echo
total=$(echo "$freed_kb" | awk '{printf "%.2f GB", $1/1024/1024}')
if [[ $APPLY -eq 1 ]]; then
  echo "Freed $total."
else
  echo "DRY RUN — $total would be freed. Re-run with --apply to delete."
fi
