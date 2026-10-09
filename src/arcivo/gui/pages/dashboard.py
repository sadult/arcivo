"""Overview: archive summary tiles, storage bar, activity, content types, recents and collections."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from ..theme.tokens import CATEGORY_COLORS, SYSTEM, TYPE_COLORS
from ..widgets.charts import ChartView
from ..widgets.common import (
    Card,
    EmptyState,
    FlowLayout,
    InsetList,
    InsetRow,
    LegendItem,
    StatCard,
    StorageBar,
    button,
    label,
)
from ..widgets.messages_model import TYPE_ICONS
from .base import Page

TILES = [  # key, icon, color, query
    ("messages", "messages-square", SYSTEM["indigo"], ""),
    ("files", "files", SYSTEM["teal"], "has:file"),
    ("total_bytes", "hard-drive", SYSTEM["orange"], "has:file sort:size"),
    ("tagged", "tags", SYSTEM["purple"], "is:tagged"),
]
CATEGORY_ORDER = ["images", "videos", "documents", "audio", "voice", "stickers", "other", "text"]
CATEGORY_QUERY = {"images": "type:image", "videos": "type:videos", "documents": "type:document", "audio": "type:audio",
                  "voice": "type:voice", "stickers": "type:sticker", "text": "type:text", "other": ""}


class DashboardPage(Page):
    key = "dashboard"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("dashboard.sync_now"), g.icons.icon("refresh-cw", g.pal.text, 14), on_click=lambda: g.sync()))
        self.actions.addWidget(button(t("dashboard.qa_export"), g.icons.icon("download", "#FFFFFF", 14), "primary",
                                      on_click=lambda: g.navigate("export")))

        self.tiles_row = QHBoxLayout()
        self.tiles_row.setSpacing(14)
        self.cards: dict[str, StatCard] = {}
        for key, icon, color, q in TILES:
            c = StatCard(g.icons.pixmap(icon, color, 16), color, t(f"dashboard.stat_{key}"), "—")
            c.clicked.connect(lambda q=q: g.explore(q))
            self.tiles_row.addWidget(c)
            self.cards[key] = c
        self.root.addLayout(self.tiles_row)

        # storage (macOS "Storage" settings look)
        self.storage_card = Card(padding=18)
        head = QHBoxLayout()
        head.addWidget(label(t("dashboard.storage_title"), "CardTitle"), 1)
        self.storage_total = label("", "Muted")
        head.addWidget(self.storage_total)
        self.storage_card.add(head)
        self.storage_bar = StorageBar(g.pal.track)
        self.storage_card.add(self.storage_bar)
        self.legend_host = QWidget()
        self.legend = FlowLayout(self.legend_host, spacing=18)
        self.storage_card.add(self.legend_host)
        self.root.addWidget(self.storage_card)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.activity_card = Card(t("dashboard.activity"), t("dashboard.activity_sub"))
        self.activity = ChartView(g.pal)
        self.activity.setMinimumHeight(250)
        self.activity_card.add(self.activity)
        row.addWidget(self.activity_card, 3)
        self.types_card = Card(t("dashboard.by_type"))
        self.types = InsetList()
        self.types_card.add(self.types)
        self.types_card.body.addStretch(1)
        row.addWidget(self.types_card, 2)
        self.root.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(14)
        self.recent_card = Card(t("dashboard.recent"), actions=[button(t("common.view_all"), variant="ghost", on_click=lambda: g.explore(""))])
        self.recent = InsetList()
        self.recent_card.add(self.recent)
        self.recent_card.body.addStretch(1)
        row2.addWidget(self.recent_card, 3)
        self.large_card = Card(t("dashboard.largest"), actions=[button(t("common.view_all"), variant="ghost",
                                                                       on_click=lambda: g.navigate("storage"))])
        self.large = InsetList()
        self.large_card.add(self.large)
        self.large_card.body.addStretch(1)
        row2.addWidget(self.large_card, 2)
        self.root.addLayout(row2)

        self.collections_card = Card(t("dashboard.collections"),
                                     actions=[button(t("common.manage"), variant="ghost", on_click=lambda: g.navigate("collections"))])
        self.col_grid = QGridLayout()
        self.col_grid.setSpacing(10)
        self.collections_card.add(self.col_grid)
        self.root.addWidget(self.collections_card)
        self.empty = EmptyState(g.icons.pixmap("refresh-cw", g.pal.text_subtle, 40), t("dashboard.empty_title"), t("dashboard.empty_text"),
                                button(t("dashboard.sync_now"), None, "primary", on_click=lambda: g.sync()))
        self.root.addWidget(self.empty)
        self.root.addStretch(1)

    def _open_message(self, mid: int) -> None:
        self.gui.navigate("explorer", query="", focus_id=mid)

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished", "collections.changed"):
            self.mark_dirty()

    @staticmethod
    def _clear_layout(lay) -> None:  # type: ignore[no-untyped-def]
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget() if it is not None else None
            if w:
                w.hide()
                w.deleteLater()

    def refresh(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        has = bool(aid) and g.ctx.messages.total(aid) > 0
        for w in (self.storage_card, self.activity_card, self.types_card, self.recent_card, self.large_card, self.collections_card,
                  *self.cards.values()):
            w.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            return
        a = g.ctx.analytics
        ov = a.overview(aid)
        for key, card in self.cards.items():
            v = ov.get(key, 0)
            card.value.setText(t.size(v) if key == "total_bytes" else t.num(v))
        self.cards["messages"].sub.setText(t("dashboard.last_30d", n=ov["last_30d"]))
        self.cards["files"].sub.setText(t("dashboard.files_sub", images=ov["images"], videos=ov["videos"]))
        self.cards["total_bytes"].sub.setText(t("dashboard.files_n", n=ov["files"]))
        self.cards["tagged"].sub.setText(t("dashboard.tagged_sub", pct=round(100 * ov["tagged"] / max(1, ov["messages"]))))

        # storage bar
        cats = {r["category"]: r for r in a.by_category(aid)}
        order = [c for c in CATEGORY_ORDER if c in cats and cats[c]["bytes"] > 0]
        self.storage_total.setText(t("dashboard.storage_total", size=t.size(ov["total_bytes"]), n=ov["files"]))
        self.storage_bar.set_segments([(c, cats[c]["bytes"], CATEGORY_COLORS.get(c, SYSTEM["gray"])) for c in order],
                                      {c: f"{t('categories.' + c)} · {t.size(cats[c]['bytes'])}" for c in order})
        self._clear_layout(self.legend)
        for c in order:
            item = LegendItem(CATEGORY_COLORS.get(c, SYSTEM["gray"]), t(f"categories.{c}"), t.size(cats[c]["bytes"]))
            item.clicked.connect(lambda q=CATEGORY_QUERY.get(c, ""): g.explore(q))
            self.legend.addWidget(item)

        tl = a.timeline(aid, "month")[-18:]
        self.activity.area([t.bucket_label(r["bucket"]) for r in tl],
                           [(t("dashboard.messages"), [r["n"] for r in tl], g.pal.accent)], fmt=lambda v: t.num(int(v)))

        chevron = g.icons.pixmap("chevron-right", g.pal.text_subtle, 14)
        self.types.clear()
        for r in a.by_type(aid)[:7]:
            mt = r["media_type"]
            row = InsetRow(g.icons.pixmap(TYPE_ICONS.get(mt, "file"), TYPE_COLORS.get(mt, SYSTEM["gray"]), 16), t(f"types.{mt}"),
                           trailing=t.num(r["n"]), chevron_px=chevron)
            row.clicked.connect(lambda mt=mt: g.explore(f"type:{mt}"))
            self.types.add(row)

        self.recent.clear()
        cq = g.ctx.search.compile("")
        for r in g.ctx.messages.page(aid, cq, 0, 7):
            mt = r["media_type"]
            text = (r["file_name"] or (r["text"] or "").replace("\n", " ")[:90] or t(f"types.{mt}"))
            row = InsetRow(g.icons.pixmap(TYPE_ICONS.get(mt, "file"), TYPE_COLORS.get(mt, SYSTEM["gray"]), 16), text,
                           t("types." + mt), trailing=t.relative(r["date_ts"]))
            row.clicked.connect(lambda mid=r["id"]: self._open_message(mid))
            self.recent.add(row)
        self.large.clear()
        for r in a.largest(aid, 7):
            row = InsetRow(g.icons.pixmap(TYPE_ICONS.get(r["media_type"], "file"), CATEGORY_COLORS.get(r["category"], SYSTEM["gray"]), 16),
                           r["file_name"] or t("types." + r["media_type"]), t.date(r["date_ts"]), trailing=t.size(r["file_size"]))
            row.clicked.connect(lambda mid=r["id"]: self._open_message(mid))
            self.large.add(row)

        self._clear_layout(self.col_grid)
        cols = [c for c in g.ctx.org.list_collections(aid) if c.pinned][:8]
        for i, c in enumerate(cols):
            card = Card(clickable=True, padding=12)
            card.setObjectName("Card")
            h = QHBoxLayout()
            h.setSpacing(8)
            ic = QLabel()
            ic.setPixmap(g.icons.pixmap(c.icon, c.color, 16))
            h.addWidget(ic)
            h.addWidget(label(c.name, None), 1)
            h.addWidget(label(t.num(c.count or 0), "Muted"))
            card.add(h)
            card.clicked.connect(lambda cid=c.id: g.navigate("collections", collection_id=cid))
            self.col_grid.addWidget(card, i // 4, i % 4)
        self.collections_card.setVisible(bool(cols))
        _ = Qt
