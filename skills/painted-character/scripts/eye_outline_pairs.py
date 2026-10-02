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

Tracing the sculpted rim (what works): a depth map of the DENSE sculpt (--trace-mesh, --step 0.002); |grad z| minus its
gaussian blur (a top-hat) turns the lid edges into thin lines; the region they enclose round --eye is a guide only -
360 rays from its centre find the strongest line just outside its edge (--rim-window), the peak refined by a
parabola, then a median (9 rays) and a gaussian (--rim-smooth) along the rim. A GEOMETRIC almond is fitted to that
ridge (pointed corners, each lid t(1-t)(c0 + c1 t + c2 t^2) over the corner chord); read the corners off --debug where
the rim lines meet and pass --corners. Knobs: --grow (whole almond), --upper/--lower (one lid, corners fixed), --inset.

  eye_outline_pairs.py --mesh MESH.ply --trace-mesh DENSE.ply --step 0.002 --img portrait.png --img-lm img.json
                       --mesh-lm mesh.json --scale 0.95 --base face_morph.json --out face_morph_eyes.json
                       --eye 0.45,17.6 --corners 0.075,17.425,0.735,17.835 --inset 0 --corner-in 0 --debug d.png
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
ap.add_argument("--inset", type=float, default=0.012, help="the geometric almond sits this far INSIDE the sculpted rim (units)")
ap.add_argument("--corner-in", type=float, default=0.02, help="and its corners this fraction of the eye length inside")
ap.add_argument("--grow", type=float, default=1.0, help="scale the geometric almond about its centre (moves the corners too)")
ap.add_argument("--upper", type=float, default=1.0, help="scale the upper lid's height over the corner-to-corner chord (corners stay)")
ap.add_argument("--lower", type=float, default=1.0, help="the same for the lower lid")
ap.add_argument("--rim", default="ridge", choices=["ridge", "region"], help="trace the rim LINE (ridge) or the enclosed region's edge")
ap.add_argument("--rim-window", type=float, default=0.05, help="how far outside the region's edge to look for the crest (units)")
ap.add_argument("--trace-mesh", help="trace the rim on this (denser) mesh instead of --mesh - same shape, finer rim")
ap.add_argument("--rim-smooth", type=float, default=3.0, help="gaussian smoothing of the rim radius along the rays (rays)")
ap.add_argument("--corners", help="x,y,x,y: the almond's inner and outer TIPS, read off the --debug picture (the rim lines' "
                                   "meeting points) - the automatic walk stops short or overshoots where the rim smears")
ap.add_argument("--sigma", type=float, default=0.03)
ap.add_argument("--close", type=int, default=3, help="px of closing on the rim lines before the region fill - raise it if a gap in the rim lets the region leak")
ap.add_argument("--paint-ply", help="take the target almond from the DARK eye paint of this SculptGL PLY (same frame) instead of the traced rim - eyes placed by hand while sculpting with the texture on)")
ap.add_argument("--paint-dark", type=float, default=8.0, help="max luminance of the eye paint (SculptGL linear bytes: eye ~0, skin ~40)")
ap.add_argument("--debug")
a = ap.parse_args()
ex, ey = (float(c) for c in a.eye.split(","))

