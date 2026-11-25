"""URDF / STL / FK 的离线测试 —— 不需要 Qt、OpenGL 或硬件。"""
from __future__ import annotations

import math
import struct

import numpy as np
import pytest

from litetool.scene.urdf_model import (UrdfModel, axis_angle, description_dir,
                                       load_default_model, load_stl,
                                       rpy_matrix)


def _write_stl(path) -> None:
    normal = (0.0, 0.0, 1.0)
    tri = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    body = struct.pack("<12fH", *normal, *tri[0], *tri[1], *tri[2], 0)
    path.write_bytes(b"x" * 80 + struct.pack("<I", 1) + body)


def _write_urdf(tmp_path):
    meshes = tmp_path / "meshes"
    meshes.mkdir()
    _write_stl(meshes / "base.STL")
    _write_stl(meshes / "arm.STL")
    urdf = tmp_path / "model.urdf"
    urdf.write_text("""
<robot name="t">
  <link name="base">
    <visual><geometry><mesh filename="package://x/meshes/base.STL"/></geometry></visual>
  </link>
  <link name="arm">
    <visual>
      <origin xyz="1 0 0" rpy="0 0 0"/>
      <geometry><mesh filename="package://x/meshes/arm.STL"/></geometry>
    </visual>
  </link>
  <joint name="j1" type="revolute">
    <parent link="base"/><child link="arm"/>
    <origin xyz="0 0 1" rpy="0 0 0"/><axis xyz="0 0 1"/>
  </joint>
</robot>
""", encoding="utf-8")
    return urdf, meshes


def test_load_stl_binary(tmp_path):
    p = tmp_path / "a.STL"
    _write_stl(p)
    verts, faces = load_stl(str(p))
    assert verts.shape == (3, 3)
    assert faces.shape == (1, 3)
    assert verts.dtype == np.float32


def test_load_stl_rejects_ascii(tmp_path):
    p = tmp_path / "a.STL"
    p.write_text("solid x\nendsolid x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_stl(str(p))


def test_urdf_fk_rotates_visual_origin(tmp_path):
    urdf, meshes = _write_urdf(tmp_path)
    m = UrdfModel.load(urdf, meshes)
    assert m.n_joints == 1
    assert m.tool_link == "arm"

    w0 = m.fk([0.0])
    assert np.allclose(w0["arm"][:3, 3], [1.0, 0.0, 1.0])

    w90 = m.fk([math.pi / 2])
    assert np.allclose(w90["arm"][:3, 3], [0.0, 1.0, 1.0], atol=1e-9)


def test_urdf_rejects_wrong_q_length(tmp_path):
    urdf, meshes = _write_urdf(tmp_path)
    m = UrdfModel.load(urdf, meshes)
    with pytest.raises(ValueError):
        m.fk([])


def test_rpy_and_axis_angle_are_orthonormal():
    for rpy in ((0.3, -0.2, 1.1), (0.0, 0.0, 0.0)):
        r = rpy_matrix(rpy)
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-12)
        assert np.linalg.det(r) == pytest.approx(1.0)
    r = axis_angle((0, 0, 1), math.pi / 2)
    assert np.allclose(r[:3, :3], [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-12)


def test_vendored_description_loads_and_has_expected_shape():
    d = description_dir()
    assert d is not None, "缺少 assets/description（3D 资产应随包）"
    m = load_default_model()
    assert m is not None
    assert m.n_joints == 7
    assert len(m.links) == 9
    triangles, vertices = m.mesh_stats()
    assert triangles > 100_000
    assert vertices == triangles * 3

    w = m.fk([0.0] * 7)
    assert np.allclose(w["joint1"][:3, 3], [0.0, 0.0, 0.06975], atol=1e-6)
    assert np.allclose(w["base_link"][:3, 3], [0.0, 0.0, 0.0], atol=1e-9)
    lo, hi = m.bounds([0.0] * 7)
    assert np.all(hi > lo)


def test_description_dir_env_override(tmp_path, monkeypatch):
    d = tmp_path / "desc"
    (d / "urdf").mkdir(parents=True)
    (d / "urdf" / "litearm_description.urdf").write_text("<robot/>", encoding="utf-8")
    monkeypatch.setenv("LITEARM_TOOL_DESCRIPTION", str(d))
    assert description_dir() == d


def test_description_dir_frozen_uses_meipass(tmp_path, monkeypatch):
    d = tmp_path / "assets" / "description"
    (d / "urdf").mkdir(parents=True)
    (d / "urdf" / "litearm_description.urdf").write_text("<robot/>", encoding="utf-8")
    monkeypatch.delenv("LITEARM_TOOL_DESCRIPTION", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert description_dir() == d
