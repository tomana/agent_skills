#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","pillow","networkx","scipy"]
# ///
"""Grayscale height map (brighter = higher) -> watertight relief STL with a FLAT back, ready to print or to
use as a mould former. Pairs with depth_estimate.py (photo -> depth map).

  heightmap_to_stl.py depth.png relief.stl --width-mm 120 [--relief-mm 12] [--base-mm 3] [--res 300] [--invert]

The image aspect is kept (height follows from the width). --res = grid points along the long side
(300 is plenty for a 0.4 mm nozzle at ~120 mm). The same thing in Blender is a subdivided plane + Displace
modifier (texture coords UV, mid level 0, strength = relief) + Solidify - this script skips Blender.
"""
import argparse
import numpy as np, trimesh
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--width-mm", type=float, required=True)
ap.add_argument("--relief-mm", type=float, default=12.0, help="height of pure white above pure black")
ap.add_argument("--base-mm", type=float, default=3.0, help="solid plate under the relief")
ap.add_argument("--res", type=int, default=300, help="grid points along the long side")
ap.add_argument("--invert", action="store_true")
a = ap.parse_args()

img = Image.open(a.inp).convert("L")
s = a.res / max(img.size); img = img.resize((max(2, round(img.width*s)), max(2, round(img.height*s))), Image.LANCZOS)
d = np.asarray(img, dtype=np.float32) / 255.0
if a.invert: d = 1.0 - d
ny, nx = d.shape
W = a.width_mm; H = W * (ny - 1) / (nx - 1)
X, Y = np.meshgrid(np.linspace(0, W, nx), np.linspace(H, 0, ny))          # image row 0 = the top edge (+y)
top = np.column_stack([X.ravel(), Y.ravel(), (a.base_mm + a.relief_mm*d).ravel()])
bot = np.column_stack([X.ravel(), Y.ravel(), np.zeros(nx*ny)])
V = np.vstack([top, bot]); N = nx*ny
idx = np.arange(N).reshape(ny, nx)
a0, b0, c0, d0 = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
F = [np.column_stack([a0, d0, c0]), np.column_stack([a0, c0, b0]),                  # top surface
     np.column_stack([a0, c0, d0]) + N, np.column_stack([a0, b0, c0]) + N]          # flat back (reversed)
ring = np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])    # the border, once round
p, q = ring, np.roll(ring, -1)
F += [np.column_stack([p, q, q + N]), np.column_stack([p, q + N, p + N])]            # side walls
m = trimesh.Trimesh(V, np.vstack(F), process=True)
trimesh.repair.fix_normals(m)
m.export(a.out)
print(f"{a.out}: {m.extents[0]:.1f} x {m.extents[1]:.1f} x {m.extents[2]:.1f} mm  grid {nx}x{ny}  "
      f"watertight {m.is_watertight}  volume {m.volume/1000:.1f} cm3")
