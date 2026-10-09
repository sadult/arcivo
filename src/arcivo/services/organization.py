"""Tagging, flags/notes and smart collections with an in-memory undo stack.

These are *local* operations and therefore always undoable (unlike Telegram
deletions, which the API cannot reverse).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..core.events import COLLECTIONS_CHANGED, DATA_CHANGED, TAGS_CHANGED, EventBus
from ..domain.models import SmartCollection, Tag
from ..repositories.organization import CollectionRepository, MarksRepository, TagRepository
from .search import SearchService


@dataclass
class UndoEntry:
    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]


class UndoStack:
    def __init__(self, limit: int = 100) -> None:
        self._undo: list[UndoEntry] = []
        self._redo: list[UndoEntry] = []
        self.limit = limit

    def push(self, entry: UndoEntry) -> None:
        self._undo.append(entry)
        self._undo = self._undo[-self.limit:]
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self) -> str | None:
        if not self._undo:
            return None
        e = self._undo.pop()
        e.undo()
        self._redo.append(e)
        return e.label

    def redo(self) -> str | None:
        if not self._redo:
            return None
        e = self._redo.pop()
        e.redo()
        self._undo.append(e)
        return e.label


class OrganizationService:
    def __init__(self, tags: TagRepository, marks: MarksRepository, collections: CollectionRepository,
                 search: SearchService, bus: EventBus) -> None:
        self.tags = tags
        self.marks = marks
        self.collections = collections
        self.search = search
        self.bus = bus
        self.undo = UndoStack()

    # ---- tags
    def list_tags(self) -> list[Tag]:
        return self.tags.list()

    def create_tag(self, name: str, color: str = "#7C83FD", description: str = "") -> Tag:
        t = self.tags.create(name, color, description)
        self.bus.publish(TAGS_CHANGED)
        return t

    def update_tag(self, tag_id: int, **kw: str) -> None:
        self.tags.update(tag_id, **kw)
        self.bus.publish(TAGS_CHANGED)

    def delete_tag(self, tag_id: int) -> None:
        self.tags.delete(tag_id)
        self.bus.publish(TAGS_CHANGED)
        self.bus.publish(DATA_CHANGED, reason="tags")

    def tag(self, account_id: int, tag_id: int, ids: list[int], *, remove: bool = False) -> int:
        before = self.tags.tagged_ids(account_id, tag_id, ids)

        def apply() -> int:
            n = (self.tags.unassign if remove else self.tags.assign)(account_id, tag_id, ids)
            self.bus.publish(TAGS_CHANGED)
            self.bus.publish(DATA_CHANGED, reason="tags")
            return n

        def revert() -> None:
            if remove:
                self.tags.assign(account_id, tag_id, list(before))
            else:
                self.tags.unassign(account_id, tag_id, [i for i in ids if i not in before])
            self.bus.publish(TAGS_CHANGED)
            self.bus.publish(DATA_CHANGED, reason="tags")

        n = apply()
        self.undo.push(UndoEntry(f"{'untag' if remove else 'tag'} {len(ids)}", revert, apply))
        return n

    # ---- marks
    def set_flag(self, account_id: int, ids: list[int], value: bool, field: str = "flagged") -> int:
        previous = self.marks.states(account_id, field, ids)

        def apply() -> int:
            n = self.marks.set_field(account_id, field, ids, int(value))
            self.bus.publish(DATA_CHANGED, reason="marks")
            return n

        def revert() -> None:
            for mid in ids:
                self.marks.set_field(account_id, field, [mid], previous.get(mid, 0))
            self.bus.publish(DATA_CHANGED, reason="marks")

        n = apply()
        self.undo.push(UndoEntry(f"{field} {len(ids)}", revert, apply))
        return n

    def set_note(self, account_id: int, message_id: int, note: str | None) -> None:
        self.marks.set_field(account_id, "note", [message_id], note or None)
        self.bus.publish(DATA_CHANGED, reason="marks")

    # ---- collections
    def list_collections(self, account_id: int | None = None, with_counts: bool = True) -> list[SmartCollection]:
        cols = self.collections.list()
        if with_counts and account_id is not None:
            for c in cols:
                try:
                    c.count = self.search.count(account_id, c.query)
                except Exception:
                    c.count = None
        return cols

    def save_collection(self, name: str, query: str, **kw: object) -> SmartCollection:
        err = self.search.validate(query)
        if err:
            raise ValueError(err)
        c = self.collections.create(name, query, **kw)
        self.bus.publish(COLLECTIONS_CHANGED)
        return c

    def update_collection(self, cid: int, **kw: object) -> None:
        if "query" in kw:
            err = self.search.validate(str(kw["query"]))
            if err:
                raise ValueError(err)
        self.collections.update(cid, **kw)
        self.bus.publish(COLLECTIONS_CHANGED)

    def seed_default_collections(self) -> int:
        """Create the starter smart collections (only called once, on a fresh database)."""
        if self.collections.list():
            return 0
        year = datetime.now().year
        for name, query, icon, color in DEFAULT_COLLECTIONS:
            self.collections.create(name, query.format(year=year), icon=icon, color=color)
        self.bus.publish(COLLECTIONS_CHANGED)
        return len(DEFAULT_COLLECTIONS)

    def delete_collection(self, cid: int) -> None:
        self.collections.delete(cid)
        self.bus.publish(COLLECTIONS_CHANGED)


DEFAULT_COLLECTIONS = [
    ("Large audio (> 20 MB)", "type:audio size:>20MB sort:size", "music", "#B07CFF"),
    ("PDFs this year", "ext:pdf after:{year}-01-01", "file-text", "#F2545B"),
    ("Videos longer than 10 min", "type:video duration:>10m sort:duration", "video", "#4C8DFF"),
    ("Links", "type:link", "link", "#2BB673"),
    ("Flagged", "is:flagged", "flag", "#F5A524"),
]
