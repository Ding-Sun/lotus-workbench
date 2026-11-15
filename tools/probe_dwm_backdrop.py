"""Probe 2: DWM backdrop on a NON-layered window (no WA_TranslucentBackground)."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]


def set_attr(hwnd: int, attr: int, value: int) -> bool:
    v = ctypes.c_int(value)
    return dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v)) == 0


class Probe(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.rect().adjusted(0, 12, 0, 0), int(Qt.AlignmentFlag.AlignHCenter), "dwm backdrop probe")


app = QApplication(sys.argv)
win = Probe()
win.setGeometry(160, 160, 520, 320)
win.show()
app.processEvents()
hwnd = int(win.winId())
print("hwnd", hwnd)
print("dark mode", set_attr(hwnd, 20, 1))
print("backdrop", set_attr(hwnd, 38, 3))


def capture() -> None:
    screen = app.primaryScreen()
    pm = screen.grabWindow(0, win.x(), win.y(), win.width(), win.height())
    pm.save(r"D:\Agent\DSH\DSHworkplace\Lotus Workbench\.tmp\acrylic_dwm.png")
    print("saved")
    app.quit()


QTimer.singleShot(900, capture)
sys.exit(app.exec())
