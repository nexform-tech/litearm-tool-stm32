"""Generate the low-detail (LOD) mesh set used by the 3D page.

The runtime ships two mesh sets under `assets/description/`:

    meshes/       the decimated preview from litearm-description (~129k triangles)
    meshes_lod/   this script's output (~45k triangles)

Why: the 3D viewport is vertex-bound, not fill-bound (measured: 129k triangles
= 11.6 ms/frame, 29k = 4.5 ms, empty scene = 2.3 ms on llvmpipe at 1200x800),
so halving the triangle count is what makes the page smooth on machines without
a discrete GPU.

Dev-time only. The runtime never imports fast_simplification; it only reads the
STL files this script writes. Regenerate when the upstream model moves:

    /tmp/3dspike-venv/bin/python tools/gen_lod.py            # all links
    /tmp/3dspike-venv/bin/python tools/gen_lod.py --ratio 0.25
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "assets", "description", "meshes")
DST = os.path.join(ROOT, "assets", "description", "meshes_lod")


def read_stl(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack("<I", data[80:84])[0]
    if len(data) != 84 + n * 50:
        raise ValueError(f"{path}: not binary STL")
    arr = np.frombuffer(data, dtype=np.uint8, count=n * 50, offset=84).reshape(n, 50)
    verts = np.frombuffer(arr[:, 12:48].tobytes(), dtype="<f4").reshape(-1, 3)
    faces = np.arange(len(verts), dtype=np.uint32).reshape(-1, 3)
    return verts.astype(np.float32), faces


def write_stl(path, verts, faces):
    tri = verts[faces.reshape(-1)].reshape(-1, 3, 3).astype("<f4")
    n = len(tri)
    # Face normals: the loader ignores the stored normal, but keep them valid.
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(normals, axis=1)
    ln[ln == 0] = 1.0
    normals = (normals / ln[:, None]).astype("<f4")
    body = np.zeros((n, 50), dtype=np.uint8)
    body[:, 0:12] = normals.view(np.uint8).reshape(n, 12)
    body[:, 12:48] = tri.view(np.uint8).reshape(n, 36)
    with open(path, "wb") as f:
        f.write(b"LiteArm Tool LOD (gen_lod.py)".ljust(80, b"\x00"))
        f.write(struct.pack("<I", n))
        f.write(body.tobytes())


def weld(verts, faces):
    """把 STL 的逐三角形独立顶点焊成索引网格。

    ⚠ 不焊就简化会得到**碎裂**的模型：STL 每个三角形各存一份顶点，网格里没有
    共享边，二次误差简化没有可坍缩的边，只会把面拆散。
    """
    v = np.ascontiguousarray(verts, dtype=np.float32)
    void = v.view(np.dtype((np.void, v.dtype.itemsize * 3))).ravel()
    uniq, first, inverse = np.unique(void, return_index=True, return_inverse=True)
    idx = inverse.reshape(-1, 3)
    return v[first], idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=float, default=0.35,
                    help="target fraction of input triangles (default 0.35)")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--dst", default=DST)
    args = ap.parse_args(argv)

    try:
        import fast_simplification
    except ImportError:
        print("fast-simplification is a dev dependency: pip install fast-simplification",
              file=sys.stderr)
        return 2

    os.makedirs(args.dst, exist_ok=True)
    total_in = total_out = 0
    for name in sorted(os.listdir(args.src)):
        if not name.lower().endswith(".stl"):
            continue
        verts, faces = read_stl(os.path.join(args.src, name))
        welded_v, welded_f = weld(verts, faces)
        # `simplify()` takes the fraction to REMOVE, not the target count.
        reduction = 1.0 - min(max(args.ratio, 0.05), 1.0)
        out_v, out_f = fast_simplification.simplify(
            welded_v, welded_f, target_reduction=reduction)
        out_f = np.asarray(out_f, dtype=np.uint32)
        out_v = np.asarray(out_v, dtype=np.float32)
        write_stl(os.path.join(args.dst, name), out_v, out_f)
        total_in += len(faces)
        total_out += len(out_f)
        print(f"{name:16s} {len(faces):6d} -> {len(out_f):6d} triangles")
    print(f"total {total_in} -> {total_out} triangles "
          f"({100.0 * total_out / max(1, total_in):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
