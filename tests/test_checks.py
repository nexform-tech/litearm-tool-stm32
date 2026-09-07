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
