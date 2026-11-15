"""Global hotkeys via the Win32 ``RegisterHotKey`` API.

Why not only the ``keyboard`` package? Low-level hooks can be flagged by
security software, need the app to stay responsive on every keypress, and
cannot report conflicts. ``RegisterHotKey`` is the OS-sanctioned route: it
fails loudly when a combination is taken, costs nothing while idle, and works
while Lotus has no focus.

``keyboard`` stays in the dependency list for later features that need to see
keys the OS will not reserve (e.g. double-tap modifiers).
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

log = logging.getLogger("lotus.hotkeys")

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}

_MODIFIER_ORDER = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))

_VK = {
    "space": 0x20,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "enter": 0x0D,
    "return": 0x0D,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "pause": 0x13,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "minus": 0xBD,
    "equals": 0xBB,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "backslash": 0xDC,
    "semicolon": 0xBA,
    "quote": 0xDE,
    "bracketleft": 0xDB,
    "bracketright": 0xDD,
    "grave": 0xC0,
    "backtick": 0xC0,
    "`": 0xC0,
}


class HotkeyError(ValueError):
    """Raised when a hotkey string cannot be parsed."""


def parse_hotkey(text: str) -> tuple[int, int]:
    """``"Ctrl+Alt+B"`` -> ``(MOD_CONTROL | MOD_ALT, VK_B)``."""
    raw = (text or "").strip()
    if not raw:
        raise HotkeyError("热键为空")

    parts = [p.strip() for p in raw.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise HotkeyError(f"无法识别的热键：{text!r}")

    mods = 0
    key_token = parts[-1]
    for token in parts[:-1]:
        modifier = _MODIFIERS.get(token.lower())
        if modifier is None:
            raise HotkeyError(f"未知的修饰键：{token}")
        mods |= modifier

    key = key_token.lower()
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _VK:
        vk = _VK[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif len(key) == 1 and 0x20 <= ord(key) <= 0x7E:
        vk = ord(key.upper())
    else:
        raise HotkeyError(f"无法识别的按键：{key_token}")

    is_function_key = 0x70 <= vk <= 0x87
    if mods == 0 and not is_function_key:
        raise HotkeyError("至少需要一个修饰键（Ctrl / Alt / Shift / Win）")

    return mods, vk


def format_hotkey(text: str) -> str:
    """Canonical display form: ``ctrl+alt+b`` -> ``Ctrl+Alt+B``."""
    try:
        mods, vk = parse_hotkey(text)
    except HotkeyError:
        return text
    tokens = [label for label, flag in _MODIFIER_ORDER if mods & flag]
    tokens.append(_vk_label(vk))
    return "+".join(tokens)


def _vk_label(vk: int) -> str:
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x70 + 1}"
    for name, code in _VK.items():
        if code == vk and name.isascii() and len(name) > 1:
            return name.capitalize()
    return f"VK({vk:#04x})"


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "HotkeyManager") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt override
        if event_type in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._owner._dispatch(int(msg.wParam))
                return True, 0
        return False, 0


class HotkeyManager(QObject):
    """Registers system-wide hotkeys and re-emits them as Qt signals."""

    triggered = Signal(str)

    def __init__(self, app: QApplication, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._ids: dict[str, int] = {}
        self._next_id = 0xB000
        self._callbacks: dict[str, Callable[[], None]] = {}

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL

        self._filter = _NativeFilter(self)
        app.installNativeEventFilter(self._filter)

    # -- public API --------------------------------------------------------
    def register(self, name: str, hotkey: str, callback: Callable[[], None] | None = None) -> tuple[bool, str]:
        """Register ``hotkey``. Returns ``(ok, human readable message)``."""
        self.unregister(name)
        try:
            mods, vk = parse_hotkey(hotkey)
        except HotkeyError as exc:
            return False, str(exc)

        hotkey_id = self._next_id
        self._next_id += 1
        if not self._user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
            error = ctypes.get_last_error()
            if error == ERROR_HOTKEY_ALREADY_REGISTERED:
                return False, f"{format_hotkey(hotkey)} 已被其他程序或系统占用"
            return False, f"{format_hotkey(hotkey)} 注册失败（错误 {error}）"

        self._ids[name] = hotkey_id
        if callback is not None:
            self._callbacks[name] = callback
        log.info("hotkey %s = %s (id=%#x)", name, format_hotkey(hotkey), hotkey_id)
        return True, format_hotkey(hotkey)

    def unregister(self, name: str) -> None:
        hotkey_id = self._ids.pop(name, None)
        self._callbacks.pop(name, None)
        if hotkey_id is not None:
            self._user32.UnregisterHotKey(None, hotkey_id)

    def reload(self, name: str, hotkey: str, callback: Callable[[], None] | None = None) -> tuple[bool, str]:
        """Re-register one hotkey after the user edits it."""
        self.unregister(name)
        return self.register(name, hotkey, callback)

    def unregister_all(self) -> None:
        for name in list(self._ids):
            self.unregister(name)

    def registered(self) -> dict[str, int]:
        return dict(self._ids)

    # -- internals ---------------------------------------------------------
    def _dispatch(self, hotkey_id: int) -> None:
        for name, registered_id in self._ids.items():
            if registered_id == hotkey_id:
                callback = self._callbacks.get(name)
                if callback is not None:
                    try:
                        callback()
                    except Exception:  # noqa: BLE001 - never let a handler kill the hook
                        log.exception("hotkey handler failed: %s", name)
                self.triggered.emit(name)
                return
