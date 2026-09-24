#!/usr/bin/env python3
"""lock-skills.py — record exactly which vendored skills this folder carries.

  usage: python3 tools/lock-skills.py [--check]

Writes skills-lock.json: for every vendored skill directory under .claude/skills/, its upstream source, the
version tag it was taken at, and a sha256 over its files. With --check it recomputes and exits non-zero if
anything drifted — so "update HyperFrames" is a deliberate act, not a side effect of someone editing a file
in place.

Vendored here (Apache-2.0, https://github.com/heygen-com/hyperframes): the hyperframes* skills and the task
workflows that ship beside them. Everything else under .claude/skills/ is this folder's own and is not locked.
"""
import argparse, hashlib, json, os, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS = os.path.join(REPO, ".claude", "skills")
LOCK = os.path.join(REPO, "skills-lock.json")
UPSTREAM = "heygen-com/hyperframes"
PIN = "0.7.3"
VENDORED_PREFIXES = ("hyperframes", "faceless-explainer", "general-video", "graphic-overlays", "motion-graphics",
                     "pr-to-video", "product-launch-video", "remotion-to-hyperframes", "slideshow", "website-to-video")


def digest(folder):
    h = hashlib.sha256()
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "node_modules"))
        for f in sorted(files):
            p = os.path.join(root, f)
            h.update(os.path.relpath(p, folder).encode()); h.update(b"\0")
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 16), b""):
                    h.update(chunk)
            h.update(b"\0")
    return h.hexdigest()


def compute():
    out = {}
    for name in sorted(os.listdir(SKILLS)):
        if not name.startswith(VENDORED_PREFIXES):
            continue
        p = os.path.join(SKILLS, name)
        if os.path.isdir(p):
            out[name] = {"source": UPSTREAM, "pin": PIN, "sha256": digest(p)}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    now = compute()
    if a.check:
        if not os.path.isfile(LOCK):
            sys.exit("[lock] no skills-lock.json — run without --check to create it")
        old = json.load(open(LOCK, encoding="utf-8")).get("skills", {})
        drift = [k for k in now if k not in old or old[k]["sha256"] != now[k]["sha256"]]
        gone = [k for k in old if k not in now]
        if drift or gone:
            print("[lock] DRIFT" + (" changed: " + ", ".join(drift) if drift else "") + (" missing: " + ", ".join(gone) if gone else ""))
            sys.exit(1)
        print(f"[lock] {len(now)} vendored skills match the lock")
        return
    json.dump({"upstream": UPSTREAM, "pin": PIN, "license": "Apache-2.0", "skills": now},
              open(LOCK, "w", encoding="utf-8"), indent=2)
    print(f"[lock] wrote {LOCK} — {len(now)} vendored skills")


if __name__ == "__main__":
    main()
