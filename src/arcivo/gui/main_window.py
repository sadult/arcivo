"""Main window: macOS-style source-list sidebar, lazily-built pages and shortcuts."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core.paths import resource_path
from .facade import Gui
from .native import app_icon
from .pages.base import Page
from .widgets.common import label, tool
from .widgets.dialogs import CommandPalette
from .widgets.toast import ToastManager

log = logging.getLogger(__name__)

NAV = [
    ("library", [("dashboard", "layout-dashboard"), ("explorer", "messages-square"), ("search", "search"), ("media", "images"),
                 ("collections", "sparkles"), ("tags", "tags")]),
    ("insights", [("statistics", "chart-column"), ("storage", "hard-drive")]),
    ("operations", [("export", "download"), ("jobs", "list-checks"), ("sync", "refresh-cw")]),
    ("system", [("account", "user"), ("settings", "settings"), ("logs", "scroll-text"), ("about", "info")]),
]


def page_class(key: str) -> type[Page]:
    from .pages import dashboard, explorer, insights, media, operations, system
    return {
        "dashboard": dashboard.DashboardPage, "explorer": explorer.ExplorerPage, "search": explorer.SearchPage,
        "media": media.MediaPage, "collections": explorer.CollectionsPage, "tags": explorer.TagsPage,
        "statistics": insights.StatisticsPage, "storage": insights.StoragePage, "export": operations.ExportPage,
        "jobs": operations.JobsPage, "sync": operations.SyncPage, "account": system.AccountPage,
        "settings": system.SettingsPage, "logs": system.LogsPage, "about": system.AboutPage,
    }[key]


class Avatar(QLabel):
    """Round monogram avatar (accent fill, white initials)."""

    def __init__(self, color: str, size: int = 26) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self._color = color
        self._text = ""

    def set_name(self, name: str) -> None:
        parts = [w for w in name.replace("@", "").split() if w]
        self._text = "".join(w[0] for w in parts[:2]).upper() or "?"
        self.update()

    def paintEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(self.rect())
        p.setPen(QColor("#FFFFFF"))
        f = QFont(self.font())
        f.setPixelSize(max(9, int(self.height() * 0.4)))
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class MainWindow(QMainWindow):
    SIDEBAR_W = 224

    def __init__(self, gui: Gui) -> None:
        super().__init__()
        self.gui = gui
        gui.window = self
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = self._build_sidebar()
        lay.addWidget(self.sidebar)
        content = QWidget()
        content.setObjectName("Content")
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.stack = QStackedWidget()
        col.addWidget(self.stack, 1)
        lay.addWidget(content, 1)
        self.pages: dict[str, Page] = {}
        self.current = ""
        gui.toasts = ToastManager(root, gui.icons, gui.pal)
        gui.navigateRequested.connect(self.navigate)
        gui.runtime.event.connect(self._on_event)
        self._shortcuts: list[QShortcut] = []
        self.apply_shortcuts()
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(lambda: gui.sync("auto"))
        self.schedule_auto_sync()
        self.status_timer = QTimer(self, interval=30000)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start()
        self.navigate("dashboard", {})
        self._update_status()

    # ------------------------------------------------------------------ building
    def _build_sidebar(self) -> QFrame:
        g, t = self.gui, self.gui.t
        sb = QFrame()
        sb.setObjectName("Sidebar")
        sb.setFixedWidth(self.SIDEBAR_W)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(1)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 4, 6)
        brand.setSpacing(8)
        logo = QLabel()
        px = QPixmap(str(resource_path("assets", "brand", "arcivo-mark-64.png")))
        if px.isNull():
            px = g.icons.pixmap("archive", g.pal.accent, 22)
        else:
            px = px.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            px.setDevicePixelRatio(2)
        logo.setPixmap(px)
        brand.addWidget(logo)
        self.brand_text = label(APP_NAME, "BrandName")
        brand.addWidget(self.brand_text)
        self.demo_badge = label(t("status.demo_short"), "DemoBadge")
        self.demo_badge.setToolTip(t("status.demo"))
        self.demo_badge.setVisible(g.demo)
        brand.addWidget(self.demo_badge)
        brand.addStretch(1)
        lay.addLayout(brand)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_sections: list[QLabel] = []
        for section, items in NAV:
            sl = label(t(f"nav.section_{section}"), "NavSection")
            self.nav_sections.append(sl)
            lay.addWidget(sl)
            for key, icon in items:
                b = QPushButton(t(f"nav.{key}"))
                b.setObjectName("NavButton")
                b.setCheckable(True)
                b.setIcon(g.icons.icon(icon, g.pal.accent, 16))
                b.setIconSize(QSize(16, 16))
                b.setToolTip(t(f"nav.{key}"))
                b.clicked.connect(lambda _=False, k=key: self.navigate(k, {}))
                lay.addWidget(b)
                self.nav_buttons[key] = b
        lay.addStretch(1)
        self.jobs_pill = QPushButton()
        self.jobs_pill.setObjectName("JobsIndicator")
        self.jobs_pill.setIcon(g.icons.icon("loader", g.pal.accent, 14))
        self.jobs_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.jobs_pill.clicked.connect(lambda: self.navigate("jobs", {}))
        self.jobs_pill.setVisible(False)
        lay.addWidget(self.jobs_pill)
        lay.addSpacing(6)
        foot = QFrame()
        foot.setObjectName("SidebarFooter")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(6, 10, 0, 0)
        fl.setSpacing(8)
        self.avatar = Avatar(g.pal.accent)
        self.avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar.mousePressEvent = lambda _e: self.navigate("account", {})  # type: ignore[method-assign]
        fl.addWidget(self.avatar)
        self.footer_text = QWidget()
        ft = QVBoxLayout(self.footer_text)
        ft.setContentsMargins(0, 0, 0, 0)
        ft.setSpacing(0)
        self.account_label = label("", "AccountName")
        self.sync_pill = label("", "SyncStatus")
        ft.addWidget(self.account_label)
        ft.addWidget(self.sync_pill)
        fl.addWidget(self.footer_text, 1)
        self.sync_btn = tool(g.icons.icon("refresh-cw", g.pal.text_muted, 16), t("dashboard.sync_now"), lambda: g.sync("incremental"))
        fl.addWidget(self.sync_btn)
        lay.addWidget(foot)
        return sb

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, kw: dict | None = None) -> None:
        kw = kw or {}
        if key not in self.pages:
            try:
                page = page_class(key)(self.gui)
            except Exception as exc:
                log.exception("Failed to build page %s", key)
                self.gui.show_error(exc)
                return
            self.pages[key] = page
            self.stack.addWidget(page)
        page = self.pages[key]
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        self.stack.setCurrentWidget(page)
        self.current = key
        if kw:
            try:
                page.open(**kw)
            except Exception as exc:
                self.gui.show_error(exc)
        page.ensure_fresh()

    def palette(self) -> None:
        t = self.gui.t
        cmds = []
        for _section, items in NAV:
            for key, icon in items:
                cmds.append((icon, t(f"nav.{key}"), t("palette.go_to"), lambda k=key: self.navigate(k, {})))
        g = self.gui
        cmds += [
            ("refresh-cw", t("palette.sync_now"), t("palette.action"), lambda: g.sync("incremental")),
            ("shield-check", t("palette.full_reconcile"), t("palette.action"), lambda: g.sync("full")),
            ("download", t("palette.export_selection"), t("palette.action"), lambda: g.actions.export(g.selection.sorted())),
            ("copy", t("palette.find_duplicates"), t("palette.action"), lambda: self.navigate("storage", {"tab": "duplicates"})),
            ("sun", t("topbar.toggle_theme"), t("palette.action"), self.toggle_theme),
            ("settings", t("nav.settings"), t("palette.go_to"), lambda: self.navigate("settings", {})),
            ("circle-help", t("search.syntax"), t("palette.help"), lambda: self.navigate("search", {"help": True})),
        ]
        for c in g.ctx.org.list_collections(g.account_id, with_counts=False):
            cmds.append((c.icon, c.name, t("palette.collection"), lambda cid=c.id: self.navigate("collections", {"collection_id": cid})))
        dlg = CommandPalette(self, g, cmds)
        geo = self.geometry()
        dlg.move(geo.x() + (geo.width() - dlg.width()) // 2, geo.y() + 90)
        dlg.exec()

    # ------------------------------------------------------------------ shortcuts
    def apply_shortcuts(self) -> None:
        for s in self._shortcuts:
            s.setEnabled(False)
            s.deleteLater()
        self._shortcuts = []
        g = self.gui

        def cur_ids() -> list[int]:
            return g.selection.sorted()

        actions = {
            "focus_search": self.focus_search,
            "command_palette": self.palette,
            "refresh": lambda: self.pages[self.current].mark_dirty() if self.current in self.pages else None,
            "sync": lambda: g.sync("incremental"),
            "clear_selection": g.selection.clear,
            "bulk_delete": lambda: g.actions.delete(cur_ids()) if cur_ids() else None,
            "export": lambda: g.actions.export(cur_ids()) if cur_ids() else self.navigate("export", {}),
            "tag": lambda: g.actions.tag(cur_ids()),
            "flag": lambda: g.actions.flag(cur_ids()),
            "toggle_sidebar": self.toggle_sidebar,
            "toggle_theme": self.toggle_theme,
            "toggle_details": self._toggle_details,
            "settings": lambda: self.navigate("settings", {}),
            "search_help": lambda: self.navigate("search", {"help": True}),
            "select_all": self._select_all,
        }
        for key in ("dashboard", "explorer", "search", "media", "statistics", "storage", "export", "jobs", "collections"):
            actions[f"nav_{key}"] = lambda k=key: self.navigate(k, {})
        for action, seq in g.settings.shortcuts.items():
            fn = actions.get(action)
            if fn is None or not seq:
                continue
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

    def _select_all(self) -> None:
        page = self.pages.get(self.current)
        browser = getattr(page, "browser", None)
        if browser is not None:
            self.gui.selection.add(browser.table.model.all_ids())
        elif getattr(page, "model", None) is not None:
            self.gui.selection.add(page.model.all_ids())  # type: ignore[union-attr]

    def _toggle_details(self) -> None:
        browser = getattr(self.pages.get(self.current), "browser", None)
        if browser is not None:
            browser.details_btn.toggle()

    # ------------------------------------------------------------------ appearance
    def focus_search(self) -> None:
        page = self.pages.get(self.current)
        box = getattr(getattr(page, "browser", None), "search", None) or getattr(page, "search", None)
        if box is None:
            self.navigate("search", {})
            page = self.pages.get("search")
            box = getattr(getattr(page, "browser", None), "search", None)
        if box is not None:
            box.setFocus()
            box.selectAll()

    def toggle_sidebar(self) -> None:
        collapsed = self.sidebar.width() > 100
        self.sidebar.setFixedWidth(60 if collapsed else self.SIDEBAR_W)
        self.brand_text.setVisible(not collapsed)
        self.demo_badge.setVisible(not collapsed and self.gui.demo)
        self.footer_text.setVisible(not collapsed)
        self.sync_btn.setVisible(not collapsed)
        self.jobs_pill.setVisible(False if collapsed else self.jobs_pill.isVisible())
        for s in self.nav_sections:
            s.setVisible(not collapsed)
        for k, b in self.nav_buttons.items():
            b.setText("" if collapsed else self.gui.t(f"nav.{k}"))

    def toggle_theme(self) -> None:
        a = self.gui.settings.appearance
        a.theme = "light" if self.gui.pal.name == "dark" else "dark"
        self.gui.save_settings()
        QTimer.singleShot(0, self.gui.controller.rebuild)

    def schedule_auto_sync(self) -> None:
        m = self.gui.settings.sync.auto_sync_interval_min
        self.auto_timer.stop()
        if m and m > 0:
            self.auto_timer.start(int(m * 60_000))

    # ------------------------------------------------------------------ events & status
    def _on_event(self, topic: str, payload: dict) -> None:
        g, t = self.gui, self.gui.t
        if topic == "sync.finished":
            g.reload_account()
            if g.settings.notifications.sync_finished:
                g.notify(t("sync.finished_title"), t("sync.finished_text", fetched=payload.get("fetched", 0), deleted=payload.get("deleted", 0)),
                         "success")
        elif topic == "sync.progress":
            self.sync_pill.setText(t("topbar.syncing", n=payload.get("fetched", 0)))
            self.sync_btn.setEnabled(False)
        elif topic == "job.finished":
            self._job_finished(payload.get("job") or {})
        elif topic == "data.changed":
            if payload.get("reason") in ("sync", "reset", "delete"):
                g.reload_account()
        for page in self.pages.values():
            try:
                page.on_event(topic, payload)
            except Exception:
                log.exception("Page %s failed handling %s", page.key, topic)
        if topic in ("sync.finished", "job.finished", "job.updated", "data.changed"):
            self._update_status()

    def _job_finished(self, job: dict) -> None:
        g, t = self.gui, self.gui.t
        st = job.get("status")
        if job.get("kind") == "sync" and st == "completed":
            return  # sync.finished already notified
        kind = "success" if st == "completed" else "warning" if st in ("partial", "cancelled", "interrupted") else "error"
        res = job.get("result") or {}
        if g.settings.notifications.job_finished or kind == "error":
            action = (t("jobs.report"), lambda: g.open_path(res["report_html"])) if res.get("report_html") else (
                t("jobs.view"), lambda: self.navigate("jobs", {}))
            g.notify(t(f"jobs.finished_{kind}", title=job.get("title", "")), job.get("error") or "", kind, action)
        if job.get("kind") == "export" and st == "completed" and res.get("delete_candidates"):
            ids = list(res["delete_candidates"])
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(t("export.post_delete_title"))
            box.setText(t("export.post_delete_text", n=len(ids)))
            box.setInformativeText(t("export.post_delete_info"))
            review = box.addButton(t("export.post_delete_review"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(t("export.post_delete_keep"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is review:
                g.actions.delete(ids, "post-export", t("export.post_delete_context", folder=res.get("output_dir", "")), job.get("id"))

    def _update_status(self) -> None:
        g, t = self.gui, self.gui.t
        aid = g.account_id
        acc = g.ctx.accounts.first()
        name = (acc["display_name"] if acc else "") or t("account.not_signed_in")
        self.account_label.setText(name)
        self.avatar.set_name(name if acc else "")
        try:
            active = g.jobs(lambda m: [j.to_dict() for j in m.active()])
        except Exception:
            active = []
        syncing = [j for j in active if j["kind"] == "sync"]
        others = [j for j in active if j["kind"] != "sync"]
        self.sync_btn.setEnabled(not syncing)
        if syncing:
            self.sync_pill.setText(t("topbar.syncing", n=syncing[0]["progress"].get("done", 0)))
        elif not (g.demo or g.ctx.auth.has_session()):
            self.sync_pill.setText(t("status.offline"))
        elif aid:
            st = g.ctx.sync_state.get(aid)
            last = max(st.get("last_incremental") or 0, st.get("last_full_sync") or 0) or None
            self.sync_pill.setText(t("topbar.synced", when=t.relative(last)))
        else:
            self.sync_pill.setText(t("topbar.not_synced"))
        self.jobs_pill.setVisible(bool(others) and self.sidebar.width() > 100)
        if others:
            self.jobs_pill.setText(t("topbar.jobs_running", n=len(others)))

    # ------------------------------------------------------------------ Qt events
    def resizeEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(e)
        if self.gui.toasts is not None:
            self.gui.toasts.reposition()

    def closeEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if not self.gui.controller.rebuilding:
            active = self.gui.jobs(lambda m: [j for j in m.active() if j.kind != "sync"])
            if active and QMessageBox.question(self, APP_NAME, self.gui.t("app.quit_with_jobs", n=len(active))) != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        super().closeEvent(e)

    def page(self, key: str) -> Page:
        self.navigate(key, {})
        return self.pages[key]

    def open_kw(self, key: str, **kw: Any) -> None:
        self.navigate(key, kw)
