#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy", "scipy"]
# ///
"""
Morph a painted body texture so its silhouette lands EXACTLY on the mesh silhouette.

Why: an image model repainting our render keeps the pose only roughly — limbs sit at slightly different angles, so
a planar projection misses on the arms. Since the silhouettes are similar, a smooth
non-rigid warp closes the gap:

1. pre-align: linear content-bbox -> silhouette-bbox map into the render frame
2. demons registration (multi-resolution) on SIGNED DISTANCE FIELDS of the two
   silhouettes -> a smooth displacement field
3. warp the RGBA texture by that field (alpha rides along)

Run: warp_to_silhouette.py TEX.png MESH_SIL.png OUT.png [check_overlay.png|-] [pad_erode_px=4]
"""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates, zoom

TEX, SIL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
CHK = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != '-' else None
PAD_ERODE = int(sys.argv[5]) if len(sys.argv) > 5 else 4           # px of the painted rim replaced by the pad

sil = np.array(Image.open(SIL).convert("L")) > 127          # fixed mask (mesh)
H, W = sil.shape
tex = np.array(Image.open(TEX).convert("RGBA")).astype(np.float32)
def figure_mask(px):
    """Content mask robust to opaque border frames (ChatGPT PNGs ship one): take the
    largest connected component that does NOT touch the image border."""
    from scipy.ndimage import label
    if px[:, :, 3].min() < 128:
        m = px[:, :, 3] > 128
    else:
        g = px[:, :, :3].mean(2)
        bg = float(np.median(np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])))
        m = np.abs(g - bg) > 12
    lab, nlab = label(m)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    sizes = [(lab == i).sum() if i not in border else 0 for i in range(1, nlab + 1)]
    if not sizes or max(sizes) == 0:                        # everything touches border -> fall back
        return m
    from scipy.ndimage import binary_fill_holes
    return binary_fill_holes(lab == (1 + int(np.argmax(sizes))))   # gray-on-gray maps have interior holes
tmask = figure_mask(tex)
tex[~tmask] = 0                                             # kill border junk: only the figure survives

# --- 1. pre-align ANCHORED ON THE HEAD (head-on-head, the proven face fit) ---
# The face must land linearly (no warping); limbs get corrected by demons below.
def head_box(m):
    """(top_row, pinch_row, x0, x1) of the head via the neck-pinch width profile."""
    wid = np.array([(lambda c: c.max()-c.min() if len(c) > 1 else 0)(np.where(m[r])[0])
                    for r in range(m.shape[0])])
    rows = np.where(wid > 0)[0]
    top = rows[0]
    half = top + (rows[-1] - top) // 2
    wr = top + int(np.argmax(wid[top:half]))                 # widest head row
    seg = wid[wr:half]
    rise = np.where(seg > wid[wr] * 1.02)[0]
    end = wr + (rise[0] if len(rise) else len(seg))
    pinch = wr + int(np.argmin(wid[wr:end]))
    hs = np.where(m[top:pinch].any(0))[0]
    return top, pinch, hs.min(), hs.max()
_, sp, _, _ = head_box(sil)                                  # sil neck pinch (head-protection row)
# GLOBAL figure-bbox pre-align (ChatGPT paints over our render -> near-identity; the
# face lands naively/linearly, which is what works — demons below only fixes limbs)
tys, txs = np.where(tmask); sys_, sxs = np.where(sil)
ty0, ty1, tx0, tx1 = tys.min(), tys.max(), txs.min(), txs.max()
sy0, sy1, sx0, sx1 = sys_.min(), sys_.max(), sxs.min(), sxs.max()
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
src_y = ty0 + (yy - sy0) * (ty1 - ty0) / (sy1 - sy0)
src_x = tx0 + (xx - sx0) * (tx1 - tx0) / (sx1 - sx0)
tex0 = np.stack([map_coordinates(tex[:, :, c], [src_y, src_x], order=1, mode='constant') for c in range(4)], -1)
m0 = map_coordinates(tmask.astype(np.float32), [src_y, src_x], order=1) > 0.5
print(f"global pre-align: fig {tx1-tx0}x{ty1-ty0} -> sil {sx1-sx0}x{sy1-sy0}; head protected above row {sp}")

def sdf(m):
    return (distance_transform_edt(~m) - distance_transform_edt(m)).astype(np.float32)

# --- 2. multi-res demons on SDFs ---
def demons(F, M, iters, sigma):
    h, w = F.shape
    u = np.zeros((2, h, w), np.float32)
    gy, gx = np.gradient(F)
    g2 = gy*gy + gx*gx
    for _ in range(iters):
        yy2, xx2 = np.mgrid[0:h, 0:w].astype(np.float32)
        Mw = map_coordinates(M, [yy2 + u[0], xx2 + u[1]], order=1, mode='nearest')
        d = Mw - F
        den = g2 + 0.05 * d*d + 1e-6
        u[0] -= gaussian_filter(d * gy / den, 2.0)
        u[1] -= gaussian_filter(d * gx / den, 2.0)
        u[0] = gaussian_filter(u[0], sigma); u[1] = gaussian_filter(u[1], sigma)
    return u