# ---- the sculpted almond: front depth map, local depression ----
m = read_mesh(a.trace_mesh or a.mesh); m = trimesh.Trimesh(m.vertices, m.faces, process=False)
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
    rim = ndimage.binary_closing(th_ > t, iterations=a.close)
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
def fit_almond(P, inset, corner_in):
    """a clean GEOMETRIC almond fitted to a traced outline (a traced outline follows every bump of the sculpt, and
    paint morphed onto it comes out squiggly): the two corners = the outline's farthest pair; each lid =
    its offset from the corner-to-corner chord, d(t) = t(1-t)(c0 + c1 t + c2 t^2) - zero at both corners (pointed), smooth, a
    little asymmetric allowed - least squares to that lid's points. Then pulled INSIDE the rim: each lid by `inset`
    units, the corners by `corner_in` of the length. Returns a dense closed outline."""
    D = np.hypot(*(P[:, None] - P[None]).transpose(2, 0, 1)); i, j = np.unravel_index(np.argmax(D), D.shape)
    A_, B_ = (P[i], P[j]) if P[i, 0] < P[j, 0] else (P[j], P[i])
    # the traced region stops where the closing sealed the rim, short of the real tips: walk each corner outward along
    # the chord while there is still RIM (th_ > 0.03) on BOTH sides of the path - i.e. still between the two lids;
    # where they have met, stop (one-sided checks walked the inner corner on into the nose's slopes)
    u0 = (B_ - A_)/np.hypot(*(B_ - A_)); n0 = np.array([-u0[1], u0[0]])
    ry, rx = np.where(th_ > 0.03); R_ = np.c_[xs[rx], ys[ry]]
    def tip(c, d):
        last = c
        for s_ in np.arange(a.step, 0.15, a.step):
            q = c + d*s_; near = R_[np.hypot(*(R_ - q).T) < 0.03]
            off = (near - q) @ n0
            qi = int(round((q[1] - ys[0])/a.step)); qj = int(round((q[0] - xs[0])/a.step))
            gap = 0 <= qi < th_.shape[0] and 0 <= qj < th_.shape[1] and th_[qi, qj] < 0.03    # q still in the dark gap
            if gap and (off > 0.004).any() and (off < -0.004).any(): last = q
            else: break
        return last
    A_, B_ = tip(A_, -u0), tip(B_, u0)
    if a.corners:
        c_ = [float(v) for v in a.corners.split(",")]; A_, B_ = np.array(c_[:2]), np.array(c_[2:])
    Lc = np.hypot(*(B_ - A_)); u = (B_ - A_)/Lc; nrm = np.array([-u[1], u[0]])
    t = (P - A_) @ u/Lc; d = (P - A_) @ nrm
    keep = (t > 0.03) & (t < 0.97); tt = np.linspace(0, 1, 160); lids = []
    for side in (1, -1):
        sel = keep & (np.sign(d) == side)
        ts_ = t[sel]; X = np.c_[ts_*(1 - ts_), ts_**2*(1 - ts_), ts_**3*(1 - ts_)]
        coef = np.linalg.lstsq(X, np.abs(d[sel]), rcond=None)[0]
        dd = np.clip(tt*(1 - tt)*(coef[0] + coef[1]*tt + coef[2]*tt**2) - inset*np.sqrt(np.clip(tt*(1 - tt)*4, 0, 1)), 0, None)
        lids.append(side*dd*(a.upper if side > 0 else a.lower))     # side +1 = the upper lid (the chord's normal points up)
    ts = corner_in + tt*(1 - 2*corner_in)                              # corners pulled in along the chord
    up = A_ + np.outer(ts*Lc, u) + np.outer(lids[0], nrm); lo = A_ + np.outer(ts*Lc, u) + np.outer(lids[1], nrm)
    return np.vstack([up, lo[::-1][1:-1]])
S_raw = outline_pts(almond, xs, ys)
if a.rim == "ridge":
    # the region's edge sits inside the rim and is jagged; follow the rim LINE itself: from the almond's centre, 360
    # rays; along each, the strongest top-hat slope in a window just outside the region's edge (the lid's crest)
    cy_, cx_ = [v.mean() for v in np.where(almond)]; C0 = np.array([xs[0] + cx_*a.step, ys[0] + cy_*a.step])
    rr = np.arange(0.02, 0.6, a.step/2); ridge = []
    for th in np.linspace(-np.pi, np.pi, 360, endpoint=False):
        q = C0 + np.outer(rr, [np.cos(th), np.sin(th)])
        rows, cols = (q[:, 1] - ys[0])/a.step, (q[:, 0] - xs[0])/a.step
        inside = ndimage.map_coordinates(almond.astype(float), [rows, cols], order=0, mode="constant") > 0.5
        if not inside.any(): continue
        r_in = rr[np.where(inside)[0].max()]
        w = (rr > r_in - 0.01) & (rr < r_in + a.rim_window)
        prof = ndimage.map_coordinates(th_, [rows, cols], order=1, mode="constant")
        if not (w.any() and prof[w].max() > 0.05): ridge.append((th, np.nan)); continue
        iw = np.where(w)[0]; k = iw[np.argmax(prof[w])]
        if 0 < k < len(rr) - 1:                                          # sub-sample peak (parabola through 3 samples)
            y0_, y1_, y2_ = prof[k - 1], prof[k], prof[k + 1]; den = y0_ - 2*y1_ + y2_
            off = 0.5*(y0_ - y2_)/den if den < 0 else 0.0
        else: off = 0.0
        ridge.append((th, rr[k] + off*(rr[1] - rr[0])))
    ang, rad = np.array(ridge).T; ok = ~np.isnan(rad)
    rad = np.interp(ang, ang[ok], rad[ok], period=2*np.pi)              # fill the misses round the circle
    rad = ndimage.median_filter(rad, size=9, mode="wrap")               # drop single-ray outliers
    rad = ndimage.gaussian_filter1d(rad, a.rim_smooth, mode="wrap")     # smooth along the rim
    S_raw = C0 + np.c_[rad*np.cos(ang), rad*np.sin(ang)]
    print(f"   rim ridge: {int(ok.sum())} of 360 rays found the lid crest (median 9 + gaussian {a.rim_smooth} rays)")
