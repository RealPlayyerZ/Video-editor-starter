#!/usr/bin/env python3
"""
match_paragraphs.py — turn a real article's paragraphs into paragraph-plan.json by aligning
them against the job's canonical transcript (outputs/<job>.transcript.json - kept-words,
rough-cut timeline, brand-corrected; see CLAUDE.md's "transcribe once" lab note).

Formalizes the manual process used on marathon-reaction-article (2026-08-28/30): paste the
REAL article text (word-for-word, from the source page - NOT the creator's out-loud
paraphrase) as one paragraph per line, and this fuzzy-aligns each paragraph's words against
the transcript's word stream to recover real start/end timestamps, in order, sequentially
(each paragraph's search starts where the last one's match ended - the creator reads the
article start to finish, so this doesn't need a full O(n*m) alignment).

The transcript's own words are what the creator actually SAID out loud (approximate
paraphrase/misreadings included) - they will never match the real article text perfectly.
That's expected. This tool finds the best-effort span and reports a match-quality score per
paragraph; anything below --min-score gets flagged in the output for manual review (the
timestamps are still filled in as a best guess, just marked "low_confidence": true) rather
than silently guessing wrong or crashing the whole job over one rough paragraph.

Output shape matches marathon-reaction-article/paragraph-plan.json exactly, MINUS
broll_clip/broll_in - that's a creative/thematic call (which trailer clip actually shows
what's being discussed) this tool deliberately does not make. Fill those in by hand (or have
Claude do it reading each paragraph's topic against the available broll library) before
running build_paragraph.py.

Usage:
  match_paragraphs.py --transcript outputs/<job>.transcript.json \
      --article article-paragraphs.txt --job <job-name> --out paragraph-plan.json

article-paragraphs.txt: one real paragraph per line (blank lines ignored).
"""
import argparse, json, re, sys
from difflib import SequenceMatcher

WORD_RE = re.compile(r"[a-z0-9']+")


