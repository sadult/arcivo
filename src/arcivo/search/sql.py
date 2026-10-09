"""Compile a :class:`ParsedQuery` into a parameterised SQL WHERE clause.

All user values are bound as parameters; only whitelisted column names are
interpolated, so the builder is safe against SQL injection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

from ..core.errors import SearchSyntaxError
from ..domain.formatting import parse_date, parse_duration, parse_size
from ..domain.models import FILE_BEARING
from .query import Clause, Node, OrGroup, ParsedQuery

_FILE_TYPES = tuple(sorted(t.value for t in FILE_BEARING))
_IN_FILE = "media_type IN (" + ",".join(f"'{t}'" for t in _FILE_TYPES) + ")"

TYPE_SQL: dict[str, str] = {
    "text": "media_type = 'text'",
    "photo": "media_type = 'photo'",
    "image": "category = 'images'",
    "video": "(media_type IN ('video','video_note') OR (media_type = 'document' AND category = 'videos'))",
    "video_note": "media_type = 'video_note'",
    "animation": "media_type = 'animation'",
    "audio": "(media_type = 'audio' OR (media_type = 'document' AND category = 'audio'))",
    "voice": "media_type = 'voice'",
    "document": "media_type = 'document'",
    "file": _IN_FILE,
    "media": _IN_FILE,
    "link": "(media_type = 'link' OR link_count > 0)",
    "sticker": "media_type = 'sticker'",
    "contact": "media_type = 'contact'",
    "location": "media_type IN ('location','venue')",
    "venue": "media_type = 'venue'",
    "poll": "media_type = 'poll'",
    "dice": "media_type = 'dice'",
    "game": "media_type = 'game'",
    "invoice": "media_type = 'invoice'",
    "story": "media_type = 'story'",
    "other": "media_type = 'other'",
}
TYPE_ALIASES = {
    "img": "image", "images": "image", "picture": "image", "pic": "image", "photos": "photo",
    "videos": "video", "round": "video_note", "videonote": "video_note", "gif": "animation", "gifs": "animation",
    "music": "audio", "song": "audio", "audios": "audio", "voices": "voice", "vn": "voice",
    "doc": "document", "docs": "document", "documents": "document", "files": "file",
    "url": "link", "links": "link", "url_link": "link", "geo": "location", "stickers": "sticker",
    "msg": "text", "message": "text", "texts": "text",
}
HAS_SQL = {
    "media": _IN_FILE, "file": _IN_FILE,
    "link": "(media_type = 'link' OR link_count > 0)", "links": "(media_type = 'link' OR link_count > 0)",
    "text": "text <> ''", "caption": f"(text <> '' AND {_IN_FILE})",
    "tag": "EXISTS (SELECT 1 FROM message_tags mt WHERE mt.account_id = m.account_id AND mt.message_id = m.id)",
    "note": "EXISTS (SELECT 1 FROM message_marks mk WHERE mk.account_id = m.account_id AND mk.message_id = m.id AND mk.note IS NOT NULL AND mk.note <> '')",
    "thumb": "has_thumb = 1",
    "reply": "reply_to_id IS NOT NULL",
    "forward": "is_forward = 1",
}
IS_SQL = {
    "flagged": "EXISTS (SELECT 1 FROM message_marks mk WHERE mk.account_id = m.account_id AND mk.message_id = m.id AND mk.flagged = 1)",
    "starred": "EXISTS (SELECT 1 FROM message_marks mk WHERE mk.account_id = m.account_id AND mk.message_id = m.id AND mk.starred = 1)",
    "forwarded": "is_forward = 1", "forward": "is_forward = 1",
    "own": "is_forward = 0",
    "reply": "reply_to_id IS NOT NULL",
    "album": "grouped_id IS NOT NULL",
    "edited": "edit_ts IS NOT NULL",
    "deleted": "remote_deleted = 1",
    "tagged": HAS_SQL["tag"],
    "untagged": "NOT " + HAS_SQL["tag"],
}
SORT_SQL = {
    "date": "m.date_ts", "size": "m.file_size", "name": "m.file_name COLLATE NOCASE", "type": "m.media_type",
    "sender": "m.sender_name COLLATE NOCASE", "chat": "m.chat_name COLLATE NOCASE", "duration": "m.duration",
    "id": "m.id", "ext": "m.extension", "edited": "m.edit_ts",
}
_CMP = re.compile(r"^(>=|<=|>|<|=)?\s*(.+)$")


@dataclass
class CompiledQuery:
    where: str = "1=1"
    params: list[object] = field(default_factory=list)
    order_by: str = "m.date_ts DESC, m.id DESC"
    sort_key: str = "date"
    sort_desc: bool = True


def fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


class SqlBuilder:
    def __init__(self, tz: tzinfo | None = None) -> None:
        self.tz = tz or datetime.now().astimezone().tzinfo

    # ---------------------------------------------------------------- dates
    def _day_start_ts(self, d: date) -> int:
        return int(datetime.combine(d, time.min, tzinfo=self.tz).timestamp())

    # ---------------------------------------------------------------- public
    def compile(self, pq: ParsedQuery, default_sort: str = "date", default_desc: bool = True) -> CompiledQuery:
        params: list[object] = []
        parts = [self._node(n, params) for n in pq.nodes]
        where = " AND ".join(p for p in parts if p) or "1=1"
        key = pq.sort_key or default_sort
        desc = default_desc if pq.sort_desc is None else pq.sort_desc
        return CompiledQuery(where, params, order_clause(key, desc), key, desc)

    def _node(self, n: Node, params: list[object]) -> str:
        if isinstance(n, OrGroup):
            inner = " OR ".join(f"({self._node(c, params)})" for c in n.clauses)
            return f"NOT ({inner})" if n.negate else f"({inner})"
        sql = self._clause(n, params)
        return f"NOT ({sql})" if n.negate else sql

    def _clause(self, c: Clause, params: list[object]) -> str:
        f, v = c.field, c.value.strip()
        if f == "text*":
            params.append(fts_escape(v) if c.phrase else fts_escape(v) + "*")
            return "m.rowid IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)"
        if f == "type":
            return self._multi(v, self._type_one)
        if f == "category":
            vals = [x.strip().lower() for x in v.split(",") if x.strip()]
            params.extend(vals)
            return f"category IN ({','.join('?' * len(vals))})"
        if f in ("sender", "chat"):
            return self._multi(v, lambda x: self._peer(f, x, params))
        if f == "ext":
            vals = [x.strip().lower().lstrip(".") for x in v.split(",") if x.strip()]
            params.extend(vals)
            return f"extension IN ({','.join('?' * len(vals))})"
        if f == "mime":
            params.append(v.lower().replace("*", "%") + ("" if "*" in v else "%"))
            return "lower(mime_type) LIKE ?"
        if f == "filename":
            params.append(f"%{_like_escape(v)}%")
            return "file_name LIKE ? ESCAPE '\\'"
        if f == "text":
            params.append(f"%{_like_escape(v)}%")
            return "text LIKE ? ESCAPE '\\'"
        if f == "domain":
            d = v.lower().removeprefix("www.")
            params.extend([d, d])
            return ("EXISTS (SELECT 1 FROM links l WHERE l.account_id = m.account_id AND l.message_id = m.id"
                    " AND (l.domain = ? OR l.domain LIKE '%.' || ?))")
        if f == "tag":
            vals = [x.strip() for x in v.split(",") if x.strip()]
            params.extend(vals)
            return ("EXISTS (SELECT 1 FROM message_tags mt JOIN tags tg ON tg.id = mt.tag_id WHERE mt.account_id = m.account_id"
                    f" AND mt.message_id = m.id AND tg.name IN ({','.join('?' * len(vals))}))")
        if f == "has":
            return self._multi(v, lambda x: self._lookup(HAS_SQL, x, "has"))
        if f == "is":
            return self._multi(v, lambda x: self._lookup(IS_SQL, x, "is"))
        if f in ("before", "after", "date"):
            return self._date(f, v, params)
        if f == "size":
            return self._numeric("file_size", v, parse_size, params, "size")
        if f == "duration":
            return self._numeric("duration", v, parse_duration, params, "duration")
        if f in ("id", "width", "height"):
            return self._numeric(f, v, lambda s: int(s), params, f)
        raise SearchSyntaxError(f"unsupported field {f}", field=f)

    # ---------------------------------------------------------------- helpers
    def _multi(self, value: str, fn) -> str:  # type: ignore[no-untyped-def]
        items = [x.strip() for x in value.split(",") if x.strip()]
        if not items:
            raise SearchSyntaxError("empty value")
        sqls = [fn(x) for x in items]
        return sqls[0] if len(sqls) == 1 else "(" + " OR ".join(sqls) + ")"

    @staticmethod
    def _type_one(x: str) -> str:
        key = x.lower()
        key = TYPE_ALIASES.get(key, key)
        if key not in TYPE_SQL:
            raise SearchSyntaxError(f"unknown type '{x}'", field="type", value=x)
        return TYPE_SQL[key]

    @staticmethod
    def _lookup(table: dict[str, str], x: str, name: str) -> str:
        key = x.lower()
        if key not in table:
            raise SearchSyntaxError(f"unknown {name}: value '{x}'", field=name, value=x)
        return table[key]

    @staticmethod
    def _peer(kind: str, x: str, params: list[object]) -> str:
        prefix = "sender" if kind == "sender" else "chat"
        if x.lower() == "me" and kind == "sender":
            return "is_forward = 0"
        if x.lstrip("-").isdigit():
            params.append(int(x))
            return f"{prefix}_id = ?"
        if x.startswith("@"):
            params.append(x[1:])
            if kind == "sender":
                return "sender_username = ? COLLATE NOCASE"
            params.append(x[1:])
            return ("(chat_id IN (SELECT peer_id FROM peers p WHERE p.account_id = m.account_id AND p.username = ? COLLATE NOCASE)"
                    " OR chat_name = ? COLLATE NOCASE)")
        params.append(f"%{_like_escape(x)}%")
        if kind == "sender":
            params.append(f"{_like_escape(x)}%")
            return "(sender_name LIKE ? ESCAPE '\\' OR sender_username LIKE ? ESCAPE '\\')"
        return "chat_name LIKE ? ESCAPE '\\'"

    def _date(self, f: str, v: str, params: list[object]) -> str:
        try:
            if ".." in v:
                a, b = v.split("..", 1)
                start = parse_date(a)[0] if a else None
                end = parse_date(b)[1] if b else None
            else:
                start, end = parse_date(v)
        except ValueError as exc:
            raise SearchSyntaxError(str(exc), field=f, value=v) from exc
        if f == "before":
            params.append(self._day_start_ts(start))  # type: ignore[arg-type]
            return "date_ts < ?"
        if f == "after":
            params.append(self._day_start_ts(start))  # type: ignore[arg-type]
            return "date_ts >= ?"
        conds = []
        if start:
            params.append(self._day_start_ts(start))
            conds.append("date_ts >= ?")
        if end:
            params.append(self._day_start_ts(end + timedelta(days=1)))
            conds.append("date_ts < ?")
        return "(" + " AND ".join(conds) + ")" if conds else "1=1"

    @staticmethod
    def _numeric(col: str, v: str, conv, params: list[object], name: str) -> str:  # type: ignore[no-untyped-def]
        try:
            if ".." in v:
                a, b = v.split("..", 1)
                conds = []
                if a:
                    params.append(conv(a))
                    conds.append(f"{col} >= ?")
                if b:
                    params.append(conv(b))
                    conds.append(f"{col} <= ?")
                return "(" + " AND ".join(conds) + ")"
            m = _CMP.match(v)
            assert m
            op = m.group(1) or (">=" if name in ("size", "duration") else "=")
            params.append(conv(m.group(2)))
            return f"{col} {op} ?"
        except (ValueError, AssertionError) as exc:
            raise SearchSyntaxError(f"invalid {name} value '{v}'", field=name, value=v) from exc


def order_clause(key: str, desc: bool) -> str:
    col = SORT_SQL.get(key, "m.date_ts")
    direction = "DESC" if desc else "ASC"
    bare = col.split(" ")[0]
    return f"({bare} IS NULL), {col} {direction}, m.id {direction}"


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
