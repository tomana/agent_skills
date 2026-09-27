"""Blender side of render.py: imports STLs, colours them by kind, renders each step, projects label anchors to
pixels. Workbench engine (fast, no lights to set up), transparent film so the caller composes onto white.

Run by render.py:  blender -b -P render_assembly.py -- <manifest.json>

manifest = {
  "objects": [{"step": 1, "kind": "part", "file": "/abs/part.stl"}, ...],   # one render per distinct step
  "colors":  {"part": [0.23, 0.49, 0.85], ...},                             # RGB 0..1 per kind
  "camera":  {"target": [x, y, z], "loc": [x, y, z], "lens": 45},           # mm units; optional "ortho": scale
  "labels":  [{"step": 1, "anchor": [x, y, z], "text": "..."}],             # optional, projected to pixels
  "res": [1600, 1200], "outdir": "/abs/dir"
}
Writes <outdir>/step<N>.png and <outdir>/step<N>_labels.json (the labels with a "px" field).
"""
import bpy, json, sys, os
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

MAN = json.load(open(sys.argv[sys.argv.index("--") + 1]))
OUTD = MAN["outdir"]; os.makedirs(OUTD, exist_ok=True)
W, H = MAN["res"]
COL = MAN["colors"]

def imp(path):
    before = set(bpy.data.objects)
    try: bpy.ops.wm.stl_import(filepath=path)            # Blender 4.x / 5.x
    except Exception: bpy.ops.import_mesh.stl(filepath=path)   # older
    return [o for o in bpy.data.objects if o not in before]

for st in sorted({o["step"] for o in MAN["objects"]}):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_shadows = True; sh.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.film_transparent = True
    for o in MAN["objects"]:
        if o["step"] != st: continue
        for ob in imp(o["file"]):
            ob.color = list(COL[o["kind"]]) + [1.0]
    c = MAN["camera"]
    tgt = bpy.data.objects.new("tgt", None); sc.collection.objects.link(tgt); tgt.location = c["target"]
    cd = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam); sc.camera = cam; cam.location = c["loc"]; cd.lens = c.get("lens", 45)
    if c.get("ortho"): cd.type = 'ORTHO'; cd.ortho_scale = c["ortho"]
    cd.clip_start, cd.clip_end = 1.0, 1e5     # STLs are in mm = Blender units; the default clip_end culls them
    con = cam.constraints.new('TRACK_TO'); con.target = tgt
    con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    sc.render.filepath = f"{OUTD}/step{st}.png"
    bpy.ops.render.render(write_still=True)
    px = []
    for L in MAN.get("labels", []):
        if L["step"] != st: continue
        p = world_to_camera_view(sc, cam, Vector(L["anchor"]))
        px.append(dict(L, px=[p.x * W, (1 - p.y) * H]))
    json.dump(px, open(f"{OUTD}/step{st}_labels.json", "w"))
    print("rendered step", st)
