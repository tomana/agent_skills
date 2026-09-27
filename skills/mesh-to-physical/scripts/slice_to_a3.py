#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "trimesh[easy]",
#   "matplotlib",
# ]
# ///
"""
Slice a mesh into horizontal contour rings and lay them out at 1:1 on A3
pages as a printable multi-page PDF. Print at 100% (no "fit to page"),
bend metal rod to each loop, stack + connect into a wireframe armature.

Up axis is Y by default (Blender Y-up export). Each slice is taken
perpendicular to the up axis; contours are drawn in the horizontal plane
(X = horizontal, Z = depth) in a CONSISTENT global frame so the rings
stack in vertical alignment. A 50 mm calibration square + a 50 mm grid
print on every page so you can (a) verify scale and (b) align taped tiles.

Example:
    ./slice_to_a3.py --stl model.stl \
        --out model_rings_A3.pdf --spacing-mm 50
"""
import argparse, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy import ndimage
import trimesh

# --- A3 (mm) ---
A3_W, A3_H = 297.0, 420.0
MM_PER_IN = 25.4


def load_mesh(path):
    m = trimesh.load(path, process=False)
    if isinstance(m, trimesh.Scene):
        m = m.dump(concatenate=True)
    return m


def horizontal_loops(mesh, y, up_idx, plane_axes):
    """Return list of (n,2) polylines (mm-unscaled, raw mesh units) at height y."""
    normal = [0, 0, 0]; normal[up_idx] = 1.0
    origin = [0, 0, 0]; origin[up_idx] = y
    sec = mesh.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        return []
    loops = []
    for poly in sec.discrete:          # list of (n,3) connected polylines
        loops.append(poly[:, plane_axes])
    return loops


def parallel_loops(M, n_idx, level, paxes, vbase, s):
    """Slice M with a plane normal to axis n_idx at `level`; project to the two
    page axes `paxes` ([page_x_axis, page_y_axis]); subtract vbase from page-y if set."""
    normal = [0.0, 0.0, 0.0]; normal[n_idx] = 1.0
    origin = [0.0, 0.0, 0.0]; origin[n_idx] = level
    sec = M.section(plane_origin=origin, plane_normal=normal)
    out = []
    if sec is not None:
        for poly in sec.discrete:
            P = poly[:, paxes].astype(float)
            if vbase is not None:
                P[:, 1] -= vbase
            out.append(P * s)
    return out


# fastening-mark styles, keyed by the *intersecting* family
FAM_STYLE = {
    "ring": ("#1f77b4", "+"),   # blue plus
    "rib":  ("#d62728", "x"),   # red cross
    "z":    ("#2ca02c", "D"),   # green diamond
}


def crossings(loops, f):
    """Points along `loops` where the scalar field f(x, y) crosses zero
    (i.e. where the contour meets another piece's plane). f takes arrays."""
    out = []
    for pl in loops:
        fv = f(pl[:, 0], pl[:, 1])
        s0, s1 = fv[:-1], fv[1:]
        for i in np.where(((s0 <= 0) & (s1 > 0)) | ((s0 >= 0) & (s1 < 0)))[0]:
            d = s0[i] - s1[i]
            t = s0[i] / d if d != 0 else 0.5
            out.append(pl[i] + t * (pl[i + 1] - pl[i]))
    return np.array(out) if out else np.empty((0, 2))


def tile_windows(lo, hi, page, step):
    """1-D tiling: returns list of (start, end) windows of length `page`
    covering [lo, hi], stepping by `step` (< page => overlap)."""
    span = hi - lo
    if span <= page:
        c = 0.5 * (lo + hi)
        return [(c - page / 2, c + page / 2)]
    n = math.ceil((span - page) / step) + 1
    return [(lo + i * step, lo + i * step + page) for i in range(n)]


def silhouette(M, ah, av, s, vbase=None, res=140):
    """Filled 2D silhouette of mesh M projected onto world axes (ah, av), in mm.
    Returns (boolean grid, extent=[x0,x1,y0,y1]) for imshow(origin='lower')."""
    V = M.vertices
    h = V[:, ah] * s
    v = V[:, av] * s
    if vbase is not None:
        v = v - vbase * s
    H, xe, ye = np.histogram2d(h, v, bins=res)
    occ = ndimage.binary_fill_holes(ndimage.binary_closing(H.T > 0, iterations=2))
    return occ, [xe[0], xe[-1], ye[0], ye[-1]]


