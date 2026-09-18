"""参数读写 —— 在 `litearm_core.Arm` 之上的一层薄封装。

为什么需要这一层：参数页要的形状是「逐写口下发，每个写口回一个 `(ok, code)`」，
这样才能把失败**精确标到表格的某一格**；而 SDK 是「失败即抛异常」。

于是这里做形状对齐：捕获 `CommandRejectedError` 取其 `.code`，其余异常（超时/链路）
归为 `code=None`。所有真实 I/O 都在 `pa.Arm` 上发生，本模块不含任何协议字节。

**线程约定**：这里每个函数都直接碰 `Arm`，故**只能在 SDK 所有者线程上调用**
（即作为 `SdkWorker.submit` 的 `fn`）。参数页不再自建后台线程。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import litearm_core as pa
import yaml

from litetool import param_catalog as C

# ERR 码中文映射（固件 `RSP_ERR` payload = [echoed_cmd, code]）
ERR_TEXT = {
    0x00: "固件无此命令（未实现）",
    0x01: "载荷过短（参数校验不通过，未执行）",
    0x02: "数值非法（NaN/超限），固件已拒绝",
    0x03: "未就绪/未使能（反馈未齐可重试；运动命令需先 enable）",
    0x04: "需先 disable（先失磁再做此操作）",
    0x05: "忙（上一条命令/IK 求解仍在执行）",
    0x06: "锁存中，须先 reset 复位（EMERGENCY/单轴故障，重试无效）",
    # [2026-09-14] 模型导入专用: 掩码不符与"数值非法"分开 —— 产线最常见的是前者
    # (漏写一个 body / 写错掩码), 而 0x02 的文案会把人往"数值有问题"的方向带。
    0x07: "掩码不符（本会话漏写或写错了 body）",
}

Result = Tuple[bool, Optional[int]]


def err_text(code: Optional[int]) -> str:
    if code is None:
        return "超时/无应答"
    return ERR_TEXT.get(code, f"code 0x{code:02X}")


def _call(fn: Callable[[], Any]) -> Result:
    """执行一次写口；异常 -> (False, code)。code=None 表示非固件拒绝（超时/链路）。"""
    try:
        fn()
        return True, None
    except pa.CommandRejectedError as e:
        return False, int(getattr(e, "code", 0))
    except Exception:  # noqa: BLE001 - 超时/链路都归 None，页面统一显示"超时/无应答"
        return False, None


# --------------------------------------------------------------------------
# 单写口
# --------------------------------------------------------------------------
def set_joint_param(arm, idx: int, kp: float, kd: float, tau_max: float) -> Result:
    return _call(lambda: arm.params.set_joint_param(idx, kp, kd, tau_max))


def set_joint_limits(arm, idx: int, q_min: float, q_max: float) -> Result:
    return _call(lambda: arm.params.set_joint_limits(idx, q_min, q_max))


def set_ff_vec(arm, item: int, values: List[float]) -> Result:
    return _call(lambda: arm.set_ff_vec(item, values))


def set_ff_scalar(arm, item: int, sub: int, value: float) -> Result:
    return _call(lambda: arm.set_ff_scalar(item, sub, value))


def set_ff_mask(arm, mask: int) -> Result:
    return _call(lambda: arm.set_ff_mask(mask))


def save_params(arm, timeout: float = 6.0) -> Result:
    return _call(lambda: arm.save_params())


def reset_factory(arm) -> Result:
    """恢复出厂默认 + 失效 flash（固件 0x36）。

    ⚠ 固件要求失能态（擦写窗口 CPU 停顿），enable 态回 `ERR{0x36,0x04}`；
    SDK 不代劳 `disable()` —— 代劳等于替调用方做安全决策。
    """
    return _call(lambda: arm.params.reset_factory())


# --------------------------------------------------------------------------
# 读回
# --------------------------------------------------------------------------
def n_readable(arm) -> int:
    """实际能读的关节数 —— `min(表宽, 台架/整臂的 N)`。

    台架 1J 上固件只有 1 个关节，SDK 的 `JointParams._check_idx` 对 `idx≥1` 会抛
    `关节索引越界`。所以**不能**无脑读 `C.NUM_JOINTS` 个：那样整个 [刷新当前] 会挂掉，
    而不是"只读得到 J1"。
    """
    return max(0, min(C.NUM_JOINTS, int(getattr(arm, "n", 0) or 0)))


def _all_joint_keys() -> List[str]:
    return ["kp", "kd", "tau_max", "q_min", "q_max"] + \
        [p.key for p in C.JOINT_PARAMS if p.kind == "vec"]


def read_snapshot(arm) -> Dict[str, Any]:
    """读回全部参数（逐关节 0x24 + 逐向量 0x2B + 逐标量 0x2C + ff_mask）。

    任何一项读不到即抛 `OSError` —— 半截快照比没有更危险（会被当成基线）。
    超出本机关节数的列填 `None`（台架 1J 上 J2..J7 如此），页面按"—"显示且不可下发。
    """
    n = n_readable(arm)
    joints: List[Dict[str, Any]] = [dict.fromkeys(_all_joint_keys())
                                    for _ in range(C.NUM_JOINTS)]
    for j in range(n):
        try:
            jp = arm.params.get_joint_param(j)
        except Exception as e:  # noqa: BLE001
            raise OSError(f"J{j + 1} 读回失败 (get_joint_param): {e}") from e
        joints[j].update(kp=jp.kp, kd=jp.kd, tau_max=jp.tau_max,
                         q_min=jp.q_min, q_max=jp.q_max)
    for p in C.JOINT_PARAMS:
        if p.kind != "vec":
            continue
        try:
            # 向量是模型级（固件恒 7 槽），台架也读得到；只取本机有的那几列
            vals = arm.get_ff_vec(p.item)
        except Exception as e:  # noqa: BLE001
            raise OSError(f"{p.key} 读回失败 (get_ff_vec item {p.item}): {e}") from e
        for j in range(min(len(vals), n)):
            joints[j][p.key] = vals[j]

    glob: Dict[str, Any] = {}
    for gp in C.GLOBAL_PARAMS:
        try:
            if gp.is_array:
                glob[gp.key] = [arm.get_ff_scalar(gp.item, sub) for sub in gp.subs]
            else:
                v = arm.get_ff_scalar(gp.item, gp.subs[0])
                glob[gp.key] = int(round(v)) if gp.model else float(v)
        except Exception as e:  # noqa: BLE001
            raise OSError(f"{gp.key} 读回失败 (get_ff_scalar): {e}") from e
    try:
        glob["ff_mask"] = int(arm.get_ff_mask()) & C.FF_ALL_MASK
    except Exception as e:  # noqa: BLE001
        raise OSError(f"ff_mask 读回失败 (get_ff_mask): {e}") from e
    return {"joints": joints, "global": glob}


# --------------------------------------------------------------------------
# 批量
# --------------------------------------------------------------------------
def run_ops(arm, ops: List[dict]) -> Dict[str, dict]:
    """顺序执行每项 op（`op['run'](arm)` 返回 (ok, code)），逐个记录成败。"""
    okc: Dict[tuple, float] = {}
    failc: Dict[tuple, Optional[int]] = {}
    for op in ops:
        try:
            r = op["run"](arm)
            ok, code = (bool(r[0]), r[1]) if isinstance(r, tuple) else (bool(r), None)
        except Exception:  # noqa: BLE001
            ok, code = False, None
        for (rk, j, val) in op["cells"]:
            if ok:
                okc[(rk, j)] = val
            else:
                failc[(rk, j)] = code
    return {"ok": okc, "fail": failc}


def send_global(arm, g: dict):
    """按 0x28/0x27 顺序下发 global；返回 (g, leaf_ok{key:bool}, model_ok, mask_ok)。"""
    leaf_ok: Dict[str, bool] = {}
    for gp in C.GLOBAL_PARAMS:
        if gp.key == "friction_model":
            continue
        v = g[gp.key]
        if gp.is_array:
            good = all(set_ff_scalar(arm, gp.item, sub, float(v[k]))[0]
                       for k, sub in enumerate(gp.subs))
        else:
            good = set_ff_scalar(arm, gp.item, gp.subs[0], float(v))[0]
        leaf_ok[gp.key] = good
    model_ok = set_ff_scalar(arm, C.GLOBAL_BY_KEY["friction_model"].item, 0,
                             float(g["friction_model"]))[0]
    mask_ok = set_ff_mask(arm, int(g["ff_mask"]))[0]
    return g, leaf_ok, model_ok, mask_ok


def dump_snapshot(snap: dict, path: str, model: dict = None) -> None:
    """写快照到 yaml。

    `[2026-09-14]` `model` 为可选第三段 (动力学模型)。产线存档**必须**带上它 ——
    `read_snapshot()` 保持纯参数 (不并模型, 否则老固件下 [刷新当前] 会整页死掉),
    所以存档若不带模型, SOP 的"断电重上电后重读模型比对"就**没有数据源**。
    """
    doc = {"joints": [{"name": f"J{i + 1}", **jd} for i, jd in enumerate(snap["joints"])],
           "global": {k: (list(v) if isinstance(v, list) else v)
                      for k, v in snap["global"].items()}}
    if model is not None:
        doc["model"] = {"body": [list(b) for b in model.get("body", [])],
                        "jm": list(model.get("jm", []))}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
