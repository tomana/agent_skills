"""blend_bake_io.py - the Blender half of blend_bake.py (mesh in/out; the baking itself is numpy).

  blender -b -P blend_bake_io.py -- export MESH.ply SESSION.blend MESH.npz
      import the sculpt PLY (y-up, face +z), save the session, write positions / triangles / smooth vertex normals
      (sculpt frame) for the rasterizer and xatlas
  blender -b -P blend_bake_io.py -- build SESSION.blend UVS.npz TEX.png OUT.glb
      put the xatlas UVs (per corner, triangle order) on the mesh, a material with TEX.png as base colour, rotate into
      the glTF convention (z-up in Blender, face -y - as body_texture_apply.py does) and export OUT.glb
"""
import bpy, sys, os, math
import numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
mode = a[0]
if mode == "export":
    PLY, BLEND, NPZ = a[1], a[2], a[3]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.ply_import(filepath=PLY)
    o = max((x for x in bpy.data.objects if x.type == "MESH"), key=lambda m: len(m.data.vertices))
    me = o.data
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris(); bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth()
    n = len(me.vertices)
    pos = np.empty(n*3, np.float32); me.vertices.foreach_get("co", pos)
    nrm = np.array([tuple(v.normal) for v in me.vertices], np.float32)
    tri = np.empty(len(me.polygons)*3, np.int32); me.polygons.foreach_get("vertices", tri)
    np.savez(NPZ, positions=pos.reshape(-1, 3), normals=nrm, triangles=tri.reshape(-1, 3))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(BLEND))
    print(f"export: {n} verts {len(me.polygons)} tris -> {NPZ}")
elif mode == "build":
    BLEND, NPZ, TEX, OUT = a[1], a[2], a[3], a[4]
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    o = max((x for x in bpy.data.objects if x.type == "MESH"), key=lambda m: len(m.data.vertices))
    me = o.data
    for l in list(me.uv_layers): me.uv_layers.remove(l)
    uv = me.uv_layers.new(name="UVMap")
    lu = np.load(NPZ)["loop_uvs"].reshape(-1, 2)
    assert len(lu) == len(me.loops), (len(lu), len(me.loops))
    uv.data.foreach_set("uv", lu.ravel())
    for attr in [x.name for x in me.color_attributes]: me.color_attributes.remove(me.color_attributes[attr])
    img = bpy.data.images.load(os.path.abspath(TEX))
    mat = bpy.data.materials.new("skin"); mat.use_nodes = True
    nt = mat.node_tree; bsdf = next(nn for nn in nt.nodes if nn.type == "BSDF_PRINCIPLED")
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = img
    nt.links.new(bsdf.inputs["Base Color"], t.outputs["Color"]); bsdf.inputs["Roughness"].default_value = 0.8
    me.materials.clear(); me.materials.append(mat)
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    o.rotation_euler = (math.pi/2, 0, 0); bpy.ops.object.transform_apply(rotation=True)
    bpy.ops.object.shade_smooth()
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(OUT), use_selection=True, export_format="GLB")
    print(f"build: {OUT} ({len(me.polygons)} tris, texture {img.size[0]}x{img.size[1]})")
