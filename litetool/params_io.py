"""参数读写 —— 在 `litearm.Arm` 之上的一层薄封装。

为什么需要这一层：参数页要的形状是「逐写口下发，每个写口回一个 `(ok, code)`」，
这样才能把失败**精确标到表格的某一格**；而 SDK 是「失败即抛异常」。

于是这里做形状对齐：捕获 `CommandRejectedError` 取其 `.code`，其余异常（超时/链路）
归为 `code=None`。所有真实 I/O 都在 `pa.Arm` 上发生，本模块不含任何协议字节。

**线程约定**：这里每个函数都直接碰 `Arm`，故**只能在 SDK 所有者线程上调用**
（即作为 `SdkWorker.submit` 的 `fn`）。参数页不再自建后台线程。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import litearm as pa
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


#: 探测上界 —— 固件当前 vec 1..15 / scalar 1..18。留余量, 固件扩容后不必同步改这里。
#: 不支持的 item 固件**立即**回 ERR{cmd,0x02} (不是静默丢弃), 所以多探几项只是一串
#: 快往返, 不会按超时计。
PROBE_MAX_ITEM = 32


def _is_unsupported(e: BaseException) -> bool:
    """固件回 `ERR{cmd,code}` 里表示"没有这个 item"的两档。

    0x00 = 无此命令 (老固件根本没实现 0x2B/0x2C);
    0x02 = 数值/参数非法 (本固件对越界 item 的答复)。
    其余 (`None` = 超时/链路) 是**真故障**, 必须上报, 不能当成"不支持"静默隐藏。
    """
    return int(getattr(e, "code", -1)) in (0x00, 0x02)


def _probe_vec(arm) -> Dict[int, List[float]]:
    """逐个 item 试读 0x2B, 返回 {item: 7 值} (只含固件支持的项)。

    先用已知基础项 item 1 做**闸门**: 它在任何实现 0x2B 的固件上都存在。若它都失败
    (ERR 0x00 或不回应), 直接判"固件不支持参数读回" —— 否则老固件上 32 次超时会把
    一次 [刷新当前] 拖成半分钟。
    """
    try:
        first = arm.get_ff_vec(1, timeout=0.5).value
    except pa.CommandRejectedError as e:
        if _is_unsupported(e):
            raise OSError("固件不支持参数读回 (0x2B) —— 需更新固件") from e
        raise OSError(f"get_ff_vec item 1 读回被拒: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise OSError(f"参数读回无应答 (get_ff_vec item 1): {e}") from e
    out: Dict[int, List[float]] = {1: list(first)}
    for item in range(2, PROBE_MAX_ITEM + 1):
        try:
            out[item] = list(arm.get_ff_vec(item, timeout=0.5).value)
        except pa.CommandRejectedError as e:
            if _is_unsupported(e):
                continue
            raise OSError(f"get_ff_vec item {item} 读回被拒: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise OSError(f"get_ff_vec item {item} 读回失败: {e}") from e
    return out


def _probe_scalar(arm) -> Dict[int, float]:
    """逐个 item 试读 0x2C (sub=0), 返回 {item: 值} (只含固件支持的项)。

    item 9 是 ff_mask 的只读扩展, 由 `get_ff_mask` 单独读, 这里跳过。
    """
    try:
        first = arm.get_ff_scalar(1, 0, timeout=0.5).value
    except pa.CommandRejectedError as e:
        if _is_unsupported(e):
            raise OSError("固件不支持参数读回 (0x2C) —— 需更新固件") from e
        raise OSError(f"get_ff_scalar item 1 读回被拒: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise OSError(f"参数读回无应答 (get_ff_scalar item 1): {e}") from e
    out: Dict[int, float] = {1: float(first)}
    for item in range(2, PROBE_MAX_ITEM + 1):
        if item == C.FF_MASK_SCALAR_ITEM:
            continue
        try:
            out[item] = float(arm.get_ff_scalar(item, 0, timeout=0.5).value)
        except pa.CommandRejectedError as e:
            if _is_unsupported(e):
                continue
            raise OSError(f"get_ff_scalar item {item} 读回被拒: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise OSError(f"get_ff_scalar item {item} 读回失败: {e}") from e
    return out


def read_snapshot(arm) -> Dict[str, Any]:
    """读回**板子实际支持**的全部参数, 并如实报告能力集合。

    读取顺序: 逐关节 0x24 (恒存在) → 探测 0x2B → 探测 0x2C → ff_mask。

    与旧实现的差别 (2026-10-31): 旧版按本地 `param_catalog` 逐项读, **任何一项读不到
    就整页失败**, 而且目录里没有的项永远不读 —— 目录一旦与板子固件脱节, 要么看不到
    板子真有的参数, 要么被一个不存在的项拖垮整页。现在:
      · 支持与否**由板子回答** (`ERR{cmd,0x02}`/`0x00` = 不支持, 跳过);
      · 超时/链路错误仍是**真故障**, 照旧抛 `OSError` (不能静默当成"不支持");
      · 返回值多一个 `supported`: `{"vec": [...], "scalar": [...]}`, 页面据此隐藏行。

    超出本机关节数的列填 `None`（台架 1J 上 J2..J7 如此）, 页面按"—"显示且不可下发。
    """
    n = n_readable(arm)
    joints: List[Dict[str, Any]] = [dict.fromkeys(_all_joint_keys())
                                    for _ in range(C.NUM_JOINTS)]
    for j in range(n):
        try:
            # ⚠ 读一帧的 getter 自 litearm（原 litearm-core）2.0 起返回 `Msg(value, hz, timestamp)`
            # 信封, 取原值一律走 `.value` (下同; 信封里另两个字段本模块不消费)。
            jp = arm.params.get_joint_param(j).value
        except Exception as e:  # noqa: BLE001
            raise OSError(f"J{j + 1} 读回失败 (get_joint_param): {e}") from e
        joints[j].update(kp=jp.kp, kd=jp.kd, tau_max=jp.tau_max,
                         q_min=jp.q_min, q_max=jp.q_max)

    vec = _probe_vec(arm)
    for p in C.JOINT_PARAMS:
        if p.kind != "vec" or p.item not in vec:
            continue
        vals = vec[p.item]
        for j in range(min(len(vals), n)):
            joints[j][p.key] = vals[j]

    scalar = _probe_scalar(arm)
    glob: Dict[str, Any] = {}
    for gp in C.GLOBAL_PARAMS:
        if gp.item not in scalar:
            continue
        if gp.is_array:
            try:
                glob[gp.key] = [arm.get_ff_scalar(gp.item, sub, timeout=0.5).value
                                for sub in gp.subs]
            except Exception as e:  # noqa: BLE001
                raise OSError(f"{gp.key} 读回失败 (get_ff_scalar): {e}") from e
        else:
            v = scalar[gp.item]
            glob[gp.key] = int(round(v)) if gp.model else float(v)
    try:
        glob["ff_mask"] = int(arm.get_ff_mask(timeout=0.5)) & C.FF_ALL_MASK
    except Exception as e:  # noqa: BLE001
        raise OSError(f"ff_mask 读回失败 (get_ff_mask): {e}") from e
    return {"joints": joints, "global": glob,
            "supported": {"vec": sorted(vec), "scalar": sorted(scalar)}}


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
    """按 0x28/0x27 顺序下发 global；返回 (g, leaf_ok{key:bool}, model_ok, mask_ok)。

    ⚠ 只发 `g` 里**存在**的键 —— `read_snapshot` 现在只返回板子支持的项; 若这里仍按
    目录全量取 `g[key]`, 不支持的项不是 KeyError 就是被写成一个默认值 (0), 两种都在
    替用户改他没见过的参数。
    """
    leaf_ok: Dict[str, bool] = {}
    for gp in C.GLOBAL_PARAMS:
        if gp.key == "friction_model" or gp.key not in g:
            continue
        v = g[gp.key]
        if gp.is_array:
            good = all(set_ff_scalar(arm, gp.item, sub, float(v[k]))[0]
                       for k, sub in enumerate(gp.subs))
        else:
            good = set_ff_scalar(arm, gp.item, gp.subs[0], float(v))[0]
        leaf_ok[gp.key] = good
    if "friction_model" in g:
        model_ok = set_ff_scalar(arm, C.GLOBAL_BY_KEY["friction_model"].item, 0,
                                 float(g["friction_model"]))[0]
    else:
        model_ok = True
    mask_ok = set_ff_mask(arm, int(g["ff_mask"]))[0] if "ff_mask" in g else True
    return g, leaf_ok, model_ok, mask_ok


def dump_snapshot(snap: dict, path: str, model: dict = None) -> None:
    """写快照到 yaml。

    `[2026-09-14]` `model` 为可选第三段 (动力学模型)。产线存档**必须**带上它 ——
    `read_snapshot()` 保持纯参数 (不并模型, 否则老固件下 [刷新当前] 会整页死掉),
    所以存档若不带模型, SOP 的"断电重上电后重读模型比对"就**没有数据源**。
    """
    # 只写有值的项: 读回里 `None` = 本板不支持 / 本机没有这个关节, 写成 null 只会
    # 让回导时多一层"这个键为什么是空的"的噪音 (normalize_snapshot 两种都接受)。
    doc = {"joints": [{"name": f"J{i + 1}",
                       **{k: v for k, v in jd.items() if v is not None}}
                      for i, jd in enumerate(snap["joints"])],
           "global": {k: (list(v) if isinstance(v, list) else v)
                      for k, v in snap["global"].items()}}
    if model is not None:
        doc["model"] = {"body": [list(b) for b in model.get("body", [])],
                        "jm": list(model.get("jm", []))}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
