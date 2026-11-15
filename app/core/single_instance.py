"""Single-instance guard.

Two layers:

* ``QLockFile`` in the data directory — authoritative, survives restarts and
  detects stale locks from crashed processes (PID is validated by Qt).
* ``QLocalServer`` — best-effort channel that tells the running copy to show
  itself. Named pipes are unavailable in some confined environments, so a
  failure here must never block startup.
"""

from __future__ import annotations

import getpass
import logging
import time

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import paths

log = logging.getLogger("lotus.instance")


class SingleInstance(QObject):
    message_received = Signal(str)

    def __init__(self, key: str = "lotus-workbench", parent: QObject | None = None) -> None:
        super().__init__(parent)
        try:
            user = getpass.getuser()
        except Exception:  # noqa: BLE001
            user = "user"
        self._name = f"{key}-{user}"
        self._lock = QLockFile(str(paths.HOME / "lotus.lock"))
        # A crashed run leaves a lock behind; let it expire instead of blocking
        # startup until the file is deleted by hand.
        self._lock.setStaleLockTime(30_000)
        self._server: QLocalServer | None = None
        self._owns_lock = False

    def acquire(self) -> bool:
        """Return True when this process owns the instance."""
        if not self._lock.tryLock(150):
            # A lock left behind by a killed process blocks every later start
            # (and pythonw exits silently), so treat anything older than two
            # minutes as stale and take it over.
            lock_path = paths.HOME / "lotus.lock"
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0
            if age > 120:
                log.warning("stale lock (%.0fs old); taking over", age)
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    log.warning("cannot remove stale lock", exc_info=True)
                if not self._lock.tryLock(150):
                    return False
            else:
                log.info("lock held by another instance (age %.0fs)", age)
                return False
        self._owns_lock = True

        # Optional IPC channel for "show yourself" messages.
        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        if server.listen(self._name):
            server.newConnection.connect(self._on_connection)
            self._server = server
        else:
            log.warning("local server unavailable (%s); messages disabled", server.errorString())
        return True

    def notify_existing(self, message: str = "show") -> None:
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(300):
            log.info("could not reach the running instance; it will be shown manually")
            return
        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._owns_lock:
            self._lock.unlock()
            self._owns_lock = False

    def _on_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            if conn is not None:
                conn.readyRead.connect(lambda c=conn: self._read(c))

    def _read(self, conn: QLocalSocket) -> None:
        payload = bytes(conn.readAll()).decode("utf-8", "replace").strip()
        if payload:
            log.info("instance message: %s", payload)
            self.message_received.emit(payload)
