"""render.py - render meshes with headless Blender and compose a titled, LABELLED PNG with matplotlib.

    from render import render
    render([("stl/bracket_world.stl", "part", "bracket"),          # (mesh or path, kind, name)
            (duct, "context", "cable duct"),
            (wall, "context")],                                     # no name -> no label
           colors={"part": [0.23, 0.49, 0.85], "context": [0.62, 0.64, 0.67]},
           camera=dict(target=[0, 0, 10], loc=[250, -300, 220], lens=45),
           out="bracket.png", title="Bracket on the wall", subtitle="blue = printed, grey = existing")

Named objects get a callout: the name in a box beside the picture, a leader line to the part. The line points at
the point on the part nearest its bounding-box centre, or at an explicit anchor: (mesh, kind, name, (x, y, z)). Labels go in two
columns (left / right of the picture, by which side the part is on) and are spread so they never overlap.
Give parts the SAME names the user and the docs use - the picture becomes the shared vocabulary.

Pass {step: [...]} + panels=[(step, "panel title"), ...] to render several steps side by side.
Blender comes from $BLENDER or `blender` on PATH. Workbench engine: a render takes seconds.
"""
import json, os, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent

def blender_bin():
    b = os.environ.get("BLENDER") or shutil.which("blender")
    if not b: raise SystemExit("Blender not found: set BLENDER=/path/to/blender or put blender on PATH")
    return b

def _item(it):
    """(mesh|path, kind[, name[, anchor]]) -> dict"""
    it = tuple(it) + (None,) * (4 - len(it))
    return dict(mesh=it[0], kind=it[1], name=it[2], anchor=it[3])

def render_steps(steps, colors, camera, res=(1600, 1200)):
    """steps: {step_no: [items]} -> {step_no: (RGBA float image, [label dicts with "px"])}"""
    import trimesh
    work = Path(tempfile.mkdtemp(prefix="render_")); objs, labels = [], []
    for st, items in steps.items():
        for i, it in enumerate(map(_item, items)):
            m = it["mesh"]
            if not isinstance(m, (str, Path)):
                f = work/f"s{st}_{i}.stl"; m.export(str(f)); path = f
            else:
                path = Path(m)
            objs.append(dict(step=st, kind=it["kind"], file=str(path.resolve())))
            if it["name"]:
                anchor = it["anchor"]
                if anchor is None:
                    mm = m if not isinstance(m, (str, Path)) else trimesh.load(str(path))
                    anchor = mm.bounds.mean(axis=0)            # an L-shape's box centre is in the air: take the
                    try:                                        # nearest point ON the part instead (needs rtree)
                        anchor = trimesh.proximity.closest_point(mm, [anchor])[0][0]
                    except Exception:
                        pass
                labels.append(dict(step=st, anchor=list(map(float, anchor)), text=it["name"], kind=it["kind"]))
    man = dict(objects=objs, colors=colors, camera=camera, res=list(res), outdir=str(work), labels=labels)
    (work/"m.json").write_text(json.dumps(man))
    r = subprocess.run([blender_bin(), "-b", "-P", str(HERE/"render_assembly.py"), "--", str(work/"m.json")],
                       capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-2000:])
    import matplotlib.image as mpimg
    return {st: (mpimg.imread(str(work/f"step{st}.png")), json.loads((work/f"step{st}_labels.json").read_text()))
            for st in steps}

def crop(im, pad=15):
    """crop to the rendered pixels -> (image, (x0, y0) offset). Clamp at 0: a part touching the frame edge would
    otherwise give a negative start index, which numpy wraps round to an EMPTY slice."""
    ys, xs = np.where(im[..., 3] > 0.02)
    if len(ys) == 0: return im, (0, 0)
    y0, x0 = max(0, ys.min() - pad), max(0, xs.min() - pad)
    return im[y0:ys.max() + pad, x0:xs.max() + pad], (x0, y0)

def _spread(ys, lo, hi, gap):
    """move label y's apart by at least `gap`, keeping them inside [lo, hi] and in order"""
    ys = list(ys)
    for i in range(1, len(ys)): ys[i] = max(ys[i], ys[i - 1] + gap)
    if ys and ys[-1] > hi:
        ys[-1] = hi
        for i in range(len(ys) - 2, -1, -1): ys[i] = min(ys[i], ys[i + 1] - gap)
    return [max(lo, y) for y in ys]

