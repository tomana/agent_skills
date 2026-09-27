---
name: print-part
description: Design a 3D-printed (FDM) part as a parametric Python script - trimesh + manifold3d booleans, shapely for 2D, run as uv inline scripts - then check it numerically (watertight, one body, bed fit, clash volume against its neighbours, bolt axes open, screw lengths), lay it out on print plates (3mf), render it and show the user. Use whenever designing, changing, splitting or preparing a printable part, a jig, a bracket, an enclosure or a fixture.
---

# print-part

A part is **a script, not a file**. Every dimension is a named parameter, the script rebuilds the part from
scratch, prints its checks, and writes STL + 3mf + pictures. Changing the design = changing a number and
re-running. This loop has been very effective: most iterations are one edit, one run, one picture to the user.

## The stack

| tool | what for |
|---|---|
| **uv inline scripts** (`#!/usr/bin/env -S uv run --script` + a `# /// script` dependency block) | every generator is directly executable, no venv to manage |
| **trimesh** | meshes, primitives, sections, export (STL, 3mf) |
| **manifold3d** (`engine="manifold"`) | all booleans: fast and they stay watertight |
| **shapely** (+ `mapbox-earcut`) | 2D outlines, offsets, clipping, then `extrude_polygon` |
| **scipy**, **rtree** | `mesh.section()` needs scipy, `mesh.contains()` needs rtree - add them or those calls crash |
| **matplotlib** | section plots, plan views, saw/marking guides at 1:1 |
| **Blender, headless** | renders of assemblies and plates - see the `blender-render` skill |
| the slicer (Bambu Studio, Orca, ...) | **the user slices**, not the agent (see `reference/printing.md`) |

Dependency line that covers all of it:
`dependencies = ["trimesh","numpy","manifold3d","shapely","mapbox-earcut","networkx","scipy","rtree","lxml","matplotlib"]`

`scripts/cad.py` has the helpers (boxes, cylinders, convex prisms, hex nut traps, booleans, export, the checks,
the fastener table, `bolt_length()`); `scripts/plate.py` packs parts onto plates and writes the 3mf;
`scripts/example_bracket.py` is a complete worked part - start by copying it.

## The loop

1. **Measure the real things** (calipers, photos with a ruler). Vendor drawings and footprints are guesses until
   measured. Ask the user for the numbers you can't know.
2. **Write the generator.** Constants at the top with names and units; argparse for the ones that get varied.
   When the user changes something, **put their reason and the date in a comment next to the number** - the
   script becomes the design history.
3. **When several parts must agree** (a floor, the corner pieces that hold it, the template that marks it), put the
   shared geometry in **one module** they all import. Never copy a position into two scripts.
4. **Print the checks on every run** (`reference/verification.md`): size + bed fit, watertight, **number of
   bodies** (a part that fell in two), clash volume against every neighbour, bolt axes open, screw lengths.
   **Prove a clash check works** by also running a variant that must clash and showing a non-zero volume.
5. **Decide the print orientation in the script**, for strength (layer lines along the load) and so that nothing
   floats (a web in mid-air, a boss on nothing). Export the print copy moved onto the bed.
6. **Lay out the plates** (`plate.py`): one 3mf per plate, bounds and overlap printed. Name every output by part
   and version so the user can't print the wrong file.
7. **Make pictures and show them**: an assembly render, a section through the critical joint, a plate render,
   a 1:1 guide when something must be cut or marked. **Label the parts and features by name** (the
   `blender-render` callouts, `ax.annotate` on sections) and use the same names in file names, docs and chat -
   the labelled picture is the shared vocabulary. The user may be on a phone - send the PNGs, don't describe
   them. Iterate on their annotated screenshots and photos of the print.
8. **Write it down** next to the part (`PART.md`): a status line, what to print on which printer, the hardware
   list with lengths, what was checked (with the numbers) and what was **not** checked.
9. **Commit what gets printed.** Keep the repo to printed / about-to-print parts; move never-printed variants out.

## Where to look

- `reference/verification.md` - the checks, with code.
- `reference/patterns.md` - fasteners and screw length, jigs instead of measuring, splitting big parts,
  break-away supports, sharing bolts, nesting parts, coupons.
- `reference/printing.md` - beds, PETG settings, first layers, why the agent doesn't slice.
- `reference/gotchas.md` - the trimesh / manifold / shapely traps that cost time.

## Don't

- Don't hand-model a variant (a miniature, a mirrored side): derive it from the master with a flag.
- Don't claim "no clash" from a check that was never shown to catch a clash.
- Don't trust a 2D section alone for connectivity: a bolt hole can split a section while the part is one body -
  count bodies in 3D.
- Don't slice headless and hand over G-code; give the 3mf + settings.
- Don't overengineer: plain, flush, simple beats clever options nobody asked for.
