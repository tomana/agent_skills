"""
Apply FRONT+BACK(+SIDE) body albedos (e.g. image-model repaints of our own orthographic renders) to a character ->
textured GLB + previews. Works on a RIGGED glb (armature + skin weights kept -> drop-in for the engine) or a plain
STL/PLY (a y-up sculpt is rotated to z-up first).

Fit: content-bbox -> mesh-bbox (fill-the-boundary at body scale). Textures painted
over our own orthographic renders register with a linear bbox map — no camera math.
Transparent-background textures are handled via their alpha (preferred mask).

Projection: per-face front/back pick by the face normal against the FRONT axis
(GLB convention: Z-up, face -Y; STL/PLY convention: Y-up, face +Z). Front-facing
polys UV into the left atlas half, back-facing into the right (x-mirrored). The seam
runs along the side silhouette; busy skin hides it.
Optional: TEX_SIDE - lateral faces (|nx| > |ny|) take a side panel instead; HEAD_UP - above this height every
front-facing face takes the front panel (the face's eye/nose walls otherwise took the side painting and left
seams on the cheeks); TEX_SIDE_NOARM (side_noarm.py) - lateral faces HIDDEN from the side camera (ray-cast; the
A-pose arm in front of the flank) sample this arm-free side painting instead of the arm.

Run: blender -b -P body_texture_apply.py -- MESH.{glb,stl,ply} TEX_FRONT TEX_BACK OUTDIR [TEX_SIDE] [HEAD_UP|-] [TEX_SIDE_NOARM]
Out: OUTDIR/atlas.png, OUTDIR/textured.glb, OUTDIR/prev_{front,back,three4}.png
"""
import bpy, sys, os
import numpy as np
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
MESH, TEXF, TEXB, OUT = a[0], a[1], a[2], a[3]
TEXS = a[4] if len(a) > 4 else None                   # optional SIDE texture (GLB path only)
HEAD_UP = float(a[5]) if len(a) > 5 and a[5] != "-" else None
TEXS2 = a[6] if len(a) > 6 else None                  # optional SIDE painting with the ARM taken out (side_noarm.py):
                                                      # the flank faces the arm hides from the side camera sample it
# HEAD_UP (sculpt units, the PLY's y): above it every FRONT-facing face takes the front panel, even the steep ones -
# the face's eye/nose walls otherwise took the side painting and left seams on the cheeks
os.makedirs(OUT, exist_ok=True)
IS_GLB = MESH.lower().endswith((".glb", ".gltf"))

# ---------- atlas: [front | back] ----------
def load_px(p):
    im = bpy.data.images.load(p); W, H = im.size
    return np.array(im.pixels[:], np.float32).reshape(H, W, 4), W, H
pf, WF, HF = load_px(TEXF)
pb, WB, HB = load_px(TEXB)
panels = [(pf, WF, HF), (pb, WB, HB)]
if TEXS:
    ps, WS, HS = load_px(TEXS)
    panels.append((ps, WS, HS))
if TEXS2:
    ps2, WS2, HS2 = load_px(TEXS2)
    panels.append((ps2, WS2, HS2))
H = max(p[2] for p in panels)
def padH(px, Hs):
    if Hs == H: return px
    out = np.zeros((H, px.shape[1], 4), np.float32); out[:Hs] = px; return out
panels = [(padH(px, Hs), Wp) for px, Wp, Hs in panels]
atlas = np.concatenate([p[0] for p in panels], axis=1)
AW = sum(p[1] for p in panels)
offs = np.cumsum([0] + [p[1] for p in panels])         # panel start columns
img = bpy.data.images.new("atlas", AW, H, alpha=True)
img.pixels[:] = atlas.ravel()
img.filepath_raw = os.path.join(OUT, "atlas.png"); img.file_format = 'PNG'; img.save()

def content_bbox(px):
    Hh, Ww = px.shape[:2]
    if px[:, :, 3].min() < 0.5:                       # transparent bg -> alpha mask
        r = px[:, :, 3] > 0.5
    else:
        g = px[:, :, :3].mean(2)
        bg = float(np.median(np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])))
        r = np.abs(g - bg) > 0.06
    # robust to opaque border frames: largest component NOT touching the image border
    # (scipy is absent inside Blender's python -> then rely on the warp step's clean alpha)
    try:
        from scipy.ndimage import label
        lab, nlab = label(r)
        border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        sizes = [(lab == i).sum() if i not in border else 0 for i in range(1, nlab + 1)]
        if sizes and max(sizes) > 0:
            r = lab == (1 + int(np.argmax(sizes)))
    except ImportError:
        pass
    ys, xs = np.where(r)
    return xs.min()/(Ww-1), xs.max()/(Ww-1), ys.min()/(H-1), ys.max()/(H-1)  # u0,u1,v0,v1 bottom-up
fu0, fu1, fv0, fv1 = content_bbox(panels[0][0])
bu0, bu1, bv0, bv1 = content_bbox(panels[1][0])
if TEXS:
    su0, su1, sv0, sv1 = content_bbox(panels[2][0])
