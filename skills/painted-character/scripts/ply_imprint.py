#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow"]
# ///
"""ply_imprint.py - imprint a PAINTED front portrait (not a generated height map) on a SculptGL head, as relief.

For "this exact face": an image model asked for a height map draws a NEW face from a description, so it can't be
exact; this reads the painting itself:

  1. FRAME: the painting's head (crown, chin, half-width at the eye row, midline) is fitted onto the mesh's head
     (crown_y, chin_y, half-width, x = 0): an anisotropic scale, so the painting's layout lands where it is drawn.
  2. MORPH (--morph 0..1): the mesh's own features (eye corners/top/bottom/centre, nose tip, mouth corner, chin -
     --mesh-lm, right side, mirrored) are moved in x/y toward the painting's (in that frame) by a thin-plate spline on
     the front of the head, so the sculpted eyes/nose/mouth coincide with the painted ones and the relief doesn't
     double them. 0 = keep the sculpt's layout (the relief then lands at the painting's positions regardless).
  3. HEIGHT from the painting: the black eyes (luminance < --eye-t, holes/highlights filled) become an almond recess
     (--eye-depth) with a low convex dome inside; everything else is band-passed luminance (light = raised, dark =
     recessed: nose ridge, nostrils, mouth line, lid rims, cheek hollows), normalised by its spread on the head.
     This is shading read as height - a known approximation (a lit forehead reads as a bulge), so the low
     frequencies are left out and the relief is shallow (--relief, --form).
  4. DISPLACE along the vertex normal, weighted by how squarely the vertex faces the front (smoothstep of normal z)
     and faded out below the chin. Colours and vertex order are kept; faces untouched.

  ply_imprint.py --in mesh.ply --img painting.png --out out.ply --img-lm img.json --mesh-lm mesh.json
                 [--morph 1.0] [--eye-depth 0.05] [--relief 0.006] [--form 0.012] [--smooth 4] [--scale 1.0]
                 [--anchor u,v] [--debug dir]
img.json (pixels): {"crown": [u, v], "chin": [u, v], "half_width": px, "nose": [u, v], "mouth": [u, v]} (+ optional
  "eye": {"inner", "outer", "top", "bottom", "centre"} for the RIGHT eye, image right; else found from the black)
mesh.json (front x/y, right side x > 0): {"crown_y", "chin_y", "half_width", "eye": {...}, "nose", "mouth", "chin"}
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import RBFInterpolator
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh, write_sculptgl

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--img", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--img-lm", required=True); ap.add_argument("--mesh-lm", required=True)
ap.add_argument("--morph", type=float, default=1.0); ap.add_argument("--eye-depth", type=float, default=0.05)
ap.add_argument("--relief", type=float, default=0.006); ap.add_argument("--form", type=float, default=0.012)
ap.add_argument("--eye-t", type=float, default=0.14); ap.add_argument("--smooth", type=int, default=4)
ap.add_argument("--scale", type=float, default=1.0, help="face size vs the head (1.2 = the painted face 20%% bigger)")
ap.add_argument("--paint-eyes", help="r,g,b: also paint the painting's eyes (a preview of their size)")
ap.add_argument("--anchor", help="u,v px the --scale grows from (default: between the nose tip and the mouth)")
ap.add_argument("--debug")
a = ap.parse_args()
IL, ML = json.load(open(a.img_lm)), json.load(open(a.mesh_lm))

# ---- the painting ----
rgb = np.asarray(Image.open(a.img).convert("RGB")).astype(np.float32)/255
L = rgb @ np.array([0.3, 0.59, 0.11], np.float32); H, W = L.shape
u_mid = IL["crown"][0]; v_cr, v_ch = IL["crown"][1], IL["chin"][1]; hw_px = IL["half_width"]
uu, vv = np.meshgrid(np.arange(W), np.arange(H))
head_img = ((uu - u_mid)/hw_px)**2 + ((vv - (v_cr + v_ch)/2)/((v_ch - v_cr)/2))**2 < 1.15   # generous ellipse
eye = (L < a.eye_t) & head_img & (vv < IL["nose"][1]) & (np.abs(uu - u_mid) > 0.04*hw_px)
eye = ndimage.binary_closing(eye, iterations=3); eye = ndimage.binary_fill_holes(eye)
lab, n = ndimage.label(eye)
if n > 2:
    keep = np.argsort(ndimage.sum(eye, lab, range(1, n + 1)))[-2:] + 1; eye = np.isin(lab, keep)
if "eye" not in IL:                                                   # the right eye's landmarks from the black
    ys, xs = np.where(eye & (uu > u_mid)); d = xs - u_mid
    i_in, i_out = np.argmin(d), np.argmax(d)
    cx = xs.mean(); col = ys[np.abs(xs - cx) < 1.5]                  # top/bottom = the lids at the centre's column
    IL["eye"] = {"inner": [xs[i_in], ys[i_in]], "outer": [xs[i_out], ys[i_out]], "top": [cx, col.min()],
                 "bottom": [cx, col.max()], "centre": [cx, ys.mean()]}
    print("   painting's right eye (px):", {k: [round(float(c)) for c in v] for k, v in IL["eye"].items()})

# height: eyes = recess + low dome; the rest = band-passed luminance (eyes filled from their surroundings first)
dist_out, (iy, ix) = ndimage.distance_transform_edt(eye, return_indices=True)
Lf = L[iy, ix]                                                        # eye pixels -> nearest skin pixel
s1, s2 = 0.018*2*hw_px, 0.09*2*hw_px
g0, g1, g2 = ndimage.gaussian_filter(Lf, 0.005*2*hw_px), ndimage.gaussian_filter(Lf, s1), ndimage.gaussian_filter(Lf, s2)
face = head_img & ~ndimage.binary_dilation(eye, iterations=int(s1))
def norm(x): return x/max(np.percentile(np.abs(x[face]), 90), 1e-6)
detail, form = norm(g0 - g1), norm(g1 - g2)
e_soft = ndimage.gaussian_filter(eye.astype(np.float32), 0.006*2*hw_px)
dome = np.sqrt(np.clip(dist_out/max(dist_out.max(), 1), 0, 1))
Hmap = (a.relief*np.clip(detail, -3, 3) + a.form*np.clip(form, -3, 3))*(1 - e_soft) - a.eye_depth*e_soft*(1 - 0.35*dome)
Hmap *= ndimage.gaussian_filter(head_img.astype(np.float32), 0.02*2*hw_px)

# ---- the mesh ----
m = read_mesh(a.inp); V = m.vertices.copy(); N = m.vertex_normals
crown_y, chin_y, hw_m = ML["crown_y"], ML["chin_y"], ML["half_width"]
sy = (crown_y - chin_y)/(v_ch - v_cr); sx = hw_m/hw_px
# --scale grows the painted face about the anchor (render a few sizes, e.g. 0.95 / 1.0 / 1.1, and pick): the anchor
# sits between the nose and the mouth by default, so they stay put while the eyes grow up and out.
anc_px = [float(c) for c in a.anchor.split(",")] if a.anchor else [u_mid, (IL["nose"][1] + IL["mouth"][1])/2]
def _base(p): return np.array([(p[0] - u_mid)*sx, crown_y - (p[1] - v_cr)*sy])
A_m = _base(anc_px)
def img2mesh(p): return A_m + a.scale*(_base(p) - A_m)
def mesh2img(xy):
    b = A_m + (xy - A_m)/a.scale
    return (b[:, 0]/sx + u_mid, (crown_y - b[:, 1])/sy + v_cr)
# weight by POSITION round the head (not by normal: the steep walls of a sculpted eye would move/lift differently
# from the floor beside them and tear): cos of the angle from the front, seen from the head's centre line
_hz = V[V[:, 1] > chin_y, 2]; zc = float(_hz.min() + _hz.max())/2                # box centre (a median sits in the dense face)
cosf = (V[:, 2] - zc)/np.maximum(np.hypot(V[:, 0], V[:, 2] - zc), 1e-9)
fw = np.clip((cosf - 0.30)/0.45, 0, 1); fw = fw*fw*(3 - 2*fw)                     # 1 in front, 0 past ~72 degrees
hw_ = np.clip((V[:, 1] - (chin_y - 0.25))/0.2, 0, 1)                              # fades out under the chin
w = fw*hw_

if a.morph > 0:
    keys = ["inner", "outer", "top", "bottom", "centre"]
    src = [ML["eye"][k] for k in keys] + [ML["nose"], ML["mouth"], ML["chin"]]
    dst = [img2mesh(IL["eye"][k]) for k in keys] + [img2mesh(IL["nose"]), img2mesh(IL["mouth"]), img2mesh(IL["chin"])]
    src, dst = np.array(src, float), np.array(dst, float)
    src = np.vstack([src, src*[-1, 1]]); dst = np.vstack([dst, dst*[-1, 1]])
    src[:, 0] = np.where(np.abs(src[:, 0]) < 1e-6, 0, src[:, 0])
    src, idx = np.unique(src.round(5), axis=0, return_index=True); dst = dst[idx]
    anc = np.array([[0, crown_y], [hw_m, crown_y - 0.3*(crown_y - chin_y)], [-hw_m, crown_y - 0.3*(crown_y - chin_y)],
                    [0.9*hw_m, chin_y + 0.45*(crown_y - chin_y)], [-0.9*hw_m, chin_y + 0.45*(crown_y - chin_y)]])
    tps = RBFInterpolator(np.vstack([src, anc]), np.vstack([dst, anc]), kernel="thin_plate_spline", smoothing=1e-4)
    sel = w > 0
    V[sel, :2] += a.morph*w[sel, None]*(tps(V[sel, :2]) - V[sel, :2])
    mv = np.linalg.norm(V[:, :2] - m.vertices[:, :2], axis=1)
    print(f"   morph {a.morph}: {int(sel.sum())} front verts, moved up to {mv.max():.3f} (median of moved {np.median(mv[mv > 1e-4]):.3f})")
    m.vertices = V; N = m.vertex_normals                                          # normals after the move

u, v = mesh2img(V[:, :2])
ui = np.clip(np.round(u).astype(int), 0, W - 1); vi = np.clip(np.round(v).astype(int), 0, H - 1)
inside = (u >= 0) & (u < W) & (v >= 0) & (v < H)
d = np.where(inside, Hmap[vi, ui], 0.0)*w
if a.smooth:                                                          # average the relief over the mesh's neighbours:
    import scipy.sparse as sp                                         # canvas grain and pixel steps don't become bumps
    e = m.edges_unique; A = sp.coo_matrix((np.ones(2*len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])),
                                          shape=(len(V), len(V))).tocsr()
    deg = np.asarray(A.sum(1)).ravel(); P = sp.diags(1/np.maximum(deg, 1)) @ A
    for _ in range(a.smooth): d = 0.5*d + 0.5*(P @ d)
V = V + N*d[:, None]
col = m.visual.vertex_colors[:, :3] if m.visual.kind == "vertex" else np.full((len(V), 3), 200, np.uint8)
if a.paint_eyes:
    ew = np.where(inside, e_soft[vi, ui], 0.0)*(w > 0.2)
    col = ((1 - ew[:, None])*col + ew[:, None]*np.array([float(c) for c in a.paint_eyes.split(",")])).astype(np.uint8)
write_sculptgl(a.out, V, m.faces, col, comment=f"ply_imprint: {Path(a.img).name} on {Path(a.inp).name}, morph {a.morph}")
print(f"-> {a.out}: displaced {int((np.abs(d) > 1e-5).sum())} verts, relief {d.min():+.3f}..{d.max():+.3f}")
if a.debug:
    Path(a.debug).mkdir(parents=True, exist_ok=True)
    hv = (Hmap - Hmap.min())/(np.ptp(Hmap) + 1e-9)
    Image.fromarray((hv*255).astype(np.uint8)).save(Path(a.debug)/"height.png")
    ov = (rgb*255).astype(np.uint8).copy()
    for p in [IL["crown"], IL["chin"], IL["nose"], IL["mouth"]] + list(IL["eye"].values()):
        x, y = int(p[0]), int(p[1]); ov[max(0, y - 4):y + 5, max(0, x - 4):x + 5] = (255, 0, 255)
    ov[eye & ~ndimage.binary_erosion(eye, iterations=2)] = (0, 255, 255)
    Image.fromarray(ov).save(Path(a.debug)/"landmarks.png"); print("   debug ->", a.debug)
