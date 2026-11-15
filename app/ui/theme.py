"""Theme: system light/dark detection, accent colour, shared palette."""

from __future__ import annotations

import logging
import winreg
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication

from ..core.config import Config
from ..core.wallpaper import dominant_color
from . import materials

log = logging.getLogger("lotus.theme")

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_DWM = r"Software\Microsoft\Windows\DWM"


def _reg_dword(root: int, path: str, name: str) -> int | None:
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return int(value)
    except (OSError, ValueError):
        return None


def system_is_dark() -> bool:
    value = _reg_dword(winreg.HKEY_CURRENT_USER, _PERSONALIZE, "AppsUseLightTheme")
    if value is None:
        return True
    return value == 0


def system_accent() -> QColor:
    """Windows stores AccentColor as 0xAABBGGRR."""
    value = _reg_dword(winreg.HKEY_CURRENT_USER, _DWM, "AccentColor")
    if value is None:
        return QColor("#0078D4")
    red = value & 0xFF
    green = (value >> 8) & 0xFF
    blue = (value >> 16) & 0xFF
    return QColor(red, green, blue)


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: QColor
    surface: QColor
    surface_hover: QColor
    text: QColor
    subtext: QColor
    border: QColor
    accent: QColor

    def rgba(self, color: QColor, alpha: int) -> QColor:
        out = QColor(color)
        out.setAlpha(alpha)
        return out

    @property
    def accent_text(self) -> QColor:
        """Accent colour adjusted for legibility on the card surface."""
        color = QColor(self.accent)
        return color.lighter(175) if self.dark else color.darker(120)


def build_palette(cfg: Config) -> Palette:
    mode = str(cfg.get("theme.mode", "system")).lower()
    dark = system_is_dark() if mode not in ("light", "dark") else mode == "dark"

    accent_setting = str(cfg.get("theme.accent", "auto"))
    if accent_setting == "wallpaper":
        accent = dominant_color() or system_accent()
    elif accent_setting == "auto":
        accent = system_accent()
    else:
        accent = QColor(accent_setting)
    if not accent.isValid():
        accent = system_accent()

    # Material preset supplies the tint; opacity is its strength (0-100).
    preset = materials.by_name(str(cfg.get("theme.material", materials.DEFAULT_MATERIAL)))
    tint = QColor(str(cfg.get("theme.tint_color", preset.color)))
    if not tint.isValid():
        tint = QColor(preset.color)

    if dark:
        return Palette(
            dark=True,
            bg=tint,
            surface=tint.lighter(118),
            surface_hover=tint.lighter(132),
            text=QColor(242, 243, 245),
            subtext=QColor(176, 180, 188),
            border=QColor(255, 255, 255, 40),
            accent=accent,
        )
    return Palette(
        dark=False,
        bg=QColor(252, 252, 252, 255),
        surface=QColor(255, 255, 255, 255),
        surface_hover=QColor(240, 241, 244, 255),
        text=QColor(27, 28, 31),
        subtext=QColor(95, 99, 104),
        border=QColor(0, 0, 0, 20),
        accent=accent,
    )


def apply_theme(app: QApplication, cfg: Config) -> Palette:
    font = QFont("Microsoft YaHei UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    palette = build_palette(cfg)
    app.setProperty("lotus_palette", palette)  # keep a reference for later windows
    log.info("theme: %s, accent %s", "dark" if palette.dark else "light", palette.accent.name())
    return palette

