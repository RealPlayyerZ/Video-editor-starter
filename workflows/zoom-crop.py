# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless"]
# ///
"""
zoom-crop.py — compute the punch-in zoom crop box for a video. Measured, not guessed.

LOCKED standard (see presets/punch-in-zoom-style.md): an ADAPTIVE crop — the tightest
window (matching the source's own aspect ratio) that comfortably contains the facecam
plus headphones plus a bit of breathing room, then scaled back up to full frame size.
The resulting zoom ratio is a per-video OUTPUT, not a fixed input — validated at 2.6x on
division2-lore-reaction's actual layout, and it will differ on other layouts. An earlier
version of this script forced a flat 2.0x on every video regardless of how much of the
frame the facecam actually occupied; a real side-by-side comparison (division2-lore-
reaction, 2026-08-26) showed that produced a lot of dead space around the face — sized
for a different, larger-facecam layout than this one — while the adaptive version reads
as an actual punch-in. Confirmed against three real options rendered on real footage:
fixed 2.0x (too loose), this adaptive fit (chosen), and a tighter face-only crop that
clipped a follower-overlay widget out of frame (rejected — keeping the overlay visible
was worth the little extra dead space).

The exact CENTER of the crop window is what must be measured per video regardless of
sizing approach — reusing a fixed position/offset across videos is what caused a real
clipping bug on division2-pvp-experience (facecam position drifted enough between videos
that the lore video's crop numbers cut off the face and the follower overlay on PVP).

How: sample frames across the whole cut (not just the intro — the facecam position is
assumed constant for the whole video, which held true across every job so far), detect
the face (OpenCV YuNet, model vendored in assets/models/ — same detector as
workflows/face-frame.py), then pad the detected face box generously to also cover
headphones (extend above/beside the raw face box) and nearby HUD overlays (extra general
margin), then size the crop window to the smallest aspect-ratio-matched box that contains
that padded region — never a fixed ratio imposed regardless of content.

Usage (before building any punch-in zoom segments):
  uv run workflows/zoom-crop.py projects/<job>/outputs/<job>.mp4
      → prints the crop box, writes projects/<job>/zoom-crop.json
  uv run workflows/zoom-crop.py --verify <rendered-zoomed-segment.mp4>
      → re-measures a rendered punch-in segment; must PASS (face comfortably inside
        frame on all 4 sides) before treating the punch-in as correct
  add --annotate out.png to either for an eyeball frame showing the computed crop box

This does NOT decide WHEN to zoom (that's the zoom-plan skill reading the transcript) —
only WHERE to point the crop once a punch-in window is already decided.
"""
import argparse, json, os, statistics, subprocess, sys, tempfile

SAMPLES = 10
HEADPHONE_PAD_TOP = 1.1        # x face height, extra space above the raw face box (hair + headband)
HEADPHONE_PAD_SIDE = 0.7       # x face width, extra space each side (headphone cups)
BREATHING_ROOM = 1.25          # extra uniform margin on the padded box before centering the crop
VERIFY_EDGE_MARGIN = 0.08      # face must sit this far (fraction of frame) from every edge to PASS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(REPO, "assets", "models", "face_detection_yunet_2023mar.onnx")


def probe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration", "-of", "csv=p=0", video],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]), int(out[1]), float(out[2])


def sample_frames(video, dur, n=SAMPLES):
    import cv2
    tmp = tempfile.mkdtemp()
    imgs = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        f = os.path.join(tmp, f"f{i}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video,
                        "-frames:v", "1", "-y", f], capture_output=True)
        img = cv2.imread(f)
        if img is not None:
            imgs.append(img)
    return imgs


def detect_faces(imgs, w, h):
    import cv2
    det = cv2.FaceDetectorYN_create(MODEL, "", (w, h), score_threshold=0.6)
    boxes = []
    for img in imgs:
        _, dets = det.detect(img)
        if dets is None or len(dets) == 0:
            continue
        x, y, bw, bh = max(((d[0], d[1], d[2], d[3]) for d in dets),
                           key=lambda d: d[2] * d[3])
        boxes.append((float(x), float(y), float(bw), float(bh)))
    return boxes


def median_box(boxes):
    cx = statistics.median(x + w / 2 for x, y, w, h in boxes)
    cy = statistics.median(y + h / 2 for x, y, w, h in boxes)
    fw = statistics.median(w for x, y, w, h in boxes)
    fh = statistics.median(h for x, y, w, h in boxes)
    return cx, cy, fw, fh


