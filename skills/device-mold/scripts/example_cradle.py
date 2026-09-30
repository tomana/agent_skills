#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh","numpy","manifold3d","shapely","mapbox-earcut","networkx","scipy","rtree","lxml","matplotlib"]
# ///
"""Worked example of the device-mold loop: a CRADLE that holds two existing devices, built from their spec sheets.

The devices are made up (a "mixer" and a "sampler"); in a real job their outlines, heights and port positions come
from the manufacturers' dimension drawings (see drawing_measure.py) and every number carries its source.

What it builds (world: x along the cradle, y front -> back, z up, the underside on z = 0):
  - one solid block MINUS the device models: each outline + clearance, swept straight up, so a device drops in;
  - two cable FURROWS behind the devices, the full length, open at both ends, a LAND between them;
  - at each device's side port a wide BAY straight out (the plug's overmould + its straight run), then a narrow
    groove that turns back into the front furrow;
  - screw-down cable CLIPS as ONE example of holding the cables (see SKILL.md "Holding the cables" for others): a
    strip across both furrows, one M3 into a heat-set insert in the land, a tab down into each furrow, each clip
    dropping into its own shallow recess so it sits square;
  - a CLOSED TUNNEL under the pockets for a flat bar that ties the two printed halves together, with rows of
    break-away HOURGLASS fins holding its roof up while printing (the bar knocks them out when pushed through);
  - two counterbored mounting holes in the front strip;
  - a corner-to-corner FIT TEST of one pocket (a thin floor + low walls) to print before the big part;
  - the cradle split into two plates, the seam in the wall between the pockets and in a gap between the fins.
Every run prints its checks, each shown to bite with a known-bad variant.

  example_cradle.py [--clr 1.0] [--bed 180] [--out out] [--render]
Out: out/stl/*.stl, out/3mf/cradle_{1,2}.3mf, out/3mf/clips.3mf, out/3mf/mixer_fit_test.3mf, out/cradle_section.png,
     out/clip_section.png
     (+ out/cradle_assembly.png with --render, needs Blender)
"""
import argparse, sys, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore", category=RuntimeWarning)   # trimesh: centre of mass of an empty overlap
from shapely.geometry import LineString, box as sbox
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/"print-part"/"scripts"))          # reuse the print-part helpers
from cad import *
from plate import pack, write_plates

ap = argparse.ArgumentParser()
ap.add_argument("--clr", type=float, default=1.0, help="clearance round each device (per side)")
ap.add_argument("--bed", type=float, default=180.0)
ap.add_argument("--out", default="out"); ap.add_argument("--render", action="store_true")
a = ap.parse_args()
out = Path(a.out)

# ---- the devices, from their spec sheets. EVERY number says where it came from. ----
DEVICES = {
    "mixer": dict(w=130.0, d=80.0, h=36.0, r=6.0,               # spec sheet: "130 x 80 x 36 mm", corner radius measured
                  port=dict(side="-x", y=52.0, z=16.0, plug_w=24.0, plug_h=9.0, plug_l=18.0,
                            source="manual p.18 'left side' drawing at 600 dpi, scale checked on the 8.9 mm USB-C socket")),
    "sampler": dict(w=96.0, d=80.0, h=32.0, r=4.0,               # spec sheet: "96 x 80 x 32 mm"
                    port=dict(side="+x", y=30.0, z=12.0, plug_w=16.0, plug_h=8.0, plug_l=16.0,
                              source="quick-start guide p.3 'right side' drawing, scale from the 80 mm depth")),
}

