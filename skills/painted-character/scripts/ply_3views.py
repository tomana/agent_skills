"""ply_3views.py - orthographic renders of a sculpt for the texture loop (Blender, headless).

Front (+z), back (-z) and side (-x) views of a y-up, face +z sculpt PLY, 2048 x 2560, workbench: a matte grey render
(rt_<view>.png, what the image model repaints) and a white-on-black silhouette (sil_<view>.png, what the paintings are
warped onto). Front/back ortho scale = 1.08 x the larger of the figure's width/height; the side view is framed on
depth x 2.2. Every later step (warp_to_silhouette, face_paint_front, body_texture_apply) assumes this framing.

Run: blender -b -P ply_3views.py -- SCULPT.ply OUTDIR
"""
import bpy, sys
import numpy as np
from mathutils import Vector
INP, OUT = sys.argv[sys.argv.index("--")+1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.ply_import(filepath=INP)
o=[x for x in bpy.data.objects if x.type=='MESH'][0]
bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active=o
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True); bpy.ops.object.shade_smooth()
me=o.data; n=len(me.vertices)
co=np.empty(n*3); me.vertices.foreach_get("co",co); co=co.reshape(n,3)
# Y-up sculpt frame, face +Z (kit convention)
ctr=Vector((0, float((co[:,1].min()+co[:,1].max())/2), float(co[:,2].mean())))
dimF=max(co[:,0].ptp(), co[:,1].ptp())*1.08
dimS=max(co[:,2].ptp()*2.2, co[:,1].ptp())*1.08
sc=bpy.context.scene; sc.render.engine='BLENDER_WORKBENCH'
sh=sc.display.shading
cd=bpy.data.cameras.new("c"); cam=bpy.data.objects.new("c",cd); sc.collection.objects.link(cam); sc.camera=cam
cd.type='ORTHO'; cd.clip_end=10000
w=bpy.data.worlds.new("w"); sc.world=w; w.use_nodes=False; sh.background_type='WORLD'
sc.render.resolution_x=2048; sc.render.resolution_y=2560
views=[("front",(0,0,40),dimF),("back",(0,0,-40),dimF),("side",(-40,0,0),dimS)]
for style in ("matte","sil"):
    if style=="matte":
        sh.light='STUDIO'; sh.color_type='SINGLE'; sh.single_color=(0.66,0.66,0.68)
        o.color=(0.66,0.66,0.68,1); w.color=(0.96,0.96,0.97)
    else:
        sh.light='FLAT'; sh.single_color=(1,1,1); o.color=(1,1,1,1); w.color=(0,0,0)
    for name,loc,dim in views:
        cd.ortho_scale=dim
        cam.location=ctr+Vector(loc)
        # explicit look-at with world up = +Y (Y-up sculpt frame; track-quat hints roll on side views)
        from mathutils import Matrix
        z=(cam.location-ctr).normalized(); up=Vector((0,1,0))
        x=up.cross(z).normalized(); y=z.cross(x)
        cam.rotation_euler=Matrix((x,y,z)).transposed().to_euler()
        pre = "rt_" if style=="matte" else "sil_"
        sc.render.filepath=f"{OUT}/{pre}{name}.png"; bpy.ops.render.render(write_still=True); print("R",style,name)
