"""Show / hide the Windows desktop icons.

Three strategies, tried in order; each one verifies the real visibility state
afterwards instead of assuming success:

1. Send ``WM_COMMAND / 0x7402`` ("View → Show desktop icons") to the icon view
   itself — this is what Explorer's own context menu does.
2. Same command to its parent (Progman / the WorkerW hosting the view).
3. Write ``HideIcons`` under Explorer\\Advanced and broadcast
   ``WM_SETTINGCHANGE`` so Explorer re-reads the shell state.

The registry fallback is last because it only takes effect reliably after the
broadcast; both are logged with return codes.
"""

from __future__ import annotations

import ctypes
import logging
import time
import winreg
from ctypes import wintypes

log = logging.getLogger("lotus.desktop_icons")

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = wintypes.HWND
u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowExW.restype = wintypes.HWND
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
u.SendMessageTimeoutW.restype = wintypes.LPARAM
u.SendNotifyMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.SendNotifyMessageW.restype = wintypes.BOOL

WM_COMMAND = 0x0111
WM_SETTINGCHANGE = 0x001A
CMD_TOGGLE_DESKTOP_ICONS = 0x7402
SMTO_ABORTIFHUNG = 0x0002
HWND_BROADCAST = wintypes.HWND(0xFFFF)

ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


def _desktop_icon_view() -> int:
    progman = int(u.FindWindowW("Progman", None))
    if progman:
        view = int(u.FindWindowExW(wintypes.HWND(progman), None, "SHELLDLL_DefView", None) or 0)
        if view:
            return view

    found = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _param):
        name = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, name, 64)
        if name.value == "WorkerW":
            view = int(u.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None) or 0)
            if view:
                found[0] = view
                return False
        return True

    u.EnumWindows(enum_proc, 0)
    return found[0]


def _icon_list(view: int) -> int:
    return int(u.FindWindowExW(wintypes.HWND(view), None, "SysListView32", "FolderView") or 0)


def icons_visible() -> bool | None:
    view = _desktop_icon_view()
    if not view:
        return None
    # Some builds hide the inner list instead of the view itself.
    item_list = _icon_list(view)
    return bool(u.IsWindowVisible(item_list or view))


def _send_command(hwnd: int, label: str) -> bool:
    if not hwnd:
        return False
    result = ctypes.c_size_t(0)
    before = icons_visible()
    u.SendMessageTimeoutW(
        wintypes.HWND(hwnd), WM_COMMAND, CMD_TOGGLE_DESKTOP_ICONS, 0,
        SMTO_ABORTIFHUNG, 1200, ctypes.byref(result),
    )
    err = ctypes.get_last_error()
    time.sleep(0.15)
    after = icons_visible()
    log.info("toggle via %s: before=%s after=%s err=%s", label, before, after, err)
    return before != after


def _registry_fallback(visible: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADVANCED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, 0 if visible else 1)
    except OSError as exc:
        log.warning("registry HideIcons failed: %s", exc)
        return False

    # Explorer re-reads shell state on WM_SETTINGCHANGE; send both the string
    # and a bare notification, some builds only react to one of them.
    for lparam in ("ShellState", ""):
        buf = ctypes.create_unicode_buffer(lparam)
        u.SendNotifyMessageW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.cast(buf, ctypes.c_void_p).value or 0)
        time.sleep(0.1)
    time.sleep(0.2)

    now = icons_visible()
    log.info("registry HideIcons=%s -> visible=%s", not visible, now)
    return now == visible


def set_icons_visible(visible: bool) -> bool:
    view = _desktop_icon_view()
    if not view:
        log.warning("desktop icon view not found")
        return False

    current = icons_visible()
    if current == visible:
        return True

    parent = int(u.GetParent(wintypes.HWND(view)) or 0)

    if _send_command(view, "DefView") and icons_visible() == visible:
        return True
    if parent and _send_command(parent, "parent") and icons_visible() == visible:
        return True
    if _send_command(view, "DefView-retry") and icons_visible() == visible:
        return True

    if _registry_fallback(visible):
        return True

    log.warning("all desktop-icon strategies failed (view=%s parent=%s)", view, parent)
    return False