print(f"front content u[{fu0:.3f},{fu1:.3f}] v[{fv0:.3f},{fv1:.3f}]  back u[{bu0:.3f},{bu1:.3f}]" + (f"  side u[{su0:.3f},{su1:.3f}]" if TEXS else ""))

# ---------- mesh ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
img = bpy.data.images.load(os.path.join(OUT, "atlas.png"))
if IS_GLB:
    bpy.ops.import_scene.gltf(filepath=MESH)
elif MESH.lower().endswith(".ply"):
    bpy.ops.wm.ply_import(filepath=MESH)
else:
    bpy.ops.wm.stl_import(filepath=MESH)
o = max((x for x in bpy.data.objects if x.type == 'MESH'), key=lambda m: len(m.data.vertices))
if not IS_GLB:
    # sculpt PLY/STL is Y-up face +Z: rotate into the GLB convention (Z-up, face -Y)
    # so the SAME projection path (incl. the side patch) applies, and the exported
    # glb comes out upright everywhere.
    import math
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    o.rotation_euler = (math.pi/2, 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    IS_GLB = True                                   # from here on: GLB convention
me = o.data
mw = np.array(o.matrix_world)
L, T = mw[:3, :3], mw[:3, 3]
NM = np.linalg.inv(L).T                               # normal matrix
n = len(me.vertices)
co = np.empty(n*3); me.vertices.foreach_get("co", co)
co = co.reshape(n, 3) @ L.T + T                       # WORLD coords (no transform_apply on rigged obj)
if IS_GLB:                                            # Z-up, face -Y: across=X, up=Z, front ny<0
    ACROSS, UP, DEPTH = co[:, 0], co[:, 2], co[:, 1]
    def world_n(normals): return normals @ NM.T
    def front_of(normals): return world_n(normals)[:, 1] < 0
else:                                                 # Y-up, face +Z
    ACROSS, UP, DEPTH = co[:, 0], co[:, 1], co[:, 2]
    def world_n(normals): return normals @ NM.T
    def front_of(normals): return world_n(normals)[:, 2] >= 0
mx0, mx1 = ACROSS.min(), ACROSS.max()
my0, my1 = UP.min(), UP.max()
print(f"mesh across[{mx0:.2f},{mx1:.2f}] up[{my0:.2f},{my1:.2f}]  ({'GLB' if IS_GLB else 'STL/PLY'} convention)")

tx = (ACROSS - mx0) / (mx1 - mx0)                     # 0..1 left->right AS SEEN FROM THE FRONT (world +X right)
ty = (UP - my0) / (my1 - my0)                         # 0..1 feet->crown  (bottom-up, matches bpy pixel rows)
def panel_uv(i, cu0, cu1, cv0, cv1, frac, tyv):
    o, wfrac = offs[i] / AW, panels[i][1] / AW
    return o + (cu0 + frac * (cu1 - cu0)) * wfrac, cv0 + tyv * (cv1 - cv0)
uf, vf = panel_uv(0, fu0, fu1, fv0, fv1, tx, ty)
ub, vb = panel_uv(1, bu0, bu1, bv0, bv1, 1 - tx, ty)  # back view mirrors X
if TEXS:
    dz0, dz1 = DEPTH.min(), DEPTH.max()
    td = (DEPTH - dz0) / (dz1 - dz0)                  # 0..1 front->back of the body
    # BOTH flanks use the same (depth,height) map: on a bilaterally symmetric body the
    # right flank is the mirror IMAGE of the left, so identical sampling lands features
    # at the same anatomical spots. (A u-mirror samples empty zones -> smear streaks.)
    # content-RIGHT = body front in the side painting -> reversed map; both flanks
    # identical (symmetric body: right flank = mirror image of left).
    usl, vsl = panel_uv(2, su0, su1, sv0, sv1, 1 - td, ty)
    usr, vsr = usl, vsl
    if TEXS2:                                         # same frame, the 4th panel (same figure bbox as the side's)
        un, vn = panel_uv(3, su0, su1, sv0, sv1, 1 - td, ty)

uvl = me.uv_layers.new(name="proj")
loops_v = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", loops_v)
pn = np.empty(len(me.polygons)*3); me.polygons.foreach_get("normal", pn)
ltot = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get("loop_total", ltot)
wn = world_n(pn.reshape(-1, 3))
is_front = np.repeat(front_of(pn.reshape(-1, 3)), ltot)
uv = np.empty((len(me.loops), 2), np.float32)
uv[:, 0] = np.where(is_front, uf[loops_v], ub[loops_v])
uv[:, 1] = np.where(is_front, vf[loops_v], vb[loops_v])
if TEXS and IS_GLB:
    lateral = np.abs(wn[:, 0]) > np.abs(wn[:, 1])     # |nx| beats |ny| -> side patch
    pc = np.empty(len(me.polygons)*3); me.polygons.foreach_get("center", pc); pc = pc.reshape(-1, 3) @ L.T + T
    if HEAD_UP is not None:
        lateral &= ~((pc[:, 2] > HEAD_UP) & (wn[:, 1] < 0))   # GLB convention: up = z, front = -y
    # OCCLUSION (arm shadows down the flanks): the side painting sees the A-pose ARM in
    # front of the torso's flank, so a flank face sampling it got the arm (its edges and shading) painted down the
    # body. A lateral face takes the side panel only if a ray from it toward the side camera (+x or -x) hits nothing;
    # an occluded one keeps its front/back projection (steep, but the skin is even).
    from mathutils.bvhtree import BVHTree
    wv = np.array([tuple(v.co) for v in me.vertices]) @ L.T + T
    bvh = BVHTree.FromPolygons([tuple(v) for v in wv], [tuple(p_.vertices) for p_ in me.polygons])
    eps = 1e-3*float(np.ptp(wv[:, 2]))
    occl = np.zeros(len(me.polygons), bool)
    for i in np.where(lateral)[0]:
        d = Vector((1.0 if wn[i, 0] >= 0 else -1.0, 0.0, 0.0))
        hit = bvh.ray_cast(Vector(pc[i]) + d*eps, d)
        occl[i] = hit[0] is not None
    lateral &= ~occl
    if TEXS2:
        is_hid = np.repeat(occl, ltot)
        uv[:, 0] = np.where(is_hid, un[loops_v], uv[:, 0]); uv[:, 1] = np.where(is_hid, vn[loops_v], uv[:, 1])
    print(f"side patch: {int(occl.sum())} lateral faces hidden from the side camera (arms in front) -> "
          + ("the arm-free side painting" if TEXS2 else "front/back"))
    is_left = np.repeat(lateral & (wn[:, 0] >= 0), ltot)
    is_right = np.repeat(lateral & (wn[:, 0] < 0), ltot)
    uv[:, 0] = np.where(is_left, usl[loops_v], uv[:, 0])
    uv[:, 1] = np.where(is_left, vsl[loops_v], uv[:, 1])
    uv[:, 0] = np.where(is_right, usr[loops_v], uv[:, 0])
    uv[:, 1] = np.where(is_right, vsr[loops_v], uv[:, 1])
    print(f"UVs: {int(is_front.sum())} front / {int(is_left.sum())+int(is_right.sum())} side loops")
else:
    print(f"UVs: {int(is_front.sum())} front loops / {int((~is_front).sum())} back loops")
uvl.data.foreach_set("uv", uv.ravel())
chk = np.empty(len(me.loops)*2); uvl.data.foreach_get("uv", chk); chk = chk.reshape(-1, 2)
print(f"UV VERIFY: u[{chk[:,0].min():.3f},{chk[:,0].max():.3f}] v[{chk[:,1].min():.3f},{chk[:,1].max():.3f}]")

mat = bpy.data.materials.new("skin"); mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
t = mat.node_tree.nodes.new("ShaderNodeTexImage"); t.image = img
mat.node_tree.links.new(bsdf.inputs["Base Color"], t.outputs["Color"])
bsdf.inputs["Roughness"].default_value = 0.8
me.materials.clear(); me.materials.append(mat)
bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
bpy.ops.object.shade_smooth()

# ---------- previews ----------
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading; sh.color_type = 'TEXTURE'; sh.light = 'STUDIO'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = False; w.color = (0.06, 0.06, 0.07); sh.background_type = 'WORLD'
for ob in bpy.data.objects:
    ob.hide_render = (ob.type == 'MESH' and ob is not o)
sc.render.resolution_x = 1100; sc.render.resolution_y = 1400
if IS_GLB:
    ctr = Vector((0, float(co[:, 1].mean()), float((my0+my1)/2)))
    F = Vector((0, -40, 0)); B = Vector((0, 40, 0)); Q = Vector((-28, -28, 6))
else:
    ctr = Vector((0, float((my0+my1)/2), float(co[:, 2].mean())))
    F = Vector((0, 0, 40)); B = Vector((0, 0, -40)); Q = Vector((28, 6, 28))
dim = max(mx1-mx0, my1-my0) * 1.08
cd = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cd.type = 'ORTHO'; cd.ortho_scale = dim; cd.clip_end = 10000
def shoot(loc, path):
    cam.location = ctr + loc
    cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("RENDERED", path)
shoot(F, os.path.join(OUT, "prev_front.png"))
shoot(B, os.path.join(OUT, "prev_back.png"))
shoot(Q, os.path.join(OUT, "prev_three4.png"))

# ---------- export (rig rides along for GLB input) ----------
# strip vertex colors: glTF multiplies COLOR_0 into the base texture -> darkens
while me.color_attributes:
    me.color_attributes.remove(me.color_attributes[0])
bpy.ops.object.select_all(action='DESELECT')
o.select_set(True)
if IS_GLB:
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE': ob.select_set(True)
bpy.context.view_layer.objects.active = o
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "textured.glb"), use_selection=True)
print(f"WROTE {OUT}/textured.glb")
