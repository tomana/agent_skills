# Design patterns that worked

## Fasteners

- **Socket head cap screws** (ISO 4762), sunk in a counterbore or proud. **M2.5** electronics, **M3** general
  printed joints (often into heat-set inserts), **M4** heavy parts, **M6** into aluminium T-slot profile with
  T-nuts. **Brass hex standoffs** for boards and floating panels.
- Printed hole sizes are in `cad.HOLES` (clearance, counterbore, nut trap). The M2.5-M4 rows are proven in PETG;
  print a coupon before relying on a new size.
- **Nut traps and heat-set inserts over glue**: demountable beats permanent. Glue is fine for flat plates onto a
  printed frame.
- **Screw length is a window, not a guess**: compute it (`bolt_length`) from the stack and where the tip must
  land. Into 8 mm T-slot (9 mm deep): tip 6-9 mm past the face.
- **Share screws between parts** when they meet: put one part's arm over the other's bracket so one screw clamps
  both. Halves the hardware and aligns the parts. Move brackets toward corners if that's where the other part is.

## Jigs instead of measuring

- **Spacer sticks with locators**: printed corner pieces get a small square boss on each arm end; the spacer
  sticks have an open slot at each end that drops over it (0.3 mm clearance). Lay corners + spacers on the sheet
  and the gap and the line set themselves - trace the outer edge and mark the drill holes through the parts.
- **The printed part is its own template**: make its outer edge equal the cut line of the sheet it holds, so
  tracing it gives the saw line.
- **Marking templates** in segments (seams away from notches and holes) when the outline is bigger than the bed.
- A 1:1 guide PNG/PDF with the sheet, the parts in place, the cut line dashed and the drill points marked.

## Big parts

- **Split into bed-sized pieces**: half-lap + locating pin/peg, or a wrap-around lap (lip over, tongue, lip under)
  that slides together in one direction.
- **Stagger the seams like brick bond** between rows so each piece bridges a seam of the other row.
- **Put seams in plain material**: not through a hole, a support or a boss (a seam can cut them loose).
- **Thread pieces onto metal stock** (aluminium angle, flat bar) through closed tunnels: the metal is the spine,
  the prints are sleeves. A test slice of the tunnel first.
- **Nest L-shaped parts**: two per plate in opposite corners, their empty insides overlapping on the diagonal
  (`plate.nest_pair`).
- Derive **scale models** (1:4 minis) from the full-size script with a flag, never by hand.

## Overhangs and tunnels

- **Break-away "mushroom" supports**: rows of small caps on thin necks under a tunnel roof, with gaps between.
  Push the metal through and they snap off in any direction. Proven in PETG on a tunnel test print.
  Keep them off seams.
- Orient so gussets and webs lie **on the bed**, not in mid-air (the worked example had it wrong at first).
- 45-degree gussets stiffen brackets a lot and print without support.

## Fits and clearances (PETG, 0.4 mm nozzle)

- Drop-in panel in a frame: 2 mm reveal per side (proven).
- Sliding fit slot over a boss: 0.3 mm per side (design value - print a coupon).
- Part against a cut sheet edge (MDF, plywood): 0.5 mm (design value; hand-sawn edges vary more).
- Overlap solids 0.3-0.5 mm where they join, never exactly coplanar (see `gotchas.md`).

## Coupons, gauges, fit slices

Before a long print: a thin slice through the critical fit (a tunnel, a lens window, a screw boss), a few
minutes each. Print long gauges diagonally. Keep coupons thin - they measure, they don't carry load.
