"""动力学模型读写 —— 在 `pylitearm_stm32.Arm.model` 之上的一层薄封装。

为什么需要这一层 (与 `params_io` 同因): 模型页要的形状是「逐写口下发, 每个写口回一个
`(ok, code)`」, 这样才能把失败**精确标到某一项**; 而 SDK 是「失败即抛异常」。

**线程约定**: 每个函数都直接碰 `Arm`, 故**只能在 SDK 所有者线程上调用**
(即作为 `SdkWorker.submit` 的 `fn`)。

## 与 `params_io` 的两处刻意差异

1. **`_call` 的错误码默认值**: `params_io._call` 用 `getattr(e, "code", 0)`, 默认 0
   —— 一个"构造了 `CommandRejectedError` 但没带 `.code`"的异常会被显示成
   「固件无此命令 (未实现)」, 误导性极强。本模块用**默认 `None`** (显示"超时/无应答")。
2. **`UnsupportedByFirmwareError` 单独识别**: 它是 `(False, 0x00)`, 与"无 code"不同 ——
   `probe()` 靠它判"旧固件"。
"""
from __future__ import annotations

import struct
from typing import Any, Callable, Dict, List, Optional, Tuple

import pylitearm_stm32 as pa

from litetool import param_catalog as C
from litetool.hyy_config import MODEL_BODY_KEYS, MODEL_ABS_MAX

#: 工具/产线实际写入的集合: body1..7 + jm。**与 SDK 的 `MODEL_MASK_WRITTEN` 同值**。
MASK_WRITTEN = (sum(1 << i for i in range(1, 8))) | (1 << 9)      # 0x2FE
assert MASK_WRITTEN == 0x2FE

#: 模型刚体数 (与固件 `DYN_MODEL_NBODY` / SDK `MODEL_NBODY` 同值, 与关节数**无关**)
NBODY = 9
BODY_PARAMS = 10
JM_N = 7

Result = Tuple[bool, Optional[int]]


def err_text(code: Optional[int]) -> str:
    """错误码 -> 中文。0x07 是本设计新增的"掩码不符"(与"数值非法"分开)。"""
    if code is None:
        return "超时/无应答"
    return {
        0x00: "固件无此命令（未实现）",
        0x01: "载荷过短",
        0x02: "数值非法（NaN/超限/零模型），固件已拒绝",
        0x04: "需先失能（模型 commit/回退要求失能态）",
        0x05: "忙（flash 正在擦写）",
        0x07: "掩码不符（本会话漏写或写错了 body）",
    }.get(code, f"code 0x{code:02X}")


def _call(fn: Callable[[], Any]) -> Result:
    """执行一次写口; 异常 -> (False, code)。

    ⚠ 与 `params_io._call` 的差别: `getattr(..., "code", None)` —— **默认 None 而非 0**。
    默认 0 会把"不带 code 的拒绝"显示成「固件无此命令」, 让操作员去查错方向。
    """
    try:
        fn()
        return True, None
    except pa.UnsupportedByFirmwareError:
        return False, 0x00                     # 固件无此命令 (能力探测的唯一稳定哨兵)
    except pa.CommandRejectedError as e:
        return False, getattr(e, "code", None)
    except Exception:                          # noqa: BLE001 - 超时/链路统一归 None
        return False, None


# --------------------------------------------------------------------------
# 能力探测
# --------------------------------------------------------------------------
def probe(arm) -> bool:
    """固件是否支持模型在线导入 (用 `0x34` 探测 —— **不能**用 0x30/0x33)。

    旧固件对 `0x30`/`0x33` 有**显式 case** 回 `ERR{cmd,0x02}` (与"数值非法"同码),
    无法区分「无此命令」与「参数非法」; 而 `0x34` 是新增号, 旧固件落 `default`
    ⇒ `ERR{0x34,0x00}` ⇒ 稳定的能力哨兵。
    """
    try:
        arm.model.probe()
        return True
    except Exception:                          # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# 读回
