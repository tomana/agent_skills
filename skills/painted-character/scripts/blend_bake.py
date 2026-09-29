#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","scipy","pillow","rtree"]
# ///
"""blend_bake.py - bake the projected paintings into a unique (xatlas) texture, BLENDED by the surface normal.

Why: rendering the textured model next to its paintings (render_like_views.py) shows the seams are the method -
body_texture_apply.py
gives each TRIANGLE one panel (front, back or side), so where two panels meet the texture switches along the triangle
edges - jagged, and wherever the two paintings disagree in tone (a portrait darkens toward the head's outline, a
side painting doesn't) a hard step - on the temple, typically. Here every TEXEL samples all panels with the projector's frame math
and mixes them by its interpolated normal: the panels cross-fade, no triangle edges.

  body:  w_front = max(nz, 0)^p, w_back = max(-nz, 0)^p, w_side = |nx|^p (p = --sharp), normalised
  head (y > --head-up), facing front (nz > 0): the portrait leads - front weight ramps 0 -> 1 over nz --head-ramp
         (the eye / nose walls stay on the portrait; the temple fades into the side painting over a band)
  side: texels hidden from their side camera by the arm (a ray toward +-x from the vertex hits the mesh; per vertex,
        interpolated) sample the arm-free side painting (side_noarm.py) instead.
Panel frame = body_texture_apply.py's: the painting's figure bbox (alpha) <-> the mesh bbox, front/back across x,
side across depth (front at content-right), all bottom-to-top in y.

  blend_bake.py MESH.npz UVS.npz FRONT.png BACK.png SIDE.png SIDE_NOARM.png OUT.png [--size 4096] [--sharp 3]
                [--head-up 16.3] [--head-ramp 0.05,0.4] [--margin 8]
MESH.npz from blend_bake_io.py export (sculpt frame), UVS.npz from xatlas_unwrap.py.
"""
import argparse
import numpy as np, trimesh
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("mesh"); ap.add_argument("uvs"); ap.add_argument("front"); ap.add_argument("back")
ap.add_argument("side"); ap.add_argument("side_noarm"); ap.add_argument("out")
ap.add_argument("--size", type=int, default=4096); ap.add_argument("--sharp", type=float, default=3.0)
ap.add_argument("--head-up", type=float, default=16.3); ap.add_argument("--head-ramp", default="0.05,0.4")
ap.add_argument("--margin", type=int, default=8)
a = ap.parse_args()
r0, r1 = (float(c) for c in a.head_ramp.split(","))

M = np.load(a.mesh); V, N, F = M["positions"].astype(np.float64), M["normals"].astype(np.float64), M["triangles"]
LU = np.load(a.uvs)["loop_uvs"].reshape(-1, 3, 2)
assert len(LU) == len(F), (len(LU), len(F))
S = a.size

# ---- per-vertex side occlusion (the arm in front of the flank) ----
tm = trimesh.Trimesh(V, F, process=False)
side_dir = np.c_[np.sign(N[:, 0]), np.zeros(len(V)), np.zeros(len(V))]; side_dir[side_dir[:, 0] == 0, 0] = 1
eps = 1e-3*np.ptp(V[:, 1])
hit = tm.ray.intersects_first(ray_origins=V + side_dir*eps + N*eps, ray_directions=side_dir)
occ_v = (hit >= 0).astype(np.float64)
print(f"   {int(occ_v.sum())} of {len(V)} vertices hidden from their side camera")

# ---- rasterize the UV triangles: texel -> (triangle, barycentrics) ----
tri_id = np.full((S, S), -1, np.int32); bary = np.zeros((S, S, 3), np.float32)
P = LU*[S, S]; P[..., 1] = S - P[..., 1]                              # pixel coords, rows top-down (v up)
for t in range(len(F)):
    p = P[t]; x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, S - 1), min(y1, S - 1)
    if x1 < x0 or y1 < y0: continue
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    (ax_, ay_), (bx_, by_), (cx_, cy_) = p
    den = (by_ - cy_)*(ax_ - cx_) + (cx_ - bx_)*(ay_ - cy_)
    if abs(den) < 1e-12: continue
    l0 = ((by_ - cy_)*(gx - cx_) + (cx_ - bx_)*(gy - cy_))/den
    l1 = ((cy_ - ay_)*(gx - cx_) + (ax_ - cx_)*(gy - cy_))/den
    l2 = 1 - l0 - l1
    ins = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
    if not ins.any(): continue
    rr, cc = np.where(ins); rr += y0; cc += x0
    tri_id[rr, cc] = t; bary[rr, cc] = np.c_[l0[ins], l1[ins], l2[ins]]
