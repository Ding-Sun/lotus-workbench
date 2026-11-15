"""Probe: does real acrylic show through a Qt translucent window?

Draws a window with a fully transparent client area and asks Windows for
acrylic (SetWindowCompositionAttribute) and DWM backdrop; screenshots each
variant so we can compare against the window behind it.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

u = ctypes.WinDLL("user32", use_last_error=True)
dwm = ctypes.WinDLL("dwmapi", use_last_error=True)


class ACCENT(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class DATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


u.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.POINTER(DATA)]
dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]


class Probe(QWidget):
    def __init__(self, label: str) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = label

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.rect().adjusted(0, 10, 0, 0), int(Qt.AlignmentFlag.AlignHCenter), self.label)


def acrylic(hwnd: int, alpha: int, color: int) -> bool:
    accent = ACCENT(4, 2, (alpha << 24) | color, 0)  # ACCENT_ENABLE_ACRYLICBLURBEHIND
    data = DATA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
    return bool(u.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data)))


def backdrop(hwnd: int) -> bool:
    value = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW
    return dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 38, ctypes.byref(value), ctypes.sizeof(value)) == 0


def main() -> int:
    app = QApplication(sys.argv)
    win = Probe("acrylic probe")
    win.setGeometry(120, 120, 520, 320)
    win.show()
    app.processEvents()
    hwnd = int(win.winId())
    print("hwnd", hwnd, "acrylic", acrylic(hwnd, 0x60, 0x1F3B3A))
    app.processEvents()

    shots = []

    def capture() -> None:
        screen = app.primaryScreen()
        pm = screen.grabWindow(0, win.x(), win.y(), win.width(), win.height())
        path = rf"D:\Agent\DSH\DSHworkplace\Lotus Workbench\.tmp\acrylic_{len(shots)}.png"
        pm.save(path)
        shots.append(path)
        print("saved", path)

    QTimer.singleShot(400, capture)
    QTimer.singleShot(900, lambda: (print("dwm backdrop", backdrop(hwnd)), capture()))
    QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
