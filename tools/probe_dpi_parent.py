"""Probe: does DPI awareness explain the SetParent(Progman) failure?

Creates a plain window after forcing Per-Monitor-V2 awareness (same as Explorer)
and retries parenting with explicit error resets.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
k = ctypes.WinDLL("kernel32", use_last_error=True)
g = ctypes.WinDLL("gdi32", use_last_error=True)

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


u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u.RegisterClassW.restype = ctypes.c_ushort
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
u.SetParent.restype = wintypes.HWND
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
u.SetWindowLongW.restype = ctypes.c_long
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
u.DefWindowProcW.restype = ctypes.c_ssize_t
u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000

# PER_MONITOR_AWARE_V2
try:
    ok = u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    print("SetProcessDpiAwarenessContext(-4) ->", ok)
except Exception as exc:  # noqa: BLE001
    print("dpi ctx error", exc)

prog = int(u.FindWindowW("Progman", None))
print("progman", prog)

proc = WNDPROC(lambda h, m, w, l: u.DefWindowProcW(h, m, w, l))
wc = WNDCLASSW()
wc.lpfnWndProc = proc
wc.hInstance = k.GetModuleHandleW(None)
wc.hbrBackground = g.CreateSolidBrush(0x00F68D4C)
wc.lpszClassName = "LotusDpiProbe"
print("register", u.RegisterClassW(ctypes.byref(wc)))

# Route 1: create directly as a child of Progman
ctypes.set_last_error(0)
child = u.CreateWindowExW(
    0, "LotusDpiProbe", "dpi-probe", WS_CHILD | WS_VISIBLE,
    80, 80, 400, 200, wintypes.HWND(prog), None, k.GetModuleHandleW(None), None,
)
print("CreateWindow(parent=Progman) ->", child, "err", ctypes.get_last_error())

# Route 2: popup then SetParent
hwnd = u.CreateWindowExW(
    0, "LotusDpiProbe", "dpi-probe2", WS_POPUP | WS_VISIBLE,
    80, 380, 400, 200, None, None, k.GetModuleHandleW(None), None,
)
print("popup ->", hwnd, "err", ctypes.get_last_error())
style = u.GetWindowLongW(hwnd, GWL_STYLE)
u.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
ctypes.set_last_error(0)
old = u.SetParent(wintypes.HWND(hwnd), wintypes.HWND(prog))
err = ctypes.get_last_error()
print("SetParent(Progman) -> old_parent", old, "err", err, "now parent", u.GetParent(hwnd))

time.sleep(1.0)
for h in (child, hwnd):
    if h:
        u.SetParent(wintypes.HWND(h), None)
        u.DestroyWindow(wintypes.HWND(h))
print("cleaned")
