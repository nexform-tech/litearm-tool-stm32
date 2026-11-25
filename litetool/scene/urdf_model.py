"""只读 3D 数字孪生：URDF 解析、STL 载入、正运动学。

这一层**不依赖 Qt / OpenGL**，可以在无显示环境里单测。渲染在
`litetool.scene.view` 里，页面在 `litetool.gui.pages.scene_page` 里。

模型资产随包放在 `assets/description/`（decimated 版，约 6.2 MB），
不引 Node/pnpm；来源见该目录的 README。
"""
from __future__ import annotations

import math
import os
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

URDF_NAME = "litearm_description.urdf"
MESH_DIR = "meshes"
URDF_DIR = "urdf"


def rpy_matrix(rpy: Sequence[float]) -> np.ndarray:
    """URDF 固定轴 rpy → 3×3 旋转 (R = Rz(yaw) @ Ry(pitch) @ Rx(roll))。"""
    r, p, y = (float(v) for v in rpy)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=float)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=float)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=float)
    return rz @ ry @ rx


def axis_angle(axis: Sequence[float], angle: float) -> np.ndarray:
    """Rodrigues：绕单位轴旋转 angle 的 3×3 矩阵。"""
    x, y, z = (float(v) for v in axis)
    n = math.sqrt(x * x + y * y + z * z)
    if n == 0.0:
        return np.eye(3)
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    return np.array([
        [x * x * C + c, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, y * y * C + c, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, z * z * C + c],
    ], dtype=float)


