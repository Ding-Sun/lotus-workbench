"""Dev check: exercise Bloom's keyboard model without showing the overlay.

Run with the venv python; it never calls show(), so nothing pops up on screen.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app.core.bloom import load_groups
from app.core.config import Config
from app.ui.bloom import BloomOverlay
from app.ui.theme import apply_theme


def press(overlay: BloomOverlay, key: Qt.Key, text: str = "", modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
    overlay.keyPressEvent(event)


def names(overlay: BloomOverlay) -> list[str]:
    return [item.name for item in overlay._display_items()]


def main() -> int:
    app = QApplication([])
    cfg = Config.load()
    pal = apply_theme(app, cfg)
    overlay = BloomOverlay(cfg, pal)
    overlay.setGeometry(0, 0, 1707, 1067)
    overlay._groups = load_groups(cfg)
    overlay._build_cards()
    overlay._position_cards()
    overlay.activate_group(0)

    assert names(overlay) == ["资源管理器", "记事本", "计算器", "画图"], names(overlay)

    press(overlay, Qt.Key.Key_unknown, "记")
    assert names(overlay) == ["记事本"], names(overlay)
    print("filter 记 ->", names(overlay))

    press(overlay, Qt.Key.Key_Escape)
    assert names(overlay) == ["资源管理器", "记事本", "计算器", "画图"]
    assert overlay._filter == ""
    print("esc cleared filter")

    press(overlay, Qt.Key.Key_Right)
    assert overlay._selected == 1, overlay._selected
    press(overlay, Qt.Key.Key_Down)
    assert overlay._selected == 3, overlay._selected
    print("arrows selected ->", overlay._selected)

    overlay.activate_group(1)
    press(overlay, Qt.Key.Key_G, "g", Qt.KeyboardModifier.AltModifier)
    print("alt+g selected ->", overlay._selected, names(overlay)[overlay._selected])
    assert names(overlay)[overlay._selected] == "GitHub"

    press(overlay, Qt.Key.Key_Tab)
    assert overlay._active == 2, overlay._active
    print("tab -> group", overlay._active)

    press(overlay, Qt.Key.Key_Tab, modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert overlay._active == 1, overlay._active
    print("shift+tab -> group", overlay._active)

    print("bloom keyboard model OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
