---
name: device-mold
description: Design a 3D-printed cradle, mould, stand or rig that holds existing devices (instruments, controllers, mixers, electronics) snugly - built from their spec sheets and the manufacturers' dimension drawings: 1:1 device models subtracted from a solid, drop-in pockets with clearance, cable furrows and port bays placed from the manual's drawings, closed tunnels for metal profiles with break-away supports, fit-test slices before the big print, split across print plates. Use whenever a printed part must hold, surround or route cables around devices you have (or have the manuals for).
---

# device-mold

A rig for devices is **one solid block minus the devices**. Model each device 1:1 from its spec sheet and drawings,
subtract it (its outline plus a clearance, swept straight up so it drops in), cut the cable paths and the metal
profiles into the same solid, and the part follows. Changing a device, a clearance or a cable route is a number
in the script - not a remodel.

This builds on the **`print-part`** skill (read it first: the loop, the helpers `cad.py` / `plate.py`, the
fastener table, the checks) and the **`blender-render`** skill (labelled renders). The example here imports both.

## Scripts

| script | does |
|---|---|
| `scripts/example_cradle.py` | a complete worked cradle for two made-up devices from a spec dict: pockets, two cable furrows + port bays, screw-down cable clips (one example of holding cables), a flat-bar tunnel with break-away hourglass fins, mounting holes, the checks (each shown to bite), a fit-test slice, two plates + a clip plate, labelled sections, `--render` |
| `scripts/drawing_measure.py` | read millimetres off a manual page: a pixel grid to pick points, scale from a known length, checked on a second one, positions + lengths, a marked-up page to keep |

```bash
cd scripts && ./example_cradle.py --out /tmp/cradle            # + --render with Blender (BLENDER=...)
```

## The order

1. **Collect the dimensions, each with its source.** Spec sheet (outer size, weight), the manual's dimension
   drawings (port positions, feet, rounded corners), calipers on the real device where you can. A device model
   you already have (a scan, a printed miniature scaled up, a vendor CAD) is a starting point, not the truth.
2. **Device models**: simple extrusions of the plan outline + the height, the ports as small boxes on the sides.
   Keep them in the script as a dict (see `DEVICES` in the example) with a `source` string per number.
3. **Layout**: where each device sits, which side each cable leaves from, where the cables go out of the rig.
   Put the busy sides (ports) toward the ends or the back; ask the user how they'll reach the device.
4. **The part generator** (below), with its checks printed on every run.
5. **Fit tests first** - small, fast prints of the risky bits: each pocket corner to corner with low walls, a
   short slice of every tunnel with its supports, a joint. Only then the big print.
6. **Plates**: split where it's strong and hidden; the metal profiles tie the pieces together.
7. **Pictures + a README next to the part**: what to print on which printer, the hardware list, what was checked
   with numbers, what was not.

## Reading dimensions off drawings