def transform(rot: Optional[np.ndarray] = None,
              pos: Sequence[float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    m = np.eye(4)
    if rot is not None:
        m[:3, :3] = rot
    m[:3, 3] = [float(v) for v in pos]
    return m


def _floats(text: Optional[str], default: str = "0 0 0") -> Tuple[float, ...]:
    return tuple(float(v) for v in (text or default).split())


def _origin(el: Optional[ET.Element]) -> np.ndarray:
    if el is None:
        return np.eye(4)
    xyz = _floats(el.get("xyz"), "0 0 0")
    rpy = _floats(el.get("rpy"), "0 0 0")
    return transform(rpy_matrix(rpy), xyz)


@dataclass(frozen=True)
class Link:
    name: str
    mesh_path: str
    visual: np.ndarray          # 4×4, link frame → visual frame
    rgba: Tuple[float, float, float, float]


@dataclass(frozen=True)
class Joint:
    name: str
    kind: str                   # revolute / continuous / fixed
    parent: str
    child: str
    origin: np.ndarray          # 4×4, parent link frame → joint frame
    axis: np.ndarray            # unit-ish 3-vector in joint frame
    index: Optional[int]        # q 下标；fixed 为 None


def load_stl(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """读 binary STL，返回 (N×3 float32 顶点, N/3×3 uint32 面)。

    本仓库随包的网格是 studio 的 decimated STL（binary）。ASCII STL 直接报错，
    避免静默读出一个空模型。
    """
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 84:
        raise ValueError(f"{path}: 文件太短，不是 binary STL")
    n = struct.unpack("<I", data[80:84])[0]
    expected = 84 + n * 50
    if len(data) != expected:
        raise ValueError(
            f"{path}: 不是 binary STL (len={len(data)}, n={n}, expected={expected})")
    raw = np.frombuffer(data, dtype=np.uint8, count=n * 50, offset=84).reshape(n, 50)
    verts = np.frombuffer(raw[:, 12:48].tobytes(), dtype="<f4").reshape(-1, 3)
    faces = np.arange(len(verts), dtype=np.uint32).reshape(-1, 3)
    return np.ascontiguousarray(verts, dtype=np.float32), faces


class UrdfModel:
    """一台臂的 URDF 模型；`fk(q)` 给出 link → 世界系的 4×4 变换。"""

    def __init__(self, links: Dict[str, Link], joints: List[Joint], root: str):
        self.links = links
        self.joints = joints
        self.root = root
        self.children: Dict[str, List[Joint]] = {}
        revolute = [j for j in joints if j.index is not None]
        for j in joints:
            self.children.setdefault(j.parent, []).append(j)
        self.n_joints = len(revolute)
        #: 优先 ee_link，否则取最后一个叶子 link（没有子关节的 link）。
        parent_links = {j.parent for j in joints}
        leaves = [name for name in links if name not in parent_links]
        self.tool_link = "ee_link" if "ee_link" in leaves else (leaves[-1] if leaves else root)
        self._meshes: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self._render_meshes: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    # ------------------------------------------------------------------ 载入
    @classmethod
    def load(cls, urdf_path: str | os.PathLike, mesh_dir: Optional[str | os.PathLike] = None) -> "UrdfModel":
        root_el = ET.parse(str(urdf_path)).getroot()
        base = Path(mesh_dir) if mesh_dir is not None else Path(urdf_path).parent.parent / MESH_DIR
        links: Dict[str, Link] = {}
        for link_el in root_el.findall("link"):
            name = link_el.get("name")
            vis = link_el.find("visual")
            mesh_el = vis.find("geometry/mesh") if vis is not None else None
            if not name or mesh_el is None:
                continue
            filename = mesh_el.get("filename") or ""
            mesh_path = str(base / os.path.basename(filename))
            color_el = vis.find("material/color")
            rgba = _floats(color_el.get("rgba"), "0.75 0.75 0.75 1") if color_el is not None \
                else (0.75, 0.75, 0.75, 1.0)
            links[name] = Link(name=name, mesh_path=mesh_path,
                               visual=_origin(vis.find("origin")),
                               rgba=tuple(float(v) for v in rgba[:4]))
        joints: List[Joint] = []
        q_index = 0
        for j_el in root_el.findall("joint"):
            parent_el = j_el.find("parent")
            child_el = j_el.find("child")
            if parent_el is None or child_el is None:
                continue
            kind = j_el.get("type") or "fixed"
            axis_el = j_el.find("axis")
            axis = np.array(_floats(axis_el.get("xyz") if axis_el is not None else None,
                                    "0 0 1"), dtype=float)
            index = None
            if kind in ("revolute", "continuous"):
                index = q_index
                q_index += 1
            joints.append(Joint(
                name=j_el.get("name") or f"joint{q_index}",
                kind=kind,
                parent=parent_el.get("link") or "",
                child=child_el.get("link") or "",
                origin=_origin(j_el.find("origin")),
                axis=axis,
                index=index,
            ))
        child_set = {j.child for j in joints}
        roots = [name for name in links if name not in child_set]
        if not roots:
            raise ValueError(f"{urdf_path}: 找不到根 link")
        return cls(links, joints, roots[0])

    # ------------------------------------------------------------------ 网格
    def mesh(self, link_name: str) -> Tuple[np.ndarray, np.ndarray]:
        if link_name not in self._meshes:
            link = self.links[link_name]
            self._meshes[link_name] = load_stl(link.mesh_path)
        return self._meshes[link_name]

    def render_mesh(self, link_name: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """返回 (索引化顶点, 面索引, 顶点法线) —— 给渲染层用。

        pyqtgraph 的 `MeshData.vertexNormals()` 是**逐顶点 Python 循环**，本模型
        129k 三角形要 ~1.7 s，正是“3D 页打开慢”的主因。这里用 numpy 一次性
        焊接重合顶点、按面积加权累加面法线，再映射回索引化网格；实测从秒级
        降到几十毫秒，同时顶点缓冲从 387k 降到约 60k。
        """
        cached = self._render_meshes.get(link_name)
        if cached is not None:
            return cached
        verts, faces = self.mesh(link_name)
        # 焊接完全重合的顶点（STL 每个三角形独立存三个顶点，重复率很高）。
        # ⚠ 不能直接用 np.unique(verts, axis=0)：对 75k×3 的 float 数组要 ~150 ms；
        # 按 12 字节 void 视图做一维 unique 只要 ~45 ms，结果完全一致。
        v = np.ascontiguousarray(verts, dtype=np.float32)
        void = v.view(np.dtype((np.void, v.dtype.itemsize * 3))).ravel()
        _, first, inverse = np.unique(void, return_index=True, return_inverse=True)
        uniq = v[first]
        idx = inverse.reshape(-1, 3).astype(np.uint32)
        v0, v1, v2 = uniq[idx[:, 0]], uniq[idx[:, 1]], uniq[idx[:, 2]]
        fn = np.cross(v1 - v0, v2 - v0)          # 长度 = 2×面积，天然面积加权
        normals = np.zeros((len(uniq), 3), dtype=np.float64)
        for k in range(3):
            for c in range(3):
                normals[:, c] += np.bincount(
                    idx[:, k], weights=fn[:, c], minlength=len(uniq))
        ln = np.linalg.norm(normals, axis=1)
        bad = ln < 1e-12
        normals[~bad] /= ln[~bad, None]
        normals[bad] = (0.0, 0.0, 1.0)
        out = (np.ascontiguousarray(uniq, dtype=np.float32),
               np.ascontiguousarray(idx, dtype=np.uint32),
               np.ascontiguousarray(normals, dtype=np.float32))
        self._render_meshes[link_name] = out
        return out

    def mesh_stats(self) -> Tuple[int, int]:
        triangles = 0
        vertices = 0
        for name in self.links:
            verts, faces = self.mesh(name)
            triangles += len(faces)
            vertices += len(verts)
        return triangles, vertices

    # ------------------------------------------------------------------ FK
    def fk(self, q: Sequence[float]) -> Dict[str, np.ndarray]:
        qv = np.asarray(q, dtype=float).reshape(-1)
        if len(qv) != self.n_joints:
            raise ValueError(f"需要 {self.n_joints} 个关节角 (给的是 {len(qv)})")
        world: Dict[str, np.ndarray] = {}
        stack: List[Tuple[str, np.ndarray]] = [(self.root, np.eye(4))]
        while stack:
            name, parent_T = stack.pop()
            link = self.links[name]
            T_link = parent_T @ link.visual
            world[name] = T_link
            for j in self.children.get(name, []):
                Tj = parent_T @ j.origin
                if j.index is not None:
                    Tj = Tj @ transform(axis_angle(j.axis, qv[j.index]))
                stack.append((j.child, Tj))
        return world

    def bounds(self, q: Optional[Sequence[float]] = None,
               max_points: int = 400) -> Tuple[np.ndarray, np.ndarray]:
        """粗略包围盒（每 link 抽样最多 max_points 个顶点），用于相机取景。"""
        qv = np.zeros(self.n_joints) if q is None else np.asarray(q, dtype=float)
        world = self.fk(qv)
        pts: List[np.ndarray] = []
        for name, link in self.links.items():
            if name not in world:
                continue
            verts, _ = self.mesh(name)
            if len(verts) > max_points:
                step = max(1, len(verts) // max_points)
                verts = verts[::step]
            m = world[name]
            pts.append(verts @ m[:3, :3].T + m[:3, 3])
        if not pts:
            raise ValueError("模型没有可渲染的网格")
        allp = np.vstack(pts)
        return allp.min(axis=0), allp.max(axis=0)


def description_dir() -> Optional[Path]:
    """找随包的 `assets/description/`。

    顺序：`$LITEARM_TOOL_DESCRIPTION` → 冻结包的 `_internal/assets/description`
    / 可执行文件同级 → 源码树仓库根。找不到返回 None（页面显示空状态）。
    """
    env = os.environ.get("LITEARM_TOOL_DESCRIPTION")
    cands: List[Path] = []
    if env:
        cands.append(Path(env))
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cands.append(Path(meipass) / "assets" / "description")
        cands.append(Path(sys.executable).resolve().parent / "assets" / "description")
    cands.append(Path(__file__).resolve().parents[2] / "assets" / "description")
    for p in cands:
        if (p / URDF_DIR / URDF_NAME).is_file():
            return p
    return None


def load_default_model() -> Optional[UrdfModel]:
    d = description_dir()
    if d is None:
        return None
    return UrdfModel.load(d / URDF_DIR / URDF_NAME, d / MESH_DIR)
