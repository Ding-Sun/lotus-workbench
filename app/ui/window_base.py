"""Frameless, translucent window base: acrylic backdrop, rounded clip, animation.

Backdrop
--------
On Windows 11 22H2+ we ask DWM for an acrylic backdrop and lower the card
alpha so the blurred desktop shows through. DWM paints that backdrop across the
whole window rectangle, so the window is additionally clipped to a rounded
region — otherwise the corners would show square acrylic patches. If DWM
refuses, the card stays opaque; geometry and behaviour are unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from . import dwm
from .theme import Palette

log = logging.getLogger("lotus.ui.window")

ACRYLIC_ALPHA = 214


def set_acrylic_alpha(percent: int) -> None:
    """Tint strength of the acrylic card, 0-100 (higher = more opaque)."""
    global ACRYLIC_ALPHA
    ACRYLIC_ALPHA = max(0, min(100, int(percent))) * 255 // 100


class _CardSurface(QWidget):
    """The rounded card itself; children (labels, lists) live on top of it."""

    def __init__(self, pal: Palette, radius: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.pal = pal
        self.radius = radius
        self._backdrop = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self.update()

    def set_backdrop(self, pixmap) -> None:
        self._backdrop = pixmap
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1).toRectF()
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        if self._backdrop is not None:
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, self._backdrop)
            painter.setClipping(False)
        else:
            painter.fillPath(path, self.pal.bg)

        pen = QPen(self.pal.border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)


class LotusWindow(QWidget):
    def __init__(
        self,
        palette: Palette,
        *,
        radius: int = 18,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Not ``self.palette``: QWidget.palette() is a method, shadowing it
        # breaks Qt internals (stylesheets, teardown).
        self.pal = palette
        self.radius = radius
        self._visible = False
        self._backdrop_checked = False
        self._acrylic = False
        self._glass_raw = None
        self._surface_mode = "acrylic"

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._surface = _CardSurface(palette, radius, self)
        outer.addWidget(self._surface)

        self._content = QVBoxLayout(self._surface)
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(0)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(200)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(self._fade)
        self._group.addAnimation(self._slide)
        self._group.finished.connect(self._on_animation_finished)

    # -- api ---------------------------------------------------------------
    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content

    def set_content_size(self, width: int, height: int) -> None:
        self.setFixedSize(width, height)

    def is_shown(self) -> bool:
        return self._visible

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        # The card surface paints itself; the shell only needs to stay transparent.
        return

    # -- placement ---------------------------------------------------------
    def center_on_screen(self, screen=None) -> None:
        screen = screen or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    @staticmethod
    def screen_at_cursor():
        return QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()

    # -- animation ---------------------------------------------------------
    def show_animated(self, offset: QPoint | None = None) -> None:
        if self._visible:
            self.raise_()
            self.activateWindow()
            return
        offset = offset or QPoint(0, 10)
        self._visible = True
        target = self.pos()
        self.prepare_glass_at(target)
        self.setWindowOpacity(0.0)
        self.move(target + offset)

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

        self._group.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._slide.setStartValue(target + offset)
        self._slide.setEndValue(target)
        self._group.start()

    def hide_animated(self, offset: QPoint | None = None) -> None:
        if not self._visible:
            return
        offset = offset or QPoint(0, 6)
        self._visible = False
        self._group.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(self.pos() + offset)
        self._group.start()

    def toggle(self) -> None:
        if self._visible:
            self.hide_animated()
        else:
            self.show_animated()

    def _on_animation_finished(self) -> None:
        if not self._visible:
            self.hide()
            self.setWindowOpacity(1.0)

    # -- backdrop ----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self._backdrop_checked:
            return
        self._backdrop_checked = True
        hwnd = int(self.winId())
        dwm.set_dark_mode(hwnd, self.pal.dark)
        ok, message = dwm.enable_acrylic(hwnd)
        log.info("backdrop: %s", message)
        if ok:
            self._acrylic = True
            base = self.pal.bg
            self._surface.set_palette(
                replace(self.pal, bg=QColor(base.red(), base.green(), base.blue(), ACRYLIC_ALPHA))
            )
            self._apply_round_region()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_round_region()

    def _apply_round_region(self) -> None:
        if not self._acrylic:
            return
        ratio = self.devicePixelRatioF()
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        radius = max(1, int(round(self.radius * ratio)))
        dwm.set_round_region(int(self.winId()), width, height, radius)

    def refresh_acrylic(self) -> None:
        """Re-apply the tint after ``set_acrylic_alpha`` changes."""
        if self._glass_raw is not None:
            self._recompose_glass()
            return
        if not self._acrylic:
            return
        base = self.pal.bg
        self._surface.set_palette(
            replace(self.pal, bg=QColor(base.red(), base.green(), base.blue(), ACRYLIC_ALPHA))
        )

    def prepare_glass(self) -> None:
        """Grab and blur whatever is behind the window, before it is shown."""
        self.prepare_glass_at(self.pos())

    def prepare_glass_at(self, pos: QPoint) -> None:
        from PySide6.QtCore import QRect

        from .glass import capture_blur

        try:
            self._glass_raw = capture_blur(QRect(pos, self.size()))
        except Exception:  # noqa: BLE001 - glass is cosmetic, never fatal
            log.debug("glass capture failed", exc_info=True)
            self._glass_raw = None
        self._recompose_glass()

    def _recompose_glass(self) -> None:
        if self._glass_raw is None or self._surface_mode == "solid":
            self._surface.set_backdrop(None)
            if self._surface_mode == "solid":
                base = self.pal.bg
                self._surface.set_palette(
                    replace(self.pal, bg=QColor(base.red(), base.green(), base.blue(), 255))
                )
            return
        from .glass import tinted_glass

        raw = self._glass_raw
        if raw.width() != self.width() or raw.height() != self.height():
            # The card was resized after the capture (e.g. a custom grid size):
            # stretch the stored backdrop instead of using a stale-size pixmap.
            raw = raw.scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        strength = ACRYLIC_ALPHA * 100 // 255
        if self._surface_mode == "mica":
            strength = min(100, strength + 22)
        self._surface.set_backdrop(
            tinted_glass(raw, self.size(), self.pal.bg, strength, self.radius)
        )

    def apply_surface_mode(self, mode: str) -> None:
        self._surface_mode = mode if mode in ("acrylic", "mica", "solid") else "acrylic"
        self._recompose_glass()

    def apply_tint(self, color: QColor, strength: int) -> None:
        """Switch the material tint live (presets); children keep their text colours."""
        tint = QColor(color)
        tint.setAlpha(255)
        self.pal = replace(self.pal, bg=tint)
        if self._glass_raw is not None:
            self._recompose_glass()
            return
        alpha = max(0, min(100, int(strength))) * 255 // 100
        self._surface.set_palette(replace(self.pal, bg=QColor(tint.red(), tint.green(), tint.blue(), alpha)))

    # -- events ------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.hide_animated()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Must accept: Qt closes top-level windows during shutdown, and an
        # ignored close event blocks the quit sequence.
        self._visible = False
        self.hide()
        event.accept()
