"""Render every settings page to PNG for a quick visual check."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.ui.settings import SettingsWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402

app = QApplication(sys.argv)
cfg = Config.load()
pal = apply_theme(app, cfg)
win = SettingsWindow(cfg, pal, icons_visible=True)
win.open_settings()

out = Path(__file__).resolve().parents[1] / ".tmp"
out.mkdir(exist_ok=True)
state = {"row": 0}


def shoot() -> None:
    row = state["row"]
    if row >= win.nav.count():
        app.quit()
        return
    win.nav.setCurrentRow(row)
    app.processEvents()
    QTimer.singleShot(
        250,
        lambda: (
            app.primaryScreen().grabWindow(
                0, win.x(), win.y(), win.width(), win.height()
            ).save(str(out / f"settings_page_{row}.png")),
            state.update(row=row + 1),
            QTimer.singleShot(200, shoot),
        ),
    )


QTimer.singleShot(600, shoot)
sys.exit(app.exec())
