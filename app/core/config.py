"""JSON-backed configuration store.

Design notes:

* One file, human-readable, UTF-8, atomic replace on save.
* Defaults are deep-merged on load so new keys appear after upgrades without
  rewriting the user's file.
* A corrupt file is moved aside instead of crashing the app.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger("lotus.config")

CONFIG_VERSION = 3

DEFAULTS: dict[str, Any] = {
    "version": CONFIG_VERSION,
    # Global hotkeys. Defaults deliberately avoid system-reserved combinations
    # (Alt+Space = window menu, Ctrl+Space = IME toggle).
    "hotkeys": {
        "bloom": "Ctrl+Alt+B",
        "petal": "Ctrl+Alt+Space",
        "ink": "Alt+N",
        "icons": "Ctrl+Alt+I",
    },
    "theme": {
        "mode": "system",  # system | light | dark
        "accent": "wallpaper",  # auto | wallpaper | #RRGGBB
        "surface_mode": "acrylic",  # acrylic | mica | solid
        "material": "冷泉",  # preset name, see app/ui/materials.py
        "tint_color": "#1F3B3A",
        "tint_opacity": 52,  # acrylic tint strength, 0-100
    },
    "bloom": {
        "layout": "grid-3x2",
        "grid": {"cols": 3, "rows": 2},
        "hover_expand": True,
        "hover_delay_ms": 250,
        "max_items_per_bubble": 16,
        "dock": "right",  # right | left
        "dock_margin": 24,
        "dock_gap": 12,
        "groups": [],
    },
    "petal": {
        "width": 360,
        "hot_edge_px": 5,
        "hot_zone_enabled": True,
        "hot_zone_top": 90,
        "hot_zone_height": 140,
        "mode": "list",  # list | grid
        "hide_delay_ms": 450,
        "show_delay_ms": 120,
        "modules": {"notes": True, "paths": True, "terminal": True},
    },
    "ink": {
        "autosave": True,
        "editor_font_size": 14,
    },
    "root": {
        "items": [],  # [{name, path, icon}]
    },
    "stem": {
        "default_dir": "",
        "terminals": ["cmd", "powershell", "powershell-admin"],
    },
    "leaf": {
        "mode": "tracked",  # tracked | scan
        "roots": [],
        "refresh_minutes": 10,
        "max_items": 200,
    },
    "seek": {
        "es_path": "",  # empty = auto-discover
    },
    "launch": {
        "track_processes": True,
    },
    "ui": {
        "language": "zh-CN",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Dotted-path access wrapper around the JSON document."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else paths.CONFIG_FILE
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        cfg = cls(path)
        cfg._read()
        return cfg

    def _read(self) -> None:
        if not self.path.exists():
            log.info("no config at %s, writing defaults", self.path)
            self.save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root is not an object")
            self.data = _deep_merge(DEFAULTS, raw)
            self.data["version"] = CONFIG_VERSION
            # v2: switch the default accent source to the wallpaper.
            if int(raw.get("version", 1) or 1) < 2:
                if str(raw.get("theme", {}).get("accent", "auto")) == "auto":
                    self.data["theme"]["accent"] = "wallpaper"
                self.save()
            if int(raw.get("version", 1) or 1) < 3:
                # v3: material presets replace the flat tint.
                theme = self.data.setdefault("theme", {})
                theme["material"] = "冷泉"
                theme["tint_color"] = "#1F3B3A"
                theme["tint_opacity"] = 52
                self.save()
        except (OSError, ValueError) as exc:
            backup = self.path.with_name(
                f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}"
            )
            log.error("config unreadable (%s); moved to %s", exc, backup)
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.data = copy.deepcopy(DEFAULTS)
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        tmp.write_text(payload + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # -- accessors ---------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any, *, save: bool = True) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
        if save:
            self.save()


