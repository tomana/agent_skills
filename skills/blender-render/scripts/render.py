"""render.py - render meshes with headless Blender and compose a titled PNG with matplotlib.

    from render import render
    render([("stl/bracket_world.stl", "part"), ("stl/wall_world.stl", "context")],
           colors={"part": [0.23, 0.49, 0.85], "context": [0.62, 0.64, 0.67]},
           camera=dict(target=[0, 0, 10], loc=[250, -300, 220], lens=45),
           out="bracket.png", title="Bracket on the wall", subtitle="blue = printed, grey = existing")

Objects are (path_or_trimesh, kind); pass `step` lists to render several steps side by side (e.g. without and with
a cover). Blender comes from $BLENDER or `blender` on PATH. Workbench engine: a render takes seconds.
"""
import json, os, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent

def blender_bin():
    b = os.environ.get("BLENDER") or shutil.which("blender")
    if not b: raise SystemExit("Blender not found: set BLENDER=/path/to/blender or put blender on PATH")
    return b

def render_steps(steps, colors, camera, res=(1600, 1200), labels=()):
    """steps: {step_no: [(path_or_mesh, kind), ...]} -> {step_no: RGBA float image}"""
    work = Path(tempfile.mkdtemp(prefix="render_")); objs = []
    for st, items in steps.items():
        for i, (m, kind) in enumerate(items):
            if not isinstance(m, (str, Path)):
                f = work/f"s{st}_{i}.stl"; m.export(str(f)); m = f
            objs.append(dict(step=st, kind=kind, file=str(Path(m).resolve())))
    man = dict(objects=objs, colors=colors, camera=camera, res=list(res), outdir=str(work), labels=list(labels))
    (work/"m.json").write_text(json.dumps(man))
    r = subprocess.run([blender_bin(), "-b", "-P", str(HERE/"render_assembly.py"), "--", str(work/"m.json")],
                       capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-2000:])
    import matplotlib.image as mpimg
    return {st: mpimg.imread(str(work/f"step{st}.png")) for st in steps}

def crop(im, pad=15):
    """crop to the rendered pixels. Clamp at 0: a part touching the frame edge would otherwise give a negative
    start index, which numpy wraps round to an EMPTY slice."""
    ys, xs = np.where(im[..., 3] > 0.02)
    if len(ys) == 0: return im
    return im[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]

def render(objects, colors, camera, out, title="", subtitle="", res=(1600, 1200), panels=None):
    """one image, or several side by side: panels=[(step_no, "panel title"), ...] with objects given per step as
    {step_no: [...]}. Writes `out` (PNG on white) and returns its path."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    steps = objects if isinstance(objects, dict) else {1: objects}
    ims = render_steps(steps, colors, camera, res)
    panels = panels or [(st, "") for st in steps]
    fig, axs = plt.subplots(1, len(panels), figsize=(10*len(panels), 8.6), squeeze=False)
    for ax, (st, t) in zip(axs[0], panels):
        ax.imshow(crop(ims[st])); ax.axis("off")
        if t: ax.set_title(t, fontsize=13, weight="bold")
    if title: fig.suptitle(title, fontsize=15, weight="bold")
    if subtitle: fig.text(0.5, 0.925, subtitle, ha="center", fontsize=11, color="#333")
    fig.tight_layout(rect=[0, 0, 1, 0.92 if title else 1])
    fig.savefig(str(out), dpi=80, facecolor="white"); plt.close(fig); print(f"  -> {out}")
    return out
