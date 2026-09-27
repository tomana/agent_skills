# Printing

## Beds

| printer | bed | keep pieces within | plate margins |
|---|---|---|---|
| Bambu A1 Mini | 180 x 180 | **<= 172** in X and Y (a 177.5 mm piece produced G-code the nozzle couldn't reach) | 4 mm |
| Creality K1 Max | 300 x 300 | ~290 (not measured) | 5 mm |

Say **which 3mf goes to which printer** when there is more than one.

## Material and settings (PETG default)

- Walls 4, **40 % gyroid** infill, top 5 / bottom 4 layers, **supports off** (design them in instead).
- Hollow closed shells: 0 % sparse infill, and never removable support inside a closed volume (it can't come out).
- PLA is fine for jigs, templates and coupons.

## PETG first layer

When the first layer won't stick or strings:
- clean the plate (dish soap + water, then isopropyl), textured PEI works best for PETG;
- slow the first layer down (~20-30 mm/s) and raise the bed a little (~75-85 C);
- a thin glue-stick layer as release/adhesion on smooth plates;
- check the Z offset / first-layer squish.

## Why the agent doesn't slice

A headless slicer CLI run looked fine but **did not resolve the profile inheritance**: PETG came out as PLA with
the wrong speeds. Hand over the 3mf (laid out, checked) + the settings above, and let the user slice in the GUI
where they see the preview.

## Outputs

- `stl/<part>.stl` (on the bed) and `stl/<part>_world.stl` (assembly coordinates). **STL is canonical** - 3mf
  transfers between tools have dropped parts.
- `3mf/<plate>.3mf` - one per plate, parts already placed.
- Pictures: assembly render, section, plate render (`blender-render` skill).