# ---- parameters ----
CLR = a.clr                                  # round each device (1.0 per side printed well in PETG for boxy gear)
FLOOR, SINK = 9.0, 14.0                      # material under the pockets (the bar tunnel is inside it), pocket depth
ZT = FLOOR; TOP = ZT + SINK                  # pocket floor, top face
END, GAP, FRONT, WALL = 34.0, 8.0, 14.0, 5.0 # end margins (room for the bays), between the devices, front strip, wall to the furrow
LANE_W, LANE_D, LAND, BACK = 12.0, 12.0, 10.0, 6.0   # two cable furrows, the land between them, the strip behind
GW = 9.0                                     # the narrow groove from a bay back to the furrow
BAR_W, BAR_T, FIT = 30.0, 3.0, 0.8           # the flat bar (30 x 3) and its fit (0.4 per side), +1 mm headroom on top
Z_BAR = 2.0                                  # the tunnel starts 2 mm above the underside
TUN = (Z_BAR, Z_BAR + BAR_T + FIT + 1.0)     # tunnel floor / roof
FIN = dict(pin=1.2, foot=1.4, waist=0.6, waist_z=0.5, cap=5.5, pitch=6.0, gap=0.2)   # break-away hourglass fins
HOLE = HOLES["M4"]; HOLE_Y = FRONT/2          # two mounting holes in the front strip
# ONE way to hold the cables - an example, not the answer (SKILL.md lists others): screw-down clips.
CLIP = dict(l=14.0, t=5.0, ov=2.0,           # length along the furrows, thickness, overlap onto the walls either side
            tab=4.0, tab_clr=0.3,            # the tab down into each furrow, its clearance per side
            recess=2.0, rec_clr=0.3,         # each clip drops into a recess this deep (+ clearance): it sits square
            pitch=20.0, margin=12.0)         # one every 20 mm, clear of the ends
CS = HOLES["M3"]; CS_LEN = 8.0               # an M3 x 8 socket head, counterbored flush into the clip
INS = dict(d=4.0, l=8.0)                     # heat-set insert hole in the land (CHECK the insert's data sheet;
                                             # 2.5 for a plain self-tapping M3 instead)
SF_H, SF_FLOOR, SF_M = 6.0, 2.5, 5.0          # fit test: wall height, floor, wall round the pocket

names = list(DEVICES); dA, dB = (DEVICES[n] for n in names)
W = END + dA["w"] + GAP + dB["w"] + END
Y0 = FRONT; D_DEV = max(dA["d"], dB["d"])
LANE_Y = [(Y0 + D_DEV + CLR + WALL, Y0 + D_DEV + CLR + WALL + LANE_W)]
LANE_Y.append((LANE_Y[0][1] + LAND, LANE_Y[0][1] + LAND + LANE_W))
Y_LAND = (LANE_Y[0][1] + LANE_Y[1][0])/2
D = LANE_Y[1][1] + BACK
PLACE = {names[0]: (END, Y0), names[1]: (END + dA["w"] + GAP, Y0)}
TUN_Y = (Y0 + D_DEV/2 - (BAR_W + FIT)/2, Y0 + D_DEV/2 + (BAR_W + FIT)/2)
HOLES_XY = [(40.0, HOLE_Y), (W - 40.0, HOLE_Y)]

def outline(dev, x, y, grow=0.0):
    """the device's plan outline (rounded rectangle) at (x, y), grown by `grow`"""
    return sbox(x + dev["r"], y + dev["r"], x + dev["w"] - dev["r"], y + dev["d"] - dev["r"]).buffer(dev["r"] + grow)

def device_model(n):
    dev = DEVICES[n]; x, y = PLACE[n]
    return extrude(outline(dev, x, y), dev["h"], ZT)            # sitting on its pocket floor

def bay_and_groove(n, clr):
    """the port bay (plug straight out) + the narrow groove turning back to the furrow"""
    dev = DEVICES[n]; p = dev["port"]; x, y = PLACE[n]; py = y + p["y"]
    if p["side"] == "-x": edge, s = x - clr, -1
    else: edge, s = x + dev["w"] + clr, 1
    x_out = edge + s*p["plug_l"]; x_turn = x_out - s*GW/2               # the cable turns just inside the bay's end
    bay = bx(edge - s*1.0, x_out, py - p["plug_w"]/2, py + p["plug_w"]/2, ZT, TOP + 1)
    groove = extrude(LineString([(x_turn, py), (x_turn, sum(LANE_Y[0])/2)]).buffer(GW/2, cap_style=2), TOP + 1 - ZT, ZT)
    return [bay, groove]

