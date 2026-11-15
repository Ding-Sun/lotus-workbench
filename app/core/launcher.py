"""Shell integration: open paths, spawn terminals, track spawned processes.

Terminals are *not* reimplemented — we ask the OS to start cmd.exe / powershell.exe
in a new console and, where possible, keep a handle so the sidebar footer can show
what Lotus started. Nothing here polls: liveness comes from waiting on the child.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("lotus.launcher")

CREATE_NEW_CONSOLE = 0x00000010
_SHELL_EXECUTE_OK = 32

TERMINALS = {
    "cmd": ("cmd.exe", "CMD"),
    "powershell": ("powershell.exe", "PowerShell"),
}


def open_path(path: str | Path) -> bool:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        return True
    except OSError as exc:
        log.warning("cannot open %s: %s", path, exc)
        return False


def reveal_path(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        subprocess.Popen(["explorer.exe", f"/select,{target}"])  # noqa: S603,S607
        return True
    except OSError as exc:
        log.warning("cannot reveal %s: %s", path, exc)
        return False


def _shell_execute(verb: str, exe: str, params: str, cwd: str) -> bool:
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, verb, exe, params, cwd, 1)
    except OSError as exc:
        log.warning("ShellExecute failed: %s", exc)
        return False
    if result <= _SHELL_EXECUTE_OK:
        log.warning("ShellExecute(%s) returned %s", exe, result)
        return False
    return True


def open_terminal(kind: str, cwd: str | Path | None = None) -> tuple[bool, str]:
    """Open a terminal window at ``cwd``. Returns ``(ok, error)``."""
    directory = str(cwd or Path.home())
    if not Path(directory).is_dir():
        directory = str(Path.home())

    if kind == "admin":
        ok = _shell_execute("runas", "powershell.exe", "-NoLogo", directory)
        return (True, "") if ok else (False, "管理员终端启动失败（可能取消了 UAC）")

    exe, _ = TERMINALS.get(kind, TERMINALS["cmd"])
    try:
        subprocess.Popen(  # noqa: S603
            [exe],
            cwd=directory,
            creationflags=CREATE_NEW_CONSOLE,
        )
    except OSError as exc:
        return False, str(exc)
    return True, ""


class ProcessRegistry(QObject):
    """Knows which long-lived processes Lotus started, without polling."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._names: dict[int, str] = {}

    def active(self) -> list[str]:
        return list(self._names.values())

    def spawn_terminal(self, kind: str, cwd: str | Path | None = None) -> tuple[bool, str]:
        directory = str(cwd or Path.home())
        if not Path(directory).is_dir():
            directory = str(Path.home())

        if kind == "admin":
            ok, error = open_terminal("admin", directory)
            # Elevated processes cannot be waited on without extra privileges;
            # they are intentionally not listed in the footer.
            return ok, error

        exe, label = TERMINALS.get(kind, TERMINALS["cmd"])
        try:
            proc = subprocess.Popen(  # noqa: S603
                [exe], cwd=directory, creationflags=CREATE_NEW_CONSOLE
            )
        except OSError as exc:
            return False, str(exc)

        self._names[proc.pid] = label
        self.changed.emit()
        threading.Thread(target=self._watch, args=(proc, label), daemon=True).start()
        return True, ""

    def _watch(self, proc: subprocess.Popen, label: str) -> None:
        try:
            proc.wait()
        except Exception:  # noqa: BLE001 - never let the watcher die loudly
            log.debug("process watcher error for %s", label, exc_info=True)
        self._names.pop(proc.pid, None)
        self.changed.emit()
