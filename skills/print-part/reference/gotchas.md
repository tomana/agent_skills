# Gotchas (each one cost an iteration)

## Geometry

- **Holes in a 2D polygon before `extrude_polygon` can crack the triangulation** - a thin ring around a hole comes
  out broken or non-manifold. Extrude the solid outline, then cut the holes as 3D cylinders.
- **Coplanar unions** (two solids sharing a face exactly) give slivers and non-manifold edges. Overlap 0.3-0.5 mm.
- **Cut order matters near features**: a cut ~1 mm from another feature can snap vertices; make the delicate cut
  last.
- A clearance **buffer can detach a tab** (the neck got eaten): extend the neck 1 mm back into the body.
- After booleans: `merge_vertices()` + `trimesh.repair.fix_normals()`; then check `is_watertight` and body count.
- When a boolean leaves a floating fragment (a lip over a pocket), keep the largest body - and find the cause.
- 2D cross product in numpy on (N, 2) arrays is deprecated: write `a[:,0]*b[:,1] - a[:,1]*b[:,0]`.

## Libraries

- `mesh.section()` needs **scipy**; `mesh.contains()` needs **rtree**; `polygons_full` pulls rtree too. Missing
  ones fail only when that call runs - put them in the script's dependency block.
- 3mf export needs **lxml** and **networkx**.
- `trimesh.load()` of a 3mf returns a Scene: `scene.dump()` gives the placed meshes.

## Pictures

- Cropping a render by its alpha: **clamp the start index at 0** (`max(0, ys.min() - pad)`). A part touching the
  frame edge gives a negative start, numpy wraps it, and the crop is empty ("zero-size array").
- Blender's default camera clip end culls a scene in millimetres ~1 m away: set `clip_end` high.
- Section plots: combine the loops with symmetric difference, or holes come out filled.

## Process

- A bed layout that "looks" fine can be 6 mm too wide: print the plate bounds on every run.
- Paths and names: say exactly which files to print; a stale 3mf from an older run looks just like the new one.
