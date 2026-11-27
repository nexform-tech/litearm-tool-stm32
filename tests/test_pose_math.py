"""点动位姿数学 —— 基座/工具系、平移/旋转、rpy 往返与万向锁。"""
from __future__ import annotations

import math

import pytest

from litetool.pose_math import (jog_pose, mat3_to_rpy, mat_mul3, rot_axis,
                                rpy_to_mat3)


def _close(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_translate_in_base_frame_uses_world_axes():
    out = jog_pose([0.1, 0.2, 0.3, 0.0, 0.0, 0.0], "X", "translate", 0.01)
    assert out == [0.11, 0.2, 0.3, 0.0, 0.0, 0.0]


def test_translate_in_tool_frame_rotates_the_direction():
    # yaw=90° 时工具 X 指向世界 Y
    pose = [0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]
    out = jog_pose(pose, "X", "translate", 0.01, "tool")
    assert _close(out[0], 0.0) and _close(out[1], 0.01)
    assert out[3:] == pose[3:], "平移不改姿态"


def test_base_rotation_premultiplies():
    pose = [0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]
    out = jog_pose(pose, "X", "rotate", math.pi / 2, "base")
    expected = mat_mul3(rot_axis("X", math.pi / 2),
                        rpy_to_mat3(*pose[3:]))
    got = rpy_to_mat3(*out[3:])
    for i in range(3):
        for j in range(3):
            assert _close(got[i][j], expected[i][j])


def test_tool_rotation_postmultiplies_and_differs_from_base():
    pose = [0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]
    base = jog_pose(pose, "X", "rotate", math.pi / 2, "base")
    tool = jog_pose(pose, "X", "rotate", math.pi / 2, "tool")
    r = rpy_to_mat3(*pose[3:])
    expected_tool = mat_mul3(r, rot_axis("X", math.pi / 2))
    got_tool = rpy_to_mat3(*tool[3:])
    for i in range(3):
        for j in range(3):
            assert _close(got_tool[i][j], expected_tool[i][j])
    assert base[3:] != tool[3:], "两个坐标系的旋转合成顺序不同"


def test_rpy_round_trip():
    for rpy in ((0.1, 0.2, 0.3), (-1.0, 0.4, 2.0), (0.0, -0.7, -2.5)):
        back = mat3_to_rpy(rpy_to_mat3(*rpy))
        for a, b in zip(back, rpy):
            assert _close(a, b, 1e-9)


def test_gimbal_lock_branch_does_not_raise():
    for pitch in (math.pi / 2, -math.pi / 2):
        r = rpy_to_mat3(0.3, pitch, 0.1)
        # 反解结果不唯一；只要矩阵一致即可
        back = rpy_to_mat3(*mat3_to_rpy(r))
        for i in range(3):
            for j in range(3):
                assert _close(back[i][j], r[i][j], 1e-6)


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        jog_pose([0, 0, 0, 0, 0], "X", "translate", 0.01)
    with pytest.raises(ValueError):
        jog_pose([0, 0, 0, 0, 0, 0], "W", "translate", 0.01)
    with pytest.raises(ValueError):
        jog_pose([0, 0, 0, 0, 0, 0], "X", "twist", 0.01)
    with pytest.raises(ValueError):
        jog_pose([0, 0, 0, 0, 0, 0], "X", "translate", 0.01, frame="world")
