"""Message browsing building blocks shared by Explorer, Search and Collections.

* :class:`MessageTable` – virtualised table with id-based multi-selection
  (checkbox, Ctrl+click toggle, Shift+click ranges, Space), drag & drop and a
  context menu.
* :class:`BulkBar` – contextual actions for the current selection.
* :class:`DetailPanel` – metadata, text, links, tags, note and preview.
* :class:`FilterPanel` – advanced filters that compile to the search syntax;
  tag rows are drop targets for dragged messages.
* :class:`MessageBrowser` – all of the above wired together.
"""

from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...i18n.translator import T
from ...services.search import SearchSpec
from ..theme.tokens import TYPE_COLORS
from .common import (
    Chip,
    EmptyState,
    FlowLayout,
    IconBadge,
    KeyValueGrid,
    SearchBox,
    button,
    hline,
    label,
    tool,
)
from .messages_model import COLUMNS, TYPE_ICONS, MessagesModel, ids_from_mime

FILTER_TYPES = ["text", "link", "photo", "video", "audio", "voice", "document", "sticker", "animation", "video_note", "contact",
                "location", "poll"]


# ============================================================================ table
class MessageTable(QWidget):
    currentChanged = Signal(object)  # message id or None
    countChanged = Signal(int)

    def __init__(self, gui) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.gui = gui
        self.sel = gui.selection
        self.model = MessagesModel(gui, self.sel, gui.settings.performance.page_size)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setObjectName("MessageTable")
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(False)
        self.view.setWordWrap(False)
        self.view.setSortingEnabled(True)
        self.view.setDragEnabled(True)
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.setIconSize(QSize(16, 16))
        vh = self.view.verticalHeader()
        vh.setVisible(False)
        vh.setDefaultSectionSize(26 if gui.settings.appearance.compact_rows else 32)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh = self.view.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COLUMNS.index("content"), QHeaderView.ResizeMode.Stretch)
        for col, w in (("type", 118), ("from", 140), ("date", 128), ("size", 80), ("duration", 72), ("tags", 96)):
            self.view.setColumnWidth(COLUMNS.index(col), w)
        hh.setSortIndicator(COLUMNS.index("date"), Qt.SortOrder.DescendingOrder)
        self.view.horizontalHeader().setSortIndicatorShown(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self._anchor: int | None = None
        self.view.clicked.connect(self._clicked)
        self.view.selectionModel().currentRowChanged.connect(self._current)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.installEventFilter(self)
        self.model.countChanged.connect(self.countChanged)

    # ---- query
    def set_query(self, q: str) -> bool:
        return self.model.set_query(q)

    def current_id(self) -> int | None:
        idx = self.view.currentIndex()
        return self.model.id_at(idx.row()) if idx.isValid() else None

    # ---- selection semantics
    def _clicked(self, idx: QModelIndex) -> None:
        from PySide6.QtWidgets import QApplication
        m = QApplication.keyboardModifiers()
        mid = self.model.id_at(idx.row())
        if mid is None:
            return
        if m & Qt.KeyboardModifier.ShiftModifier and self._anchor is not None:
            self.sel.add(self.model.ids_between(self._anchor, idx.row()))
        elif m & Qt.KeyboardModifier.ControlModifier:
            self.sel.toggle(mid)
            self._anchor = idx.row()
        else:
            self._anchor = idx.row()

    def _current(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        self.currentChanged.emit(self.model.id_at(cur.row()) if cur.isValid() else None)

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[no-untyped-def]
        if obj is self.view and ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Space:
            mid = self.current_id()
            if mid is not None:
                self.sel.toggle(mid)
                return True
        return super().eventFilter(obj, ev)

    def target_ids(self) -> list[int]:
        """Selection if any, otherwise the current row."""
        if self.sel.ids:
            return self.sel.sorted()
        mid = self.current_id()
        return [mid] if mid is not None else []

    def _menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        t, g, ic = T(), self.gui, self.gui.icons
        row = self.model.row_at(idx.row())
        mid = row["id"]
        ids = self.sel.sorted() if self.sel.contains(mid) else [mid]
        m = QMenu(self)
        m.addAction(ic.icon("square-check-big"), t("explorer.deselect") if self.sel.contains(mid) else t("explorer.select"),
                    lambda: self.sel.toggle(mid))
        m.addSeparator()
        m.addAction(ic.icon("tag"), t("explorer.tag_n", n=len(ids)), lambda: g.actions.tag(ids))
        m.addAction(ic.icon("flag"), t("explorer.flag"), lambda: g.actions.flag(ids, True))
        m.addAction(ic.icon("flag"), t("explorer.unflag"), lambda: g.actions.flag(ids, False))
        m.addAction(ic.icon("copy"), t("explorer.copy_text"), lambda: g.actions.copy_text(ids))
        m.addAction(ic.icon("download"), t("explorer.export_n", n=len(ids)), lambda: g.actions.export(ids))
        m.addSeparator()
        m.addAction(ic.icon("filter"), t("explorer.same_type"), lambda: g.explore(f"type:{row['media_type']}"))
        if row["sender_name"]:
            name = row["sender_name"].replace('"', "")
            m.addAction(ic.icon("user"), t("explorer.same_sender"), lambda: g.explore(f'sender:"{name}"'))
        if row["extension"]:
            m.addAction(ic.icon("file"), t("explorer.same_ext", ext=row["extension"]), lambda: g.explore(f"ext:{row['extension']}"))
        m.addSeparator()
        act = QAction(ic.icon("trash-2", g.pal.danger), t("explorer.delete_n", n=len(ids)), m)
        act.triggered.connect(lambda: g.actions.delete(ids))
        m.addAction(act)
        m.exec(self.view.viewport().mapToGlobal(pos))


# ============================================================================ bulk bar
class BulkBar(QFrame):
    def __init__(self, gui, table: MessageTable | None = None, ids_provider=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Banner")
        self.gui = gui
        self.table = table
        t, ic = T(), gui.icons
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        lay.setSpacing(6)
        badge = QLabel()
        badge.setPixmap(ic.pixmap("square-check-big", gui.pal.accent, 18))
        lay.addWidget(badge)
        self.count = label("", None)
        lay.addWidget(self.count)
        self.all_btn = button(t("explorer.select_all_matching"), variant="ghost", on_click=self._select_all)
        lay.addWidget(self.all_btn)
        lay.addStretch(1)
        lay.addWidget(button(t("explorer.tag"), ic.icon("tag", size=15), on_click=lambda: gui.actions.tag(gui.selection.sorted())))
        lay.addWidget(button(t("explorer.flag"), ic.icon("flag", size=15), on_click=lambda: gui.actions.flag(gui.selection.sorted())))
        lay.addWidget(button(t("explorer.export"), ic.icon("download", size=15),
                             on_click=lambda: gui.actions.export(gui.selection.sorted())))
        lay.addWidget(button(t("explorer.delete"), ic.icon("trash-2", "#FFFFFF", 15), "danger",
                             on_click=lambda: gui.actions.delete(gui.selection.sorted())))
        lay.addWidget(tool(ic.icon("x"), t("explorer.clear_selection"), gui.selection.clear))
        gui.selection.changed.connect(self.update_state)
        self.update_state()

    def _select_all(self) -> None:
        if self.table is not None:
            self.gui.selection.add(self.table.model.all_ids())

    def update_state(self) -> None:
        t = T()
        n = len(self.gui.selection.ids)
        self.setVisible(n > 0)
        if not n:
            return
        if self.table is not None and self.table.model.cq is not None:
            vis = self.table.model.selected_visible()
            txt = t("explorer.selected_n", n=n)
            if vis != n:
                txt += "  ·  " + t("explorer.selected_hidden", n=n - vis)
            self.count.setText(txt)
            total = self.table.model.total
            self.all_btn.setText(t("explorer.select_all_matching_n", n=total))
            self.all_btn.setVisible(vis < total)
        else:
            self.count.setText(t("explorer.selected_n", n=n))
            self.all_btn.setVisible(False)


# ============================================================================ detail panel
class DetailPanel(QFrame):
    closed = Signal()

    def __init__(self, gui) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Card")
        self.gui = gui
        self.mid: int | None = None
        self.setMinimumWidth(320)
        self.setMaximumWidth(460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        sa.setWidget(inner)
        outer.addWidget(sa)
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)
        self._empty()

    def _clear(self) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
            elif it.layout():
                _drop_layout(it.layout())

    def _empty(self) -> None:
        self._clear()
        self.lay.addWidget(EmptyState(self.gui.icons.pixmap("eye", self.gui.pal.text_subtle, 36), T()("details.empty_title"),
                                      T()("details.empty_text")))

    def show_message(self, mid: int | None) -> None:
        self.mid = mid
        aid = self.gui.account_id
        if mid is None or aid is None:
            self._empty()
            return
        r = self.gui.ctx.messages.get(aid, mid)
        if r is None:
            self._empty()
            return
        t, g = T(), self.gui
        self._clear()
        mt = r["media_type"]
        head = QHBoxLayout()
        head.addWidget(IconBadge(g.icons.pixmap(TYPE_ICONS.get(mt, "file"), TYPE_COLORS.get(mt, "#8A94A6"), 20),
                                 TYPE_COLORS.get(mt, "#8A94A6"), 40))
        col = QVBoxLayout()
        col.setSpacing(0)
        title = r["file_name"] or (f"{r['performer']} — {r['audio_title']}" if r["performer"] else "") or t(f"types.{mt}")
        tl = label(title, "CardTitle", wrap=True, selectable=True)
        col.addWidget(tl)
        col.addWidget(label(f"{t(f'types.{mt}')} · #{t.num(mid)}", "Subtle"))
        head.addLayout(col, 1)
        head.addWidget(tool(g.icons.icon("x"), t("common.close"), self.closed.emit), 0, Qt.AlignmentFlag.AlignTop)
        self.lay.addLayout(head)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setVisible(False)
        self.lay.addWidget(self.preview)
        if r["has_thumb"] and mt in ("photo", "video", "animation", "video_note") and not g.settings.privacy.hide_previews_in_screenshots:
            p = g.ctx.cache.thumbnail_path(aid, mid)
            if p:
                self._set_preview(p)
            else:
                g.runtime.submit(g.ctx.cache.fetch_thumbnail(aid, mid), lambda path, m=mid: self._set_preview(path) if path and self.mid == m else None,
                                 lambda _e: None)

        kv = KeyValueGrid()
        kv.add(t("details.date"), t.date(r["date_ts"], with_time=True))
        if r["edit_ts"]:
            kv.add(t("details.edited"), t.date(r["edit_ts"], with_time=True))
        if r["file_size"]:
            kv.add(t("details.size"), t.size(r["file_size"]))
        if r["duration"]:
            kv.add(t("details.duration"), t.duration(r["duration"]))
        if r["width"] and r["height"]:
            kv.add(t("details.dimensions"), f"{r['width']}×{r['height']}")
        if r["extension"] or r["mime_type"]:
            kv.add(t("details.format"), " · ".join(x for x in (r["extension"], r["mime_type"]) if x))
        if r["sender_name"] or r["sender_username"]:
            kv.add(t("details.sender"), " ".join(x for x in (r["sender_name"], f"@{r['sender_username']}" if r["sender_username"] else "") if x))
        if r["chat_name"]:
            kv.add(t("details.chat"), f"{r['chat_name']} ({t('chat_types.' + (r['chat_type'] or 'user'))})")
        if r["is_forward"]:
            kv.add(t("details.forwarded"), t.date(r["fwd_date_ts"], with_time=True) if r["fwd_date_ts"] else t("common.yes"))
        if r["views"]:
            kv.add(t("details.views"), t.num(r["views"]))
        if r["remote_deleted"]:
            kv.add(t("details.status"), t("details.remote_deleted"))
        self.lay.addWidget(kv)

        if r["text"]:
            self.lay.addWidget(label(t("details.text"), "SectionTitle"))
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            rtl = any("\u0600" <= ch <= "\u06FF" for ch in r["text"][:200])
            tb.setHtml(f'<div dir="{"rtl" if rtl else "ltr"}" style="white-space: pre-wrap">{html.escape(r["text"])}</div>')
            tb.setMinimumHeight(90)
            tb.setMaximumHeight(240)
            self.lay.addWidget(tb)
        links = g.ctx.messages.links_for(aid, mid)
        if links:
            self.lay.addWidget(label(t("details.links", n=len(links)), "SectionTitle"))
            for u in links[:8]:
                lb = label(f'<a href="{html.escape(u)}">{html.escape(u[:70])}</a>', None, wrap=True)
                lb.setOpenExternalLinks(True)
                self.lay.addWidget(lb)

        self.lay.addWidget(label(t("details.tags"), "SectionTitle"))
        tags = g.ctx.tags.tags_for(aid, mid)
        chips = QWidget()
        fl = FlowLayout(chips)
        for tg in tags:
            fl.addWidget(Chip(tg.name, tg.color))
        if not tags:
            fl.addWidget(label(t("details.no_tags"), "Subtle"))
        self.lay.addWidget(chips)

        marks = g.ctx.marks.get(aid, mid)
        self.lay.addWidget(label(t("details.note"), "SectionTitle"))
        self.note = QPlainTextEdit(marks.get("note") or "")
        self.note.setPlaceholderText(t("details.note_placeholder"))
        self.note.setMaximumHeight(90)
        self.lay.addWidget(self.note)
        save = button(t("details.save_note"), variant="ghost", on_click=lambda: (g.ctx.org.set_note(aid, mid, self.note.toPlainText().strip()),
                                                                               g.notify(t("details.note_saved"), "", "success")))
        self.lay.addWidget(save, 0, Qt.AlignmentFlag.AlignTrailing)

        self.lay.addWidget(hline())
        grid = QGridLayout()
        grid.setSpacing(6)
        flagged = bool(marks.get("flagged"))
        grid.addWidget(button(t("explorer.unflag") if flagged else t("explorer.flag"), g.icons.icon("flag", size=15),
                              on_click=lambda: (g.actions.flag([mid], not flagged), self.show_message(mid))), 0, 0)
        grid.addWidget(button(t("explorer.tag"), g.icons.icon("tag", size=15), on_click=lambda: (g.actions.tag([mid]), self.show_message(mid))), 0, 1)
        grid.addWidget(button(t("explorer.copy_text"), g.icons.icon("copy", size=15), on_click=lambda: g.actions.copy_text([mid])), 1, 0)
        grid.addWidget(button(t("explorer.export"), g.icons.icon("download", size=15), on_click=lambda: g.actions.export([mid])), 1, 1)
        grid.addWidget(button(t("explorer.delete"), g.icons.icon("trash-2", "#FFFFFF", 15), "danger",
                              on_click=lambda: g.actions.delete([mid])), 2, 0, 1, 2)
        self.lay.addLayout(grid)
        self.lay.addStretch(1)

    def _set_preview(self, path) -> None:  # type: ignore[no-untyped-def]
        px = QPixmap(str(path))
        if px.isNull():
            return
        self.preview.setPixmap(px.scaled(QSize(380, 220), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.preview.setVisible(True)


def _drop_layout(lay) -> None:  # type: ignore[no-untyped-def]
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().hide()
            it.widget().deleteLater()
        elif it.layout():
            _drop_layout(it.layout())


# ============================================================================ filters
class TagDropRow(QCheckBox):
    """A tag filter checkbox that also accepts dragged messages (assigns the tag)."""

    def __init__(self, gui, tag) -> None:  # type: ignore[no-untyped-def]
        super().__init__(f"{tag.name}  ·  {T().num(tag.count)}")
        self.gui = gui
        self.tag = tag
        self.setIcon(gui.icons.icon("tag", tag.color, 14))
        self.setAcceptDrops(True)
        self.setToolTip(T()("filters.drop_hint"))

    def dragEnterEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if ids_from_mime(e.mimeData()):
            e.acceptProposedAction()
            self.setProperty("dropTarget", True)
            self.style().polish(self)

    def dragLeaveEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        self.setProperty("dropTarget", False)
        self.style().polish(self)

    def dropEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        ids = ids_from_mime(e.mimeData())
        self.setProperty("dropTarget", False)
        self.style().polish(self)
        if ids:
            self.gui.actions.tag_with(self.tag.id, ids)
            e.acceptProposedAction()


class FilterPanel(QFrame):
    changed = Signal()

    def __init__(self, gui) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Card")
        self.gui = gui
        self.setFixedWidth(270)
        t = T()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        sa.setWidget(inner)
        outer.addWidget(sa)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label(t("filters.title"), "CardTitle"), 1)
        head.addWidget(tool(gui.icons.icon("funnel-x"), t("filters.reset"), self.reset))
        lay.addLayout(head)
        self._timer = QTimer(self, singleShot=True, interval=220)
        self._timer.timeout.connect(self.changed)

        lay.addWidget(label(t("filters.types"), "NavSection"))
        grid = QGridLayout()
        grid.setSpacing(4)
        self.type_boxes: dict[str, QCheckBox] = {}
        for i, ty in enumerate(FILTER_TYPES):
            cb = QCheckBox(t(f"types.{ty}"))
            cb.setIcon(gui.icons.icon(TYPE_ICONS.get(ty, "file"), TYPE_COLORS.get(ty), 14))
            cb.toggled.connect(self._changed)
            grid.addWidget(cb, i // 2, i % 2)
            self.type_boxes[ty] = cb
        lay.addLayout(grid)

        lay.addWidget(label(t("filters.date"), "NavSection"))
        self.after_on, self.after = self._date_row(lay, t("filters.after"))
        self.before_on, self.before = self._date_row(lay, t("filters.before"))

        lay.addWidget(label(t("filters.size"), "NavSection"))
        self.min_size, self.max_size = self._range_row(lay, "1MB", "500MB")
        lay.addWidget(label(t("filters.duration"), "NavSection"))
        self.min_dur, self.max_dur = self._range_row(lay, "30s", "10m")

        lay.addWidget(label(t("filters.people"), "NavSection"))
        self.sender = self._combo(t("filters.any_sender"))
        self.chat = self._combo(t("filters.any_chat"))
        lay.addWidget(self.sender)
        lay.addWidget(self.chat)
        lay.addWidget(label(t("filters.extension"), "NavSection"))
        self.ext = QLineEdit()
        self.ext.setPlaceholderText("pdf, zip, mp3")
        self.ext.textChanged.connect(self._changed)
        lay.addWidget(self.ext)
        self.flagged = QCheckBox(t("filters.flagged_only"))
        self.flagged.setIcon(gui.icons.icon("flag", gui.pal.warning, 14))
        self.flagged.toggled.connect(self._changed)
        lay.addWidget(self.flagged)

        lay.addWidget(label(t("filters.tags"), "NavSection"))
        self.tags_box = QVBoxLayout()
        self.tags_box.setSpacing(2)
        lay.addLayout(self.tags_box)
        lay.addWidget(label(t("filters.drop_hint"), "Subtle", wrap=True))
        lay.addStretch(1)
        self.tag_rows: list[TagDropRow] = []
        self.reload()

    def _changed(self, *_a: Any) -> None:
        self._timer.start()

    def _date_row(self, lay: QVBoxLayout, text: str):  # type: ignore[no-untyped-def]
        from PySide6.QtCore import QDate
        row = QHBoxLayout()
        cb = QCheckBox(text)
        de = QDateEdit(QDate.currentDate())
        de.setCalendarPopup(True)
        de.setDisplayFormat("yyyy-MM-dd")
        de.setEnabled(False)
        cb.toggled.connect(de.setEnabled)
        cb.toggled.connect(self._changed)
        de.dateChanged.connect(self._changed)
        row.addWidget(cb, 1)
        row.addWidget(de, 1)
        lay.addLayout(row)
        return cb, de

    def _range_row(self, lay: QVBoxLayout, ph_min: str, ph_max: str):  # type: ignore[no-untyped-def]
        row = QHBoxLayout()
        a, b = QLineEdit(), QLineEdit()
        a.setPlaceholderText(T()("filters.min", example=ph_min))
        b.setPlaceholderText(T()("filters.max", example=ph_max))
        for w in (a, b):
            w.textChanged.connect(self._changed)
            row.addWidget(w)
        lay.addLayout(row)
        return a, b

    def _combo(self, any_text: str) -> QComboBox:
        c = QComboBox()
        c.setEditable(False)
        c.addItem(any_text, None)
        c.currentIndexChanged.connect(self._changed)
        return c

    def reload(self) -> None:
        aid = self.gui.account_id
        for combo, kind in ((self.sender, "sender"), (self.chat, "chat")):
            cur = combo.currentData()
            combo.blockSignals(True)
            while combo.count() > 1:
                combo.removeItem(1)
            if aid:
                for r in self.gui.ctx.messages.peers(aid, kind)[:300]:
                    if r["name"]:
                        combo.addItem(f"{r['name']}  ({T().num(r['n'])})", r["name"])
            i = combo.findData(cur)
            combo.setCurrentIndex(max(0, i))
            combo.blockSignals(False)
        checked = {r.tag.name for r in self.tag_rows if r.isChecked()}
        for r in self.tag_rows:
            r.hide()
            r.deleteLater()
        self.tag_rows = []
        for tag in self.gui.ctx.org.list_tags():
            row = TagDropRow(self.gui, tag)
            row.setChecked(tag.name in checked)
            row.toggled.connect(self._changed)
            self.tags_box.addWidget(row)
            self.tag_rows.append(row)

    def reset(self) -> None:
        for w in [*self.type_boxes.values(), self.after_on, self.before_on, self.flagged, *self.tag_rows]:
            w.blockSignals(True)
            w.setChecked(False)
            w.blockSignals(False)
        for w in (self.min_size, self.max_size, self.min_dur, self.max_dur, self.ext):
            w.blockSignals(True)
            w.clear()
            w.blockSignals(False)
        for c in (self.sender, self.chat):
            c.blockSignals(True)
            c.setCurrentIndex(0)
            c.blockSignals(False)
        self.changed.emit()

    def set_types(self, types: list[str]) -> None:
        for k, cb in self.type_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(k in types)
            cb.blockSignals(False)

    def active_count(self) -> int:
        return sum(1 for x in self.query_parts() if x)

    def spec(self) -> SearchSpec:
        return SearchSpec(
            types=[k for k, cb in self.type_boxes.items() if cb.isChecked()] or None,
            tags=[r.tag.name for r in self.tag_rows if r.isChecked()] or None,
            sender=self.sender.currentData(), chat=self.chat.currentData(),
            ext=[e.strip().lstrip(".") for e in self.ext.text().replace(" ", ",").split(",") if e.strip()] or None,
            after=self.after.date().toString("yyyy-MM-dd") if self.after_on.isChecked() else None,
            before=self.before.date().toString("yyyy-MM-dd") if self.before_on.isChecked() else None,
            min_size=self.min_size.text().strip() or None, max_size=self.max_size.text().strip() or None,
            min_duration=self.min_dur.text().strip() or None, max_duration=self.max_dur.text().strip() or None,
            flagged=self.flagged.isChecked())

    def query_parts(self) -> list[str]:
        q = self.spec().to_query()
        return q.split(" ") if q else []

    def query(self) -> str:
        return self.spec().to_query()


# ============================================================================ browser
class MessageBrowser(QWidget):
    """Search box + optional filters + virtual table + bulk bar + details."""

    queryChanged = Signal(str)

    def __init__(self, gui, *, filters: bool = True, search: bool = True, base_query: str = "",  # type: ignore[no-untyped-def]
                 placeholder: str | None = None) -> None:
        super().__init__()
        self.gui = gui
        self.base_query = base_query
        t = T()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = SearchBox(gui.icons.pixmap("search", gui.pal.text_subtle, 16), placeholder or t("explorer.search_placeholder"))
        self.search.setVisible(search)
        bar.addWidget(self.search, 1)
        self.filter_btn = button(t("filters.title"), gui.icons.icon("sliders-horizontal", size=15))
        self.filter_btn.setCheckable(True)
        self.filter_btn.setVisible(filters)
        bar.addWidget(self.filter_btn)
        self.details_btn = tool(gui.icons.icon("panel-left"), t("explorer.toggle_details"), checkable=True)
        bar.addWidget(self.details_btn)
        if not search:
            bar.insertStretch(0, 1)
        lay.addLayout(bar)
        self.status = label("", "Muted")
        self.error = label("", None, wrap=True)
        self.error.setObjectName("DangerBanner")
        self.error.setVisible(False)
        lay.addWidget(self.error)

        self.table = MessageTable(gui)
        self.bulk = BulkBar(gui, self.table)
        lay.addWidget(self.bulk)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.filters = FilterPanel(gui) if filters else None
        if self.filters:
            split.addWidget(self.filters)
            self.filters.setVisible(False)
            self.filters.changed.connect(self.apply)
            self.filter_btn.toggled.connect(self.filters.setVisible)
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        cl.addWidget(self.table, 1)
        cl.addWidget(self.status)
        split.addWidget(center)
        self.details = DetailPanel(gui)
        self.details.setVisible(False)
        split.addWidget(self.details)
        split.setStretchFactor(split.indexOf(center), 1)
        lay.addWidget(split, 1)
        self.empty = EmptyState(gui.icons.pixmap("search", gui.pal.text_subtle, 40), t("explorer.no_results"), t("explorer.no_results_text"))
        self.empty.setVisible(False)
        cl.insertWidget(0, self.empty, 1)

        self.search.debounced.connect(lambda _q: self.apply())
        self.search.submitted.connect(lambda _q: self.apply())
        self.table.countChanged.connect(self._count)
        self.table.currentChanged.connect(self._current)
        self.details_btn.toggled.connect(self._toggle_details)
        self.details.closed.connect(lambda: self.details_btn.setChecked(False))
        self._last_query: str | None = None

    def _toggle_details(self, on: bool) -> None:
        self.details.setVisible(on)
        if on:
            self.details.show_message(self.table.current_id())

    def _current(self, mid) -> None:  # type: ignore[no-untyped-def]
        if self.details.isVisible():
            self.details.show_message(mid)

    def full_query(self) -> str:
        parts = [self.base_query, self.search.text().strip(), self.filters.query() if self.filters else ""]
        return " ".join(p for p in parts if p)

    def set_text(self, q: str) -> None:
        self.search.blockSignals(True)
        self.search.setText(q)
        self.search.blockSignals(False)
        self.apply()

    def apply(self) -> None:
        q = self.full_query()
        if q == self._last_query:
            return
        sel = self.gui.selection
        if sel.ids and self._last_query is not None:
            policy = self.gui.settings.selection_on_filter_change
            if policy == "clear":
                sel.clear()
            elif policy == "ask":
                n = len(sel.ids)
                self.gui.notify(T()("explorer.selection_kept", n=n), T()("explorer.selection_kept_text"), "info",
                                (T()("explorer.clear_selection"), sel.clear))
        ok = self.table.set_query(q)
        self.error.setVisible(not ok)
        if not ok:
            try:
                self.gui.ctx.search.compile(q)
            except Exception as exc:
                self.error.setText("  " + T()("search.invalid", error=str(exc)))
            return
        self._last_query = q
        if self.filters:
            n = self.filters.active_count()
            self.filter_btn.setText(T()("filters.title") + (f"  ({T().num(n)})" if n else ""))
        self.queryChanged.emit(q)
        self.bulk.update_state()

    def refresh(self) -> None:
        self._last_query = None
        if self.filters:
            self.filters.reload()
        self.apply()

    def _count(self, n: int) -> None:
        t = T()
        self.status.setText(t("explorer.results_n", n=n) + "   ·   " + t("explorer.selection_hint"))
        self.empty.setVisible(n == 0)
        self.table.setVisible(n > 0)

