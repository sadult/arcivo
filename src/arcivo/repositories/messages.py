"""Message index repository (Telegram is the source of truth; this is a cache/index)."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from urllib.parse import urlparse

from ..db.database import Database
from ..domain.models import MessageRecord
from ..search.sql import CompiledQuery

COLUMNS = [
    "id", "date_ts", "edit_ts", "media_type", "category", "text", "file_name", "extension", "mime_type",
    "file_size", "duration", "width", "height", "performer", "audio_title", "media_id", "dc_id", "sender_id",
    "sender_name", "sender_username", "chat_id", "chat_name", "chat_type", "is_forward", "fwd_date_ts",
    "fwd_msg_id", "reply_to_id", "grouped_id", "saved_peer_id", "link_count", "views", "has_thumb", "extra_json",
]
LIST_COLUMNS = ("m.id, m.date_ts, m.edit_ts, m.media_type, m.category, substr(m.text, 1, 300) AS text, m.file_name, "
                "m.extension, m.mime_type, m.file_size, m.duration, m.width, m.height, m.performer, m.audio_title, "
                "m.sender_name, m.sender_username, m.chat_name, m.chat_type, m.is_forward, m.grouped_id, m.link_count, "
                "m.has_thumb, m.remote_deleted, "
                "(SELECT group_concat(tg.name, ',') FROM message_tags mt JOIN tags tg ON tg.id = mt.tag_id "
                " WHERE mt.account_id = m.account_id AND mt.message_id = m.id) AS tags, "
                "(SELECT mk.flagged FROM message_marks mk WHERE mk.account_id = m.account_id AND mk.message_id = m.id) AS flagged")


def _row_values(account_id: int, r: MessageRecord, now: int) -> tuple:
    return (
        account_id, r.id, r.date_ts, r.edit_ts, r.media_type.value, (r.category.value if r.category else "other"), r.text or "",
        r.file_name, r.extension, r.mime_type, r.file_size, r.duration, r.width, r.height, r.performer, r.audio_title,
        r.media_id, r.dc_id, r.sender_id, r.sender_name, r.sender_username, r.chat_id, r.chat_name, r.chat_type,
        int(r.is_forward), r.fwd_date_ts, r.fwd_msg_id, r.reply_to_id, r.grouped_id, r.saved_peer_id, len(r.links),
        r.views, int(r.has_thumb), json.dumps(r.extra, ensure_ascii=False) if r.extra else None, now,
    )


_UPSERT = (
    "INSERT INTO messages (account_id, " + ", ".join(COLUMNS) + ", synced_at) VALUES ("
    + ", ".join("?" * (len(COLUMNS) + 2)) + ") ON CONFLICT(account_id, id) DO UPDATE SET "
    + ", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "id") + ", synced_at = excluded.synced_at, remote_deleted = 0"
)


class MessageRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ write
    def upsert_many(self, account_id: int, records: Iterable[MessageRecord]) -> int:
        now = int(time.time())
        n = 0
        with self.db.transaction() as c:
            for r in records:
                c.execute(_UPSERT, _row_values(account_id, r, now))
                c.execute("DELETE FROM links WHERE account_id = ? AND message_id = ?", (account_id, r.id))
                for url in dict.fromkeys(r.links):
                    domain = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower().removeprefix("www.")
                    c.execute("INSERT OR IGNORE INTO links(account_id, message_id, url, domain) VALUES (?,?,?,?)",
                              (account_id, r.id, url, domain or None))
                for pid, ptype, name, uname in (
                    (r.sender_id, "user", r.sender_name, r.sender_username),
                    (r.chat_id, r.chat_type or "channel", r.chat_name, None),
                ):
                    if pid is not None:
                        c.execute("INSERT INTO peers(account_id, peer_id, peer_type, name, username) VALUES (?,?,?,?,?) "
                                  "ON CONFLICT DO UPDATE SET name = coalesce(excluded.name, name), "
                                  "username = coalesce(excluded.username, username)", (account_id, pid, ptype, name, uname))
                n += 1
        return n

    def delete_local(self, account_id: int, ids: Iterable[int]) -> int:
        ids = list(ids)
        total = 0
        with self.db.transaction() as c:
            for chunk in _chunks(ids, 500):
                ph = ",".join("?" * len(chunk))
                total += c.execute(f"DELETE FROM messages WHERE account_id = ? AND id IN ({ph})", (account_id, *chunk)).rowcount
                c.execute(f"DELETE FROM message_tags WHERE account_id = ? AND message_id IN ({ph})", (account_id, *chunk))
                c.execute(f"DELETE FROM message_marks WHERE account_id = ? AND message_id IN ({ph})", (account_id, *chunk))
        return total

    def mark_remote_deleted(self, account_id: int, ids: Iterable[int]) -> int:
        n = 0
        with self.db.transaction() as c:
            for chunk in _chunks(list(ids), 500):
                ph = ",".join("?" * len(chunk))
                n += c.execute(f"UPDATE messages SET remote_deleted = 1 WHERE account_id = ? AND id IN ({ph})",
                               (account_id, *chunk)).rowcount
        return n

    # ------------------------------------------------------------------ read
    def get(self, account_id: int, message_id: int) -> sqlite3.Row | None:
        rows = self.db.query("SELECT * FROM messages WHERE account_id = ? AND id = ?", (account_id, message_id))
        return rows[0] if rows else None

    def links_for(self, account_id: int, message_id: int) -> list[str]:
        return [r[0] for r in self.db.query("SELECT url FROM links WHERE account_id = ? AND message_id = ?",
                                             (account_id, message_id))]

    def count(self, account_id: int, cq: CompiledQuery) -> int:
        return int(self.db.scalar(f"SELECT count(*) FROM messages m WHERE m.account_id = ? AND {cq.where}",
                                  [account_id, *cq.params]) or 0)

    def page(self, account_id: int, cq: CompiledQuery, offset: int, limit: int) -> list[sqlite3.Row]:
        sql = (f"SELECT {LIST_COLUMNS} FROM messages m WHERE m.account_id = ? AND {cq.where} "
               f"ORDER BY {cq.order_by} LIMIT ? OFFSET ?")
        return self.db.query(sql, [account_id, *cq.params, limit, offset])

    def iter_rows(self, account_id: int, cq: CompiledQuery, chunk: int = 1000, full: bool = True) -> Iterator[sqlite3.Row]:
        """Stream matching rows in keyset-friendly chunks without loading everything into RAM."""
        cols = "m.*" if full else LIST_COLUMNS
        offset = 0
        while True:
            rows = self.db.query(f"SELECT {cols} FROM messages m WHERE m.account_id = ? AND {cq.where} "
                                 f"ORDER BY {cq.order_by} LIMIT ? OFFSET ?", [account_id, *cq.params, chunk, offset])
            if not rows:
                return
            yield from rows
            offset += len(rows)

    def ids(self, account_id: int, cq: CompiledQuery) -> list[int]:
        return [r[0] for r in self.db.query(f"SELECT m.id FROM messages m WHERE m.account_id = ? AND {cq.where} "
                                            f"ORDER BY {cq.order_by}", [account_id, *cq.params])]

    def rows_by_ids(self, account_id: int, ids: list[int]) -> list[sqlite3.Row]:
        out: list[sqlite3.Row] = []
        for chunk in _chunks(ids, 500):
            ph = ",".join("?" * len(chunk))
            out.extend(self.db.query(f"SELECT * FROM messages WHERE account_id = ? AND id IN ({ph})", (account_id, *chunk)))
        order = {mid: i for i, mid in enumerate(ids)}
        out.sort(key=lambda r: order.get(r["id"], 0))
        return out

    def max_id(self, account_id: int) -> int:
        return int(self.db.scalar("SELECT coalesce(max(id), 0) FROM messages WHERE account_id = ?", (account_id,)) or 0)

    def recent_ids(self, account_id: int, n: int) -> list[int]:
        return [r[0] for r in self.db.query("SELECT id FROM messages WHERE account_id = ? ORDER BY id DESC LIMIT ?",
                                            (account_id, n))]

    def all_ids(self, account_id: int) -> set[int]:
        return {r[0] for r in self.db.query("SELECT id FROM messages WHERE account_id = ?", (account_id,))}

    def total(self, account_id: int) -> int:
        return int(self.db.scalar("SELECT count(*) FROM messages WHERE account_id = ?", (account_id,)) or 0)

    def peers(self, account_id: int, kind: str) -> list[sqlite3.Row]:
        col = "sender" if kind == "sender" else "chat"
        return self.db.query(f"SELECT {col}_id AS peer_id, {col}_name AS name, count(*) AS n FROM messages "
                             f"WHERE account_id = ? AND {col}_id IS NOT NULL GROUP BY {col}_id ORDER BY n DESC",
                             (account_id,))


def _chunks(seq: list[int], n: int) -> Iterator[list[int]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def ids_range(db: Database, account_id: int, cq: CompiledQuery, offset: int, limit: int) -> list[int]:
    return [r[0] for r in db.query(f"SELECT m.id FROM messages m WHERE m.account_id = ? AND {cq.where} ORDER BY {cq.order_by} "
                                   "LIMIT ? OFFSET ?", [account_id, *cq.params, limit, offset])]


def count_within(db: Database, account_id: int, cq: CompiledQuery, ids: list[int]) -> int:
    n = 0
    for chunk in _chunks(ids, 500):
        ph = ",".join("?" * len(chunk))
        n += int(db.scalar(f"SELECT count(*) FROM messages m WHERE m.account_id = ? AND {cq.where} AND m.id IN ({ph})",
                           [account_id, *cq.params, *chunk]) or 0)
    return n
