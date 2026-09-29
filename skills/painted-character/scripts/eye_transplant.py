#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy","scipy","pillow"]
# ///
"""eye_transplant.py - put the EYES of a repainted portrait into the original portrait's eye almonds.

For eye variants of one portrait (skins that differ only in the eyes). An image model can repaint the portrait with
open eyes and it looks real, but the face drifts a little - and every frame downstream (the imprint, the texture
morph) is fitted to the ORIGINAL. So only the eye content moves over (procedurally drawn eyes look like a cartoon):

  original almond: the near-black blob ringed by skin
  source almond:   a low-saturation blob (grey sclera, iris, black pupil) ringed by saturated skin - in ANY image of
                   any size: an image-model repaint, or another painting / book cover / photo whose eyes you want
                   exactly (a 45 px source eye is enough for a ~76 px texture eye)
The eyes are paired left-left, right-right by x.
Both outlines are resampled at --n points by angle round their centroids and paired; a thin-plate spline from the
original's pixels to the source's (outlines + centroids) samples the source eye INTO the original almond, grown by
--grow px and feathered, so the lids of the original stay where they are.

  eye_transplant.py --orig portrait.png --src repaint_or_reference.png --out portrait_eyes.png [--n 32] [--grow 2]
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import RBFInterpolator

ap = argparse.ArgumentParser()
ap.add_argument("--orig", required=True); ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--n", type=int, default=32); ap.add_argument("--grow", type=int, default=2)
ap.add_argument("--sat", type=float, default=0.40, help="max HSV saturation inside a source eye (shaded sclera ~0.3)")
ap.add_argument("--skin-sat", type=float, default=0.42, help="min median saturation round a source eye (skin)")
a = ap.parse_args()

O = np.asarray(Image.open(a.orig).convert("RGB")).astype(np.float32)
C = np.asarray(Image.open(a.src).convert("RGB")).astype(np.float32)          # any size: the eyes are found in it
H, W = O.shape[:2]
LO = O @ np.array([0.3, 0.59, 0.11], np.float32)

def eyes_orig():
    eye = ndimage.binary_fill_holes(ndimage.binary_closing(LO < 0.14*255, iterations=3))
    lab, n = ndimage.label(eye); sizes = ndimage.sum(eye, lab, range(1, n + 1)); out = []
    for k in np.argsort(sizes)[::-1] + 1:
        m = lab == k; ring = ndimage.binary_dilation(m, iterations=12) & ~ndimage.binary_dilation(m, iterations=4)
        if np.median(LO[ring]) > 85 and m.sum() > 500: out.append(m)
        if len(out) == 2: break
    return out

def outline(m):
    e = m & ~ndimage.binary_erosion(m); r, c = np.where(e); return np.c_[c, r].astype(float)
def by_angle(P, n):
    c = P.mean(0); th = np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0]); res = []
    for t in np.linspace(-np.pi, np.pi, n, endpoint=False):
        d = np.abs(np.angle(np.exp(1j*(th - t)))); near = d < np.pi/n
        cand = P[near] if near.any() else P[[np.argmin(d)]]
        res.append(cand[np.argmax(np.hypot(*(cand - c).T))])
    return np.array(res), c

def eyes_src(C):
    """the source's two eyes: low-saturation blobs (grey sclera, iris, black pupil) ringed by saturated skin, sorted by x"""
    Hs, Ws = C.shape[:2]; mx, mn = C.max(2), C.min(2); sat = (mx - mn)/np.maximum(mx, 1)
    low = ndimage.binary_opening(sat < a.sat, iterations=1)             # holes are filled PER BLOB below: a grey frame
    lab, n = ndimage.label(low); sizes = ndimage.sum(low, lab, range(1, n + 1))   # round a picture would fill everything
    r1, r2 = max(3, int(0.012*Ws)), max(1, int(0.004*Ws)); out = []
    for k in np.argsort(sizes)[::-1][:12] + 1:
        m = lab == k
        if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any() or sizes[k - 1] < 1e-4*Hs*Ws: continue
        m = ndimage.binary_fill_holes(m)                                   # the pupil / glint inside
        ring = ndimage.binary_dilation(m, iterations=r1) & ~ndimage.binary_dilation(m, iterations=r2)
        if np.median(sat[ring]) > a.skin_sat: out.append(m)
        if len(out) == 2: break
    return sorted(out, key=lambda m: np.where(m)[1].mean())

out = O.copy()
EO = sorted(eyes_orig(), key=lambda m: np.where(m)[1].mean()); ES = eyes_src(C)
assert len(EO) == 2 and len(ES) == 2, f"found {len(EO)} eyes in the original, {len(ES)} in the source"
for m, cm in zip(EO, ES):
    Po, co = by_angle(outline(m), a.n); Pc, cc = by_angle(outline(cm), a.n)
    tps = RBFInterpolator(np.vstack([Po, co]), np.vstack([Pc, cc]), kernel="thin_plate_spline", smoothing=1.0)
    grow = ndimage.binary_dilation(m, iterations=a.grow)
    r, c = np.where(grow); q = tps(np.c_[c, r].astype(float))
    samp = np.stack([ndimage.map_coordinates(C[..., ch], [q[:, 1], q[:, 0]], order=3, mode='nearest') for ch in range(3)], -1)
    w = np.clip(ndimage.distance_transform_edt(grow)/2.5, 0, 1)[r, c][:, None]
    out[r, c] = out[r, c]*(1 - w) + samp*w
    print(f"   eye at ({co[0]:.0f}, {co[1]:.0f}): original {np.ptp(Po[:, 0]):.0f} x {np.ptp(Po[:, 1]):.0f} px <- source "
          f"{np.ptp(Pc[:, 0]):.0f} x {np.ptp(Pc[:, 1]):.0f} px at ({cc[0]:.0f}, {cc[1]:.0f})")
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out); print(f"-> {a.out}")
