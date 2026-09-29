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
                    [--src-dark 0.22] [--black 4]   # dark source eyes on a grey canvas

--whole: bend the WHOLE source image into the original's frame instead of pasting only its eyes - both eye outlines
(paired by angle) + centroids, the mouth line (the darkest row below the nostrils, ~0.85-1.2 x the eye distance under
the eyes, and its corners), the head outline above the eyes and the image border are pinned; one thin-plate spline.
Use it to take a whole repainted face (e.g. an image-model repaint of the portrait) into the portrait's frame.
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import RBFInterpolator

ap = argparse.ArgumentParser()
ap.add_argument("--orig", required=True); ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--n", type=int, default=32); ap.add_argument("--grow", type=int, default=2)
ap.add_argument("--whole", action="store_true", help="bend the WHOLE source image into the original's frame (eyes, head "
                "outline and the image edges pinned), not just its eyes")
ap.add_argument("--sat", type=float, default=0.40, help="max HSV saturation inside a source eye (shaded sclera ~0.3)")
ap.add_argument("--skin-sat", type=float, default=0.42, help="min median saturation round a source eye (skin)")
ap.add_argument("--black", type=float, help="levels each pasted eye so its 30th-percentile luminance lands here (a uniform subtract, so detail inside keeps its contrast) - a print's dark-grey eye becomes black")
ap.add_argument("--src-dark", type=float, help="find the source eyes as DARK blobs (luminance < this x 255) instead of unsaturated ones - for black/dark eyes on a grey canvas, which is as unsaturated as the eyes")
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
    L = C @ np.array([0.3, 0.59, 0.11], np.float32)
    low = ndimage.binary_opening((L < a.src_dark*255) if a.src_dark else (sat < a.sat), iterations=1)   # holes are filled
                                                                        # PER BLOB below: a grey frame
    lab, n = ndimage.label(low); sizes = ndimage.sum(low, lab, range(1, n + 1))   # round a cover would fill everything
    r1, r2 = max(3, int(0.012*Ws)), max(1, int(0.004*Ws)); out = []
    for k in np.argsort(sizes)[::-1][:12] + 1:
        m = lab == k
        if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any() or sizes[k - 1] < 1e-4*Hs*Ws: continue
        m = ndimage.binary_fill_holes(m)                                   # the pupil / glint inside
        ring = ndimage.binary_dilation(m, iterations=r1) & ~ndimage.binary_dilation(m, iterations=r2)
        if np.median(sat[ring]) > a.skin_sat: out.append(m)
        if len(out) == 2: break
    return sorted(out, key=lambda m: np.where(m)[1].mean())

def head_outline(img, n):
    """the head's outline above the eyes' level (skin = saturated + bright), by angle round the eyes' midpoint"""
    mx, mn = img.max(2), img.min(2); sat = (mx - mn)/np.maximum(mx, 1); L = img @ np.array([0.3, 0.59, 0.11], np.float32)
    skin = ndimage.binary_opening((sat > a.skin_sat) & (L > 60), iterations=2)
    lab, k = ndimage.label(skin); skin = lab == (np.argmax(ndimage.sum(skin, lab, range(1, k + 1))) + 1)
    return ndimage.binary_fill_holes(skin)

out = O.copy()
EO = sorted(eyes_orig(), key=lambda m: np.where(m)[1].mean()); ES = eyes_src(C)
assert len(EO) == 2 and len(ES) == 2, f"found {len(EO)} eyes in the original, {len(ES)} in the source"
for m, cm in zip(EO, ES):
    Po, co = by_angle(outline(m), a.n); Pc, cc = by_angle(outline(cm), a.n)
    tps = RBFInterpolator(np.vstack([Po, co]), np.vstack([Pc, cc]), kernel="thin_plate_spline", smoothing=1.0)
    grow = ndimage.binary_dilation(m, iterations=a.grow)
    r, c = np.where(grow); q = tps(np.c_[c, r].astype(float))
    samp = np.stack([ndimage.map_coordinates(C[..., ch], [q[:, 1], q[:, 0]], order=3, mode='nearest') for ch in range(3)], -1)
    if a.black is not None:
        Ls = samp @ np.array([0.3, 0.59, 0.11], np.float32); shift = np.percentile(Ls, 30) - a.black
        samp = np.clip(samp - max(shift, 0.0), 0, 255)
    w = np.clip(ndimage.distance_transform_edt(grow)/2.5, 0, 1)[r, c][:, None]
    out[r, c] = out[r, c]*(1 - w) + samp*w
    print(f"   eye at ({co[0]:.0f}, {co[1]:.0f}): original {np.ptp(Po[:, 0]):.0f} x {np.ptp(Po[:, 1]):.0f} px <- source "
          f"{np.ptp(Pc[:, 0]):.0f} x {np.ptp(Pc[:, 1]):.0f} px at ({cc[0]:.0f}, {cc[1]:.0f})")
