"""Tags, marks (flag/star/note) and smart collections — all local-only."""

from __future__ import annotations

import time
from collections.abc import Iterable

from ..db.database import Database
from ..domain.models import SmartCollection, Tag


class TagRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[Tag]:
        rows = self.db.query("SELECT t.id, t.name, t.color, t.description, count(mt.message_id) AS n FROM tags t "
                             "LEFT JOIN message_tags mt ON mt.tag_id = t.id GROUP BY t.id ORDER BY t.name COLLATE NOCASE")
        return [Tag(r["id"], r["name"], r["color"], r["description"], r["n"]) for r in rows]

    def get_by_name(self, name: str) -> Tag | None:
        r = self.db.query("SELECT id, name, color, description FROM tags WHERE name = ?", (name,))
        return Tag(r[0]["id"], r[0]["name"], r[0]["color"], r[0]["description"]) if r else None

    def create(self, name: str, color: str = "#7C83FD", description: str = "") -> Tag:
        name = name.strip()
        if not name:
            raise ValueError("tag name is empty")
        with self.db.transaction() as c:
            cur = c.execute("INSERT INTO tags(name, color, description) VALUES (?,?,?)", (name, color, description))
        return Tag(int(cur.lastrowid or 0), name, color, description)

    def update(self, tag_id: int, *, name: str | None = None, color: str | None = None, description: str | None = None) -> None:
        with self.db.transaction() as c:
            if name is not None:
                c.execute("UPDATE tags SET name = ? WHERE id = ?", (name.strip(), tag_id))
            if color is not None:
                c.execute("UPDATE tags SET color = ? WHERE id = ?", (color, tag_id))
            if description is not None:
                c.execute("UPDATE tags SET description = ? WHERE id = ?", (description, tag_id))

    def delete(self, tag_id: int) -> None:
        with self.db.transaction() as c:
            c.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def assign(self, account_id: int, tag_id: int, message_ids: Iterable[int]) -> int:
        with self.db.transaction() as c:
            return sum(c.execute("INSERT OR IGNORE INTO message_tags(account_id, message_id, tag_id) VALUES (?,?,?)",
                                 (account_id, mid, tag_id)).rowcount for mid in message_ids)

    def unassign(self, account_id: int, tag_id: int, message_ids: Iterable[int]) -> int:
        with self.db.transaction() as c:
            return sum(c.execute("DELETE FROM message_tags WHERE account_id = ? AND tag_id = ? AND message_id = ?",
                                 (account_id, tag_id, mid)).rowcount for mid in message_ids)

    def tagged_ids(self, account_id: int, tag_id: int, among: Iterable[int]) -> set[int]:
        among = list(among)
        out: set[int] = set()
        for i in range(0, len(among), 500):
            chunk = among[i:i + 500]
            ph = ",".join("?" * len(chunk))
            out |= {r[0] for r in self.db.query(
                f"SELECT message_id FROM message_tags WHERE account_id = ? AND tag_id = ? AND message_id IN ({ph})",
                (account_id, tag_id, *chunk))}
        return out

    def tags_for(self, account_id: int, message_id: int) -> list[Tag]:
        rows = self.db.query("SELECT t.id, t.name, t.color, t.description FROM tags t JOIN message_tags mt ON mt.tag_id = t.id "
                             "WHERE mt.account_id = ? AND mt.message_id = ? ORDER BY t.name", (account_id, message_id))
        return [Tag(r["id"], r["name"], r["color"], r["description"]) for r in rows]


class MarksRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, account_id: int, message_id: int) -> dict:
        r = self.db.query("SELECT flagged, starred, note FROM message_marks WHERE account_id = ? AND message_id = ?",
                          (account_id, message_id))
        return dict(r[0]) if r else {"flagged": 0, "starred": 0, "note": None}

    def states(self, account_id: int, field: str, ids: list[int]) -> dict[int, int]:
        assert field in ("flagged", "starred")
        out: dict[int, int] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            ph = ",".join("?" * len(chunk))
            for r in self.db.query(f"SELECT message_id, {field} FROM message_marks WHERE account_id = ? AND message_id IN ({ph})",
                                   (account_id, *chunk)):
                out[r[0]] = r[1]
        return out

    def set_field(self, account_id: int, field: str, ids: Iterable[int], value: object) -> int:
        assert field in ("flagged", "starred", "note")
        now = int(time.time())
        with self.db.transaction() as c:
            n = 0
            for mid in ids:
                c.execute(f"INSERT INTO message_marks(account_id, message_id, {field}, updated_at) VALUES (?,?,?,?) "
                          f"ON CONFLICT DO UPDATE SET {field} = excluded.{field}, updated_at = excluded.updated_at",
                          (account_id, mid, value, now))
                n += 1
            return n


class CollectionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _from(r) -> SmartCollection:  # type: ignore[no-untyped-def]
        return SmartCollection(r["id"], r["name"], r["query"], r["icon"], r["color"], bool(r["pinned"]), r["sort_key"],
                               bool(r["sort_desc"]), r["description"])

    def list(self) -> list[SmartCollection]:
        return [self._from(r) for r in self.db.query("SELECT * FROM collections ORDER BY position, id")]

    def get(self, cid: int) -> SmartCollection | None:
        r = self.db.query("SELECT * FROM collections WHERE id = ?", (cid,))
        return self._from(r[0]) if r else None

    def create(self, name: str, query: str, **kw: object) -> SmartCollection:
        with self.db.transaction() as c:
            pos = c.execute("SELECT coalesce(max(position), 0) + 1 FROM collections").fetchone()[0]
            cur = c.execute("INSERT INTO collections(name, query, icon, color, pinned, sort_key, sort_desc, description, position)"
                            " VALUES (?,?,?,?,?,?,?,?,?)",
                            (name, query, kw.get("icon", "sparkles"), kw.get("color", "#7C83FD"), int(bool(kw.get("pinned", True))),
                             kw.get("sort_key", "date"), int(bool(kw.get("sort_desc", True))), kw.get("description", ""), pos))
        return self.get(int(cur.lastrowid or 0))  # type: ignore[return-value]

    def update(self, cid: int, **kw: object) -> None:
        allowed = {"name", "query", "icon", "color", "pinned", "sort_key", "sort_desc", "description", "position"}
        sets = {k: v for k, v in kw.items() if k in allowed}
        if not sets:
            return
        with self.db.transaction() as c:
            c.execute(f"UPDATE collections SET {', '.join(f'{k} = ?' for k in sets)}, updated_at = strftime('%s','now') "
                      "WHERE id = ?", (*sets.values(), cid))

    def delete(self, cid: int) -> None:
        with self.db.transaction() as c:
            c.execute("DELETE FROM collections WHERE id = ?", (cid,))
