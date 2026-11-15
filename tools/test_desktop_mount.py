"""Minimal desktop-layer mount experiment.

Puts one solid-colour Qt window into the desktop's WorkerW layer, checks that a
normal window covers it, saves screenshots, then always unmounts.

Run:  .venv\\Scripts\\python.exe tools\\test_desktop_mount.py
It never touches desktop icons or the user's windows.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.EnumWindows.restype = wintypes.BOOL

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
WM_SPAWN_WORKER = 0x052C

_shots = ROOT / ".tmp"
_log: list[str] = []


def log(message: str) -> None:
    line = f"[mount] {message}"
    print(line, flush=True)
    _log.append(line)


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


def has_defview(hwnd: int) -> bool:
    return bool(user32.FindWindowExW(wintypes.HWND(hwnd), None, "SHELLDLL_DefView", None))


def workerw_list() -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _param):
        if class_name(hwnd) == "WorkerW":
            found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc, 0)
    return found


def spawn_workerw() -> None:
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(
        wintypes.HWND(user32.FindWindowW("Progman", None)),
        WM_SPAWN_WORKER,
        0,
        0,
        0,
        1000,
        ctypes.byref(result),
    )


def pick_target() -> int:
    """WorkerW that sits directly behind the icon layer."""
    progman = user32.FindWindowW("Progman", None)
    host = progman if has_defview(progman) else None
    if host is None:
        for hwnd in workerw_list():
            if has_defview(hwnd):
                host = hwnd
                break

    if host is not None:
        nxt = user32.GetWindow(wintypes.HWND(host), GW_HWNDNEXT)
        while nxt:
            if class_name(nxt) == "WorkerW":
                return int(nxt)
            nxt = user32.GetWindow(wintypes.HWND(nxt), GW_HWNDNEXT)

    candidates = [hwnd for hwnd in workerw_list() if not has_defview(hwnd)]
    return int(candidates[-1]) if candidates else 0


class SolidWindow(QWidget):
    def __init__(self, text: str, color: QColor) -> None:
        super().__init__()
        self._text = text
        self._color = color
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.setPen(QColor("#111111"))
        font = QFont("Microsoft YaHei UI", 16)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


def grab(name: str) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    pixmap = screen.grabWindow(0)
    path = _shots / name
    pixmap.save(str(path))
    log(f"screenshot -> {path.name}")


def main() -> int:
    app = QApplication(sys.argv)
    screen = app.primaryScreen()
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    log(f"screen={geo.width()}x{geo.height()} dpr={dpr}")

    before = workerw_list()
    log(f"WorkerW before={len(before)}")
    spawn_workerw()
    time.sleep(0.6)
    after = workerw_list()
    log(f"WorkerW after={len(after)}")

    target = pick_target()
    log(f"target WorkerW={target} class={class_name(target) if target else '-'}")
    if not target:
        log("no WorkerW found; aborting")
        return 1

    demo = SolidWindow("LOTUS · 桌面层测试", QColor("#4C8DF6"))
    demo.setGeometry(120, 120, 560, 320)
    demo.show()
    app.processEvents()

    hwnd = int(demo.winId())
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = (style & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME)) | WS_CHILD
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    user32.SetParent(hwnd, wintypes.HWND(target))
    user32.SetWindowPos(
        hwnd, None, 120, 120, int(560 * dpr), int(320 * dpr),
        SWP_FRAMECHANGED | SWP_SHOWWINDOW | SWP_NOZORDER | SWP_NOACTIVATE,
    )
    app.processEvents()
    log(f"parent after mount={int(user32.GetParent(hwnd) or 0)}")

    state = {"cover": None, "mounted": True}

    def unmount() -> None:
        if not state["mounted"]:
            return
        state["mounted"] = False
        log("unmounting")
        user32.SetParent(hwnd, None)
        style2 = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style2 = (style2 & ~WS_CHILD) | WS_POPUP | WS_CAPTION
        user32.SetWindowLongW(hwnd, GWL_STYLE, style2)
        demo.hide()
        app.processEvents()
        log(f"parent after unmount={int(user32.GetParent(hwnd) or 0)}")

    def step1() -> None:
        grab("mount_1_desktop.png")
        # A normal top-level window must cover the mounted one.
        cover = SolidWindow("普通窗口（应盖住蓝色块）", QColor("#F5F5F5"))
        cover.setGeometry(60, 60, 760, 480)
        cover.show()
        cover.raise_()
        state["cover"] = cover
        QTimer.singleShot(700, step2)

    def step2() -> None:
        grab("mount_2_covered.png")
        cover = state["cover"]
        if cover is not None:
            cover.close()
        QTimer.singleShot(500, step3)

    def step3() -> None:
        grab("mount_3_revealed.png")
        unmount()
        QTimer.singleShot(500, step4)

    def step4() -> None:
        grab("mount_4_unmounted.png")
        log("done")
        app.quit()

    QTimer.singleShot(500, step1)
    # Watchdog: never leave the desktop modified.
    QTimer.singleShot(25_000, lambda: (unmount(), app.quit()))
    code = app.exec()
    unmount()
    (_shots / "mount_log.txt").write_text("\n".join(_log), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
