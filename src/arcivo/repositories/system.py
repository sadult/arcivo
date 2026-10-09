"""Accounts, sync state, jobs, reports, cache registry and audit log."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from ..db.database import Database


class AccountRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure(self, telegram_user_id: int, display_name: str = "", username: str | None = None) -> int:
        with self.db.transaction() as c:
            c.execute("INSERT INTO accounts(telegram_user_id, display_name, username) VALUES (?,?,?) "
                      "ON CONFLICT(telegram_user_id) DO UPDATE SET display_name = excluded.display_name, "
                      "username = excluded.username", (telegram_user_id, display_name, username))
            aid = int(c.execute("SELECT id FROM accounts WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()[0])
            c.execute("INSERT OR IGNORE INTO sync_state(account_id) VALUES (?)", (aid,))
        return aid

    def first(self) -> sqlite3.Row | None:
        r = self.db.query("SELECT * FROM accounts ORDER BY id LIMIT 1")
        return r[0] if r else None

    def by_telegram_id(self, tid: int) -> sqlite3.Row | None:
        r = self.db.query("SELECT * FROM accounts WHERE telegram_user_id = ?", (tid,))
        return r[0] if r else None


class SyncStateRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, account_id: int) -> dict[str, Any]:
        r = self.db.query("SELECT * FROM sync_state WHERE account_id = ?", (account_id,))
        return dict(r[0]) if r else {"account_id": account_id, "initial_complete": 0, "checkpoint_id": 0, "max_message_id": 0,
                                     "last_full_sync": None, "last_incremental": None, "last_reconcile": None, "total_synced": 0}

    def update(self, account_id: int, **fields: Any) -> None:
        allowed = {"initial_complete", "checkpoint_id", "max_message_id", "last_full_sync", "last_incremental",
                   "last_reconcile", "total_synced"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        with self.db.transaction() as c:
            c.execute("INSERT OR IGNORE INTO sync_state(account_id) VALUES (?)", (account_id,))
            if sets:
                c.execute(f"UPDATE sync_state SET {', '.join(f'{k} = ?' for k in sets)} WHERE account_id = ?",
                          (*sets.values(), account_id))


class JobRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, job: dict[str, Any]) -> None:
        with self.db.transaction() as c:
            c.execute("INSERT INTO jobs(id, kind, title, status, params_json, progress_json, error, created_at, started_at, finished_at)"
                      " VALUES (:id, :kind, :title, :status, :params_json, :progress_json, :error, :created_at, :started_at, :finished_at)"
                      " ON CONFLICT(id) DO UPDATE SET status = excluded.status, progress_json = excluded.progress_json,"
                      " error = excluded.error, started_at = excluded.started_at, finished_at = excluded.finished_at", job)

    def list(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))

    def get(self, job_id: str) -> sqlite3.Row | None:
        r = self.db.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return r[0] if r else None

    def mark_interrupted(self) -> int:
        with self.db.transaction() as c:
            return c.execute("UPDATE jobs SET status = 'interrupted' WHERE status IN ('running','queued','paused')").rowcount

    def set_item(self, job_id: str, message_id: int, status: str, *, bytes_: int | None = None, path: str | None = None,
                 error: str | None = None) -> None:
        with self.db.transaction() as c:
            c.execute("INSERT INTO job_items(job_id, message_id, status, bytes, path, error) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT DO UPDATE SET status = excluded.status, bytes = excluded.bytes, path = excluded.path, "
                      "error = excluded.error", (job_id, message_id, status, bytes_, path, error))

    def items(self, job_id: str, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.db.query("SELECT * FROM job_items WHERE job_id = ? AND status = ?", (job_id, status))
        return self.db.query("SELECT * FROM job_items WHERE job_id = ?", (job_id,))

    def clear_finished(self) -> int:
        with self.db.transaction() as c:
            return c.execute("DELETE FROM jobs WHERE status IN ('completed','cancelled','failed','partial','interrupted')").rowcount


class ReportRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, job_id: str | None, kind: str, summary: dict[str, Any], json_path: str | None, html_path: str | None) -> int:
        with self.db.transaction() as c:
            cur = c.execute("INSERT INTO reports(job_id, kind, summary_json, json_path, html_path, created_at) VALUES (?,?,?,?,?,?)",
                            (job_id, kind, json.dumps(summary, ensure_ascii=False), json_path, html_path, int(time.time())))
        return int(cur.lastrowid or 0)

    def list(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,))

    def for_job(self, job_id: str) -> sqlite3.Row | None:
        r = self.db.query("SELECT * FROM reports WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,))
        return r[0] if r else None


class CacheRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def put(self, account_id: int, message_id: int, kind: str, path: str, size: int, sha256: str | None = None) -> None:
        now = int(time.time())
        with self.db.transaction() as c:
            c.execute("INSERT INTO cache_entries(account_id, message_id, kind, path, size, sha256, created_at, last_used) "
                      "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET path = excluded.path, size = excluded.size, "
                      "sha256 = excluded.sha256, last_used = excluded.last_used", (account_id, message_id, kind, path, size, sha256, now, now))

    def get(self, account_id: int, message_id: int, kind: str) -> sqlite3.Row | None:
        r = self.db.query("SELECT * FROM cache_entries WHERE account_id = ? AND message_id = ? AND kind = ?",
                          (account_id, message_id, kind))
        return r[0] if r else None

    def touch(self, account_id: int, message_id: int, kind: str) -> None:
        self.db.execute("UPDATE cache_entries SET last_used = ? WHERE account_id = ? AND message_id = ? AND kind = ?",
                        (int(time.time()), account_id, message_id, kind))
        self.db.conn.commit()

    def stats(self) -> list[sqlite3.Row]:
        return self.db.query("SELECT kind, count(*) AS files, coalesce(sum(size),0) AS bytes, max(last_used) AS last_used "
                             "FROM cache_entries GROUP BY kind")

    def oldest(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM cache_entries ORDER BY last_used ASC LIMIT ?", (limit,))

    def remove(self, rows: list[sqlite3.Row]) -> None:
        with self.db.transaction() as c:
            for r in rows:
                c.execute("DELETE FROM cache_entries WHERE account_id = ? AND message_id = ? AND kind = ?",
                          (r["account_id"], r["message_id"], r["kind"]))

    def clear(self, kind: str | None = None) -> list[sqlite3.Row]:
        rows = self.db.query("SELECT * FROM cache_entries" + (" WHERE kind = ?" if kind else ""), (kind,) if kind else ())
        with self.db.transaction() as c:
            c.execute("DELETE FROM cache_entries" + (" WHERE kind = ?" if kind else ""), (kind,) if kind else ())
        return rows

    def set_hash(self, account_id: int, message_id: int, sha256: str, size: int) -> None:
        with self.db.transaction() as c:
            c.execute("INSERT OR REPLACE INTO file_hashes(account_id, message_id, sha256, size) VALUES (?,?,?,?)",
                      (account_id, message_id, sha256, size))


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, action: str, **details: Any) -> None:
        with self.db.transaction() as c:
            c.execute("INSERT INTO audit_log(ts, action, details) VALUES (?,?,?)",
                      (int(time.time()), action, json.dumps(details, ensure_ascii=False, default=str)))

    def list(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
