"""Win11-style settings window: left navigation, right pages.

Frameless like the rest of Lotus, but with a real title bar: drag anywhere on
the header, minimise, and a close button that hides the window without touching
the tray process.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core import paths
from ..core.config import Config
from .icons import lotus_icon
from .materials import PRESETS
from .theme import Palette
from .window_base import LotusWindow

log = logging.getLogger("lotus.settings")

ACCENT_PRESETS = ("#4747D1", "#2E8B8B", "#8C5AA8", "#C06A3A", "#3A7D44", "#B03A5B")
GITHUB_URL = "https://github.com/Ding-Sun/lotus-workbench"


class _DragBar(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._press: QPoint | None = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint() - self.window().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._press)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._press = None
        super().mouseReleaseEvent(event)


class SettingsWindow(LotusWindow):
    def __init__(
        self,
        cfg: Config,
        pal: Palette,
        *,
        on_dock_changed: Callable[[str], None] | None = None,
        on_icons_changed: Callable[[bool], None] | None = None,
        on_hotkey_changed: Callable[[str, str], None] | None = None,
        on_petal_changed: Callable[[], None] | None = None,
        on_bloom_changed: Callable[[], None] | None = None,
        icons_visible: bool | None = None,
    ) -> None:
        super().__init__(pal, radius=14)
        self.cfg = cfg
        self.on_dock_changed = on_dock_changed
        self.on_icons_changed = on_icons_changed
        self.on_hotkey_changed = on_hotkey_changed
        self.on_petal_changed = on_petal_changed
        self.on_bloom_changed = on_bloom_changed
        self.set_content_size(980, 700)
        self._icons_visible = icons_visible
        self._build(icons_visible)

    # -- small widgets -----------------------------------------------------
    def _text(self, text: str, size: int, color: str | None = None, weight: int = 400) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color or self.pal.text.name()}; font-size: {size}px;"
            f" font-weight: {weight}; background: transparent;"
        )
        return label

    def _card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet(
            "QWidget#settingsCard { background: rgba(255,255,255,%d); border-radius: 10px; }"
            % (14 if self.pal.dark else 150)
        )
        return card

    def _row(self, title: str, subtitle: str, control: QWidget) -> QWidget:
        row = QWidget()
        row.setFixedHeight(60)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(self._text(title, 13))
        if subtitle:
            col.addWidget(self._text(subtitle, 10, self.pal.subtext.name()))
        layout.addLayout(col)
        layout.addStretch(1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _segment(self, options: list[tuple[str, str]], current: str, callback) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        group = QButtonGroup(holder)
        group.setExclusive(True)
        for value, text in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(value == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(30)
            button.setMinimumWidth(72)
            button.setStyleSheet(
                "QPushButton { color: %s; background: transparent; border: 1px solid %s;"
                " border-radius: 7px; padding: 0 12px; font-size: 12px; }"
                "QPushButton:checked { background: %s; color: #ffffff; border-color: %s; }"
                % (
                    self.pal.text.name(),
                    self.pal.border.name(),
                    self.pal.accent.name(),
                    self.pal.accent.name(),
                )
            )
            group.addButton(button)
            layout.addWidget(button)
            button.clicked.connect(lambda _checked=False, v=value: callback(v))
        return holder

    def _checkbox(self, checked: bool, callback) -> QCheckBox:
        box = QCheckBox()
        box.setChecked(checked)
        box.setStyleSheet("QCheckBox { background: transparent; }")
        box.toggled.connect(callback)
        return box

    def _spin(self, value: int, minimum: int, maximum: int, suffix: str, callback) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setFixedWidth(96)
        spin.setStyleSheet(
            f"QSpinBox {{ color: {self.pal.text.name()}; background: rgba(255,255,255,16);"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 3px 6px; }}"
        )
        spin.valueChanged.connect(callback)
        return spin

    def _section(self, title: str) -> QWidget:
        label = self._text(title, 11, self.pal.subtext.name(), 600)
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.addWidget(label)
        layout.addStretch(1)
        return wrapper

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 8, 20, 16)
        outer.setSpacing(8)
        return page, outer

    # -- shell -------------------------------------------------------------
    def _build(self, icons_visible: bool | None) -> None:
        root = self.content_layout
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(52)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 0, 10, 0)
        header_layout.setSpacing(6)
        header_layout.addWidget(self._text("设置", 15, None, 600))
        header_layout.addStretch(1)
        self.min_button = self._window_button("—")
        self.min_button.setToolTip("隐藏窗口（托盘继续运行）")
        # Qt.Tool windows cannot minimise cleanly on Windows: the frame is
        # re-painted halfway. Hiding gives the same one-click result, and the
        # window always comes back in one piece.
        self.min_button.clicked.connect(self.hide_animated)
        header_layout.addWidget(self.min_button)
        self.close_button = self._window_button("✕")
        self.close_button.clicked.connect(self.hide_animated)
        header_layout.addWidget(self.close_button)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setFixedWidth(210)
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setStyleSheet(
            "QListWidget { background: rgba(255,255,255,10); border: none; outline: none;"
            " padding: 10px 8px; }"
            "QListWidget::item { color: %s; border-radius: 7px; padding: 9px 12px; margin: 2px 0;"
            " font-size: 13px; }"
            "QListWidget::item:selected { background: %s; color: #ffffff; }"
            "QListWidget::item:hover:!selected { background: rgba(255,255,255,18); }"
            % (self.pal.text.name(), self.pal.accent.name())
        )
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        pages = [
            ("外观", self._page_appearance()),
            ("桌面收纳", self._page_bloom()),
            ("侧边栏", self._page_petal()),
            ("快捷键", self._page_hotkeys()),
            ("搜索与索引", self._page_search()),
            ("关于", self._page_about()),
        ]
        for title, widget in pages:
            item = QListWidgetItem(title)
            item.setSizeHint(QSize(180, 40))
            self.nav.addItem(item)
            self.stack.addWidget(widget)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

    def _window_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(34, 30)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ color: {self.pal.subtext.name()}; background: transparent;"
            " border: none; border-radius: 6px; font-size: 13px; }"
            "QPushButton:hover { background: rgba(255,255,255,26); color: %s; }"
            % self.pal.text.name()
        )
        return button

    # -- pages -------------------------------------------------------------
    def _page_appearance(self) -> QWidget:
        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(
            self._row(
                "主题",
                "跟随系统，或固定浅色 / 深色（重启生效）",
                self._segment(
                    [("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")],
                    str(self.cfg.get("theme.mode", "system")),
                    self._set_mode,
                ),
            )
        )
        layout.addWidget(
            self._row(
                "窗口材质",
                "亚克力 = 模糊底图 + 淡色；云母 = 更浓；纯色 = 不透明",
                self._segment(
                    [("acrylic", "亚克力"), ("mica", "云母"), ("solid", "纯色")],
                    str(self.cfg.get("theme.surface_mode", "acrylic")),
                    self._set_surface,
                ),
            )
        )

        opacity_box = QWidget()
        opacity_layout = QHBoxLayout(opacity_box)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(8)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.cfg.get("theme.tint_opacity", 52)))
        self.opacity_slider.setFixedWidth(150)
        self.opacity_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: %s; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: %s; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0;"
            " border-radius: 6px; background: %s; }"
            % (self.pal.border.name(), self.pal.accent.name(), self.pal.text.name())
        )
        self.opacity_value = self._text(f"{self.opacity_slider.value()}%", 11, self.pal.subtext.name())
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_value)
        layout.addWidget(self._row("不透明度", "越高越实，越低越透", opacity_box))

        accent_holder = QWidget()
        accent_layout = QHBoxLayout(accent_holder)
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(6)
        for color in ACCENT_PRESETS:
            chip = QPushButton()
            chip.setFixedSize(22, 22)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(color)
            chip.setStyleSheet(
                f"QPushButton {{ background: {color}; border: 2px solid transparent;"
                " border-radius: 11px; }"
                "QPushButton:hover { border-color: rgba(255,255,255,160); }"
            )
            chip.clicked.connect(lambda _checked=False, c=color: self._set_accent(c))
            accent_layout.addWidget(chip)
        layout.addWidget(
            self._row(
                "强调色",
                "跟随系统 / 壁纸取色 / 固定色（重启生效）",
                self._segment(
                    [("auto", "系统"), ("wallpaper", "壁纸")],
                    "wallpaper" if str(self.cfg.get("theme.accent")) == "wallpaper" else "auto",
                    self._set_accent_mode,
                ),
            )
        )
        layout.addWidget(self._row("预设色", "点选一个固定强调色", accent_holder))
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _page_bloom(self) -> QWidget:
        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(
            self._row(
                "停靠位置",
                "收纳盒固定在屏幕哪一侧",
                self._segment(
                    [("left", "靠左"), ("right", "靠右")],
                    str(self.cfg.get("bloom.dock", "right")),
                    self._set_dock,
                ),
            )
        )
        layout.addWidget(
            self._row(
                "桌面图标",
                "隐藏系统图标，只留 Lotus 收纳盒",
                self._checkbox(self._icons_visible is False, self._set_icons),
            )
        )
        layout.addWidget(
            self._row(
                "悬停展开延迟",
                "鼠标停在收纳盒上多久后展开",
                self._spin(
                    int(self.cfg.get("bloom.hover_delay_ms", 250)),
                    0,
                    1200,
                    " ms",
                    lambda v: self.cfg.set("bloom.hover_delay_ms", int(v)),
                ),
            )
        )
        layout.addWidget(
            self._row(
                "每个气泡最多图标",
                "超出部分暂时隐藏",
                self._spin(
                    int(self.cfg.get("bloom.max_items_per_bubble", 16)),
                    4,
                    40,
                    " 个",
                    self._set_max_items,
                ),
            )
        )
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _page_petal(self) -> QWidget:
        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(
            self._row(
                "边缘热区",
                "鼠标进入右上角一小块区域时呼出侧边栏",
                self._checkbox(bool(self.cfg.get("petal.hot_zone_enabled", True)), self._set_hotzone),
            )
        )
        layout.addWidget(
            self._row(
                "常用路径显示方式",
                "列表样式，或 Windows 风格的大图标网格",
                self._segment(
                    [("list", "列表"), ("grid", "图标")],
                    str(self.cfg.get("petal.mode", "list")),
                    self._set_petal_mode,
                ),
            )
        )
        layout.addWidget(
            self._row(
                "热区垂直位置",
                "距屏幕顶部多少像素开始（避开关闭按钮）",
                self._spin(
                    int(self.cfg.get("petal.hot_zone_top", 90)),
                    0,
                    800,
                    " px",
                    lambda v: self._set_zone_value("top", int(v)),
                ),
            )
        )
        layout.addWidget(
            self._row(
                "热区高度",
                "这块区域的高度",
                self._spin(
                    int(self.cfg.get("petal.hot_zone_height", 140)),
                    40,
                    600,
                    " px",
                    lambda v: self._set_zone_value("height", int(v)),
                ),
            )
        )
        modules = self.cfg.get("petal.modules", {}) or {}
        for key, title in (("notes", "最近速记"), ("paths", "常用路径"), ("terminal", "终端入口")):
            layout.addWidget(
                self._row(
                    f"显示 {title}",
                    "关闭后侧边栏不显示该模块",
                    self._checkbox(bool(modules.get(key, True)), lambda v, k=key: self._set_module(k, v)),
                )
            )
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _page_hotkeys(self) -> QWidget:
        from PySide6.QtWidgets import QKeySequenceEdit

        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        for name, title, hint in (
            ("bloom", "显示 / 隐藏收纳盒", "Bloom"),
            ("petal", "呼出侧边栏", "Petal"),
            ("ink", "呼出速记", "Ink"),
            ("icons", "隐藏 / 显示桌面图标", "桌面"),
        ):
            editor = QKeySequenceEdit()
            editor.setKeySequence(QKeySequence(str(self.cfg.get(f"hotkeys.{name}", ""))))
            editor.setFixedWidth(170)
            editor.setStyleSheet(
                f"QKeySequenceEdit {{ color: {self.pal.text.name()};"
                " background: rgba(255,255,255,16);"
                f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 3px 6px; }}"
            )
            editor.editingFinished.connect(
                lambda n=name, e=editor: self._set_hotkey(n, e.keySequence().toString())
            )
            layout.addWidget(self._row(title, f"{hint} 快捷键，改完立即生效", editor))
        outer.addWidget(card)
        outer.addWidget(
            self._text("提示：与其他软件冲突时注册会失败，界面会弹出提示。", 10, self.pal.subtext.name())
        )
        outer.addStretch(1)
        return page

    def _page_search(self) -> QWidget:
        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        path_box = QWidget()
        path_layout = QHBoxLayout(path_box)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.es_edit = QLineEdit(str(self.cfg.get("seek.es_path", "")))
        self.es_edit.setMinimumWidth(260)
        self.es_edit.setStyleSheet(
            f"QLineEdit {{ color: {self.pal.text.name()}; background: rgba(255,255,255,16);"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 4px 8px; }}"
        )
        self.es_edit.editingFinished.connect(self._set_es_path)
        browse = QPushButton("浏览…")
        browse.setFixedHeight(28)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setStyleSheet(
            f"QPushButton {{ color: {self.pal.text.name()}; background: rgba(255,255,255,16);"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 0 12px; }}"
        )
        browse.clicked.connect(self._browse_es)
        path_layout.addWidget(self.es_edit)
        path_layout.addWidget(browse)
        layout.addWidget(self._row("es.exe 路径", "Everything 命令行搜索工具", path_box))

        self.roots_list = QListWidget()
        self.roots_list.setFixedHeight(120)
        self.roots_list.setStyleSheet(
            f"QListWidget {{ color: {self.pal.text.name()}; background: rgba(255,255,255,10);"
            f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 4px; }}"
        )
        for root in self.cfg.get("leaf.roots", []) or []:
            self.roots_list.addItem(str(root))
        outer.addWidget(card)

        roots_card = self._card()
        roots_layout = QVBoxLayout(roots_card)
        roots_layout.setContentsMargins(16, 12, 16, 12)
        roots_layout.setSpacing(8)
        roots_layout.addWidget(self._text("文档扫描根目录", 13))
        roots_layout.addWidget(self._text("用于以后索引 docx / pdf", 10, self.pal.subtext.name()))
        roots_layout.addWidget(self.roots_list)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add = QPushButton("添加目录…")
        remove = QPushButton("移除选中")
        for button in (add, remove):
            button.setFixedHeight(28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ color: {self.pal.text.name()}; background: rgba(255,255,255,16);"
                f" border: 1px solid {self.pal.border.name()}; border-radius: 6px; padding: 0 12px; }}"
            )
        add.clicked.connect(self._add_root)
        remove.clicked.connect(self._remove_root)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        roots_layout.addLayout(buttons)
        outer.addWidget(roots_card)
        outer.addStretch(1)
        return page

    def _page_about(self) -> QWidget:
        page, outer = self._page()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(lotus_icon(self.pal).pixmap(56, 56))
        logo.setFixedSize(56, 56)
        row.addWidget(logo)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(self._text(APP_NAME, 18, None, 600))
        text_col.addWidget(self._text(f"版本 v{__version__}", 11, self.pal.subtext.name()))
        row.addLayout(text_col)
        row.addStretch(1)
        layout.addLayout(row)

        link_color = self.pal.accent.lighter(150).name()
        link = QLabel(f'<a style="color:{link_color}" href="{GITHUB_URL}">{GITHUB_URL}</a>')
        link.setOpenExternalLinks(True)
        link.setStyleSheet("background: transparent; font-size: 12px;")
        layout.addWidget(link)
        layout.addWidget(
            self._text(
                "开源协议：MIT License\n第三方组件：Everything（es.exe，用于全局搜索）",
                11,
                self.pal.subtext.name(),
            )
        )
        layout.addWidget(
            self._text(f"数据目录：{paths.HOME}", 10, self.pal.subtext.name())
        )
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # -- actions -----------------------------------------------------------
    def _set_mode(self, value: str) -> None:
        self.cfg.set("theme.mode", value)

    def _set_surface(self, mode: str) -> None:
        self.cfg.set("theme.surface_mode", mode)
        self._apply_surface_everywhere(mode)

    def _apply_surface_everywhere(self, mode: str) -> None:
        from PySide6.QtWidgets import QApplication

        for widget in QApplication.topLevelWidgets():
            if widget is self:
                continue
            apply = getattr(widget, "apply_surface_mode", None)
            if callable(apply):
                apply(mode)

    def _set_opacity(self, value: int) -> None:
        from PySide6.QtWidgets import QApplication

        from .window_base import set_acrylic_alpha

        self.cfg.set("theme.tint_opacity", int(value))
        self.opacity_value.setText(f"{value}%")
        set_acrylic_alpha(int(value))
        for widget in QApplication.topLevelWidgets():
            refresh = getattr(widget, "refresh_acrylic", None)
            if callable(refresh):
                refresh()

    def _set_accent_mode(self, value: str) -> None:
        self.cfg.set("theme.accent", value)

    def _set_accent(self, color: str) -> None:
        self.cfg.set("theme.accent", color)

    def _set_dock(self, value: str) -> None:
        self.cfg.set("bloom.dock", value)
        if self.on_dock_changed is not None:
            self.on_dock_changed(value)

    def _set_icons(self, hidden: bool) -> None:
        if self.on_icons_changed is not None:
            self.on_icons_changed(hidden)

    def _set_max_items(self, value: int) -> None:
        self.cfg.set("bloom.max_items_per_bubble", int(value))
        if self.on_bloom_changed is not None:
            self.on_bloom_changed()

    def _set_hotzone(self, enabled: bool) -> None:
        self.cfg.set("petal.hot_zone_enabled", bool(enabled))
        self._notify_petal()

    def _set_petal_mode(self, mode: str) -> None:
        self.cfg.set("petal.mode", mode)
        self._notify_petal()

    def _set_zone_value(self, key: str, value: int) -> None:
        self.cfg.set(f"petal.hot_zone_{key}", int(value))
        self._notify_petal()

    def _set_module(self, key: str, enabled: bool) -> None:
        self.cfg.set(f"petal.modules.{key}", bool(enabled))
        self._notify_petal()

    def _notify_petal(self) -> None:
        if self.on_petal_changed is not None:
            self.on_petal_changed()

    def _set_hotkey(self, name: str, sequence: str) -> None:
        if not sequence:
            return
        self.cfg.set(f"hotkeys.{name}", sequence)
        if self.on_hotkey_changed is not None:
            self.on_hotkey_changed(name, sequence)

    def _set_es_path(self) -> None:
        self.cfg.set("seek.es_path", self.es_edit.text().strip())

    def _browse_es(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 es.exe", "", "可执行文件 (*.exe)")
        if path:
            self.es_edit.setText(path)
            self._set_es_path()

    def _add_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择扫描目录")
        if path:
            self.roots_list.addItem(path)
            self._save_roots()

    def _remove_root(self) -> None:
        for item in self.roots_list.selectedItems():
            self.roots_list.takeItem(self.roots_list.row(item))
        self._save_roots()

    def _save_roots(self) -> None:
        roots = [self.roots_list.item(i).text() for i in range(self.roots_list.count())]
        self.cfg.set("leaf.roots", roots)

    # -- window ------------------------------------------------------------
    def open_settings(self) -> None:
        screen = self.screen_at_cursor()
        self.center_on_screen(screen)
        self.show_animated()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide_animated()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- title bar dragging ------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 52:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if getattr(self, "_drag_offset", None) is not None and event.position().y() <= 60:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_surface_everywhere(str(self.cfg.get("theme.surface_mode", "acrylic")))


