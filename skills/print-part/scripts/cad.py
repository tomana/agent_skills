"""cad.py - small helpers for parametric FDM parts: trimesh + manifold3d booleans, shapely for 2D.

Import it from a uv inline script that sits next to it:

    #!/usr/bin/env -S uv run --script
    # /// script
    # requires-python = ">=3.11"
    # dependencies = ["trimesh","numpy","manifold3d","shapely","mapbox-earcut","networkx","scipy","rtree","lxml"]
    # ///
    from cad import *

Units are millimetres. Z is up and the print bed is z = 0.
"""
import math
from pathlib import Path
import numpy as np
import trimesh
from trimesh.creation import box as _box, cylinder as _cyl, extrude_polygon
from trimesh.transformations import translation_matrix as T, rotation_matrix as R

MF = dict(engine="manifold")          # every boolean goes through manifold3d: fast and watertight

# ---------------------------------------------------------------- fasteners
# Printed hole sizes (clearance included), socket head cap screws (ISO 4762). Rows marked "verified" printed and
# fitted well in PETG on a 0.4 mm nozzle; the rest are standard dimensions plus the same clearance, so print a
# coupon before trusting them on a big part.
HOLES = {
    #        clearance Ø, counterbore Ø x depth, hex nut trap across-flats x depth
    "M2.5": dict(clear=2.9, cb_d=5.0, cb_h=2.8, nut_af=5.3, nut_h=2.3, verified=True),
    "M3":   dict(clear=3.4, cb_d=6.0, cb_h=3.3, nut_af=5.8, nut_h=2.7, verified=True),
    "M4":   dict(clear=4.5, cb_d=7.6, cb_h=4.3, nut_af=7.3, nut_h=3.5, verified=True),
    "M6":   dict(clear=6.6, cb_d=11.2, cb_h=6.5, nut_af=10.4, nut_h=5.4, verified=False),   # clear 6.6 verified
}
STANDARD_LENGTHS = (6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50)

def bolt_length(stack, engage_min, engage_max, lengths=STANDARD_LENGTHS, washer=0.0):
    """Pick screw lengths that fit a clamp stack.
    stack      = everything the screw passes through under its head (mm)
    engage_min = how far past the stack the tip must reach (through the nut / insert / slot lip + nut)
    engage_max = how far it may reach before it bottoms out (blind hole, T-slot depth)
    Returns [(length, tip_past_stack), ...] for every standard length inside the window."""
    return [(L, round(L - stack - washer, 2)) for L in lengths if engage_min - 1e-9 <= L - stack - washer <= engage_max + 1e-9]

# ---------------------------------------------------------------- primitives
def bx(x0, x1, y0, y1, z0, z1):
    """axis-aligned box from its extents (any order)"""
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return _box(extents=[x1 - x0, y1 - y0, z1 - z0], transform=T([(x0 + x1)/2, (y0 + y1)/2, (z0 + z1)/2]))

def zcyl(r, x, y, z0, z1, sections=48):
    """vertical cylinder (holes, bosses)"""
    c = _cyl(radius=r, height=abs(z1 - z0), sections=sections); c.apply_translation([x, y, (z0 + z1)/2]); return c

def cyl(r, center, axis, length, sections=48):
    """cylinder of `length` along axis 0/1/2, centred at `center`"""
    c = _cyl(radius=r, height=length, sections=sections)
    if axis == 0: c.apply_transform(R(math.pi/2, [0, 1, 0]))
    elif axis == 1: c.apply_transform(R(math.pi/2, [1, 0, 0]))
    c.apply_translation(center); return c

def hex_prism(across_flats, x, y, z0, z1):
    """hex nut trap: a 6-sided cylinder sized by the nut's across-flats (flat faces along x)"""
    c = _cyl(radius=across_flats/math.sqrt(3), height=abs(z1 - z0), sections=6)
    c.apply_translation([x, y, (z0 + z1)/2]); return c

