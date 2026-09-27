---
name: mesh-to-physical
description: Turn a 3D model or a photo into something to build by hand - slice a mesh into 1:1 contour templates on A3 pages (for bending wire armatures, cutting ribs, stacking layers), or turn a reference image into a depth map and a printable relief with a flat back (masks, mould formers). Use when a model has to become paper templates, wire, card or papier-mache, or when a picture should become a relief.
---

# mesh-to-physical

## Mesh -> 1:1 paper templates

`scripts/slice_to_a3.py` slices a mesh and lays the contours out at **true size on A3 pages** as a multi-page PDF,
with a 50 mm grid, a red 50 mm calibration square, crop marks and dashed centre lines. Wide slices tile across
pages.

```bash
./slice_to_a3.py --stl model.stl --out rings_A3.pdf --spacing-mm 50                 # horizontal rings
./slice_to_a3.py --stl model.stl --out front_A3.pdf --slice-normal z                # front-view slices
./slice_to_a3.py --stl model.stl --out fan_A3.pdf --mode fan --fan 8                # radial ribs through the axis
./slice_to_a3.py --stl inner.stl --overlay-stl outer.stl --out overlay_A3.pdf       # solid inner + faint outer
```
- Units: `--unit-scale` (default 1000, metres -> mm) or `--target-height-mm` to scale to a height. `--up` picks
  the up axis (Blender exports Y-up).
- **Different slice directions catch different features**: horizontal rings miss limbs that splay sideways;
  front-view slices catch them; a radial fan suits a round core.
- **Print at 100 %, no fit-to-page, and measure the red square** before cutting anything.
  With CUPS: `lp -o fit-to-page=false -o media=A3 file.pdf`. If `lp` hangs it is reading stdin: the filename
  didn't attach (often a wrapped paste) - keep the command on one line.

## Photo -> depth -> relief

```bash
./depth_estimate.py photo.jpg depth.png [--upscale 2] [--invert]      # Depth Anything V2 (small), brighter = closer
./heightmap_to_stl.py depth.png relief.stl --width-mm 120 --relief-mm 12 --base-mm 3
```
- `depth_estimate.py` downloads the model (~100 MB) on its first run and uses the CPU if there is no GPU.
- `heightmap_to_stl.py` makes a watertight solid with a flat back (printable as is, or a former to lay
  papier-mache or pull a mould over). `--res` sets the grid (300 along the long side is plenty).
- It's a relief (2.5D), faithful for masks and faces from the front. A closed full-round form needs modelling.
- Same result inside Blender: a subdivided plane + **Displace** (image texture, coords UV, mid level 0,
  strength = relief) - apply it - **Solidify** - export STL.

## Mesh cleanup gotchas (Blender)

- A boolean cut on an **open / non-manifold sculpt** only works where the cutter passes through solid
  geometry; elsewhere it merges the cutter's faces in. Cut through solid material for a clean flat base.
- An inner shell for an armature: offset every vertex inward along its normal (constant wall, not a scale), then
  voxel-remesh to heal self-intersections and make it watertight.
- Scale uniformly from one anchored measurement (e.g. head width) and write the factor down.
