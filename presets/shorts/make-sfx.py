#!/usr/bin/env python3
"""
make-sfx.py — synthesize the utility sound-effect set for the Shorts comedy layer.

Pure Python + the wave module (no numpy, no downloads, no rights questions). Writes 48 kHz /
16-bit / stereo WAVs into assets/sfx/synth/, one per tag, peak-normalized to -3 dBFS. These are
the FALLBACKS: any file the creator drops into assets/sfx/ whose name carries the same tag
("vine-boom.mp3" → boom, "record-scratch.wav" → scratch) wins over the synthetic one — see
assets/sfx/README.md and gags.py:sfx_library().

  presets/shorts/make-sfx.py            # (re)generate everything
  presets/shorts/make-sfx.py boom womp  # just these

Deterministic (seeded), ~1 s per sound.
"""
import array, math, os, random, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "assets", "sfx", "synth"))
SR = 48000
TWO_PI = 2.0 * math.pi


# ----------------------------------------------------------------------------- building blocks
def frames(dur):
    return int(dur * SR)


def sine_sweep(dur, f_of_t, amp_of_t):
    """Phase-accumulated sine: f_of_t(t) in Hz, amp_of_t(t) in 0..1."""
    out, ph = [], 0.0
    for i in range(frames(dur)):
        t = i / SR
        ph += TWO_PI * f_of_t(t) / SR
        out.append(math.sin(ph) * amp_of_t(t))
    return out


def harmonics(dur, f_of_t, amp_of_t, partials):
    """Sum of partials [(mult, gain), ...] on one phase accumulator (brassy / square-ish tones)."""
    out, ph = [], 0.0
    for i in range(frames(dur)):
        t = i / SR
        ph += TWO_PI * f_of_t(t) / SR
        out.append(sum(g * math.sin(ph * m) for m, g in partials) * amp_of_t(t))
    return out


def noise(dur, rng):
    return [rng.uniform(-1.0, 1.0) for _ in range(frames(dur))]


def svf(x, fc_of_t, q=0.7, mode="band"):
    """Chamberlin state-variable filter with a per-sample cutoff — the one tool that makes
    whooshes, risers and scratches out of white noise. mode: band | low | high."""
    low = band = 0.0
    out = []
    for i, s in enumerate(x):
        fc = min(fc_of_t(i / SR), SR / 6.5)
        f = 2.0 * math.sin(math.pi * fc / SR)
        low += f * band
        high = s - low - q * band
        band += f * high
        out.append(band if mode == "band" else low if mode == "low" else high)
    return out


def env_decay(tau, attack=0.004):
    return lambda t: (min(1.0, t / attack) if attack else 1.0) * math.exp(-t / tau)


def env_adsr(a, d, s_level, r, dur):
    def f(t):
        if t < a:
            return t / a
        if t < a + d:
            return 1.0 - (1.0 - s_level) * (t - a) / d
        if t < dur - r:
            return s_level
        return max(0.0, s_level * (dur - t) / r)
    return f


def mix(*layers):
    n = max(len(l) for l in layers)
    return [sum(l[i] for l in layers if i < len(l)) for i in range(n)]


def gain(x, g):
    return [s * g for s in x]


def saturate(x, drive=1.6):
    return [math.tanh(s * drive) for s in x]


def bitcrush(x, bits=4):
    q = float(2 ** (bits - 1))
    return [math.floor(s * q) / q for s in x]


