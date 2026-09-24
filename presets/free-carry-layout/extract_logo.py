#!/usr/bin/env python3
"""extract_logo.py — lift the Z-helmet out of the outro video into a transparent PNG.

The outro has no alpha and no flat backdrop (a swirling pink/salmon gradient), so chroma key is out.
What separates the helmet is TONE, not hue: the helmet body is near-black with a blue visor, the swirl
behind it is bright pink. Alpha = dark pixels OR blue-visor pixels -> largest connected blob -> holes
filled -> SYMMETRY CUT -> edges feathered. Run it once; the PNG is then a reusable brand asset.

THE SYMMETRY CUT (2026-09-21). The outro's glowing ring sweeps in FRONT of the helmet in every single
frame, and where it crosses the jaw the tone test swallows it -- so the blob grew a bright magenta tail
off the bottom-right of the chin that reads as a neck ("that little pink to the bottom right of it?
It's like my neck"). No colour rule can lift it: the ribbon's magenta is the same magenta as the
helmet's own rim light, so keying it punches holes in the shell. Geometry separates them instead. The
helmet is front-facing and near-symmetric about its vertical axis (measured IoU 0.913); the ribbon is a
one-sided diagonal. Intersecting the silhouette with its own mirror therefore drops the tail and keeps
the helmet, headphone cans included. The ribbon light still PAINTS the jaw -- that stays, and reads as
the rim lighting it looks like -- but the helmet now ends at the chin.
"""
import sys
import numpy as np
from PIL import Image, ImageFilter

src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
W, H = im.size
# helmet bbox measured off a grid overlay (1280x720 view -> x 420-880, y 150-640), padded
x0, y0, x1, y1 = int(W * 0.27), int(H * 0.17), int(W * 0.74), int(H * 0.92)
crop = im.crop((x0, y0, x1, y1))
a = np.asarray(crop).astype(np.float32) / 255.0
r, g, b = a[..., 0], a[..., 1], a[..., 2]
v = a.max(2)
blue = (b > r + 0.08) & (b > 0.10)                      # visor + the blue head shading
dark = v < 0.42                                          # the black shell
mask = (dark | blue) & ~((r > 0.75) & (g < 0.55) & (b < 0.62))   # never the hot-pink swirl
m = Image.fromarray((mask * 255).astype(np.uint8))
m = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))   # close gaps
arr = np.asarray(m) > 127


def largest(bits):
    """largest connected component (4-way flood fill, iterative)"""
    lab = np.zeros(bits.shape, np.int32); cur = 0; best = (0, 0)
    hh, ww = bits.shape
    for sy in range(0, hh, 2):
        for sx in range(0, ww, 2):
            if bits[sy, sx] and lab[sy, sx] == 0:
                cur += 1; stack = [(sy, sx)]; lab[sy, sx] = cur; n = 0
                while stack:
                    cy, cx = stack.pop(); n += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < hh and 0 <= nx < ww and bits[ny, nx] and lab[ny, nx] == 0:
                            lab[ny, nx] = cur; stack.append((ny, nx))
                if n > best[1]: best = (cur, n)
    return lab == best[0], best[1]


def span_fill(mm, axis):
    """fill interior holes -- the white Z and the lit jaw are BRIGHT, so the tone test rejects them and a
    flood-from-the-corner leaks in through the visor edge. Scanline-fill rows and columns and keep the
    intersection: conservative, and the helmet is convex enough in both axes for it."""
    f = np.zeros_like(mm)
    it = range(mm.shape[0]) if axis == 0 else range(mm.shape[1])
    for i in it:
        line = mm[i, :] if axis == 0 else mm[:, i]
        idx = np.flatnonzero(line)
        if idx.size:
            if axis == 0: f[i, idx[0]:idx[-1] + 1] = True
            else: f[idx[0]:idx[-1] + 1, i] = True
    return f


keep, area = largest(arr)
filled = (span_fill(keep, 0) & span_fill(keep, 1)) | keep

# --- symmetry cut: find the helmet's vertical axis by maximising mirror overlap, then intersect
xs = np.nonzero(filled)[1]
best = None
for cx in range(xs.min() + 50, xs.max() - 50, 2):
    half = min(cx - xs.min(), xs.max() - cx)
    L = filled[:, cx - half:cx]; R = filled[:, cx:cx + half][:, ::-1]
    iou = (L & R).sum() / max(1, (L | R).sum())
    if best is None or iou > best[0]: best = (iou, cx, half)
iou, cx, half = best
mir = np.zeros_like(filled)
mir[:, cx - half:cx] = filled[:, cx:cx + half][:, ::-1]
mir[:, cx:cx + half] = filled[:, cx - half:cx][:, ::-1]
sym, _ = largest(filled & mir)
# close the nicks the intersection leaves along the rims (dilate then erode, same radius -> no net growth)
s = Image.fromarray((sym * 255).astype(np.uint8))
for _ in range(3): s = s.filter(ImageFilter.MaxFilter(9))
for _ in range(3): s = s.filter(ImageFilter.MinFilter(9))
sym = np.asarray(s) > 127

alpha = Image.fromarray((sym * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2))
rgba = crop.convert("RGBA"); rgba.putalpha(alpha)
bb = rgba.getbbox(); rgba = rgba.crop(bb)
rgba.save(out)
hh, ww = arr.shape
print(f"[logo] {out} {rgba.size[0]}x{rgba.size[1]}  axis x={cx} (mirror IoU {iou:.3f}), "
      f"symmetry cut dropped {(1 - sym.sum() / max(1, filled.sum())) * 100:.1f}% of the blob")