filled = tri_id >= 0
rr, cc = np.where(filled); tt = tri_id[rr, cc]; bb = bary[rr, cc].astype(np.float64)
print(f"   rasterized {len(F)} triangles -> {len(rr)} texels ({100*len(rr)/S/S:.0f} % of {S}^2)")
Vt = np.einsum("nk,nkd->nd", bb, V[F[tt]]); Nt = np.einsum("nk,nkd->nd", bb, N[F[tt]])
Nt /= np.maximum(np.linalg.norm(Nt, axis=1, keepdims=True), 1e-9); Ot = np.einsum("nk,nk->n", bb, occ_v[F[tt]])

# ---- panel frames ----
def load(pth):
    im = np.asarray(Image.open(pth).convert("RGBA")).astype(np.float32)
    al = im[..., 3] > 127
    lab, n = ndimage.label(al)
    if n > 1:
        border = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
        sizes = [(lab == i).sum() if i not in border else 0 for i in range(1, n + 1)]
        al = lab == (1 + int(np.argmax(sizes)))
    ys, xs = np.where(al); return im[..., :3], (xs.min(), xs.max(), ys.min(), ys.max())
mx0, mx1 = V[:, 0].min(), V[:, 0].max(); my0, my1 = V[:, 1].min(), V[:, 1].max(); mz0, mz1 = V[:, 2].min(), V[:, 2].max()
tx = (Vt[:, 0] - mx0)/(mx1 - mx0); ty = (Vt[:, 1] - my0)/(my1 - my0); td = (mz1 - Vt[:, 2])/(mz1 - mz0)   # td 0 = front
def sample(img_bb, u01):
    img, (x0, x1, y0, y1) = img_bb
    px = x0 + u01*(x1 - x0); py = y1 - ty*(y1 - y0)
    return np.stack([ndimage.map_coordinates(img[..., c], [py, px], order=1, mode="nearest") for c in range(3)], -1)
cF = sample(load(a.front), tx); cB = sample(load(a.back), 1 - tx)
cS = sample(load(a.side), 1 - td); cSn = sample(load(a.side_noarm), 1 - td)
cSide = cS*(1 - Ot[:, None]) + cSn*Ot[:, None]

# ---- weights ----
nx, nz = Nt[:, 0], Nt[:, 2]
wF = np.clip(nz, 0, None)**a.sharp; wB = np.clip(-nz, 0, None)**a.sharp; wS = np.abs(nx)**a.sharp
head = (Vt[:, 1] > a.head_up) & (nz > 0)
h = np.clip((nz - r0)/(r1 - r0), 0, 1); h = h*h*(3 - 2*h)
hw = np.clip((Vt[:, 1] - a.head_up)/0.15, 0, 1)                      # fade the head rule in over 0.15 units
tot = wF + wB + wS + 1e-9; wF, wB, wS = wF/tot, wB/tot, wS/tot
wF = np.where(head, (1 - hw)*wF + hw*h, wF); wS = np.where(head, (1 - hw)*wS + hw*(1 - h), wS); wB = np.where(head, (1 - hw)*wB, wB)
col = cF*wF[:, None] + cB*wB[:, None] + cSide*wS[:, None]

out = np.zeros((S, S, 3), np.float32); out[rr, cc] = col
_, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)          # gutter: nearest texel
grow = ndimage.binary_dilation(filled, iterations=a.margin)
out[grow & ~filled] = out[iy[grow & ~filled], ix[grow & ~filled]]
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
print(f"-> {a.out}: {S}x{S}, blended front/back/side (p {a.sharp}; head front ramp nz {r0}..{r1} above y {a.head_up})")