def norm_words(text):
    return WORD_RE.findall(text.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--article", required=True, help="one real paragraph per line")
    ap.add_argument("--job", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-score", type=float, default=0.35,
                     help="match ratio below this gets flagged low_confidence (default 0.35 - "
                          "article text and spoken/misheard text never align perfectly)")
    args = ap.parse_args()

    transcript = json.load(open(args.transcript))
    twords = transcript["words"]
    tnorm = [norm_words(w["text"]) for w in twords]
    tflat = [w for sub in tnorm for w in sub]  # flat normalized word list, 1:1 isn't guaranteed
    # per-flat-word index -> transcript word index (a transcript "word" entry can itself expand
    # to >1 normalized token, e.g. "V-17" -> ["v","17"] - map every flat token back to its
    # source entry so start/end lookups stay correct either way)
    flat_to_tword = []
    for i, sub in enumerate(tnorm):
        flat_to_tword.extend([i] * len(sub))

    paragraphs = [l.strip() for l in open(args.article, encoding="utf-8") if l.strip()]
    if not paragraphs:
        sys.exit("no paragraphs found in --article (one real paragraph per line)")

    # GLOBAL alignment, not a per-paragraph greedy window: a first version searched each
    # paragraph in a fixed lookahead window with the cursor advancing after each match, and
    # it drifted catastrophically on real data (verified against marathon-reaction-article's
    # known-good paragraph-plan.json - one bad early match threw off every paragraph after it,
    # and by the back third of the video the cursor had run off the end, leaving 38 of 46
    # paragraphs completely unmatched). Instead: flatten the WHOLE article and the WHOLE
    # transcript into two long word sequences and run ONE SequenceMatcher over both. difflib's
    # matching blocks come back in non-decreasing order in BOTH sequences, so this is a real
    # (if approximate) global alignment - no manually-advanced cursor to drift.
    p_word_lists = [norm_words(t) for t in paragraphs]
    article_flat, p_bounds = [], []
    for words in p_word_lists:
        start = len(article_flat)
        article_flat.extend(words)
        p_bounds.append((start, len(article_flat)))

    print(f"[match] aligning {len(article_flat)} article words against "
          f"{len(tflat)} transcript words (one pass, may take a moment)...", file=sys.stderr)
    sm = SequenceMatcher(None, article_flat, tflat, autojunk=True)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]

    out, low_confidence = [], []
    for idx, (p_start, p_end) in enumerate(p_bounds, 1):
        text = paragraphs[idx - 1]
        # A matching block can straddle a paragraph boundary (block.a..block.a+size may cross
        # p_end) - a first version counted the WHOLE block's transcript range for every
        # paragraph it touched, which collapsed adjacent paragraphs onto the same identical
        # transcript span (verified wrong against marathon's known-good plan: consecutive
        # paragraphs came back with byte-for-byte identical start/end). Fix: clip each block to
        # this paragraph's exact [p_start, p_end) article-word range before reading its
        # transcript-side offset - since a block is a contiguous 1:1-aligned run, the clipped
        # sub-range's transcript offset is just the same clip applied to block.b.
        clips = []  # (t_start, t_end_inclusive, n_words) after clipping to this paragraph
        for blk in blocks:
            ov_start = max(blk.a, p_start)
            ov_end = min(blk.a + blk.size, p_end)
            if ov_start >= ov_end:
                continue
            t_start = blk.b + (ov_start - blk.a)
            t_end = blk.b + (ov_end - blk.a) - 1  # inclusive
            clips.append((t_start, t_end, ov_end - ov_start))

        # Real articles repeat short phrases verbatim across sections (e.g. every paragraph
        # here opens with some form of "Marathon Season 3"), so a paragraph can pick up a
        # stray clipped match far from where it's actually spoken - verified against
        # marathon's known-good plan: naive min/max across ALL clips blew paragraph 3's end
        # out from 108s to 164s off a single distant stray match. Fix: cluster the clips by
        # transcript-time proximity (30s gap = new cluster - longer than any real paragraph
        # takes to read) and keep only the cluster with the most matched words, discarding
        # isolated far-away matches as noise rather than letting them stretch the bounds.
        first_flat = last_flat = matched_words = None
        if clips:
            clips.sort()
            gap_secs = lambda a_end, b_start: (
                twords[flat_to_tword[b_start]]["start"] - twords[flat_to_tword[a_end]]["end"])
            clusters, cur = [], [clips[0]]
            for c in clips[1:]:
                if gap_secs(cur[-1][1], c[0]) > 30.0:  # >30s of real time = new cluster
                    clusters.append(cur)
                    cur = [c]
                else:
                    cur.append(c)
            clusters.append(cur)
            best = max(clusters, key=lambda cl: sum(c[2] for c in cl))
            first_flat = min(c[0] for c in best)
            last_flat = max(c[1] for c in best)
            matched_words = sum(c[2] for c in best)
        score = (matched_words or 0) / max(1, p_end - p_start)
        if first_flat is None:
            print(f"[match] para{idx:02d}: NO transcript words matched - leaving null, "
                  f"needs manual start/end", file=sys.stderr)
            out.append({"idx": idx, "start": None, "end": None, "text": text,
                        "low_confidence": True})
            low_confidence.append(idx)
            continue
        start_tword = flat_to_tword[first_flat]
        end_tword = flat_to_tword[last_flat]
        start_t = twords[start_tword]["start"]
        end_t = twords[end_tword]["end"]
        entry = {"idx": idx, "start": round(start_t, 3), "end": round(end_t, 3), "text": text}
        if score < args.min_score:
            entry["low_confidence"] = True
            low_confidence.append(idx)
        out.append(entry)
        print(f"[match] para{idx:02d} [{start_t:.2f}-{end_t:.2f}] score={score:.2f} "
              f"{'(LOW - review)' if score < args.min_score else ''}", file=sys.stderr)

    # Enforce monotonic ordering (paragraphs are read in order - a repeated real-world phrase
    # can otherwise pull a later paragraph's match earlier than the one before it). Any
    # paragraph whose start doesn't come after the previous one's is flagged for manual review
    # rather than silently left in a broken, out-of-order state.
    prev_end = -1.0
    for entry in out:
        if entry["start"] is None:
            continue
        if entry["start"] < prev_end:
            entry["low_confidence"] = True
            if entry["idx"] not in low_confidence:
                low_confidence.append(entry["idx"])
        prev_end = max(prev_end, entry["end"])

    # Deliberately NOT closing gaps between consecutive paragraphs here. A gap after a
    # paragraph is very often an entire zoom-plan.json reaction window (tens of seconds), not
    # a small natural pause - this tool only sees paragraphs, not zoom windows, so it can't
    # tell the two apart. A first version stretched every paragraph's end forward to the next
    # paragraph's start unconditionally, which silently swallowed whole reaction windows into
    # the preceding paragraph's card (caught against marathon's known-good plan: paragraph 3's
    # end got stretched from a correct 107.58s to 164.03s, eating the entire 108.1-163.0
    # reaction window). assemble_final.py already closes real small pauses correctly, because
    # it works on the full interleaved zoom+paragraph timeline where that distinction is
    # actually visible - let it do that job; this tool just reports what it measured.
    json.dump({"job": args.job, "paragraphs": out}, open(args.out, "w"), indent=2)
    print(f"[match] wrote {args.out} - {len(out)} paragraphs, "
          f"{len(low_confidence)} flagged low_confidence: {low_confidence}", file=sys.stderr)
    if low_confidence:
        print("[match] review the flagged paragraphs' start/end by hand before building - "
              "a bad match here throws off every paragraph after it in a job with sequential "
              "cursor advancement", file=sys.stderr)


if __name__ == "__main__":
    main()
