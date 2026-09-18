"""守着工具对 SDK 的**唯一两处私有耦合** —— 它们失效必须"测试先红"。

工具之所以要碰 SDK 私有面，只有两个理由（都写在模块 docstring 里）：

1. `Arm._a._on_status` —— 把运动期间的 100Hz 状态也推给曲线。不挂这个钩子，
   `movej` 那种阻塞调用期间曲线会冻住，而那正是最该看波形的时刻。
2. `Arm._write_cmd(..., guarded=False)` —— 急停的**插队**写：只写不读，
   因而不会被在途的长命令占住的所有者线程挡住。

SDK 若重命名/移走这两处，本文件必须先失败 —— 否则工具会**静默降级**成
"连上了但曲线不动"、"急停排队等到超时"，两种都比启动即报错难查得多。
"""
import inspect

import pytest

import litearm_core as pa
from litearm_core.arm import Arm, _Ack


def test_ack_still_has_on_status_hook_seam():
    assert callable(getattr(_Ack, "_on_status", None)), (
        "litearm_core 的 _Ack._on_status 不见了 —— "
        "请更新 litetool/sdk_worker.py::_attach_state_hook")


def test_arm_connect_still_publishes_ack_as_underscore_a():
    """钩子要从 `arm._a` 上取；这个属性名是 connect() 里定死的。"""
    src = inspect.getsource(Arm.connect)
    assert "_a = _Ack(" in src, (
        "Arm.connect() 不再把 _Ack 存到 self._a —— "
        "请更新 litetool/sdk_worker.py::_attach_state_hook")


def test_ack_decoded_state_is_published_as_dot_state():
    """钩子读的是 `ack.state`（解码后的 RobotState）。"""
    src = inspect.getsource(_Ack)
    assert "self.state = " in src


def test_write_cmd_keeps_guarded_kwarg():
    """急停旁路依赖 `guarded=False` 语义：「降能量方向的安全动作永远可达」。"""
    params = inspect.signature(Arm._write_cmd).parameters
    assert "guarded" in params, (
        "Arm._write_cmd 不再接受 guarded —— "
        "请更新 litetool/sdk_worker.py::SdkWorker.emergency_now")


def test_write_cmd_does_not_read():
    """紧急旁路的正确性前提：`_write_cmd` 只写不读（否则会与所有者线程抢帧）。"""
    src = inspect.getsource(Arm._write_cmd)
    for forbidden in ("read_frame", "expect(", "pump("):
        assert forbidden not in src, f"_write_cmd 里出现了 {forbidden}"


def test_emergency_command_constant_present():
    assert pa._protocol.CMD_EMERGENCY_STOP == 0x12


@pytest.mark.parametrize("name", [
    # SDK 的公开面 —— 工具逐条都有 UI 入口，见 README 的覆盖表
    "connect", "close", "enable", "disable", "emergency_stop", "reset",
    "clear_faults", "set_motion_mode", "park", "zero_g", "zero_g_start",
    "zero_g_stop", "last_reset_reason", "set_speed", "movej", "move_p",
    "get_tcp", "ik", "home", "move_js", "send_mit", "send_mit_all",
    "get_state", "get_status_now", "set_ff_mask", "ff_preset", "set_ff_vec",
    "set_ff_scalar", "get_ff_vec", "get_ff_scalar", "get_ff_mask",
    "set_gravity_scale", "set_inertia_scale", "set_payload",
    "set_gravity_vector", "save_params",
])
def test_public_api_surface_intact(name):
    """工具覆盖的就是这张表；SDK 删/改名会让 UI 出现死按钮，这里拦住。"""
    assert hasattr(Arm, name), f"Arm.{name} 不见了"


@pytest.mark.parametrize("name", ["set_joint_param", "set_joint_limits",
                                  "get_joint_param", "all_joint_params",
                                  "reset_factory"])
def test_joint_params_api_intact(name):
    from litearm_core.params import JointParams
    assert hasattr(JointParams, name)


@pytest.mark.parametrize("name", ["start", "stop", "reader", "capture", "dump"])
def test_log_api_intact(name):
    from litearm_core.log import ArmLog
    assert hasattr(ArmLog, name)


def test_diag_api_intact():
    from litearm_core.diagnostics import Diagnostics
    assert hasattr(Diagnostics, "kin_bench")


# ---------------------------------------------------------------- 参数编号契约
def test_joint_vec_item_numbers_match_sdk():
    """工具参数目录里的 0x26 item 编号必须与 SDK 的 `FF_VEC_ITEMS` 逐条对齐。

    ⚠ 这是**最危险**的一类漂移：编号错了不会报错，只会把 kp 写到摩擦槽、
    把 gs 写到 ki 槽 —— 现象是"臂变得怪怪的"，几乎查不出来。
    """
    from litetool import param_catalog as C
    bad = []
    for p in C.JOINT_PARAMS:
        if p.kind != "vec":
            continue
        sdk = Arm.FF_VEC_ITEMS.get(p.item)
        if sdk != p.key:
            bad.append(f"item {p.item}: 工具={p.key!r} SDK={sdk!r}")
    assert not bad, "逐关节向量编号与 SDK 不一致:\n  " + "\n  ".join(bad)


def test_global_scalar_item_numbers_match_sdk():
    from litetool import param_catalog as C
    bad = []
    for gp in C.GLOBAL_PARAMS:
        sdk = (Arm.FF_SCALAR_ITEMS.get(gp.item)
               or Arm.FF_SCALAR_RO_ITEMS.get(gp.item))
        if sdk != gp.key:
            bad.append(f"item {gp.item}: 工具={gp.key!r} SDK={sdk!r}")
    assert not bad, "全局标量编号与 SDK 不一致:\n  " + "\n  ".join(bad)


def test_ff_mask_readback_item_matches_sdk():
    """ff_mask 走只读扩展项（0x2C item 9），两边编号必须一致。"""
    from litetool import param_catalog as C
    assert C.FF_MASK_SCALAR_ITEM in Arm.FF_SCALAR_RO_ITEMS
    assert Arm.FF_SCALAR_RO_ITEMS[C.FF_MASK_SCALAR_ITEM] == "ff_mask"


def test_ff_mask_bits_match_sdk():
    """ff_mask 位定义：工具侧复选框组与 SDK 常量必须一致。"""
    from litetool import param_catalog as C
    pairs = [("FF_MASTER", "FF_MASTER"), ("FF_G", "FF_G"),
             ("FF_INERTIA", "FF_INERTIA"), ("FF_CORIOLIS", "FF_CORIOLIS"),
             ("FF_FRICTION", "FF_FRICTION"), ("FF_INTEGRAL", "FF_INTEGRAL"),
             ("FF_WALL", "FF_WALL"), ("FF_QUANT", "FF_QUANT"),
             ("FF_VELREF", "FF_VELREF")]
    for tool_name, sdk_name in pairs:
        assert getattr(C, tool_name) == getattr(pa._protocol, sdk_name), tool_name
    assert C.FF_ALL_MASK == pa._protocol.FF_ALL


def test_ff_vec_length_matches_sdk():
    """0x26 向量恒 7 值（固件侧槽位固定），工具侧常量不能漂。"""
    from litetool import param_catalog as C
    assert C.FF_VEC_LEN == pa._protocol.KIN_N
