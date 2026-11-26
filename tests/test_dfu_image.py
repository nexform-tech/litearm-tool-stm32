"""固件镜像判据 + 升级流水线（纯离线，不需要硬件 / Qt / pyusb）。

镜像与流水线两半都从 studio 原样搬过来（见 `litetool/dfu/` 的文件头）；这里保留
它的判据用例，确保"选了错文件"与"进 DFU 之后失败"这两类结局在 tool 侧仍然成立。
"""
from __future__ import annotations


import pytest

from litetool.dfu import image, job


# ------------------------------------------------------------------ 造一份镜像

def _rec(off: int, typ: int, data: bytes) -> str:
    body = bytes([len(data), (off >> 8) & 0xFF, off & 0xFF, typ]) + data
    return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()


def _ext(upper16: int) -> str:
    return _rec(0, 0x04, bytes([(upper16 >> 8) & 0xFF, upper16 & 0xFF]))


def make_hex(payload: bytes = b"Litearm1.9.0-7J\x00\x00\x00\x00",
             base_hi: int = 0x0800, extra: str = "") -> str:
    """一份起于应用基址的最小合法 Intel HEX（`extra` 用来追加别的地址段）。"""
    lines = [_ext(base_hi)]
    for off in range(0, len(payload), 16):
        lines.append(_rec(off & 0xFFFF, 0x00, payload[off:off + 16]))
    if extra:
        lines.append(extra)
    lines.append(":00000001FF")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 镜像判据

def test_a_valid_hex_image_is_summarized_and_32b_aligned():
    blob, summary = image.inspect("fw.hex", make_hex().encode())
    assert summary.base == image.APP_BASE
    assert summary.format == "hex"
    assert summary.version == "Litearm1.9.0-7J"
    assert summary.version_note == ""
    assert len(blob) % 32 == 0, "长度必须补齐到 H7 flash word —— 否则会二次编程坏 ECC"


def test_a_bare_bin_is_accepted_at_the_app_base_and_padded():
    blob, summary = image.inspect("fw.bin", b"\x01" * 100)
    assert summary.base == image.APP_BASE and summary.format == "bin"
    assert len(blob) == 128 and len(blob) % 32 == 0
    # 裸 bin 里没有版本串 —— 提取不到是**正常**的，但要说清原因。
    assert summary.version is None and "未找到" in summary.version_note


@pytest.mark.parametrize("text,reason", [
    # 起于 0x08020000：应用只能烧到 0x08000000
    (_ext(0x0802) + "\n" + _rec(0, 0x00, b"\xAA" * 8) + "\n:00000001FF\n",
     "image_not_at_app_base"),
    # 起于基址但伸进受保护区 (扇区 6 许可证 / 扇区 7 标定)
    (_ext(0x0800) + "\n" + _rec(0, 0x00, b"\xAA" * 8) + "\n"
     + _ext(0x080C) + "\n" + _rec(0, 0x00, b"\xBB" * 8) + "\n:00000001FF\n",
     "image_covers_protected"),
    # 起于基址但越出 1MB
    (_ext(0x0800) + "\n" + _rec(0, 0x00, b"\xAA" * 8) + "\n"
     + _ext(0x0810) + "\n" + _rec(0, 0x00, b"\xBB" * 8) + "\n:00000001FF\n",
     "image_too_large"),
    ("这不是 HEX，也不是 bin\n", "image_unreadable"),
])
def test_unusable_images_are_rejected_with_a_reason(text: str, reason: str):
    """短码是**界面的判据** —— 文案要分中英文，所以不能靠异常消息选。"""
    with pytest.raises(image.ImageError) as ei:
        image.inspect("fw.hex", text.encode())
    assert ei.value.reason == reason


def test_the_protected_span_is_rejected_even_when_it_is_the_whole_image():
    """整份镜像落在受保护区 ⇒ 先撞"基址不对"。两条拦法都对，重点是**不许放过**。"""
    text = _ext(0x080C) + "\n" + _rec(0, 0x00, b"\xAA" * 8) + "\n:00000001FF\n"
    with pytest.raises(image.ImageError) as ei:
        image.inspect("fw.hex", text.encode())
    assert ei.value.reason in ("image_covers_protected", "image_not_at_app_base")


def test_summary_to_dict_keeps_the_ui_contract():
    _, summary = image.inspect("fw.hex", make_hex().encode())
    doc = summary.to_dict()
    assert set(doc) == {"name", "format", "base", "size", "holes",
                        "version", "versionNote", "sha256"}
    assert len(doc["sha256"]) == 64


# ------------------------------------------------------------------ 流水线