# --------------------------------------------------------------------------
def read_model(arm) -> Dict[str, Any]:
    """读回**生效 bank** 全模型: `{"body": [[10]×9], "jm": [7], "status": ModelStatus}`。

    任何一项读不到即抛 `OSError` —— 半截快照比没有更危险 (会被当成基线)。

    ⚠ 判据**只有固件能力** (`0x34` 是否可用), **不掺 `arm.n`**: 模型恒 9 刚体,
    与关节数解耦 (台架 1J 上固件同样支持 9 刚体)。照抄 `params_io.n_readable`
    会让台架完全无法验证模型。
    """
    body: List[List[float]] = []
    for i in range(NBODY):
        try:
            v = arm.model.get_body(i)
        except Exception as e:                  # noqa: BLE001
            raise OSError(f"模型 body{i} 读回失败: {e}") from e
        if len(v) != BODY_PARAMS:
            raise OSError(f"模型 body{i} 长度 {len(v)} != {BODY_PARAMS}")
        body.append([float(x) for x in v])
    try:
        jm = [float(x) for x in arm.model.get_jm()]
    except Exception as e:                      # noqa: BLE001
        raise OSError(f"模型 jm 读回失败: {e}") from e
    if len(jm) != JM_N:
        raise OSError(f"模型 jm 长度 {len(jm)} != {JM_N}")
    try:
        st = arm.model.status()
    except Exception as e:                      # noqa: BLE001
        raise OSError(f"模型状态读回失败: {e}") from e
    return {"body": body, "jm": jm, "status": st}


def read_model_safe(arm) -> Optional[Dict[str, Any]]:
    """`read_model` 的"不抛"版本 —— 供 [刷新当前] 用 (老固件下不应把整页打挂)。"""
    try:
        return read_model(arm)
    except Exception:                          # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# 下发
# --------------------------------------------------------------------------
def send_model(arm, model: Dict[str, Any], mask: int = MASK_WRITTEN) -> Dict[str, Any]:
    """逐帧下发模型并 commit。返回 `{"frames": {(kind, idx): (ok, code)}, "commit": Result}`。

    **只发 `mask` 指定的项** (默认 body1..7 + jm)。`body0` (base, 不参与递推) 与
    `body8` (ee, payload 复合位, 固件拒绝其质量非 0) **不发**。

    ⚠ **必须逐帧请求-应答, 不得流水线** —— 固件 `usb_cmd_process()` 每拍全排空 RX,
    而应答 FIFO 深度只有 4 (`REPLY_FIFO_DEPTH`); 9 帧流水线会丢掉 3~5 个 ACK。
    SDK 的 `_cmd` 本身就在等 ACK, 故这里顺序调用即可。

    任一帧失败 ⇒ **立即中止且不 commit** (staging 里残留的半套不影响生效模型,
    但下一次导入会重新惰性初始化, 故无需清理)。
    """
    frames: Dict[Tuple[str, int], Result] = {}
    body = model["body"]
    jm = model["jm"]

    for i in range(NBODY):
        if not (mask & (1 << i)):
            continue
        vals = list(body[i])
        if len(vals) != BODY_PARAMS:
            frames[("body", i)] = (False, None)
            return {"frames": frames, "commit": (False, None),
                    "aborted": f"body{i} 参数个数 {len(vals)} != {BODY_PARAMS}"}
        r = _call(lambda i=i, vals=vals: arm.model.set_body(i, vals))
        frames[("body", i)] = r
        if not r[0]:
            return {"frames": frames, "commit": (False, None), "aborted": f"body{i} 写入被拒"}

    if mask & (1 << 9):
        vals = [float(x) for x in jm]
        if len(vals) != JM_N:
            frames[("jm", 0)] = (False, None)
            return {"frames": frames, "commit": (False, None),
                    "aborted": f"jm 个数 {len(vals)} != {JM_N}"}
        r = _call(lambda: arm.model.set_jm(vals))
        frames[("jm", 0)] = r
        if not r[0]:
            return {"frames": frames, "commit": (False, None), "aborted": "jm 写入被拒"}

    commit = _call(lambda: arm.model.commit(mask))
    return {"frames": frames, "commit": commit, "aborted": None}


def revert_model(arm) -> Result:
    """只回退模型 (0x37)。**不动 flash** —— 见 `pylitearm_stm32.model.ModelParams.revert`。"""
    return _call(lambda: arm.model.revert())


def get_gravity(arm, q) -> List[float]:
    """给定 q 求 G(q) (0x39) —— 静态重力核查用。"""
    return [float(x) for x in arm.model.get_gravity(list(q))]


# --------------------------------------------------------------------------
# 读回比对 (闸)
# --------------------------------------------------------------------------
def _f32(v) -> float:
    """把快照值先固定成 float32 —— yaml 是 float64、设备回 float32。

    直接比会让 90/91 个值里那 1 个差 1 ULP 的项 (J4 的 ixy) 恒报差异。
    """
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-6, 1e-6 * abs(b))


