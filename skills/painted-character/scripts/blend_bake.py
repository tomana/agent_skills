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
        interpolated) take a harmonic fill from the visible surface round them (the SIDE_NOARM argument is kept for
        compatibility but no longer sampled).
Panel frame = body_texture_apply.py's: the painting's figure bbox (alpha) <-> the mesh bbox, front/back across x,
side across depth (front at content-right), all bottom-to-top in y.

  blend_bake.py MESH.npz UVS.npz FRONT.png BACK.png SIDE.png SIDE_NOARM.png OUT.png [--size 4096] [--sharp 3]
                [--head-up 16.3] [--head-ramp 0.05,0.4] [--margin 8]
MESH.npz from blend_bake_io.py export (sculpt frame), UVS.npz from xatlas_unwrap.py.

Transitions: each panel is also weighted by how deep inside ITS OWN silhouette the texel lands (--rim-px): paintings
darken toward their outlines, so near a panel's rim the panel that sees the surface face-on takes over. The side is
pulled to the front / back where they overlap by a smooth gain field (harmonic over the mesh); the front is the
reference and never changes. --no-match skips the field.
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
ap.add_argument("--rim-px", type=float, default=30, help="a panel hands over within this many px of its silhouette")
ap.add_argument("--no-match", dest="match", action="store_false", help="skip the tone match of side/back to the front")
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
    ys, xs = np.where(al); return im[..., :3], (xs.min(), xs.max(), ys.min(), ys.max()), ndimage.distance_transform_edt(al)
mx0, mx1 = V[:, 0].min(), V[:, 0].max(); my0, my1 = V[:, 1].min(), V[:, 1].max(); mz0, mz1 = V[:, 2].min(), V[:, 2].max()
tx = (Vt[:, 0] - mx0)/(mx1 - mx0); ty = (Vt[:, 1] - my0)/(my1 - my0); td = (mz1 - Vt[:, 2])/(mz1 - mz0)   # td 0 = front
def sample(img_bb, u01, tyy=None):
    img, (x0, x1, y0, y1), dist = img_bb
    px = x0 + u01*(x1 - x0); py = y1 - (ty if tyy is None else tyy)*(y1 - y0)
    col_ = np.stack([ndimage.map_coordinates(img[..., c], [py, px], order=1, mode="nearest") for c in range(3)], -1)
    q_ = np.clip(ndimage.map_coordinates(dist, [py, px], order=1, mode="nearest")/a.rim_px, 0, 1)
    return col_, q_*q_*(3 - 2*q_)                                      # colour, "deep inside this painting" 0..1
PF, PB, PS, PSn = load(a.front), load(a.back), load(a.side), load(a.side_noarm)
(cF, qF), (cB, qB) = sample(PF, tx), sample(PB, 1 - tx)
(cS, qS), (cSn, qSn) = sample(PS, 1 - td), sample(PSn, 1 - td)
# HIDDEN FLANK (behind the arm from the side camera): no painting sees it well - the side painting has the arm there,
# its arm-free fill and the steep front/back both carry the painted shading beside the arm (a darker, more orange
# patch). So its colour comes from the SURFACE round it: per vertex, the low-passed blend of the panels at every
# vertex the side camera DOES see, extended harmonically (graph Laplacian, Dirichlet on the visible vertices) over the
# hidden ones, interpolated to the texels.
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
e_ = tm.edges_unique; n_ = len(V)
A_ = sp.coo_matrix((np.ones(2*len(e_)), (np.r_[e_[:, 0], e_[:, 1]], np.r_[e_[:, 1], e_[:, 0]])), shape=(n_, n_)).tocsr()
Lap = (sp.diags(np.asarray(A_.sum(1)).ravel()) - A_).tocsr()
tv = (V[:, 0] - mx0)/(mx1 - mx0); tyv = (V[:, 1] - my0)/(my1 - my0); tdv = (mz1 - V[:, 2])/(mz1 - mz0)
def lpv(img_bb, u01, sig=10):
    img, bbx, dist = img_bb
    return sample((np.stack([ndimage.gaussian_filter(img[..., c], sig) for c in range(3)], -1), bbx, dist), u01, tyv)
(lcF, qFv), (lcB, qBv), (lcS, qSv) = lpv(PF, tv), lpv(PB, 1 - tv), lpv(PS, 1 - tdv)
vF = np.clip(N[:, 2], 0, None)**a.sharp*qFv; vB = np.clip(-N[:, 2], 0, None)**a.sharp*qBv; vS = np.abs(N[:, 0])**a.sharp*qSv
vsum = vF + vB + vS + 1e-9
Cv = (lcF*vF[:, None] + lcB*vB[:, None] + lcS*vS[:, None])/vsum[:, None]
hid = occ_v > 0.5; vis = ~hid
fillv = Cv.copy()
if hid.any():
    Lhh = Lap[hid][:, hid].tocsc(); Lhv = Lap[hid][:, vis]
    for c in range(3): fillv[hid, c] = spsolve(Lhh, -(Lhv @ Cv[vis, c]))
