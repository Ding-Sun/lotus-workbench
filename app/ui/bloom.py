"""Bloom — the bubble-group launcher overlay.

A dimmed full-screen layer with draggable bubble cards. Keyboard first:
arrows move inside the active bubble, typing filters, digits launch, Alt+letter
jumps, Enter opens, Esc clears the filter or closes.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QFileInfo,
    QMimeData,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QScrollArea,
    QWidget,
)

from ..core.bloom import (
    BloomGroup,
    BloomItem,
    item_from_path,
    load_groups,
    open_item,
    resolve_target,
    save_groups,
)
from ..core.config import Config
from .theme import Palette

log = logging.getLogger("lotus.bloom")

TILE = 92
GAP = 8
COLS = 3
PAD = 14
HEADER = 44
COLLAPSED_W = 252
COLLAPSED_H = 112
EXPANDED_W = COLS * TILE + (COLS - 1) * GAP + 2 * PAD  # 320
MAX_ROWS = 3
MIME_ITEM = "application/x-lotus-item"

_icon_provider = QFileIconProvider()
_icon_cache: dict[str, QIcon] = {}


def _menu_exec(menu: QMenu, pos: QPoint, overlay: "BloomOverlay") -> None:
    overlay._modal += 1
    try:
        menu.exec(pos)
    finally:
        overlay._modal -= 1


def _letter_icon(text: str, pal: Palette) -> QPixmap:
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(pal.accent)
    color.setAlpha(56)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRect(4, 4, 88, 88), 20, 20)
    painter.setPen(QColor(pal.text))
    font = painter.font()
    font.setPointSize(38)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, (text or "?")[:1].upper())
    painter.end()
    return pixmap


def item_icon(item: BloomItem, pal: Palette) -> QIcon:
    key = f"{item.type}:{item.target}"
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    if item.type == "url" or item.target.lower().startswith(("http://", "https://")):
        icon = QIcon(_letter_icon(item.name or "?", pal))
    else:
        path = Path(resolve_target(item.target))
        if path.exists():
            icon = _icon_provider.icon(QFileInfo(str(path)))
        else:
            icon = _icon_provider.icon(QFileIconProvider.IconType.File)
    _icon_cache[key] = icon
    return icon


class ItemTile(QWidget):
    clicked = Signal(str, int)
    activated = Signal(str, int)
    context_requested = Signal(str, int, QPoint)

    def __init__(self, item: BloomItem, index: int, group_id: str, pal: Palette, parent: QWidget) -> None:
        super().__init__(parent)
        self.item = item
        self.index = index
        self.group_id = group_id
        self.pal = pal
        self._hover = False
        self._selected = False
        self._hover_t = 0.0
        self._press = None
        self._icon = item_icon(item, pal)
        self.setFixedSize(TILE, TILE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{item.name}\n{item.target}")
        self.setMouseTracking(True)

        # 100 ms hover fade, matching Untamed's FluentAnimation duration.
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(100)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_tick)

    def _on_hover_tick(self, value) -> None:
        self._hover_t = float(value)
        self.update()

    def _animate_hover(self, target: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)

        if self._selected:
            fill = QColor(self.pal.accent)
            fill.setAlpha(56)
            painter.setBrush(fill)
            pen = QColor(self.pal.accent)
            pen.setAlpha(160)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, 10, 10)
        elif self._hover_t > 0.01:
            base = 26 if self.pal.dark else 16
            fill = QColor(255, 255, 255) if self.pal.dark else QColor(0, 0, 0)
            fill.setAlpha(int(base * self._hover_t))
            painter.setBrush(fill)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 10, 10)

        # FluentAnimation lifts the content 2 px on hover.
        lift = int(round(2 * self._hover_t))
        pixmap = self._icon.pixmap(44, 44)
        painter.drawPixmap((TILE - pixmap.width()) // 2, 9 - lift, pixmap)

        painter.setPen(QColor(self.pal.text))
        font = painter.font()
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text = metrics.elidedText(self.item.name, Qt.TextElideMode.ElideRight, TILE - 12)
        painter.drawText(
            QRect(4, 58 - lift, TILE - 8, 28),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            text,
        )

    # -- events ------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover = True
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover = False
        self._animate_hover(0.0)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self.clicked.emit(self.group_id, self.index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._press).manhattanLength() < 12:
            return

        drag = QDrag(self)
        data = QMimeData()
        data.setData(
            MIME_ITEM,
            json.dumps({"group": self.group_id, "index": self.index}).encode("utf-8"),
        )
        drag.setMimeData(data)
        drag.setPixmap(self._icon.pixmap(40, 40))
        self._press = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.group_id, self.index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.context_requested.emit(self.group_id, self.index, event.globalPos())


class BubbleCard(QWidget):
    hovered = Signal(str)
    item_clicked = Signal(str, int)
    item_activated = Signal(str, int)
    item_menu = Signal(str, int, QPoint)
    header_menu = Signal(str, QPoint)
    files_dropped = Signal(str, list)
    item_moved = Signal(str, int, int)
    drag_finished = Signal(str, QPoint)

    def __init__(self, group: BloomGroup, pal: Palette, parent: QWidget) -> None:
        super().__init__(parent)
        self.group = group
        self.group_id = group.id
        self.pal = pal
        self._expanded = False
        self._active = False
        self._press = None
        self._dragging = False
        self._display_items: list[BloomItem] = list(group.items)
        self._tiles: list[ItemTile] = []
        self._anim: QPropertyAnimation | None = None

        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.name_label = QLabel(group.name, self)
        self.name_label.setStyleSheet(
            f"color: {pal.text.name()}; font-size: 14px; font-weight: 600; background: transparent;"
        )
        self.count_label = QLabel("", self)
        self.count_label.setStyleSheet(
            f"color: {pal.subtext.name()}; font-size: 11px; background: transparent;"
        )

        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        self.scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GAP)
        self.scroll.setWidget(self.container)
        self.scroll.hide()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self.set_items(group.items)

    # -- geometry ----------------------------------------------------------
    def rows(self) -> int:
        count = len(self._display_items)
        return max(1, min(MAX_ROWS, math.ceil(count / COLS)))

    def expanded_size(self) -> QSize:
        height = HEADER + PAD + self.rows() * TILE + (self.rows() - 1) * GAP + PAD
        return QSize(EXPANDED_W, height)

    def collapsed_size(self) -> QSize:
        return QSize(COLLAPSED_W, COLLAPSED_H)

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        size = self.expanded_size() if expanded else self.collapsed_size()
        center = self.geometry().center()
        target = QRect(QPoint(0, 0), size)
        target.moveCenter(center)
        target = self._clamp(target)

        if expanded:
            self.scroll.show()
            self.raise_()

        if animate:
            self._anim = QPropertyAnimation(self, b"geometry", self)
            self._anim.setDuration(170)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            self._anim.finished.connect(self._on_anim_finished)
            self._anim.start()
        else:
            self.setGeometry(target)
        self.update()

    def _on_anim_finished(self) -> None:
        if not self._expanded:
            self.scroll.hide()

    def _clamp(self, rect: QRect) -> QRect:
        parent = self.parentWidget()
        if parent is None:
            return rect
        margin = 16
        bounds = parent.rect().adjusted(margin, margin, -margin, -margin)
        x = min(max(rect.x(), bounds.left()), bounds.right() - rect.width())
        y = min(max(rect.y(), bounds.top()), bounds.bottom() - rect.height())
        return QRect(x, y, rect.width(), rect.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self.name_label.setGeometry(PAD, 12, self.width() - 2 * PAD - 60, 22)
        self.count_label.setGeometry(self.width() - PAD - 54, 15, 54, 18)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        inner_w = max(1, self.width() - 2 * PAD)
        inner_h = max(1, self.height() - HEADER - PAD)
        self.scroll.setGeometry(PAD, HEADER, inner_w, inner_h)

    # -- content -----------------------------------------------------------
    def set_items(self, items: list[BloomItem]) -> None:
        self._display_items = list(items)
        self._rebuild_tiles()
        self.count_label.setText(f"{len(items)} 项")
        if self._expanded:
            center = self.geometry().center()
            target = QRect(QPoint(0, 0), self.expanded_size())
            target.moveCenter(center)
            self.setGeometry(self._clamp(target))

    def display_items(self) -> list[BloomItem]:
        return list(self._display_items)

    def _rebuild_tiles(self) -> None:
        for tile in self._tiles:
            tile.deleteLater()
        self._tiles.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for index, item in enumerate(self._display_items):
            tile = ItemTile(item, index, self.group_id, self.pal, self.container)
            tile.clicked.connect(self.item_clicked.emit)
            tile.activated.connect(self.item_activated.emit)
            tile.context_requested.connect(self.item_menu.emit)
            self.grid.addWidget(tile, index // COLS, index % COLS)
            self._tiles.append(tile)
        self.container.setMinimumHeight(max(1, self.rows() * TILE + (self.rows() - 1) * GAP))
        self.update()

    def select(self, index: int) -> None:
        for i, tile in enumerate(self._tiles):
            tile.set_selected(i == index)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def set_name(self, name: str) -> None:
        self.group.name = name
        self.name_label.setText(name)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)

        fill = QColor(self.pal.surface)
        fill.setAlpha(238 if self._active else 224)
        painter.fillPath(path, fill)

        pen = QColor(self.pal.accent if self._active else self.pal.border)
        pen.setAlpha(170 if self._active else 255)
        painter.setPen(pen)
        painter.drawPath(path)

        if not self._expanded and self._display_items:
            x = PAD
            y = self.height() - 44
            for item in self._display_items[:4]:
                pixmap = item_icon(item, self.pal).pixmap(26, 26)
                painter.drawPixmap(x, y, pixmap)
                x += 32
            remaining = len(self._display_items) - 4
            if remaining > 0:
                painter.setPen(QColor(self.pal.subtext))
                font = painter.font()
                font.setPointSizeF(8.0)
                painter.setFont(font)
                painter.drawText(QRect(x - 2, y + 6, 60, 18), int(Qt.AlignmentFlag.AlignLeft), f"+{remaining}")

    # -- events ------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.hovered.emit(self.group_id)
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= HEADER:
            self._press = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        parent = self.parentWidget()
        if parent is None:
            return
        parent_pos = parent.mapFromGlobal(event.globalPosition().toPoint())
        target = parent_pos - self._press
        if not self._dragging:
            if (target - self.pos()).manhattanLength() < 8:
                return
            self._dragging = True
            self.raise_()
        self.move(target)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dragging:
            self._dragging = False
            self._press = None
            self.drag_finished.emit(self.group_id, self.pos())
        self._press = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.pos().y() <= HEADER:
            self.header_menu.emit(self.group_id, event.globalPos())
        else:
            event.ignore()

    # -- drag and drop -----------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(MIME_ITEM):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(MIME_ITEM):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        mime = event.mimeData()
        if mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.toLocalFile()]
            if paths:
                self.files_dropped.emit(self.group_id, paths)
            event.acceptProposedAction()
            return
        if mime.hasFormat(MIME_ITEM):
            try:
                payload = json.loads(bytes(mime.data(MIME_ITEM)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return
            if payload.get("group") != self.group_id:
                event.ignore()
                return
            target_index = len(self.group.items) - 1
            for tile in self._tiles:
                if tile.geometry().translated(self.container.pos()).contains(event.position().toPoint()):
                    target_index = tile.index
                    break
            self.item_moved.emit(self.group_id, int(payload.get("index", 0)), target_index)
            event.acceptProposedAction()


class BloomOverlay(QWidget):
    def __init__(self, cfg: Config, pal: Palette) -> None:
        super().__init__()
        self.cfg = cfg
        self.pal = pal
        self._groups: list[BloomGroup] = []
        self._cards: list[BubbleCard] = []
        self._active = -1
        self._selected = 0
        self._filter = ""
        self._fade: QPropertyAnimation | None = None
        self._modal = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self.filter_label = QLabel(self)
        self.filter_label.setStyleSheet(
            f"color: {pal.text.name()}; background: rgba(20,20,24,200); border-radius: 9px;"
            " padding: 4px 12px; font-size: 12px;"
        )
        self.filter_label.hide()

    # -- lifecycle ---------------------------------------------------------
    def is_shown(self) -> bool:
        return self.isVisible()

    def show_overlay(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        self.setGeometry(screen.geometry())
        log.info("bloom overlay: geometry=%s screen=%s", self.geometry(), screen.geometry())
        self._groups = load_groups(self.cfg)
        self._filter = ""
        self._selected = 0
        self._build_cards()
        self._position_cards()
        self.filter_label.hide()

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(140)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self.activate_group(0)

    def hide_overlay(self) -> None:
        self.hide()
        self._filter = ""
        self.filter_label.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide_overlay()
        else:
            self.show_overlay()

    # -- cards -------------------------------------------------------------
    def _build_cards(self) -> None:
        for card in self._cards:
            card.hide()
            card.deleteLater()
        self._cards.clear()
        for group in self._groups:
            card = BubbleCard(group, self.pal, self)
            card.hovered.connect(self.activate_group_by_id)
            card.item_clicked.connect(self._on_item_clicked)
            card.item_activated.connect(self._on_item_activated)
            card.item_menu.connect(self._on_item_menu)
            card.header_menu.connect(self._on_header_menu)
            card.files_dropped.connect(self._on_files_dropped)
            card.item_moved.connect(self._on_item_moved)
            card.drag_finished.connect(self._on_card_dragged)
            card.show()
            self._cards.append(card)

    def _grid_size(self) -> tuple[int, int]:
        cols = max(1, int(self.cfg.get("bloom.grid.cols", 3)))
        rows = max(1, int(self.cfg.get("bloom.grid.rows", 2)))
        return cols, rows

    def _cell_rect(self, col: int, row: int) -> QRect:
        cols, rows = self._grid_size()
        margin_x, margin_y = 80, 90
        width = max(1, self.width() - 2 * margin_x)
        height = max(1, self.height() - 2 * margin_y)
        cell_w = width // cols
        cell_h = height // rows
        return QRect(margin_x + col * cell_w, margin_y + row * cell_h, cell_w, cell_h)

    def _position_cards(self) -> None:
        for card in self._cards:
            group = card.group
            cell = self._cell_rect(group.col, group.row)
            size = card.collapsed_size()
            x = cell.center().x() - size.width() // 2
            y = cell.center().y() - size.height() // 2
            card.setGeometry(x, y, size.width(), size.height())

    def activate_group(self, index: int) -> None:
        if not self._cards:
            return
        index = max(0, min(index, len(self._cards) - 1))
        self._active = index
        self._selected = 0
        for i, card in enumerate(self._cards):
            card.set_active(i == index)
            card.set_expanded(i == index)
        self._apply_filter()
        self._cards[index].raise_()

    def activate_group_by_id(self, group_id: str) -> None:
        for index, card in enumerate(self._cards):
            if card.group_id == group_id:
                if index != self._active:
                    self.activate_group(index)
                return

    def _active_card(self) -> BubbleCard | None:
        if 0 <= self._active < len(self._cards):
            return self._cards[self._active]
        return None

    # -- filtering ---------------------------------------------------------
    def _apply_filter(self) -> None:
        card = self._active_card()
        if card is None:
            return
        query = self._filter.strip().lower()
        if query:
            items = [item for item in card.group.items if query in item.name.lower() or query in item.target.lower()]
        else:
            items = list(card.group.items)
        card.set_items(items)
        self._selected = min(self._selected, max(0, len(items) - 1))
        card.select(self._selected)

        if query:
            self.filter_label.setText(f"筛选：{self._filter}    Esc 清除")
            self.filter_label.adjustSize()
            self.filter_label.move((self.width() - self.filter_label.width()) // 2, 28)
            self.filter_label.show()
            self.filter_label.raise_()
        else:
            self.filter_label.hide()

    def _display_items(self) -> list[BloomItem]:
        card = self._active_card()
        return card.display_items() if card is not None else []

    # -- opening -----------------------------------------------------------
    def _launch(self, item: BloomItem) -> None:
        self.hide_overlay()
        QTimer.singleShot(90, lambda: open_item(item))

    def _on_item_clicked(self, group_id: str, index: int) -> None:
        self.activate_group_by_id(group_id)
        self._selected = index
        card = self._active_card()
        if card is not None:
            card.select(index)

    def _on_item_activated(self, group_id: str, index: int) -> None:
        items = self._display_items()
        if 0 <= index < len(items):
            self._launch(items[index])

    # -- menus -------------------------------------------------------------
    def _on_item_menu(self, group_id: str, index: int, pos: QPoint) -> None:
        card = next((c for c in self._cards if c.group_id == group_id), None)
        if card is None:
            return
        items = card.display_items()
        if not (0 <= index < len(items)):
            return
        item = items[index]

        menu = QMenu(self)
        menu.addAction("打开", lambda: self._launch(item))
        if item.target and Path(item.target).exists():
            menu.addAction("在资源管理器中定位", lambda: self._reveal(item.target))
        menu.addSeparator()
        menu.addAction("从分组移除", lambda: self._remove_item(group_id, item))
        _menu_exec(menu, pos, self)

    def _reveal(self, target: str) -> None:
        import subprocess

        try:
            subprocess.Popen(["explorer.exe", f"/select,{target}"])
        except OSError:
            log.warning("cannot reveal %s", target, exc_info=True)

    def _on_header_menu(self, group_id: str, pos: QPoint) -> None:
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        menu = QMenu(self)
        menu.addAction("重命名分组…", lambda: self._rename_group(group))
        menu.addAction("移除此分组", lambda: self._delete_group(group))
        _menu_exec(menu, pos, self)

    def _rename_group(self, group: BloomGroup) -> None:
        self._modal += 1
        try:
            name, ok = QInputDialog.getText(self, "重命名分组", "名称", text=group.name)
        finally:
            self._modal -= 1
        if ok and name.strip():
            group.name = name.strip()
            for card in self._cards:
                if card.group_id == group.id:
                    card.set_name(group.name)
            self._save()

    def _delete_group(self, group: BloomGroup) -> None:
        self._modal += 1
        try:
            answer = QMessageBox.question(
                self,
                "移除分组",
                f"确定移除「{group.name}」及其 {len(group.items)} 个条目？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        finally:
            self._modal -= 1
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._groups = [g for g in self._groups if g.id != group.id]
        self._save()
        self._build_cards()
        self._position_cards()
        if self._cards:
            self.activate_group(0)

    def _remove_item(self, group_id: str, item: BloomItem) -> None:
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        group.items = [existing for existing in group.items if existing is not item]
        self._save()
        self._refresh_card(group_id)

    # -- mutations ---------------------------------------------------------
    def _refresh_card(self, group_id: str) -> None:
        for card in self._cards:
            if card.group_id == group_id:
                card.set_items(list(card.group.items))
        self._apply_filter()

    def _on_files_dropped(self, group_id: str, paths: list[str]) -> None:
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None:
            return
        limit = int(self.cfg.get("bloom.max_items_per_bubble", 16))
        existing = {item.target.lower() for item in group.items}
        added = 0
        for path in paths:
            if len(group.items) >= limit:
                log.info("group %s reached item limit %s", group.name, limit)
                break
            if path.lower() in existing:
                continue
            group.items.append(item_from_path(path))
            existing.add(path.lower())
            added += 1
        if added:
            self._save()
            self._refresh_card(group_id)
            log.info("added %d items to %s", added, group.name)

    def _on_item_moved(self, group_id: str, source: int, target: int) -> None:
        group = next((g for g in self._groups if g.id == group_id), None)
        if group is None or not (0 <= source < len(group.items)):
            return
        target = max(0, min(target, len(group.items) - 1))
        if source == target:
            return
        item = group.items.pop(source)
        group.items.insert(target, item)
        self._save()
        self._refresh_card(group_id)

    def _on_card_dragged(self, group_id: str, pos: QPoint) -> None:
        group = next((g for g in self._groups if g.id == group_id), None)
        card = next((c for c in self._cards if c.group_id == group_id), None)
        if group is None or card is None:
            return
        center = card.geometry().center()
        cols, rows = self._grid_size()
        best = (0, 0)
        best_distance = None
        for row in range(rows):
            for col in range(cols):
                cell_center = self._cell_rect(col, row).center()
                distance = (cell_center - center).manhattanLength()
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best = (col, row)
        group.col, group.row = best
        self._save()
        self._position_cards()

    def _save(self) -> None:
        save_groups(self.cfg, self._groups)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 51))

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and not self._modal:
            # Clicking another app dismisses the launcher, like Spotlight.
            QTimer.singleShot(0, self._hide_if_inactive)
        return super().event(event)

    def _hide_if_inactive(self) -> None:
        if self.isVisible() and not self._modal:
            self.hide_overlay()

    # -- keyboard ----------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = int(event.key())
        modifiers = event.modifiers()
        items = self._display_items()
        key_esc = int(Qt.Key.Key_Escape)
        key_tab = int(Qt.Key.Key_Tab)
        key_backspace = int(Qt.Key.Key_Backspace)
        key_return = int(Qt.Key.Key_Return)
        key_enter = int(Qt.Key.Key_Enter)
        arrows = {
            int(Qt.Key.Key_Left): -1,
            int(Qt.Key.Key_Right): 1,
            int(Qt.Key.Key_Up): -COLS,
            int(Qt.Key.Key_Down): COLS,
        }

        if key == key_esc:
            if self._filter:
                self._filter = ""
                self._apply_filter()
            else:
                self.hide_overlay()
            event.accept()
            return

        if key == key_tab:
            if self._cards:
                step = -1 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1
                self.activate_group((self._active + step) % len(self._cards))
            event.accept()
            return

        if key in arrows:
            if items:
                self._selected = max(0, min(len(items) - 1, self._selected + arrows[key]))
                card = self._active_card()
                if card is not None:
                    card.select(self._selected)
            event.accept()
            return

        if key in (key_return, key_enter):
            if 0 <= self._selected < len(items):
                self._launch(items[self._selected])
            event.accept()
            return

        if key == key_backspace:
            if self._filter:
                self._filter = self._filter[:-1]
                self._apply_filter()
            event.accept()
            return

        digit_1 = int(Qt.Key.Key_1)
        digit_9 = int(Qt.Key.Key_9)
        if digit_1 <= key <= digit_9:
            index = key - digit_1
            if 0 <= index < len(items):
                self._launch(items[index])
            event.accept()
            return

        if modifiers & Qt.KeyboardModifier.AltModifier:
            text = event.text()
            if text:
                for index, item in enumerate(items):
                    if item.name.lower().startswith(text.lower()):
                        self._selected = index
                        card = self._active_card()
                        if card is not None:
                            card.select(index)
                        break
            event.accept()
            return

        if modifiers == Qt.KeyboardModifier.NoModifier and event.text() and event.text().isalpha():
            self._filter += event.text()
            self._apply_filter()
            event.accept()
            return

        super().keyPressEvent(event)

    # -- mouse -------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.childAt(event.position().toPoint()) is None:
            self.hide_overlay()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.childAt(event.pos()) is not None:
            event.ignore()
            return
        menu = QMenu(self)
        menu.addAction("新建分组…", self._create_group)
        _menu_exec(menu, event.globalPos(), self)

    def _create_group(self) -> None:
        self._modal += 1
        try:
            name, ok = QInputDialog.getText(self, "新建分组", "名称", text="新分组")
        finally:
            self._modal -= 1
        if not ok or not name.strip():
            return
        cols, rows = self._grid_size()
        used = {(group.col, group.row) for group in self._groups}
        slot = (0, 0)
        for row in range(rows):
            for col in range(cols):
                if (col, row) not in used:
                    slot = (col, row)
                    break
            else:
                continue
            break
        self._groups.append(BloomGroup(name=name.strip(), col=slot[0], row=slot[1]))
        self._save()
        self._build_cards()
        self._position_cards()
