"""render_like_views.py - render a textured glb in EXACTLY the frames ply_3views.py rendered the sculpt in (front, back,
side; ortho, 2048 x 2560), flat-lit so only the texture shows - to put the model next to the paintings it was projected
from and see where the projection loses them.

Frame = ply_3views.py's: ortho scale 1.08 x max(width, height) for front/back, 1.08 x max(2.2 x depth, height) for the
side; centred on x = 0, mid-height, mean depth. The glb is in glTF convention (Blender: z up, face -y).

  blender -b -P render_like_views.py -- textured.glb OUTDIR [flat|studio]   -> OUTDIR/re_{front,back,side}.png
"""
import bpy, sys, os
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]; GLB, OUT = a[0], a[1]; LIGHT = (a[2] if len(a) > 2 else "flat").upper()
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
ms = [o for o in bpy.data.objects if o.type == "MESH"]
co = np.vstack([np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices]) for o in ms])
for o in ms: bpy.context.view_layer.objects.active = o; o.select_set(True)
bpy.ops.object.shade_smooth()
sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"; sc.view_settings.view_transform = "Standard"
sh = sc.display.shading; sh.light = LIGHT; sh.color_type = "TEXTURE"; sh.show_cavity = False
sc.render.film_transparent = True; sc.render.resolution_x, sc.render.resolution_y = 2048, 2560
ptp = np.ptp(co, 0); ctr = Vector((0.0, float(co[:, 1].mean()), float((co[:, 2].min() + co[:, 2].max())/2)))
dimF = max(ptp[0], ptp[2])*1.08; dimS = max(ptp[1]*2.2, ptp[2])*1.08
cd = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cd.type = "ORTHO"; cd.clip_end = 10000
for name, d, dim in (("front", Vector((0, -40, 0)), dimF), ("back", Vector((0, 40, 0)), dimF), ("side", Vector((-40, 0, 0)), dimS)):
    cd.ortho_scale = dim; cam.location = ctr + d
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, f"re_{name}.png"); bpy.ops.render.render(write_still=True); print("R", name)