def hourglass(x, y0, y1, z0, z1, f=FIN):
    """one break-away fin, `pin` wide across the tunnel (y0..y1): foot -> thin waist (the break point, low) ->
    45-degree flanks -> a flat top at most `cap` long, `gap` under the roof. Nothing overhangs more than 45 degrees."""
    from shapely.geometry import Polygon
    from trimesh.creation import extrude_polygon
    zw = z0 + f["waist_z"]; top = min(f["cap"], f["waist"] + 2*(z1 - zw)); zt = zw + (top - f["waist"])/2
    prof = [(-f["foot"]/2, z0 - 0.3), (f["foot"]/2, z0 - 0.3), (f["foot"]/2, z0), (f["waist"]/2, zw), (top/2, zt),
            (top/2, z1), (-top/2, z1), (-top/2, zt), (-f["waist"]/2, zw), (-f["foot"]/2, z0)]
    m = extrude_polygon(Polygon([(x + u, z) for u, z in prof]).buffer(0), y1 - y0)
    m.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0], [0, 1, 0, 0], [0, 0, 0, 1.0]])); return m

SEAM = PLACE[names[1]][0] - GAP/2                                   # in the wall between the pockets
CY0, CY1 = LANE_Y[0][0] - CLIP["ov"], LANE_Y[1][1] + CLIP["ov"]      # the clip's extent across the furrows
CLIP_X = [x for x in np.arange(CLIP["margin"], W - CLIP["margin"] + 0.01, CLIP["pitch"])
          if abs(x - SEAM) > CLIP["l"]/2 + CLIP["rec_clr"] + 3]      # no recess across the seam
Z_CLIP = TOP - CLIP["recess"]                                        # the clip's underside, in its recess

def clip_at(xc, tab_clr=None):
    """one clip in place: a strip across both furrows, a tab down into each, a counterbored M3 over the land"""
    tc = CLIP["tab_clr"] if tab_clr is None else tab_clr; h = CLIP["l"]/2
    parts = [bx(xc - h, xc + h, CY0, CY1, Z_CLIP, Z_CLIP + CLIP["t"])]
    parts += [bx(xc - h, xc + h, y0 + tc, y1 - tc, Z_CLIP - CLIP["tab"], Z_CLIP + 0.01) for y0, y1 in LANE_Y]
    top = Z_CLIP + CLIP["t"]
    return diff(union(*parts), zcyl(CS["clear"]/2, xc, Y_LAND, Z_CLIP - 1, top + 1),
                zcyl(CS["cb_d"]/2, xc, Y_LAND, top - CS["cb_h"], top + 1))

def clip_cuts(xc, ins_d=None):
    """what a clip needs in the cradle: its recess (+ clearance) and the insert hole in the land"""
    h = CLIP["l"]/2 + CLIP["rec_clr"]; d = INS["d"] if ins_d is None else ins_d
    return [bx(xc - h, xc + h, CY0 - CLIP["rec_clr"], CY1 + CLIP["rec_clr"], Z_CLIP, TOP + 1),
            zcyl(d/2, xc, Y_LAND, Z_CLIP - INS["l"], Z_CLIP + 0.5)]
FIN_X = [x for x in np.arange(3.3, W - 3.0, FIN["pitch"]) if abs(x - SEAM) > FIN["pitch"]/2]   # a gap at the seam
FIN_ROWS = [TUN_Y[0] + (TUN_Y[1] - TUN_Y[0])*k/3 for k in (1, 2)]     # two rows: the roof spans ~10 mm

