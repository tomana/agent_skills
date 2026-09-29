#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","networkx","scipy","shapely"]
# ///
"""head_transplant.py - put another sculpt's HEAD on a body sculpt, joined by a smooth neck.

Made for two sculpts of the same figure in the same frame (e.g. an 18.5-unit y-up A-pose character): the head just
drops on, only the neck needs joining. Also stitches a head sculpted on its own (head_cut.py) back onto its body.

How:
  1. cut the BODY at --cut-body (keeps below) and the HEAD donor at --cut-head (keeps above) with planes. Pick heights
     where the section is ONE loop (the neck) in both - not through the shoulders.
  2. --align (default on): shift the head in x/z so its neck loop sits where the body's neck is at that height
     (--no-align keeps the donor where it was sculpted - right when both are the same figure in the same frame).
  3. loft between the two loops: both are resampled by angle round their centroid, --rings intermediate rings
     interpolate them, and the original loop vertices are zippered onto the first/last ring (no vertex is moved or
     dropped outside the neck).
  4. Taubin-smooth a band round the join (--band above/below the loft) so the neck flows.
  5. colours: body keeps its (SculptGL-painted) vertex colours; the head keeps its own if it has them, else it gets
     the body's median neck colour; the loft interpolates. Write a SculptGL-flavoured PLY.

  head_transplant.py --body body.ply --head other_head.stl --cut-body 15.58 --cut-head 15.90 --out body_newhead.ply
  head_transplant.py --body full.ply --head head_sculpted.ply --cut-body 15.70 --cut-head 15.90 --no-align --out new.ply
Then: open the PLY in SculptGL, blend/paint the neck + head, export.
"""
import argparse, sys
from pathlib import Path
import numpy as np, trimesh
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sculptgl_io import read_mesh, write_sculptgl

