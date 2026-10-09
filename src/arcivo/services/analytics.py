"""Statistics & analytics computed in SQL over the local index (offline)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db.database import Database
from ..search.sql import CompiledQuery

SIZE_BUCKETS = [(0, 100 * 1024, "< 100 KB"), (100 * 1024, 1024**2, "100 KB – 1 MB"), (1024**2, 10 * 1024**2, "1 – 10 MB"),
                (10 * 1024**2, 100 * 1024**2, "10 – 100 MB"), (100 * 1024**2, 1024**3, "100 MB – 1 GB"), (1024**3, 1 << 62, "> 1 GB")]
BUCKET_FMT = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m", "year": "%Y"}


@dataclass
class TimeRange:
    start_ts: int | None = None
    end_ts: int | None = None

    @classmethod
    def last(cls, days: int | None) -> TimeRange:
        return cls(int(time.time()) - days * 86400, None) if days else cls()

    def sql(self, params: list[Any]) -> str:
        conds = []
        if self.start_ts is not None:
            conds.append("date_ts >= ?")
            params.append(self.start_ts)
        if self.end_ts is not None:
            conds.append("date_ts < ?")
            params.append(self.end_ts)
        return (" AND " + " AND ".join(conds)) if conds else ""


def local_offset_s() -> int:
    off = datetime.now().astimezone().utcoffset()
    return int(off.total_seconds()) if off else 0


class AnalyticsService:
    def __init__(self, db: Database, tz_offset_s: int | None = None) -> None:
        self.db = db
        self.off = local_offset_s() if tz_offset_s is None else tz_offset_s

    def _where(self, account_id: int, rng: TimeRange | None, cq: CompiledQuery | None) -> tuple[str, list[Any]]:
        params: list[Any] = [account_id]
        where = "m.account_id = ?" + (rng.sql(params) if rng else "")
        if cq is not None:
            where += f" AND {cq.where}"
            params.extend(cq.params)
        return where, params

    def overview(self, account_id: int, rng: TimeRange | None = None, cq: CompiledQuery | None = None) -> dict[str, Any]:
        w, p = self._where(account_id, rng, cq)
        r = self.db.query(f"""
            SELECT count(*) AS messages,
              sum(media_type IN ('photo','video','video_note','animation','audio','voice','document','sticker')) AS files,
              sum(category = 'images') AS images, sum(category = 'videos') AS videos,
              sum(media_type = 'audio' OR (media_type = 'document' AND category = 'audio')) AS audio,
              sum(media_type = 'voice') AS voice, sum(media_type = 'document') AS documents,
              sum(media_type = 'link' OR link_count > 0) AS links, sum(media_type = 'text') AS texts,
              sum(media_type = 'sticker') AS stickers, sum(media_type = 'animation') AS gifs,
              coalesce(sum(file_size), 0) AS total_bytes,
              count(DISTINCT sender_id) AS senders,
              count(DISTINCT CASE WHEN chat_type = 'channel' THEN chat_id END) AS channels,
              count(DISTINCT CASE WHEN chat_type IN ('group','channel','user') THEN chat_id END) AS chats,
              sum(is_forward) AS forwarded, min(date_ts) AS first_ts, max(date_ts) AS last_ts,
              coalesce(sum(duration), 0) AS total_duration
            FROM messages m WHERE {w}""", p)[0]
        out = {k: (r[k] or 0) for k in r.keys()}  # noqa: SIM118 (sqlite3.Row)
        now = int(time.time())
        for label, days in (("last_24h", 1), ("last_7d", 7), ("last_30d", 30), ("last_365d", 365)):
            out[label] = int(self.db.scalar(f"SELECT count(*) FROM messages m WHERE {w} AND date_ts >= ?", [*p, now - days * 86400]) or 0)
        out["tagged"] = int(self.db.scalar(
            "SELECT count(DISTINCT message_id) FROM message_tags WHERE account_id = ?", (account_id,)) or 0)
        return out

    def timeline(self, account_id: int, bucket: str = "month", rng: TimeRange | None = None, by_type: bool = False,
                 cq: CompiledQuery | None = None) -> list[dict[str, Any]]:
        fmt = BUCKET_FMT[bucket]
        w, p = self._where(account_id, rng, cq)
        group = ", media_type" if by_type else ""
        rows = self.db.query(f"SELECT strftime('{fmt}', date_ts + {self.off}, 'unixepoch') AS bucket{group}, count(*) AS n, "
                             f"coalesce(sum(file_size),0) AS bytes FROM messages m WHERE {w} GROUP BY bucket{group} ORDER BY bucket", p)
        return [dict(r) for r in rows]

    def growth(self, account_id: int, bucket: str = "month") -> list[dict[str, Any]]:
        total_n = total_b = 0
        out = []
        for r in self.timeline(account_id, bucket):
            total_n += r["n"]
            total_b += r["bytes"]
            out.append({"bucket": r["bucket"], "messages": total_n, "bytes": total_b})
        return out

    def by_type(self, account_id: int, rng: TimeRange | None = None, cq: CompiledQuery | None = None) -> list[dict[str, Any]]:
        w, p = self._where(account_id, rng, cq)
        return [dict(r) for r in self.db.query(
            f"SELECT media_type, count(*) AS n, coalesce(sum(file_size),0) AS bytes, avg(file_size) AS avg_bytes "
            f"FROM messages m WHERE {w} GROUP BY media_type ORDER BY n DESC", p)]

    def by_category(self, account_id: int, rng: TimeRange | None = None) -> list[dict[str, Any]]:
        w, p = self._where(account_id, rng, None)
        return [dict(r) for r in self.db.query(
            f"SELECT category, count(*) AS n, coalesce(sum(file_size),0) AS bytes, avg(file_size) AS avg_bytes, "
            f"max(file_size) AS max_bytes FROM messages m WHERE {w} GROUP BY category ORDER BY bytes DESC", p)]

    def hours(self, account_id: int, rng: TimeRange | None = None) -> list[int]:
        w, p = self._where(account_id, rng, None)
        counts = [0] * 24
        for r in self.db.query(f"SELECT CAST(strftime('%H', date_ts + {self.off}, 'unixepoch') AS INTEGER) AS h, count(*) AS n "
                               f"FROM messages m WHERE {w} GROUP BY h", p):
            counts[r["h"]] = r["n"]
        return counts

    def weekdays(self, account_id: int, rng: TimeRange | None = None) -> list[int]:
        """Counts per weekday, Monday=0 … Sunday=6."""
        w, p = self._where(account_id, rng, None)
        counts = [0] * 7
        for r in self.db.query(f"SELECT CAST(strftime('%w', date_ts + {self.off}, 'unixepoch') AS INTEGER) AS d, count(*) AS n "
                               f"FROM messages m WHERE {w} GROUP BY d", p):
            counts[(r["d"] + 6) % 7] = r["n"]
        return counts

    def heatmap(self, account_id: int, rng: TimeRange | None = None) -> list[list[int]]:
        w, p = self._where(account_id, rng, None)
        grid = [[0] * 24 for _ in range(7)]
        for r in self.db.query(f"SELECT CAST(strftime('%w', date_ts + {self.off}, 'unixepoch') AS INTEGER) AS d, "
                               f"CAST(strftime('%H', date_ts + {self.off}, 'unixepoch') AS INTEGER) AS h, count(*) AS n "
                               f"FROM messages m WHERE {w} GROUP BY d, h", p):
            grid[(r["d"] + 6) % 7][r["h"]] = r["n"]
        return grid

    def top_days(self, account_id: int, n: int = 10, rng: TimeRange | None = None) -> list[dict[str, Any]]:
        w, p = self._where(account_id, rng, None)
        return [dict(r) for r in self.db.query(
            f"SELECT strftime('%Y-%m-%d', date_ts + {self.off}, 'unixepoch') AS day, count(*) AS n FROM messages m WHERE {w} "
            f"GROUP BY day ORDER BY n DESC LIMIT ?", [*p, n])]

    def top(self, account_id: int, what: str, n: int = 10, rng: TimeRange | None = None) -> list[dict[str, Any]]:
        w, p = self._where(account_id, rng, None)
        if what == "senders":
            sql = (f"SELECT coalesce(sender_name, sender_username, 'Unknown') AS label, sender_id AS key, count(*) AS n, "
                   f"coalesce(sum(file_size),0) AS bytes FROM messages m WHERE {w} AND (sender_id IS NOT NULL OR sender_name IS NOT NULL) "
                   f"GROUP BY coalesce(sender_id, sender_name) ORDER BY n DESC LIMIT ?")
        elif what == "chats":
            sql = (f"SELECT coalesce(chat_name, 'Unknown') AS label, chat_id AS key, chat_type, count(*) AS n, coalesce(sum(file_size),0) AS bytes "
                   f"FROM messages m WHERE {w} AND chat_id IS NOT NULL GROUP BY chat_id ORDER BY n DESC LIMIT ?")
        elif what == "extensions":
            sql = (f"SELECT extension AS label, extension AS key, count(*) AS n, coalesce(sum(file_size),0) AS bytes FROM messages m "
                   f"WHERE {w} AND extension IS NOT NULL GROUP BY extension ORDER BY n DESC LIMIT ?")
        elif what == "domains":
            sql = (f"SELECT l.domain AS label, l.domain AS key, count(*) AS n, 0 AS bytes FROM links l JOIN messages m "
                   f"ON m.account_id = l.account_id AND m.id = l.message_id WHERE {w} AND l.domain IS NOT NULL "
                   f"GROUP BY l.domain ORDER BY n DESC LIMIT ?")
        else:
            raise ValueError(what)
        return [dict(r) for r in self.db.query(sql, [*p, n])]

    def size_distribution(self, account_id: int, rng: TimeRange | None = None) -> list[dict[str, Any]]:
        w, p = self._where(account_id, rng, None)
        out = []
        for lo, hi, label in SIZE_BUCKETS:
            r = self.db.query(f"SELECT count(*) AS n, coalesce(sum(file_size),0) AS bytes FROM messages m WHERE {w} "
                              f"AND file_size >= ? AND file_size < ?", [*p, lo, hi])[0]
            out.append({"label": label, "n": r["n"], "bytes": r["bytes"]})
        return out

    def largest(self, account_id: int, n: int = 20, category: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [account_id]
        extra = ""
        if category:
            extra = " AND category = ?"
            params.append(category)
        return [dict(r) for r in self.db.query(
            "SELECT id, file_name, media_type, category, extension, file_size, date_ts, sender_name, chat_name, duration "
            f"FROM messages WHERE account_id = ? AND file_size IS NOT NULL{extra} ORDER BY file_size DESC LIMIT ?", [*params, n])]

    def media_averages(self, account_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT media_type, avg(duration) AS avg_duration, max(duration) AS max_duration, avg(file_size) AS avg_bytes, "
            "avg(width) AS avg_width, avg(height) AS avg_height FROM messages WHERE account_id = ? AND duration IS NOT NULL "
            "GROUP BY media_type", (account_id,))]
