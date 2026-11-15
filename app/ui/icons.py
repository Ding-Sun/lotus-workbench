"""Programmatic icons so the project ships without binary assets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap

from .theme import Palette


def lotus_pixmap(palette: Palette, size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    scale = size / 64.0

    # Backing plate.
    plate = QPainterPath()
    plate.addRoundedRect(QRectF(2 * scale, 2 * scale, 60 * scale, 60 * scale), 16 * scale, 16 * scale)
    painter.fillPath(plate, QColor(24, 25, 30))

    accent = QColor(palette.accent)
    petal_alpha = (255, 210, 150)
    angles = (-38.0, 0.0, 38.0)
    for angle, alpha in zip(angles, petal_alpha):
        color = QColor(accent)
        color.setAlpha(alpha)
        painter.save()
        painter.translate(QPointF(32 * scale, 42 * scale))
        painter.rotate(angle)
        petal = QPainterPath()
        petal.addEllipse(QRectF(-8 * scale, -30 * scale, 16 * scale, 34 * scale))
        painter.fillPath(petal, color)
        painter.restore()

    # Water line.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 46))
    painter.drawEllipse(QRectF(20 * scale, 46 * scale, 24 * scale, 5 * scale))
    painter.end()
    return pixmap


def lotus_icon(palette: Palette, size: int = 64) -> QIcon:
    icon = QIcon()
    for edge in (16, 24, 32, 48, 64):
        icon.addPixmap(lotus_pixmap(palette, edge))
    return icon
