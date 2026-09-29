#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["xatlas", "numpy"]
# ///
"""xatlas unwrap: uniform-texel-density UVs — every triangle gets paintable area.
In: mesh.npz (positions float32 [n,3], triangles int32 [m,3])
Out: uvs.npz (loop_uvs float32 [m,3,2] — per-corner UVs in triangle order)"""
import sys, numpy as np, xatlas
d = np.load(sys.argv[1])
pos, tri = d["positions"], d["triangles"]
print(f"xatlas: {len(pos)} verts, {len(tri)} tris ...")
vmap, idx, uvs = xatlas.parametrize(pos.astype(np.float32), tri.astype(np.uint32))
loop_uvs = uvs[idx].astype(np.float32)          # [m,3,2]
np.savez(sys.argv[2], loop_uvs=loop_uvs)
print(f"done: {len(uvs)} uv verts, atlas islands packed")
