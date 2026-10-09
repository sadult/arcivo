"""SQLite access: per-thread connections, WAL, pragmas, transactions."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..core.errors import DatabaseError

log = logging.getLogger(__name__)


class Database:
    """Thread-aware SQLite wrapper.

    Each thread gets its own connection (SQLite connections must not be shared
    across threads); WAL mode allows the GUI to read while a sync job writes.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else path
        self._local = threading.local()
        self._lock = threading.RLock()
        self._all: list[sqlite3.Connection] = []
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # shared in-memory DB for tests
        self._uri = (f"file:arcivo-mem-{id(self)}?mode=memory&cache=shared" if path == ":memory:" else None)
        self._keepalive = self._open() if self._uri else None

    def _open(self) -> sqlite3.Connection:
        try:
            if self._uri:
                conn = sqlite3.connect(self._uri, uri=True, check_same_thread=False, timeout=30)
            else:
                conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._uri:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -32000")  # ~32 MB page cache per connection
        conn.execute("PRAGMA busy_timeout = 30000")
        with self._lock:
            self._all.append(conn)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._open()
            self._local.conn = c
        return c

    def execute(self, sql: str, params: tuple | list | dict = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            log.error("SQL error: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def query(self, sql: str, params: tuple | list | dict = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def scalar(self, sql: str, params: tuple | list | dict = ()) -> object:
        row = self.execute(sql, params).fetchone()
        return None if row is None else row[0]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        c = self.conn
        if c.in_transaction:  # nested: join the outer transaction
            yield c
            return
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise

    def size_bytes(self) -> int:
        if not isinstance(self.path, Path) or not self.path.exists():
            return 0
        total = self.path.stat().st_size
        for suffix in ("-wal", "-shm"):
            p = self.path.with_name(self.path.name + suffix)
            if p.exists():
                total += p.stat().st_size
        return total

    def vacuum(self) -> None:
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")

    def integrity_check(self) -> str:
        return str(self.scalar("PRAGMA integrity_check"))

    def optimize_fts(self) -> None:
        self.execute("INSERT INTO messages_fts(messages_fts) VALUES ('optimize')")

    def backup_to(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        dst = sqlite3.connect(str(target))
        try:
            self.conn.backup(dst)
        finally:
            dst.close()

    def close(self) -> None:
        with self._lock:
            for c in self._all:
                try:
                    c.close()
                except sqlite3.Error:
                    pass
            self._all.clear()
        self._local = threading.local()
