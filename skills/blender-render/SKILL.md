---
name: blender-render
description: Render STL meshes with headless Blender (workbench engine, seconds per image) and compose titled PNGs with matplotlib, every part LABELLED with its name - assembly views, before/after steps side by side, print plates on the bed. Use whenever a 3D part, assembly or print plate should be shown to the user as a picture, especially when the user is on a phone.
---

# blender-render

Headless Blender driven by a JSON manifest. No scene files, no lights to set up: the workbench engine with studio
light, object colours per "kind", cavity + shadows, transparent film. The Python side crops by alpha and adds
titles.

## Scripts

| script | call | does |
|---|---|---|
| `render_assembly.py` | `blender -b -P render_assembly.py -- manifest.json` | Blender side: import STLs, colour by kind, one PNG per step, label anchors projected to pixels |
| `render.py` | `from render import render` | Python side: writes the manifest, runs Blender, crops, draws the name callouts, titles, saves the PNG |
| `plate_view.py` | `./plate_view.py plate.3mf [...] --bed 180` | a 3mf/STL plate lying on the bed, each part labelled with its 3mf name, title with the footprint |

Blender comes from `$BLENDER` or `blender` on PATH (tested with Blender 5.0; the STL import falls back to the old
operator on 3.x/4.x). If the agent runs in a sandbox, Blender may need it lifted.

## Use

```python
from render import render
render([("stl/part_world.stl", "part", "corner bracket"),                 # (path or trimesh, kind, name)
        (rail_mesh, "alu", "top rail"),
        (part, "part", "M6 counterbore", (x, y, z)),                        # a feature: name + anchor point
        (floor, "floor")],                                                  # no name -> no label
       colors={"part": [0.23, 0.49, 0.85], "alu": [0.62, 0.64, 0.67]},
       camera=dict(target=[0, 0, 10], loc=[250, -300, 220], lens=45),    # mm; add "ortho": 400 for a plan view
       out="part.png", title="Part in place", subtitle="blue = printed, grey = existing")

# two steps side by side (without / with a cover):
render({1: [...parts], 2: [...parts, (cover, "cover")]}, colors, camera, "steps.png",
       panels=[(1, "without the cover"), (2, "with the cover")])
```

## Name everything the user will talk about

Pictures are where the user and the agent agree on words. Every object with a name gets a callout: a box beside
the picture (edge in the part's colour) and a leader line to the point on the part nearest its centre - or to an
explicit anchor, which is how you name a feature (a hole, a gusset, a slot) rather than a whole part. Labels sit
in two columns and are spread so they never overlap.

- Use the **same name everywhere**: the callout, the STL / 3mf node name, the part doc, the chat. "The corner
  bracket's M6 counterbore" then means one thing to both sides.
- Name what is under discussion (the parts that changed, the two things that clash), not every screw.
- Plates: `plate.write_plates` stores each part's name in the 3mf, so `plate_view.py` labels them - the user can
  say "bracket_2 lifted off the bed".
- Label section plots too (`ax.annotate` with an arrow) - gaps in mm next to the parts' names.

## Picture habits that worked

- **Colour means something and the subtitle says what**: printed parts blue, existing hardware grey, sheet
  material brown, the neighbour that was clashing red.
- **Views from where the problem is**: from below for something hanging, a close-up of the joint, top-down
  (ortho) with and without the cover plate.
- Pair a render with a **matplotlib section** through the joint (see the print-part skill) - renders show shape,
  sections show gaps in mm.
- Render every plate before handing over the 3mf - it catches parts off the bed and floating features.
- Send the PNGs to the user right away; iterate on their annotated screenshots.
