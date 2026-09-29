#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow","rtree"]
# ///
"""side_noarm.py - the SIDE painting with the arm taken out, for the torso's flank behind it.

For arm shadows down the flanks. In the side view the A-pose arm hangs in front of the torso, so the flank faces
behind it sampled the ARM (its edges and shading) from the side painting - dark lines down the body. Sending those faces to the front/back painting instead gave
a darker jagged band (the painted form shading at the torso's edge). So: find the flank faces hidden from the side
camera (a ray from each lateral face toward +x/-x hits something), take the faces that HIDE them (the arm), draw
those into the side image as a mask, and fill the mask from the torso round it (nearest pixel, then a diffusion
smooth). body_texture_apply.py uses this image only for the hidden faces (its NOARM argument); the arm's own sides
keep the real side painting.

Frame = body_texture_apply's side panel: x from depth (front at content-right), y from height, both linear onto the
side image's figure bbox (its alpha).

  side_noarm.py MESH.ply warp_side.png OUT.png [--head-up 16.3] [--grow 3]
"""
import argparse, sys
from pathlib import Path
import numpy as np, trimesh
from PIL import Image, ImageDraw
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh

ap = argparse.ArgumentParser()
ap.add_argument("mesh"); ap.add_argument("side"); ap.add_argument("out")
ap.add_argument("--head-up", type=float, default=16.3, help="faces above this height are left alone (the head)")
ap.add_argument("--grow", type=int, default=3, help="px the arm mask is grown by")
a = ap.parse_args()

m = read_mesh(a.mesh); m = trimesh.Trimesh(m.vertices, m.faces, process=False)
V, F, N, C = m.vertices, m.faces, m.face_normals, m.triangles_center      # PLY frame: x across, y up, z = front
lateral = (np.abs(N[:, 0]) > np.abs(N[:, 2])) & (C[:, 1] < a.head_up)
idx = np.where(lateral)[0]
d = np.c_[np.sign(N[idx, 0]), np.zeros(len(idx)), np.zeros(len(idx))]
eps = 1e-3*np.ptp(V[:, 1])
hit = m.ray.intersects_first(ray_origins=C[idx] + d*eps, ray_directions=d)
hidden = idx[hit >= 0]; occluders = np.unique(hit[hit >= 0])
print(f"   {len(idx)} lateral body faces, {len(hidden)} hidden from the side camera, {len(occluders)} faces hide them")

img = np.asarray(Image.open(a.side).convert("RGBA")).astype(np.float32); H, W = img.shape[:2]
alpha = img[..., 3] > 127; ys, xs = np.where(alpha); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
zmin, zmax = V[:, 2].min(), V[:, 2].max(); ymin, ymax = V[:, 1].min(), V[:, 1].max()
def to_px(P):                                                          # body_texture_apply's side-panel map
    u = x0 + (P[:, 2] - zmin)/(zmax - zmin)*(x1 - x0)                 # front (+z) at content-RIGHT
    v = y1 - (P[:, 1] - ymin)/(ymax - ymin)*(y1 - y0)                 # image rows top-down
    return np.c_[u, v]
mask_im = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(mask_im)
for f in F[occluders]:
    dr.polygon([tuple(p) for p in to_px(V[f])], fill=255)
mask = ndimage.binary_dilation(np.asarray(mask_im) > 0, iterations=a.grow) & alpha
# fill: nearest un-masked figure pixel, then diffuse inside the mask so the fill carries no streaks
src = alpha & ~mask
_, (iy, ix) = ndimage.distance_transform_edt(~src, return_indices=True)
rgb = img[..., :3].copy(); rgb[mask] = rgb[iy[mask], ix[mask]]
for _ in range(60):
    blur = ndimage.uniform_filter(rgb, size=(7, 7, 1))
    rgb[mask] = blur[mask]
out = np.dstack([rgb, img[..., 3]])
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(a.out)
print(f"-> {a.out}: arm filled over {int(mask.sum())} px of the side painting")
