"""Win+D survival test for bottom-pinned desktop widgets.

Shows two blue boxes:
  A = normal frameless window pinned to HWND_BOTTOM
  B = same + WS_EX_TOOLWINDOW / NOACTIVATE + Qt WindowStaysOnBottomHint
Both log every 500 ms whether they are minimized. Press Win+D while it runs;
after ~30 s the report says which one survived.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

u = ctypes.WinDLL("user32", use_last_error=True)
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
u.SetWindowLongW.restype = ctypes.c_long
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
u.IsIconic.argtypes = [wintypes.HWND]
u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

REPORT = ROOT / ".tmp" / "win_d_report.txt"
lines: list[str] = []


def log(text: str) -> None:
    print(f"[wind] {text}", flush=True)
    lines.append(text)


class Box(QWidget):
    def __init__(self, title: str, color: str, tool: bool) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if not tool:
            flags = Qt.WindowType.FramelessWindowHint
        super().__init__(None, flags)
        self.title = title
        self._color = QColor(color)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAcceptDrops(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), self._color)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Microsoft YaHei UI", 14))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.title)


def main() -> int:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    app = QApplication(sys.argv)

    normal = Box("A 普通窗口\nWin+D 后还在吗？", "#3B7DD8", tool=False)
    normal.setGeometry(160, 160, 420, 220)
    normal.show()

    tool = Box("B 工具窗口\nWin+D 后还在吗？", "#D8833B", tool=True)
    tool.setGeometry(620, 160, 420, 220)
    tool.show()

    app.processEvents()

    hwnd_n = int(normal.winId())
    hwnd_t = int(tool.winId())

    ex = u.GetWindowLongW(hwnd_t, GWL_EXSTYLE)
    u.SetWindowLongW(hwnd_t, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

    for hwnd in (hwnd_n, hwnd_t):
        u.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    log("two boxes shown; press Win+D now")

    state = {"n_min": False, "t_min": False, "n_seen": False, "t_seen": False}
    samples: list[str] = []

    def tick() -> None:
        n_min = bool(u.IsIconic(hwnd_n))
        t_min = bool(u.IsIconic(hwnd_t))
        if n_min != state["n_min"]:
            log(f"normal minimized={n_min}")
            state["n_min"] = n_min
            if n_min:
                state["n_seen"] = True
        if t_min != state["t_min"]:
            log(f"tool minimized={t_min}")
            state["t_min"] = t_min
            if t_min:
                state["t_seen"] = True
        samples.append(f"{n_min},{t_min}")

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(500)

    def finish() -> None:
        timer.stop()
        log(f"final normal_min={state['n_min']} tool_min={state['t_min']}")
        log(f"ever minimized: normal={state['n_seen']} tool={state['t_seen']}")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        normal.close()
        tool.close()
        app.quit()

    QTimer.singleShot(30_000, finish)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
