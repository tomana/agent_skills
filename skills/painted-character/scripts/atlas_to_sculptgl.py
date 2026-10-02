#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","pillow","rtree"]
# ///
"""atlas_to_sculptgl.py - the textured look on the DENSE sculpt, as vertex colours SculptGL shows.

SculptGL reads PLY/OBJ/STL (no glb, no UV textures), so to sculpt with the texture visible the baked atlas goes onto
the sculpt itself: every vertex of the dense mesh finds the closest point on the decimated mesh the atlas belongs to
(same shape), interpolates that triangle's UVs and samples the atlas (bilinear). SculptGL treats PLY colour bytes as
LINEAR and sRGB-encodes them for display, so the atlas's sRGB colours are written linearised. The geometry and vertex
order of the dense sculpt are untouched - sculpt on it and export as usual.

  atlas_to_sculptgl.py --dense sculpt.ply --mesh blend/mesh.npz --uvs blend/uvs.npz --atlas blend/skin.png --out out.ply
"""
import argparse, sys
from pathlib import Path
import numpy as np, trimesh
from PIL import Image
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh, write_sculptgl

ap = argparse.ArgumentParser()
ap.add_argument("--dense", required=True); ap.add_argument("--mesh", required=True); ap.add_argument("--uvs", required=True)
ap.add_argument("--atlas", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()

D = read_mesh(a.dense)
M = np.load(a.mesh); V, F = M["positions"].astype(np.float64), M["triangles"]
LU = np.load(a.uvs)["loop_uvs"].reshape(-1, 3, 2); assert len(LU) == len(F)
low = trimesh.Trimesh(V, F, process=False)
cp, dist, tid = trimesh.proximity.closest_point(low, D.vertices)
bc = trimesh.triangles.points_to_barycentric(low.triangles[tid], cp)
uv = np.einsum("nk,nkd->nd", bc, LU[tid])
A = np.asarray(Image.open(a.atlas).convert("RGB")).astype(np.float32); S = A.shape[0]
px, py = uv[:, 0]*S - 0.5, (1 - uv[:, 1])*S - 0.5                    # the bake's rows run top-down (v up)
col = np.stack([ndimage.map_coordinates(A[..., c], [py, px], order=1, mode="nearest") for c in range(3)], -1)/255.0
lin = np.where(col <= 0.04045, col/12.92, ((col + 0.055)/1.055)**2.4)
write_sculptgl(a.out, D.vertices, D.faces, np.clip(lin*255 + 0.5, 0, 255).astype(np.uint8),
               comment=f"atlas_to_sculptgl: {Path(a.atlas).name} on {Path(a.dense).name} (rgb LINEAR for SculptGL)")
print(f"-> {a.out}: {len(D.vertices)} v coloured from {Path(a.atlas).name}; dense->decimated distance p99 "
      f"{np.percentile(dist, 99):.4f}, max {dist.max():.4f}")
