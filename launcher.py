"""Entry point used by PyInstaller and by `python -m` style runs."""

from __future__ import annotations

import sys
import traceback


def _report_failure(exc_text: str) -> None:
    try:
        from app.core import paths

        log_dir = paths.HOME / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "crash.log").write_text(exc_text, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(
            None,
            "Lotus 启动失败",
            "启动时发生错误，详情见 %USERPROFILE%\\.lotus\\logs\\crash.log\n\n" + exc_text[-1200:],
        )
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    try:
        from app.main import main as run

        return run()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - last-resort guard: never die silently
        text = traceback.format_exc()
        print(text, file=sys.stderr)
        _report_failure(text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
