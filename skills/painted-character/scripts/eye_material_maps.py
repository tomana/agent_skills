#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy","scipy","pillow"]
# ///
"""eye_material_maps.py - glossy-eye material maps (<base>_spec.png + <base>_rough.png) for a character whose skins
differ only in the eyes.

For a renderer that reads two optional maps in the colour UV:
  _spec  R = the glint mask, G = darken the albedo there (0 here: the skins carry their own eye colours, pale eyeballs
         included), A = the glint's spread (1 = a broad lobe, which on a domed eye lights the whole eye like chrome;
         0 = a small wet highlight - the shader multiplies its exponent). Read G and A so a one-channel grey map
         (G = R, A = 1 after the usual swizzle) keeps its old meaning.
  _rough 0 = glossy .. 1 = rough; the skin gets --skin-rough (the renderer's default without a map), the eyes --eye-rough.
The eye mask needs no geometry: the skins are the same texture except the eyes, so wherever any two skins differ is
an eye (an atlas packer puts small charts of the eye surface on their own - they count too). Closed, holes filled,
single-texel specks dropped, feathered by --feather texels. Use only the skins that differ in the EYES (not a skin
with a whole repainted face).

  eye_material_maps.py OUT_BASE skin_0.png skin_1.png [...] [--eye-rough 0.04] [--skin-rough 0.5] [--darken 0] [--eye-spread 0]
  -> OUT_BASE_spec.png, OUT_BASE_rough.png (same size as the skins)
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("out_base"); ap.add_argument("skins", nargs="+")
ap.add_argument("--eye-rough", type=float, default=0.04); ap.add_argument("--skin-rough", type=float, default=0.5)
ap.add_argument("--darken", type=float, default=0.0); ap.add_argument("--thresh", type=int, default=3)
ap.add_argument("--eye-spread", type=float, default=0.0, help="A in the eyes: 1 = the broad lobe (chrome-white on a domed eye), 0 = a small wet highlight (12x the exponent)")
ap.add_argument("--feather", type=float, default=1.5)
a = ap.parse_args()

S = [np.asarray(Image.open(p).convert("RGB")).astype(np.int16) for p in a.skins]
diff = np.zeros(S[0].shape[:2], bool)
for i in range(len(S)):
    for j in range(i + 1, len(S)):
        diff |= np.abs(S[i] - S[j]).max(2) > a.thresh
m = ndimage.binary_fill_holes(ndimage.binary_closing(diff, iterations=3))
lab, n = ndimage.label(m); sizes = ndimage.sum(m, lab, range(1, n + 1))
m = np.isin(lab, np.where(sizes >= 10)[0] + 1)                              # small charts of the eye surface stay
w = np.clip(ndimage.gaussian_filter(m.astype(np.float32), a.feather), 0, 1)
spec = np.dstack([w, w*a.darken, np.zeros_like(w), 1 - w*(1 - a.eye_spread)])
rough = a.skin_rough + (a.eye_rough - a.skin_rough)*w
Image.fromarray((spec*255 + 0.5).astype(np.uint8), "RGBA").save(f"{a.out_base}_spec.png")
Image.fromarray((rough*255 + 0.5).astype(np.uint8), "L").save(f"{a.out_base}_rough.png")
print(f"-> {a.out_base}_spec.png / _rough.png: eye mask {int(m.sum())} texels in {int((sizes >= 10).sum())} islands "
      f"(of {len(S)} skins), eye rough {a.eye_rough}, skin rough {a.skin_rough}, darken {a.darken}")