def _draw_minimap_one(fig, rect, mm):
    """One locator inset: figure silhouette + red marker for this slice."""
    ax = fig.add_axes(rect, zorder=10)
    ax.set_facecolor("white")
    occ, ext = mm["grid"], mm["extent"]
    ax.imshow(occ, origin="lower", extent=ext, cmap="Greys",
              aspect="equal", interpolation="nearest", alpha=0.45, zorder=1)
    k = mm["kind"]
    ticks = mm.get("ticks")
    val = mm.get("value")
    if k in ("hline", "vline") and ticks is not None:
        # faint trace of every slice + mm marks; the current one in red
        for t in ticks:
            cur = abs(t - val) < 1e-6
            col = "red" if cur else "0.72"
            (ax.axhline if k == "hline" else ax.axvline)(
                t, color=col, lw=1.3 if cur else 0.4, zorder=3 if cur else 2)
            if k == "hline":
                ax.text(-0.02, t, f"{t:.0f}", transform=ax.get_yaxis_transform(),
                        ha="right", va="center", fontsize=4.0, clip_on=False,
                        color="red" if cur else "0.45")
            else:
                ax.text(t, 1.02, f"{t:.0f}", transform=ax.get_xaxis_transform(),
                        ha="center", va="bottom", rotation=90, fontsize=4.0,
                        clip_on=False, color="red" if cur else "0.45")
    elif k == "hline":
        ax.axhline(val, color="red", lw=1.3, zorder=3)
    elif k == "vline":
        ax.axvline(val, color="red", lw=1.3, zorder=3)
    elif k == "angle":
        L = max(abs(x) for x in ext) * 1.3
        dx, dy = math.cos(mm["angle"]), math.sin(mm["angle"])
        ax.plot([-dx * L, dx * L], [-dy * L, dy * L], color="red", lw=1.3, zorder=3)
        ax.plot([0], [0], "o", color="red", ms=2.5, zorder=4)
    elif k == "loops":                      # draw the actual slice outline in red
        for pl in mm["loops"]:
            ax.plot(pl[:, 0], pl[:, 1], color="red", lw=1.1, zorder=3)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor("0.5"); sp.set_linewidth(0.6)
    if mm.get("label"):
        ax.set_title(mm["label"], fontsize=6, color="0.35", pad=2)


def draw_minimaps(fig, mmlist):
    """Right-aligned row of locator insets in the top-right corner."""
    w, h, gap, y = 0.185, 0.150, 0.012, 0.820
    x0 = 0.980 - (len(mmlist) * w + (len(mmlist) - 1) * gap)
    for i, mm in enumerate(mmlist):
        _draw_minimap_one(fig, [x0 + i * (w + gap), y, w, h], mm)


