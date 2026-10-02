#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow"]
# ///
"""vcolors_to_atlas.py - SculptGL vertex paint INTO the baked atlas (the inverse of atlas_to_sculptgl.py).

Sculpt with the texture on (atlas_to_sculptgl.py), fix the paint by hand (drag the eyes until they are right), and
take that PLY's colours as the skin: every atlas texel of the decimated mesh (UV triangle -> barycentrics -> 3-D point)
takes the colour of the dense sculpt there (inverse-distance over the 4 nearest dense vertices; the PLY bytes are
LINEAR as atlas_to_sculptgl.py wrote them and SculptGL returns them as-is, so they are sRGB-encoded back). Above
--from-y (ramping in over --ramp) the paint replaces the base atlas; below it the base atlas stays (where the sculpt's
vertices are sparse the atlas is sharper).

  vcolors_to_atlas.py --dense painted.ply --mesh blend/mesh.npz --uvs blend/uvs.npz --base blend/skin.png --out skin.png
                      [--from-y 15.9] [--ramp 0.3]
"""
import argparse, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh

ap = argparse.ArgumentParser()
ap.add_argument("--dense", required=True); ap.add_argument("--mesh", required=True); ap.add_argument("--uvs", required=True)
ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--from-y", type=float, default=15.9); ap.add_argument("--ramp", type=float, default=0.3)
a = ap.parse_args()

M = np.load(a.mesh); V, F = M["positions"].astype(np.float64), M["triangles"]
LU = np.load(a.uvs)["loop_uvs"].reshape(-1, 3, 2)
base = np.asarray(Image.open(a.base).convert("RGB")).astype(np.float32); S = base.shape[0]
D = read_mesh(a.dense); DC = D.visual.vertex_colors[:, :3].astype(np.float64)/255.0
DC = np.where(DC <= 0.0031308, 12.92*DC, 1.055*np.power(DC, 1/2.4) - 0.055)*255.0       # linear bytes -> sRGB
tree = cKDTree(D.vertices)

out = base.copy(); P = LU*[S, S]; P[..., 1] = S - P[..., 1]           # pixel coords, rows top-down (as blend_bake.py)
lo_tri = V[F][:, :, 1].max(1) >= a.from_y - a.ramp                     # only triangles reaching into the painted zone
n = 0
for t in np.where(lo_tri)[0]:
    p = P[t]; x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, S - 1), min(y1, S - 1)
    if x1 < x0 or y1 < y0: continue
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    (ax_, ay_), (bx_, by_), (cx_, cy_) = p
    den = (by_ - cy_)*(ax_ - cx_) + (cx_ - bx_)*(ay_ - cy_)
    if abs(den) < 1e-12: continue
    l0 = ((by_ - cy_)*(gx - cx_) + (cx_ - bx_)*(gy - cy_))/den; l1 = ((cy_ - ay_)*(gx - cx_) + (ax_ - cx_)*(gy - cy_))/den
    l2 = 1 - l0 - l1; ins = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
    if not ins.any(): continue
    rr, cc = np.where(ins); rr += y0; cc += x0
    bc = np.c_[l0[ins], l1[ins], l2[ins]]; X = bc @ V[F[t]]
    w = np.clip((X[:, 1] - (a.from_y - a.ramp))/a.ramp, 0, 1); w = w*w*(3 - 2*w)
    d, k = tree.query(X, k=4); iw = 1/np.maximum(d, 1e-6); iw /= iw.sum(1, keepdims=True)
    col = np.einsum("nk,nkc->nc", iw, DC[k])
    out[rr, cc] = (1 - w[:, None])*out[rr, cc] + w[:, None]*col; n += len(rr)
Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8)).save(a.out)
print(f"-> {a.out}: {n} texels from {Path(a.dense).name}'s vertex paint (above y {a.from_y}, ramp {a.ramp}), the rest from {Path(a.base).name}")