Manuals rarely dimension what you need (where exactly is the power socket on the side?), but their drawings are
usually drawn to scale.
- Render the page at **600 dpi** (`pdftoppm -r 600 -f N -l N -png manual.pdf page`).
- `drawing_measure.py page.png --grid grid.png` and read the pixel coordinates you need off the grid picture.
- **Calibrate on a feature whose size you know** (the device's depth from the spec sheet), and **check the scale
  on a second known feature** (a standard connector: USB-C ~8.9 x 3.2, a 6.35 mm jack, a DIN socket). A few % off
  is fine; more means the drawing isn't to scale there or you picked the wrong edges.
- Write the number **with its source** into the script:
  `PORT_Y = 57.5  # manual p.18 side drawing, 600 dpi, scale from the 114 mm depth, socket checked (9.4 vs 8.9)`.
- A guess (from a photo, from a small model) stays marked as a guess in the script until it is measured. A port
  placed from a guess is the classic reprint - search for the real drawing before the print, not after.
- The **plug is bigger than the socket**: the overmould (12-13 mm wide for USB-C), a straight run before the cable
  may bend, and room for the fingers. Room for anything else on that side (a card slot, a switch) comes too.

## The part

- **Pockets**: the plan outline + clearance (1.0 mm per side held boxy devices well in PETG - confirm with the fit
  test), extruded from the pocket floor to above the top so the device drops in. The pocket depth is how much of
  the device the rig holds; the rest stands up.
- **Cables**: generic **furrows the full length, open at both ends** (a cable can leave either side), not one groove
  per cable; down the legs too if the rig has legs. At each port a wide **bay** (plug width + its straight run),
  then a narrow groove back to the furrow. How the cables are *held* in the furrows is a separate choice - below.

### Holding the cables - the example's clips are one answer, not the answer

The example models **screw-down clips**: a strip across two furrows, one M3 into a heat-set insert in the land
between them, a tab down into each furrow, each clip in its own shallow recess (+0.3) so it drops in square;
checked in place (no collision; tabs without clearance must collide), the insert keeping 1.5 mm to the furrows, the
screw length against the insert hole; printed top face down on their own plate (`out/clip_section.png`). That
suits a rig that travels and whose cables rarely change. **Look for the solution that fits the use** - ask the user
how often cables go in and out, whether the rig travels, whether it is seen - and consider, for example:

- **Snap lips** on the furrow walls (a small overhang the cable pushes past) - no hardware, quick to change, but the
  lips are thin and wear; print a test coupon first.
- **Hook-and-loop straps** through slots under the land - fast, adjustable, gentle on thick cables.
- **Zip-tie anchors**: a tunnel under a bridge every few centimetres - cheapest, secure, but cut to change.
- **A sliding or snap-on cover** over the whole furrow (a rail on both walls) - tidy and seen-proof, one part.
- **Magnets** in the land and a printed cap with magnets - no screws, fast; mind the strength and the polarity.
- **Friction alone**: a furrow a little narrower than the cable bundle, or a TPU insert strip - nothing to lose.
- **Combs / cable guides** at the ends only, when the furrow is deep enough to hold cables by itself.

![the example cradle from behind: two furrows, the clips in their recesses](../../docs/cradle_assembly.png)
![section through a clip in place](../../docs/cradle_clip_section.png)

Whatever it is, model it like the clips: the part in place, a check that it clears (and one that shows the check
bites), a fit test before the big print.

- **Metal profiles** (flat bar, angle) through **closed tunnels**, open at both ends: 0.4 mm per side, +1 mm
  headroom on top (a wide roof sags). The printed pieces **thread onto the profiles** - stronger and simpler than
  puzzle joints.
- **Break-away supports under tunnel roofs**: rows of thin **hourglass fins** - a foot, a thin waist low down (the
  break point: 0.6 mm at 0.5 mm up), 45-degree flanks, a flat top (at most ~5.5 mm) 0.2 mm under the roof, one every
  6 mm, rows ~10 mm apart. Every edge is 45 degrees or steeper, so they print clean; pushing the metal through
  knocks them over one by one. (T-shaped "mushrooms" with a flat cap print as spaghetti under the cap.)
- **Bolts between pieces** (legs to a top): if the stack is taller than the screws you have, counterbore deep
  instead of buying longer screws; a **hex nut channel** from below the size of the nut's across-flats (a vertex up
  when the piece prints on its side: self-supporting).
- **Rounded outside**: intersect with a convex envelope (the hull of rounded-rectangle rings stepped up a
  quarter-round). Leave margin for the radius - rounding eats walls.
- Pieces print **flat side down, no supports**; tunnels bridge onto the fins.

## The checks (print them every run; prove each one bites)

| check | how | proof it works |
|---|---|---|
| devices clear | intersection volume device models vs the part (without the break-away fins) = 0 | the same with pockets 0.5 mm too small: > 0 |
| profiles clear | volume profile vs part without fins = 0; with fins > 0 (by design) | - |
| walls | rows of `contains()` probe points in the wall mid-line / a ring 1.5 mm outside each hole and counterbore | the probe moved into the pocket / the hole moved against a pocket: False |
| thin floors | probe points in the floor over a tunnel | - |
| one body | `len(m.split())` for every printed piece | - |
| bed fit, seams | every piece on its plate (`plate.py`); the seam not through a clip pocket, a thin wall or a fin | assert the distances |
| ports | plug bottom vs bay floor, plug top vs the top (an open bay is fine) | - |
| fit test | the device model clear of the test piece's walls | no pocket at all: > 0 |

A check that was never shown to catch the bad case proves nothing: "no clash" from a check that can't clash.

## Fit tests

- **Pocket, corner to corner**: the pocket's whole outline + a few mm, a thin solid floor slab (a plain slice would
  open into a tunnel below) and **low walls** (5-6 mm). Tests the clearance on every side and both corners with the
  port. Much faster than the part; a 30 mm slice of one side misses the corners.
- **Tunnel slice**: 30-60 mm of the tunnel with its fins, for the smaller printer: push the real profile through.
- Iterate on what the user reports back ("the fins print as spaghetti", "the port is 12 mm off") and keep the
  printed versions' files, so what is on the bed matches what is in the repo.

## Pictures for the person printing

- A **section** through a pocket and a tunnel (matplotlib, `cad.section`), every feature labelled by name, the
  device outline dashed.
- A **render** from where the cables and ports are visible, parts and features named (`blender-render`).
- A **plan view of each fit test** with the device outline, and a plate view of every 3mf.
- Close-ups of details that are hard to picture (the fins, a nut channel) - angled, with their sizes.

## Don't

- Don't place a port from a photo or a small model and print the big part; get the drawing or measure.
- Don't make one groove per cable; generic furrows that run through survive the next device swap.
- Don't take the example's clips as the default: pick the cable holder from how the rig is used (see above).
- Don't split through a pocket's thin wall or a clip pocket; don't put a seam through the supports.
- Don't skip the fit test because the numbers "look right".
