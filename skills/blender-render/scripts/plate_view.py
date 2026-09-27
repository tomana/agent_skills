#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","matplotlib","networkx","lxml","scipy","rtree"]
# ///
"""Render a print plate (3mf or stl) lying on the bed, each part LABELLED with its name from the 3mf (the names
plate.write_plates gives them), so the layout can be checked - and talked about - before slicing.

  plate_view.py plates/brackets.3mf [more.3mf ...] [--bed 180] [--color 0.23,0.49,0.85] [--out-dir .] [--no-labels]
      -> <name>_plate.png per file (title: part count + the footprint in mm)
"""
import argparse
from pathlib import Path
import trimesh
from render import render

ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+")
ap.add_argument("--bed", type=float, default=180.0); ap.add_argument("--color", default="0.23,0.49,0.85")
ap.add_argument("--out-dir", default="."); ap.add_argument("--no-labels", dest="labels", action="store_false")
a = ap.parse_args()
for src in map(Path, a.files):
    s = trimesh.load(str(src))
    if isinstance(s, trimesh.Scene):                     # keep the node names: they become the labels
        parts = []
        for node in s.graph.nodes_geometry:
            tf, gname = s.graph[node]; g = s.geometry[gname].copy(); g.apply_transform(tf); parts.append((g, node))
    else:
        parts = [(s, src.stem)]
    bed = trimesh.creation.box(extents=[a.bed, a.bed, 1]); bed.apply_translation([a.bed/2, a.bed/2, -0.5])
    b = trimesh.util.concatenate([p for p, _ in parts]).bounds
    render([(bed, "bed")] + [(p, "part", name if a.labels else None) for p, name in parts],
           colors=dict(part=[float(v) for v in a.color.split(",")], bed=[0.2, 0.21, 0.23]),
           camera=dict(target=[a.bed/2, a.bed/2, 4], loc=[a.bed*0.22, -a.bed*0.6, a.bed*1.28], lens=42),
           out=Path(a.out_dir)/f"{src.stem}_plate.png", res=(1400, 1200),
           title=f"{src.name}: {len(parts)} parts, {b[0][0]:.0f}..{b[1][0]:.0f} x {b[0][1]:.0f}..{b[1][1]:.0f} of {a.bed:.0f} mm")
