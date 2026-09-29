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

## Eyes: skins that differ only in the eyes

- Keep one portrait with plain (e.g. black) eyes; every variant is that portrait with only the eyes changed, so the
  skins share one UV layout and crossfade cleanly.
- **Exact eyes from any picture**: `eye_transplant.py --orig portrait.png --src <picture> --out portrait_eyes.png`
  finds the source's eyes as low-saturation blobs ringed by skin (any image size; a 45 px source eye fills a ~76 px
  texture eye fine) and maps them into the portrait's almonds by paired outlines. Then the same
  `face_paint_front.py` -> `delight.py` -> `body_texture_apply.py`, into its own folder.
- An image-model repaint of the portrait ("change ONLY the eyes, like reference 2") gives a sharper, not exact,
  alternative - transplant its eyes the same way, since the rest of its face drifts.
- Procedurally drawn irises look like a cartoon. Don't.

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
