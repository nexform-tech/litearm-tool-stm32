"""checks.py 测试 —— Δq 意图层确认逻辑（无硬件）。"""
import pytest

from litetool import checks


def test_within_threshold_no_confirm():
    plan = checks.plan_motion([0.1, 0.2, 0.3], [0.15, 0.25, 0.33], threshold=0.5)
    assert plan.deltas == pytest.approx([0.05, 0.05, 0.03])
    assert plan.exceeds == []
    assert plan.needs_confirm is False


def test_single_joint_over_threshold():
    plan = checks.plan_motion([0.0, 0.0, 0.0], [0.0, 1.4, 0.0], threshold=0.5)
    assert plan.exceeds == [2]          # 1-based 关节号
    assert plan.needs_confirm is True


def test_multiple_exceeding_sorted():
    plan = checks.plan_motion([0.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.1, 2.0], threshold=0.5)
    assert plan.exceeds == [2, 4]


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        checks.plan_motion([0.0, 0.0], [0.0], threshold=0.5)


def test_empty_lists_no_confirm():
    plan = checks.plan_motion([], [], threshold=0.5)
    assert plan.deltas == [] and plan.exceeds == [] and plan.needs_confirm is False


def test_confirm_lines_only_show_exceeding_with_format():
    cur = [0.0, 0.12, 0.0]
    tgt = [0.0, 1.4, 0.0]
    plan = checks.plan_motion(cur, tgt, threshold=0.5)
    lines = checks.confirm_lines(plan)
    assert len(lines) == 1
    assert lines[0] == "J2: 当前 0.120 → 目标 1.400（Δ 1.280 rad）"


def test_confirm_lines_custom_labels():
    plan = checks.plan_motion([0.0], [1.0], threshold=0.5)
    lines = checks.confirm_lines(plan, labels=["J0"])
    assert lines[0].startswith("J0:")


# ---------------------------------------------------------------- 笛卡尔幅度
def test_plan_pose_within_thresholds():
    cur = [0.30, 0.0, 0.35, 3.1416, 0.0, 0.0]
    tgt = [0.31, 0.0, 0.36, 3.1416, 0.0, 0.0]
    p = checks.plan_pose(cur, tgt, pos_threshold=0.05, rot_threshold=0.30)
    assert not p.needs_confirm
    assert p.dpos == pytest.approx(0.014142, rel=1e-3)
    assert p.drot == pytest.approx(0.0, abs=1e-6)


def test_plan_pose_position_over_threshold():
    p = checks.plan_pose([0.30, 0.0, 0.35, 0, 0, 0], [0.60, 0.0, 0.35, 0, 0, 0])
    assert p.needs_confirm and p.dpos == pytest.approx(0.30)
    assert "位置移动" in p.summary()


def test_plan_pose_rotation_over_threshold():
    p = checks.plan_pose([0.3, 0, 0.35, 0.0, 0.0, 0.0], [0.3, 0, 0.35, 1.0, 0.0, 0.0])
    assert p.needs_confirm and p.drot == pytest.approx(1.0, rel=1e-6)


def test_plan_pose_without_current_tcp_still_requires_confirm():
    """拿不到当前 TCP 时**也要确认**。

    原先这里放行，结果是连上后第一个 movep（输入框还是默认值、最容易手滑的时刻）
    完全绕过幅度闸门。无基线不是"免检"，而是"无从判断，请人来看一眼"。
    """
    p = checks.plan_pose(None, [0.9, 0.0, 0.35, 0, 0, 0])
    assert p.needs_confirm
    assert "拿不到" in p.summary()
    assert "+0.9000" in p.summary()          # 把目标值摆出来给人核对


def test_orient_angle_is_zero_for_same_rotation():
    """万向锁 (pitch=±π/2) 下同一个旋转可以有无穷多组 RPY：此处只有 r−y 有意义。

    固件在 |pitch|≈π/2 时**强制 yaw=0**，于是同一个旋转的 rpy 分量能差很远 ——
    逐分量比较会永远判不到位（movep 每次耗满超时），夹角判据不会。
    """
    import math
    a = [0.0, math.pi / 2, 0.0]
    b = [0.3, math.pi / 2, 0.3]          # r−y = 0，与 a 是同一个旋转
    assert checks._orient_angle(a, b) == pytest.approx(0.0, abs=1e-3)
    c = [0.3, math.pi / 2, -0.3]         # r−y = 0.6，是**不同**的旋转
    assert checks._orient_angle(a, c) == pytest.approx(0.6, abs=1e-3)
