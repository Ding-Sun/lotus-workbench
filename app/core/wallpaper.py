"""Pick a usable accent colour from the current desktop wallpaper.

Untamed uses an octree over album art; for a wallpaper a coarse bucket vote is
plenty: downscale, quantise, weight saturated pixels a bit higher, then average
the winning bucket. Falls back to ``None`` so callers can use the system accent.
"""

from __future__ import annotations

import logging
import os
import winreg
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

log = logging.getLogger("lotus.wallpaper")


def wallpaper_path() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            value, _ = winreg.QueryValueEx(key, "Wallpaper")
        path = Path(value) if value else None
        if path and path.is_file():
            return path
    except (OSError, ValueError):
        pass

    # Slideshow / theme wallpapers live here.
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
        if candidate.is_file():
            return candidate
    return None


def dominant_color() -> QColor | None:
    path = wallpaper_path()
    if path is None:
        return None

    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.scaled(
        48, 48, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )

    buckets: dict[tuple[int, int, int], list[float]] = {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            key = (color.red() // 32, color.green() // 32, color.blue() // 32)
            # Prefer colourful pixels over grey noise.
            saturation = max(color.red(), color.green(), color.blue()) - min(
                color.red(), color.green(), color.blue()
            )
            entry = buckets.setdefault(key, [0.0, 0.0, 0.0, 0.0])
            weight = 1.0 + saturation / 128.0
            entry[0] += color.red() * weight
            entry[1] += color.green() * weight
            entry[2] += color.blue() * weight
            entry[3] += weight

    if not buckets:
        return None

    best = max(buckets.values(), key=lambda item: item[3])
    weight = best[3] or 1.0
    color = QColor(
        int(best[0] / weight),
        int(best[1] / weight),
        int(best[2] / weight),
    )

    # Raw dominant colours are often near-black wallpaper shadow; lift them
    # into a range that works as a selection highlight.
    hue, saturation, lightness, alpha = color.getHslF()
    if hue < 0:
        return None
    color.setHslF(
        hue,
        max(0.35, min(0.60, saturation)),
        max(0.55, min(0.65, lightness)),
        alpha,
    )
    log.info("wallpaper accent: %s from %s", color.name(), path.name)
    return color

