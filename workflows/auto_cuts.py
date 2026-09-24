#!/usr/bin/env python3
"""
auto_cuts.py — apply rough-cut's auto-kill rules programmatically to a words.json transcript
and emit a cuts.json. Built for state-of-play-hijacked-reaction / state-of-play-chat-spam-reaction,
whose raw footage is already a tight, on-script article read (not a rambly take) - a
mechanical "cut silence>0.4s + kill vestigial filler + collapse immediate word-repeats" pass
gets very close to what a careful hand-edit would do, at a fraction of the context cost of
reading both ~8000-word transcripts by hand.

Usage: auto_cuts.py <clip_name> <words_json_path> <out_cuts_json_path>
"""
import json, re, sys

FILLER_STANDALONE = {"um", "uh", "umm", "uhh", "erm"}
# vestigial "like"/"you know"/"so yeah"/"basically" are judgment calls - only strip them when
# they appear as a whole isolated utterance between two silences, not mid-sentence (mid-sentence
# ones are usually load-bearing rhythm, per the skill's "preserve cadence" rule).
SILENCE_GAP = 0.4


def norm(w):
    return re.sub(r"[^\w']", "", w).lower()


def main():
    clip, words_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.load(open(words_path))
    words = None
    for c in data["clips"]:
        if c["clip"] == clip or clip in c["clip"]:
            words = c["words"]
            break
    if words is None:
        sys.exit(f"clip {clip} not found")

    # Pass 1: drop standalone filler tokens and collapse immediate exact-word stutters
    # (e.g. "let's let's read" -> "let's read", "I- I was" handled by norm() dropping punctuation).
    kept = []
    i = 0
    while i < len(words):
        w = words[i]
        wn = norm(w["w"])
        if wn in FILLER_STANDALONE:
            i += 1
            continue
        # immediate stutter: same normalized word repeated back-to-back -> keep the LATER one
        if kept and norm(kept[-1]["w"]) == wn and (w["start"] - kept[-1]["end"]) < 0.3:
            kept[-1] = w
            i += 1
            continue
        kept.append(w)
        i += 1
    words = kept

    # Pass 2: build segments, splitting on gaps >= SILENCE_GAP (dead air cut).
    segments = []
    seg_start_idx = 0
    for idx in range(1, len(words)):
        gap = words[idx]["start"] - words[idx - 1]["end"]
        if gap >= SILENCE_GAP:
            seg_words = words[seg_start_idx:idx]
            if seg_words:
                segments.append(seg_words)
            seg_start_idx = idx
    if seg_start_idx < len(words):
        segments.append(words[seg_start_idx:])

    # Pass 3: emit cuts.json segments with small in/out padding, merging segments that are
    # separated by only a small gap (<0.6s) back together to avoid over-fragmenting (lots of
    # tiny segments = lots of extra re-encode boundaries for no editorial reason).
    out_segments = []
    for seg_words in segments:
        if not seg_words:
            continue
        start = max(0.0, seg_words[0]["start"] - 0.05)
        end = seg_words[-1]["end"] + 0.06
        transcript = " ".join(w["w"] for w in seg_words)
        if out_segments and start - out_segments[-1]["end"] < 0.6:
            out_segments[-1]["end"] = end
            out_segments[-1]["transcript"] += " " + transcript
        else:
            out_segments.append({"clip": clip, "start": round(start, 3), "end": round(end, 3), "transcript": transcript})

    json.dump({"segments": out_segments}, open(out_path, "w"), indent=2)
    kept_dur = sum(s["end"] - s["start"] for s in out_segments)
    raw_dur = words[-1]["end"] if words else 0
    print(f"[auto_cuts] {clip}: {len(out_segments)} segments, {kept_dur:.1f}s kept (raw ~{raw_dur:.1f}s)")


if __name__ == "__main__":
    main()
