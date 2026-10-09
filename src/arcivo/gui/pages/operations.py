"""Export center, Job manager and Sync center pages."""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import ArcivoError
from ...core.paths import default_export_dir
from ...export.naming import PLACEHOLDERS
from ...export.writers import FORMATS
from ...jobs.manager import FINAL
from ...services.export import ExportSpec
from ..widgets.common import (
    Card,
    EmptyState,
    FlowLayout,
    KeyValueGrid,
    Segmented,
    StatCard,
    button,
    label,
    tool,
)
from .base import Page

MEDIA_TYPES = ["photo", "video", "audio", "voice", "document", "animation", "video_note", "sticker"]
STATUS_COLORS = {"queued": "#8A94A6", "running": "#4C8DFF", "paused": "#F5A524", "completed": "#2BB673", "partial": "#F5A524",
                 "failed": "#F2545B", "cancelled": "#8A94A6", "interrupted": "#F5A524", "cancelling": "#8A94A6"}
KIND_ICONS = {"sync": "refresh-cw", "export": "download", "delete": "trash-2"}


class ExportPage(Page):
    key = "export"

    def build(self) -> None:
        g, t = self.gui, self.t
        s = g.settings.export
        self.ids: list[int] = []
        cols = QHBoxLayout()
        cols.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)

        src = Card(t("export.source"), t("export.source_sub"))
        self.source = Segmented([("selection", t("export.src_selection")), ("query", t("export.src_query")), ("all", t("export.src_all"))],
                                "query")
        self.source.changed.connect(lambda _k: self._source_changed())
        src.add(self.source)
        self.query = QLineEdit()
        self.query.setPlaceholderText(t("export.query_placeholder"))
        self.query.textChanged.connect(lambda _x: self._timer.start())
        self.collection = QComboBox()
        self.collection.currentIndexChanged.connect(self._collection_picked)
        row = QHBoxLayout()
        row.addWidget(self.query, 2)
        row.addWidget(self.collection, 1)
        src.add(row)
        self.src_info = label("", "Muted", wrap=True)
        src.add(self.src_info)
        left.addWidget(src)

        fmt = Card(t("export.formats"), t("export.formats_sub"))
        fl = QWidget()
        flow = FlowLayout(fl)
        self.formats: dict[str, QCheckBox] = {}
        for f in FORMATS:
            cb = QCheckBox(t(f"export.fmt_{f}"))
            cb.setChecked(f == s.format)
            cb.toggled.connect(lambda _x: self._timer.start())
            flow.addWidget(cb)
            self.formats[f] = cb
        fmt.add(fl)
        self.inc_text = QCheckBox(t("export.include_text"))
        self.inc_text.setChecked(s.include_text)
        self.inc_meta = QCheckBox(t("export.include_metadata"))
        self.inc_meta.setChecked(s.include_metadata)
        fmt.add(self.inc_text)
        fmt.add(self.inc_meta)
        left.addWidget(fmt)

        media = Card(t("export.media"), t("export.media_sub"))
        self.download = QCheckBox(t("export.download_media"))
        self.download.setChecked(s.download_media)
        self.download.toggled.connect(lambda on: (self.media_box.setEnabled(on), self._timer.start()))
        media.add(self.download)
        self.media_box = QWidget()
        mf = FlowLayout(self.media_box)
        self.media_types: dict[str, QCheckBox] = {}
        for m in MEDIA_TYPES:
            cb = QCheckBox(t(f"types.{m}"))
            cb.setChecked(True)
            cb.toggled.connect(lambda _x: self._timer.start())
            mf.addWidget(cb)
            self.media_types[m] = cb
        self.media_box.setEnabled(s.download_media)
        media.add(self.media_box)
        left.addWidget(media)

        naming = Card(t("export.naming"), t("export.naming_sub"))
        form = QFormLayout()
        form.setSpacing(8)
        self.folder_t = QLineEdit(s.folder_template)
        self.file_t = QLineEdit(s.file_template)
        for w in (self.folder_t, self.file_t):
            w.setObjectName("Mono")
            w.textChanged.connect(lambda _x: self._timer.start())
        form.addRow(t("export.folder_template"), self.folder_t)
        form.addRow(t("export.file_template"), self.file_t)
        naming.add(form)
        ph = QWidget()
        pf = FlowLayout(ph)
        self._last_template = self.file_t
        self.folder_t.installEventFilter(self)
        self.file_t.installEventFilter(self)
        for p in PLACEHOLDERS:
            b = button("{" + p + "}", variant="ghost")
            b.setToolTip(t(f"export.ph_{p}"))
            b.clicked.connect(lambda _=False, p=p: self._insert(p))
            pf.addWidget(b)
        naming.add(ph)
        left.addWidget(naming)

        out = Card(t("export.output"))
        row = QHBoxLayout()
        self.out_dir = QLineEdit(g.settings.export_dir or str(default_export_dir()))
        row.addWidget(self.out_dir, 1)
        row.addWidget(button(t("common.browse"), g.icons.icon("folder-open", size=14), on_click=self._browse))
        out.add(row)
        self.name = QLineEdit(t("export.default_name"))
        out.add(self.name)
        self.skip = QCheckBox(t("export.skip_existing"))
        self.skip.setChecked(True)
        self.hash = QCheckBox(t("export.hash_files"))
        self.hash.setChecked(True)
        self.propose = QCheckBox(t("export.propose_delete"))
        self.propose.setIcon(g.icons.icon("triangle-alert", g.pal.warning, 14))
        out.add(self.skip)
        out.add(self.hash)
        out.add(self.propose)
        out.add(label(t("export.propose_delete_hint"), "Subtle", wrap=True))
        left.addWidget(out)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(14)
        self.preview = Card(t("export.preview"), t("export.preview_sub"))
        self.pv = KeyValueGrid()
        self.preview.add(self.pv)
        self.samples = label("", "Mono", wrap=True, selectable=True)
        self.preview.add(self.samples)
        self.err = label("", None, wrap=True)
        self.err.setObjectName("DangerBanner")
        self.err.setVisible(False)
        self.preview.add(self.err)
        self.start = button(t("export.start"), g.icons.icon("download", "#FFFFFF", 16), "primary", on_click=self._start)
        self.start.setMinimumHeight(40)
        self.preview.add(self.start)
        right.addWidget(self.preview)
        self.recent = Card(t("export.recent"))
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("PlainList")
        self.recent_list.setMinimumHeight(260)
        self.recent_list.itemActivated.connect(lambda it: g.open_path(it.data(Qt.ItemDataRole.UserRole)))
        self.recent_list.itemDoubleClicked.connect(lambda it: g.open_path(it.data(Qt.ItemDataRole.UserRole)))
        self.recent.add(self.recent_list)
        right.addWidget(self.recent)
        right.addStretch(1)
        cols.addLayout(right, 2)
        self.root.addLayout(cols)
        self._timer = QTimer(self, singleShot=True, interval=300)
        self._timer.timeout.connect(self._update_preview)

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[no-untyped-def]
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.Type.FocusIn and obj in (self.folder_t, self.file_t):
            self._last_template = obj
        return super().eventFilter(obj, ev)

    def _insert(self, p: str) -> None:
        self._last_template.insert("{" + p + "}")
        self._last_template.setFocus()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.t("export.output"), self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def _collection_picked(self, i: int) -> None:
        q = self.collection.itemData(i)
        if q:
            self.source.set("query")
            self.query.setText(q)

    def _source_changed(self) -> None:
        self.query.setEnabled(self.source.value() == "query")
        self.collection.setEnabled(self.source.value() == "query")
        self._timer.start()

    def open(self, **kw: Any) -> None:
        if kw.get("ids"):
            self.ids = list(kw["ids"])
            self.source.set("selection")
        elif kw.get("query"):
            self.source.set("query")
            self.query.setText(kw["query"])
        self._source_changed()

    def refresh(self) -> None:
        g = self.gui
        self.collection.blockSignals(True)
        self.collection.clear()
        self.collection.addItem(self.t("export.pick_collection"), None)
        for c in g.ctx.org.list_collections(g.account_id, with_counts=False):
            self.collection.addItem(g.icons.icon(c.icon, c.color, 14), c.name, c.query)
        self.collection.blockSignals(False)
        self.recent_list.clear()
        for r in g.ctx.reports.list(20):
            if r["kind"] != "export":
                continue
            it = QListWidgetItem(g.icons.icon("folder-open", size=16), f"{self.t.date(r['created_at'], with_time=True)}\n{r['html_path']}")
            it.setData(Qt.ItemDataRole.UserRole, r["html_path"])
            self.recent_list.addItem(it)
        if not self.recent_list.count():
            self.recent_list.addItem(self.t("export.no_recent"))
        self._source_changed()

    def spec(self) -> ExportSpec:
        src = self.source.value()
        ids = (self.ids or self.gui.selection.sorted()) if src == "selection" else None
        if src == "selection" and self.gui.selection.ids:
            ids = self.gui.selection.sorted()
        return ExportSpec(
            output_dir=self.out_dir.text().strip(), query=self.query.text().strip() if src == "query" else "", ids=ids,
            name=self.name.text().strip() or "Arcivo Export", formats=[f for f, cb in self.formats.items() if cb.isChecked()],
            include_text=self.inc_text.isChecked(), include_metadata=self.inc_meta.isChecked(), download_media=self.download.isChecked(),
            media_types=[m for m, cb in self.media_types.items() if cb.isChecked()] or None,
            folder_template=self.folder_t.text().strip(), file_template=self.file_t.text().strip(), skip_existing=self.skip.isChecked(),
            hash_files=self.hash.isChecked(), propose_delete=self.propose.isChecked(), language=self.t.lang)

    def _update_preview(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        self.pv.clear()
        self.err.setVisible(False)
        self.start.setEnabled(False)
        if not aid:
            return
        spec = self.spec()
        if self.source.value() == "selection" and not spec.ids:
            self.src_info.setText(t("export.no_selection"))
            return
        try:
            spec.validate()
            if spec.query:
                err = g.ctx.search.validate(spec.query)
                if err:
                    raise ArcivoError(t("search.invalid", error=err))
            pv = g.ctx.exporter.preview(aid, spec)
        except Exception as exc:
            self.err.setText(g.error_text(exc))
            self.err.setVisible(True)
            return
        self.src_info.setText(t("export.src_info", n=pv["messages"]))
        self.pv.add(t("export.pv_messages"), t.num(pv["messages"]))
        self.pv.add(t("export.pv_files"), t.num(pv["files"]) if spec.download_media else t("export.pv_no_media"))
        self.pv.add(t("export.pv_size"), t.size(pv["estimated_bytes"]) if spec.download_media else "—")
        self.pv.add(t("export.pv_formats"), ", ".join(f.upper() for f in spec.formats) or "—")
        self.samples.setText("\n".join(pv["sample_paths"]) if spec.download_media and pv["sample_paths"] else "")
        self.start.setEnabled(pv["messages"] > 0)

    def _start(self) -> None:
        g = self.gui
        spec = self.spec()
        try:
            spec.validate()
        except Exception as exc:
            g.show_error(exc)
            return
        params = spec.to_params()
        params["account_id"] = g.account_id
        if g.submit_job("export", self.t("export.job_title", name=spec.name), params):
            g.navigate("jobs")


class JobRow(Card):
    def __init__(self, gui, job: dict) -> None:  # type: ignore[no-untyped-def]
        super().__init__(padding=14)
        self.gui = gui
        self.job_id = job["id"]
        g, t = gui, gui.t
        top = QHBoxLayout()
        from ..widgets.common import IconBadge
        self.badge = IconBadge(g.icons.pixmap(KIND_ICONS.get(job["kind"], "list-checks"), g.pal.accent, 18), g.pal.accent, 36)
        top.addWidget(self.badge)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = label(job["title"], "CardTitle")
        self.meta = label("", "Subtle")
        col.addWidget(self.title)
        col.addWidget(self.meta)
        top.addLayout(col, 1)
        self.status = label("", "Pill")
        top.addWidget(self.status)
        self.btns: dict[str, Any] = {}
        for key, icon, tip in (("pause", "pause", t("jobs.pause")), ("resume", "play", t("jobs.resume")), ("cancel", "x", t("jobs.cancel")),
                               ("retry", "rotate-ccw", t("jobs.retry")), ("report", "file-text", t("jobs.report")),
                               ("folder", "folder-open", t("jobs.open_folder"))):
            b = tool(g.icons.icon(icon), tip, lambda k=key: self._act(k))
            top.addWidget(b)
            self.btns[key] = b
        self.add(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.add(self.bar)
        self.detail = label("", "Muted", wrap=True)
        self.add(self.detail)
        self.job = job
        self.update_job(job)

    def update_job(self, job: dict) -> None:
        t = self.gui.t
        self.job = job
        st = job["status"]
        p = job["progress"]
        color = STATUS_COLORS.get(st, "#8A94A6")
        self.status.setText(t(f"jobs.status_{st}"))
        self.status.setStyleSheet(f"color: {color}; border-color: {color};")
        self.bar.setValue(1000 if st == "completed" else int(1000 * (p.get("fraction") or 0)))
        started = job.get("started_at") or job.get("created_at")
        kind_label = t(f"jobs.kind_{job['kind']}")
        self.meta.setText(f"{kind_label} · {t.date(job['created_at'], with_time=True)}"
                          + (f" · {t.duration((job.get('finished_at') or time.time()) - started)}" if started else ""))
        parts = []
        if p.get("total"):
            parts.append(t("jobs.items", done=p.get("done", 0), total=p["total"]))
        if p.get("failed"):
            parts.append(t("jobs.failed_n", n=p["failed"]))
        if p.get("skipped"):
            parts.append(t("jobs.skipped_n", n=p["skipped"]))
        if p.get("bytes_total"):
            parts.append(f"{t.size(p.get('bytes_done', 0))} / {t.size(p['bytes_total'])}")
        if st == "running":
            if p.get("speed_bps"):
                parts.append(t("jobs.speed", speed=t.size(p["speed_bps"])))
            if p.get("eta_s"):
                parts.append(t("jobs.eta", eta=t.duration(p["eta_s"])))
            if p.get("phase"):
                parts.append(t("jobs.phase", phase=t(f"jobs.phase_{p['phase']}") if t.has(f"jobs.phase_{p['phase']}") else p["phase"]))
            if p.get("current"):
                parts.append(str(p["current"])[:60])
        if job.get("error"):
            parts.append(t("jobs.error", error=job["error"][:200]))
        res = job.get("result") or {}
        if job["kind"] == "sync" and st in ("completed", "partial"):
            parts.append(t("jobs.sync_result", fetched=res.get("fetched", 0), deleted=res.get("deleted", 0)))
        if job["kind"] == "delete" and res.get("deleted") is not None:
            parts.append(t("jobs.deleted_n", n=res["deleted"]))
        self.detail.setText("  ·  ".join(parts) or t("jobs.waiting"))
        final = st in {s.value for s in FINAL}
        self.btns["pause"].setVisible(st == "running")
        self.btns["resume"].setVisible(st == "paused")
        self.btns["cancel"].setVisible(not final)
        self.btns["retry"].setVisible(st in ("failed", "partial", "cancelled", "interrupted"))
        self.btns["report"].setVisible(bool(res.get("report_html")))
        self.btns["folder"].setVisible(bool(res.get("output_dir")))

    def _act(self, key: str) -> None:
        g = self.gui
        jid = self.job_id
        res = self.job.get("result") or {}
        try:
            if key == "pause":
                g.jobs(lambda m: m.pause(jid))
            elif key == "resume":
                g.jobs(lambda m: m.resume(jid))
            elif key == "cancel":
                g.jobs(lambda m: m.cancel(jid))
            elif key == "retry":
                g.jobs(lambda m: m.retry(jid))
            elif key == "report":
                g.open_path(res["report_html"])
            elif key == "folder":
                g.open_path(res["output_dir"])
        except Exception as exc:
            g.show_error(exc)


class JobsPage(Page):
    key = "jobs"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("jobs.clear_finished"), g.icons.icon("trash-2", size=15), on_click=self._clear))
        self.summary = label("", "Muted")
        self.root.addWidget(self.summary)
        self.list = QVBoxLayout()
        self.list.setSpacing(10)
        self.root.addLayout(self.list)
        self.empty = EmptyState(g.icons.pixmap("list-checks", g.pal.text_subtle, 40), t("jobs.empty"), t("jobs.empty_text"))
        self.root.addWidget(self.empty)
        self.root.addStretch(1)
        self.rows: dict[str, JobRow] = {}

    def refresh(self) -> None:
        jobs = self.gui.jobs(lambda m: [j.to_dict() for j in m.list()])
        for jid in list(self.rows):
            if jid not in {j["id"] for j in jobs}:
                row = self.rows.pop(jid)
                row.hide()
                row.deleteLater()
        for i, j in enumerate(jobs[:60]):
            row = self.rows.get(j["id"])
            if row is None:
                row = JobRow(self.gui, j)
                self.rows[j["id"]] = row
            else:
                row.update_job(j)
            self.list.insertWidget(i, row)
        self.empty.setVisible(not jobs)
        active = sum(1 for j in jobs if j["status"] in ("running", "queued", "paused"))
        self.summary.setText(self.t("jobs.summary", active=active, total=len(jobs)))

    def on_event(self, topic: str, payload: dict) -> None:
        if topic == "job.updated":
            j = payload.get("job") or {}
            row = self.rows.get(j.get("id"))
            if row is not None:
                row.update_job(j)
            else:
                self.mark_dirty()
        elif topic == "job.finished":
            self.mark_dirty()

    def _clear(self) -> None:
        n = self.gui.jobs(lambda m: m.clear_finished())
        self.gui.notify(self.t("jobs.cleared", n=n), "", "success")
        self.mark_dirty()


