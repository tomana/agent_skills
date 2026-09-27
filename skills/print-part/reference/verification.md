# Verification - the checks every generator prints

Numbers first, pictures second. Each check below is a few lines with `scripts/cad.py`.

## Per part

```python
report("bracket", m)          # extents, watertight, bodies, fits the bed
```
- **Bed fit**: the piece's X and Y must fit the usable bed (see `printing.md`). Z is rarely the limit.
- **Watertight**: an open mesh slices empty or badly.
- **Bodies = 1**: a boolean that cut a part in two, or a support that ended up floating. Keep only the largest body
  if a stray sliver appears (`max(m.split(), key=lambda b: b.volume)`), but find out why first.

## Clashes with neighbours

```python
worst = worst_overlap(printed_parts, neighbours)             # mm3, 0 when clear
worst_old = worst_overlap(printed_parts_old_version, neighbours)
print(f"clash {worst:.1f} mm3 (old version {worst_old:.0f} mm3 - the check bites)")
```
- Model the neighbours you must clear (rails, panels, walls, cables, the device) as simple boxes in **world
  coordinates**. Export every part's `_world.stl` so any other script can load it.
- Run the check on the known-bad variant too. A check that returns 0 for everything proves nothing.
- Touching is fine (0 volume); the check is intersection volume, not contact.

## Holes and screws

```python
axis_open = not solid_at(part, [(x, y, z)])[0]           # the bolt axis is empty ...
wall_ok   = solid_at(part, [(x + r + 2, y, z)])[0]       # ... and there is material beside it
bolt_length(stack=22, engage_min=6, engage_max=9)        # -> [(30, 8.0)]: M6x30 goes 8 mm past the stack
```
- Probe the axis through **every** part the screw passes (bracket, plate, board): one missed hole = a part
  that can't be assembled.
- `bolt_length`: *stack* = everything under the head; *engage_min* = the tip must get through the nut / insert /
  slot lip; *engage_max* = where it bottoms out (T-slot depth, blind hole). Include the washer. Tell the user the
  window and which standard length fits, and what changes it (a thicker board, a washer).

## Sections and outlines

```python
sec = section(m, origin=[x, 0, 0], normal=[1, 0, 0], drop=0)   # shapely polygon in (y, z)
```
- Plot a section through the joint that matters (a bracket and its screw, a lap joint, a tunnel with its
  supports). Colour each part, label gaps in mm. Users catch design errors in these pictures fast.
- For templates and jigs: compare the traced outline with the intended one -
  `outline.symmetric_difference(target).area` should be ~0 (it was 0.14 mm2 for a traced saw line).

## Plates

`plate.write_plates` prints bounds and the boolean overlap between parts on each plate. Bounding boxes lie for
L-shaped parts nested into each other - the boolean is the real test.

## Say what wasn't checked

A number that was assumed (a nut's thickness, a slot's lip, a board's real thickness) goes in the part doc as an
assumption, with how to verify it (calipers, a coupon).
