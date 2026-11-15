"""Windows 11 DWM backdrop helpers.

Qt-painted windows do not get the system acrylic automatically, so we ask the
compositor for a transient (acrylic) backdrop. Everything here degrades to a
plain painted card when the OS or the API does not cooperate.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger("lotus.dwm")

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_WINDOW_CORNER_PREFERENCE = 33

DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2  # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4

DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

_MIN_BUILD_ACRYLIC = 22621  # Windows 11 22H2


def windows_build() -> int:
    try:
        return sys.getwindowsversion().build
    except Exception:  # noqa: BLE001
        return 0


def _dwmapi() -> ctypes.WinDLL:
    return ctypes.WinDLL("dwmapi", use_last_error=True)


def _set_attribute(hwnd: int, attribute: int, value: int) -> int:
    api = _dwmapi()
    data = ctypes.c_int(value)
    return api.DwmSetWindowAttribute(
        wintypes.HWND(hwnd), ctypes.c_uint(attribute), ctypes.byref(data), ctypes.sizeof(data)
    )


def set_dark_mode(hwnd: int, enabled: bool) -> bool:
    """Tell DWM this window is dark so acrylic is tinted dark, not light."""
    value = 1 if enabled else 0
    try:
        if _set_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, value) == 0:
            return True
        # Windows 10 1809-1909 used attribute 19.
        return _set_attribute(hwnd, 19, value) == 0
    except OSError:
        return False


def enable_acrylic(hwnd: int) -> tuple[bool, str]:
    """Ask DWM for an acrylic backdrop behind ``hwnd``."""
    build = windows_build()
    if build < _MIN_BUILD_ACRYLIC:
        return False, f"系统版本 {build} 不支持系统亚克力"
    try:
        result = _set_attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW)
    except OSError as exc:
        return False, f"DWM 调用失败：{exc}"
    if result != 0:
        return False, f"DWM 拒绝亚克力（HRESULT {result:#x}）"
    return True, f"acrylic (build {build})"


def set_round_corners(hwnd: int, *, small: bool = False) -> bool:
    """Prefer DWM-drawn rounded corners (only affects window shadows/edges)."""
    try:
        result = _set_attribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            DWMWCP_ROUNDSMALL if small else DWMWCP_ROUND,
        )
    except OSError:
        return False
    return result == 0


def set_round_region(hwnd: int, width: int, height: int, radius: int) -> bool:
    """Clip the whole window (content *and* DWM backdrop) to a rounded rect.

    Needed because the acrylic backdrop is painted over the entire window
    rectangle, so a merely alpha-transparent corner would still show a square
    backdrop patch.
    """
    try:
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2)
        if not region:
            return False
        # SetWindowRgn takes ownership of the region; do not delete it.
        return bool(user32.SetWindowRgn(wintypes.HWND(hwnd), region, True))
    except OSError:
        return False
