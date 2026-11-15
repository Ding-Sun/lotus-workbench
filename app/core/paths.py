"""Filesystem locations used by Lotus Workbench.

Everything user-owned lives under ``%USERPROFILE%\\.lotus`` by default; set
``LOTUS_HOME`` to relocate it (useful for testing and for portable installs).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_SLUG = "lotus"


def _lotus_home() -> Path:
    override = os.environ.get("LOTUS_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".lotus"


HOME: Path = _lotus_home()
NOTES_DIR: Path = HOME / "notes"
LOGS_DIR: Path = HOME / "logs"
CACHE_DIR: Path = HOME / "cache"
CONFIG_FILE: Path = HOME / "config.json"
LEAF_INDEX_FILE: Path = CACHE_DIR / "leaf-index.json"


def ensure_dirs() -> None:
    """Create every directory Lotus may write to. Cheap and idempotent."""
    for directory in (HOME, NOTES_DIR, LOGS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Directory containing bundled resources (``assets/``)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    return app_root().joinpath("assets", *parts)