WORK = 640 / W                                              # register at ~640 wide
Fw = zoom(sil.astype(np.float32), WORK, order=1) > 0.5
Mw = zoom(m0.astype(np.float32), WORK, order=1) > 0.5
F = np.clip(sdf(Fw), -60, 60)
M = np.clip(sdf(Mw), -60, 60)
h, w = F.shape
# stage 1: coarse (quarter res) catches the big limb offsets
Fc = np.clip(sdf(zoom(Fw.astype(np.float32), 0.25, order=1) > 0.5), -20, 20)
Mc = np.clip(sdf(zoom(Mw.astype(np.float32), 0.25, order=1) > 0.5), -20, 20)
u1 = demons(Fc, Mc, iters=80, sigma=2.0)
u1 = np.stack([zoom(u1[0], h / u1.shape[1], order=1), zoom(u1[1], w / u1.shape[2], order=1)])[:, :h, :w] * 4.0
# stage 2: fine refinement on M pre-warped by u1 (compose u = u1 + u2 — smooth fields)
yyw, xxw = np.mgrid[0:h, 0:w].astype(np.float32)
M1 = map_coordinates(M, [yyw + u1[0], xxw + u1[1]], order=1, mode='nearest')
u2 = demons(F, M1, iters=80, sigma=2.0)
u = u1 + u2
print("registered (coarse + fine)")

# --- 3. upscale field, damp it deep inside the shape, warp the full-res texture ---
u_full = np.stack([zoom(u[0], H / u.shape[1], order=1) / WORK,
                   zoom(u[1], W / u.shape[2], order=1) / WORK])
u_full = u_full[:, :H, :W]
# boundary-weighted: full correction near the silhouette (thin limbs = fully inside the
# band), fading to zero deep inside -> the face/chest interior is never smeared.
din = distance_transform_edt(sil).astype(np.float32)
t = np.clip((din - 60.0) / 90.0, 0, 1)                      # 1 @ <60px from edge, 0 @ >150px
wgt = 1.0 - t*t*(3-2*t)
# HEAD PROTECTION: zero warp above the neck pinch (the face must stay linear/crisp),
# ramping in over ~120px below it.
rowratio = np.clip((yy - sp) / 120.0, 0, 1)
wgt = wgt * (rowratio*rowratio*(3-2*rowratio))
u_full *= wgt[None, :, :]
out = np.stack([map_coordinates(tex0[:, :, c], [yy + u_full[0], xx + u_full[1]], order=1, mode='constant') for c in range(4)], -1)
wm = map_coordinates(m0.astype(np.float32), [yy + u_full[0], xx + u_full[1]], order=1) > 0.5
# EDGE-PAD: RGB outside the figure = nearest figure color (side-facing polys sample
# just past the silhouette — without this they hit transparent black). Alpha stays the
# figure mask so the projector's content-bbox still sees the figure.
# The pad (and the figure's outermost PAD_ERODE px) take the colour from PAD_ERODE px INSIDE the edge: a painting's
# rim pixels are anti-aliased into its background, and padding THOSE outward drew grey streaks down the arms' and
# legs' sides once projected (a busy skin pattern hides it; a smooth skin shows it).
from scipy.ndimage import binary_erosion
core = binary_erosion(wm, iterations=PAD_ERODE) if PAD_ERODE else wm
if not core.any(): core = wm
_, (iy, ix) = distance_transform_edt(~core, return_indices=True)
out[:, :, :3] = np.where(core[..., None], out[:, :, :3], out[iy, ix, :3])
out[:, :, 3] = wm.astype(np.float32) * 255
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(OUT)
iou = (wm & sil).sum() / max((wm | sil).sum(), 1)
print(f"WROTE {OUT}  silhouette IoU after warp: {iou:.3f}")

if CHK:
    er = sil & np.roll(sil,1,0) & np.roll(sil,-1,0) & np.roll(sil,1,1) & np.roll(sil,-1,1)
    edge = sil & ~er
    for _ in range(2):
        edge = edge | np.roll(edge,1,0) | np.roll(edge,-1,0) | np.roll(edge,1,1) | np.roll(edge,-1,1)
    q = out[:, :, :3].copy()
    q[edge] = (255, 235, 0)
    Image.fromarray(np.clip(q, 0, 255).astype(np.uint8)).save(CHK)
    print(f"check -> {CHK}")