if a.whole:
    # one spline for the whole picture: both eyes' outlines + centroids, the head outline above the mouth (by angle
    # round the eyes' midpoint), and the image border pinned proportionally
    src_pts, dst_pts = [], []
    for m, cm in zip(EO, ES):
        Po, co = by_angle(outline(m), a.n); Pc, cc = by_angle(outline(cm), a.n)
        src_pts += [Po, co[None]]; dst_pts += [Pc, cc[None]]
    mid_o = np.mean([np.array(np.where(m))[::-1].mean(1) for m in EO], 0)
    mid_c = np.mean([np.array(np.where(m))[::-1].mean(1) for m in ES], 0)
    def head_pts(img, mid):
        hm = head_outline(img, a.n); e = hm & ~ndimage.binary_erosion(hm); r_, c_ = np.where(e); P = np.c_[c_, r_].astype(float)
        th = np.arctan2(P[:, 1] - mid[1], P[:, 0] - mid[0]); res = []
        for t in np.linspace(-np.pi + 0.35, -0.35, 13):                  # upper half (image y down), clear of the neck
            d = np.abs(np.angle(np.exp(1j*(th - t)))); near = d < 0.08
            if near.any(): cand = P[near]; res.append(cand[np.argmax(np.hypot(*(cand - mid).T))])
            else: res.append([np.nan, np.nan])
        return np.array(res)
    def mouth_pts(img, mid, iod):
        """the mouth line: the darkest row of a central band below the eyes, and its corners (where the dip fades)"""
        Li = ndimage.gaussian_filter(img @ np.array([0.3, 0.59, 0.11], np.float32), 2)
        x0, x1 = int(mid[0] - 0.1*iod), int(mid[0] + 0.1*iod)
        r0, r1 = int(mid[1] + 0.85*iod), int(mid[1] + 1.2*iod)              # below the nostrils (~0.7 x the eye distance)
        prof = Li[r0:r1, x0:x1].mean(1); row = r0 + int(np.argmin(prof))
        dip = (Li[row - 12] + Li[row + 12])/2 - Li[row]                  # darker than 12 px above/below
        xs_ = np.arange(img.shape[1]); dark = (dip > 0.35*dip[x0:x1].mean()) & (np.abs(xs_ - mid[0]) < 0.5*iod)
        lab_, _ = ndimage.label(dark); k_ = lab_[int(mid[0])]
        seg = np.where(lab_ == k_)[0] if k_ else np.array([int(mid[0])])
        return np.array([[mid[0], row], [seg.min(), row], [seg.max(), row]], float)
    iod = lambda E: abs(np.subtract(*[np.where(m)[1].mean() for m in E]))    # distance between the eye centres
    Mo, Mc = mouth_pts(O, mid_o, iod(EO)), mouth_pts(C, mid_c, iod(ES))
    print(f"   mouth: original row {Mo[0, 1]:.0f} x {Mo[1, 0]:.0f}..{Mo[2, 0]:.0f}  <- source row {Mc[0, 1]:.0f} x {Mc[1, 0]:.0f}..{Mc[2, 0]:.0f}")
    src_pts.append(Mo); dst_pts.append(Mc)
    Ho, Hc = head_pts(O, mid_o), head_pts(C, mid_c); ok = ~(np.isnan(Ho).any(1) | np.isnan(Hc).any(1))
    src_pts.append(Ho[ok]); dst_pts.append(Hc[ok])
    Hs, Ws = C.shape[:2]; bx = np.linspace(0, W - 1, 6); by = np.linspace(0, H - 1, 8)
    border = np.array([(x, 0) for x in bx] + [(x, H - 1) for x in bx] + [(0, y) for y in by] + [(W - 1, y) for y in by], float)
    src_pts.append(border); dst_pts.append(border*[(Ws - 1)/(W - 1), (Hs - 1)/(H - 1)])
    S_, D_ = np.vstack(src_pts), np.vstack(dst_pts)
    tps = RBFInterpolator(S_, D_, kernel="thin_plate_spline", smoothing=5.0)
    st = 4; gy, gx = np.mgrid[0:H:st, 0:W:st]; q = tps(np.c_[gx.ravel(), gy.ravel()]).reshape(gy.shape + (2,))
    qx = ndimage.zoom(q[..., 0], (H/gy.shape[0], W/gy.shape[1]), order=1)[:H, :W]
    qy = ndimage.zoom(q[..., 1], (H/gy.shape[0], W/gy.shape[1]), order=1)[:H, :W]
    out = np.stack([ndimage.map_coordinates(C[..., ch], [qy, qx], order=3, mode="nearest") for ch in range(3)], -1)
    print(f"   whole: {len(S_)} pinned points ({int(ok.sum())} on the head outline); the source now sits in the original's frame")
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out); print(f"-> {a.out}")
