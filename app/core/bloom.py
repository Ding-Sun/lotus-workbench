"""Bloom data model: bubble groups, items, persistence, launching."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

log = logging.getLogger("lotus.bloom")


@dataclass
class BloomItem:
    name: str
    target: str
    type: str = "app"  # app | file | url

    def to_dict(self) -> dict:
        return {"name": self.name, "target": self.target, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict) -> "BloomItem":
        return cls(
            name=str(data.get("name") or ""),
            target=str(data.get("target") or ""),
            type=str(data.get("type") or "app"),
        )


@dataclass
class BloomGroup:
    name: str
    items: list[BloomItem] = field(default_factory=list)
    col: int = 0
    row: int = 0
    x: int | None = None
    y: int | None = None
    cols: int = 3
    rows: int = 0  # 0 = auto (use global max_items)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "col": self.col,
            "row": self.row,
            "cols": self.cols,
            "rows": self.rows,
            "items": [item.to_dict() for item in self.items],
        }
        if self.x is not None and self.y is not None:
            data["x"] = self.x
            data["y"] = self.y
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BloomGroup":
        x = data.get("x")
        y = data.get("y")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            name=str(data.get("name") or "未命名分组"),
            col=int(data.get("col") or 0),
            row=int(data.get("row") or 0),
            x=int(x) if isinstance(x, (int, float)) else None,
            y=int(y) if isinstance(y, (int, float)) else None,
            cols=max(1, min(6, int(data.get("cols") or 3))),
            rows=max(0, min(6, int(data.get("rows") or 0))),
            items=[BloomItem.from_dict(raw) for raw in data.get("items", []) if isinstance(raw, dict)],
        )


def load_groups(cfg: Config) -> list[BloomGroup]:
    raw = cfg.get("bloom.groups", [])
    groups = [BloomGroup.from_dict(entry) for entry in raw if isinstance(entry, dict)]
    return groups


def save_groups(cfg: Config, groups: list[BloomGroup]) -> None:
    cfg.set("bloom.groups", [group.to_dict() for group in groups])


def _seed() -> list[BloomGroup]:
    return [
        BloomGroup(
            name="系统",
            col=0,
            row=0,
            items=[
                BloomItem("资源管理器", "explorer.exe", "app"),
                BloomItem("记事本", "notepad.exe", "app"),
                BloomItem("计算器", "calc.exe", "app"),
                BloomItem("画图", "mspaint.exe", "app"),
            ],
        ),
        BloomGroup(
            name="网络",
            col=1,
            row=0,
            items=[
                BloomItem("GitHub", "https://github.com", "url"),
                BloomItem("哔哩哔哩", "https://www.bilibili.com", "url"),
                BloomItem("知乎", "https://www.zhihu.com", "url"),
            ],
        ),
        BloomGroup(
            name="工作区",
            col=2,
            row=0,
            items=[
                BloomItem("用户目录", str(Path.home()), "file"),
                BloomItem("下载", str(Path.home() / "Downloads"), "file"),
                BloomItem("文档", str(Path.home() / "Documents"), "file"),
            ],
        ),
    ]


def ensure_default_groups(cfg: Config) -> None:
    if load_groups(cfg):
        return
    save_groups(cfg, _seed())
    log.info("seeded default bloom groups")


def resolve_target(target: str) -> str:
    """Turn bare executable names into full paths when possible."""
    if not target:
        return target
    if os.path.exists(target):
        return target
    found = shutil.which(target)
    return found or target


def open_item(item: BloomItem) -> bool:
    """Launch one entry. URLs go to the browser, everything else to the shell."""
    target = item.target.strip()
    if not target:
        return False
    if item.type == "url" or target.lower().startswith(("http://", "https://")):
        try:
            webbrowser.open(target)
            return True
        except Exception:  # noqa: BLE001
            log.warning("cannot open url: %s", target, exc_info=True)
            return False
    target = resolve_target(target)
    try:
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
        return True
    except OSError:
        log.warning("cannot open %s", target, exc_info=True)
        return False


def item_name_from_path(path: str) -> str:
    name = Path(path).name
    return name or path


def item_from_path(path: str) -> BloomItem:
    suffix = Path(path).suffix.lower()
    if suffix in (".url", ".website"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.lower().startswith("url="):
                    return BloomItem(item_name_from_path(path), line[4:].strip(), "url")
        except OSError:
            pass
    if suffix == ".lnk":
        return BloomItem(Path(path).stem, path, "app")
    return BloomItem(item_name_from_path(path), path, "file")