def measure(video, annotate=None):
    w, h, dur = probe(video)
    print(f"source: {w}x{h}  {dur:.1f}s")
    imgs = sample_frames(video, dur)
    boxes = detect_faces(imgs, w, h)
    if len(boxes) < len(imgs) / 2:
        print(f"✗ face detected in only {len(boxes)}/{len(imgs)} frames — "
              f"not writing a crop. Eyeball the facecam position manually.")
        sys.exit(1)
    cx, cy, fw, fh = median_box(boxes)
    print(f"face: center=({cx:.0f},{cy:.0f})  box={fw:.0f}x{fh:.0f}  "
          f"({len(boxes)}/{len(imgs)} frames)")

    # Pad the raw face box to cover headphones + general breathing room, then size the
    # crop window to the SMALLEST box (matching the source's own aspect ratio) that
    # still contains that padded region — the zoom ratio falls out of this as a result,
    # it's never imposed as a fixed target. This is what "adaptive" means here.
    pad_w = fw * (1 + 2 * HEADPHONE_PAD_SIDE) * BREATHING_ROOM
    pad_h = fh * (1 + HEADPHONE_PAD_TOP + 0.4) * BREATHING_ROOM  # a bit of chin room too

    aspect = w / h
    crop_h = max(pad_h, pad_w / aspect)
    crop_w = crop_h * aspect
    crop_w = round(min(crop_w, w) / 2) * 2
    crop_h = round(min(crop_h, h) / 2) * 2
    zoom_actual = w / crop_w
    print(f"padded ROI (face+headphones+breathing room): {pad_w:.0f}x{pad_h:.0f}")

    if crop_w >= w * 0.95 or crop_h >= h * 0.95:
        print(f"⚠ padded region nearly fills the whole frame — the computed zoom "
              f"({zoom_actual:.2f}x) is barely a punch-in at all. This video's facecam "
              f"may already be close-up, or face detection over-padded here — review the "
              f"annotated frame before trusting this.")

    crop_x = max(0, min(w - crop_w, round(cx - crop_w / 2)))
    crop_y = max(0, min(h - crop_h, round(cy - crop_h / 2)))
    clamped = (crop_x != round(cx - crop_w / 2)) or (crop_y != round(cy - crop_h / 2))
    if clamped:
        print(f"⚠ ideal crop center clamped to stay inside frame bounds — face sits "
              f"near an edge of the source; breathing room on that side will be tighter.")

    result = {
        "video": os.path.abspath(video),
        "source": {"w": w, "h": h},
        "face": {"cx": round(cx), "cy": round(cy), "w": round(fw), "h": round(fh),
                 "frames": len(boxes)},
        "zoom": round(zoom_actual, 3),
        "crop": {"w": crop_w, "h": crop_h, "x": crop_x, "y": crop_y},
        "ffmpeg": f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={w}:{h}:flags=lanczos",
    }
    print(f"→ crop {crop_w}x{crop_h} at ({crop_x},{crop_y}), scaled back to {w}x{h}  "
          f"(actual zoom {zoom_actual:.2f}x)")
    print(f"  ffmpeg -vf \"{result['ffmpeg']}\"")

    vdir = os.path.dirname(os.path.abspath(video))
    if os.path.basename(vdir) == "outputs":
        out = os.path.join(os.path.dirname(vdir), "zoom-crop.json")
        with open(out, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"wrote {out}")

    if annotate:
        annotate_frame(imgs[len(imgs) // 2], result, annotate)
    return result


def annotate_frame(img, result, out):
    import cv2
    f, c = result["face"], result["crop"]
    fx, fy = f["cx"] - f["w"] // 2, f["cy"] - f["h"] // 2
    cv2.rectangle(img, (fx, fy), (fx + f["w"], fy + f["h"]), (0, 0, 255), 4)       # face: red
    cv2.rectangle(img, (c["x"], c["y"]), (c["x"] + c["w"], c["y"] + c["h"]),
                  (0, 255, 255), 4)                                                # crop: yellow
    cv2.imwrite(out, img)
    print(f"annotated frame → {out} (red=detected face, yellow=zoom crop window)")


def verify(render, annotate=None):
    w, h, dur = probe(render)
    imgs = sample_frames(render, dur)
    boxes = detect_faces(imgs, w, h)
    if not boxes:
        print("✗ no face detected in the rendered segment")
        sys.exit(1)
    cx, cy, fw, fh = median_box(boxes)
    left, right = cx - fw / 2, cx + fw / 2
    top, bottom = cy - fh / 2, cy + fh / 2
    margin_x, margin_y = w * VERIFY_EDGE_MARGIN, h * VERIFY_EDGE_MARGIN
    ok = (left > margin_x and right < w - margin_x
          and top > margin_y and bottom < h - margin_y)
    print(f"face box: ({left:.0f},{top:.0f})-({right:.0f},{bottom:.0f}) in {w}x{h} frame "
          f"(need ≥{margin_x:.0f}px / ≥{margin_y:.0f}px margin from edges)")
    print("✓ PASS — face comfortably inside frame, no edge clipping" if ok
          else "✗ FAIL — face too close to an edge; re-measure with zoom-crop.py and re-render")
    if annotate:
        import cv2
        img = imgs[len(imgs) // 2]
        cv2.rectangle(img, (int(margin_x), int(margin_y)),
                      (int(w - margin_x), int(h - margin_y)), (255, 0, 0), 3)
        cv2.imwrite(annotate, img)
        print(f"annotated frame → {annotate}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--verify", metavar="RENDER")
    ap.add_argument("--annotate", metavar="OUT_PNG")
    a = ap.parse_args()
    if a.verify:
        verify(a.verify, annotate=a.annotate)
    elif a.video:
        measure(a.video, annotate=a.annotate)
    else:
        ap.error("give a base cut to measure, or --verify RENDER")
