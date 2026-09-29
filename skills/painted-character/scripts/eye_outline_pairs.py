#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow","rtree","shapely","matplotlib"]
# ///
"""eye_outline_pairs.py - morph pairs that put the painted eye's OUTLINE on the sculpted eye's outline.

Five hand-read points per eye (in a --base morph JSON) get the eye's centre and size, not its shape - the painted
eye edge then misses the sculpted rim. This reads both outlines and pairs them densely:

  sculpted: a front depth map of the head (rays along -z on a --step grid); its slope, top-hatted (minus a --sigma
            smoothed copy), shows the almond's rim as a thin line; the almond = the region it encloses round --eye.
  painted:  the portrait's black eye (luminance < 0.14, holes filled), mapped into mesh x/y by the imprint frame
            (the same --img-lm/--mesh-lm/--scale face_paint_front.py uses).
Both outlines are resampled at --n points by angle round their own centroid and paired sculpt -> paint (right eye,
mirrored by the consumer). The other pairs (nose, mouth, chin) and the anchors are copied from --base.

  eye_outline_pairs.py --mesh MESH.ply --img portrait.png --img-lm img.json --mesh-lm mesh.json --scale 0.95
                       --base face_morph.json --out face_morph_eyes.json [--eye 0.45,17.62] [--n 24] [--debug d.png]
"""
import argparse, json, sys
from pathlib import Path
import numpy as np, trimesh
from PIL import Image
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh

ap = argparse.ArgumentParser()
ap.add_argument("--mesh", required=True); ap.add_argument("--img", required=True)
ap.add_argument("--img-lm", required=True); ap.add_argument("--mesh-lm", required=True); ap.add_argument("--scale", type=float, default=1.0)
ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--eye", default="0.45,17.62", help="x,y inside the RIGHT sculpted eye (x > 0)")
ap.add_argument("--n", type=int, default=24); ap.add_argument("--step", type=float, default=0.004)
ap.add_argument("--sigma", type=float, default=0.03)
ap.add_argument("--debug")
a = ap.parse_args()
ex, ey = (float(c) for c in a.eye.split(","))

# ---- the sculpted almond: front depth map, local depression ----
m = read_mesh(a.mesh); m = trimesh.Trimesh(m.vertices, m.faces, process=False)
xs = np.arange(0.0, 1.0, a.step); ys = np.arange(ey - 0.55, ey + 0.55, a.step)            # right half of the face
X, Y = np.meshgrid(xs, ys)
org = np.c_[X.ravel(), Y.ravel(), np.full(X.size, m.vertices[:, 2].max() + 1)]
loc, ri, _ = m.ray.intersects_location(org, np.tile([0, 0, -1.0], (X.size, 1)), multiple_hits=False)
D = np.full(X.size, np.nan); D[ri] = loc[:, 2]; D = D.reshape(X.shape)
valid = ~np.isnan(D); Df = np.where(valid, D, np.nanmin(D))
# the almond's RIM is a thin line of steep slope (the eye floor is a low dome, not a depression): top-hat the slope
# (slope minus its smoothed self) -> the rim lines; the almond = the region they enclose round the eye centre. The
# threshold is the lowest that keeps that region closed (not touching the grid edge) and of a sane size.
gy, gx = np.gradient(Df, a.step); G = np.hypot(gx, gy)*valid
th_ = G - ndimage.gaussian_filter(G, a.sigma/a.step)
ci, cj = np.argmin(np.abs(ys - ey)), np.argmin(np.abs(xs - ex))
almond = None
for t in (0.03, 0.05, 0.08, 0.12, 0.2, 0.3):
    rim = ndimage.binary_closing(th_ > t, iterations=3)
    lab, _ = ndimage.label(~rim & valid); k = lab[ci, cj]
    if k == 0: continue
    reg = lab == k; area = reg.sum()*a.step**2
    touches = reg[0].any() or reg[-1].any() or reg[:, 0].any() or reg[:, -1].any()
    if not touches and 0.05 < area < 0.6:
        almond = ndimage.binary_fill_holes(ndimage.binary_dilation(reg, iterations=2)); print(f"   rim threshold {t}: almond {area:.3f} units^2"); break
if almond is None: sys.exit("no closed rim round the eye centre - check --eye / --sigma (see --debug)")
dep = th_

def outline_pts(mask, px, py):
    """boundary pixels of mask -> x/y points (px, py: the pixel -> coordinate arrays)"""
    edge = mask & ~ndimage.binary_erosion(mask)
    r, c = np.where(edge); return np.c_[px[c], py[r]]
