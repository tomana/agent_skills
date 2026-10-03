# shoulder_field.py - keep the UPPER-ARM bone off the chest, so a raised arm doesn't crumple the chest beside the neck.
#
# Weight transfers (and "shoulder follows the arm" passes) often leave the upper-arm bone owning the top of the chest
# well inside the joint (measured on a production character: 0.3-0.45 halfway between the neck and the joint). Per side:
#   s(v)   = position along the collar joint -> shoulder joint axis (0 at the collar joint, 1 at the shoulder)
#   keep   = smoothstep(S0, S1, s): how much of its upper-arm weight a vertex keeps (0 inside, 1 at/after the joint)
#   region = near that axis (radius RAD, fading over FALL), above the armpit (z > shoulder_z - BELOW, fading over FALLZ)
#   Shldr -> Shldr*(1 - f*(1 - keep)); the removed weight goes to the Collar bone; totals kept
# then a light seam-aware Laplacian on {Shldr, Collar}; run weld_seam_weights.py after it (last).
# Bone names follow the DAZ/Poser convention (lShldr/lCollar, rShldr/rCollar) - adapt for other rigs.
#
#   blender -b --python shoulder_field.py -- in=<rig.glb> out=<glb> [s0=0.3] [s1=1.1] [rad=0.9] [fall=0.5]
#                                         [below=0.35] [fallz=0.4] [iters=10]
import bpy, sys
import numpy as np

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
def arg(k, d=None):
    for a in argv:
        if a.startswith(k+"="): return a.split("=", 1)[1]
    return d
IN, OUT = arg("in"), arg("out")
S0, S1 = float(arg("s0", "0.45")), float(arg("s1", "1.0"))
RAD, FALL = float(arg("rad", "0.9")), float(arg("fall", "0.5"))
BELOW, FALLZ = float(arg("below", "0.35")), float(arg("fallz", "0.4"))
ITERS = int(arg("iters", "6"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
arm  = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
mesh = next(o for o in bpy.data.objects if o.type == 'MESH')
M = arm.matrix_world
P = {b.name: np.array((M @ b.head_local)[:]) for b in arm.data.bones}
me = mesh.data; nv = len(me.vertices); Mm = mesh.matrix_world
co = np.array([(Mm @ v.co)[:] for v in me.vertices])
gi = {g.name: g.index for g in mesh.vertex_groups}
W = np.zeros((nv, len(gi)), np.float64)
for v in me.vertices:
    for g in v.groups: W[v.index, g.group] = g.weight
W0 = W.copy()
def sstep(a, b, x):
    t = np.clip((x - a)/max(1e-6, b - a), 0.0, 1.0); return t*t*(3.0 - 2.0*t)

adj = [[] for _ in range(nv)]
for e in me.edges:
    a, b = e.vertices; adj[a].append(b); adj[b].append(a)
# seam-aware neighbours: copies of a position share their neighbours
key = np.round(co/1e-5).astype(np.int64); _, wid = np.unique(key, axis=0, return_inverse=True); wid = wid.ravel()
groups = {}
for i, w in enumerate(wid): groups.setdefault(int(w), []).append(i)
nb = [sorted(set(j for c in groups[int(wid[i])] for j in adj[c])) for i in range(nv)]

report = []
for side in ("l", "r"):
    sh, cl = gi[f"{side}Shldr"], gi[f"{side}Collar"]
    A, B = P[f"{side}Collar"], P[f"{side}Shldr"]; ax = B - A; L = np.linalg.norm(ax); u = ax/L
    s = ((co - A) @ u)/L
    foot = A + np.outer(np.clip(s, 0, 1.2)*L, u); r = np.linalg.norm(co - foot, axis=1)
    f = (1.0 - sstep(RAD, RAD + FALL, r)) * sstep(B[2] - BELOW - FALLZ, B[2] - BELOW, co[:, 2]) * (s > -0.3)
    keep = sstep(S0, S1, s)
    moved = W[:, sh]*f*(1.0 - keep)
    W[:, sh] -= moved; W[:, cl] += moved
    act = np.where(f > 1e-3)[0]
    for _ in range(ITERS):
        Wn = W[:, [sh, cl]].copy()
        for i in act:
            if nb[i]:
                m = 0.5*W[i, [sh, cl]] + 0.5*W[nb[i]][:, [sh, cl]].mean(0); tot = W[i, sh] + W[i, cl]; ms = m.sum()
                Wn[i] = m*(tot/ms) if ms > 1e-9 else W[i, [sh, cl]]
        W[:, [sh, cl]] = Wn
    chest_top = (s > 0.2) & (s < 0.7) & (f > 0.5)
    report.append(f"{side}: {int((f > 1e-3).sum())} verts in the field; Shldr on the chest top (s 0.2-0.7) "
                  f"{W0[chest_top, sh].mean():.2f} -> {W[chest_top, sh].mean():.2f}, Collar {W0[chest_top, cl].mean():.2f} -> {W[chest_top, cl].mean():.2f}")

ch = np.where(np.abs(W - W0).max(1) > 1e-6)[0]
for i in ch:
    ii = int(i)
    for g in range(W.shape[1]):
        if W[i, g] > 1e-6: mesh.vertex_groups[g].add([ii], float(W[i, g]), 'REPLACE')
        elif W0[i, g] > 0: mesh.vertex_groups[g].remove([ii])
print(f"SHOULDER_FIELD s0={S0} s1={S1} rad={RAD} fall={FALL} below={BELOW} fallz={FALLZ} iters={ITERS}; " + " | ".join(report), flush=True)

bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True); arm.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format='GLB',
                          export_yup=True, export_skins=True, export_normals=True,
                          export_materials='EXPORT', export_texcoords=True, export_image_format='AUTO')
print(f"EXPORTED {OUT}", flush=True)
