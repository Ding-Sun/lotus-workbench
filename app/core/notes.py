"""Note storage for Ink.

One Markdown file per note, with a tiny front-matter block for the title and
timestamps, so a note is readable and editable in any text editor — no index
file that can drift out of sync.

    ---
    title: 无标题
    created: 2026-11-09T22:45:00
    updated: 2026-11-09T22:47:12
    ---
    body...
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import paths

log = logging.getLogger("lotus.notes")

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_UNSAFE = re.compile(r"[\\/:*?\"<>|]+")


@dataclass
class Note:
    path: Path
    title: str
    body: str
    created: datetime
    updated: datetime

    @property
    def preview(self) -> str:
        text = " ".join(self.body.split())
        return text[:80]


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _parse(path: Path) -> Note:
    stat = path.stat()
    fallback_time = datetime.fromtimestamp(stat.st_mtime)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raw = ""

    title = ""
    created = fallback_time
    updated = fallback_time
    body = raw

    match = _FRONT_MATTER.match(raw)
    if match:
        body = raw[match.end() :]
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "title":
                title = value
            elif key in ("created", "updated"):
                try:
                    stamp = datetime.fromisoformat(value)
                except ValueError:
                    continue
                if key == "created":
                    created = stamp
                else:
                    updated = stamp

    if not title:
        first = body.strip().splitlines()[0] if body.strip() else ""
        title = first.lstrip("# ").strip() or path.stem

    return Note(
        path=path,
        title=title,
        body=body.lstrip("\r\n"),
        created=created,
        updated=updated,
    )


def humanize(moment: datetime) -> str:
    delta = _now() - moment
    if delta < timedelta(minutes=1):
        return "刚刚"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)} 分钟前"
    if delta < timedelta(hours=6):
        return f"{int(delta.total_seconds() // 3600)} 小时前"
    if moment.date() == _now().date():
        return moment.strftime("今天 %H:%M")
    return moment.strftime("%m-%d %H:%M")


class NotesStore(QObject):
    changed = Signal()

    def __init__(self, directory: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.directory = Path(directory) if directory else paths.NOTES_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    # -- reads -------------------------------------------------------------
    def all(self) -> list[Note]:
        notes: list[Note] = []
        for path in self.directory.glob("*.md"):
            try:
                notes.append(_parse(path))
            except OSError:
                log.warning("unreadable note: %s", path, exc_info=True)
        notes.sort(key=lambda note: note.updated, reverse=True)
        return notes

    def recent(self, count: int = 3) -> list[Note]:
        return self.all()[:count]

    def search(self, query: str) -> list[Note]:
        needle = query.strip().lower()
        notes = self.all()
        if not needle:
            return notes
        return [
            note
            for note in notes
            if needle in note.title.lower() or needle in note.body.lower()
        ]

    def load(self, path: Path) -> Note | None:
        if not path.exists():
            return None
        try:
            return _parse(path)
        except OSError:
            return None

    # -- writes ------------------------------------------------------------
    def save(self, title: str, body: str, path: Path | None = None) -> Note:
        now = _now()
        title = " ".join(title.split()) or "无标题"

        if path is not None and path.exists():
            note = _parse(path)
            note.title = title
            note.body = body
            note.updated = now
            target = path
        else:
            target = self._new_path(title)
            note = Note(path=target, title=title, body=body, created=now, updated=now)

        target.write_text(self._render(note), encoding="utf-8")
        self.changed.emit()
        log.info("note saved: %s", target.name)
        return note

    def delete(self, path: Path) -> bool:
        try:
            path.unlink()
        except OSError:
            log.warning("cannot delete note %s", path, exc_info=True)
            return False
        self.changed.emit()
        return True

    def is_empty(self, title: str, body: str) -> bool:
        return not body.strip() and not title.strip()

    # -- helpers -----------------------------------------------------------
    def _new_path(self, title: str) -> Path:
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        slug = _UNSAFE.sub("", title)[:24].strip() or "note"
        candidate = self.directory / f"{stamp}-{slug}.md"
        counter = 2
        while candidate.exists():
            candidate = self.directory / f"{stamp}-{slug}-{counter}.md"
            counter += 1
        return candidate

    @staticmethod
    def _render(note: Note) -> str:
        return (
            "---\n"
            f"title: {note.title}\n"
            f"created: {note.created.isoformat(timespec='seconds')}\n"
            f"updated: {note.updated.isoformat(timespec='seconds')}\n"
            "---\n"
            f"{note.body}\n"
        )
