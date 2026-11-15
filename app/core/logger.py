"""Rotating file logging.

``pythonw.exe`` has no console, so a file handler is the only reliable record;
the console handler is attached only when stderr is actually available.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

LOGGER_NAME = "lotus"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _file_handler(target: Path) -> RotatingFileHandler:
    return RotatingFileHandler(
        target,
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    paths.ensure_dirs()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        # A second instance (or a locked file) must never kill startup: fall
        # back to the temp directory and keep going.
        try:
            file_handler = _file_handler(paths.LOGS_DIR / "lotus.log")
        except OSError:
            fallback = Path(tempfile.gettempdir()) / "lotus.log"
            file_handler = _file_handler(fallback)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        logger.addHandler(file_handler)

        if sys.stderr is not None:
            console = logging.StreamHandler(sys.stderr)
            console.setLevel(level)
            console.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
            logger.addHandler(console)

    return logger
