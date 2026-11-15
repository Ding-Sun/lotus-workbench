"""Petal — the right-edge sidebar.

Slides in from the right edge (5 px hot strip, hotkey, or tray), closes itself
when the pointer leaves. Clicking a path opens it; Shift+click opens a terminal
there. Nothing is polled except the cursor position while the sidebar is hidden
(one cheap check every 60 ms) and the clock once per second.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QFileInfo, QObject, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import launcher
from ..core.config import Config
from ..core.launcher import ProcessRegistry
from ..core.notes import NotesStore, humanize
from .rows import KeyboardList
from .theme import Palette
from .window_base import LotusWindow

log = logging.getLogger("lotus.petal")

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_TERMINALS = (
    ("cmd", "CMD", "在默认目录打开 CMD"),
    ("powershell", "PowerShell", "在默认目录打开 PowerShell"),
    ("admin", "管理员 PS", "以管理员身份打开 PowerShell（会弹 UAC）"),
)


def ensure_default_roots(cfg: Config) -> None:
    """Seed Downloads / Desktop / Documents / Videos on first run."""
    items = cfg.get("root.items", [])
    if isinstance(items, list) and items:
        return
    home = Path.home()
    candidates = (
        ("下载", home / "Downloads"),
        ("桌面", home / "Desktop"),
        ("文档", home / "Documents"),
        ("视频", home / "Videos"),
    )
    seeded = [{"name": name, "path": str(path)} for name, path in candidates if path.is_dir()]
    if seeded:
        cfg.set("root.items", seeded)
        log.info("seeded %d default root paths", len(seeded))


class EdgeWatcher(QObject):
    """Fires once when the pointer enters the small top-right hot corner."""

    entered = Signal()

    def __init__(
        self,
        is_open: Callable[[], bool],
        *,
        edge_px: int = 5,
        zone_top: int = 90,
        zone_height: int = 140,
        interval_ms: int = 60,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_open = is_open
        self._edge = max(1, edge_px)
        self._zone_top = max(0, zone_top)
        self._zone_height = max(20, zone_height)
        self._inside = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def apply(self, enabled: bool, top: int, height: int) -> None:
        """Live-apply hot-zone settings from the settings window."""
        self._zone_top = max(0, int(top))
        self._zone_height = max(40, int(height))
        if enabled:
            self._inside = False
            self._timer.start()
        else:
            self._timer.stop()

    def _check(self) -> None:
        if self._is_open():
            # Keep the "inside" latch set while open so closing the sidebar
            # while the pointer still sits on the edge does not reopen it.
            self._inside = True
            return
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos)
        if screen is None:
            return
        geo = screen.availableGeometry()
        zone_top = geo.top() + self._zone_top
        inside = (
            pos.x() >= geo.right() - self._edge + 1
            and zone_top <= pos.y() <= zone_top + self._zone_height
        )
        if inside and not self._inside:
            self.entered.emit()
        self._inside = inside


class PetalWindow(LotusWindow):
    visibility_changed = Signal(bool)
    settings_requested = Signal()
    new_group_requested = Signal()
    desktop_icons_requested = Signal()

    def __init__(
        self,
        cfg: Config,
        palette: Palette,
        registry: ProcessRegistry,
        notes: NotesStore,
        open_manager: Callable[[Path | None], None],
    ) -> None:
        super().__init__(palette, radius=14)
        self.cfg = cfg
        self.registry = registry
        self.notes = notes
        self.open_manager = open_manager
        self._width = int(cfg.get("petal.width", 360))
        self.setFixedWidth(self._width)
        self.setFixedHeight(640)
        self.setAcceptDrops(True)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_animated)
        self._busy = 0  # >0 while a menu/dialog is open

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)

        self.registry.changed.connect(self._update_running)
        self.notes.changed.connect(self.refresh_notes, Qt.ConnectionType.QueuedConnection)
        self.setAcceptDrops(True)
        self._build()
        self.refresh_notes()

    # -- construction ------------------------------------------------------
    def apply_modules(self) -> None:
        """Show / hide sidebar modules according to config.petal.modules."""
        for key, block in (
            ("notes", self.notes_block),
            ("paths", self.paths_block),
            ("terminal", self.terminal_block),
        ):
            block.setVisible(bool(self.cfg.get(f"petal.modules.{key}", True)))
        self.apply_mode()

    def apply_mode(self) -> None:
        grid = str(self.cfg.get("petal.mode", "list")).lower() == "grid"
        self.path_list.setVisible(not grid)
        self.path_grid.setVisible(grid)

    def _label(self, text: str, size: int, color: str, weight: int = 400) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-size: {size}px; font-weight: {weight}; background: transparent;"
        )
        return label

    def _section(self, text: str, trailing: QWidget | None = None, icon: str = "", color: str = "") -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(8)
        title = f"{icon}  {text}" if icon else text
        layout.addWidget(self._label(title, 11, color or self.pal.subtext.name(), 600))
        layout.addStretch(1)
        if trailing is not None:
            layout.addWidget(trailing)
        return row

    def _button(self, text: str, *, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip or text)
        button.setFixedHeight(32)
        button.setStyleSheet(
            f"QPushButton {{ color: {self.pal.text.name()};"
            f" background: {self.pal.surface.name()};"
            f" border: 1px solid {self.pal.border.name()};"
            " border-radius: 7px; font-size: 12px; padding: 0 10px; }"
            f"QPushButton:hover {{ background: {self.pal.surface_hover.name()}; }}"
            f"QPushButton:pressed {{ background: {self.pal.surface_hover.name()}; }}"
        )
        return button

    def _build(self) -> None:
        text_color = self.pal.text.name()
        sub_color = self.pal.subtext.name()

        root = self.content_layout
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.addWidget(self._label("Petal", 16, text_color, 600))
        header.addStretch(1)
        self.add_button = QPushButton("＋")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setFixedSize(26, 26)
        self.add_button.setToolTip("添加常用路径")
        self.add_button.setStyleSheet(
            f"QPushButton {{ color: {sub_color}; background: transparent;"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 13px; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {text_color}; background: {self.pal.surface.name()}; }}"
        )
        self.add_button.clicked.connect(self._add_path_dialog)
        header.addWidget(self.add_button)

        self.new_box_button = QPushButton("▦")
        self.new_box_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_box_button.setFixedSize(26, 26)
        self.new_box_button.setToolTip("新建收纳盒")
        self.new_box_button.setStyleSheet(
            f"QPushButton {{ color: {sub_color}; background: transparent;"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 13px; font-size: 13px; }}"
            f"QPushButton:hover {{ color: {text_color}; background: {self.pal.surface.name()}; }}"
        )
        self.new_box_button.clicked.connect(self.new_group_requested.emit)
        header.addWidget(self.new_box_button)
        root.addLayout(header)

        root.addSpacing(18)
        self.all_notes = QPushButton("全部")
        self.all_notes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_notes.setFixedHeight(20)
        self.all_notes.setStyleSheet(
            f"QPushButton {{ color: {sub_color}; background: transparent; border: none;"
            " font-size: 11px; padding: 0 2px; }"
            f"QPushButton:hover {{ color: {text_color}; }}"
        )
        self.all_notes.clicked.connect(lambda: self.open_manager(None))

        self.notes_block = QWidget()
        notes_layout = QVBoxLayout(self.notes_block)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(6)
        notes_layout.addWidget(self._section("最近速记", self.all_notes, icon="📝", color=self.pal.accent.lighter(135).name()))
        self.notes_list = KeyboardList(self.pal)
        self.notes_list.activated.connect(self._open_note_index)
        notes_layout.addWidget(self.notes_list)
        self.notes_empty = self._label("还没有笔记 · Alt+N 记一笔", 11, sub_color)
        notes_layout.addWidget(self.notes_empty)
        root.addWidget(self.notes_block)

        root.addSpacing(20)
        self.paths_block = QWidget()
        paths_layout = QVBoxLayout(self.paths_block)
        paths_layout.setContentsMargins(0, 0, 0, 0)
        paths_layout.setSpacing(6)
        paths_layout.addWidget(self._section("常用路径", icon="📂", color="#5FB3A1"))
        self.path_list = KeyboardList(self.pal)
        self.path_list.activated.connect(self._open_index)
        paths_layout.addWidget(self.path_list)

        self.path_grid = QListWidget()
        self.path_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.path_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.path_grid.setMovement(QListWidget.Movement.Static)
        self.path_grid.setGridSize(QSize(96, 96))
        self.path_grid.setIconSize(QSize(38, 38))
        self.path_grid.setWordWrap(True)
        self.path_grid.setSpacing(4)
        self.path_grid.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            f"QListWidget::item {{ color: {text_color}; border-radius: 8px; padding: 4px; }}"
            f"QListWidget::item:selected {{ background: rgba(255,255,255,26); }}"
        )
        self.path_grid.itemDoubleClicked.connect(self._grid_activated)
        paths_layout.addWidget(self.path_grid)
        root.addWidget(self.paths_block)

        root.addStretch(1)

        root.addSpacing(18)
        self.terminal_block = QWidget()
        terminal_layout = QVBoxLayout(self.terminal_block)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(8)
        terminal_layout.addWidget(self._section("终端", icon="⌨"))
        terminals = QHBoxLayout()
        terminals.setSpacing(8)
        for kind, text, tip in _TERMINALS:
            button = self._button(text, tooltip=tip)
            button.clicked.connect(lambda _checked=False, k=kind: self._spawn_terminal(k))
            terminals.addWidget(button, 1)
        terminal_layout.addLayout(terminals)
        root.addWidget(self.terminal_block)
        self.apply_modules()

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.settings_button = QPushButton("⚙   设置")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setFixedHeight(34)
        self.settings_button.setStyleSheet(
            f"QPushButton {{ color: {text_color}; background: {self.pal.surface.name()};"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 8px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {self.pal.surface_hover.name()}; }}"
        )
        self.settings_button.clicked.connect(self.settings_requested.emit)
        actions.addWidget(self.settings_button, 2)

        self.desktop_button = QPushButton("🖥  隐藏桌面")
        self.desktop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.desktop_button.setFixedHeight(34)
        self.desktop_button.setStyleSheet(
            f"QPushButton {{ color: {text_color}; background: {self.pal.surface.name()};"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 8px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {self.pal.surface_hover.name()}; }}"
        )
        self.desktop_button.clicked.connect(self.desktop_icons_requested.emit)
        actions.addWidget(self.desktop_button, 2)
        root.addLayout(actions)
        root.addSpacing(12)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(1)
        self.time_label = self._label("--:--", 15, text_color, 600)
        self.date_label = self._label("", 10, sub_color)
        left.addWidget(self.time_label)
        left.addWidget(self.date_label)
        footer.addLayout(left)
        footer.addStretch(1)

        self.running_label = self._label("运行中：无", 10, sub_color)
        self.running_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        footer.addWidget(self.running_label)
        root.addLayout(footer)

        self.reload_paths()

    # -- paths -------------------------------------------------------------
    def _items(self) -> list[dict]:
        items = self.cfg.get("root.items", [])
        return items if isinstance(items, list) else []

    def _display(self, path: str) -> str:
        try:
            home = str(Path.home())
            if path.lower().startswith(home.lower()):
                return "~" + path[len(home) :]
        except Exception:  # noqa: BLE001
            pass
        return path

    def reload_paths(self) -> None:
        items = self._items()
        entries = []
        for item in items:
            path = str(item.get("path", ""))
            label = str(item.get("name") or Path(path).name)
            subtitle = self._display(path)
            if not Path(path).is_dir():
                subtitle += "  （不存在）"
            entries.append((label, subtitle))
        self.path_list.set_items(entries)
        for index, row in enumerate(self.path_list.rows()):
            row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            row.customContextMenuRequested.connect(
                lambda pos, i=index, r=row: self._path_menu(i, r.mapToGlobal(pos))
            )

        provider = QFileIconProvider()
        self.path_grid.clear()
        for item in items:
            path = str(item.get("path", ""))
            label = str(item.get("name") or Path(path).name)
            icon = provider.icon(QFileIconProvider.IconType.Folder)
            if Path(path).exists():
                icon = provider.icon(QFileInfo(path))
            entry = QListWidgetItem(icon, label)
            entry.setData(Qt.ItemDataRole.UserRole, path)
            entry.setToolTip(path)
            entry.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.path_grid.addItem(entry)
        self.apply_mode()

    def _grid_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            launcher.open_path(str(path))

    def _save_items(self, items: list[dict]) -> None:
        self.cfg.set("root.items", items)
        self.reload_paths()

    def _add_path(self, path: str) -> None:
        path = str(Path(path))
        items = self._items()
        if any(str(item.get("path", "")).lower() == path.lower() for item in items):
            return
        items.append({"name": Path(path).name or path, "path": path})
        self._save_items(items)
        log.info("root path added: %s", path)

    def _add_path_dialog(self) -> None:
        self._busy += 1
        try:
            directory = QFileDialog.getExistingDirectory(self, "添加常用路径", str(Path.home()))
        finally:
            self._busy -= 1
        if directory:
            self._add_path(directory)

    def _open_index(self, index: int) -> None:
        items = self._items()
        if not (0 <= index < len(items)):
            return
        path = str(items[index].get("path", ""))
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._spawn_terminal("powershell", path)
        else:
            launcher.open_path(path)

    def _path_menu(self, index: int, global_pos: QPoint) -> None:
        items = self._items()
        if not (0 <= index < len(items)):
            return
        item = items[index]
        path = str(item.get("path", ""))

        menu = QMenu(self)
        menu.addAction("打开", lambda: launcher.open_path(path))
        menu.addAction("在终端中打开", lambda: self._spawn_terminal("powershell", path))
        menu.addAction("在资源管理器中定位", lambda: launcher.reveal_path(path))
        menu.addSeparator()
        menu.addAction("重命名…", lambda: self._rename(index))
        menu.addAction("移除", lambda: self._remove(index))
        self._busy += 1
        try:
            menu.exec(global_pos)
        finally:
            self._busy -= 1

    def _rename(self, index: int) -> None:
        items = self._items()
        if not (0 <= index < len(items)):
            return
        current = str(items[index].get("name", ""))
        self._busy += 1
        try:
            name, ok = QInputDialog.getText(self, "重命名", "名称", text=current)
        finally:
            self._busy -= 1
        if ok and name.strip():
            items[index]["name"] = name.strip()
            self._save_items(items)

    def _remove(self, index: int) -> None:
        items = self._items()
        if not (0 <= index < len(items)):
            return
        removed = items.pop(index)
        self._save_items(items)
        log.info("root path removed: %s", removed.get("path"))

    # -- terminals ---------------------------------------------------------
    def _default_dir(self) -> str:
        configured = str(self.cfg.get("stem.default_dir", "") or "")
        return configured if Path(configured).is_dir() else str(Path.home())

    def _spawn_terminal(self, kind: str, directory: str | None = None) -> None:
        ok, error = self.registry.spawn_terminal(kind, directory or self._default_dir())
        if not ok:
            log.warning("terminal failed (%s): %s", kind, error)
            self.running_label.setText(f"启动失败：{error}")
        else:
            log.info("terminal spawned: %s", kind)

    def _update_running(self) -> None:
        names = self.registry.active()
        if not names:
            self.running_label.setText("运行中：无")
        else:
            self.running_label.setText("运行中：" + "、".join(names))

    # -- recent notes ------------------------------------------------------
    def refresh_notes(self) -> None:
        recent = self.notes.recent(3)
        self.notes_list.set_items([(note.title, humanize(note.updated)) for note in recent])
        self.notes_list.clear_selection()
        has_notes = bool(recent)
        self.notes_list.setVisible(has_notes)
        self.notes_empty.setVisible(not has_notes)

    def _open_note_index(self, index: int) -> None:
        recent = self.notes.recent(3)
        if 0 <= index < len(recent):
            self.open_manager(recent[index].path)

    # -- clock -------------------------------------------------------------
    def _tick(self) -> None:
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M"))
        self.date_label.setText(f"{now.month}月{now.day}日 {_WEEKDAYS[now.weekday()]}")

    # -- show / hide -------------------------------------------------------
    def show_at_cursor(self) -> None:
        screen = self.screen_at_cursor()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.setFixedHeight(geo.height())
        self.move(geo.right() - self.width() + 1, geo.top())
        self.apply_modules()
        self._tick()
        self._update_running()
        self.refresh_notes()
        self.show_animated(QPoint(self.width(), 0))
        self.path_list.setFocus()
        self.visibility_changed.emit(True)

    def toggle(self) -> None:
        if self.is_shown():
            self.hide_animated(QPoint(self.width(), 0))
        else:
            self.show_at_cursor()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.hide_animated(QPoint(self.width(), 0))
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._clock.start()
        self._tick()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().hideEvent(event)
        self._clock.stop()
        self._hide_timer.stop()
        self.visibility_changed.emit(False)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._busy <= 0:
            delay = int(self.cfg.get("petal.hide_delay_ms", 450))
            self._hide_timer.start(max(150, delay))
        super().leaveEvent(event)

    # -- drag & drop -------------------------------------------------------
    def _dropped_dirs(self, event) -> list[str]:
        paths = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local and Path(local).is_dir():
                    paths.append(local)
        return paths

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dropped_dirs(event):
            self._hide_timer.stop()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        delay = int(self.cfg.get("petal.hide_delay_ms", 450))
        self._hide_timer.start(max(150, delay))
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hide_timer.stop()
        for path in self._dropped_dirs(event):
            self._add_path(path)
        event.acceptProposedAction()