def write(name, samples, peak_db=-3.0):
    os.makedirs(OUT_DIR, exist_ok=True)
    pk = max(1e-9, max(abs(s) for s in samples))
    g = (10 ** (peak_db / 20.0)) / pk
    a = array.array("h")
    for s in samples:
        v = int(max(-1.0, min(1.0, s * g)) * 32767)
        a.append(v); a.append(v)          # stereo (dual mono) to match the base cut's layout
    path = os.path.join(OUT_DIR, f"{name}.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(a.tobytes())
    print(f"  {name:10s} {len(samples) / SR:4.2f}s  → {path}")


# ----------------------------------------------------------------------------- the sounds
def boom():
    """Sub-bass hit in the 'vine boom' family: 90→32 Hz sweep, long tail, click transient, tanh."""
    rng = random.Random(1)
    sub = sine_sweep(1.4, lambda t: 32 + 70 * math.exp(-t / 0.11), env_decay(0.38, 0.003))
    body = sine_sweep(1.4, lambda t: 2 * (32 + 70 * math.exp(-t / 0.11)), env_decay(0.12, 0.003))
    click = svf(noise(0.012, rng), lambda t: 900.0, 0.5, "low")
    return saturate(mix(sub, gain(body, 0.25), gain(click, 0.8)), 1.9)


def hit():
    """Cinematic impact: tighter boom + a bright noise crack."""
    rng = random.Random(2)
    sub = sine_sweep(0.9, lambda t: 45 + 110 * math.exp(-t / 0.06), env_decay(0.22, 0.002))
    crack = svf(noise(0.06, rng), lambda t: 2600 - 30000 * t, 0.6, "band")
    crack = [s * math.exp(-i / SR / 0.02) for i, s in enumerate(crack)]
    return saturate(mix(sub, gain(crack, 0.9)), 1.7)


def whoosh():
    """Filtered noise sweeping up then down — under punch-ins, quiet."""
    rng = random.Random(3)
    dur = 0.45
    fc = lambda t: 350 + 3200 * math.sin(math.pi * min(1.0, t / dur))
    amp = lambda t: math.sin(math.pi * min(1.0, t / dur)) ** 1.6
    return [s * amp(i / SR) for i, s in enumerate(svf(noise(dur, rng), fc, 0.55, "band"))]


def ding():
    parts = [(1046.5, 1.0, 0.65), (2093.0, 0.35, 0.35), (3140.0, 0.16, 0.22), (4186.0, 0.07, 0.14)]
    return mix(*[sine_sweep(1.4, lambda t, f=f: f, lambda t, g=g, tau=tau: g * env_decay(tau, 0.002)(t)) for f, g, tau in parts])


def pop():
    return sine_sweep(0.14, lambda t: 70 + 260 * math.exp(-t / 0.018), env_decay(0.03, 0.001))


def riser():
    rng = random.Random(4)
    dur = 1.6
    nz = svf(noise(dur, rng), lambda t: 150 * (7000 / 150) ** min(1.0, t / dur), 0.5, "band")
    nz = [s * (min(1.0, i / SR / dur) ** 1.8) for i, s in enumerate(nz)]
    tone = sine_sweep(dur, lambda t: 80 * (900 / 80) ** min(1.0, t / dur), lambda t: 0.3 * min(1.0, t / dur) ** 1.5)
    return mix(nz, tone)


def glitch():
    rng = random.Random(5)
    total = frames(0.5)
    out = [0.0] * total
    for _ in range(8):
        start = rng.randint(0, total - frames(0.07))
        ln = frames(rng.uniform(0.025, 0.06))
        f = rng.uniform(200, 1800)
        a = rng.uniform(0.4, 1.0)
        for i in range(ln):
            t = i / SR
            sq = 1.0 if math.sin(TWO_PI * f * t) >= 0 else -1.0
            out[start + i] += a * (0.7 * sq + 0.3 * rng.uniform(-1, 1))
    return bitcrush(out, 4)


def buzz():
    """Error buzzer: two squares beating, lowpassed."""
    dur = 0.35
    sq = lambda f: harmonics(dur, lambda t: f, env_adsr(0.003, 0.02, 0.85, 0.06, dur), [(1, 1.0), (3, 1 / 3), (5, 1 / 5), (7, 1 / 7)])
    return svf(mix(sq(110.0), gain(sq(165.0), 0.8)), lambda t: 1300.0, 0.8, "low")


def bassdrop():
    dur = 1.8
    amp = lambda t: min(1.0, t / 0.3) * (1.0 if t < 1.2 else math.exp(-(t - 1.2) / 0.25))
    return saturate(sine_sweep(dur, lambda t: 90 * (22 / 90) ** min(1.0, t / 1.2), amp), 1.5)


def scratch():
    """Record-scratch placeholder: three noise bursts with a wobbling bandpass + a falling tone.
    A real one dropped in as record-scratch.* replaces this automatically."""
    rng = random.Random(6)
    dur = 0.55
    bursts = [(0.0, 0.16), (0.19, 0.33), (0.36, 0.55)]
    amp = lambda t: max((math.sin(math.pi * (t - a) / (b - a)) ** 0.7 if a <= t < b else 0.0) for a, b in bursts)
    nz = svf(noise(dur, rng), lambda t: 700 + 1700 * (0.5 + 0.5 * math.sin(TWO_PI * 9.0 * t)), 0.45, "band")
    nz = [s * amp(i / SR) for i, s in enumerate(nz)]
    tone = sine_sweep(dur, lambda t: 1300 - 900 * ((t * 6.0) % 1.0), lambda t: 0.3 * amp(t))
    return mix(nz, tone)


def crickets():
    dur = 1.7
    out = [0.0] * frames(dur)
    for voice, (f, phase) in enumerate([(4300.0, 0.0), (4650.0, 0.23)]):
        t_burst = phase
        while t_burst < dur:
            for k in range(5):
                a = t_burst + k * 0.042
                for i in range(frames(0.016)):
                    idx = frames(a) + i
                    if idx < len(out):
                        env = math.sin(math.pi * i / frames(0.016))
                        out[idx] += 0.5 * env * math.sin(TWO_PI * f * idx / SR)
            t_burst += 0.46
    return out


def shutter():
    rng = random.Random(7)
    dur = 0.16
    out = [0.0] * frames(dur)
    for start in (0.0, 0.055):
        c = svf(noise(0.008, rng), lambda t: 2200.0, 0.4, "band")
        for i, s in enumerate(c):
            out[frames(start) + i] += s * math.exp(-i / SR / 0.003)
        lo = sine_sweep(0.03, lambda t: 180.0, env_decay(0.01, 0.001))
        for i, s in enumerate(lo):
            out[frames(start) + i] += 0.5 * s
    return out


def boing():
    return sine_sweep(0.6, lambda t: 330 * (1 + 0.35 * math.sin(TWO_PI * 7.5 * t) * math.exp(-t / 0.3)), env_decay(0.24, 0.003))


def womp():
    """Sad-trombone-ish descending four notes, the last one wobbling."""
    notes = [(233.1, 0.28), (220.0, 0.28), (207.7, 0.28), (196.0, 0.75)]
    brass = [(1, 1.0), (2, 0.5), (3, 0.42), (4, 0.25), (5, 0.18), (6, 0.1)]
    seq = []
    for k, (f, d) in enumerate(notes):
        last = k == len(notes) - 1
        fo = (lambda t, f=f: f * (1 + 0.04 * math.sin(TWO_PI * 5.5 * t))) if last else (lambda t, f=f: f)
        seq += harmonics(d, fo, env_adsr(0.02, 0.05, 0.8, 0.12 if not last else 0.3, d), brass)
        seq += [0.0] * frames(0.03)
    return saturate(svf(seq, lambda t: 1800.0, 0.9, "low"), 1.3)


def airhorn():
    dur = 0.9
    saw = [(m, 1.0 / m) for m in range(1, 9)]
    voices = [harmonics(dur, lambda t, d=d: 415.3 * d, env_adsr(0.02, 0.1, 0.9, 0.15, dur), saw) for d in (0.994, 1.0, 1.006)]
    return saturate(svf(mix(*voices), lambda t: 1400.0, 0.5, "band"), 1.4)


def laugh_track():
    """Not a laugh — a soft, short crowd-ish 'hah' shaped from noise, for the 'crowd reacts' gag.
    Deliberately subtle; drop a real one in as laugh.* to replace."""
    rng = random.Random(8)
    dur = 1.1
    out = [0.0] * frames(dur)
    for start in (0.0, 0.17, 0.33, 0.52, 0.72):
        seg = svf(noise(0.14, rng), lambda t: 900 - 1800 * t, 0.9, "band")
        for i, s in enumerate(seg):
            idx = frames(start) + i
            if idx < len(out):
                out[idx] += s * math.sin(math.pi * i / len(seg)) ** 0.8 * (1.0 - 0.12 * start)
    return out


def tick():
    """A countdown tick: a 1.8 kHz click over a small low thump."""
    click = sine_sweep(0.05, lambda t: 1800.0, env_decay(0.012, 0.001))
    thump = sine_sweep(0.12, lambda t: 150 + 80 * math.exp(-t / 0.02), env_decay(0.035, 0.001))
    return mix(gain(click, 0.8), thump)


def heartbeat():
    """Lub-dub: two sub-bass thumps 0.17 s apart."""
    lub = sine_sweep(0.35, lambda t: 55 + 30 * math.exp(-t / 0.04), env_decay(0.10, 0.003))
    dub = [0.0] * frames(0.17) + sine_sweep(0.35, lambda t: 48 + 25 * math.exp(-t / 0.04), env_decay(0.09, 0.003))
    return saturate(mix(lub, gain(dub, 0.8)), 1.4)


SOUNDS = {"boom": boom, "hit": hit, "whoosh": whoosh, "ding": ding, "pop": pop, "riser": riser, "glitch": glitch,
          "buzz": buzz, "bassdrop": bassdrop, "scratch": scratch, "crickets": crickets, "shutter": shutter,
          "boing": boing, "womp": womp, "airhorn": airhorn, "laugh": laugh_track, "tick": tick, "heartbeat": heartbeat}

if __name__ == "__main__":
    names = sys.argv[1:] or list(SOUNDS)
    print(f"[make-sfx] → {OUT_DIR}")
    for n in names:
        if n not in SOUNDS:
            raise SystemExit(f"[make-sfx] unknown sound {n!r}; have: {', '.join(SOUNDS)}")
        write(n, SOUNDS[n]())
