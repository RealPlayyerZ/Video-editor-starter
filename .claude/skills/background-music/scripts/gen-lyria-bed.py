#!/usr/bin/env python3
"""
gen-lyria-bed.py — generate one or more royalty-free background-music beds with Google Lyria
(`models/lyria-3-pro-preview`, ~2.5 min each) for the background-music step.

Generalized 2026-09-08 from the per-job gen_music.py used on gpt-astra-6-reaction and
dlss-5-reaction. Generate SEVERAL variants per job and feed them all to mix-music-ducked.py
--tracks: it rotates between them across duck windows so a long video never loops one bed
("it's the same music all the way through" was real creator feedback).

Usage:
  gen-lyria-bed.py <out-prefix> [--mood energetic-dark|upbeat|chill|tense] [--prompt "..."] [--count 3]

  Writes <out-prefix>-v1.mp3 … -vN.mp3 (or exactly <out-prefix> if it ends in .mp3 and --count 1).
  API key: ~/.video-editor-secrets/gemini-api-key (house convention) or $GEMINI_API_KEY.
"""
import argparse, os, sys

MOODS = {
    # The creator's stated preference for reaction videos (2026-09-08): NOT happy/triumphant.
    "energetic-dark": (
        "High-energy driving electronic background bed, pulsing dark synth bass, aggressive tight "
        "arpeggios, tense forward-momentum percussion - urgent and intense, NOT happy or triumphant, "
        "more like a countdown to something big than a celebration. No vocals, no drops, steady "
        "mid-tempo groove suitable for looping under narration."
    ),
    "tense": (
        "Moody tension-building electronic bed, low industrial pulse, sparse ticking percussion, "
        "slowly rising synth pads like a system alert or countdown. No vocals, no drops, steady and "
        "loopable under narration."
    ),
    "upbeat": (
        "Upbeat, confident electronic background bed with a bright synth hook and punchy but not "
        "busy drums - hype, gamer-casual energy. No vocals, no big drops, steady tempo, loopable "
        "under narration."
    ),
    "chill": (
        "Laid-back lo-fi electronic bed, warm pads, soft muted drums, relaxed head-nod tempo. No "
        "vocals, no drops, loopable under narration."
    ),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_prefix")
    ap.add_argument("--mood", choices=sorted(MOODS), default="energetic-dark")
    ap.add_argument("--prompt", default=None, help="override the mood prompt entirely")
    ap.add_argument("--count", type=int, default=3, help="how many distinct variants to generate")
    args = ap.parse_args()

    key_path = os.path.expanduser("~/.video-editor-secrets/gemini-api-key")
    api_key = os.environ.get("GEMINI_API_KEY") or (open(key_path).read().strip() if os.path.isfile(key_path) else None)
    if not api_key:
        sys.exit("gen-lyria-bed: no API key (set GEMINI_API_KEY or create ~/.video-editor-secrets/gemini-api-key)")

    from google import genai  # imported late so --help works without the package
    client = genai.Client(api_key=api_key)
    prompt = args.prompt or MOODS[args.mood]

    for i in range(1, args.count + 1):
        if args.count == 1 and args.out_prefix.lower().endswith(".mp3"):
            out = args.out_prefix
        else:
            base = args.out_prefix[:-4] if args.out_prefix.lower().endswith(".mp3") else args.out_prefix
            out = f"{base}-v{i}.mp3"
        # Nudge each variant so the rotation actually sounds different, not three takes of one idea.
        variant = prompt if i == 1 else prompt + f" Variation {i}: different melodic motif and rhythm from the previous take."
        resp = client.models.generate_content(model="models/lyria-3-pro-preview", contents=variant)
        part = next((p for p in resp.candidates[0].content.parts if getattr(p, "inline_data", None) is not None), None)
        if part is None:
            sys.exit(f"gen-lyria-bed: no audio in response for variant {i}")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(part.inline_data.data)
        print(f"wrote {out} ({len(part.inline_data.data)} bytes) [{args.mood if not args.prompt else 'custom'}]")


if __name__ == "__main__":
    main()