class SyncPage(Page):
    key = "sync"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("sync.now"), g.icons.icon("refresh-cw", "#FFFFFF", 15), "primary", on_click=lambda: g.sync("incremental")))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards: dict[str, StatCard] = {}
        for i, (k, icon, color) in enumerate((("messages", "database", "#7C83FD"), ("last", "clock", "#36C2B4"),
                                               ("initial", "circle-check", "#2BB673"), ("reconcile", "shield-check", "#F5A524"))):
            c = StatCard(g.icons.pixmap(icon, color, 18), color, t(f"sync.card_{k}"), "—", clickable=False)
            grid.addWidget(c, 0, i)
            self.cards[k] = c
        self.root.addLayout(grid)
        live = Card(t("sync.live"), t("sync.live_sub"))
        self.live_text = label(t("sync.idle"), None, wrap=True)
        self.live_bar = QProgressBar()
        self.live_bar.setRange(0, 0)
        self.live_bar.setFixedHeight(6)
        self.live_bar.setTextVisible(False)
        self.live_bar.setVisible(False)
        live.add(self.live_text)
        live.add(self.live_bar)
        self.root.addWidget(live)
        modes = Card(t("sync.modes"), t("sync.modes_sub"))
        for mode, icon in (("incremental", "refresh-cw"), ("initial", "play"), ("full", "shield-check")):
            row = QHBoxLayout()
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(t(f"sync.mode_{mode}"), "CardTitle"))
            col.addWidget(label(t(f"sync.mode_{mode}_text"), "Muted", wrap=True))
            row.addLayout(col, 1)
            row.addWidget(button(t("sync.run"), g.icons.icon(icon, size=14), on_click=lambda m=mode: g.sync(m)))
            modes.add(row)
        self.root.addWidget(modes)
        opts = Card(t("sync.settings"), t("sync.settings_sub"))
        form = QFormLayout()
        s = g.settings.sync
        self.auto_start = QCheckBox(t("settings.auto_sync_on_start"))
        self.auto_start.setChecked(s.auto_sync_on_start)
        self.auto_start.toggled.connect(lambda v: self._set("auto_sync_on_start", v))
        self.interval = QComboBox()
        for m in (0, 15, 30, 60, 180, 720):
            self.interval.addItem(t("sync.interval_off") if m == 0 else t("sync.interval_min", n=m), m)
        self.interval.setCurrentIndex(max(0, self.interval.findData(s.auto_sync_interval_min)))
        self.interval.currentIndexChanged.connect(lambda _i: self._set("auto_sync_interval_min", self.interval.currentData()))
        self.keep_deleted = QCheckBox(t("settings.keep_remote_deleted"))
        self.keep_deleted.setChecked(s.keep_remote_deleted)
        self.keep_deleted.toggled.connect(lambda v: self._set("keep_remote_deleted", v))
        form.addRow("", self.auto_start)
        form.addRow(t("sync.interval"), self.interval)
        form.addRow("", self.keep_deleted)
        opts.add(form)
        opts.add(label(t("sync.rate_note"), "Subtle", wrap=True))
        self.root.addWidget(opts)
        hist = Card(t("sync.history"))
        self.hist = QListWidget()
        self.hist.setObjectName("PlainList")
        self.hist.setMinimumHeight(220)
        hist.add(self.hist)
        self.root.addWidget(hist)
        self.root.addStretch(1)

    def _set(self, key: str, value: Any) -> None:
        setattr(self.gui.settings.sync, key, value)
        self.gui.save_settings()
        if key == "auto_sync_interval_min" and self.gui.window is not None:
            self.gui.window.schedule_auto_sync()

    def refresh(self) -> None:
        g, t = self.gui, self.t
        aid = g.account_id
        if aid:
            st = g.ctx.sync_state.get(aid)
            self.cards["messages"].value.setText(t.num(g.ctx.messages.total(aid)))
            last = max(st.get("last_incremental") or 0, st.get("last_full_sync") or 0) or None
            self.cards["last"].value.setText(t.relative(last))
            self.cards["initial"].value.setText(t("common.yes") if st.get("initial_complete") else t("sync.in_progress"))
            self.cards["initial"].sub.setText(t("sync.checkpoint", id=st.get("checkpoint_id") or 0) if not st.get("initial_complete") else "")
            self.cards["reconcile"].value.setText(t.relative(st.get("last_reconcile")))
        self.hist.clear()
        for j in g.jobs(lambda m: [x.to_dict() for x in m.list() if x.kind == "sync"])[:30]:
            r = j.get("result") or {}
            status = t(f"jobs.status_{j['status']}")
            result = t("jobs.sync_result", fetched=r.get("fetched", 0), deleted=r.get("deleted", 0))
            it = QListWidgetItem(g.icons.icon("refresh-cw", STATUS_COLORS.get(j["status"]), 15),
                                 f"{t.date(j['created_at'], with_time=True)} · {status} · {result}")
            self.hist.addItem(it)

    def on_event(self, topic: str, payload: dict) -> None:
        t = self.t
        if topic == "sync.progress":
            self.live_bar.setVisible(True)
            self.live_text.setText(t("sync.progress", n=payload.get("fetched", 0), mode=t(f"sync.mode_{payload.get('mode', 'incremental')}")))
        elif topic == "sync.finished":
            self.live_bar.setVisible(False)
            self.live_text.setText(t("sync.finished_text", fetched=payload.get("fetched", 0), deleted=payload.get("deleted", 0)))
            self.mark_dirty()
        elif topic == "job.finished":
            self.mark_dirty()
