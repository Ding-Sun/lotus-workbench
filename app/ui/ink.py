"""Ink — quick capture editor and the note manager."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.notes import Note, NotesStore, humanize
from .rows import KeyboardList
from .theme import Palette
from .window_base import LotusWindow

log = logging.getLogger("lotus.ink")


class _BodyEdit(QPlainTextEdit):
    escape_pressed = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def _primary_button(pal: Palette, text: str) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedHeight(30)
    button.setStyleSheet(
        f"QPushButton {{ color: #ffffff; background: {pal.accent.name()};"
        " border: none; border-radius: 7px; font-size: 12px; padding: 0 14px; }"
        f"QPushButton:hover {{ background: {pal.accent.lighter(115).name()}; }}"
    )
    return button


def _ghost_button(pal: Palette, text: str) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedHeight(30)
    button.setStyleSheet(
        f"QPushButton {{ color: {pal.text.name()}; background: transparent;"
        f" border: 1px solid {pal.border.name()}; border-radius: 7px; font-size: 12px; padding: 0 14px; }}"
        f"QPushButton:hover {{ background: {pal.surface_hover.name()}; }}"
    )
    return button


class InkEditorWindow(LotusWindow):
    """One-shot capture window: open, type, Esc saves and hides."""

    def __init__(self, cfg: Config, palette: Palette, store: NotesStore) -> None:
        super().__init__(palette, radius=14)
        self.cfg = cfg
        self.store = store
        self._path = None
        self._saved_snapshot = ("", "")
        self.set_content_size(720, 430)
        self._build()

    # -- construction ------------------------------------------------------
    def _label(self, text: str, size: int, color: str, weight: int = 400) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-size: {size}px; font-weight: {weight}; background: transparent;"
        )
        return label

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {self.pal.border.name()}; border: none;")
        return line

    def _build(self) -> None:
        text_color = self.pal.text.name()
        sub_color = self.pal.subtext.name()

        root = self.content_layout
        root.setContentsMargins(34, 26, 34, 20)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.addWidget(self._label("速记", 15, text_color, 600))
        header.addStretch(1)
        header.addWidget(self._label("Esc 保存并收起 · Ctrl+S 仅保存", 11, sub_color))
        root.addLayout(header)

        root.addSpacing(14)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("标题（可留空）")
        self.title_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {text_color};"
            " font-size: 19px; font-weight: 600; padding: 2px 0; }"
            f"QLineEdit:focus {{ border: none; }}"
        )
        root.addWidget(self.title_edit)

        root.addSpacing(8)
        root.addWidget(self._divider())
        root.addSpacing(8)

        self.body_edit = _BodyEdit()
        self.body_edit.setPlaceholderText("写点什么…")
        self.body_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.body_edit.escape_pressed.connect(self._save_and_hide)
        self.body_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; border: none; color: {text_color};"
            " font-size: 14px; padding: 0;"
            f" selection-background-color: {self.pal.accent.name()}; }}"
        )
        root.addWidget(self.body_edit, 1)

        root.addSpacing(6)
        footer = QHBoxLayout()
        self.status = self._label("", 11, sub_color)
        footer.addWidget(self.status)
        footer.addStretch(1)
        self.counter = self._label("0 字", 11, sub_color)
        footer.addWidget(self.counter)
        root.addLayout(footer)

        self.body_edit.textChanged.connect(self._update_counter)

    # -- behaviour ---------------------------------------------------------
    def _update_counter(self) -> None:
        text = self.body_edit.toPlainText()
        self.counter.setText(f"{len(text.replace(' ', '').replace(chr(10), ''))} 字")

    def open_new(self) -> None:
        self._path = None
        self._saved_snapshot = ("", "")
        self.title_edit.clear()
        self.body_edit.clear()
        self.status.setText("")
        self.center_on_screen(self.screen_at_cursor())
        self.show_animated()
        self.body_edit.setFocus()

    def open_note(self, note: Note) -> None:
        self._path = note.path
        self.title_edit.setText(note.title)
        self.body_edit.setPlainText(note.body)
        self._saved_snapshot = (note.title, note.body)
        self.status.setText(f"编辑：{note.title}")
        self.center_on_screen(self.screen_at_cursor())
        self.show_animated()
        self.body_edit.setFocus()
        cursor = self.body_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.body_edit.setTextCursor(cursor)

    def save(self) -> Note | None:
        title = self.title_edit.text().strip()
        body = self.body_edit.toPlainText()
        if not title and body.strip():
            # No title typed: the first line becomes the title, like a memo.
            title = body.strip().splitlines()[0].lstrip("# ").strip()[:60]
        if self.store.is_empty(title, body):
            if self._path is None:
                return None
            # Editing an existing note that was cleared out: keep the file but
            # let the user delete it from the manager instead.
            return None

        note = self.store.save(title, body, self._path)
        self._path = note.path
        self._saved_snapshot = (note.title, note.body)
        self.status.setText(f"已保存 · {note.updated.strftime('%H:%M')}")
        return note

    def _save_and_hide(self) -> None:
        self.save()
        self.hide_animated()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self._save_and_hide()
            event.accept()
            return
        if event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save()
            event.accept()
            return
        super().keyPressEvent(event)


class NotesManagerWindow(LotusWindow):
    """Two-pane manager: search and pick on the left, edit on the right."""

    def __init__(self, cfg: Config, palette: Palette, store: NotesStore) -> None:
        super().__init__(palette, radius=14)
        self.cfg = cfg
        self.store = store
        self._notes: list[Note] = []
        self._current = None
        self._snapshot = ("", "")
        self.set_content_size(920, 600)
        self._build()
        self.store.changed.connect(self._on_store_changed, Qt.ConnectionType.QueuedConnection)

    # -- construction ------------------------------------------------------
    def _label(self, text: str, size: int, color: str, weight: int = 400) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-size: {size}px; font-weight: {weight}; background: transparent;"
        )
        return label

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {self.pal.border.name()}; border: none;")
        return line

    def _build(self) -> None:
        text_color = self.pal.text.name()
        sub_color = self.pal.subtext.name()

        root = self.content_layout
        root.setContentsMargins(30, 24, 30, 22)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.addWidget(self._label("笔记", 16, text_color, 600))
        header.addSpacing(10)
        self.count_label = self._label("", 11, sub_color)
        header.addWidget(self.count_label)
        header.addStretch(1)
        header.addWidget(self._label("Esc 关闭", 11, sub_color))
        root.addLayout(header)

        root.addSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(24)

        # -- left: search + list
        left_widget = QWidget()
        left_widget.setFixedWidth(300)
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题或正文…")
        self.search_edit.setStyleSheet(
            f"QLineEdit {{ background: {self.pal.surface.name()}; border: 1px solid {self.pal.border.name()};"
            f" border-radius: 8px; padding: 7px 10px; color: {text_color}; font-size: 12px; }}"
        )
        self.search_edit.textChanged.connect(self._reload)
        left.addWidget(self.search_edit)

        self.note_list = KeyboardList(self.pal)
        self.note_list.activated.connect(self._open_index)
        left.addWidget(self.note_list, 1)
        columns.addWidget(left_widget, 0)

        # -- right: editor
        right = QVBoxLayout()
        right.setSpacing(8)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("标题")
        self.title_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {text_color};"
            " font-size: 18px; font-weight: 600; padding: 2px 0; }"
        )
        right.addWidget(self.title_edit)
        right.addWidget(self._divider())

        self.body_edit = _BodyEdit()
        self.body_edit.setPlaceholderText("选择左侧笔记，或直接在下方输入新内容")
        self.body_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; border: none; color: {text_color};"
            f" font-size: 13px; selection-background-color: {self.pal.accent.name()}; }}"
        )
        self.body_edit.escape_pressed.connect(self._close)
        right.addWidget(self.body_edit, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.save_button = _primary_button(self.pal, "保存")
        self.save_button.clicked.connect(self._save_current)
        self.delete_button = _ghost_button(self.pal, "删除")
        self.delete_button.clicked.connect(self._delete_current)
        actions.addWidget(self.save_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        self.status = self._label("", 11, sub_color)
        actions.addWidget(self.status)
        right.addLayout(actions)

        columns.addLayout(right, 1)
        root.addLayout(columns, 1)

    # -- data --------------------------------------------------------------
    def _reload(self) -> None:
        query = self.search_edit.text()
        self._notes = self.store.search(query) if query else self.store.all()
        self.note_list.set_items(
            [(note.title, f"{humanize(note.updated)} · {note.preview}") for note in self._notes]
        )
        self.count_label.setText(f"{len(self._notes)} 篇")
        if self._current is not None:
            for index, note in enumerate(self._notes):
                if note.path == self._current:
                    self.note_list.select(index)
                    break

    def open_note(self, path=None) -> None:
        self._reload()
        self.center_on_screen(self.screen_at_cursor())
        self.show_animated()
        if path is not None:
            for index, note in enumerate(self._notes):
                if note.path == path:
                    self.note_list.select(index)
                    self._load(self._notes[index])
                    break
        elif self._current is None and self._notes:
            self.note_list.select(0)
            self._load(self._notes[0])
        self.note_list.setFocus()

    def _open_index(self, index: int) -> None:
        if 0 <= index < len(self._notes):
            self._save_if_dirty()
            self._load(self._notes[index])

    def _load(self, note: Note) -> None:
        self._current = note.path
        self.title_edit.setText(note.title)
        self.body_edit.setPlainText(note.body)
        self._snapshot = (note.title, note.body)
        self.status.setText(f"{humanize(note.updated)}")

    def _is_dirty(self) -> bool:
        return (self.title_edit.text().strip(), self.body_edit.toPlainText()) != self._snapshot

    def _save_if_dirty(self) -> None:
        if self._current is not None and self._is_dirty():
            self._save_current()

    def _save_current(self) -> None:
        title = self.title_edit.text().strip()
        body = self.body_edit.toPlainText()
        if not title and not body.strip():
            return
        note = self.store.save(title, body, self._current)
        self._current = note.path
        self._snapshot = (note.title, note.body)
        self.status.setText(f"已保存 · {note.updated.strftime('%H:%M')}")

    def _delete_current(self) -> None:
        if self._current is None or not self._current.exists():
            return
        answer = QMessageBox.question(
            self,
            "删除笔记",
            "确定删除这篇笔记？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        path = self._current
        if self.store.delete(path):
            self._current = None
            self.title_edit.clear()
            self.body_edit.clear()
            self._snapshot = ("", "")
            self.status.setText("已删除")

    def _on_store_changed(self) -> None:
        if self.isVisible():
            self._reload()

    # -- window ------------------------------------------------------------
    def _close(self) -> None:
        title = self.title_edit.text().strip()
        body = self.body_edit.toPlainText().strip()
        if (title or body) and self._is_dirty():
            self._save_current()
        self.hide_animated()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self._close()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._reload()

