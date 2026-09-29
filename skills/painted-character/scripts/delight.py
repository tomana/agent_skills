#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy","scipy","pillow"]
# ///
"""delight.py - take the painted LIGHTING out of a warped body painting, so it works as an albedo.

Image models paint form shading even when told "flat, even light":
the torso's sides under the arms come out darker, and projected onto the model those bands read as shadows cast by
the arms (and the renderer lights the model again on top). This divides the figure's colours by their LOCAL mean
brightness (a masked gaussian of luminance, --sigma px) and multiplies by the body's median brightness: slow
light/dark goes, detail smaller than ~sigma (collarbones, ribs, knuckles) stays, hue is untouched. The head (rows
above --head-row, ramping in over 80 px) is left alone - the portrait's face is placed there on purpose. The pad
outside the figure is rebuilt from 4 px inside the edge (as warp_to_silhouette.py does).

  delight.py IN.png OUT.png [--sigma 18] [--head-row 432] [--clamp 0.7,1.5] [--strength 1.0] [--target 155]
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--sigma", type=float, default=18); ap.add_argument("--head-row", type=float, default=None)
ap.add_argument("--clamp", default="0.7,1.5"); ap.add_argument("--strength", type=float, default=1.0)
ap.add_argument("--target", type=float, help="body brightness to aim for (give every panel the SAME one, or the\n                                             panels meet in visible steps)")
a = ap.parse_args()
lo, hi = (float(c) for c in a.clamp.split(","))

img = np.asarray(Image.open(a.inp).convert("RGBA")).astype(np.float32); H, W = img.shape[:2]
mask = img[..., 3] > 127
core = ndimage.binary_erosion(mask, iterations=4)
rgb = img[..., :3]; L = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
m = core.astype(np.float32)
Lb = ndimage.gaussian_filter(L*m, a.sigma)/np.maximum(ndimage.gaussian_filter(m, a.sigma), 1e-3)
rows = np.arange(H)[:, None]*np.ones((1, W))
w = np.ones((H, W), np.float32)
if a.head_row is not None:
    t = np.clip((rows - a.head_row)/80.0, 0, 1); w = t*t*(3 - 2*t)
body = core & (w > 0.99)
target = a.target if a.target else (float(np.median(L[body])) if body.any() else float(np.median(L[core])))
gain = np.clip(target/np.maximum(Lb, 1.0), lo, hi)**a.strength
gain = 1 + (gain - 1)*w
out = rgb*gain[..., None]
_, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
out = np.where(core[..., None], out, out[iy, ix])                     # rebuild the pad from inside the edge
Image.fromarray(np.clip(np.dstack([out, img[..., 3]]), 0, 255).astype(np.uint8), "RGBA").save(a.out)
print(f"-> {a.out}: body brightness {target:.0f}, gain {gain[core].min():.2f}..{gain[core].max():.2f} (median "
      f"{np.median(gain[core]):.2f}), head rows < {a.head_row} kept")
