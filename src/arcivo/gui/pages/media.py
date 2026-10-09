"""Media browser: thumbnail grid for photos, videos, audio, voice, documents and stickers."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QListView, QStyle, QStyledItemDelegate

from ..theme.style import qcolor
from ..theme.tokens import TYPE_COLORS
from ..widgets.browser import BulkBar, DetailPanel
from ..widgets.common import EmptyState, SearchBox, Segmented, hbox, label
from ..widgets.messages_model import TYPE_ICONS, MessagesModel
from .base import Page

KINDS = [("all", "has:media -type:sticker"), ("photos", "type:photo"), ("videos", "type:video"), ("gifs", "type:animation"),
         ("audio", "type:audio"), ("voice", "type:voice"), ("documents", "type:document"), ("stickers", "type:sticker")]
SORTS = [("date_desc", "sort:date"), ("date_asc", "sort:date order:asc"), ("size_desc", "sort:size"), ("name_asc", "sort:name order:asc"),
         ("duration_desc", "sort:duration")]


class ThumbCache:
    def __init__(self, gui) -> None:  # type: ignore[no-untyped-def]
        self.gui = gui
        self.pix: dict[int, QPixmap | None] = {}
        self.pending: set[int] = set()
        self.on_ready = None

    def get(self, mid: int) -> QPixmap | None:
        if mid in self.pix:
            return self.pix[mid]
        aid = self.gui.account_id
        p = self.gui.ctx.cache.thumbnail_path(aid, mid)
        if p:
            px = QPixmap(str(p))
            self.pix[mid] = None if px.isNull() else px
            return self.pix[mid]
        if mid not in self.pending and len(self.pending) < 24:
            self.pending.add(mid)
            self.gui.runtime.submit(self.gui.ctx.cache.fetch_thumbnail(aid, mid), lambda path, m=mid: self._done(m, path),
                                    lambda _e, m=mid: self._done(m, None))
        return None

    def _done(self, mid: int, path) -> None:  # type: ignore[no-untyped-def]
        self.pending.discard(mid)
        px = QPixmap(str(path)) if path else QPixmap()
        self.pix[mid] = None if px.isNull() else px
        if self.on_ready:
            self.on_ready(mid)


class TileDelegate(QStyledItemDelegate):
    W, H = 188, 196

    def __init__(self, gui, model: MessagesModel, thumbs: ThumbCache) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.gui = gui
        self.model = model
        self.thumbs = thumbs

    def sizeHint(self, _o, _i) -> QSize:  # type: ignore[no-untyped-def]
        return QSize(self.W, self.H)

    def paint(self, p: QPainter, opt, idx: QModelIndex) -> None:  # type: ignore[no-untyped-def]
        r = self.model.row_at(idx.row())
        if r is None:
            return
        g, t, pal = self.gui, self.gui.t, self.gui.pal
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(opt.rect.adjusted(6, 6, -6, -6))
        selected = g.selection.contains(r["id"])
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        current = bool(opt.state & QStyle.StateFlag.State_HasFocus)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, qcolor(pal.hover if hover else pal.surface_alt))
        pen = QPen(qcolor(pal.accent if selected or current else pal.border), 2 if selected else 1)
        p.setPen(pen)
        p.drawPath(path)
        thumb = QRectF(rect.x() + 8, rect.y() + 8, rect.width() - 16, 118)
        tp = QPainterPath()
        tp.addRoundedRect(thumb, 9, 9)
        mt = r["media_type"]
        color = qcolor(TYPE_COLORS.get(mt, "#8A94A6"))
        px = self.thumbs.get(r["id"]) if r["has_thumb"] and not g.settings.privacy.hide_previews_in_screenshots else None
        p.setClipPath(tp)
        if px is not None:
            scaled = px.scaled(thumb.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            sx = (scaled.width() - thumb.width()) / 2
            sy = (scaled.height() - thumb.height()) / 2
            p.drawPixmap(thumb.toRect(), scaled, QRect(int(sx), int(sy), int(thumb.width()), int(thumb.height())))
        else:
            grad = QLinearGradient(thumb.topLeft(), thumb.bottomRight())
            c1, c2 = QColor(color), QColor(color)
            c1.setAlpha(70)
            c2.setAlpha(25)
            grad.setColorAt(0, c1)
            grad.setColorAt(1, c2)
            p.fillRect(thumb, grad)
            icon = g.icons.pixmap(TYPE_ICONS.get(mt, "file"), color.name(), 34)
            s = icon.deviceIndependentSize()
            p.drawPixmap(int(thumb.center().x() - s.width() / 2), int(thumb.center().y() - s.height() / 2), icon)
            if r["extension"]:
                p.setPen(qcolor(pal.text_muted))
                f = p.font()
                f.setPixelSize(11)
                f.setBold(True)
                p.setFont(f)
                p.drawText(thumb.adjusted(0, 0, 0, -10), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, r["extension"].upper())
        p.setClipping(False)
        if r["duration"] and mt in ("video", "animation", "video_note", "audio", "voice"):
            badge = t.duration(r["duration"])
            f = p.font()
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            w = p.fontMetrics().horizontalAdvance(badge) + 12
            br = QRectF(thumb.right() - w - 6, thumb.bottom() - 24, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(br, 9, 9)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, badge)
        # checkbox
        cb = QRectF(thumb.x() + 8, thumb.y() + 8, 20, 20)
        if selected or hover:
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(qcolor(pal.accent) if selected else QColor(0, 0, 0, 90))
            p.drawRoundedRect(cb, 6, 6)
            if selected:
                p.drawPixmap(int(cb.x() + 2), int(cb.y() + 2), g.icons.pixmap("check", "#FFFFFF", 16))
        # text
        name = r["file_name"] or (f"{r['performer']} — {r['audio_title']}" if r["performer"] else "") or (r["text"] or "")[:60] \
            or t(f"types.{mt}")
        f = p.font()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(qcolor(pal.text))
        tr = QRectF(rect.x() + 10, thumb.bottom() + 8, rect.width() - 20, 18)
        p.drawText(tr, Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, int(tr.width())))
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(qcolor(pal.text_subtle))
        meta = " · ".join(x for x in (t.size(r["file_size"]) if r["file_size"] else "", t.date(r["date_ts"])) if x)
        p.drawText(QRectF(tr.x(), tr.bottom() + 2, tr.width(), 16), Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter, meta)
        p.restore()


class MediaPage(Page):
    key = "media"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        self.kind = Segmented([(k, t(f"media.kind_{k}")) for k, _ in KINDS], "all")
        self.kind.changed.connect(lambda _k: self.apply())
        self.sort = QComboBox()
        for k, _q in SORTS:
            self.sort.addItem(t(f"media.sort_{k}"), k)
        self.sort.currentIndexChanged.connect(lambda _i: self.apply())
        self.search = SearchBox(g.icons.pixmap("search", g.pal.text_subtle, 16), t("media.search_placeholder"))
        self.search.debounced.connect(lambda _q: self.apply())
        self.search.submitted.connect(lambda _q: self.apply())
        self.root.addLayout(hbox(self.kind, self.search, self.sort, stretch_at=1))
        self.model = MessagesModel(g, g.selection, 300)
        self.thumbs = ThumbCache(g)
        self.view = QListView()
        self.view.setObjectName("MediaGrid")
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(0)
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setDragEnabled(True)
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setModel(self.model)
        self.view.setItemDelegate(TileDelegate(g, self.model, self.thumbs))
        self.thumbs.on_ready = lambda _m: self.view.viewport().update()
        self.view.clicked.connect(self._clicked)
        self.view.doubleClicked.connect(lambda idx: g.selection.toggle(self.model.id_at(idx.row())))
        self.bulk = BulkBar(g, None)
        self.root.addWidget(self.bulk)
        self.details = DetailPanel(g)
        self.details.setVisible(False)
        self.details.closed.connect(lambda: self.details.setVisible(False))
        from PySide6.QtWidgets import QSplitter
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.view)
        split.addWidget(self.details)
        split.setStretchFactor(0, 1)
        self.empty = EmptyState(g.icons.pixmap("images", g.pal.text_subtle, 40), t("media.empty"), t("media.empty_text"))
        self.root.addWidget(self.empty, 1)
        self.root.addWidget(split, 1)
        self.status = label("", "Muted")
        self.root.addWidget(self.status)
        g.selection.changed.connect(self.view.viewport().update)
        self._anchor: int | None = None

    def _clicked(self, idx: QModelIndex) -> None:
        from PySide6.QtWidgets import QApplication
        mid = self.model.id_at(idx.row())
        if mid is None:
            return
        mods = QApplication.keyboardModifiers()
        rect = self.view.visualRect(idx)
        pos = self.view.viewport().mapFromGlobal(self.view.cursor().pos())
        in_box = QRect(rect.x() + 14, rect.y() + 14, 26, 26).contains(pos)
        if mods & Qt.KeyboardModifier.ShiftModifier and self._anchor is not None:
            self.gui.selection.add(self.model.ids_between(self._anchor, idx.row()))
        elif mods & Qt.KeyboardModifier.ControlModifier or in_box:
            self.gui.selection.toggle(mid)
            self._anchor = idx.row()
        else:
            self._anchor = idx.row()
            self.details.setVisible(True)
            self.details.show_message(mid)

    def apply(self) -> None:
        q = " ".join(x for x in (dict(KINDS)[self.kind.value()], self.search.text().strip(), dict(SORTS)[self.sort.currentData()]) if x)
        ok = self.model.set_query(q)
        n = self.model.total if ok else 0
        self.empty.setVisible(n == 0)
        self.view.setVisible(n > 0)
        self.status.setText(self.t("media.items_n", n=n) + "   ·   " + self.t("media.hint"))
        self.bulk.update_state()

    def open(self, **kw: Any) -> None:
        if kw.get("kind"):
            self.kind.set(kw["kind"])
            self.apply()

    def refresh(self) -> None:
        self.apply()

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("data.changed", "sync.finished"):
            self.mark_dirty()