def build(clr=CLR, fins=True, hole_xy=HOLES_XY, clips=True, ins_d=None):
    body = bx(0, W, 0, D, 0, TOP)
    cuts = [extrude(outline(DEVICES[n], *PLACE[n], clr), TOP + 1 - ZT, ZT) for n in names]         # drop-in pockets
    cuts += [c for n in names for c in bay_and_groove(n, clr)]
    cuts += [bx(-1, W + 1, y0, y1, TOP - LANE_D, TOP + 1) for y0, y1 in LANE_Y]                     # furrows, both ends open
    if clips: cuts += [c for xc in CLIP_X for c in clip_cuts(xc, ins_d)]                              # clip recesses + inserts
    cuts += [bx(-1, W + 1, *TUN_Y, *TUN)]                                                           # the bar's closed tunnel
    for hx, hy in hole_xy:                                                                          # M4, counterbored from the top
        cuts += [zcyl(HOLE["clear"]/2, hx, hy, -1, TOP + 1), zcyl(HOLE["cb_d"]/2, hx, hy, TOP - HOLE["cb_h"], TOP + 1)]
    m = diff(body, *cuts)
    if fins:
        m = union(m, *[hourglass(x, yr - FIN["pin"]/2, yr + FIN["pin"]/2, TUN[0], TUN[1] - FIN["gap"]) for yr in FIN_ROWS for x in FIN_X])
    return clean(m)

print(f"cradle for {', '.join(names)}: {W:.0f} x {D:.0f} x {TOP:.0f}, pockets {SINK:.0f} deep, clearance {CLR}")
for n in names:
    p = DEVICES[n]["port"]; print(f"  {n} port {p['side']} at y {p['y']}, z {p['z']}  <- {p['source']}")
cradle = build(); plain = build(fins=False)                        # `plain`: the fins are in the bar's path on purpose
clips = {f"clip_{i + 1}": clip_at(xc) for i, xc in enumerate(CLIP_X)}
devs = {n: device_model(n) for n in names}
bar = bx(0.5, W - 0.5, TUN_Y[0] + FIT/2, TUN_Y[1] - FIT/2, TUN[0] + 0.05, TUN[0] + 0.05 + BAR_T)

# ---- the checks, printed every run, each proved to bite ----
report("cradle", cradle, bed=a.bed); print(f"  (longer than one {a.bed:.0f} bed: split into two plates below)")
worst = worst_overlap(list(devs.values()), [plain])
tight = worst_overlap(list(devs.values()), [build(clr=-0.5, fins=False)])
print(f"  devices vs cradle: {'none' if worst < 0.05 else f'{worst:.1f} mm3'}   (pockets 0.5 mm too small: {tight:.0f} mm3 - the check works)")
print(f"  flat bar vs tunnel: {overlap(bar, plain):.2f} mm3 without the fins; with them {overlap(bar, cradle):.0f} mm3 - "
      f"by design, the bar knocks {len(FIN_X)*len(FIN_ROWS)} fins out")
for n in names:
    p = DEVICES[n]["port"]; top_ = ZT + p["z"] + p["plug_h"]/2
    print(f"  {n} plug: bottom {ZT + p['z'] - p['plug_h']/2:.1f} over a bay floor at {ZT:.1f}, top {top_:.1f} "
          f"({'open bay, sticks up ' + format(top_ - TOP, '.1f') if top_ > TOP else 'inside'})")
def probes(xs, y, zs): return [(x, y, z) for x in xs for z in zs]
xs_ = np.linspace(PLACE[names[0]][0] + 10, PLACE[names[0]][0] + dA["w"] - 10, 6); zs_ = np.linspace(ZT + 1, TOP - 1, 4)
wall_y = Y0 + D_DEV + CLR + WALL/2
ok_wall = all(solid_at(plain, probes(xs_, wall_y, zs_)))
bad_wall = all(solid_at(plain, probes(xs_, wall_y - WALL, zs_)))            # the same probe line inside the pocket
roof = all(solid_at(plain, probes(xs_, sum(TUN_Y)/2, [(TUN[1] + ZT)/2])))
print(f"  wall pocket|furrow ({WALL:.0f}): solid {ok_wall} (the probe moved into the pocket: {bad_wall} - it bites); "
      f"floor over the tunnel {ZT - TUN[1]:.1f}: solid {roof}")
