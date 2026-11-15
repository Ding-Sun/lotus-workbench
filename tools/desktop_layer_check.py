"""Desktop-layer check that must run at the user's normal integrity level.

Run it by double-clicking tools\\desktop_layer_check.bat (NOT through DSH: the
sandbox token is restricted and cannot talk to Explorer's windows).

It tries the two known routes, keeps a blue window on the desktop for a few
seconds, writes a report to .tmp/desktop_layer_report.txt, and always restores.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

u = ctypes.WinDLL("user32", use_last_error=True)
g = ctypes.WinDLL("gdi32", use_last_error=True)
k = ctypes.WinDLL("kernel32", use_last_error=True)

u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = wintypes.HWND
u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowExW.restype = wintypes.HWND
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND
u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
u.SetParent.restype = wintypes.HWND
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
u.SetWindowLongW.restype = ctypes.c_long
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
u.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
u.SendMessageTimeoutW.restype = wintypes.LPARAM
u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
u.GetWindow.restype = wintypes.HWND

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
GW_HWNDNEXT = 2

ROOT_TMP = ROOT / ".tmp"
REPORT = ROOT_TMP / "desktop_layer_report.txt"
_lines: list[str] = []


def log(message: str) -> None:
    print(f"[desktop] {message}", flush=True)
    _lines.append(message)


def cls(h: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(wintypes.HWND(h), b, 256)
    return b.value


def workers() -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if cls(int(h)) == "WorkerW":
            found.append(int(h))
        return True

    u.EnumWindows(cb, 0)
    return found


def has_defview(h: int) -> bool:
    return bool(u.FindWindowExW(wintypes.HWND(h), None, "SHELLDLL_DefView", None))


def target_workerw(progman: int) -> int:
    host = progman if has_defview(progman) else 0
    if not host:
        for h in workers():
            if has_defview(h):
                host = h
                break
    if host:
        nxt = u.GetWindow(wintypes.HWND(host), GW_HWNDNEXT)
        while nxt:
            if cls(int(nxt)) == "WorkerW":
                return int(nxt)
            nxt = u.GetWindow(nxt, GW_HWNDNEXT)
    candidates = [h for h in workers() if not has_defview(h)]
    return candidates[-1] if candidates else 0


class Probe(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._text = "LOTUS 桌面层测试\n如果普通窗口能盖住我、Win+D 能看到我，就说明挂载成功"

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#3B7DD8"))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Microsoft YaHei UI", 12))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._text)


def main() -> int:
    ROOT_TMP.mkdir(exist_ok=True)
    app = QApplication(sys.argv)

    progman = int(u.FindWindowW("Progman", None))
    log(f"Progman={progman}")
    log(f"WorkerW before={len(workers())}")

    res = ctypes.c_size_t(0)
    ok = u.SendMessageTimeoutW(wintypes.HWND(progman), 0x052C, 0, 0, 0, 2000, ctypes.byref(res))
    log(f"0x052C ok={ok} err={ctypes.get_last_error()}")
    time.sleep(0.6)
    log(f"WorkerW after={len(workers())}")

    win = Probe()
    win.setGeometry(150, 150, 560, 260)
    win.show()
    app.processEvents()
    hwnd = int(win.winId())

    target = target_workerw(progman)
    log(f"workerw target={target}")

    def mount(parent: int, label: str) -> bool:
        style = u.GetWindowLongW(hwnd, GWL_STYLE)
        u.SetWindowLongW(hwnd, GWL_STYLE, (style & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME)) | WS_CHILD)
        ctypes.set_last_error(0)
        u.SetParent(wintypes.HWND(hwnd), wintypes.HWND(parent))
        err = ctypes.get_last_error()
        u.SetWindowPos(hwnd, None, 150, 150, 560, 260,
                       SWP_FRAMECHANGED | SWP_SHOWWINDOW | SWP_NOZORDER | SWP_NOACTIVATE)
        parent_now = int(u.GetParent(hwnd) or 0)
        log(f"mount[{label}]: err={err} parent={parent_now} expected={parent} -> {'OK' if parent_now == parent else 'FAIL'}")
        return parent_now == parent

    mounted = mount(progman, "progman")
    if not mounted and target:
        mounted = mount(target, "workerw")
    if not mounted:
        log("both routes failed; window stays a normal top-level window")
    REPORT.write_text("\n".join(_lines), encoding="utf-8")

    def step_show() -> None:
        screen = app.primaryScreen()
        if screen:
            screen.grabWindow(0).save(str(ROOT_TMP / "desktop_layer_on.png"))
        log("screenshot desktop_layer_on.png")

    def step_cover() -> None:
        win.setWindowOpacity(1.0)
        screen = app.primaryScreen()
        if screen:
            screen.grabWindow(0).save(str(ROOT_TMP / "desktop_layer_after.png"))
        log("done; window will stay 3s more")
        QTimer.singleShot(3000, finish)

    def finish() -> None:
        try:
            u.SetParent(wintypes.HWND(hwnd), None)
            style = u.GetWindowLongW(hwnd, GWL_STYLE)
            u.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_CHILD) | WS_POPUP | WS_CAPTION)
        except Exception:  # noqa: BLE001
            pass
        win.hide()
        REPORT.write_text("\n".join(_lines), encoding="utf-8")
        log(f"report -> {REPORT}")
        app.quit()

    QTimer.singleShot(400, step_show)
    QTimer.singleShot(2500, step_cover)
    QTimer.singleShot(9000, finish)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
