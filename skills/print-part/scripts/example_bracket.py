#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","manifold3d","shapely","mapbox-earcut","networkx","scipy","rtree","lxml","matplotlib"]
# ///
"""Worked example of the whole loop: a wall shelf bracket, built parametrically, checked numerically, laid out on a
plate, and (with --render) rendered for the user.

World: the wall is the plane y = 0, z up. The bracket's back plate lies on the wall, the shelf arm sticks out
along +y at the top, a 45-degree gusset ties them. A cable duct runs up the wall beside it (a neighbour to clear).

  example_bracket.py [--width 30] [--arm 80] [--out out] [--render]
Out: out/stl/bracket.stl (+ _world), out/3mf/bracket_{1,2}.3mf (4 brackets, 2 per plate), out/bracket_section.png,
     with --render: out/bracket_assembly.png + out/bracket_plate.png
"""
import argparse, sys
from pathlib import Path
import numpy as np
from cad import *
from plate import pack, write_plates

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=float, default=30.0)     # along x
ap.add_argument("--arm", type=float, default=80.0)       # shelf depth, along y
ap.add_argument("--out", default="out"); ap.add_argument("--render", action="store_true")
a = ap.parse_args()

# ---- parameters: every number has a name
W, ARM, H = a.width, a.arm, 90.0          # width, arm length, back plate height
T = 8.0                                    # plate / arm thickness (leaves 3.7 mm under an M4 counterbore)
G, GW = 45.0, 6.0                          # gusset leg length (45 degrees) and thickness
WALL = HOLES["M4"]; SHELF = HOLES["M3"]
Z_WALL_HOLES = (20.0, 60.0)                # two M4 into the wall, counterbored flush
Y_SHELF_HOLE = ARM - 15.0                  # one M3 up into the shelf board, nut trapped from below
DUCT = (W/2 + 3.0, W/2 + 3.0 + 25.0)       # the neighbouring cable duct, x range (3 mm clear of the bracket)

def build(W):
    back = bx(-W/2, W/2, 0, T, 0, H)
    arm = bx(-W/2, W/2, 0, ARM, H - T, H)
    # the gusset sits on the +x edge: that face goes DOWN on the bed when the part lies on its side for printing,
    # so it prints on the bed instead of as an unsupported web in mid-air (the first version had it centred)
    gusset = prism([(T - 0.3, H - T + 0.3), (T - 0.3, H - T - G), (T + G, H - T + 0.3)], W/2 - GW, W/2, axis=0)  # 0.3 overlap: no coplanar faces
    m = union(back, arm, gusset)
    cuts = []
    for z in Z_WALL_HOLES:                 # M4: clearance through, counterbore from the open (+y) face
        cuts += [cyl(WALL["clear"]/2, (0, T/2, z), 1, 3*T), cyl(WALL["cb_d"]/2, (0, T - WALL["cb_h"]/2 + 0.01, z), 1, WALL["cb_h"])]
    cuts += [zcyl(SHELF["clear"]/2, 0, Y_SHELF_HOLE, H - T - 1, H + 1),                      # M3 up through the arm
             hex_prism(SHELF["nut_af"], 0, Y_SHELF_HOLE, H - T - 0.01, H - T + SHELF["nut_h"])]  # nut trap from below
    return clean(diff(m, *cuts))

print(f"bracket  W {W}  arm {ARM}  H {H}  T {T}")
br = build(W)
duct = bx(*DUCT, 0, 30, 0, 200)
out = Path(a.out)

# ---- checks, printed every run
report("bracket (world)", br)
worst = worst_overlap([br], [duct])
worst_old = worst_overlap([build(W + 12)], [duct])      # prove the check bites: a 12 mm wider bracket must clash
print(f"  clash with the duct: {'none' if worst < 0.01 else f'{worst:.1f} mm3'}   (a 12 mm wider bracket: {worst_old:.0f} mm3 - the check works)")
for z in Z_WALL_HOLES:
    axis, off = solid_at(br, [(0, T/2, z)])[0], solid_at(br, [(WALL['cb_d']/2 + 2, T/2, z)])[0]
    print(f"  M4 at z {z:.0f}: axis open {not axis}, solid beside it {off}")
BOARD = 18.0                                              # the shelf board the M3 comes down through
print("  M3 lengths (board 18 + arm above the nut):", bolt_length(stack=BOARD + T - SHELF["nut_h"], engage_min=SHELF["nut_h"],
      engage_max=SHELF["nut_h"] + 5.0, lengths=(16, 20, 25, 30, 35)), "(length, tip past the stack; must pass the nut, <= 5 mm proud)")

# ---- print orientation: lie the L on its side (profile flat on the bed): no supports, layers run along the arm
p = br.copy(); p.apply_transform(R(np.pi/2, [0, 1, 0])); p = export(p, "bracket", out)
report("bracket (on the bed)", p)
plates = write_plates(pack({f"bracket_{i + 1}": p for i in range(4)}), out/"3mf"/"bracket")   # 2 per plate at this size

# ---- a section through the wall holes: the check a picture gives that numbers don't
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sec = section(br, [0, 0, 0], [1, 0, 0], drop=0)
fig, ax = plt.subplots(figsize=(6, 6))
for g in getattr(sec, "geoms", [sec]):
    x, y = g.exterior.xy; ax.fill(x, y, fc="#3b7dd8", ec="#123", lw=0.8)
    for hl in g.interiors: x, y = hl.xy; ax.fill(x, y, fc="white", ec="#123", lw=0.8)
ax.axvline(0, color="#777", ls=":"); ax.text(-3, 45, "wall", rotation=90, color="#777", ha="right")
ax.set_aspect("equal"); ax.grid(alpha=0.3); ax.set_xlabel("y (mm from the wall)"); ax.set_ylabel("z (mm)")
ax.set_xlim(-8, None); ax.set_title("section x = 0: counterbored M4s, M3 + nut trap in the arm", fontsize=10)
fig.savefig(str(out/"bracket_section.png"), dpi=90, bbox_inches="tight"); print(f"  -> {out/'bracket_section.png'}")

if a.render:                                              # the sibling skill's renderer
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"blender-render"/"scripts"))
    from render import render
    wall = bx(-120, 120, -8, 0, -10, 200)
    render([(wall, "wall"), (duct, "duct"), (br, "part")],
           colors=dict(part=[0.23, 0.49, 0.85], duct=[0.62, 0.64, 0.67], wall=[0.93, 0.92, 0.88]),
           camera=dict(target=[0, 30, 55], loc=[-230, 300, 190], lens=45), out=out/"bracket_assembly.png",
           title="Shelf bracket on the wall", subtitle="blue = printed part, grey = cable duct it must clear")
    import subprocess
    subprocess.run([str(Path(__file__).resolve().parents[2]/"blender-render"/"scripts"/"plate_view.py"),
                    *map(str, plates), "--out-dir", str(out)], check=True)