def draw_page(pdf, layers, win_x, win_z, header, grid_mm, margin_mm,
              tile_label, calib_mm=50.0, minimaps=None, marks=None):
    """layers: list of (loops_mm, color, lw) drawn back-to-front."""
    fig = plt.figure(figsize=(A3_W / MM_PER_IN, A3_H / MM_PER_IN))
    ax = fig.add_axes([0, 0, 1, 1])  # full-bleed; data units == page mm
    ax.set_xlim(win_x[0], win_x[1])
    ax.set_ylim(win_z[0], win_z[1])
    ax.set_aspect("equal")
    ax.axis("off")

    # 50 mm grid in global mm coords -> continuous across taped tiles
    gx0 = math.floor(win_x[0] / grid_mm) * grid_mm
    gz0 = math.floor(win_z[0] / grid_mm) * grid_mm
    for gx in np.arange(gx0, win_x[1] + grid_mm, grid_mm):
        ax.axvline(gx, color="0.85", lw=0.4, zorder=0)
    for gz in np.arange(gz0, win_z[1] + grid_mm, grid_mm):
        ax.axhline(gz, color="0.85", lw=0.4, zorder=0)
    # major axes (model centerlines) for vertical stacking alignment
    ax.axvline(0, color="0.6", lw=0.6, ls="--", zorder=1)
    ax.axhline(0, color="0.6", lw=0.6, ls="--", zorder=1)

    # the contour loops, layer by layer (weak overlay under, strong primary over)
    for zo, (loops_mm, color, lw) in enumerate(layers):
        for pl in loops_mm:
            ax.plot(pl[:, 0], pl[:, 1], color=color, lw=lw, zorder=4 + zo)

    # fastening crosses: where this piece meets the other families
    if marks:
        for m in marks:
            P = m["pts"]
            ax.plot(P[:, 0], P[:, 1], linestyle="none", marker=m["marker"],
                    color=m["color"], ms=7, mew=1.4, zorder=8)
            for p in P:
                ax.text(p[0] + 2.5, p[1] + 2.5, m["label"], fontsize=4.2,
                        color=m["color"], zorder=8, clip_on=True)

    # printable-area crop marks (corner ticks inset by margin)
    mx0, mx1 = win_x[0] + margin_mm, win_x[1] - margin_mm
    mz0, mz1 = win_z[0] + margin_mm, win_z[1] - margin_mm
    t = 6.0
    for (cx, cz, dx, dz) in [(mx0, mz0, 1, 1), (mx1, mz0, -1, 1),
                             (mx0, mz1, 1, -1), (mx1, mz1, -1, -1)]:
        ax.plot([cx, cx + dx * t], [cz, cz], color="black", lw=0.8, zorder=6)
        ax.plot([cx, cx], [cz, cz + dz * t], color="black", lw=0.8, zorder=6)

    # 50 mm calibration square (data coords => prints exactly 50 mm at 100%)
    sx, sz = win_x[0] + margin_mm + 4, win_z[0] + margin_mm + 4
    ax.add_patch(plt.Rectangle((sx, sz), calib_mm, calib_mm, fill=False,
                               edgecolor="red", lw=0.8, zorder=6))
    ax.text(sx + calib_mm / 2, sz - 4, f"{calib_mm:.0f} mm — print at 100%",
            ha="center", va="top", color="red", fontsize=6, transform=ax.transData)

    # fastening legend (family colour/marker), bottom-right
    if marks:
        seen = []
        for m in marks:
            if m["fam"] not in [f[0] for f in seen]:
                seen.append((m["fam"], m["color"], m["marker"]))
        for i, (fam, col, mk) in enumerate(seen):
            yy = 0.018 + i * 0.020
            ax.plot([0.855], [yy], marker=mk, color=col, ms=7, mew=1.4,
                    transform=ax.transAxes, clip_on=False, zorder=8)
            ax.text(0.872, yy, f"fasten to {fam}", transform=ax.transAxes,
                    va="center", ha="left", fontsize=6, color=col, zorder=8)

    # header + tile label (top-left, leaving the top-right corner for the mini-map)
    ax.text(0.015, 0.987, header, ha="left", va="top",
            transform=ax.transAxes, fontsize=8, family="monospace")
    if tile_label:
        ax.text(0.015, 0.968, tile_label, ha="left", va="top",
                transform=ax.transAxes, fontsize=7, family="monospace", color="0.3")

    if minimaps:
        draw_minimaps(fig, minimaps)

    pdf.savefig(fig)
    plt.close(fig)