def readback_compare(arm, model: Dict[str, Any], mask: int = MASK_WRITTEN) -> List[Tuple]:
    """读回 bank 逐项比对。返回差异清单 `[(label, want_f32, got_f32)]` (空 = 全绿)。

    只覆盖 `mask` 指定的项。**这是"字节落位"的证明, 不是"模型正确"的证明** ——
    对 wrong-but-consistent (错台 yaml / 跨会话拼接) 必然全绿; 那类只能靠静态重力核查。
    """
    got = read_model(arm)
    diffs: List[Tuple] = []
    for i in range(NBODY):
        if not (mask & (1 << i)):
            continue
        for k, key in enumerate(MODEL_BODY_KEYS):
            w, g = _f32(model["body"][i][k]), got["body"][i][k]
            if not _same(w, g):
                diffs.append((f"B{i}.{key}", w, g))
    if mask & (1 << 9):
        for k in range(JM_N):
            w, g = _f32(model["jm"][k]), got["jm"][k]
            if not _same(w, g):
                diffs.append((f"jm.J{k + 1}", w, g))
    return diffs


def validate_model(model: Dict[str, Any]) -> List[str]:
    """工具侧前置校验 (在**下发前**做, 让操作员看到准确原因而不是固件的 `0x02`)。

    与固件写口同口径: 逐项有限且 `|v| <= 1e6`; `body8` 质量必须为 0。
    **不做物理范围钳制** —— 辨识基参数单个无物理意义 (m 全是 1.0、I 含负值)。
    返回中文错误清单 (空 = 合法)。
    """
    errs: List[str] = []
    body = model.get("body") or []
    jm = model.get("jm") or []
    if len(body) != NBODY:
        errs.append(f"模型 body 须为 {NBODY} 个, 实际 {len(body)}")
        return errs
    for i, b in enumerate(body):
        if len(b) != BODY_PARAMS:
            errs.append(f"body{i} 须为 {BODY_PARAMS} 个, 实际 {len(b)}")
            continue
        for k, key in enumerate(MODEL_BODY_KEYS):
            v = float(b[k])
            if v != v or abs(v) > MODEL_ABS_MAX:
                errs.append(f"body{i}.{key} = {v} 非有限或超出 ±{MODEL_ABS_MAX:g}")
        if i == NBODY - 1 and float(b[0]) != 0.0:
            errs.append(f"body{i} 是 ee 固定体 (payload 复合位), 质量必须为 0, 实际 {b[0]}")
    if len(jm) != JM_N:
        errs.append(f"jm 须为 {JM_N} 个, 实际 {len(jm)}")
    else:
        for k, v in enumerate(jm):
            if float(v) != float(v) or abs(float(v)) > MODEL_ABS_MAX:
                errs.append(f"jm.J{k + 1} = {v} 非有限或超出 ±{MODEL_ABS_MAX:g}")
    return errs


def flatten_model(model: Dict[str, Any]) -> Dict[str, float]:
    """模型 -> 打平字典 `{"B1.m": v, ..., "jm.J1": v}` (供 diff 显示与存档)。"""
    flat: Dict[str, float] = {}
    for i, b in enumerate(model.get("body") or []):
        for k, key in enumerate(MODEL_BODY_KEYS):
            flat[f"B{i}.{key}"] = float(b[k])
    for k, v in enumerate(model.get("jm") or []):
        flat[f"jm.J{k + 1}"] = float(v)
    return flat


#: diff/比对的默认范围 = 实际写入的集合 (body1..7 + jm)。
#: ⚠ 必须限定: `body0` (base, 不参与递推) 与 `body8` (ee, payload 复合位) **不写**,
#: 设备保持原值 ⇒ 把它们算进 diff 会**每次都报一条假"修改"**。
MODEL_DIFF_LABELS = tuple(
    [f"B{i}.{k}" for i in range(1, 8) for k in MODEL_BODY_KEYS]
    + [f"jm.J{i}" for i in range(1, 8)])


def model_diff(old: Optional[Dict[str, Any]], new: Dict[str, Any],
               only: Optional[Tuple[str, ...]] = None) -> List[Tuple]:
    """模型段 diff —— `[(label, old, new)]`, 供 `ParamDiffDialog` 的模型段。

    默认只比**实际写入的集合** (body1..7 + jm); `new` 缺失某项 (如 YAML 模型段的
    body0) 时也不报。这是"旧值列全空 / 满屏新增"这类反模式的防线。
    """
    labels = only if only is not None else MODEL_DIFF_LABELS
    fo = flatten_model(old) if old else {}
    fn = flatten_model(new)
    out: List[Tuple] = []
    for lab in labels:
        if lab not in fn:
            continue
        ov = fo.get(lab)
        if ov is None or not _same(_f32(ov), _f32(fn[lab])):
            out.append((lab, ov, fn[lab]))
    return out
