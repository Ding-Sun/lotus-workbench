"""Entry point for `python -m app`.

A last-resort guard: a windowed interpreter (pythonw) has nowhere to print, so
startup failures are written to `.lotus\\logs\\crash.log` and shown in a dialog
instead of disappearing silently.
"""

from __future__ import annotations

import sys
import traceback


def _report(text: str) -> None:
    try:
        from .core import paths

        log_dir = paths.HOME / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "crash.log").write_text(text, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(
            None,
            "Lotus 启动失败",
            "启动时发生错误，详情见 %USERPROFILE%\\.lotus\\logs\\crash.log\n\n" + text[-1200:],
        )
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        from .main import main

        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        text = traceback.format_exc()
        print(text, file=sys.stderr)
        _report(text)
        sys.exit(1)