def prism(pts, a0, a1, axis=0):
    """CONVEX polygon given in the plane perpendicular to `axis`, extruded from a0 to a1 along it.
    axis=0: pts are (y, z); axis=1: (x, z); axis=2: (x, y). Gussets, wedges, chamfered brackets."""
    n = len(pts); V = []
    for a in (a0, a1):
        for u, v in pts:
            V.append({0: [a, u, v], 1: [u, a, v], 2: [u, v, a]}[axis])
    F = []
    for i in range(1, n - 1): F += [[0, i + 1, i], [n, n + i, n + i + 1]]
    for i in range(n):
        j = (i + 1) % n; F += [[i, j, n + j], [i, n + j, n + i]]
    m = trimesh.Trimesh(np.array(V, float), np.array(F)); m.merge_vertices(); trimesh.repair.fix_normals(m); return m

def extrude(poly, h, z0=0.0):
    """shapely Polygon -> solid of height h from z0. Put HOLES in afterwards with diff() in 3D: holes baked into the
    2D polygon can crack the triangulation (a thin ring around a hole comes out broken)."""
    m = extrude_polygon(poly, h); m.apply_translation([0, 0, z0]); return m

# ---------------------------------------------------------------- booleans
def union(*ms): return trimesh.boolean.union(list(ms), **MF)
def diff(a, *ms): return trimesh.boolean.difference([a] + list(ms), **MF)
def inter(a, b): return trimesh.boolean.intersection([a, b], **MF)

def rot_z(m, deg, about=(0, 0, 0)):
    c = m.copy(); c.apply_transform(R(math.radians(deg), [0, 0, 1], about)); return c

def clean(m):
    m.merge_vertices(); trimesh.repair.fix_normals(m); return m

# ---------------------------------------------------------------- output
def to_bed(m):
    """copy moved so its bounding box starts at the origin (how it lies on the bed)"""
    p = m.copy(); p.apply_translation(-p.bounds[0]); return p

def export(m, name, out):
    """write <out>/stl/<name>_world.stl (assembly coordinates, for clash checks and renders) and
    <out>/stl/<name>.stl (moved onto the bed). STL is the canonical output: 3mf transfers have failed before."""
    d = Path(out)/"stl"; d.mkdir(parents=True, exist_ok=True)
    m.export(str(d/f"{name}_world.stl")); p = to_bed(m); p.export(str(d/f"{name}.stl")); return p

# ---------------------------------------------------------------- checks (print them, every run)
def bodies(m):
    return len(m.split(only_watertight=False))

def report(name, m, bed=180.0, margin=4.0):
    e = m.extents; fit = e[0] <= bed - 2*margin and e[1] <= bed - 2*margin
    print(f"  {name}: {e[0]:6.1f} x {e[1]:6.1f} x {e[2]:5.1f}  watertight {m.is_watertight}  bodies {bodies(m)}  "
          f"fits {bed:.0f} bed {fit}")
    return fit and m.is_watertight

def overlap(a, b):
    """intersection volume in mm3 (0 if the bounding boxes don't even touch)"""
    if not ((a.bounds[0] < b.bounds[1]).all() and (b.bounds[0] < a.bounds[1]).all()): return 0.0
    return inter(a, b).volume

def worst_overlap(parts, neighbours):
    return max((overlap(p, q) for p in parts for q in neighbours), default=0.0)

def section(m, origin, normal, drop):
    """planar section of m as ONE shapely (Multi)Polygon in the 2 axes left after dropping axis `drop`.
    Loops are combined with symmetric difference, so holes come out as holes. Needs scipy."""
    from shapely.geometry import Polygon
    s = m.section(plane_origin=origin, plane_normal=normal); acc = Polygon()
    if s is None: return acc
    keep = [i for i in range(3) if i != drop]
    for lp in s.discrete:
        if len(lp) >= 4: acc = acc.symmetric_difference(Polygon(lp[:, keep]).buffer(0))
    return acc

def solid_at(m, pts):
    """True where each point is inside m. Use it to probe that a bolt axis is open through every part it
    passes, and that the material a few mm off the axis is solid. Needs rtree."""
    return list(m.contains(np.asarray(pts, float)))
