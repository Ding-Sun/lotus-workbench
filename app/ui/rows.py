"""Keyboard-navigable list rows shared by Bloom / Petal / Seek.

Painting the row background ourselves (instead of stylesheets) keeps hover and
selection cheap: no relayout, one repaint of a 56 px strip.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .theme import Palette

ROW_HEIGHT = 54


class ListRow(QWidget):
    """One line: title + optional subtitle, with hover/selection states."""

    activated = Signal()
    hover_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        pal: Palette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pal = pal
        self._selected = False
        self._hover = False
        self.setFixedHeight(ROW_HEIGHT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(1)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {pal.text.name()}; font-size: 13px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setStyleSheet(
            f"color: {pal.subtext.name()}; font-size: 11px; background: transparent;"
        )
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)

    # -- state -------------------------------------------------------------
    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        if not (self._selected or self._hover):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0, 0, 0, 0)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)

        if self._selected:
            fill = QColor(self.pal.accent)
            fill.setAlpha(46 if self.pal.dark else 24)
            painter.fillPath(path, fill)
            border = QColor(self.pal.accent)
            border.setAlpha(105 if self.pal.dark else 72)
            painter.setPen(border)
            painter.drawPath(path)
        else:
            hover = QColor(255, 255, 255, 16) if self.pal.dark else QColor(0, 0, 0, 10)
            painter.fillPath(path, hover)

    # -- events ------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover = True
        self.update()
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover = False
        self.update()
        self.hover_changed.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)


class KeyboardList(QWidget):
    """Vertical list with arrows / Enter, mirroring Bloom's interaction model."""

    activated = Signal(int)
    selection_changed = Signal(int)

    def __init__(self, pal: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pal = pal
        self._rows: list[ListRow] = []
        self._index = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addStretch(1)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- content -----------------------------------------------------------
    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        self._clear()
        layout = self.layout()
        for index, (title, subtitle) in enumerate(items):
            row = ListRow(title, subtitle, pal=self.pal)
            row.activated.connect(lambda i=index: self._activate(i))
            layout.insertWidget(layout.count() - 1, row)
            self._rows.append(row)

        self._index = 0 if self._rows else -1
        self._sync_selection()

    def _clear(self) -> None:
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()
        layout.addStretch(1)

    def count(self) -> int:
        return len(self._rows)

    def rows(self) -> list[ListRow]:
        return list(self._rows)

    def current_index(self) -> int:
        return self._index

    # -- selection ---------------------------------------------------------
    def _activate(self, index: int) -> None:
        self.select(index)
        self.activated.emit(index)

    def select(self, index: int) -> None:
        if not self._rows:
            return
        index = max(0, min(index, len(self._rows) - 1))
        if index == self._index:
            self._sync_selection()
            return
        self._index = index
        self._sync_selection()
        self.selection_changed.emit(index)

    def clear_selection(self) -> None:
        self._index = -1
        self._sync_selection()

    def _sync_selection(self) -> None:
        for i, row in enumerate(self._rows):
            row.set_selected(i == self._index)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().focusInEvent(event)
        self._sync_selection()

    # -- keyboard ----------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            step = 1 if key == Qt.Key.Key_Down else -1
            self.select(self._index + step)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self.select(0)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self.select(len(self._rows) - 1)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if 0 <= self._index < len(self._rows):
                self._activate(self._index)
            event.accept()
            return
        super().keyPressEvent(event)