def emit_panel(pdf, layers, header_base, grid_mm, margin_mm,
               page_step_x, page_step_z, minimaps=None, marks=None):
    """Tile the layers across A3 page(s). layers: list of (loops_mm, color, lw). Returns page count."""
    allpts = np.vstack([pl for loops, _, _ in layers for pl in loops])
    x0, x1 = allpts[:, 0].min(), allpts[:, 0].max()
    z0, z1 = allpts[:, 1].min(), allpts[:, 1].max()
    cols = tile_windows(x0 - 6, x1 + 6, A3_W, page_step_x)
    rows = tile_windows(z0 - 6, z1 + 6, A3_H, page_step_z)
    R, C = len(rows), len(cols)
    pages = 0
    for ri, wz in enumerate(reversed(rows)):       # top page first
        for ci, wx in enumerate(cols):
            tile_lbl = f"tile r{ri+1}/{R} c{ci+1}/{C}" if (R * C > 1) else ""
            header = f"{header_base} | size {x1-x0:.0f}x{z1-z0:.0f} mm"
            draw_page(pdf, layers, wx, wz, header, grid_mm, margin_mm, tile_lbl,
                      minimaps=minimaps, marks=marks)
            pages += 1
    return pages


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--spacing-mm", type=float, default=50.0,
                    help="vertical gap between rings (default 50)")
    ap.add_argument("--up", choices=["x", "y", "z"], default="y",
                    help="up axis of the mesh (default y, Blender Y-up)")
    ap.add_argument("--unit-scale", type=float, default=1000.0,
                    help="mesh-units -> mm (default 1000: metres->mm)")
    ap.add_argument("--target-height-mm", type=float, default=None,
                    help="scale so the up-axis height equals this (overrides --unit-scale)")
    ap.add_argument("--margin-mm", type=float, default=10.0,
                    help="blank printer border / tile overlap (default 10)")
    ap.add_argument("--grid-mm", type=float, default=50.0)
    ap.add_argument("--mode", choices=["parallel", "horizontal", "fan"], default="parallel",
                    help="parallel stacked slices (see --slice-normal), or a vertical fan of radial ribs")
    ap.add_argument("--slice-normal", choices=["x", "y", "z"], default="y",
                    help="parallel mode: axis the slicing planes step along. "
                         "y=horizontal rings (footprint); z=coronal (front view, captures arms); x=sagittal (side view)")
    ap.add_argument("--fan", type=int, default=4,
                    help="fan mode: number of radial planes through the up-axis (e.g. 4 or 8)")
    ap.add_argument("--overlay-stl", default=None,
                    help="second mesh (e.g. outer shell) drawn as a weak reference outline")
    ap.add_argument("--primary-lw", type=float, default=1.6)
    ap.add_argument("--overlay-lw", type=float, default=0.6)
    ap.add_argument("--overlay-color", default="0.6", help="matplotlib color for the weak overlay")
    ap.add_argument("--no-minimap", action="store_true",
                    help="disable the upper-right locator inset")
    ap.add_argument("--marks", action="store_true",
                    help="stamp colour-coded fastening crosses where this piece meets the "
                         "other families (rings/ribs/Z-slices). Defines the full cage via --cage-*")
    ap.add_argument("--cage-rings-mm", type=float, default=30.0,
                    help="--marks: ring spacing of the cage to fasten to")
    ap.add_argument("--cage-z-mm", type=float, default=30.0,
                    help="--marks: Z-slice spacing of the cage to fasten to")
    ap.add_argument("--cage-fan", type=int, default=4,
                    help="--marks: number of radial ribs in the cage to fasten to")
    args = ap.parse_args()

    up_idx = {"x": 0, "y": 1, "z": 2}[args.up]
    plane_axes = [i for i in (0, 1, 2) if i != up_idx]  # the two horizontal axes

    mesh = load_mesh(args.stl)
    overlay = load_mesh(args.overlay_stl) if args.overlay_stl else None
    vmin = mesh.vertices.min(axis=0); vmax = mesh.vertices.max(axis=0)
    base = vmin[up_idx]
    top = vmax[up_idx]
    raw_h = top - base
    if args.target_height_mm:
        s = args.target_height_mm / raw_h
        print(f"target height {args.target_height_mm} mm -> unit-scale {s:.2f}")
    else:
        s = args.unit_scale
    height_mm = (top - base) * s
    print(f"mesh loaded: {len(mesh.faces)} faces")
    print(f"height ({args.up}) = {height_mm:.1f} mm  "
          f"plane extents {(vmax-vmin)[plane_axes]*s} mm")

    page_step_x = A3_W - args.margin_mm  # overlap = margin
    page_step_z = A3_H - args.margin_mm

    # --- cage spec for fastening marks (same for every page, regardless of family drawn) ---
    cage_ring_heights, cage_z_depths, cage_rib_angles = [], [], []
    if args.marks:
        dax = plane_axes[1]                       # depth axis (Z when up=Y)
        rspc = args.cage_rings_mm / s
        cage_ring_heights = [(lv - base) * s
                             for lv in np.arange(base + rspc * 0.5, top, rspc)]
        zspc = args.cage_z_mm / s
        cage_z_depths = [lv * s
                         for lv in np.arange(vmin[dax] + zspc * 0.5, vmax[dax], zspc)]
        nfan = max(1, args.cage_fan)
        cage_rib_angles = [i * math.pi / nfan for i in range(nfan)]

    if args.mode == "fan":
        # vertical ribs: N planes all containing the up-axis, rotated around it.
        # plane i has horizontal in-plane direction d=(cosθ,0,sinθ) (when up=Y),
        # horizontal normal n perpendicular to d. Profile coord = (signed dist along d, height).
        a, b = plane_axes          # the two horizontal axes (e.g. 0=X, 2=Z when up=Y)
        N = max(1, args.fan)
        # mini-map: top-down silhouette (look down the up-axis), red diameter per rib
        sil = None if args.no_minimap else \
            silhouette(overlay if overlay is not None else mesh, a, b, s)

        def fan_loops(M, ct, st):
            normal = [0.0, 0.0, 0.0]
            normal[a], normal[b] = -st, ct           # n ⟂ d, horizontal
            sec = M.section(plane_origin=[0, 0, 0], plane_normal=normal)
            out = []
            if sec is not None:
                for poly in sec.discrete:
                    P = poly.astype(float)
                    horiz = P[:, a] * ct + P[:, b] * st   # projection onto d
                    vert = P[:, up_idx] - base
                    out.append(np.column_stack([horiz, vert]) * s)
            return out

        n_pages = 0
        with PdfPages(args.out) as pdf:
            for i in range(N):
                theta = i * math.pi / N
                ct, st = math.cos(theta), math.sin(theta)
                prim = fan_loops(mesh, ct, st)
                if not prim:
                    print(f"rib {i+1}/{N}: no intersection"); continue
                layers = []
                if overlay is not None:
                    ov = fan_loops(overlay, ct, st)
                    if ov:
                        layers.append((ov, args.overlay_color, args.overlay_lw))
                layers.append((prim, "black", args.primary_lw))
                deg = round(math.degrees(theta))
                hdr = f"RADIAL RIB {i+1:02d}/{N}  @ {deg:3d} deg  | through centre axis"
                mms = None if sil is None else [{
                    "grid": sil[0], "extent": sil[1], "kind": "angle",
                    "angle": theta, "label": f"top-down  rib {i+1}/{N}  {deg}°"}]
                marks = []
                if args.marks:
                    rc, rm = FAM_STYLE["ring"]      # rings cross this rib at each height
                    for hk in cage_ring_heights:
                        pts = crossings(prim, lambda x, y, hk=hk: y - hk)
                        if len(pts):
                            marks.append({"pts": pts, "color": rc, "marker": rm,
                                          "fam": "ring", "label": f"h{hk:.0f}"})
                    zc, zm = FAM_STYLE["z"]          # Z-slices cross at d = z/sinθ
                    if abs(st) > 1e-6:
                        for zj in cage_z_depths:
                            d0 = zj / st
                            pts = crossings(prim, lambda x, y, d0=d0: x - d0)
                            if len(pts):
                                marks.append({"pts": pts, "color": zc, "marker": zm,
                                              "fam": "z", "label": f"z{zj:.0f}"})
                n_pages += emit_panel(pdf, layers, hdr, args.grid_mm, args.margin_mm,
                                      page_step_x, page_step_z, minimaps=mms,
                                      marks=marks or None)
        print(f"\nwrote {args.out}\nribs: {N}   pages: {n_pages}")
        return

    # --- parallel stacked slices, normal to the chosen axis ---
    n_idx = {"x": 0, "y": 1, "z": 2}[args.slice_normal]
    is_rings = (n_idx == up_idx)
    if is_rings:
        paxes = list(plane_axes); vbase = None      # footprint (no up axis in plane)
    else:
        px = [i for i in (0, 1, 2) if i not in (n_idx, up_idx)][0]
        paxes = [px, up_idx]; vbase = base          # page-y = height above base

    spacing_mesh = args.spacing_mm / s
    lo, hi = vmin[n_idx], vmax[n_idx]
    levels = np.arange(lo + spacing_mesh * 0.5, hi, spacing_mesh)
    # every slice position (mm) in the marker coordinate, for the ruler traces
    tick_vals = [((lv - base) * s if is_rings else lv * s) for lv in levels]

    # mini-map: silhouette + a sweeping line at this slice's position.
    #   rings (cut along up-axis)  -> front view (X,height),  horizontal marker
    #   z-slice (coronal)          -> side  view (Z,height),  vertical marker
    #   x-slice (sagittal)         -> front view (X,height),  vertical marker
    sil = sil_top = None
    if not args.no_minimap:
        silmesh = overlay if overlay is not None else mesh
        sil_top = silhouette(silmesh, plane_axes[0], plane_axes[1], s)  # top-down (X,Z)
        if is_rings:
            sil = silhouette(silmesh, plane_axes[0], up_idx, s, vbase=base)
            mm_kind, mm_view = "hline", "front"
        else:
            ah = 2 if args.slice_normal == "z" else 0
            sil = silhouette(silmesh, ah, up_idx, s, vbase=base)
            mm_kind = "vline"
            mm_view = "side" if args.slice_normal == "z" else "front"

    n_pages = 0
    n_sl = 0
    with PdfPages(args.out) as pdf:
        for level in levels:
            prim = parallel_loops(mesh, n_idx, level, paxes, vbase, s)
            if not prim:
                continue
            layers = []
            if overlay is not None:
                ov = parallel_loops(overlay, n_idx, level, paxes, vbase, s)
                if ov:
                    layers.append((ov, args.overlay_color, args.overlay_lw))
            layers.append((prim, "black", args.primary_lw))
            n_sl += 1
            if is_rings:
                hdr = (f"RING {n_sl:02d}  h={(level-base)*s:6.1f} mm from base  "
                       f"| {args.spacing_mm:.0f} mm spacing")
                mm_val = (level - base) * s
            else:
                hdr = (f"{args.slice_normal.upper()}-SLICE {n_sl:02d}  "
                       f"@ {args.slice_normal}={level*s:6.1f} mm  | {args.spacing_mm:.0f} mm spacing")
                mm_val = level * s
            mms = None
            if sil is not None:
                orient = {"grid": sil[0], "extent": sil[1], "kind": mm_kind,
                          "value": mm_val, "ticks": tick_vals,
                          "label": f"{mm_view}  #{n_sl:02d}"}
                if is_rings:                    # top-down: draw this ring's outline
                    top = {"grid": sil_top[0], "extent": sil_top[1], "kind": "loops",
                           "loops": prim, "label": f"top-down  #{n_sl:02d}"}
                else:                           # top-down: line at the slice depth/offset
                    top = {"grid": sil_top[0], "extent": sil_top[1],
                           "kind": "hline" if args.slice_normal == "z" else "vline",
                           "value": level * s, "ticks": tick_vals,
                           "label": f"top-down  #{n_sl:02d}"}
                mms = [orient, top]

            marks = []
            if args.marks and is_rings:
                # ring page (X,Z): mark ribs (radial lines) + Z-slices (Z=z_j)
                rc, rm = FAM_STYLE["rib"]
                for th in cage_rib_angles:
                    ct, st = math.cos(th), math.sin(th)
                    pts = crossings(prim, lambda x, y, st=st, ct=ct: -st * x + ct * y)
                    if len(pts):
                        marks.append({"pts": pts, "color": rc, "marker": rm,
                                      "fam": "rib", "label": f"{round(math.degrees(th))}°"})
                zc, zm = FAM_STYLE["z"]
                for zj in cage_z_depths:
                    pts = crossings(prim, lambda x, y, zj=zj: y - zj)
                    if len(pts):
                        marks.append({"pts": pts, "color": zc, "marker": zm,
                                      "fam": "z", "label": f"z{zj:.0f}"})
            elif args.marks and args.slice_normal == "z":
                # coronal page (X,height): mark rings (height=h_k) + ribs (X=z/tanθ)
                zj = level * s
                rc, rm = FAM_STYLE["ring"]
                for hk in cage_ring_heights:
                    pts = crossings(prim, lambda x, y, hk=hk: y - hk)
                    if len(pts):
                        marks.append({"pts": pts, "color": rc, "marker": rm,
                                      "fam": "ring", "label": f"h{hk:.0f}"})
                bc, bm = FAM_STYLE["rib"]
                for th in cage_rib_angles:
                    ct, st = math.cos(th), math.sin(th)
                    if abs(st) < 1e-6:
                        continue
                    x0 = zj * ct / st
                    pts = crossings(prim, lambda x, y, x0=x0: x - x0)
                    if len(pts):
                        marks.append({"pts": pts, "color": bc, "marker": bm,
                                      "fam": "rib", "label": f"{round(math.degrees(th))}°"})

            n_pages += emit_panel(pdf, layers, hdr, args.grid_mm, args.margin_mm,
                                  page_step_x, page_step_z, minimaps=mms,
                                  marks=marks or None)

    print(f"\nwrote {args.out}")
    print(f"slices: {n_sl}   pages: {n_pages}")


if __name__ == "__main__":
    main()
