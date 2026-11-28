"""界面偏好 —— 只存"操作员的选择"，与固件/交互配置无关。

用 ``QSettings`` 的 INI 格式（跨平台路径一致、可直接查看/删除）：
Linux ``~/.config/NexForm/litearm-tool-stm32.ini``，Windows
``%APPDATA%\\NexForm\\litearm-tool-stm32.ini``。

**默认值不写在这里**：没有记录时返回空串，由调用方按
``config.yaml -> language -> 系统`` 的顺序解析（见 ``litetool.i18n``）。
"""
from __future__ import annotations

from PyQt5.QtCore import QSettings

ORGANIZATION = "NexForm"
APPLICATION = "litearm-tool-stm32"
LANGUAGE_KEY = "ui/language"
_VALID = ("", "zh", "en")


class UiPreferences:
    def __init__(self, settings: QSettings | None = None, path: str | None = None):
        if settings is not None:
            self._s = settings
        elif path:
            self._s = QSettings(str(path), QSettings.IniFormat)
        else:
            self._s = QSettings(QSettings.IniFormat, QSettings.UserScope,
                                ORGANIZATION, APPLICATION)

    def language(self) -> str:
        """已保存的选择；``""`` = 没有选择（跟随配置/系统）。"""
        value = self._s.value(LANGUAGE_KEY, "", type=str) or ""
        return value if value in _VALID else ""

    def set_language(self, value: str) -> None:
        value = value if value in _VALID else ""
        if value:
            self._s.setValue(LANGUAGE_KEY, value)
        else:
            self._s.remove(LANGUAGE_KEY)
        self._s.sync()

    def path(self) -> str:
        return self._s.fileName()
