"""Virtualised message table model + id-based selection manager.

Rows are fetched lazily in pages from SQLite (LIMIT/OFFSET on indexed columns),
so the view stays fluid with hundreds of thousands of messages and memory is
bounded by an LRU page cache. Selection is tracked by *message id* — not by
row — so it survives sorting, paging and filter changes.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QColor

from ...core.errors import SearchSyntaxError
from ...i18n.translator import T
from ...repositories.messages import count_within, ids_range
from ...search.sql import CompiledQuery
from ..theme.style import qcolor
from ..theme.tokens import TYPE_COLORS

MIME_IDS = "application/x-arcivo-message-ids"
TYPE_ICONS = {"text": "file-text", "link": "link", "photo": "image", "video": "video", "video_note": "video", "animation": "clapperboard",
              "audio": "music", "voice": "mic", "document": "file", "sticker": "sticker", "contact": "contact",
              "location": "map-pin", "venue": "map-pin", "poll": "list-checks", "dice": "square-stack", "other": "circle-help"}
COLUMNS = ["type", "content", "from", "date", "size", "duration", "tags"]
SORT_FOR_COLUMN = {"type": "type", "content": "name", "from": "sender", "date": "date", "size": "size", "duration": "duration"}


class SelectionManager(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[int] = set()

    def __len__(self) -> int:
        return len(self.ids)

    def contains(self, mid: int) -> bool:
        return mid in self.ids

    def toggle(self, mid: int) -> None:
        self.ids.symmetric_difference_update({mid})
        self.changed.emit()

    def set(self, ids) -> None:  # type: ignore[no-untyped-def]
        self.ids = set(ids)
        self.changed.emit()

    def add(self, ids) -> None:  # type: ignore[no-untyped-def]
        self.ids.update(ids)
        self.changed.emit()

    def remove(self, ids) -> None:  # type: ignore[no-untyped-def]
        self.ids.difference_update(ids)
        self.changed.emit()

    def clear(self) -> None:
        if self.ids:
            self.ids.clear()
            self.changed.emit()

    def sorted(self) -> list[int]:
        return sorted(self.ids)


class MessagesModel(QAbstractTableModel):
    countChanged = Signal(int)
    queryError = Signal(str)

    def __init__(self, gui, selection: SelectionManager, page_size: int = 400) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.gui = gui
        self.sel = selection
        self.page_size = page_size
        self.query = ""
        self.sort_key = "date"
        self.sort_desc = True
        self.cq: CompiledQuery | None = None
        self._count = 0
        self._pages: OrderedDict[int, list[Any]] = OrderedDict()
        self._max_pages = 40
        selection.changed.connect(self._selection_changed)
        self.headers = {c: T()(f"explorer.col_{c}") for c in COLUMNS}

    # ------------------------------------------------------------------ query
    def set_query(self, query: str, sort_key: str | None = None, sort_desc: bool | None = None) -> bool:
        try:
            cq = self.gui.ctx.search.compile(query, sort_key or self.sort_key, self.sort_desc if sort_desc is None else sort_desc)
        except SearchSyntaxError as exc:
            self.queryError.emit(str(exc))
            return False
        self.beginResetModel()
        self.query = query
        self.cq = cq
        self.sort_key, self.sort_desc = cq.sort_key, cq.sort_desc
        self._pages.clear()
        aid = self.gui.account_id
        self._count = self.gui.ctx.messages.count(aid, cq) if aid else 0
        self.endResetModel()
        self.countChanged.emit(self._count)
        return True

    def refresh(self) -> None:
        self.set_query(self.query)

    @property
    def total(self) -> int:
        return self._count

    def _page(self, p: int) -> list[Any]:
        if p in self._pages:
            self._pages.move_to_end(p)
            return self._pages[p]
        aid = self.gui.account_id
        rows = self.gui.ctx.messages.page(aid, self.cq, p * self.page_size, self.page_size) if aid and self.cq else []
        self._pages[p] = rows
        while len(self._pages) > self._max_pages:
            self._pages.popitem(last=False)
        return rows

    def row_at(self, row: int) -> Any | None:
        if row < 0 or row >= self._count:
            return None
        page = self._page(row // self.page_size)
        i = row % self.page_size
        return page[i] if i < len(page) else None

    def id_at(self, row: int) -> int | None:
        r = self.row_at(row)
        return r["id"] if r is not None else None

    def ids_between(self, a: int, b: int) -> list[int]:
        lo, hi = min(a, b), max(a, b)
        return ids_range(self.gui.ctx.db, self.gui.account_id, self.cq, lo, hi - lo + 1)

    def all_ids(self) -> list[int]:
        return self.gui.ctx.messages.ids(self.gui.account_id, self.cq) if self.cq and self.gui.account_id else []

    def selected_visible(self) -> int:
        if not self.sel.ids or not self.cq:
            return 0
        if len(self.sel.ids) > 20000:
            return len(self.sel.ids)
        return count_within(self.gui.ctx.db, self.gui.account_id, self.cq, list(self.sel.ids))

    # ------------------------------------------------------------------ Qt API
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else self._count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[no-untyped-def]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[COLUMNS[section]]
        return None

    def flags(self, index: QModelIndex):  # type: ignore[no-untyped-def]
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        if index.column() == 0:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        return f

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[no-untyped-def]
        r = self.row_at(index.row())
        if r is None:
            return None
        col = COLUMNS[index.column()]
        t = T()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == "type":
                return t(f"types.{r['media_type']}")
            if col == "content":
                text = (r["text"] or "").replace("\n", " ").strip()
                name = r["file_name"] or ""
                if r["performer"] and r["audio_title"]:
                    name = f"{r['performer']} — {r['audio_title']}"
                if name and text:
                    return f"{name} · {text[:120]}"
                return name or text[:200] or t(f"types.{r['media_type']}")
            if col == "from":
                parts = [p for p in (r["sender_name"], r["chat_name"]) if p]
                return " · ".join(dict.fromkeys(parts)) or t("explorer.me")
            if col == "date":
                return t.date(r["date_ts"], with_time=True)
            if col == "size":
                return t.size(r["file_size"]) if r["file_size"] else ""
            if col == "duration":
                return t.duration(r["duration"]) if r["duration"] else ""
            if col == "tags":
                return (r["tags"] or "").replace(",", ", ")
        if role == Qt.ItemDataRole.DecorationRole and col == "type":
            return self.gui.icons.icon(TYPE_ICONS.get(r["media_type"], "file"), TYPE_COLORS.get(r["media_type"], "#8A94A6"), 16)
        if role == Qt.ItemDataRole.CheckStateRole and col == "type":
            return Qt.CheckState.Checked if self.sel.contains(r["id"]) else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole and self.sel.contains(r["id"]):
            return qcolor(self.gui.pal.selection)
        if role == Qt.ItemDataRole.ForegroundRole:
            if r["remote_deleted"]:
                return qcolor(self.gui.pal.danger)
            if col in ("from", "date", "size", "duration", "type"):
                return qcolor(self.gui.pal.text_muted)
        if role == Qt.ItemDataRole.TextAlignmentRole and col in ("size", "duration"):
            return int(Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == "content":
            return (r["text"] or r["file_name"] or "")[:600]
        if role == Qt.ItemDataRole.UserRole:
            return r["id"]
        if role == Qt.ItemDataRole.FontRole and r["flagged"]:
            f = self.gui.window.font() if self.gui.window else None
            if f is not None:
                f.setBold(True)
                return f
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # type: ignore[no-untyped-def]
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            mid = self.id_at(index.row())
            if mid is not None:
                self.sel.toggle(mid)
                return True
        return False

    def sort(self, column: int, order=Qt.SortOrder.DescendingOrder) -> None:  # type: ignore[no-untyped-def]
        key = SORT_FOR_COLUMN.get(COLUMNS[column])
        if key:
            self.sort_key = key
            self.sort_desc = order == Qt.SortOrder.DescendingOrder
            self.set_query(self.query, key, self.sort_desc)

    def _selection_changed(self) -> None:
        if self._count:
            self.dataChanged.emit(self.index(0, 0), self.index(self._count - 1, len(COLUMNS) - 1),
                                  [Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.BackgroundRole])

    # ------------------------------------------------------------------ drag & drop
    def mimeTypes(self) -> list[str]:
        return [MIME_IDS]

    def mimeData(self, indexes) -> QMimeData:  # type: ignore[no-untyped-def]
        ids = {self.id_at(i.row()) for i in indexes} - {None}
        if ids & self.sel.ids:
            ids = set(self.sel.ids)
        md = QMimeData()
        md.setData(MIME_IDS, json.dumps(sorted(ids)).encode())
        md.setText("\n".join(f"#{i}" for i in sorted(ids)[:200]))
        return md


def ids_from_mime(md: QMimeData) -> list[int]:
    if md.hasFormat(MIME_IDS):
        try:
            return [int(x) for x in json.loads(bytes(md.data(MIME_IDS)).decode())]
        except (ValueError, TypeError):
            return []
    return []


def type_color(media_type: str) -> QColor:
    return qcolor(TYPE_COLORS.get(media_type, "#8A94A6"))
