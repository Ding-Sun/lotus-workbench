"""Frosted-glass backdrop captured from whatever is behind a window.

The DWM acrylic APIs return success but do nothing for Qt windows on this
Windows build, so we grab the screen region behind the window before it is
shown, blur it, and paint it inside the card. The tint slider then controls how
much colour is laid over that blurred backdrop.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

log = logging.getLogger("lotus.glass")


def capture_blur(rect: QRect, radius: float = 26.0) -> QPixmap | None:
    screen = QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
    if screen is None or rect.width() <= 0 or rect.height() <= 0:
        return None

    shot = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
    if shot.isNull():
        return None

    # Downscale first: blur is cheap at 1/4 size and looks smoother.
    small = shot.scaled(
        max(1, rect.width() // 4),
        max(1, rect.height() // 4),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(small)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius / 4.0)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    out = QImage(small.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    scene.render(painter)
    painter.end()

    return QPixmap.fromImage(
        out.scaled(
            rect.width(),
            rect.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def tinted_glass(glass: QPixmap | None, size: QSize, tint, strength: int, radius: int) -> QPixmap:
    """Compose blurred backdrop + coloured tint into one pixmap."""
    result = QPixmap(size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRoundedRect(0, 0, size.width(), size.height(), radius, radius)
    painter.setClipPath(path)

    if glass is not None:
        painter.drawPixmap(QPoint(0, 0), glass)
    else:
        painter.fillRect(result.rect(), Qt.GlobalColor.transparent)

    color = tint
    color = color.__class__(color)
    color.setAlpha(max(0, min(100, strength)) * 255 // 100)
    painter.fillRect(result.rect(), color)
    painter.end()
    return result