class Hooks:
    """`job.UpgradeHooks` 的假件；记录相位顺序，可注入失败。"""

    def __init__(self, *, fail: str | None = None,
                 version: str = "Litearm1.9.0-7J",
                 on_flash=None, cancelled=None):
        self.calls: list[str] = []
        self.fail = fail
        self.version = version
        self.on_flash = on_flash
        self.cancelled = cancelled
        self.blob = None
        self.progress: list[tuple[int, int, str]] = []

    def disarm(self):
        self.calls.append("disarm")
        if self.fail == "disarm":
            raise job.UpgradeError("arm_enabled", "机械臂没有失能")

    def enter_dfu(self):
        self.calls.append("enter_dfu")
        if self.fail == "enter":
            raise job.UpgradeError("dfu_not_entered", "ACK 丢了")

    def wait_for_dfu(self, is_cancelled):
        self.calls.append("wait")

    def flash(self, blob, base, on_progress):
        self.calls.append("flash")
        self.blob = blob
        total = len(blob)
        on_progress(total // 2, total, "写入一半")
        if self.on_flash:
            self.on_flash()
        if self.fail == "flash":
            raise job.UpgradeError("flash_failed", "读回校验失败")
        on_progress(total, total, "读回校验通过")

    def detach(self):
        self.calls.append("detach")

    def reconnect(self, is_cancelled):
        self.calls.append("reconnect")
        return "/dev/ttyACM0", self.version


def _summary():
    blob, summary = image.inspect("fw.hex", make_hex().encode())
    return blob, summary


def _run(hooks, *, from_dfu=False, cancelled=False):
    blob, summary = _summary()
    progress = []
    result = job.run_upgrade(
        blob=blob, base=summary.base, summary=summary, hooks=hooks,
        emit=progress.append, is_cancelled=lambda: cancelled,
        from_dfu=from_dfu)
    return result, progress, blob


def test_full_pipeline_walks_every_phase_and_reports_success():
    hooks = Hooks()
    result, progress, blob = _run(hooks)

    assert hooks.calls == ["disarm", "enter_dfu", "wait", "flash",
                           "detach", "reconnect"]
    assert hooks.blob == blob
    assert result.ok is True and result.reason is None
    assert result.version == "Litearm1.9.0-7J" and result.port == "/dev/ttyACM0"
    phases = [p.phase for p in progress]
    assert phases[0] == job.PHASE_VALIDATE
    assert phases[-3:] == [job.PHASE_DETACH, job.PHASE_RECONNECT, job.PHASE_DONE]
    assert any(p.phase == job.PHASE_FLASH and p.total == len(blob)
               for p in progress)


def test_from_dfu_skips_disarm_and_enter():
    """板子已经在 bootloader 里：应用没在跑 ⇒ 没有"要先失能"的东西。"""
    hooks = Hooks()
    result, progress, _ = _run(hooks, from_dfu=True)

    assert hooks.calls == ["wait", "flash", "detach", "reconnect"]
    assert result.ok is True
    phases = [p.phase for p in progress]
    assert job.PHASE_DISARM not in phases and job.PHASE_ENTER_DFU not in phases
    assert phases[1] == job.PHASE_WAIT_DFU


def test_a_flash_failure_is_reported_and_the_device_is_detached():
    hooks = Hooks(fail="flash")
    result, _, _ = _run(hooks)

    assert result.ok is False and result.reason == "flash_failed"
    assert "detach" in hooks.calls, "失败的板子不许留在 bootloader 里"
    assert "reconnect" not in hooks.calls


def test_a_disarm_failure_stops_before_touching_dfu():
    hooks = Hooks(fail="disarm")
    result, _, _ = _run(hooks)

    assert result.ok is False and result.reason == "arm_enabled"
    assert hooks.calls == ["disarm"]
    assert "detach" not in hooks.calls


def test_a_dropped_ack_on_enter_dfu_still_detaches_the_board():
    """ACK 丢了但设备可能已经跳了 —— 失败收尾仍要试着把它拉出来。"""
    hooks = Hooks(fail="enter")
    result, _, _ = _run(hooks)

    assert result.ok is False and result.reason == "dfu_not_entered"
    assert "flash" not in hooks.calls
    assert "detach" in hooks.calls


def test_a_version_mismatch_is_a_warning_not_a_failure():
    """读回校验已经过了 ⇒ 镜像确实写进去了。版本对不上要让人看见, 但不是失败。"""
    hooks = Hooks(version="Litearm1.8.0-7J")
    result, _, _ = _run(hooks)

    assert result.ok is True
    assert result.warning and "1.9.0" in result.warning and "1.8.0" in result.warning


def test_cancel_before_start_stops_the_pipeline():
    hooks = Hooks()
    result, progress, _ = _run(hooks, cancelled=True)

    assert result.ok is False and result.reason == "cancelled"
    assert hooks.calls == []
    assert [p.phase for p in progress] == [job.PHASE_VALIDATE]


def test_cancel_after_the_flash_finished_is_not_a_failure():
    """烧完了才按的取消：镜像已经落盘, 不能说"没升级"。"""
    state = {"cancelled": False}
    hooks = Hooks(on_flash=lambda: state.update(cancelled=True))
    blob, summary = _summary()
    progress = []
    result = job.run_upgrade(
        blob=blob, base=summary.base, summary=summary, hooks=hooks,
        emit=progress.append, is_cancelled=lambda: state["cancelled"])

    assert result.ok is True
    assert "detach" in hooks.calls and "reconnect" in hooks.calls


def test_a_raising_hook_is_folded_into_a_result():
    """任何一步都不许把异常漏出去 —— 漏出去操作员就看不到是哪一步坏的。"""
    class Bad(Hooks):
        def wait_for_dfu(self, is_cancelled):
            raise RuntimeError("usb 炸了")

    hooks = Bad()
    result, _, _ = _run(hooks)
    assert result.ok is False and result.reason == "flash_failed"
    assert "usb 炸了" in result.message
    assert "detach" in hooks.calls, "已进入 DFU 的板子仍要尝试拉出来"


def test_progress_carries_done_and_total():
    hooks = Hooks()
    _, progress, blob = _run(hooks)
    flash = [p for p in progress if p.phase == job.PHASE_FLASH]
    assert flash[-1].done == len(blob) and flash[-1].total == len(blob)