fillt = np.einsum("nk,nkd->nd", bb, fillv[F[tt]])
print(f"   hidden flank: {int(hid.sum())} vertices filled from the visible surface round them")
cSide = cS*(1 - Ot[:, None]) + fillt*Ot[:, None]; qSide = qS*(1 - Ot) + Ot

# ---- weights ----
nx, nz = Nt[:, 0], Nt[:, 2]
wF = np.clip(nz, 0, None)**a.sharp; wB = np.clip(-nz, 0, None)**a.sharp; wS = np.abs(nx)**a.sharp
# RIM: every painting darkens toward its own silhouette (painted form shading, the anti-aliased edge); near a panel's
# rim its weight hands over to the panel that sees the surface face-on (--rim-px: the handover width in painting px)
w0 = (wF, wB, wS)
wF, wB, wS = wF*(0.05 + 0.95*qF), wB*(0.05 + 0.95*qB), wS*(0.05 + 0.95*qSide)
head = (Vt[:, 1] > a.head_up) & (nz > 0)
h = np.clip((nz - r0)/(r1 - r0), 0, 1); h = h*h*(3 - 2*h)
hw = np.clip((Vt[:, 1] - a.head_up)/0.15, 0, 1)                      # fade the head rule in over 0.15 units
tot = wF + wB + wS + 1e-9; wF, wB, wS = wF/tot, wB/tot, wS/tot
wF = np.where(head, (1 - hw)*wF + hw*h, wF); wS = np.where(head, (1 - hw)*wS + hw*(1 - h), wS); wB = np.where(head, (1 - hw)*wB, wB)
# ---- tone match (the panels differ slightly in brightness and hue; the face must not change). The FRONT is the reference and is never changed (the face lives there). The back gets one global per-channel
# gain (matched through the side); the SIDE gets a smooth correction FIELD over the mesh: at vertices where it overlaps
# the front it must match the front, where it overlaps the back it must match the (gained) back, and in between it is
# harmonic (a graph-Laplacian solve) - the remaining front/back difference becomes a gentle gradient across the flank
# instead of a step. All in log colour (a gain), on low-passed panel colours sampled at the vertices. (Height bins
# with a left/right split were tried first: they cut a seam down the back of the head.)
if a.match:
    lF, lB = np.log(np.maximum(lcF, 1)), np.log(np.maximum(lcB, 1))
    lS = np.log(np.maximum(lcS*(1 - occ_v[:, None]) + fillv*occ_v[:, None], 1))
    vS = vS*(1 - occ_v) + np.abs(N[:, 0])**a.sharp*occ_v
    tv_ = vF + vB + vS + 1e-9; vF, vB, vS = vF/tv_, vB/tv_, vS/tv_
    cfs, cbs = np.minimum(vF, vS), np.minimum(vB, vS)
    # the side is pulled to the front where they overlap and to the back where they overlap; harmonic in between.
    # (Global gains are not needed: the paintings' interiors already agree within 1-2 levels after delight.py.)
    tgt = (cfs[:, None]*(lF - lS) + cbs[:, None]*(lB - lS))/np.maximum(cfs + cbs, 1e-9)[:, None]
    cw = np.where(cfs + cbs > 0.03, cfs + cbs, 0.0)
    lam = 20.0; K = (Lap + sp.diags(lam*cw) + sp.identity(n_)*0.02).tocsc()      # 0.02: decays to 0 far from any band
    dS = np.stack([spsolve(K, lam*cw*tgt[:, c]) for c in range(3)], -1); dS = np.clip(dS, -0.2, 0.2)
    dSt = np.einsum("nk,nkd->nd", bb, dS[F[tt]])
    cSide = cSide*np.exp(dSt)
    print(f"   tone match: side field {np.exp(dS.min(0)).round(2)}..{np.exp(dS.max(0)).round(2)} ({int((cw > 0).sum())} anchored vertices)")
seam = (np.minimum(wF, wS) > 0.2) | (np.minimum(wB, wS) > 0.2)
def seam_err():
    e1 = np.abs(cF - cSide)[np.minimum(wF, wS) > 0.2].mean(0); e2 = np.abs(cB - cSide)[np.minimum(wB, wS) > 0.2].mean(0)
    b1 = (cF - cSide)[np.minimum(wF, wS) > 0.2].mean(0); b2 = (cB - cSide)[np.minimum(wB, wS) > 0.2].mean(0)
    return e1.round(1), e2.round(1), "bias", b1.round(1), b2.round(1)
print(f"   seam |diff| (front-side, back-side) per channel: {seam_err()}")
col = cF*wF[:, None] + cB*wB[:, None] + cSide*wS[:, None]

out = np.zeros((S, S, 3), np.float32); out[rr, cc] = col
_, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)          # gutter: nearest texel
grow = ndimage.binary_dilation(filled, iterations=a.margin)
out[grow & ~filled] = out[iy[grow & ~filled], ix[grow & ~filled]]
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
print(f"-> {a.out}: {S}x{S}, blended front/back/side (p {a.sharp}; head front ramp nz {r0}..{r1} above y {a.head_up})")
