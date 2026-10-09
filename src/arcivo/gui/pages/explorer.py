"""Explorer (all messages with filters), Search (query language) and Collections/Tags pages."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...search.query import FIELD_ALIASES
from ..widgets.browser import MessageBrowser
from ..widgets.common import Card, FlowLayout, Segmented, button, label, tool
from ..widgets.dialogs import CollectionDialog
from .base import Page

QUICK_TYPES = [("all", ""), ("photos", "type:photo"), ("videos", "type:video"), ("audio", "type:audio"), ("voice", "type:voice"),
               ("documents", "type:document"), ("links", "has:link"), ("text", "type:text")]


class ExplorerPage(Page):
    key = "explorer"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        self.quick = Segmented([(k, t(f"explorer.quick_{k}")) for k, _ in QUICK_TYPES], "all")
        self.quick.changed.connect(self._quick)
        self.actions.addWidget(self.quick)
        self.actions.addWidget(button(t("explorer.save_collection"), g.icons.icon("sparkles", size=15), on_click=self._save))
        self.browser = MessageBrowser(g, filters=True)
        self.browser.base_query = ""
        self.root.addWidget(self.browser, 1)

    def _quick(self, key: str) -> None:
        self.browser.base_query = dict(QUICK_TYPES)[key]
        self.browser.apply()

    def _save(self) -> None:
        q = self.browser.full_query()
        dlg = CollectionDialog(self, self.gui, name="", query=q)
        if dlg.exec():
            v = dlg.values()
            self.gui.ctx.org.save_collection(v.pop("name"), v.pop("query"), **v)
            self.gui.notify(self.t("collections.saved"), "", "success")

    def open(self, **kw: Any) -> None:
        if "query" in kw:
            self.quick.set("all")
            self.browser.base_query = ""
            if self.browser.filters:
                self.browser.filters.reset()
            self.browser.set_text(kw["query"] or "")
        if kw.get("focus_id"):
            self.browser.details_btn.setChecked(True)
            self.browser.details.show_message(kw["focus_id"])

    def refresh(self) -> None:
        self.browser.refresh()

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished", "tags.changed"):
            self.mark_dirty()


EXAMPLES = [
    "invoice type:document",
    "type:audio size:>10MB",
    "type:video duration:>5m sort:size",
    "after:2025-01-01 before:2025-06-30 has:link",
    'sender:"Ali" -is:forwarded',
    "ext:pdf,docx tag:Work",
    "(type:photo OR type:video) date:2025",
    "is:flagged OR tag:Important",
]


class SearchPage(Page):
    key = "search"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("search.syntax"), g.icons.icon("circle-help", size=15), on_click=self.toggle_help))
        self.actions.addWidget(button(t("explorer.save_collection"), g.icons.icon("sparkles", size=15), on_click=self._save))
        chips = QWidget()
        fl = FlowLayout(chips)
        fl.addWidget(label(t("search.try"), "Muted"))
        for ex in EXAMPLES:
            b = button(ex, variant="ghost")
            b.setObjectName("Mono")
            b.clicked.connect(lambda _=False, q=ex: self.browser.set_text(q))
            fl.addWidget(b)
        self.root.addWidget(chips)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.browser = MessageBrowser(g, filters=False, placeholder=t("search.placeholder"))
        split.addWidget(self.browser)
        self.help = QTextBrowser()
        self.help.setObjectName("Card")
        self.help.setMinimumWidth(340)
        self.help.setMaximumWidth(440)
        self.help.setHtml(self._help_html())
        self.help.setVisible(False)
        split.addWidget(self.help)
        split.setStretchFactor(0, 1)
        self.root.addWidget(split, 1)

    def _help_html(self) -> str:
        t = self.t
        rows = [
            ("word", t("search.h_word")), ('"exact phrase"', t("search.h_phrase")), ("pre*", t("search.h_prefix")),
            ("-word", t("search.h_not")), ("a OR b", t("search.h_or")), ("( … )", t("search.h_group")),
            ("type:audio,voice", t("search.h_type")), ("ext:pdf", t("search.h_ext")), ("size:>10MB  size:1MB..50MB", t("search.h_size")),
            ("duration:>3m", t("search.h_duration")), ("date:2025-03  after:2025-01-01", t("search.h_date")),
            ("date:today / yesterday / last7d", t("search.h_date_rel")), ("sender:name  chat:name", t("search.h_people")),
            ("tag:Work", t("search.h_tag")), ("has:link / media / note / caption", t("search.h_has")),
            ("is:flagged / forwarded / edited / untagged", t("search.h_is")), ("name:report  text:hello", t("search.h_fields")),
            ("sort:size order:asc", t("search.h_sort")),
        ]
        body = "".join(f"<tr><td style='padding:4px 10px 4px 0'><code>{a}</code></td><td style='padding:4px 0'>{b}</td></tr>" for a, b in rows)
        fields = ", ".join(sorted(set(FIELD_ALIASES.values())))
        return (f"<div><h3>{t('search.syntax')}</h3><p>{t('search.h_intro')}</p><table>{body}</table>"
                f"<p style='color:gray'>{t('search.h_fields_list', fields=fields)}</p><p>{t('search.h_persian')}</p></div>")

    def toggle_help(self) -> None:
        self.help.setVisible(not self.help.isVisible())

    def _save(self) -> None:
        q = self.browser.full_query()
        if not q:
            return
        dlg = CollectionDialog(self, self.gui, name=q[:40], query=q)
        if dlg.exec():
            v = dlg.values()
            self.gui.ctx.org.save_collection(v.pop("name"), v.pop("query"), **v)
            self.gui.notify(self.t("collections.saved"), "", "success")

    def open(self, **kw: Any) -> None:
        if kw.get("query") is not None:
            self.browser.set_text(kw["query"])
        if kw.get("help"):
            self.help.setVisible(True)
        self.browser.search.setFocus()

    def refresh(self) -> None:
        self.browser.refresh()

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished"):
            self.mark_dirty()


class CollectionsPage(Page):
    key = "collections"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("collections.new"), g.icons.icon("plus", "#FFFFFF", 15), "primary", on_click=self._new))
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setObjectName("PlainList")
        self.list.setMinimumWidth(280)
        self.list.setMaximumWidth(360)
        self.list.currentItemChanged.connect(lambda cur, _p: self._select(cur))
        ll.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.edit_btn = button(t("common.edit"), g.icons.icon("sliders-horizontal", size=14), on_click=self._edit)
        self.del_btn = button(t("common.delete"), g.icons.icon("trash-2", size=14), on_click=self._delete)
        row.addWidget(self.edit_btn)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        ll.addLayout(row)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.c_icon = QLabel()
        self.c_title = label("", "SectionTitle")
        self.c_query = label("", "Mono", selectable=True)
        head.addWidget(self.c_icon)
        head.addWidget(self.c_title)
        head.addWidget(self.c_query, 1)
        self.export_btn = button(t("collections.export"), g.icons.icon("download", size=14),
                                 on_click=lambda: g.actions.export(query=self.browser.full_query()))
        head.addWidget(self.export_btn)
        rl.addLayout(head)
        self.browser = MessageBrowser(g, filters=False, search=True, placeholder=t("collections.search_within"))
        rl.addWidget(self.browser, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.root.addWidget(split, 1)
        self._pending: int | None = None

    def refresh(self) -> None:
        g = self.gui
        cur = self._pending or (self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None)
        self.list.blockSignals(True)
        self.list.clear()
        self.cols = {c.id: c for c in g.ctx.org.list_collections(g.account_id)}
        select = None
        for c in self.cols.values():
            it = QListWidgetItem(g.icons.icon(c.icon, c.color, 16), f"{c.name}\n{self.t.num(c.count or 0)} · {c.query[:38]}")
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            self.list.addItem(it)
            if c.id == cur:
                select = it
        self.list.blockSignals(False)
        if select is None and self.list.count():
            select = self.list.item(0)
        if select is not None:
            self.list.setCurrentItem(select)
            self._select(select)
        self._pending = None

    def _select(self, it: QListWidgetItem | None) -> None:
        if it is None:
            return
        c = self.cols.get(it.data(Qt.ItemDataRole.UserRole))
        if c is None:
            return
        self.c_icon.setPixmap(self.gui.icons.pixmap(c.icon, c.color, 20))
        self.c_title.setText(c.name)
        self.c_query.setText(c.query)
        self.browser.base_query = c.query
        self.browser.search.clear()
        self.browser.refresh()

    def _current(self):  # type: ignore[no-untyped-def]
        it = self.list.currentItem()
        return self.cols.get(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _new(self) -> None:
        dlg = CollectionDialog(self, self.gui)
        if dlg.exec():
            v = dlg.values()
            c = self.gui.ctx.org.save_collection(v.pop("name"), v.pop("query"), **v)
            self._pending = c.id
            self.mark_dirty()

    def _edit(self) -> None:
        c = self._current()
        if c is None:
            return
        dlg = CollectionDialog(self, self.gui, c.name, c.query, c.icon, c.color, c.pinned)
        if dlg.exec():
            self.gui.ctx.org.update_collection(c.id, **dlg.values())
            self._pending = c.id
            self.mark_dirty()

    def _delete(self) -> None:
        c = self._current()
        if c and QMessageBox.question(self, self.t("collections.delete_title"), self.t("collections.delete_text", name=c.name)) \
                == QMessageBox.StandardButton.Yes:
            self.gui.ctx.org.delete_collection(c.id)
            self.mark_dirty()

    def open(self, **kw: Any) -> None:
        if kw.get("collection_id"):
            self._pending = kw["collection_id"]
            self.mark_dirty()

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("collections.changed", "data.changed", "sync.finished"):
            self.mark_dirty()


class TagsPage(Page):
    key = "tags"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("tags.create"), g.icons.icon("plus", "#FFFFFF", 15), "primary", on_click=self._create))
        card = Card(t("tags.all"), t("tags.all_sub"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([t("tags.name"), t("tags.messages"), t("tags.description"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 110)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(3, 170)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open(r))
        self.table.setMinimumHeight(420)
        card.add(self.table)
        self.root.addWidget(card)
        tips = Card(t("tags.tips"))
        tips.add(label(t("tags.tips_text"), "Muted", wrap=True))
        self.root.addWidget(tips)
        self.root.addStretch(1)

    def refresh(self) -> None:
        g, t = self.gui, self.t
        self.tags = g.ctx.org.list_tags()
        self.table.setRowCount(len(self.tags))
        for i, tag in enumerate(self.tags):
            self.table.setItem(i, 0, QTableWidgetItem(g.icons.icon("tag", tag.color, 16), tag.name))
            self.table.setItem(i, 1, QTableWidgetItem(t.num(tag.count)))
            self.table.setItem(i, 2, QTableWidgetItem(tag.description or ""))
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(2)
            h.addWidget(tool(g.icons.icon("search"), t("tags.show"), lambda r=i: self._open(r)))
            h.addWidget(tool(g.icons.icon("sliders-horizontal"), t("tags.rename"), lambda r=i: self._rename(r)))
            h.addWidget(tool(g.icons.icon("sun"), t("tags.recolor"), lambda r=i: self._recolor(r)))
            h.addWidget(tool(g.icons.icon("trash-2", g.pal.danger), t("common.delete"), lambda r=i: self._delete(r)))
            self.table.setCellWidget(i, 3, w)

    def _open(self, r: int) -> None:
        name = self.tags[r].name
        self.gui.explore(f'tag:"{name}"' if " " in name else f"tag:{name}")

    def _create(self) -> None:
        name, ok = QInputDialog.getText(self, self.t("tags.create"), self.t("tags.name"))
        if ok and name.strip():
            try:
                self.gui.ctx.org.create_tag(name.strip())
            except Exception as exc:
                self.gui.show_error(exc, self.t("tags.create_failed"))

    def _rename(self, r: int) -> None:
        tag = self.tags[r]
        name, ok = QInputDialog.getText(self, self.t("tags.rename"), self.t("tags.name"), text=tag.name)
        if ok and name.strip():
            self.gui.ctx.org.update_tag(tag.id, name=name.strip())

    def _recolor(self, r: int) -> None:
        tag = self.tags[r]
        c = QColorDialog.getColor(QColor(tag.color), self)
        if c.isValid():
            self.gui.ctx.org.update_tag(tag.id, color=c.name())

    def _delete(self, r: int) -> None:
        tag = self.tags[r]
        if QMessageBox.question(self, self.t("tags.delete_title"), self.t("tags.delete_text", name=tag.name, n=tag.count)) \
                == QMessageBox.StandardButton.Yes:
            self.gui.ctx.org.delete_tag(tag.id)

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("tags.changed", "data.changed"):
            self.mark_dirty()



