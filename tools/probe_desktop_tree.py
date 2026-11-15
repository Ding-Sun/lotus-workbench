"""Dump the desktop window tree after asking Explorer to spawn a WorkerW."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
u.EnumWindows.restype = wintypes.BOOL
u.EnumChildWindows.restype = wintypes.BOOL
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
u.SendMessageTimeoutW.restype = wintypes.LPARAM


def cls(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, b, 256)
    return b.value


def title(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, b, 256)
    return b.value


def rect(h):
    r = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return f"{r.left},{r.top},{r.right},{r.bottom}"


def dump(h, depth=0, limit=[40]):
    if limit[0] <= 0:
        return
    limit[0] -= 1
    print("  " * depth + f"{h} {cls(h)} visible={bool(u.IsWindowVisible(h))} rect={rect(h)} title={title(h)[:24]!r}")
    children = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(child, _):
        children.append(int(child))
        return True

    u.EnumChildWindows(wintypes.HWND(h), cb, 0)
    for child in children:
        dump(child, depth + 1, limit)


prog = int(u.FindWindowW("Progman", None))
print("before:")
dump(prog, limit=[20])

res = ctypes.c_size_t(0)
ok = u.SendMessageTimeoutW(wintypes.HWND(prog), 0x052C, 0, 0, 0, 2000, ctypes.byref(res))
print(f"\nSendMessageTimeout ok={ok} err={ctypes.get_last_error()} result={res.value}")
time.sleep(0.8)

print("\nafter:")
dump(prog, limit=[40])

top = []

@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def top_cb(h, _):
    if cls(h) == "WorkerW":
        top.append(int(h))
    return True


u.EnumWindows(top_cb, 0)
print(f"\ntop-level WorkerW: {len(top)}")
for h in top[:20]:
    print("  ", h, "visible", bool(u.IsWindowVisible(h)), "rect", rect(h))