def draw_labels(ax, im, labels, colors, offset, fontsize=12):
    """callouts in two columns beside the image; returns the x-limits needed to show them"""
    h, w = im.shape[:2]; x0, y0 = offset
    pts = [(L["px"][0] - x0, L["px"][1] - y0, L) for L in labels]
    split = w/2                                         # by side of the picture; if that leaves one column
    if len(pts) > 3 and (all(p[0] < w/2 for p in pts) or all(p[0] >= w/2 for p in pts)):   # empty, balance them
        split = float(np.median([p[0] for p in pts])) + 1e-6
    left = sorted([p for p in pts if p[0] < split], key=lambda p: p[1])
    right = sorted([p for p in pts if p[0] >= split], key=lambda p: p[1])
    # sizes in DATA units (image pixels): the image is scaled into the axes, so a 12 pt label is many image pixels
    # tall when a 1600 px render sits in a 1000 px wide axes. Solve for the scale with the label margins included.
    fig = ax.figure; pos = ax.get_position(); pt = fig.dpi/72.0
    A_w, A_h = pos.width*fig.get_figwidth()*fig.dpi, pos.height*fig.get_figheight()*fig.dpi
    longest = max((len(L["text"]) for _, _, L in pts), default=0)
    sides = (1 if left else 0) + (1 if right else 0)
    pad, char = w*0.03, fontsize*pt*0.62                        # pad in data units, char width in screen px
    s = max((w + sides*pad)/max(A_w - sides*longest*char, 1.0), h/A_h)   # data units per screen px (equal aspect)
    gap = fontsize*pt*2.2*s                                     # one boxed line + air
    margin = pad + longest*char*s
    for side, col in ((-1, left), (1, right)):
        ys = _spread([p[1] for p in col], gap/2, h - gap/2, gap)
        for (px, py, L), ty in zip(col, ys):
            tx = -pad if side < 0 else w + pad
            c = colors.get(L.get("kind"), [0.3, 0.3, 0.3])
            if 0.3*c[0] + 0.59*c[1] + 0.11*c[2] > 0.8: c = [0.35, 0.35, 0.35]    # a near-white kind: dark edge
            ax.plot([px], [py], "o", ms=5, color="#111", zorder=5)
            ax.annotate(L["text"], xy=(px, py), xytext=(tx, ty), ha="right" if side < 0 else "left", va="center",
                        fontsize=fontsize, weight="bold", annotation_clip=False, zorder=6,
                        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=c, lw=2),
                        arrowprops=dict(arrowstyle="-", color="#222", lw=1.2, shrinkA=0, shrinkB=3))
    return (-margin if left else 0), (w + margin if right else w)

def render(objects, colors, camera, out, title="", subtitle="", res=(1600, 1200), panels=None, fontsize=12):
    """one image, or several side by side (panels=[(step, "panel title"), ...] with {step: [...]}).
    Writes `out` (PNG on white) and returns its path."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    steps = objects if isinstance(objects, dict) else {1: objects}
    shots = render_steps(steps, colors, camera, res)
    panels = panels or [(st, "") for st in steps]
    has_labels = any(shots[st][1] for st, _ in panels)
    fig, axs = plt.subplots(1, len(panels), figsize=((13 if has_labels else 10)*len(panels), 8.6), squeeze=False)
    for ax, (st, t) in zip(axs[0], panels):
        im, labels = shots[st]; im, off = crop(im)
        ax.imshow(im); ax.axis("off")
        if labels:
            xl, xr = draw_labels(ax, im, labels, colors, off, fontsize)
            ax.set_xlim(xl, xr); ax.set_ylim(im.shape[0], 0)
        if t: ax.set_title(t, fontsize=13, weight="bold")
    if title: fig.suptitle(title, fontsize=15, weight="bold")
    if subtitle: fig.text(0.5, 0.925, subtitle, ha="center", fontsize=11, color="#333")
    fig.tight_layout(rect=[0, 0, 1, 0.92 if title else 1])
    fig.savefig(str(out), dpi=80, facecolor="white"); plt.close(fig); print(f"  -> {out}")
    return out
