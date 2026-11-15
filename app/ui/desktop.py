"""Desktop layer: one bottom-pinned window per bubble group.

This replaces the old full-screen Bloom overlay. Each bubble is its own
top-level window, so empty desktop space has no window at all and clicks pass
straight through to the icons.

Windows are pushed to the bottom of the Z order and marked no-activate at rest;
a watchdog re-shows/re-beds them after Win+D or a display change.
"""

from __future__ import annotations

import ctypes
import logging
import pathlib
from ctypes import wintypes

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.bloom import BloomGroup, BloomItem, item_from_path, load_groups, open_item, save_groups
from ..core.config import Config
from .bloom import COLS, GAP, HEADER, PAD, TILE, ItemTile
from .theme import Palette
from .window_base import LotusWindow

log = logging.getLogger("lotus.desktop")

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
u.SetWindowLongW.restype = ctypes.c_long
u.IsIconic.argtypes = [wintypes.HWND]
u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
u.GetWindow.restype = wintypes.HWND

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_BOTTOM = wintypes.HWND(1)
HWND_TOPMOST = wintypes.HWND(-1)
GW_HWNDPREV = 3
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

DRAG_ZONE = 58


class DesktopBubble(LotusWindow):
    moved = Signal(str, int, int)
    data_changed = Signal()

    def __init__(self, group: BloomGroup, pal: Palette, front: bool = False, max_items: int = 16) -> None:
        super().__init__(pal, radius=14)
        self.group = group
        self.front = front
        self.max_items = max(1, int(max_items))
        self._press: QPoint | None = None
        self._dragging = False
        self.layer = None
        self.setAcceptDrops(True)

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._build()
        self._resize_to_content()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        root = self.content_layout
        root.setContentsMargins(PAD, 10, PAD, PAD)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.name_label = QLabel(self.group.name)
        self.name_label.setStyleSheet(
            f"color: {self.pal.text.name()}; font-size: 13px; font-weight: 600; background: transparent;"
        )
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            f"color: {self.pal.subtext.name()}; font-size: 10px; background: transparent;"
        )
        header.addWidget(self.name_label)
        header.addStretch(1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GAP)
        root.addWidget(self.container)

        self._tiles: list[ItemTile] = []
        self._rebuild()

    def _rebuild(self) -> None:
        for tile in self._tiles:
            tile.setParent(None)
            tile.deleteLater()
        self._tiles.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for index, item in enumerate(self.group.items[: self._limit()]):
            tile = ItemTile(item, index, self.group.id, self.pal, self.container)
            tile.activated.connect(self._open_item)
            tile.context_requested.connect(self._item_menu)
            self.grid.addWidget(tile, index // self._cols(), index % self._cols())
            self._tiles.append(tile)
        self.count_label.setText(f"{len(self.group.items)} 项")
        self._resize_to_content()

    def _cols(self) -> int:
        return max(1, min(6, int(self.group.cols or COLS)))

    def _limit(self) -> int:
        rows = int(self.group.rows or 0)
        if rows > 0:
            return self._cols() * rows
        return self.max_items

    def _rows(self) -> int:
        shown = min(len(self.group.items), self._limit())
        cols = self._cols()
        return max(1, (shown + cols - 1) // cols)

    def _resize_to_content(self) -> None:
        cols = self._cols()
        width = cols * TILE + (cols - 1) * GAP + 2 * PAD
        height = 10 + 24 + 6 + self._rows() * TILE + (self._rows() - 1) * GAP + PAD
        self.setFixedSize(width, height)
        self._recompose_glass()

    # -- behaviour ---------------------------------------------------------
    def _open_item(self, _group_id: str, index: int) -> None:
        if 0 <= index < len(self.group.items):
            open_item(self.group.items[index])

    def _item_menu(self, _group_id: str, index: int, pos: QPoint) -> None:
        if not (0 <= index < len(self.group.items)):
            return
        item = self.group.items[index]
        menu = QMenu(self)
        menu.addAction("打开", lambda: open_item(item))
        menu.addSeparator()
        menu.addAction("从分组移除", lambda: self._remove(index))
        menu.exec(pos)

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self.group.items):
            self.group.items.pop(index)
            self._rebuild()
            self.data_changed.emit()

    def _header_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("添加文件…", self._add_files)
        menu.addAction("重命名…", self._rename)

        size_menu = menu.addMenu("收纳盒大小")
        for label, cols in (("紧凑（2 列）", 2), ("标准（3 列）", 3), ("宽（4 列）", 4)):
            size_menu.addAction(label, lambda _checked=False, c=cols: self._set_cols(c))
        size_menu.addSeparator()
        size_menu.addAction("自定义（列 × 行）…", self._custom_size)

        menu.addSeparator()
        menu.addAction("新建收纳盒", lambda: self._create_group())
        menu.addAction("删除此收纳盒", self._delete)
        menu.exec(pos)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加文件到收纳盒", str(pathlib.Path.home()))
        if not paths:
            return
        for raw in paths:
            self.group.items.append(item_from_path(pathlib.Path(raw)))
        self._rebuild()
        self.data_changed.emit()
        log.info("bubble %s: added %d files", self.group.name, len(paths))

    def _set_cols(self, cols: int) -> None:
        self.group.cols = max(1, min(6, int(cols)))
        self.group.rows = 0
        self._rebuild()
        self.data_changed.emit()

    def _custom_size(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("收纳盒大小")
        form = QVBoxLayout(dialog)
        form.setContentsMargins(18, 16, 18, 14)
        form.setSpacing(10)
        form.addWidget(QLabel(f"「{self.group.name}」的行列数"))
        row = QHBoxLayout()
        row.setSpacing(10)
        cols_spin = QSpinBox(dialog)
        cols_spin.setRange(1, 4)
        cols_spin.setValue(self._cols())
        cols_spin.setPrefix("列 ")
        rows_spin = QSpinBox(dialog)
        rows_spin.setRange(1, 6)
        rows_spin.setValue(int(self.group.rows or 2))
        rows_spin.setPrefix("行 ")
        row.addWidget(cols_spin)
        row.addWidget(rows_spin)
        form.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        confirm = QPushButton("确定")
        cancel.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        form.addLayout(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.group.cols = cols_spin.value()
            self.group.rows = rows_spin.value()
            self._rebuild()
            self.data_changed.emit()

    # -- drag & drop -------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [
            pathlib.Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if not paths:
            return
        for path in paths:
            if path.exists():
                self.group.items.append(item_from_path(path))
        self._rebuild()
        self.data_changed.emit()
        log.info("bubble %s: dropped %d items", self.group.name, len(paths))
        event.acceptProposedAction()

    def _create_group(self) -> None:
        if self.layer is not None:
            self.layer.create_group()

    def _rename(self) -> None:
        name, ok = QInputDialog.getText(self, "重命名分组", "名称", text=self.group.name)
        if ok and name.strip():
            self.group.name = name.strip()
            self.name_label.setText(self.group.name)
            self.data_changed.emit()

    def _delete(self) -> None:
        answer = QMessageBox.question(
            self,
            "删除收纳盒",
            f"确定删除「{self.group.name}」？里面的图标不会影响原文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self.layer is not None:
                self.layer.remove_group(self.group.id)
            else:
                self.close()

    # -- native bedding ----------------------------------------------------
    def _apply_native_style(self) -> None:
        hwnd = int(self.winId())
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        wanted = (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        if wanted != ex:
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, wanted)

    def bed_at_bottom(self) -> None:
        """Insert just above the desktop (Progman), below every normal window.

        ``HWND_BOTTOM`` sinks the window *below* the desktop shell on this
        build, which makes it invisible; inserting after whatever currently
        sits above Progman keeps us at the top of the desktop band instead.
        """
        hwnd = int(self.winId())
        self._apply_native_style()
        progman = int(u.FindWindowW("Progman", None))
        anchor = 0
        if progman:
            anchor = int(u.GetWindow(wintypes.HWND(progman), GW_HWNDPREV) or 0)
        insert_after = wintypes.HWND(anchor) if anchor and anchor != hwnd else HWND_BOTTOM
        u.SetWindowPos(
            hwnd, insert_after, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        top = int(u.GetWindow(wintypes.HWND(progman), GW_HWNDPREV) or 0) if progman else 0
        log.info(
            "bed: hwnd=%s anchor=%s top_of_desktop=%s ok=%s",
            hwnd, anchor, top, top == hwnd,
        )

    # -- events ------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.front:
            QTimer.singleShot(0, self.force_front)
        else:
            QTimer.singleShot(0, self.bed_at_bottom)

    def force_front(self) -> None:
        hwnd = int(self.winId())
        u.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        # Right click anywhere on the card opens the box menu (tiles have
        # their own item menu and do not reach here).
        self._header_menu(event.globalPos())
        event.accept()

    def is_minimized(self) -> bool:
        return bool(u.IsIconic(int(self.winId())))


class DesktopLayer(QObject):
    """Owns the bubble windows and keeps them bedded to the desktop band."""

    def __init__(self, cfg: Config, pal: Palette, front: bool = False) -> None:
        super().__init__()
        self.cfg = cfg
        self.pal = pal
        self.front = front
        self.groups: list[BloomGroup] = []
        self.bubbles: list[DesktopBubble] = []
        self._visible = True
        self._shift = 0
        self._anims: dict[str, QPropertyAnimation] = {}
        self._watch = QTimer(self)
        self._watch.setInterval(900)
        self._watch.timeout.connect(self._keep_on_desktop)

    # -- lifecycle ---------------------------------------------------------
    def _make_bubble(self, group: BloomGroup, index: int, screen) -> DesktopBubble:
        bubble = DesktopBubble(group, self.pal, front=self.front, max_items=int(self.cfg.get("bloom.max_items_per_bubble", 16)))
        bubble.layer = self
        bubble.data_changed.connect(self._on_changed)
        return bubble

    def create_group(self, name: str = "新收纳盒", items: list[BloomItem] | None = None) -> BloomGroup:
        group = BloomGroup(name=name, items=list(items or []))
        self.groups.append(group)
        save_groups(self.cfg, self.groups)
        self.rebuild()
        log.info("group created: %s (%d total)", group.name, len(self.groups))
        return group

    def remove_group(self, group_id: str) -> None:
        removed = [g for g in self.groups if g.id == group_id]
        self.groups = [g for g in self.groups if g.id != group_id]
        save_groups(self.cfg, self.groups)
        self.rebuild()
        if removed:
            log.info("group removed: %s (%d left)", removed[0].name, len(self.groups))

    def _dock(self, animate: bool = False) -> None:
        """Arrange the bubbles in one fixed column, offset by the shift."""
        if not self.bubbles:
            return
        screen = QApplication.primaryScreen().availableGeometry()
        side = str(self.cfg.get("bloom.dock", "right")).lower()
        margin = int(self.cfg.get("bloom.dock_margin", 24))
        gap = int(self.cfg.get("bloom.dock_gap", 12))
        y = screen.top() + margin
        for bubble in self.bubbles:
            width = bubble.width()
            if side == "left":
                x = screen.left() + margin + self._shift
            else:
                x = screen.right() - width - margin - self._shift
            self._move_bubble(bubble, x, y, animate)
            y += bubble.height() + gap

    def _move_bubble(self, bubble: DesktopBubble, x: int, y: int, animate: bool) -> None:
        target = QPoint(x, y)
        if not animate or bubble.pos() == target:
            bubble.move(target)
            return
        anim = QPropertyAnimation(bubble, b"pos", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(bubble.pos())
        anim.setEndValue(target)
        anim.start()
        self._anims[bubble.group.id] = anim

    def set_shift(self, shift: int, animate: bool = True) -> None:
        """Slide every bubble sideways (e.g. when the sidebar takes the edge)."""
        shift = max(0, int(shift))
        if shift == self._shift:
            return
        self._shift = shift
        self._dock(animate=animate)

    def reload_dock(self) -> None:
        """Re-read the dock side/margins and animate to the new layout."""
        self._dock(animate=True)

    def build(self) -> None:
        self.groups = load_groups(self.cfg)
        self._destroy()
        screen = QApplication.primaryScreen().availableGeometry()
        for group in self.groups:
            bubble = self._make_bubble(group, 0, screen)
            bubble.prepare_glass()
            bubble.show()
            self.bubbles.append(bubble)
        self._dock()
        self._watch.start()
        log.info("desktop layer built: %d bubbles (front=%s)", len(self.bubbles), self.front)

    def _destroy(self) -> None:
        for bubble in self.bubbles:
            bubble.close()
            bubble.deleteLater()
        self.bubbles.clear()

    def rebuild(self) -> None:
        self.groups = load_groups(self.cfg)
        for bubble in self.bubbles:
            bubble.close()
            bubble.deleteLater()
        self.bubbles.clear()
        screen = QApplication.primaryScreen().availableGeometry()
        for group in self.groups:
            bubble = self._make_bubble(group, 0, screen)
            bubble.prepare_glass()
            if self._visible:
                bubble.show()
            self.bubbles.append(bubble)
        self._dock()

    # -- visibility --------------------------------------------------------
    def is_visible(self) -> bool:
        return self._visible

    def show_all(self) -> None:
        self._visible = True
        self._dock()
        for bubble in self.bubbles:
            bubble.show()
            if self.front:
                bubble.force_front()
            else:
                bubble.bed_at_bottom()

    def hide_all(self) -> None:
        self._visible = False
        for bubble in self.bubbles:
            bubble.hide()

    def toggle(self) -> None:
        if self._visible:
            self.hide_all()
        else:
            self.show_all()

    # -- persistence -------------------------------------------------------
    def _on_changed(self) -> None:
        save_groups(self.cfg, self.groups)
        self._dock()

    # -- Win+D recovery ----------------------------------------------------
    def _keep_on_desktop(self) -> None:
        if not self._visible:
            return
        for bubble in self.bubbles:
            if not bubble.isVisible():
                bubble.show()
                if self.front:
                    bubble.force_front()
                else:
                    bubble.bed_at_bottom()
                log.info("bubble recovered after hide: %s", bubble.group.name)
            elif bubble.is_minimized():
                bubble.showNormal()
                if self.front:
                    bubble.force_front()
                else:
                    bubble.bed_at_bottom()
                log.info("bubble restored after minimize: %s", bubble.group.name)







