"""System tray presence: the always-there entry point."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..core import paths
from ..core.config import Config
from .icons import lotus_icon
from .theme import Palette

log = logging.getLogger("lotus.tray")


class Tray(QSystemTrayIcon):
    bloom_requested = Signal()
    petal_requested = Signal()
    ink_requested = Signal()
    settings_requested = Signal()
    icons_toggle_requested = Signal(bool)
    quit_requested = Signal()

    def __init__(self, palette: Palette, cfg: Config, parent=None) -> None:
        self._icon = lotus_icon(palette)
        super().__init__(self._icon, parent)
        self.cfg = cfg
        self.setToolTip("Lotus Workbench")
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        bloom = menu.addAction("打开工作台 Bloom")
        bloom.triggered.connect(self.bloom_requested.emit)

        petal = menu.addAction("侧边栏 Petal")
        petal.triggered.connect(self.petal_requested.emit)

        ink = menu.addAction("速记 Ink")
        ink.triggered.connect(self.ink_requested.emit)

        menu.addSeparator()

        self.icons_action = menu.addAction("隐藏桌面图标")
        self.icons_action.setCheckable(True)
        self.icons_action.toggled.connect(self.icons_toggle_requested.emit)

        menu.addSeparator()

        open_data = menu.addAction("打开数据目录")
        open_data.triggered.connect(lambda: os.startfile(str(paths.HOME)))  # noqa: S606

        settings = menu.addAction("设置…")
        settings.triggered.connect(self.settings_requested.emit)

        menu.addSeparator()

        quit_action = menu.addAction("退出 Lotus")
        quit_action.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(menu)

    def notify(self, title: str, message: str, *, warning: bool = False) -> None:
        icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
        try:
            self.showMessage(title, message, icon, 4000)
        except Exception:  # noqa: BLE001 - notifications are best-effort
            log.debug("tray notification failed", exc_info=True)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.bloom_requested.emit()