ap = argparse.ArgumentParser()
ap.add_argument("--body", required=True); ap.add_argument("--head", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--cut-body", type=float, required=True); ap.add_argument("--cut-head", type=float, required=True)
ap.add_argument("--no-align", dest="align", action="store_false")
ap.add_argument("--rings", type=int, default=6); ap.add_argument("--n", type=int, default=240)
ap.add_argument("--band", type=float, default=0.18); ap.add_argument("--smooth", type=int, default=25)
a = ap.parse_args()

def largest(m):
    parts = m.split(only_watertight=False)
    return max(parts, key=lambda p: len(p.faces)) if len(parts) > 1 else m

def cut(m, y, keep_below):
    n = [0, -1, 0] if keep_below else [0, 1, 0]
    return trimesh.intersections.slice_mesh_plane(m, plane_normal=n, plane_origin=[0, y, 0], cap=False)

def boundary_loop(m, y):
    """the ordered boundary cycle of m lying at height y (the cut)"""
    e = m.edges_sorted; u = trimesh.grouping.group_rows(e, require_count=1); be = e[u]
    near = np.abs(m.vertices[be].mean(axis=1)[:, 1] - y) < 1e-3
    be = be[near]
    nxt = {}
    for p, q in be: nxt.setdefault(p, []).append(q); nxt.setdefault(q, []).append(p)
    start = be[0][0]; loop = [start]; prev = None; cur = start
    while True:
        nb = [v for v in nxt[cur] if v != prev]
        if not nb: break
        prev, cur = cur, nb[0]
        if cur == start: break
        loop.append(cur)
    return np.array(loop)

def by_angle(m, loop):
    """loop vertices, their angle (0..2pi, round the loop centroid in x-z), ordered by increasing angle"""
    p = m.vertices[loop]; c = p.mean(axis=0)
    th = np.mod(np.arctan2(p[:, 0] - c[0], p[:, 2] - c[2]), 2*np.pi)          # 0 = +z (front), increasing towards +x
    if np.sum(np.diff(np.unwrap(th))) < 0: loop, th, p = loop[::-1], th[::-1], p[::-1]   # make it counter-clockwise
    k = np.argmin(th); loop, th = np.roll(loop, -k), np.roll(th, -k)
    return loop, th, c

def resample(m, loop, th, n):
    """n points on the loop at uniform angles"""
    p = m.vertices[loop]; t = np.unwrap(th); t = t - t[0]
    tt = np.r_[t, 2*np.pi]; pp = np.vstack([p, p[:1]])
    q = np.linspace(0, 2*np.pi, n, endpoint=False)
    return np.c_[np.interp(q, tt, pp[:, 0]), np.interp(q, tt, pp[:, 1]), np.interp(q, tt, pp[:, 2])]

def zipper(ia, sa, ib, sb):
    """triangles between two closed ordered rings (indices ia/ib, params sa/sb in [0,1))"""
    tris = []; i = j = 0; na, nb = len(ia), len(ib)
    while i < na or j < nb:
        a_next = sa[i + 1] if i + 1 < na else 1.0 + sa[0]
        b_next = sb[j + 1] if j + 1 < nb else 1.0 + sb[0]
        if (a_next <= b_next and i < na) or j >= nb:
            tris.append([ia[i % na], ia[(i + 1) % na], ib[j % nb]]); i += 1
        else:
            tris.append([ia[i % na], ib[(j + 1) % nb], ib[j % nb]]); j += 1
    return tris

from scipy.spatial import cKDTree
def colours_of(src):
    return src.visual.vertex_colors[:, :3] if src.visual.kind == "vertex" else None
body = read_mesh(a.body); head = largest(read_mesh(a.head))
body_rgb, head_rgb = colours_of(body), colours_of(head)
b = cut(body, a.cut_body, True); h = cut(head, a.cut_head, False)
for part in (b, h): part.merge_vertices(merge_tex=True, merge_norm=True)   # the cut leaves per-face duplicates along the loop
b = largest(b); h = largest(h)
lb, thb, cb = by_angle(b, boundary_loop(b, a.cut_body))
lh, thh, ch = by_angle(h, boundary_loop(h, a.cut_head))
# align: the head's neck loop over where the BODY's neck is at that same height (keeps the body's neck lean; comparing
# the two cut loops at different heights would tilt the head back). Off for a donor already posed on this body.
def neck_centroid(m, y):
    s = m.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    loops = sorted([lp for lp in s.discrete if len(lp) > 3], key=lambda lp: abs(lp[:, 0].mean()))
    return loops[0].mean(axis=0)
if a.align:
    cbh = neck_centroid(body, a.cut_head); shift = np.array([cbh[0] - ch[0], 0.0, cbh[2] - ch[2]])
else:
    shift = np.zeros(3)
hv = h.vertices + shift
print(f"body {len(b.vertices)} v below y {a.cut_body} (neck loop {len(lb)} v) | head {len(h.vertices)} v above y {a.cut_head} "
      f"(neck loop {len(lh)} v) | head shifted x {shift[0]:+.3f} z {shift[2]:+.3f}")

# assemble: body verts, head verts, then the loft rings
V = [b.vertices, hv]; nb_, nh_ = len(b.vertices), len(hv)
F = [b.faces, h.faces + nb_]
rb = resample(b, lb, thb, a.n); hh = trimesh.Trimesh(hv, h.faces, process=False); rh = resample(hh, lh, thh, a.n)
rings = []; base = nb_ + nh_
for k in range(1, a.rings + 1):
    t = k/(a.rings + 1); t = t*t*(3 - 2*t)                                        # smoothstep spacing
    rings.append(np.arange(base, base + a.n)); V.append((1 - t)*rb + t*rh); base += a.n
s_ring = np.arange(a.n)/a.n
F.append(np.array(zipper(lb, thb/(2*np.pi), rings[0], s_ring)))
for r0, r1 in zip(rings[:-1], rings[1:]):
    q = [[r0[i], r0[(i + 1) % a.n], r1[i]] for i in range(a.n)] + [[r0[(i + 1) % a.n], r1[(i + 1) % a.n], r1[i]] for i in range(a.n)]
    F.append(np.array(q))
F.append(np.array(zipper(rings[-1], s_ring, lh + nb_, thh/(2*np.pi))))
V = np.vstack(V); F = np.vstack(F)
m = trimesh.Trimesh(V, F, process=False); trimesh.repair.fix_winding(m); trimesh.repair.fix_normals(m)   # (no merge: keeps the
                                                                                        #  vertex order the colours use)

# colours (before smoothing moves anything, keyed to the source order)
# (the cut makes new vertices - take every kept vertex's colour from the nearest vertex of the source)
cb_ = body_rgb[cKDTree(body.vertices).query(b.vertices)[1]] if body_rgb is not None else np.full((nb_, 3), 180, np.uint8)
neck = np.median(cb_[np.abs(b.vertices[:, 1] - a.cut_body) < 0.3], axis=0).astype(np.uint8)
ch_ = head_rgb[cKDTree(head.vertices).query(h.vertices)[1]] if head_rgb is not None else np.tile(neck, (nh_, 1))
cr = [np.tile(((1 - (k + 1)/(a.rings + 1))*neck + (k + 1)/(a.rings + 1)*ch_[lh].mean(axis=0)).astype(np.uint8), (a.n, 1)) for k in range(a.rings)]
C = np.vstack([cb_, ch_] + cr)
assert len(C) == len(m.vertices), (len(C), len(m.vertices))

# Taubin smoothing on a band round the join (vertices only; weights fade out at the band edges)
y = m.vertices[:, 1]; lo, hi = a.cut_body - a.band, a.cut_head + a.band
w = np.clip(np.minimum(y - lo, hi - y)/(0.5*a.band), 0, 1); band = np.where(w > 0)[0]
nbrs = m.vertex_neighbors; P = m.vertices.copy()
for it in range(a.smooth):
    for lam in (0.5, -0.53):
        L = np.array([P[nbrs[i]].mean(axis=0) - P[i] if len(nbrs[i]) else np.zeros(3) for i in band])
        P[band] += (lam*w[band])[:, None]*L
m.vertices = P
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
write_sculptgl(a.out, m.vertices, m.faces, C, comment=f"head_transplant: body {Path(a.body).name} + head {Path(a.head).name}")
open_edges = len(trimesh.grouping.group_rows(m.edges_sorted, require_count=1))
print(f"-> {a.out}: {len(m.vertices)} v {len(m.faces)} f, open edges {open_edges}, watertight {m.is_watertight}, "
      f"components {len(m.split(only_watertight=False))}, smoothed band y {lo:.2f}-{hi:.2f} ({len(band)} v)")
