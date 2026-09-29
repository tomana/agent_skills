#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","shapely"]
# ///
"""head_cut.py - cut the head (with a neck stub) off a full-figure SculptGL PLY, to sculpt it on its own.

A whole figure is slow and awkward to sculpt in the browser; the head alone is not. Cut it off, sculpt it, stitch it
back with head_transplant.py.

Keeps everything above --y (a plane through the neck: pick a height where the section is ONE loop - on an 18.5-unit
y-up figure with the head at the top, e.g. y >= 15.55), in the same coordinates, with its colours (the cut's new vertices take the nearest old vertex's).
The head is left open at the neck. Stitch it back with head_transplant.py, cutting the sculpted head a little ABOVE
--y and the full body a little below it, so whatever happened at the open edge while sculpting is cut away:

  head_cut.py --in full.ply --out head.ply [--y 15.80]
  head_transplant.py --body full.ply --head head_sculpted.ply --cut-body 15.70 --cut-head 15.90 --no-align --out new.ply
"""
import argparse, sys
from pathlib import Path
import numpy as np, trimesh
from scipy.spatial import cKDTree
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh, write_sculptgl

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--y", type=float, default=15.80)
a = ap.parse_args()

m = read_mesh(a.inp)
h = trimesh.intersections.slice_mesh_plane(m, plane_normal=[0, 1, 0], plane_origin=[0, a.y, 0], cap=False)
h.merge_vertices(merge_tex=True, merge_norm=True)                    # the slice leaves per-face duplicates on the cut
parts = h.split(only_watertight=False)
h = max(parts, key=lambda p: len(p.faces))
col = m.visual.vertex_colors[:, :3][cKDTree(m.vertices).query(h.vertices)[1]] if m.visual.kind == "vertex" \
      else np.full((len(h.vertices), 3), 200, np.uint8)
write_sculptgl(a.out, h.vertices, h.faces, col, comment=f"head_cut: {Path(a.inp).name} above y {a.y}")
open_edges = len(trimesh.grouping.group_rows(h.edges_sorted, require_count=1))
print(f"-> {a.out}: {len(h.vertices)} v {len(h.faces)} f above y {a.y} (of {len(m.vertices)} v), "
      f"open edges {open_edges} (the neck ring), dropped {len(parts) - 1} stray pieces")
