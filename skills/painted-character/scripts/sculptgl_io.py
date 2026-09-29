"""sculptgl_io.py - read any sculpt mesh (SculptGL PLY, other PLY, STL, OBJ, GLB) and write the PLY flavour SculptGL
opens: binary LE, x y z float + red green blue uchar, triangles as `list uchar uint`.

SculptGL's own PLY export appends a SECOND copy of the face block after the first; trimesh then fails with "PLY is
unexpected length" - read_mesh parses those itself and reads only the first nf faces."""
import re
import numpy as np, trimesh

def _read_sculptgl_ply(raw, end, hdr):
    nv = int(re.search(r"element vertex (\d+)", hdr).group(1)); nf = int(re.search(r"element face (\d+)", hdr).group(1))
    vb = np.frombuffer(raw[end:end + nv*15], np.uint8).reshape(nv, 15)
    pos = vb[:, :12].copy().view("<f4").reshape(nv, 3); col = vb[:, 12:15].copy()
    fb = np.frombuffer(raw[end + nv*15:end + nv*15 + nf*13], np.uint8).reshape(nf, 13)
    tri = fb[:, 1:].copy().view("<u4").reshape(nf, 3)
    return trimesh.Trimesh(pos, tri, vertex_colors=np.c_[col, np.full(nv, 255, np.uint8)], process=False)

def read_mesh(path):
    path = str(path)
    if path.lower().endswith(".ply"):
        raw = open(path, "rb").read(); end = raw.find(b"end_header\n") + 11; hdr = raw[:end].decode(errors="ignore")
        props = re.findall(r"property (\w+) (\w+)", hdr.split("element face")[0])
        if "binary_little_endian" in hdr and [p for _, p in props] == ["x", "y", "z", "red", "green", "blue"] \
                and "list uchar uint" in hdr:
            return _read_sculptgl_ply(raw, end, hdr)
    m = trimesh.load(path, force="mesh")
    return m

def write_sculptgl(path, verts, faces, rgb, comment="written by sculptgl_io.py"):
    verts = np.ascontiguousarray(verts, "<f4"); faces = np.ascontiguousarray(faces, "<u4"); rgb = np.asarray(rgb, np.uint8)[:, :3]
    nv, nf = len(verts), len(faces)
    hdr = (f"ply\nformat binary_little_endian 1.0\ncomment {comment}\nelement vertex {nv}\nproperty float x\nproperty float y\n"
           f"property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face {nf}\n"
           "property list uchar uint vertex_indices\nend_header\n").encode()
    vb = np.zeros((nv, 15), np.uint8); vb[:, :12] = verts.view(np.uint8).reshape(nv, 12); vb[:, 12:15] = rgb
    fb = np.zeros((nf, 13), np.uint8); fb[:, 0] = 3; fb[:, 1:] = faces.view(np.uint8).reshape(nf, 12)
    open(path, "wb").write(hdr + vb.tobytes() + fb.tobytes())
