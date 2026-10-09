"""Statistics and Storage analyzer pages."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ...domain.formatting import parse_size
from ...services.analytics import TimeRange
from ...services.storage import METHODS, keep_selection
from ..theme.tokens import CATEGORY_COLORS, TYPE_COLORS
from ..widgets.charts import ChartView, Heatmap, palette_color
from ..widgets.common import Card, EmptyState, KeyValueGrid, Segmented, StatCard, button, label
from ..widgets.messages_model import TYPE_ICONS
from .base import Page

RANGES = [("30", 30), ("90", 90), ("365", 365), ("all", None)]


def _table(headers: list[str], stretch: int = 0) -> QTableWidget:
    tb = QTableWidget(0, len(headers))
    tb.setHorizontalHeaderLabels(headers)
    tb.verticalHeader().setVisible(False)
    tb.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tb.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    tb.setShowGrid(False)
    tb.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    tb.verticalHeader().setDefaultSectionSize(34)
    return tb


def _num_item(text: str, value: float) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setData(Qt.ItemDataRole.UserRole, value)
    it.setTextAlignment(int(Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter))
    return it


class StatisticsPage(Page):
    key = "statistics"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.range = Segmented([(k, t(f"stats.range_{k}")) for k, _ in RANGES], "365")
        self.range.changed.connect(lambda _k: self.mark_dirty())
        self.bucket = QComboBox()
        for b in ("day", "week", "month", "year"):
            self.bucket.addItem(t(f"stats.bucket_{b}"), b)
        self.bucket.setCurrentIndex(2)
        self.bucket.currentIndexChanged.connect(lambda _i: self.mark_dirty())
        self.actions.addWidget(self.range)
        self.actions.addWidget(self.bucket)

        self.kpis = QGridLayout()
        self.kpis.setSpacing(12)
        self.kpi: dict[str, StatCard] = {}
        for i, (k, icon, color) in enumerate((("messages", "messages-square", "#7C83FD"), ("bytes", "hard-drive", "#F5A524"),
                                               ("per_day", "calendar", "#36C2B4"), ("busiest", "flag", "#F2545B"),
                                               ("duration", "clock", "#B07CFF"), ("forwarded", "arrow-right", "#4C8DFF"))):
            c = StatCard(g.icons.pixmap(icon, color, 18), color, t(f"stats.kpi_{k}"), "—", clickable=False)
            self.kpis.addWidget(c, 0, i)
            self.kpi[k] = c
        self.root.addLayout(self.kpis)

        self.timeline = ChartView(g.pal, 280)
        self.timeline.clicked.connect(self._bucket_clicked)
        c = Card(t("stats.timeline"), t("stats.timeline_sub"))
        c.add(self.timeline)
        self.root.addWidget(c)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.types = ChartView(g.pal, 300)
        self.types.clicked.connect(lambda k: g.explore(f"type:{k}"))
        c1 = Card(t("stats.by_type"), t("stats.click_to_explore"))
        c1.add(self.types)
        row.addWidget(c1, 3)
        self.cats = ChartView(g.pal, 300)
        c2 = Card(t("stats.by_size"), t("stats.by_size_sub"))
        c2.add(self.cats)
        row.addWidget(c2, 2)
        self.root.addLayout(row)

        self.growth = ChartView(g.pal, 240)
        c = Card(t("stats.growth"), t("stats.growth_sub"))
        c.add(self.growth)
        self.root.addWidget(c)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.hours = ChartView(g.pal, 220)
        c = Card(t("stats.hours"))
        c.add(self.hours)
        row.addWidget(c, 3)
        self.weekdays = ChartView(g.pal, 220)
        c = Card(t("stats.weekdays"))
        c.add(self.weekdays)
        row.addWidget(c, 2)
        self.root.addLayout(row)

        self.heat = Heatmap(g.pal)
        c = Card(t("stats.heatmap"), t("stats.heatmap_sub"))
        c.add(self.heat)
        self.root.addWidget(c)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.tops: dict[str, QTableWidget] = {}
        for i, what in enumerate(("senders", "chats", "domains", "extensions")):
            tb = _table([t(f"stats.top_{what}"), t("stats.count"), t("stats.size")])
            tb.setMinimumHeight(300)
            tb.cellDoubleClicked.connect(lambda r, _c, w=what: self._top_clicked(w, r))
            c = Card(t(f"stats.top_{what}_title"))
            c.add(tb)
            grid.addWidget(c, i // 2, i % 2)
            self.tops[what] = tb
        self.root.addLayout(grid)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.sizes = ChartView(g.pal, 240)
        c = Card(t("stats.size_dist"))
        c.add(self.sizes)
        row.addWidget(c, 3)
        self.avg = KeyValueGrid()
        c = Card(t("stats.media_avg"))
        c.add(self.avg)
        c.add(QWidget(), 1)
        row.addWidget(c, 2)
        self.root.addLayout(row)
        self.empty = EmptyState(g.icons.pixmap("chart-column", g.pal.text_subtle, 40), t("stats.empty"), t("dashboard.empty_text"))
        self.root.addWidget(self.empty)
        self.root.addStretch(1)

    def _rng(self) -> TimeRange:
        return TimeRange.last(dict(RANGES)[self.range.value()])

    def _bucket_clicked(self, key: str) -> None:
        b = self.bucket.currentData()
        if (b == "month" and len(key) == 7) or b == "day" or b == "year":
            self.gui.explore(f"date:{key}")

    def _top_clicked(self, what: str, row: int) -> None:
        it = self.tops[what].item(row, 0)
        if not it:
            return
        v = it.data(Qt.ItemDataRole.UserRole) or it.text()
        q = {"senders": f'sender:"{v}"', "chats": f'chat:"{v}"', "domains": f"{v}", "extensions": f"ext:{v}"}[what]
        self.gui.explore(q)

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished"):
            self.mark_dirty()

    def refresh(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        has = bool(aid) and g.ctx.messages.total(aid) > 0
        for i in range(self.root.count()):
            it = self.root.itemAt(i)
            w = it.widget()
            if w is not None and w is not self.empty:
                w.setVisible(has)
            elif it.layout() is not None:
                for j in range(it.layout().count()):
                    ww = it.layout().itemAt(j).widget()
                    if ww:
                        ww.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            return
        a, rng = g.ctx.analytics, self._rng()
        ov = a.overview(aid, rng)
        days = max(1, ((ov["last_ts"] or 0) - (ov["first_ts"] or 0)) / 86400) if ov["messages"] else 1
        top_day = a.top_days(aid, 1, rng)
        self.kpi["messages"].value.setText(t.num(ov["messages"]))
        self.kpi["bytes"].value.setText(t.size(ov["total_bytes"]))
        self.kpi["per_day"].value.setText(t.num(round(ov["messages"] / days, 1)))
        self.kpi["busiest"].value.setText(t.num(top_day[0]["n"]) if top_day else "—")
        self.kpi["busiest"].sub.setText(t.bucket_label(top_day[0]["day"]) if top_day else "")
        self.kpi["duration"].value.setText(t.duration(ov["total_duration"]))
        self.kpi["forwarded"].value.setText(t.num(ov["forwarded"]))

        bucket = self.bucket.currentData()
        tl = a.timeline(aid, bucket, rng)
        if bucket == "day":
            tl = tl[-120:]
        self.timeline.area([t.bucket_label(r["bucket"]) for r in tl],
                           [(t("stats.messages"), [r["n"] for r in tl], g.pal.accent)], keys=[r["bucket"] for r in tl],
                           fmt=lambda v: t.num(int(v)))
        bt = a.by_type(aid, rng)
        self.types.bars([t(f"types.{r['media_type']}") for r in bt], [r["n"] for r in bt], keys=[r["media_type"] for r in bt],
                        fmt=lambda v: t.num(int(v)), horizontal=True)
        cats = [c for c in a.by_category(aid, rng) if c["bytes"]]
        self.cats.donut([(t(f"categories.{c['category']}"), c["bytes"], CATEGORY_COLORS.get(c["category"], "#8A94A6"), c["category"])
                         for c in cats], fmt=lambda v: t.size(v), center_text=t.size(ov["total_bytes"]))
        gr = a.growth(aid, "month")
        self.growth.area([t.bucket_label(r["bucket"]) for r in gr],
                         [(t("stats.storage"), [r["bytes"] / 1024**2 for r in gr], "#36C2B4")], fmt=lambda v: t.size(v * 1024**2))
        hrs = a.hours(aid, rng)
        self.hours.bars([f"{h:02d}" for h in range(24)], hrs, color=g.pal.accent, fmt=lambda v: t.num(int(v)), max_labels=24)
        wd = a.weekdays(aid, rng)
        self.weekdays.bars([t(f"common.weekday_{i}") for i in range(7)], wd, color="#36C2B4", fmt=lambda v: t.num(int(v)))
        self.heat.set_data(a.heatmap(aid, rng))
        for what, tb in self.tops.items():
            rows = a.top(aid, what, 12, rng)
            tb.setRowCount(len(rows))
            for i, r in enumerate(rows):
                it = QTableWidgetItem(r["label"] or "—")
                it.setData(Qt.ItemDataRole.UserRole, r["label"])
                if what == "extensions":
                    it.setIcon(g.icons.icon("file", palette_color(i), 14))
                tb.setItem(i, 0, it)
                tb.setItem(i, 1, _num_item(t.num(r["n"]), r["n"]))
                tb.setItem(i, 2, _num_item(t.size(r["bytes"]) if r["bytes"] else "", r["bytes"]))
        sd = a.size_distribution(aid, rng)
        self.sizes.bars([r["label"] for r in sd], [r["n"] for r in sd], color="#F5A524", fmt=lambda v: t.num(int(v)))
        self.avg.clear()
        for r in a.media_averages(aid):
            self.avg.add(t(f"types.{r['media_type']}"),
                         t("stats.avg_line", avg=t.duration(r["avg_duration"]), max=t.duration(r["max_duration"]), size=t.size(r["avg_bytes"])))


class StoragePage(Page):
    key = "storage"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("storage.refresh"), g.icons.icon("rotate-ccw", size=15), on_click=self.mark_dirty))
        self.cards_row = QGridLayout()
        self.cards_row.setSpacing(12)
        self.cards: dict[str, StatCard] = {}
        for i, (k, icon, color) in enumerate((("total", "hard-drive", "#7C83FD"), ("media", "images", "#36C2B4"),
                                               ("documents", "file-text", "#F2545B"), ("wasted", "copy", "#F5A524"))):
            c = StatCard(g.icons.pixmap(icon, color, 18), color, t(f"storage.card_{k}"), "—")
            self.cards_row.addWidget(c, 0, i)
            self.cards[k] = c
        self.cards["wasted"].clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.cards["media"].clicked.connect(lambda: g.navigate("media"))
        self.cards["documents"].clicked.connect(lambda: g.explore("type:document sort:size"))
        self.root.addLayout(self.cards_row)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.donut = ChartView(g.pal, 280)
        self.donut.clicked.connect(lambda k: g.explore(self._cat_query(k)))
        c = Card(t("storage.by_category"), t("stats.click_to_explore"))
        c.add(self.donut)
        row.addWidget(c, 2)
        self.ext = ChartView(g.pal, 280)
        self.ext.clicked.connect(lambda k: g.explore(f"ext:{k} sort:size"))
        c = Card(t("storage.by_extension"), t("stats.click_to_explore"))
        c.add(self.ext)
        row.addWidget(c, 3)
        self.root.addLayout(row)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMinimumHeight(520)
        # large files
        lf = QWidget()
        ll = QGridLayout(lf)
        ll.setContentsMargins(0, 10, 0, 0)
        self.min_size = QLineEdit("10MB")
        self.min_size.setPlaceholderText("10MB")
        self.min_size.setMaximumWidth(120)
        self.cat = QComboBox()
        self.cat.addItem(self.t("storage.all_categories"), None)
        for cat in ("videos", "audio", "documents", "images", "voice", "stickers"):
            self.cat.addItem(t(f"categories.{cat}"), cat)
        self.min_size.editingFinished.connect(self._load_large)
        self.cat.currentIndexChanged.connect(lambda _i: self._load_large())
        ll.addWidget(label(t("storage.min_size"), "Muted"), 0, 0)
        ll.addWidget(self.min_size, 0, 1)
        ll.addWidget(self.cat, 0, 2)
        ll.setColumnStretch(3, 1)
        self.large_info = label("", "Muted")
        ll.addWidget(self.large_info, 0, 3)
        for j, (txt, icon, fn, variant) in enumerate(((t("explorer.tag"), "tag", lambda: g.actions.tag(self._checked_large()), None),
                                                       (t("explorer.export"), "download", lambda: g.actions.export(self._checked_large()), None),
                                                       (t("explorer.delete"), "trash-2", lambda: g.actions.delete(self._checked_large(), "storage-cleanup"), "danger"))):
            ll.addWidget(button(txt, g.icons.icon(icon, "#FFFFFF" if variant else None, 14), variant, on_click=fn), 0, 4 + j)
        self.large = _table(["", t("storage.col_name"), t("storage.col_type"), t("storage.col_size"), t("storage.col_date"),
                             t("storage.col_from")], stretch=1)
        self.large.setColumnWidth(0, 34)
        self.large.setColumnWidth(2, 110)
        self.large.setColumnWidth(3, 100)
        self.large.setColumnWidth(4, 120)
        self.large.setColumnWidth(5, 170)
        self.large.cellDoubleClicked.connect(lambda r, _c: g.navigate("explorer", query="", focus_id=self.large.item(r, 1).data(Qt.ItemDataRole.UserRole)))
        ll.addWidget(self.large, 1, 0, 1, 7)
        self.tabs.addTab(lf, g.icons.icon("hard-drive", size=15), t("storage.tab_large"))
        # extensions
        self.ext_table = _table([t("storage.col_ext"), t("stats.count"), t("stats.size"), t("storage.col_share")])
        self.ext_table.cellDoubleClicked.connect(lambda r, _c: g.explore(f"ext:{self.ext_table.item(r, 0).text()} sort:size"))
        self.tabs.addTab(self.ext_table, g.icons.icon("file", size=15), t("storage.tab_extensions"))
        # duplicates
        dup = QWidget()
        dl = QGridLayout(dup)
        dl.setContentsMargins(0, 10, 0, 0)
        self.method = QComboBox()
        for m in METHODS:
            self.method.addItem(t(f"storage.method_{m}"), m)
        self.method.currentIndexChanged.connect(lambda _i: self._load_dups())
        self.keep = QComboBox()
        self.keep.addItem(t("storage.keep_oldest"), "oldest")
        self.keep.addItem(t("storage.keep_newest"), "newest")
        dl.addWidget(label(t("storage.method"), "Muted"), 0, 0)
        dl.addWidget(self.method, 0, 1)
        dl.addWidget(self.keep, 0, 2)
        self.dup_info = label("", "Muted", wrap=True)
        dl.addWidget(self.dup_info, 0, 3)
        dl.setColumnStretch(3, 1)
        dl.addWidget(button(t("storage.select_dups"), g.icons.icon("square-check-big", size=14), on_click=self._select_dups), 0, 4)
        dl.addWidget(button(t("storage.review_delete"), g.icons.icon("trash-2", "#FFFFFF", 14), "danger", on_click=self._delete_dups), 0, 5)
        self.dups = QTreeWidget()
        self.dups.setHeaderLabels([t("storage.col_name"), t("storage.col_size"), t("storage.col_date"), t("storage.col_from"), "#"])
        self.dups.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in ((1, 100), (2, 120), (3, 160), (4, 90)):
            self.dups.setColumnWidth(i, w)
        dl.addWidget(self.dups, 1, 0, 1, 6)
        dl.addWidget(label(t("storage.dup_note"), "Subtle", wrap=True), 2, 0, 1, 6)
        self.tabs.addTab(dup, g.icons.icon("copy", size=15), t("storage.tab_duplicates"))
        self.root.addWidget(self.tabs)
        self.empty = EmptyState(g.icons.pixmap("hard-drive", g.pal.text_subtle, 40), t("stats.empty"), t("dashboard.empty_text"))
        self.root.addWidget(self.empty)
        self.root.addStretch(1)

    @staticmethod
    def _cat_query(cat: str) -> str:
        return {"images": "type:image", "videos": "type:video", "audio": "type:audio", "voice": "type:voice", "documents": "type:document",
                "stickers": "type:sticker"}.get(cat, "has:file") + " sort:size"

    def open(self, **kw: Any) -> None:
        if kw.get("tab") == "duplicates":
            self.tabs.setCurrentIndex(2)

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished"):
            self.mark_dirty()

    def refresh(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        has = bool(aid) and g.ctx.messages.total(aid) > 0
        self.tabs.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            return
        s = g.ctx.storage
        b = s.breakdown(aid)
        summary = s.duplicate_summary(aid)
        best = summary["media_id"]
        self.cards["total"].value.setText(t.size(b["total_bytes"]))
        self.cards["total"].sub.setText(t("storage.files_n", n=sum(c["n"] for c in b["categories"])))
        self.cards["media"].value.setText(t.size(b["media_bytes"]))
        self.cards["documents"].value.setText(t.size(b["documents_bytes"]))
        self.cards["wasted"].value.setText(t.size(best["wasted_bytes"]))
        self.cards["wasted"].sub.setText(t("storage.groups_n", n=best["groups"]))
        cats = [c for c in b["categories"] if c["bytes"]]
        self.donut.donut([(t(f"categories.{c['category']}"), c["bytes"], CATEGORY_COLORS.get(c["category"], "#8A94A6"), c["category"])
                          for c in cats], fmt=lambda v: t.size(v), center_text=t.size(b["total_bytes"]))
        ext = s.by_extension(aid, 40)
        top = ext[:12]
        self.ext.bars([r["extension"] for r in top], [r["bytes"] / 1024**2 for r in top], keys=[r["extension"] for r in top],
                      color="#7C83FD", fmt=lambda v: t.size(v * 1024**2), horizontal=True, axis_format="%.0f MB")
        total = b["total_bytes"] or 1
        self.ext_table.setRowCount(len(ext))
        for i, r in enumerate(ext):
            self.ext_table.setItem(i, 0, QTableWidgetItem(g.icons.icon("file", palette_color(i), 14), r["extension"]))
            self.ext_table.setItem(i, 1, _num_item(t.num(r["n"]), r["n"]))
            self.ext_table.setItem(i, 2, _num_item(t.size(r["bytes"]), r["bytes"]))
            self.ext_table.setItem(i, 3, _num_item(f"{r['bytes'] / total * 100:.1f}%", r["bytes"]))
        self._load_large()
        self._load_dups()

    def _load_large(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        if not aid:
            return
        try:
            mn = parse_size(self.min_size.text() or "0")
        except ValueError:
            mn = 0
        rows = g.ctx.storage.large_files(aid, mn, self.cat.currentData(), 300)
        self.large.setRowCount(len(rows))
        total = 0
        for i, r in enumerate(rows):
            total += r["file_size"] or 0
            chk = QTableWidgetItem()
            chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.large.setItem(i, 0, chk)
            it = QTableWidgetItem(g.icons.icon(TYPE_ICONS.get(r["media_type"], "file"), TYPE_COLORS.get(r["media_type"]), 15),
                                  r["file_name"] or t(f"types.{r['media_type']}"))
            it.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.large.setItem(i, 1, it)
            self.large.setItem(i, 2, QTableWidgetItem(t(f"types.{r['media_type']}")))
            self.large.setItem(i, 3, _num_item(t.size(r["file_size"]), r["file_size"] or 0))
            self.large.setItem(i, 4, QTableWidgetItem(t.date(r["date_ts"])))
            self.large.setItem(i, 5, QTableWidgetItem(r["sender_name"] or r["chat_name"] or ""))
        self.large_info.setText(t("storage.large_info", n=len(rows), size=t.size(total)))

    def _checked_large(self) -> list[int]:
        ids = []
        for i in range(self.large.rowCount()):
            if self.large.item(i, 0).checkState() == Qt.CheckState.Checked:
                ids.append(self.large.item(i, 1).data(Qt.ItemDataRole.UserRole))
        if not ids:
            self.gui.notify(self.t("storage.check_first"), "", "info")
        return ids

    def _load_dups(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        if not aid:
            return
        method = self.method.currentData()
        self.groups = g.ctx.storage.duplicates(aid, method, 300)
        self.dups.clear()
        wasted = 0
        for grp in self.groups:
            wasted += grp.wasted
            first = grp.members[0]
            parent = QTreeWidgetItem([f"{first['file_name'] or t('types.' + first['media_type'])}", t.size(grp.size), "", "",
                                      t("storage.copies_n", n=len(grp.members))])
            parent.setIcon(0, g.icons.icon(TYPE_ICONS.get(first["media_type"], "file"), TYPE_COLORS.get(first["media_type"]), 15))
            for m in grp.members:
                QTreeWidgetItem(parent, [m["file_name"] or "", t.size(m["file_size"]), t.date(m["date_ts"], with_time=True),
                                         m["sender_name"] or m["chat_name"] or "", f"#{t.num(m['id'])}"])
            self.dups.addTopLevelItem(parent)
        self.dup_info.setText(t("storage.dup_info", groups=len(self.groups), size=t.size(wasted),
                                confidence=t(f"storage.confidence_{METHODS[method][0]}")))

    def _dup_ids(self) -> list[int]:
        keep = self.keep.currentData()
        out: list[int] = []
        for grp in getattr(self, "groups", []):
            out.extend(keep_selection(grp, keep))
        return out

    def _select_dups(self) -> None:
        ids = self._dup_ids()
        self.gui.selection.set(ids)
        self.gui.notify(self.t("storage.selected_dups", n=len(ids)), self.t("storage.selected_dups_text"), "success",
                        (self.t("storage.open_explorer"), lambda: self.gui.explore("")))

    def _delete_dups(self) -> None:
        ids = self._dup_ids()
        method = self.method.currentData()
        ctx = self.t("storage.delete_context", confidence=self.t(f"storage.confidence_{METHODS[method][0]}"),
                     keep=self.keep.currentText())
        self.gui.actions.delete(ids, "duplicates", ctx)

