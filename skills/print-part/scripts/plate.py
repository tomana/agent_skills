"""plate.py - lay printed parts out on a bed and write one 3mf per plate, with the checks printed.

    from plate import pack, nest_pair, write_plates
    plates = pack({"bracket_1": m1, "bracket_2": m2, ...}, bed=180)     # shelf packing, fills plates in order
    write_plates(plates, "out/3mf/brackets")                          # -> brackets.3mf / brackets_1.3mf ...

Parts go in as they should lie on the bed (flat face down). Lay them out with pack() for boxy parts; for L-shaped
parts that are too big to sit side by side, nest_pair() puts two of them in opposite bed corners so their empty
insides overlap on the diagonal (checked with a boolean, not just bounding boxes).
"""
from pathlib import Path
import trimesh

MF = dict(engine="manifold")

def _placed(m, x, y):
    g = m.copy(); g.apply_translation([x - g.bounds[0][0], y - g.bounds[0][1], -g.bounds[0][2]]); return g

def pack(parts, bed=180.0, margin=4.0, gap=6.0):
    """shelf packing: tallest (in y) first, left to right, a new row when the row is full, a new plate when the
    plate is full. Returns [ {name: placed_mesh} , ...] one dict per plate."""
    items = sorted(parts.items(), key=lambda kv: -kv[1].extents[1])
    plates, cur, x, y, row_h = [], {}, margin, margin, 0.0
    for name, m in items:
        e = m.extents
        if e[0] > bed - 2*margin or e[1] > bed - 2*margin:
            raise ValueError(f"{name} ({e[0]:.1f} x {e[1]:.1f}) is bigger than the bed - split it or nest it")
        if x + e[0] > bed - margin:                        # next row
            x, y, row_h = margin, y + row_h + gap, 0.0
        if y + e[1] > bed - margin:                        # next plate
            plates.append(cur); cur, x, y, row_h = {}, margin, margin, 0.0
        cur[name] = _placed(m, x, y); x += e[0] + gap; row_h = max(row_h, e[1])
    if cur: plates.append(cur)
    return plates

def nest_pair(a, b, bed=180.0, margin=4.0):
    """two L-shaped parts on one plate: `a` into the far corner (x, y max), `b` into the near corner (0, 0).
    Orient them first so each one's arms run along the bed edges of its own corner (a's arms along the top and
    right edges, b's along the bottom and left). Raises if they still collide."""
    ea, eb = a.extents, b.extents
    pa = _placed(a, bed - margin - ea[0], bed - margin - ea[1]); pb = _placed(b, margin, margin)
    ov = trimesh.boolean.intersection([pa, pb], **MF).volume if (pa.bounds[0] < pb.bounds[1]).all() else 0.0
    if ov > 0.01: raise ValueError(f"nested pair collides ({ov:.1f} mm3) - rotate them or use two plates")
    return {"a": pa, "b": pb}

def check(plate, bed=180.0):
    """bounds inside the bed + no two parts overlapping (real boolean volume)"""
    gs = list(plate.values()); ov = 0.0
    for i in range(len(gs)):
        for j in range(i + 1, len(gs)):
            if (gs[i].bounds[0] < gs[j].bounds[1]).all() and (gs[j].bounds[0] < gs[i].bounds[1]).all():
                ov += trimesh.boolean.intersection([gs[i], gs[j]], **MF).volume
    lo = min(g.bounds[0][0] for g in gs), min(g.bounds[0][1] for g in gs)
    hi = max(g.bounds[1][0] for g in gs), max(g.bounds[1][1] for g in gs)
    ok = lo[0] >= 0 and lo[1] >= 0 and hi[0] <= bed and hi[1] <= bed and ov < 0.01
    return ok, lo, hi, ov

def write_plates(plates, stem, bed=180.0):
    """one 3mf per plate: <stem>.3mf if there is one plate, else <stem>_1.3mf, <stem>_2.3mf ..."""
    stem = Path(stem); stem.parent.mkdir(parents=True, exist_ok=True); out = []
    for i, plate in enumerate(plates):
        f = stem.with_name(stem.name + ("" if len(plates) == 1 else f"_{i + 1}") + ".3mf")
        sc = trimesh.Scene()
        for name, g in plate.items(): sc.add_geometry(g, node_name=name)
        sc.export(str(f)); ok, lo, hi, ov = check(plate, bed)
        print(f"  plate {f.name}: {len(plate)} parts  {lo[0]:.1f}..{hi[0]:.1f} x {lo[1]:.1f}..{hi[1]:.1f}  "
              f"overlap {ov:.2f} mm3  ({bed:.0f} bed: {'OK' if ok else 'BAD'})")
        out.append(f)
    return out
