#!/usr/bin/env python3
"""scan-transcript.py — find the words the transcriber probably got wrong.

  usage: scan-transcript.py <job_dir> [--dict /usr/share/dict/words] [--min-prob 0.45]

Reads <job_dir>/transcript/words.json and prints SUSPECTS — words worth a human look — with context.
It changes nothing. Claude reads the list, decides in context, and adds real mishears to
presets/caption-corrections.json (recurring names/brands) or <job>/corrections.local.json (one-offs).

A word is a suspect when any of these hold:
  * the recogniser's own confidence for it is low (prob below --min-prob)
  * a dictionary is available and the word isn't in it (proper nouns show up here too — that's fine, skip them)
  * it looks like a stitched or broken token (digits mixed with letters, internal capitals)
Skipped: numbers, tokens of one or two characters, anything already in the corrections list (either side).

Dictionary: /usr/share/dict/words if it exists (Ubuntu: sudo apt install wamerican). Without one the scan
still works on confidence and shape alone — it just surfaces fewer proper-noun mishears.
"""
import argparse, json, os, re, sys

PUNCT = ".,!?;:\"'’”()[]"


def norm(tok):
    return tok.strip(PUNCT).lower()


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--dict", default="/usr/share/dict/words")
    ap.add_argument("--min-prob", type=float, default=0.45)
    a = ap.parse_args()

    words_path = os.path.join(a.job_dir, "transcript", "words.json")
    if not os.path.isfile(words_path):
        sys.exit(f"[scan] no transcript at {words_path} — run transcribe.sh first")
    clips = load_json(words_path)["clips"]

    known = set()
    repo = os.path.abspath(os.path.join(a.job_dir, "..", ".."))
    for cand in (os.path.join(repo, "presets", "caption-corrections.json"),
                 os.path.join(a.job_dir, "corrections.local.json")):
        if os.path.isfile(cand):
            d = load_json(cand)
            for k, v in d.get("auto", {}).items():
                known.add(k.lower()); known.add(str(v).lower())
            for k in d.get("flag", {}):
                known.add(k.lower())

    dictionary = None
    if os.path.isfile(a.dict):
        with open(a.dict, encoding="utf-8", errors="ignore") as f:
            dictionary = {ln.strip().lower() for ln in f if ln.strip()}
        # common inflections the word list may lack
        extra = set()
        for w in list(dictionary):
            extra.update({w + "s", w + "es", w + "ed", w + "ing", w + "ly", w + "er", w + "est"})
        dictionary |= extra
    else:
        print(f"[scan] no dictionary at {a.dict} — scanning on confidence and shape only", file=sys.stderr)

    suspects = {}
    for clip in clips:
        ws = clip["words"]
        for i, w in enumerate(ws):
            tok = w["w"]; key = norm(tok)
            if len(key) <= 2 or key.replace(",", "").replace(".", "").isdigit() or key in known:
                continue
            reasons = []
            if w.get("prob", 1.0) < a.min_prob:
                reasons.append(f"prob {w.get('prob', 0):.2f}")
            if dictionary is not None and key.isalpha() and key not in dictionary:
                reasons.append("not in dictionary")
            if re.search(r"\d", key) and re.search(r"[a-z]", key):
                reasons.append("digits+letters")
            if re.search(r"[a-z][A-Z]", tok.strip(PUNCT)):
                reasons.append("internal capital")
            if not reasons:
                continue
            ctx = " ".join(x["w"] for x in ws[max(0, i - 3): i + 4])
            entry = suspects.setdefault(key, {"n": 0, "reasons": set(), "ctx": ctx, "at": w["start"], "clip": clip["file"]})
            entry["n"] += 1; entry["reasons"].update(reasons)

    if not suspects:
        print("[scan] no suspects — transcript looks clean")
        return
    print(f"[scan] {len(suspects)} suspect word(s):")
    for key, e in sorted(suspects.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {key:<18} x{e['n']:<3} {', '.join(sorted(e['reasons'])):<28} {e['clip']} @{e['at']:.1f}s   …{e['ctx']}…")
    print("[scan] judge each in context. Real mishear -> add to presets/caption-corrections.json (auto: single word only).")


if __name__ == "__main__":
    main()
