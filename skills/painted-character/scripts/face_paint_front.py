#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow"]
# ///
"""face_paint_front.py - paste the face of a painted portrait into the loop's FRONT texture, in the imprint's frame.

A whole-figure painting gives the head only a few hundred pixels (pupils would be a few pixels), so the face comes
from the portrait itself (~1000 px across the head), mapped with the SAME frame ply_imprint.py sculpted it with
(--img-lm/--mesh-lm/--scale/--anchor), so the painted eyes land in the sculpted eye sockets. --morph then bends it so
its features land exactly on the sculpted ones (pairs read off a gridded front render; eye_outline_pairs.py for the
eye outlines).

The target is the loop's warp_front.png: the sculpt's front orthographic frame from ply_3views.py (2048 x 2560,
centre (0, mid-height), ortho scale = 1.08 x the larger of the figure's width/height, spanning the image height).
The portrait's face is blended in through a soft oval (--feather) so it fades into the body painting at the temples,
crown and neck.

  face_paint_front.py --mesh sculpt.ply --front warp_front.png --img portrait.png --img-lm img.json --mesh-lm mesh.json
                      --scale 0.95 --out warp_front_face.png [--oval 0.92] [--feather 0.10] [--morph pairs.json]
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh

ap = argparse.ArgumentParser()
ap.add_argument("--mesh", required=True); ap.add_argument("--front", required=True); ap.add_argument("--img", required=True)
ap.add_argument("--img-lm", required=True); ap.add_argument("--mesh-lm", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--scale", type=float, default=1.0); ap.add_argument("--anchor")
ap.add_argument("--oval", type=float, default=0.92, help="the blend oval, as a fraction of the painted head's half-size")
ap.add_argument("--feather", type=float, default=0.10, help="oval edge softness (fraction of the half-size)")
ap.add_argument("--morph", help="JSON: sculpt[] -> paint[] feature pairs in mesh x/y (+ anchors, mirror_x): bends the "
                                 "portrait so its eyes/mouth land on the sculpted ones")
a = ap.parse_args()
IL, ML = json.load(open(a.img_lm)), json.load(open(a.mesh_lm))

V = read_mesh(a.mesh).vertices
ctr_y = (V[:, 1].min() + V[:, 1].max())/2
dimF = max(np.ptp(V[:, 0]), np.ptp(V[:, 1]))*1.08
F4 = np.asarray(Image.open(a.front).convert("RGBA")).astype(np.float32); H, W = F4.shape[:2]
F = F4[..., :3]                                                       # the ALPHA (the figure mask) is kept: the
                                                                      # projector finds the figure by it - without it the
                                                                      # whole frame read as the figure and the face slid
                                                                      # down onto the cheeks
px = dimF/max(W, H)                                                   # Blender ortho: the scale spans the larger side

# the imprint's frame (ply_imprint.py): portrait px <-> mesh x/y, grown by --scale about the anchor
u_mid, v_cr, v_ch, hw_px = IL["crown"][0], IL["crown"][1], IL["chin"][1], IL["half_width"]
crown_y, chin_y, hw_m = ML["crown_y"], ML["chin_y"], ML["half_width"]
sy = (crown_y - chin_y)/(v_ch - v_cr); sx = hw_m/hw_px
anc = [float(c) for c in a.anchor.split(",")] if a.anchor else [u_mid, (IL["nose"][1] + IL["mouth"][1])/2]
A = np.array([(anc[0] - u_mid)*sx, crown_y - (anc[1] - v_cr)*sy])

yy, xx = np.mgrid[0:H, 0:W]
mx = (xx - W/2 + 0.5)*px; my = ctr_y - (yy - H/2 + 0.5)*px           # front image px -> mesh x/y
if a.morph:                                                           # sculpted feature -> where the painting has it
    from scipy.interpolate import RBFInterpolator
    J = json.load(open(a.morph)); src, dst = np.array(J["sculpt"], float), np.array(J["paint"], float)
    if J.get("mirror_x"):
        src = np.vstack([src, src*[-1, 1]]); dst = np.vstack([dst, dst*[-1, 1]])
        src, idx = np.unique(src.round(6), axis=0, return_index=True); dst = dst[idx]
    anc = np.array(J.get("anchors", []), float)
    if len(anc):
        if J.get("mirror_x"): anc = np.unique(np.vstack([anc, anc*[-1, 1]]).round(6), axis=0)
        src = np.vstack([src, anc]); dst = np.vstack([dst, anc])
    tps = RBFInterpolator(src, dst, kernel="thin_plate_spline", smoothing=1e-5)
    near = (np.abs(mx) < hw_m*1.3) & (my > chin_y - 0.5) & (my < crown_y + 0.2)   # the head only (speed)
    q = tps(np.c_[mx[near], my[near]]); mx = mx.copy(); my = my.copy(); mx[near], my[near] = q[:, 0], q[:, 1]
    print(f"   morph: {len(J['sculpt'])} feature pairs (mirrored) + {len(anc)} anchors, head px moved up to "
          f"{np.hypot(q[:, 0] - (xx[near] - W/2 + 0.5)*px, q[:, 1] - (ctr_y - (yy[near] - H/2 + 0.5)*px)).max():.3f} units")
bx = A[0] + (mx - A[0])/a.scale; by = A[1] + (my - A[1])/a.scale       # undo the growth
u = bx/sx + u_mid; v = (crown_y - by)/sy + v_cr                       # -> portrait px
P = np.asarray(Image.open(a.img).convert("RGB")).astype(np.float32); PH, PW = P.shape[:2]
inside = (u >= 0) & (u < PW - 1) & (v >= 0) & (v < PH - 1)
samp = np.stack([ndimage.map_coordinates(P[..., c], [np.clip(v, 0, PH - 1), np.clip(u, 0, PW - 1)], order=1) for c in range(3)], -1)

# blend oval: centred on the painted head (midline, halfway crown-chin), half-sizes = half-width x half-height
cu, cv = u_mid, (v_cr + v_ch)/2; ru, rv = hw_px*a.oval, (v_ch - v_cr)/2*a.oval
r = np.sqrt(((u - cu)/ru)**2 + ((v - cv)/rv)**2)
w = np.clip((1 + a.feather - r)/(2*a.feather), 0, 1)*inside
w = w*w*(3 - 2*w)
out = F*(1 - w[..., None]) + samp*w[..., None]
Image.fromarray(np.clip(np.dstack([out, F4[..., 3]]), 0, 255).astype(np.uint8), "RGBA").save(a.out)
ys, xs = np.where(w > 0.5)
print(f"-> {a.out}: portrait face blended over {int((w > 0.01).sum())} px (full weight x {xs.min()}..{xs.max()}, "
      f"y {ys.min()}..{ys.max()} of {W}x{H}; {1/px:.0f} px per unit)")
