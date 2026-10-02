---
name: painted-character
description: Take a sculpted character from a reference painting to a textured, rig-ready mesh - SculptGL round trips (recolour, cut the head off and stitch it back, decimate by region), imprinting a painted face as relief, image-model repaints of your own renders warped onto the silhouettes, pasting the painting's face and MORPHING it onto the sculpted features, removing painted lighting and arm shadows, eye variants taken from any picture, and projection to a textured glb with swappable skins. Use whenever someone sculpts or paints a character, asks for a texture "like this picture", wants eyes / pupils / a face from a reference, a head-only sculpt round, fewer polygons with the detail kept, or a character ready for rigging.
---

# painted-character

A loop between a browser sculpting tool ([SculptGL](https://stephaneginier.com/sculptgl/)), headless Blender and
small numpy/trimesh scripts. Every script is a self-contained `uv run --script` in `scripts/`; the Blender ones run
as `blender -b -P script.py -- args`. Conventions: the sculpt is **y-up, face toward +z**; the examples use an
18.5-unit figure with the head above y ~15.5 - read your own heights off a gridded render.

## The rules that made it work

1. **Read, don't generate, where a picture was given.** "This exact face" means its pixels: imprint the painting
   itself as relief (`ply_imprint.py`), paste its face into the texture (`face_paint_front.py`), take its eyes
   (`eye_transplant.py --src <that picture>`). An image model is for what no picture covers - the body, the back,
   the side.
2. **Morph the paint onto the sculpt, don't hope it lines up.** Read the sculpted features (eyes, nose tip, mouth
   corners, chin) off a gridded front render, read the painted ones, and bend the painting onto the sculpt with a
   thin-plate spline (`--morph pairs.json`). A few points per eye get its centre and size; the eye OUTLINE needs
   ~24 paired points (`eye_outline_pairs.py` reads the sculpted rim from a depth map). The mouth needed 3 pairs.
3. **Check alignment with an overlay**, not by eye: draw the painted feature's edge in magenta on the grey render,
   and check that the vertex in the middle of the sculpted eye samples the eye colour in the atlas.
4. **Keep the alpha.** The projector finds the figure by it; an RGB-only paste made the whole frame the "figure" and
   slid the face down onto the cheeks.
5. **Show a picture at every step** - before/after, the face close-up, the engine screenshot. Most of the fixes
   above started as "that looks off" on a picture.
6. **Go back to the densest export** for each decimation; decimating a decimated mesh compounds the error.
7. **Anti-alias every downsample.** A portrait pasted at a quarter of its resolution without a low-pass turns canvas
   grain into noise (the face came out ~10x noisier than the body); a gaussian at 0.5 x the shrink factor fixes it.
8. **Measure, then change one thing.** Seam bias, grain (high-pass std), face |diff| after a change - numbers from
   the bake, next to a picture, beat eyeballing.

## The whole process, as it went (a worked example)

One character, start to finish, over two sittings - the order that worked, and where each step came from:

1. **The target is a picture the person already has** (a painted front portrait). Every later step is judged against it.
2. **Sculpt toward it**: recolour the sculpt to a contrasting flat colour (`skin_paint.py`), the person smooths the
   face and reshapes the head so its outline matches the portrait.
3. **Imprint the portrait as relief** (`ply_imprint.py --morph 0`), tried at several face sizes against the head
   (x0.95 ... x1.3, rendered side by side); the person picks one.
4. **Cut the head off** (`head_cut.py`), the person sculpts it alone (much easier in a browser sculptor), **stitch it
   back** (`head_transplant.py --no-align`: watertight, nothing moves outside the neck band).
5. **Decimate the head only** to the budget (`region_decimate.py`, e.g. ~20k triangles for the whole figure).
6. **Render the sculpt** front/back/side with silhouettes (`ply_3views.py`); an **image model repaints each render**
   in the portrait's look (`codex_img.sh`, reference 1 = our render, reference 2 = the portrait); **warp** each onto
   its silhouette (IoU ~0.98).
7. **Trace the sculpted eye rim** (ridge along rays on the dense sculpt, geometric almond fit, corners read off the
   debug plot) and **paste the portrait's face morphed onto the sculpt** (`face_paint_front.py --morph`, anti-aliased).
8. **Eye skins** from real pictures (`eye_transplant.py`: a book cover's own eyes; a whole image-model repaint with
   `--whole`); procedural pupils were dropped - they looked like a cartoon.
9. **Remove painted light** (`delight.py`, one target for all panels) and the **arm shadows** on the flanks.
10. **Bake blended** into one atlas (`blend_bake.py`): rim-depth weights, harmonic fill of the arm-hidden flank, a
    smooth side-to-front/back gain field; the front (the face) never changes. All skins share one `uvs.npz`.
11. **Check by rendering in the paintings' frames** (`render_like_views.py`) next to the paintings, and in the target
    engine on recorded motion; fix the cause, re-bake, show.
12. **Rig** (transfer weights from a good rig of the same body), install the skins, verify in the engine.

What it took to get "really good": the morphs (mouth, then the eye outline), the blended bake (seams), measuring the
transition bands (panel rims, not panel interiors, were off), and anti-aliasing the face (grain).

## SculptGL round trips (PLY in, PLY out)

Never route a sculpt through glTF (it splits vertices along UV seams). SculptGL PLYs carry a duplicate face block
that trimesh rejects - read them with `scripts/sculptgl_io.py`; SculptGL also reorders vertices, so compare exports
by position (KD-tree), not by index.

| want | command |
|---|---|
| one flat colour / no paint (a contrasting colour makes SculptGL's transparency usable) | `skin_paint.py --in X.ply --out Y.ply --skin 40,180,230` (`--no-colour`) |
| sculpt the head alone | `head_cut.py --in full.ply --out head.ply --y 15.80` |
| stitch it back | `head_transplant.py --body full.ply --head head_sculpted.ply --cut-body 15.70 --cut-head 15.90 --no-align --out new.ply` - watertight, unchanged outside the neck band; don't move or scale the head while sculpting it |
| another sculpt's head on this body | `head_transplant.py --body body.ply --head other.stl --cut-body .. --cut-head .. --out ..` |
| fewer polygons, detail kept | Blender's quadric decimate with X-symmetry, the body and the head at their own ratios (e.g. head only x0.33 -> ~20k tris total) |
| a painted face as relief | `ply_imprint.py --in mesh.ply --img painting.png --img-lm img.json --mesh-lm mesh.json --morph 0 --eye-depth 0.08 --form 0.015 --smooth 2 --scale 0.95` - smooth the face first; try `--scale` 0.95 / 1.0 / 1.1 (face size vs head) and pick |

## The texture loop

```bash
T=tex; M=decimated.ply; P=painting.png
blender -b -P ply_3views.py -- $M $T                        # rt_{front,back,side}.png renders + sil_* silhouettes
codex_img.sh $T/tex_front.png "FRONT VIEW. $(cat prompt_skin.txt)" $T/rt_front.png $P      # and back, side
for s in front back side; do warp_to_silhouette.py $T/tex_$s.png $T/sil_$s.png $T/warp_$s.png; done
eye_outline_pairs.py --mesh $M --img $P --img-lm img.json --mesh-lm mesh.json --scale 0.95 \
    --base face_morph.json --out face_morph_eyes.json --eye 0.45,17.6 --debug eye_pairs.png
face_paint_front.py --mesh $M --front $T/warp_front.png --img $P --img-lm img.json --mesh-lm mesh.json \
    --scale 0.95 --morph face_morph_eyes.json --out $T/warp_front_face.png
side_noarm.py $M $T/warp_side.png $T/warp_side_noarm.png                  # the flank the arm hides
for f in front_face back side side_noarm; do delight.py $T/warp_$f.png $T/warp_${f}_flat.png --head-row 432 --target 155; done
blender -b -P body_texture_apply.py -- $M $T/warp_front_face_flat.png $T/warp_back_flat.png $T/skin0 \
    $T/warp_side_flat.png 16.3 $T/warp_side_noarm_flat.png                # -> textured.glb + atlas.png
```

- **The repaint prompt**: keep EXACTLY the pose, silhouette, proportions and framing of reference 1 (your render),
  the look of reference 2 (the painting); flat, even light; plain background; no text. The model held the pose well
  enough that the warp reached a silhouette IoU of ~0.98. Two generations can run at once; ~2 min each.
- **Why paste the face**: a whole-figure painting gives the head ~230 px; the portrait gives ~1000.
- **Arm shadows down the flanks** had two causes: the side painting shows the A-pose ARM in front of the torso (the
  projector ray-casts each lateral face to its side camera; hidden faces sample `side_noarm`'s arm-free painting),
  and the model's own form shading (`delight.py`, with the SAME `--target` for every panel or they meet in steps).
- `body_texture_apply.py`'s 6th argument (a height) sends every front-facing face of the head to the front panel,
  so the eye and nose walls don't pick up the side painting.
- `codex_img.sh` needs the Codex CLI installed and logged in with a ChatGPT subscription (no API key); it forces
  Codex's built-in image generation and forbids it from drawing the image with code.

## Tracing a sculpted feature's rim (`eye_outline_pairs.py`)

The step that made painted eyes sit in sculpted almonds, and what failed on the way:

1. **Depth map, not a render.** Rays along -z over the feature on a fine grid (`--step 0.002`) give z(x, y). Trace on
   the DENSE sculpt (`--trace-mesh`, same shape) - a decimated mesh makes the rim coarse.
2. **The rim is a line of steep slope.** |grad z| minus its own gaussian blur (a top-hat) turns lid edges into thin
   bright lines. (A "local depression" test fails when the eye floor is a low dome.)
3. **The region those lines enclose** round a seed inside the feature is only a guide - its edge sits inside the rim
   and is jagged.
4. **Follow the ridge**: 360 rays from the region's centre; on each, the strongest top-hat value in a window just
   outside the region's edge, refined by a parabola through 3 samples; a median (9 rays) drops outliers and a
   gaussian smooths along the rim.
5. **Fit a geometric shape** to the ridge (for an almond: pointed corners, each lid t(1-t)(c0 + c1 t + c2 t^2) over the
   corner-to-corner chord) and **morph the paint onto the fit, never the raw trace** - a traced outline follows every
   bump of the sculpt and the paint comes out squiggly. Corners are the weak spot: automatic tip-finding stops short
   or runs into neighbouring slopes, so read them off the debug picture where the rim lines meet (`--corners`).
6. **Knobs for the person judging the overlay**: `--grow` (whole shape, moves the corners), `--upper`/`--lower` (one
   lid's height, corners fixed), `--inset` (inside the rim). With a good ridge trace none should be needed.
7. **Pair by angle** (~24 points round each centroid), mirror for the other side, add the nose/mouth/chin pairs, and
   feed the face paste's `--morph`. Check with the painted edge drawn over the grey render and the debug plot.

The same recipe fits any sculpted feature with a crisp rim (lips, nostrils, a mask edge): depth map -> top-hat slope
-> ridge along rays -> smooth -> geometric fit -> paired thin-plate morph.

## Eyes: skins that differ only in the eyes

- To take a WHOLE repainted face (not just its eyes): `eye_transplant.py --orig portrait.png --src repaint.png --whole`
  bends it into the portrait's frame (eye outlines, mouth line, head outline, border pinned).

- Keep one portrait with plain (e.g. black) eyes; every variant is that portrait with only the eyes changed, so the
  skins share one UV layout and crossfade cleanly.
- **Exact eyes from any picture**: `eye_transplant.py --orig portrait.png --src <picture> --out portrait_eyes.png`
  finds the source's eyes as low-saturation blobs ringed by skin (any image size; a 45 px source eye fills a ~76 px
  texture eye fine) and maps them into the portrait's almonds by paired outlines. DARK eyes on a grey canvas (the
  canvas is as unsaturated as the eyes, so the default grabs the background): `--src-dark 0.22` finds them by
  luminance instead. Then the same `face_paint_front.py` -> `delight.py` -> bake, into its own skin file.
- An image-model repaint of the portrait ("change ONLY the eyes, like reference 2") gives a sharper, not exact,
  alternative - transplant its eyes the same way, since the rest of its face drifts.
- A print's dark-grey eyes read grey on the model: `eye_transplant.py --black 4` levels each pasted eye so its 30th
  percentile lands at 4 (a uniform subtract - the detail inside keeps its contrast).
- **Shiny eyes**: if the renderer reads a gloss mask + roughness map in the colour UV, `eye_material_maps.py OUT_BASE
  skin_0.png skin_1.png ...` builds them with no geometry - the skins differ only in the eyes, so where they differ IS
  the eye (feed only eye-only variants, not one with a whole repainted face). R = glint mask, G = darkening (0),
  A = the glint's spread (0 = a small wet highlight; a broad lobe on a domed eye lights the whole eye like chrome),
  roughness low in the eyes, the renderer's default on the skin. Keep grey maps working: have the shader read G / A
  so a one-channel map (G = R, A = 1) keeps its old meaning.
- **Sculpt with the texture visible**: `atlas_to_sculptgl.py` puts the baked atlas onto the dense sculpt as vertex colours
  (closest point on the decimated mesh -> its UVs -> the atlas; written linear, the way SculptGL expects).
- **Hand-fixed paint back into the texture**: sculpt with the texture on, drag the eyes until they are right, then
  `vcolors_to_atlas.py` bakes that PLY's colours into the atlas (round trip median 0, p99 8 levels), and
  `eye_outline_pairs.py --paint-ply <that PLY>` makes the dark eye paint the target outline for every other eye skin.
- Procedurally drawn irises look like a cartoon. Don't.

## Bake it blended, and check it the same way (the final step)

Per-triangle projection (`body_texture_apply.py`) switches panel along triangle edges: wherever two paintings meet
and disagree in tone you get a jagged seam (the temple, the flank). Bake instead:

```bash
blender -b -P blend_bake_io.py -- export MESH.ply blend/session.blend blend/mesh.npz
./xatlas_unwrap.py blend/mesh.npz blend/uvs.npz
./blend_bake.py blend/mesh.npz blend/uvs.npz front.png back.png side.png side_noarm.png blend/skin.png   # ~20 s at 4096
blender -b -P blend_bake_io.py -- build blend/session.blend blend/uvs.npz blend/skin.png blend/skin.glb
```
Every texel samples all panels and mixes them by its interpolated normal, weighted also by how deep inside each
painting's own silhouette it lands (paintings darken at their outlines); the flank hidden behind an arm is filled
harmonically from the visible surface; the side is pulled to front/back by a smooth field; the front never changes (the portrait leads on the face; hidden
flanks use the arm-free side). Bake every skin with the same `uvs.npz` so they share one UV layout.

**How to find what's wrong:** `render_like_views.py` renders the textured model in the paintings' own frames (flat
light); put the render next to the painting with a difference map, name the cause (not the symptom), change one
thing, re-render, show it. The same loop drives the feature morph: trace the rim, overlay, adjust.

## Handoff to the rig

`textured.glb` is unrigged, UV-mapped, with the atlas `[front | back | side | side without the arm]` embedded.
Transfer the skin weights from an already-good rig of the same body (nearest-surface transfer is fine when the body
is the same; bone-heat for a new body), keep the UVs, and drop the other variants' `atlas.png` next to it as
swappable skins - same pixel size, same layout. Verify in the engine on a recording or a fixed pose, with a
screenshot per skin.

## Open ends

- The front/side seam on the side of the head and the backs of the legs are paint-over territory (edit the atlas at
  its pixel size and it drops back in).
- A next loop: render the TEXTURED head, have the model refine that render, and project it back in the head's frame.
