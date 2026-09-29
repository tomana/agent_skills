#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy"]
# ///
"""skin_paint.py - repaint a SculptGL PLY in one flat skin colour (or strip the colours).

Use it to wipe old paint before a sculpt round, to give a sculpt one skin tone sampled from a reference painting
(the median of its lit forehead, cheeks and chin), or a contrasting colour so SculptGL's transparency is readable.
The default 150/116/80 is a warm yellow-tan. The geometry and vertex order are untouched.

  skin_paint.py --in mesh.ply --out mesh_skin.ply [--skin 150,116,80]
  skin_paint.py --in mesh.ply --out mesh_plain.ply --no-colour          # no vertex colours at all
"""
import argparse, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh, write_sculptgl

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--skin", default="150,116,80"); ap.add_argument("--no-colour", action="store_true")
a = ap.parse_args()

m = read_mesh(a.inp); V = m.vertices
if a.no_colour:
    with open(a.out, "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\ncomment skin_paint: no colour, from {Path(a.inp).name}\n"
                 f"element vertex {len(V)}\nproperty float x\nproperty float y\nproperty float z\n"
                 f"element face {len(m.faces)}\nproperty list uchar uint vertex_indices\nend_header\n").encode())
        f.write(V.astype("<f4").tobytes())
        rec = np.zeros(len(m.faces), dtype=[("n", "u1"), ("i", "<u4", (3,))]); rec["n"] = 3; rec["i"] = m.faces
        f.write(rec.tobytes())
    print(f"-> {a.out}: {len(V)} v, no vertex colours"); sys.exit()

skin = np.array([float(c) for c in a.skin.split(",")])
out = np.tile(skin, (len(V), 1))
write_sculptgl(a.out, V, m.faces, np.clip(out, 0, 255).astype(np.uint8), comment=f"skin_paint: skin {a.skin} from {Path(a.inp).name}")
print(f"-> {a.out}: {len(V)} v, all skin {a.skin}")
