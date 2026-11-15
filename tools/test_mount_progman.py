"""Route B probe: parent a window directly to Progman (desktop) and verify.

0x052C no longer spawns a WorkerW on this build (26200), so the classic
"behind icons WorkerW" route is unavailable. This checks whether Progman
itself can host a child window, structurally only (no screenshots).
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = ctypes.c_ushort
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

_proc_ref = None


def log(text: str) -> None:
    print(f"[routeB] {text}", flush=True)


def run() -> int:
    progman = int(user32.FindWindowW("Progman", None))
    log(f"progman={progman}")
    if not progman:
        return 1

    hinstance = kernel32.GetModuleHandleW(None)
    wndproc = WNDPROC(
        lambda h, msg, wp, lp: user32.DefWindowProcW(h, msg, wp, lp)
    )
    global _proc_ref
    _proc_ref = wndproc

    wc = WNDCLASSW()
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinstance
    wc.lpszClassName = "LotusMountProbe"
    wc.hbrBackground = gdi32.CreateSolidBrush(0x00F68D4C)  # COLORREF BGR
    atom = user32.RegisterClassW(ctypes.byref(wc))
    log(f"RegisterClass atom={atom} err={ctypes.get_last_error()}")

    hwnd = user32.CreateWindowExW(
        0, "LotusMountProbe", "LotusProbe", WS_POPUP,
        100, 100, 600, 300, None, None, hinstance, None,
    )
    log(f"CreateWindow hwnd={hwnd} err={ctypes.get_last_error()}")
    if not hwnd:
        return 1

    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
    old_parent = user32.SetParent(hwnd, wintypes.HWND(progman))
    log(f"SetParent returned old_parent={old_parent} err={ctypes.get_last_error()}")
    user32.SetWindowPos(
        hwnd, None, 100, 100, 600, 300,
        SWP_FRAMECHANGED | SWP_SHOWWINDOW | SWP_NOZORDER | SWP_NOACTIVATE,
    )
    user32.ShowWindow(hwnd, 5)  # SW_SHOW

    parent = user32.GetParent(hwnd)
    visible = bool(user32.IsWindowVisible(hwnd))
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    log(f"parent={parent} (progman={progman}) visible={visible}")
    log(f"rect={rect.left},{rect.top},{rect.right},{rect.bottom}")
    log(f"style={user32.GetWindowLongW(hwnd, GWL_STYLE):#010x}")

    # Put it behind the icon list inside Progman if possible.
    defview = user32.FindWindowExW(wintypes.HWND(progman), None, "SHELLDLL_DefView", None)
    log(f"defview={defview}")

    result = 0 if parent == progman and visible else 2
    log(f"progman mount result={'OK' if result == 0 else 'FAIL'}")
    user32.DestroyWindow(hwnd)
    return result


if __name__ == "__main__":
    sys.exit(run())
