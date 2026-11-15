"""Application bootstrap: config, theme, tray, hotkeys, windows."""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__
from .core import paths
from .core.bloom import ensure_default_groups
from .core.config import Config
from .core.desktop_icons import icons_visible, set_icons_visible
from .core.hotkeys import HotkeyManager
from .core.launcher import ProcessRegistry
from .core.logger import setup_logging
from .core.notes import NotesStore
from .core.single_instance import SingleInstance
from .ui.settings import SettingsWindow
from .ui.desktop import DesktopLayer
from .ui.ink import InkEditorWindow, NotesManagerWindow
from .ui.petal import EdgeWatcher, PetalWindow, ensure_default_roots
from .ui.theme import apply_theme
from .ui.tray import Tray
from .ui.window_base import set_acrylic_alpha

log = logging.getLogger("lotus")

_HOTKEYS = (("bloom", "工作台"), ("petal", "侧边栏"), ("ink", "速记"), ("icons", "桌面图标"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lotus")
    parser.add_argument("--bloom", action="store_true", help="启动后立即打开气泡启动器（调试用）")
    parser.add_argument("--front", action="store_true", help="调试：气泡置顶显示，不压在桌面层")
    parser.add_argument("--petal", action="store_true", help="启动后立即展开侧边栏（调试用）")
    parser.add_argument("--ink", nargs="?", const="", metavar="NOTE", help="启动后立即打开速记窗口（调试用）")
    parser.add_argument("--notes", action="store_true", help="启动后立即打开笔记管理（调试用）")
    parser.add_argument("--settings", action="store_true", help="启动后立即打开控制中心（调试用）")
    parser.add_argument("--shot", metavar="PNG", help="打开对应窗口、截图并退出（开发验证）")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    args, qt_args = build_parser().parse_known_args(raw_args)

    paths.ensure_dirs()

    app = QApplication([sys.argv[0] or "lotus", *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Lotus")
    app.setQuitOnLastWindowClosed(False)

    # Take the single-instance lock *before* touching the log file: a second
    # launch must exit without racing the first one for lotus.log.
    instance = SingleInstance()
    if not args.shot and not instance.acquire():
        instance.notify_existing("toggle")
        log_message = "another Lotus instance is running; asked it to toggle"
        QMessageBox.information(
            None,
            "Lotus Workbench",
            "Lotus 已经在运行了。\n\n"
            "它可能藏在托盘里，或者是以管理员身份启动的实例。\n"
            "按 Ctrl+Alt+B 显示 / 隐藏收纳盒；要重启请先退出托盘里的 Lotus。",
        )
        print(log_message, file=sys.stderr)
        return 0

    setup_logging()
    log.info("Lotus Workbench %s starting", __version__)

    cfg = Config.load()
    palette = apply_theme(app, cfg)
    set_acrylic_alpha(int(cfg.get("theme.tint_opacity", 78)))

    ensure_default_roots(cfg)
    ensure_default_groups(cfg)

    registry = ProcessRegistry()
    notes = NotesStore()
    editor = InkEditorWindow(cfg, palette, notes)
    manager = NotesManagerWindow(cfg, palette, notes)
    petal = PetalWindow(cfg, palette, registry, notes, manager.open_note)
    bloom = DesktopLayer(cfg, palette, front=args.front)
    bloom.build()
    tray = Tray(palette, cfg)
    tray.show()
    log.info(
        "tray: available=%s visible=%s",
        QSystemTrayIcon.isSystemTrayAvailable(),
        tray.isVisible(),
    )
    tray.notify(
        "Lotus 已启动",
        "气泡已放在桌面右侧。最小化窗口或按 Win+D 就能看到；Ctrl+Alt+B 显示/隐藏。",
    )

    def on_icons_toggle(hidden: bool) -> None:
        nonlocal icons_hidden
        icons_hidden = hidden
        ok = set_icons_visible(not hidden)
        if not ok:
            tray.notify("桌面图标", "切换失败：系统拒绝了这次操作", warning=True)
        current = icons_visible()
        if current is not None:
            tray.icons_action.blockSignals(True)
            tray.icons_action.setChecked(not current)
            tray.icons_action.blockSignals(False)

    icons_hidden = False
    tray.icons_toggle_requested.connect(on_icons_toggle)
    current_icons = icons_visible()
    if current_icons is not None:
        tray.icons_action.blockSignals(True)
        tray.icons_action.setChecked(not current_icons)
        tray.icons_action.blockSignals(False)

    # Explorer restarts bring the icons back; re-apply the user's choice.
    icons_guard = QTimer(app)
    icons_guard.setInterval(3000)

    def keep_icons_hidden() -> None:
        if icons_hidden and icons_visible() is True:
            set_icons_visible(False)
            log.info("desktop icons re-hidden after Explorer restart")

    icons_guard.timeout.connect(keep_icons_hidden)
    icons_guard.start()

    def show_bloom() -> None:
        log.info("bloom: toggling desktop layer (visible=%s)", bloom.is_visible())
        bloom.toggle()
        state = "显示" if bloom.is_visible() else "隐藏"
        tray.notify("气泡层", f"已{state}（在桌面右侧）")

    def show_petal() -> None:
        log.info("petal: toggling")
        petal.toggle()

    def show_ink(path: str | None = None) -> None:
        if path:
            note = notes.load(pathlib.Path(path))
            if note is not None:
                log.info("ink: editing %s", note.path.name)
                editor.open_note(note)
                return
            log.warning("ink: note not found: %s", path)
        log.info("ink: new note")
        editor.open_new()

    def show_notes() -> None:
        log.info("notes: manager")
        manager.open_note(None)

    def toggle_icons_hotkey() -> None:
        current = icons_visible()
        if current is None:
            tray.notify("桌面图标", "找不到桌面图标层", warning=True)
            return
        tray.icons_action.setChecked(not current)

    hotkeys = HotkeyManager(app)
    handlers = {
        "bloom": show_bloom,
        "petal": show_petal,
        "ink": lambda: show_ink(),
        "icons": toggle_icons_hotkey,
    }
    for name, label in _HOTKEYS:
        ok, message = hotkeys.register(name, str(cfg.get(f"hotkeys.{name}", "")), handlers[name])
        if ok:
            log.info("hotkey %s ready: %s", name, message)
        else:
            log.warning("hotkey %s unavailable: %s", name, message)
            tray.notify(f"{label}热键不可用", message, warning=True)

    tray.bloom_requested.connect(show_bloom)
    tray.petal_requested.connect(show_petal)
    tray.ink_requested.connect(lambda: show_ink())

    def on_instance_message(_message: str) -> None:
        log.info("second launch: toggling desktop layer")
        bloom.toggle()

    instance.message_received.connect(on_instance_message)

    edge = EdgeWatcher(
        lambda: petal.is_shown(),
        edge_px=int(cfg.get("petal.hot_edge_px", 5)),
        zone_top=int(cfg.get("petal.hot_zone_top", 90)),
        zone_height=int(cfg.get("petal.hot_zone_height", 140)),
    )
    edge.entered.connect(petal.show_at_cursor)
    edge.apply(
        bool(cfg.get("petal.hot_zone_enabled", True)),
        int(cfg.get("petal.hot_zone_top", 90)),
        int(cfg.get("petal.hot_zone_height", 140)),
    )

    def on_hotkey_changed(name: str, sequence: str) -> None:
        ok, message = hotkeys.reload(name, sequence, handlers[name])
        if ok:
            log.info("hotkey %s updated: %s", name, message)
            tray.notify("快捷键已更新", f"{name} → {message}")
        else:
            log.warning("hotkey %s update failed: %s", name, message)
            tray.notify("快捷键不可用", message, warning=True)

    def on_petal_changed() -> None:
        petal.apply_modules()
        edge.apply(
            bool(cfg.get("petal.hot_zone_enabled", True)),
            int(cfg.get("petal.hot_zone_top", 90)),
            int(cfg.get("petal.hot_zone_height", 140)),
        )

    settings = SettingsWindow(
        cfg,
        palette,
        on_dock_changed=lambda _value: bloom.reload_dock(),
        on_icons_changed=lambda hidden: tray.icons_action.setChecked(hidden),
        on_hotkey_changed=on_hotkey_changed,
        on_petal_changed=on_petal_changed,
        on_bloom_changed=bloom.rebuild,
        icons_visible=icons_visible(),
    )
    tray.settings_requested.connect(settings.open_settings)
    petal.settings_requested.connect(settings.open_settings)
    petal.new_group_requested.connect(lambda: bloom.create_group())
    petal.desktop_icons_requested.connect(
        lambda: tray.icons_action.setChecked(icons_visible() is True)
    )

    def on_petal_visibility(visible: bool) -> None:
        bloom.set_shift(petal.width() + 12 if visible else 0)

    petal.visibility_changed.connect(on_petal_visibility)

    def shutdown() -> None:
        log.info("shutting down")
        if icons_visible() is False:
            log.info("restoring desktop icons on exit")
            set_icons_visible(True)
        hotkeys.unregister_all()
        instance.release()
        tray.hide()
        app.quit()

    tray.quit_requested.connect(shutdown)
    app.aboutToQuit.connect(hotkeys.unregister_all)

    if args.shot:
        if args.settings:
            target, label, opener = settings, "settings", settings.open_settings
        elif args.notes:
            target, label, opener = manager, "notes", show_notes
        elif args.ink is not None:
            target, label, opener = editor, "ink", lambda: show_ink(args.ink)
        elif args.petal:
            target, label, opener = petal, "petal", petal.show_at_cursor
        else:
            target, label, opener = None, "desktop", bloom.show_all
        opener()

        def capture() -> None:
            screen = app.primaryScreen()
            if screen is not None:
                if target is None:
                    pixmap = screen.grabWindow(0)
                else:
                    pixmap = screen.grabWindow(0, target.x(), target.y(), target.width(), target.height())
                pixmap.save(args.shot)
                log.info("screenshot saved to %s (%s)", args.shot, label)
            app.quit()

        QTimer.singleShot(1200, capture)
    elif args.settings:
        settings.open_settings()
    elif args.notes:
        show_notes()
    elif args.ink is not None:
        show_ink(args.ink)
    elif args.petal:
        petal.show_at_cursor()
    elif args.bloom:
        bloom.show_all()

    return app.exec()