def by_angle(P, n):
    c = P.mean(0); th = np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0])
    q = np.linspace(-np.pi, np.pi, n, endpoint=False); out = []
    for t in q:                                                       # the farthest outline point near each angle
        d = np.abs(np.angle(np.exp(1j*(th - t)))); near = d < (np.pi/n)
        cand = P[near] if near.any() else P[[np.argmin(d)]]
        out.append(cand[np.argmax(np.hypot(*(cand - c).T))])
    return np.array(out), c
S_out, S_c = by_angle(outline_pts(almond, xs, ys), a.n)

# ---- the painted almond, in mesh x/y (the imprint frame) ----
IL, ML = json.load(open(a.img_lm)), json.load(open(a.mesh_lm))
P = np.asarray(Image.open(a.img).convert("RGB")).astype(np.float32); L = P @ np.array([0.3, 0.59, 0.11], np.float32)
eye = ndimage.binary_fill_holes(ndimage.binary_closing(L < 0.14*255, iterations=3))
lab2, n2 = ndimage.label(eye); sizes = ndimage.sum(eye, lab2, range(1, n2 + 1))
u_mid = IL["crown"][0]; cands = []
for kk in np.argsort(sizes)[::-1][:6] + 1:                            # the right-hand (image-right) eye, ringed by skin
    mk = lab2 == kk; rr, cc = np.where(mk)
    ring = ndimage.binary_dilation(mk, iterations=12) & ~ndimage.binary_dilation(mk, iterations=4)
    if cc.mean() > u_mid and np.median(L[ring]) > 85: cands.append(kk)
eyeR = lab2 == cands[0]
v_cr, v_ch, hw_px = IL["crown"][1], IL["chin"][1], IL["half_width"]
crown_y, chin_y, hw_m = ML["crown_y"], ML["chin_y"], ML["half_width"]
sy = (crown_y - chin_y)/(v_ch - v_cr); sx = hw_m/hw_px
anc = [u_mid, (IL["nose"][1] + IL["mouth"][1])/2]
A = np.array([(anc[0] - u_mid)*sx, crown_y - (anc[1] - v_cr)*sy])
def img2mesh(u, v):
    b = np.c_[(u - u_mid)*sx, crown_y - (v - v_cr)*sy]; return A + a.scale*(b - A)
pu = np.arange(P.shape[1], dtype=float); pv = np.arange(P.shape[0], dtype=float)
edge = eyeR & ~ndimage.binary_erosion(eyeR); r, c = np.where(edge)
P_out, P_c = by_angle(img2mesh(pu[c], pv[r]), a.n)

base = json.load(open(a.base))
keep = [(s_, p_) for s_, p_ in zip(base["sculpt"], base["paint"]) if s_[1] < 17.25]              # nose/mouth/chin
out = {"comment": f"eye_outline_pairs.py: {a.n} paired outline points per eye (sculpted almond from a front depth map, "
                  f"painted almond from {Path(a.img).name} in the imprint frame) + the non-eye pairs of {Path(a.base).name}",
       "mirror_x": True,
       "sculpt": [list(map(float, p)) for p in S_out] + [s_ for s_, _ in keep],
       "paint":  [list(map(float, p)) for p in P_out] + [p_ for _, p_ in keep],
       "anchors": base.get("anchors", [])}
json.dump(out, open(a.out, "w"), indent=1)
sw, sh = np.ptp(S_out, 0); pw, ph = np.ptp(P_out, 0)
print(f"-> {a.out}: sculpted almond {sw:.3f} x {sh:.3f} at ({S_c[0]:.3f}, {S_c[1]:.3f}); painted {pw:.3f} x {ph:.3f} at "
      f"({P_c[0]:.3f}, {P_c[1]:.3f}); {len(keep)} other pairs kept")
if a.debug:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(np.clip(dep, 0, 3), extent=[xs[0], xs[-1], ys[0], ys[-1]], origin="lower", cmap="gray")
    ax.plot(*np.vstack([S_out, S_out[:1]]).T, "c.-", label="sculpted almond")
    ax.plot(*np.vstack([P_out, P_out[:1]]).T, "m.-", label="painted almond (imprint frame)")
    for s_, p_ in zip(S_out, P_out): ax.annotate("", p_, s_, arrowprops=dict(arrowstyle="->", color="y", lw=0.8))
    ax.legend(); ax.set_title("right eye: sculpt -> paint pairs"); fig.tight_layout(); fig.savefig(a.debug, dpi=80)
