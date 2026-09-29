#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy","pillow","matplotlib"]
# ///
"""drawing_measure.py - read millimetres off a manufacturer's dimension drawing (a manual page, a spec sheet).

Manuals rarely dimension the things you need (where exactly is the power port on the side?), but their drawings are
usually to scale. So: render the page at 600 dpi, calibrate the scale on a feature whose size you KNOW (the device's
depth from the spec sheet, a connector of standard size), check it on a SECOND known feature, then measure.

  pdftoppm -r 600 -f 18 -l 18 -png manual.pdf page              # one page -> page-18.png (poppler-utils)
  drawing_measure.py page-18.png --grid grid.png [--step 100] [--crop x0,y0,x1,y1]
      -> the page (or a crop) with a labelled pixel grid: read the pixel coordinates of the points you need off it
  drawing_measure.py page-18.png --ref 812,1440,3510,1440,114 --check socket:1402,1290,1507,1290,8.94 \\
                     --origin 812,1440 --pt port:1402,1302 --pt sd:1020,1302 --dist slot:1000,1250,1000,1350 \\
                     --out marked.png
      --ref x1,y1,x2,y2,MM    two pixels a known length apart: the scale, and the drawing's axis (u along it)
      --check name:...,MM     a second known feature: prints measured vs known (a few % = trust it; more = the
                              drawing isn't to scale there, or you picked the wrong edges)
      --origin x,y            where positions are measured from (a device edge / corner)
      --pt name:x,y           a point: its position from the origin, u along the ref axis, v across it (mm)
      --dist name:x1,y1,x2,y2 a length (mm)
      --out marked.png        the page with every point / length drawn and named - show it, keep it with the part

Write the result into the part script WITH its source, e.g.
    PORT_Y = 57.5    # manual p.18 "right side" drawing, 600 dpi, scale from the 114 mm depth, socket checked (9.4 vs 8.9)
"""
import argparse
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__.split("\n\n")[0])
ap.add_argument("image")
ap.add_argument("--grid"); ap.add_argument("--step", type=int, default=100); ap.add_argument("--crop")
ap.add_argument("--ref"); ap.add_argument("--check", action="append", default=[])
ap.add_argument("--origin"); ap.add_argument("--pt", action="append", default=[]); ap.add_argument("--dist", action="append", default=[])
ap.add_argument("--out")
a = ap.parse_args()
nums = lambda s: [float(v) for v in s.split(",")]
def named(s): n, v = s.split(":", 1); return n, nums(v)

img = Image.open(a.image).convert("RGB")
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

if a.grid:                                             # a pixel grid to read coordinates off
    x0, y0, x1, y1 = (int(v) for v in nums(a.crop)) if a.crop else (0, 0, img.width, img.height)
    sub = img.crop((x0, y0, x1, y1)); w, h = sub.size
    fig, ax = plt.subplots(figsize=(min(24, 4 + w/150), min(24, 4 + h/150)))
    ax.imshow(sub, extent=[x0, x1, y1, y0])
    ax.set_xticks(np.arange((x0//a.step)*a.step, x1, a.step)); ax.set_yticks(np.arange((y0//a.step)*a.step, y1, a.step))
    ax.grid(color="red", alpha=0.45, lw=0.6); ax.tick_params(labelsize=7); plt.xticks(rotation=90)
    fig.tight_layout(); fig.savefig(a.grid, dpi=110); print(f"-> {a.grid}: pixels {x0}..{x1} x {y0}..{y1}, grid every {a.step} px")

if a.ref:
    rx1, ry1, rx2, ry2, rmm = nums(a.ref)
    rv = np.array([rx2 - rx1, ry2 - ry1]); rpx = float(np.hypot(*rv)); mmpx = rmm/rpx
    u = rv/rpx; v = np.array([-u[1], u[0]])            # u along the reference, v across it (a scan may be rotated)
    print(f"scale: {rmm} mm over {rpx:.1f} px -> {mmpx:.5f} mm/px ({1/mmpx*25.4:.0f} px per inch of the real part)")
    marks = [("ref", (rx1, ry1, rx2, ry2), f"{rmm:g} (ref)")]
    for s in a.check:
        n, (x1_, y1_, x2_, y2_, mm) = named(s); got = float(np.hypot(x2_ - x1_, y2_ - y1_))*mmpx
        print(f"check {n}: measured {got:.2f} mm, known {mm:g} mm -> {100*(got - mm)/mm:+.1f} %")
        marks.append((n, (x1_, y1_, x2_, y2_), f"{got:.1f} (known {mm:g})"))
    o = np.array(nums(a.origin)) if a.origin else np.array([rx1, ry1])
    pts = []
    for s in a.pt:
        n, (x, y) = named(s); d = (np.array([x, y]) - o)*mmpx
        print(f"point {n}: u {d @ u:8.2f} mm   v {d @ v:8.2f} mm   (from the origin, u along the ref)")
        pts.append((n, x, y, f"u {d @ u:.1f} / v {d @ v:.1f}"))
    for s in a.dist:
        n, (x1_, y1_, x2_, y2_) = named(s); got = float(np.hypot(x2_ - x1_, y2_ - y1_))*mmpx
        print(f"length {n}: {got:.2f} mm"); marks.append((n, (x1_, y1_, x2_, y2_), f"{got:.1f}"))
    if a.out:
        fig, ax = plt.subplots(figsize=(12, 12*img.height/img.width)); ax.imshow(img); ax.axis("off")
        ax.plot(*o, "c+", ms=18, mew=2); ax.annotate("origin", o, xytext=(8, 8), textcoords="offset points", color="c", weight="bold")
        for n, (x1_, y1_, x2_, y2_), t in marks:
            ax.plot([x1_, x2_], [y1_, y2_], "-", color="#e67e22", lw=2)
            ax.annotate(f"{n}: {t} mm", ((x1_ + x2_)/2, (y1_ + y2_)/2), xytext=(0, 10), textcoords="offset points",
                        ha="center", fontsize=9, weight="bold", color="#e67e22", bbox=dict(fc="white", ec="#e67e22", lw=1))
        for n, x, y, t in pts:
            ax.plot(x, y, "mo", ms=6)
            ax.annotate(f"{n}: {t} mm", (x, y), xytext=(10, -12), textcoords="offset points", fontsize=9, weight="bold",
                        color="m", bbox=dict(fc="white", ec="m", lw=1))
        fig.tight_layout(); fig.savefig(a.out, dpi=100); print(f"-> {a.out}")