def ring_ok(m, x, y):
    """>= 1.5 mm of plastic round a counterbored hole: rings of probes outside the shank and the counterbore"""
    pts = [(x + r*np.cos(t), y + r*np.sin(t), z) for t in np.linspace(0, 2*np.pi, 16, endpoint=False)
           for z, r in [(z, HOLE["clear"]/2 + 1.5) for z in np.linspace(1, TOP - HOLE["cb_h"] - 1, 3)] +
                       [(z, HOLE["cb_d"]/2 + 1.5) for z in np.linspace(TOP - HOLE["cb_h"] + 0.5, TOP - 0.5, 2)]]
    return all(solid_at(m, pts))
print(f"  mounting holes: >= 1.5 mm plastic round both {all(ring_ok(plain, *h) for h in HOLES_XY)}  "
      f"(one moved 4 mm back, against the pocket: {ring_ok(build(fins=False, hole_xy=[(40.0, HOLE_Y + 4)]), 40.0, HOLE_Y + 4)} - it bites)")

# the clips: in place they touch nothing; tabs with no clearance must collide; the insert keeps >= 1.5 mm to the furrows
xc_ = CLIP_X[len(CLIP_X)//2]
c_ok = max(overlap(c, plain) for c in clips.values())
c_bad = overlap(clip_at(xc_, tab_clr=-0.3), plain)
def ins_ok(m):
    r = INS["d"]/2 + 1.5
    return all(solid_at(m, [(xc_ + r*np.cos(t), Y_LAND + r*np.sin(t), z) for t in np.linspace(0, 2*np.pi, 16, endpoint=False)
                            for z in np.linspace(Z_CLIP - INS["l"] + 0.5, Z_CLIP - 0.5, 3)]))
under_head = CLIP["t"] - CS["cb_h"]; into = CS_LEN - under_head
print(f"  {len(clips)} clips every {CLIP['pitch']:.0f} mm: in place vs the cradle {'none' if c_ok < 0.05 else f'{c_ok:.1f} mm3'} "
      f"(tabs 0.3 too wide: {c_bad:.0f} mm3 - it bites); insert Ø{INS['d']} keeps 1.5 mm to the furrows {ins_ok(plain)} "
      f"(Ø{LAND - 1.0:.0f}: {ins_ok(build(fins=False, ins_d=LAND - 1.0))} - it bites)")
print(f"  clip screw M3 x {CS_LEN:.0f}: head flush, {under_head:.1f} mm of clip under it, {into:.1f} mm into the "
      f"{INS['l']:.0f} mm insert hole ({'ok' if into <= INS['l'] - 0.5 else 'TOO LONG'})")

# ---- plates: two halves that thread onto the bar; the seam in the wall between the pockets, in a fin gap ----
halves = {"cradle_L": inter(cradle, bx(-1, SEAM, -1, D + 1, -1, TOP + 1)), "cradle_R": inter(cradle, bx(SEAM, W + 1, -1, D + 1, -1, TOP + 1))}
near = min(abs(x - SEAM) for x in FIN_X)
print(f"  seam x {SEAM:.1f}: {GAP - 2*CLR:.0f} mm wall between the pockets, nearest fin {near:.1f} mm away")
for k, m in halves.items(): report(k, m, bed=a.bed)
for k, m in {**halves, **{f"{n}_model": d for n, d in devs.items()}, "flat_bar": bar, "clip": clips["clip_1"]}.items(): export(m, k, out)
write_plates(pack({k: to_bed(m) for k, m in halves.items()}, bed=a.bed), out/"3mf"/"cradle", bed=a.bed)
flip = np.diag([1.0, -1.0, -1.0, 1.0])                                  # the clips print top face down, tabs up
write_plates(pack({k: to_bed(m.copy().apply_transform(flip)) for k, m in clips.items()}, bed=a.bed), out/"3mf"/"clips", bed=a.bed)

# ---- the fit test: the mixer pocket corner to corner, low walls on a thin floor - print THIS first ----
n0 = names[0]; pb = outline(DEVICES[n0], *PLACE[n0], CLR).bounds
x0, y0, x1, y1 = pb[0] - SF_M, pb[1] - SF_M, pb[2] + SF_M, pb[3] + SF_M
fit = union(bx(x0, x1, y0, y1, ZT - SF_FLOOR, ZT + 0.01), inter(plain, bx(x0, x1, y0, y1, ZT - 0.01, ZT + SF_H)))
fit = max(fit.split(only_watertight=False), key=lambda b: b.volume)   # a solid floor slab: a slice would open into the tunnel
above = bx(x0 - 1, x1 + 1, y0 - 1, y1 + 1, ZT + 0.05, ZT + SF_H + 1)
print(f"  {n0} fit test: the model clear {overlap(devs[n0], inter(fit, above)) < 0.05} "
      f"(no pocket at all: {overlap(devs[n0], bx(x0, x1, y0, y1, ZT + 0.05, ZT + SF_H)):.0f} mm3 - it bites)")
report(f"{n0}_fit_test", fit, bed=a.bed)
export(fit, f"{n0}_fit_test", out); write_plates(pack({f"{n0}_fit_test": to_bed(fit)}, bed=a.bed), out/"3mf"/f"{n0}_fit_test", bed=a.bed)

# ---- a labelled section through the mixer: pocket, furrow, tunnel, fins ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
xs = PLACE[n0][0] + dA["w"]/2; xs = min(FIN_X, key=lambda x: abs(x - xs))          # through a fin
sec = section(cradle, [xs, 0, 0], [1, 0, 0], drop=0)
fig, ax = plt.subplots(figsize=(9, 3.6))
for g in getattr(sec, "geoms", [sec]):
    if g.is_empty: continue
    x_, y_ = g.exterior.xy; ax.fill(x_, y_, fc="#3b7dd8", ec="#123", lw=0.8)
    for hl in g.interiors: x_, y_ = hl.xy; ax.fill(x_, y_, fc="white", ec="#123", lw=0.8)
ax.add_patch(plt.Rectangle((Y0, ZT), dA["d"], dA["h"], fc="none", ec="#c0392b", ls="--", lw=1.2))
def callout(t, xy, xyt):
    ax.annotate(t, xy=xy, xytext=xyt, fontsize=8.5, weight="bold", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#3b7dd8", lw=1.4), arrowprops=dict(arrowstyle="-", color="#222", lw=1))
callout(f"{n0} (model)", (Y0 + dA["d"]/2, ZT + SINK + 8), (Y0 + dA["d"]/2, TOP + 20))
callout(f"pocket +{CLR} mm", (Y0 - CLR, ZT + 6), (Y0 - 4, TOP + 12))
callout("cable furrows", (sum(LANE_Y[0])/2, TOP - LANE_D/2), (sum(LANE_Y[0])/2 + 8, TOP + 12))
callout("flat-bar tunnel", (TUN_Y[0] + 3, sum(TUN)/2), (TUN_Y[0] - 14, -8))
callout("break-away fin", (FIN_ROWS[1], TUN[0] + 1), (FIN_ROWS[1] - 4, -8))
callout(f"floor over the tunnel {ZT - TUN[1]:.1f}", (TUN_Y[1] - 2, (TUN[1] + ZT)/2), (TUN_Y[1] + 38, -8))
ax.set_aspect("equal"); ax.set_xlim(-8, D + 8); ax.set_ylim(-14, TOP + 26); ax.grid(alpha=0.25)
ax.set_xlabel("y (mm, front -> back)"); ax.set_ylabel("z (mm)"); ax.set_title(f"section x = {xs:.1f} through the {n0} and a fin", fontsize=10)
fig.savefig(str(out/"cradle_section.png"), dpi=100, bbox_inches="tight", facecolor="white"); print(f"  -> {out/'cradle_section.png'}")

# ---- a labelled section through a clip in place: the furrows, the land with its insert, the recess, the tabs ----
sc = section(cradle, [xc_, 0, 0], [1, 0, 0], drop=0); scl = section(clips[f"clip_{len(CLIP_X)//2 + 1}"], [xc_, 0, 0], [1, 0, 0], drop=0)
fig, ax = plt.subplots(figsize=(7, 3.8))
for geo, fc in ((sc, "#3b7dd8"), (scl, "#e08a2e")):
    for g in getattr(geo, "geoms", [geo]):
        if g.is_empty: continue
        x_, y_ = g.exterior.xy; ax.fill(x_, y_, fc=fc, ec="#123", lw=0.8)
        for hl in g.interiors: x_, y_ = hl.xy; ax.fill(x_, y_, fc="white", ec="#123", lw=0.8)
def callout2(t, xy, xyt, ec="#3b7dd8"):
    ax.annotate(t, xy=xy, xytext=xyt, fontsize=8.5, weight="bold", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=ec, lw=1.4), arrowprops=dict(arrowstyle="-", color="#222", lw=1))
callout2("clip (printed, top face down)", ((CY0 + CY1)/2 + 12, Z_CLIP + CLIP["t"]), ((CY0 + CY1)/2 + 16, TOP + 16), "#e08a2e")
callout2(f"tab {CLIP['tab']:.0f} deep, {CLIP['tab_clr']} clear", (sum(LANE_Y[1])/2, Z_CLIP - CLIP["tab"]/2), (LANE_Y[1][1] + 16, Z_CLIP - 9), "#e08a2e")
callout2(f"M3 x {CS_LEN:.0f}, head flush", (Y_LAND, Z_CLIP + CLIP["t"] - 1), (LANE_Y[0][0] - 16, TOP + 14), "#e08a2e")
callout2(f"insert Ø{INS['d']} x {INS['l']:.0f} in the land", (Y_LAND + INS["d"]/2, Z_CLIP - INS["l"]/2), (LANE_Y[0][0] - 28, Z_CLIP - 17))
callout2(f"recess {CLIP['recess']:.0f} deep, +{CLIP['rec_clr']}", (CY1 + 0.3, TOP - 1), (CY1 + 18, TOP + 4))
callout2("cable furrow", (sum(LANE_Y[0])/2, TOP - LANE_D + 2), (LANE_Y[0][0] - 28, TOP + 2))
ax.set_aspect("equal"); ax.set_xlim(LANE_Y[0][0] - 50, D + 30); ax.set_ylim(TOP - LANE_D - 20, TOP + 22); ax.grid(alpha=0.25)
ax.set_xlabel("y (mm, front -> back)"); ax.set_ylabel("z (mm)")
ax.set_title(f"section x = {xc_:.1f} through a clip in place - one way to hold the cables, not the only one", fontsize=10)
fig.savefig(str(out/"clip_section.png"), dpi=100, bbox_inches="tight", facecolor="white"); print(f"  -> {out/'clip_section.png'}")

if a.render:
    sys.path.insert(0, str(HERE.parents[1]/"blender-render"/"scripts"))
    from render import render
    p = DEVICES[names[0]]["port"]
    render([(cradle, "part"), (devs[names[0]], "device", names[0]), (devs[names[1]], "device", names[1]), (bar, "bar"),
            (cradle, "part", "cradle (printed)", (W*0.8, D - BACK/2, TOP)),
            (bar, "bar", "flat bar (in its tunnel)", (0.5, sum(TUN_Y)/2, TUN[0] + BAR_T)),
            (cradle, "part", f"{names[0]} port bay", (PLACE[names[0]][0] - CLR - p["plug_l"]/2, Y0 + p["y"], ZT)),
            (cradle, "part", "cable furrows", (W*0.55, sum(LANE_Y[0])/2, TOP - LANE_D)),
            *[(c, "clip") for c in clips.values()],
            (clips["clip_1"], "clip", "cable clip (one M3 each)", (CLIP_X[0], CY1, Z_CLIP + CLIP["t"]))],
           colors=dict(part=[0.23, 0.49, 0.85], device=[0.62, 0.64, 0.67], bar=[0.85, 0.86, 0.88], clip=[0.88, 0.54, 0.18]),
           camera=dict(target=[W/2, D/2, 0], loc=[W/2 - 210, D + 260, 330], lens=45), out=out/"cradle_assembly.png",
           title="Cradle for two devices", subtitle="blue = printed, orange = the cable clips, grey = the devices (spec-sheet models)")
