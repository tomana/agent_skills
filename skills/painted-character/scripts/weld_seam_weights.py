# weld_seam_weights.py - one weight set per POSITION, so UV seams can't crack open when a rig bends.
#
# A textured glb splits vertices along every UV seam. A weight transfer samples each copy separately, and any
# per-vertex smoothing pass sees the copies as unconnected, so copies of one point end up with different bone weights
# (measured on a production character: hundreds of pairs, up to 0.8 apart, most on the neck) - under skinning they move
# apart and the seam opens as thin cracks / light specks. Run this LAST, after every weight pass:
#   1. group the vertices by position (all copies within --eps, KD-tree + union-find - rounding to a grid splits
#      copies that straddle a cell edge)
#   2. each group's weights = the mean of its copies' weights
#   3. optional seam-aware smoothing on the WELDED graph (iters, inside a z band) - off by default
#   4. keep the strongest MAXINF bones (4 = one JOINTS_0/WEIGHTS_0 set) and renormalise, the same for every copy
#   5. write the group's weights to every copy; export
#
#   blender -b --python weld_seam_weights.py -- in=<rig.glb> out=<glb> [eps=1e-5] [maxinf=4] [iters=0] [zmin] [zmax]
import bpy, sys
import numpy as np

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
def arg(k, d=None):
    for a in argv:
        if a.startswith(k+"="): return a.split("=", 1)[1]
    return d
IN, OUT = arg("in"), arg("out")
EPS, MAXINF, ITERS = float(arg("eps", "1e-5")), int(arg("maxinf", "4")), int(arg("iters", "0"))
ZMIN, ZMAX = float(arg("zmin", "-1e9")), float(arg("zmax", "1e9"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
arm  = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
mesh = next(o for o in bpy.data.objects if o.type == 'MESH')
me = mesh.data; nv = len(me.vertices); ng = len(mesh.vertex_groups)
Mm = mesh.matrix_world
co = np.array([(Mm @ v.co)[:] for v in me.vertices])
W = np.zeros((nv, ng), np.float64)
for v in me.vertices:
    for g in v.groups: W[v.index, g.group] = g.weight

# 1-2: weld by position (a KD-tree radius + union-find - rounding to a grid splits copies that straddle a cell edge),
# average
from mathutils import kdtree
kd = kdtree.KDTree(nv)
for i, c in enumerate(co): kd.insert(c, i)
kd.balance()
par = np.arange(nv)
def find(i):
    while par[i] != i: par[i] = par[par[i]]; i = par[i]
    return i
for i, c in enumerate(co):
    for (_, j, _) in kd.find_range(c, EPS):
        a, b = find(i), find(j)
        if a != b: par[max(a, b)] = min(a, b)
roots = np.array([find(i) for i in range(nv)])
_, wid, counts = np.unique(roots, return_inverse=True, return_counts=True)
wid = wid.ravel(); nw = int(wid.max()) + 1
Wg = np.zeros((nw, ng)); np.add.at(Wg, wid, W); Wg /= np.bincount(wid, minlength=nw)[:, None]
before = np.abs(W - Wg[wid]).sum(1)
split = counts[wid] > 1

# 3: optional seam-aware smoothing on the welded graph
if ITERS > 0:
    zg = np.zeros(nw); np.add.at(zg, wid, co[:, 2]); zg /= np.bincount(wid, minlength=nw)
    adj = [set() for _ in range(nw)]
    for e in me.edges:
        a, b = wid[e.vertices[0]], wid[e.vertices[1]]
        if a != b: adj[a].add(b); adj[b].add(a)
    act = np.where((zg > ZMIN) & (zg < ZMAX))[0]
    adjl = [np.fromiter(adj[i], int) for i in range(nw)]
    for _ in range(ITERS):
        Wn = Wg.copy()
        for i in act:
            if len(adjl[i]): Wn[i] = 0.5*Wg[i] + 0.5*Wg[adjl[i]].mean(0)
        Wg = Wn

# 4: the strongest MAXINF bones, renormalised
order = np.argsort(-Wg, axis=1)
keep = np.zeros_like(Wg, bool); np.put_along_axis(keep, order[:, :MAXINF], True, axis=1)
Wg = np.where(keep, Wg, 0.0); s = Wg.sum(1, keepdims=True); Wg = np.where(s > 1e-9, Wg/np.maximum(s, 1e-9), Wg)

# 5: write back - every copy of a position gets the same weights
Wn = Wg[wid]
for g in range(ng):
    vg = mesh.vertex_groups[g]
    nz = np.where(Wn[:, g] > 1e-6)[0]; z0 = np.where((Wn[:, g] <= 1e-6) & (W[:, g] > 0))[0]
    if len(z0): vg.remove([int(i) for i in z0])
    for i in nz: vg.add([int(i)], float(Wn[i, g]), 'REPLACE')
print(f"WELD_SEAMS {nv} verts -> {nw} positions ({int(split.sum())} copies on seams); copies that disagreed > 0.02: "
      f"{int((before[split] > 0.02).sum())} (max {before.max():.2f}); influences capped at {MAXINF}; smoothing iters {ITERS}", flush=True)

bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True); arm.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format='GLB',
                          export_yup=True, export_skins=True, export_normals=True,
                          export_materials='EXPORT', export_texcoords=True, export_image_format='AUTO')
print(f"EXPORTED {OUT}", flush=True)