S_model = fit_almond(S_raw, a.inset, a.corner_in)
S_model = S_model.mean(0) + a.grow*(S_model - S_model.mean(0))
if a.paint_ply:                                                         # the hand-placed paint wins over the trace
    pm = read_mesh(a.paint_ply); PV = pm.vertices; PC = pm.visual.vertex_colors[:, :3].astype(float)
    Lp = PC @ np.array([0.3, 0.59, 0.11]); fr = pm.vertex_normals[:, 2] > 0
    sel = fr & (PV[:, 0] > 0) & (np.abs(PV[:, 1] - ey) < 0.55) & (Lp < a.paint_dark)
    ci_ = np.round((PV[sel, 1] - ys[0])/a.step).astype(int); cj_ = np.round((PV[sel, 0] - xs[0])/a.step).astype(int)
    ok_ = (ci_ >= 0) & (ci_ < len(ys)) & (cj_ >= 0) & (cj_ < len(xs))
    pmask = np.zeros((len(ys), len(xs)), bool); pmask[ci_[ok_], cj_[ok_]] = True
    pmask = ndimage.binary_fill_holes(ndimage.binary_closing(ndimage.binary_dilation(pmask, iterations=2), iterations=3))
    labp, nlp = ndimage.label(pmask); pmask = labp == (np.argmax(ndimage.sum(pmask, labp, range(1, nlp + 1))) + 1)
    pmask = ndimage.binary_erosion(pmask, iterations=2)                 # undo the dilation
    Pp = outline_pts(pmask, xs, ys); cpp = Pp.mean(0)
    thp = np.arctan2(Pp[:, 1] - cpp[1], Pp[:, 0] - cpp[0]); o = np.argsort(thp)
    rp = ndimage.gaussian_filter1d(np.hypot(*(Pp[o] - cpp).T), 2, mode="wrap")
    S_model = cpp + np.c_[rp*np.cos(thp[o]), rp*np.sin(thp[o])]
    print(f"   target almond = the eye PAINT of {Path(a.paint_ply).name}: {int(sel.sum())} dark verts, "
          f"{np.ptp(S_model[:, 0]):.3f} x {np.ptp(S_model[:, 1]):.3f} at ({cpp[0]:.3f}, {cpp[1]:.3f})")
S_out, S_c = by_angle(S_model, a.n)

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
    ax.imshow(np.clip(dep, 0, 1.5), extent=[xs[0], xs[-1], ys[0], ys[-1]], origin="lower", cmap="gray")
    ax.plot(*S_raw.T, ".", ms=2, color="orange", label=f"traced rim ({a.rim})")
    ax.plot(*np.vstack([S_out, S_out[:1]]).T, "c.-", label="geometric almond, inside the rim")
    ax.plot(*np.vstack([P_out, P_out[:1]]).T, "m.-", label="painted almond (imprint frame)")
    for s_, p_ in zip(S_out, P_out): ax.annotate("", p_, s_, arrowprops=dict(arrowstyle="->", color="y", lw=0.8))
    ax.legend(); ax.set_title("right eye: sculpt -> paint pairs"); fig.tight_layout(); fig.savefig(a.debug, dpi=80)
