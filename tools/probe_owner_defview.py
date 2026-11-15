"""Probe DeskBox's trick: owner the window to SHELLDLL_DefView (not SetParent)."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = wintypes.HWND
u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowExW.restype = wintypes.HWND
u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

GWLP_HWNDPARENT = -8
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

prog = int(u.FindWindowW("Progman", None))
defview = int(u.FindWindowExW(wintypes.HWND(prog), None, "SHELLDLL_DefView", None))
print("progman", prog, "defview", defview)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
w = QWidget(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.setGeometry(300, 300, 420, 220)
w.show()
app.processEvents()

hwnd = int(w.winId())
print("hwnd", hwnd, "owner before", u.GetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_HWNDPARENT))

ctypes.set_last_error(0)
old = u.SetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_HWNDPARENT, defview)
err = ctypes.get_last_error()
now = u.GetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_HWNDPARENT)
print(f"SetWindowLongPtr(owner=defview): old={old} err={err} now={now} match={now == defview}")
print("GetParent", u.GetParent(wintypes.HWND(hwnd)))

u.SetWindowPos(wintypes.HWND(hwnd), HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
print("visible after bed", bool(u.IsWindowVisible(hwnd)))

QTimer.singleShot(1500, app.quit)
app.exec()
