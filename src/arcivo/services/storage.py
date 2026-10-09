"""Storage analyzer and duplicate detection (read-only — never deletes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..db.database import Database

METHODS = {
    "media_id": ("certain", "Same Telegram file (identical upload)"),
    "hash": ("certain", "Identical content (SHA-256 of downloaded file)"),
    "name_size": ("likely", "Same file name and size"),
    "size_duration": ("possible", "Same size and duration"),
}


@dataclass
class DuplicateGroup:
    method: str
    confidence: str
    key: str
    size: int
    members: list[dict[str, Any]] = field(default_factory=list)

    @property
    def wasted(self) -> int:
        return self.size * max(0, len(self.members) - 1)


class StorageService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def breakdown(self, account_id: int) -> dict[str, Any]:
        rows = self.db.query("SELECT category, count(*) AS n, coalesce(sum(file_size),0) AS bytes FROM messages "
                             "WHERE account_id = ? AND file_size IS NOT NULL GROUP BY category ORDER BY bytes DESC", (account_id,))
        cats = [dict(r) for r in rows]
        total = sum(c["bytes"] for c in cats)
        media = sum(c["bytes"] for c in cats if c["category"] in ("images", "videos", "audio", "voice", "stickers"))
        for c in cats:
            c["share"] = c["bytes"] / total if total else 0
        return {"total_bytes": total, "media_bytes": media, "documents_bytes": next(
            (c["bytes"] for c in cats if c["category"] == "documents"), 0), "categories": cats}

    def by_extension(self, account_id: int, limit: int = 30) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT coalesce(extension, '—') AS extension, count(*) AS n, coalesce(sum(file_size),0) AS bytes FROM messages "
            "WHERE account_id = ? AND file_size IS NOT NULL GROUP BY extension ORDER BY bytes DESC LIMIT ?", (account_id, limit))]

    def large_files(self, account_id: int, min_size: int = 0, category: str | None = None, limit: int = 200,
                    offset: int = 0, sort_desc: bool = True) -> list[dict[str, Any]]:
        params: list[Any] = [account_id, min_size]
        extra = ""
        if category:
            extra, params = " AND category = ?", [*params, category]
        return [dict(r) for r in self.db.query(
            "SELECT id, file_name, media_type, category, extension, file_size, date_ts, sender_name, chat_name FROM messages "
            f"WHERE account_id = ? AND file_size >= ?{extra} ORDER BY file_size {'DESC' if sort_desc else 'ASC'} LIMIT ? OFFSET ?",
            [*params, limit, offset])]

    def duplicates(self, account_id: int, method: str = "media_id", limit: int = 500) -> list[DuplicateGroup]:
        if method not in METHODS:
            raise ValueError(method)
        confidence = METHODS[method][0]
        if method == "media_id":
            key_sql, cond = "CAST(media_id AS TEXT)", "media_id IS NOT NULL"
            src = "messages m"
        elif method == "name_size":
            key_sql, cond = "lower(file_name) || '|' || file_size", "file_name IS NOT NULL AND file_size > 0"
            src = "messages m"
        elif method == "size_duration":
            key_sql, cond = "file_size || '|' || CAST(round(duration) AS INTEGER)", "duration IS NOT NULL AND file_size > 0"
            src = "messages m"
        else:
            key_sql, cond = "h.sha256", "1=1"
            src = "messages m JOIN file_hashes h ON h.account_id = m.account_id AND h.message_id = m.id"
        groups = self.db.query(
            f"SELECT {key_sql} AS k, count(*) AS n, max(m.file_size) AS size FROM {src} WHERE m.account_id = ? AND {cond} "
            f"GROUP BY k HAVING n > 1 ORDER BY size * (n - 1) DESC LIMIT ?", (account_id, limit))
        out: list[DuplicateGroup] = []
        for g in groups:
            members = self.db.query(
                f"SELECT m.id, m.file_name, m.media_type, m.file_size, m.date_ts, m.sender_name, m.chat_name FROM {src} "
                f"WHERE m.account_id = ? AND {cond} AND {key_sql} = ? ORDER BY m.date_ts", (account_id, g["k"]))
            out.append(DuplicateGroup(method, confidence, str(g["k"]), int(g["size"] or 0), [dict(r) for r in members]))
        return out

    def duplicate_summary(self, account_id: int) -> dict[str, Any]:
        summary = {}
        for method in ("media_id", "hash", "name_size", "size_duration"):
            groups = self.duplicates(account_id, method, limit=10000)
            summary[method] = {"groups": len(groups), "items": sum(len(g.members) for g in groups),
                               "wasted_bytes": sum(g.wasted for g in groups), "confidence": METHODS[method][0]}
        return summary


def keep_selection(group: DuplicateGroup, keep: str = "oldest") -> list[int]:
    """Return ids to *select* (not delete) leaving one copy: keep oldest/newest."""
    members = sorted(group.members, key=lambda m: m["date_ts"])
    keeper = members[0] if keep == "oldest" else members[-1]
    return [m["id"] for m in members if m["id"] != keeper["id"]]
