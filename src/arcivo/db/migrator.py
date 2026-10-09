"""Forward-only, versioned SQL migrations with automatic pre-migration backups."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from ..core.errors import DatabaseError
from .database import Database

log = logging.getLogger(__name__)
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def discover() -> list[Migration]:
    out: list[Migration] = []
    for entry in resources.files("arcivo.db.migrations").iterdir():
        m = _NAME.match(entry.name)
        if m:
            out.append(Migration(int(m.group(1)), m.group(2), entry.read_text(encoding="utf-8")))
    out.sort(key=lambda m: m.version)
    versions = [m.version for m in out]
    if len(set(versions)) != len(versions):
        raise DatabaseError("duplicate migration versions")
    return out


def current_version(db: Database) -> int:
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
               " applied_at INTEGER NOT NULL)")
    return int(db.scalar("SELECT coalesce(max(version), 0) FROM schema_migrations") or 0)


def pending(db: Database) -> list[Migration]:
    cur = current_version(db)
    return [m for m in discover() if m.version > cur]


def migrate(db: Database, backup_dir: Path | None = None) -> list[int]:
    todo = pending(db)
    if not todo:
        return []
    if backup_dir is not None and isinstance(db.path, Path) and db.path.exists() and current_version(db) > 0:
        target = backup_dir / f"{db.path.stem}.v{current_version(db)}.{int(time.time())}.bak.db"
        log.info("Backing up database before migration to %s", target.name)
        db.backup_to(target)
    applied: list[int] = []
    conn = db.conn
    for m in todo:
        log.info("Applying migration %04d_%s", m.version, m.name)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in _split(m.sql):
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                         (m.version, m.name, int(time.time())))
            conn.execute("COMMIT")
        except Exception as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise DatabaseError(f"migration {m.version} failed: {exc}") from exc
        applied.append(m.version)
    return applied


def _split(sql: str) -> list[str]:
    """Split a script into statements, keeping CREATE TRIGGER ... END; blocks intact."""
    statements: list[str] = []
    buf: list[str] = []
    in_trigger = False
    for line in sql.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        upper = stripped.upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if upper == "END;":
                statements.append("\n".join(buf))
                buf, in_trigger = [], False
        elif stripped.endswith(";"):
            statements.append("\n".join(buf))
            buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf))
    return statements
