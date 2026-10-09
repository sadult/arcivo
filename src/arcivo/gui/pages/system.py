"""Account, Settings, Logs and About pages."""

from __future__ import annotations

import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QSize, Qt, QTimer, qVersion
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME, APP_TAGLINE, AUTHOR, BUILD, REPO_URL, TELEGRAM_HANDLE, TELEGRAM_URL, __version__
from ...core.config import DEFAULT_SHORTCUTS
from ...core.logging_setup import recent_lines
from ...core.paths import resource_path
from ...db.migrator import current_version
from ..widgets.common import Card, KeyValueGrid, button, hbox, label
from .base import Page


# ============================================================================ account
def _describe_op(t, op: dict) -> str:  # type: ignore[no-untyped-def]
    """Human-readable line for an audit-log entry (falls back to the raw action name)."""
    import json

    try:
        d = json.loads(op.get("details") or "{}") or {}
    except ValueError:
        d = {}
    action = str(op.get("action") or "")
    key = "account.op_" + action.replace(".", "_")
    if action == "sync":
        mode = t(f"sync.mode_{d.get('mode', 'incremental')}")
        return t(key, mode=mode, fetched=d.get("fetched", 0), deleted=d.get("deleted", 0))
    if action in ("delete.start", "delete.finish", "reset_index"):
        return t(key, count=d.get("count", 0), deleted=d.get("deleted", 0), failed=d.get("failed", 0))
    return action


class AccountPage(Page):
    key = "account"

    def build(self) -> None:
        g, t = self.gui, self.t
        self.actions.addWidget(button(t("common.refresh"), g.icons.icon("rotate-ccw", size=15), on_click=self.mark_dirty))
        self.login_btn = button(t("account.sign_in"), g.icons.icon("lock", "#FFFFFF", 15), "primary", on_click=lambda: g.controller.login())
        self.actions.addWidget(self.login_btn)
        self.logout_btn = button(t("account.log_out"), g.icons.icon("log-out", size=15), on_click=self._logout)
        self.actions.addWidget(self.logout_btn)
        self.profile = Card(padding=20)
        self.profile.setObjectName("Hero")
        row = QHBoxLayout()
        self.avatar = QLabel()
        self.avatar.setFixedSize(64, 64)
        row.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = label("…", "SectionTitle")
        self.handle = label("", "Muted")
        self.badges = label("", "Subtle")
        col.addWidget(self.name)
        col.addWidget(self.handle)
        col.addWidget(self.badges)
        row.addLayout(col, 1)
        self.profile.add(row)
        self.root.addWidget(self.profile)
        grid = QHBoxLayout()
        grid.setSpacing(12)
        self.conn = KeyValueGrid()
        c = Card(t("account.connection"), t("account.connection_sub"))
        c.add(self.conn)
        c.add(QWidget(), 1)
        grid.addWidget(c)
        self.sec = KeyValueGrid()
        c = Card(t("account.security"), t("account.security_sub"))
        c.add(self.sec)
        c.add(QWidget(), 1)
        grid.addWidget(c)
        self.local = KeyValueGrid()
        c = Card(t("account.local"), t("account.local_sub"))
        c.add(self.local)
        c.add(QWidget(), 1)
        grid.addWidget(c)
        self.root.addLayout(grid)
        ops = Card(t("account.operations"), t("account.operations_sub"))
        self.ops = QListWidget()
        self.ops.setObjectName("PlainList")
        self.ops.setMinimumHeight(220)
        ops.add(self.ops)
        self.root.addWidget(ops)
        notice = Card(t("account.api_notice_title"))
        notice.add(label(t("account.api_notice"), "Muted", wrap=True))
        self.root.addWidget(notice)
        self.root.addStretch(1)

    def refresh(self) -> None:
        from ...services.account import account_overview
        self.gui.run(account_overview(self.gui.ctx), self._show)

    def _avatar(self, name: str) -> QPixmap:
        from PySide6.QtGui import QColor, QFont, QPainter
        px = QPixmap(128, 128)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self.gui.pal.accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 128, 128)
        p.setPen(QColor("#FFFFFF"))
        f = QFont(self.font())
        f.setPixelSize(52)
        f.setBold(True)
        p.setFont(f)
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        p.end()
        px.setDevicePixelRatio(2)
        return px

    def _show(self, info: dict[str, Any]) -> None:
        t = self.t
        user = info.get("user") or {}
        authorized = bool(info.get("authorized"))
        self.login_btn.setVisible(not authorized and not self.gui.demo)
        self.logout_btn.setVisible(authorized)
        self.name.setText(user.get("name") or t("account.not_signed_in"))
        self.handle.setText(" · ".join(x for x in ((f"@{user['username']}" if user.get("username") else ""), user.get("phone") or "") if x))
        badges = [t("account.premium") if user.get("premium") else "", (t("account.lang", lang=user["lang"]) if user.get("lang") else ""),
                  t("account.demo") if self.gui.demo else ""]
        self.badges.setText(" · ".join(b for b in badges if b))
        self.avatar.setPixmap(self._avatar(user.get("name") or "?"))
        self.conn.clear()
        c = info.get("connection") or {}
        self.conn.add(t("account.status"), t("account.connected") if c.get("connected") else t("account.disconnected"))
        if c:
            self.conn.add(t("account.dc"), str(c.get("dc_id") or "—"))
            self.conn.add(t("account.server"), f"{c.get('server') or '—'}:{c.get('port') or ''}")
            self.conn.add(t("account.layer"), str(c.get("layer") or "—"))
            self.conn.add(t("account.library"), c.get("library") or "—")
            self.conn.add(t("account.latency"), f"{c['latency_ms']} ms" if c.get("latency_ms") else "—")
        if info.get("connection_error"):
            self.conn.add(t("account.error"), info["connection_error"])
        self.sec.clear()
        self.sec.add(t("account.session"), t(f"account.session_{info.get('session_status', 'missing')}"))
        self.sec.add(t("account.store"), info.get("credential_store") or "—")
        self.sec.add(t("account.portable"), t("common.yes") if info.get("portable") else t("common.no"))
        self.sec.add(t("account.app_version"), f"{__version__} ({info.get('build')})")
        self.local.clear()
        self.local.add(t("account.db_path"), info.get("database_path") or "—")
        self.local.add(t("account.db_size"), t.size(info.get("database_bytes")))
        self.local.add(t("account.messages"), t.num(info.get("messages") or 0))
        cache = info.get("cache") or {}
        self.local.add(t("account.cache"), t.size(cache.get("disk_bytes")))
        sync = info.get("sync") or {}
        last = max(sync.get("last_incremental") or 0, sync.get("last_full_sync") or 0) or None
        self.local.add(t("account.last_sync"), t.relative(last))
        self.ops.clear()
        for op in info.get("last_operations") or []:
            self.ops.addItem(f"{t.date(op.get('ts'), with_time=True)}  ·  {_describe_op(t, op)}")
        if not self.ops.count():
            self.ops.addItem(t("account.no_operations"))

    def _logout(self) -> None:
        t, g = self.t, self.gui
        box = QMessageBox(self)
        box.setWindowTitle(t("account.log_out"))
        box.setText(t("account.logout_text"))
        forget = QCheckBox(t("account.forget_api"))
        box.setCheckBox(forget)
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
        box.button(QMessageBox.StandardButton.Ok).setText(t("account.log_out"))
        if box.exec() != QMessageBox.StandardButton.Ok:
            return

        def done(_r: Any) -> None:
            if g.settings.privacy.clear_cache_on_logout:
                g.ctx.cache.clear()
            g.notify(t("account.logged_out"), t("account.logged_out_text"), "success")
            g.reload_account()
            self.mark_dirty()
        g.run(g.ctx.auth.logout(revoke_remote=True, forget_api=forget.isChecked()), done)

    def on_event(self, topic: str, payload: dict) -> None:
        if topic in ("auth.changed", "sync.finished"):
            self.mark_dirty()


# ============================================================================ settings
SECTIONS = [("appearance", "sun"), ("sync", "refresh-cw"), ("performance", "cpu"), ("export", "download"), ("notifications", "bell"),
            ("privacy", "shield-check"), ("network", "globe"), ("shortcuts", "keyboard"), ("data", "database"), ("advanced", "settings")]


class SettingsPage(Page):
    key = "settings"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        body = QHBoxLayout()
        body.setSpacing(16)
        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(210)
        self.nav.setIconSize(QSize(16, 16))
        self.stack = QStackedWidget()
        for key, icon in SECTIONS:
            self.nav.addItem(t(f"settings.sec_{key}"))
            self.nav.item(self.nav.count() - 1).setIcon(g.icons.icon(icon, g.pal.accent, 16))
            page = getattr(self, f"_sec_{key}")()
            from PySide6.QtWidgets import QFrame, QScrollArea
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setWidget(page)
            self.stack.addWidget(sa)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        self.root.addLayout(body, 1)

    # ---- helpers
    def _section(self, key: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(14)
        lay.addWidget(label(self.t(f"settings.sec_{key}"), "SectionTitle"))
        lay.addWidget(label(self.t(f"settings.sec_{key}_sub"), "Muted", wrap=True))
        return w, lay

    def _form_card(self, lay: QVBoxLayout, title: str | None = None) -> QFormLayout:
        c = Card(title)
        f = QFormLayout()
        f.setSpacing(10)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter)
        c.add(f)
        lay.addWidget(c)
        return f

    def _save(self, rebuild: bool | str = False) -> None:
        """Settings save automatically; ``True`` rebuilds the window, ``"restart"`` tells the user to restart."""
        self.gui.save_settings()
        if rebuild == "restart":
            self.gui.notify(self.t("settings.saved"), self.t("settings.restart_hint"), "info")
        if rebuild is True:
            QTimer.singleShot(50, self.gui.controller.rebuild)

    def _check(self, obj: Any, attr: str, text: str, rebuild: bool | str = False) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(bool(getattr(obj, attr)))
        cb.toggled.connect(lambda v: (setattr(obj, attr, bool(v)), self._save(rebuild)))
        return cb

    def _combo(self, obj: Any, attr: str, options: list[tuple[Any, str]], rebuild: bool | str = False) -> QComboBox:
        c = QComboBox()
        c.setMinimumWidth(220)
        for v, text in options:
            c.addItem(text, v)
        c.setCurrentIndex(max(0, c.findData(getattr(obj, attr))))
        c.currentIndexChanged.connect(lambda _i: (setattr(obj, attr, c.currentData()), self._save(rebuild)))
        return c

    def _spin(self, obj: Any, attr: str, lo: float, hi: float, step: float = 1, suffix: str = "", double: bool = False) -> QWidget:
        s = QDoubleSpinBox() if double else QSpinBox()
        s.setMinimumWidth(140)
        s.setRange(lo, hi)  # type: ignore[arg-type]
        s.setSingleStep(step)  # type: ignore[arg-type]
        if suffix:
            s.setSuffix(f" {suffix}")
        s.setValue(getattr(obj, attr))
        s.valueChanged.connect(lambda v: (setattr(obj, attr, v), self._save()))
        return s

    def _text(self, obj: Any, attr: str, browse: bool = False) -> QWidget:
        e = QLineEdit(str(getattr(obj, attr) or ""))
        e.editingFinished.connect(lambda: (setattr(obj, attr, e.text().strip()), self._save()))
        if not browse:
            return e
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(e, 1)

        def pick() -> None:
            d = QFileDialog.getExistingDirectory(self, "", e.text())
            if d:
                e.setText(d)
                setattr(obj, attr, d)
                self._save()
        h.addWidget(button(self.t("common.browse"), self.gui.icons.icon("folder-open", size=14), on_click=pick))
        return w

    # ---- sections
    def _sec_appearance(self) -> QWidget:
        t, a = self.t, self.gui.settings.appearance
        w, lay = self._section("appearance")
        f = self._form_card(lay)
        f.addRow(t("settings.theme"), self._combo(a, "theme", [("system", t("settings.theme_system")), ("light", t("settings.theme_light")),
                                                               ("dark", t("settings.theme_dark"))], True))
        f.addRow(t("settings.font_scale"), self._combo(a, "font_scale", [(0.9, "90%"), (1.0, "100%"), (1.1, "110%"), (1.25, "125%")], True))
        f.addRow("", self._check(a, "animations", t("settings.animations")))
        f.addRow("", self._check(a, "compact_rows", t("settings.compact_rows"), True))
        lay.addStretch(1)
        return w

    def _sec_sync(self) -> QWidget:
        t, s = self.t, self.gui.settings.sync
        w, lay = self._section("sync")
        f = self._form_card(lay)
        f.addRow("", self._check(s, "auto_sync_on_start", t("settings.auto_sync_on_start")))
        f.addRow(t("settings.auto_sync_interval"), self._spin(s, "auto_sync_interval_min", 0, 1440, 5, t("common.minutes")))
        f.addRow(t("settings.recheck_recent"), self._spin(s, "recheck_recent", 0, 5000, 50))
        f.addRow(t("settings.batch_size"), self._spin(s, "batch_size", 10, 100, 10))
        f.addRow(t("settings.request_delay"), self._spin(s, "request_delay_s", 0.3, 10, 0.1, t("common.seconds"), double=True))
        f.addRow(t("settings.max_flood_wait"), self._spin(s, "max_flood_wait_s", 0, 86400, 60, t("common.seconds")))
        f.addRow("", self._check(s, "keep_remote_deleted", t("settings.keep_remote_deleted")))
        lay.addWidget(label(t("sync.rate_note"), "Subtle", wrap=True))
        lay.addStretch(1)
        return w

    def _sec_performance(self) -> QWidget:
        t, p = self.t, self.gui.settings.performance
        w, lay = self._section("performance")
        f = self._form_card(lay)
        f.addRow(t("settings.download_concurrency"), self._spin(p, "download_concurrency", 1, 6))
        f.addRow(t("settings.page_size"), self._spin(p, "page_size", 100, 2000, 100))
        f.addRow(t("settings.thumbnail_cache"), self._spin(p, "thumbnail_cache_mb", 32, 8192, 32, "MB"))
        f.addRow(t("settings.preview_max"), self._spin(p, "preview_max_mb", 1, 500, 5, "MB"))
        lay.addStretch(1)
        return w

    def _sec_export(self) -> QWidget:
        from ...export.writers import FORMATS
        t, e, s = self.t, self.gui.settings.export, self.gui.settings
        w, lay = self._section("export")
        f = self._form_card(lay)
        f.addRow(t("settings.default_format"), self._combo(e, "format", [(x, t(f"export.fmt_{x}")) for x in FORMATS]))
        f.addRow(t("export.folder_template"), self._text(e, "folder_template"))
        f.addRow(t("export.file_template"), self._text(e, "file_template"))
        f.addRow("", self._check(e, "include_metadata", t("export.include_metadata")))
        f.addRow("", self._check(e, "include_text", t("export.include_text")))
        f.addRow("", self._check(e, "download_media", t("export.download_media")))
        f.addRow(t("settings.export_dir"), self._text(s, "export_dir", browse=True))
        f.addRow(t("settings.download_dir"), self._text(s, "download_dir", browse=True))
        lay.addStretch(1)
        return w

    def _sec_notifications(self) -> QWidget:
        t, n = self.t, self.gui.settings.notifications
        w, lay = self._section("notifications")
        f = self._form_card(lay)
        for k in ("toasts", "job_finished", "sync_finished", "errors"):
            f.addRow("", self._check(n, k, t(f"settings.notify_{k}")))
        lay.addStretch(1)
        return w

    def _sec_privacy(self) -> QWidget:
        t, p = self.t, self.gui.settings.privacy
        w, lay = self._section("privacy")
        f = self._form_card(lay)
        f.addRow("", self._check(p, "mask_phone", t("settings.mask_phone")))
        f.addRow("", self._check(p, "hide_previews_in_screenshots", t("settings.hide_previews")))
        f.addRow("", self._check(p, "clear_cache_on_logout", t("settings.clear_cache_on_logout")))
        c = Card(t("settings.privacy_facts"))
        c.add(label(t("settings.privacy_facts_text"), "Muted", wrap=True))
        c.add(hbox(button(t("welcome.show_again"), self.gui.icons.icon("sparkles", size=14), on_click=self._show_welcome), None))
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _show_welcome(self) -> None:
        from ..welcome import WelcomeSheet
        WelcomeSheet(self.gui.pal, self.gui.icons, self.window()).exec()

    def _sec_network(self) -> QWidget:
        from ...telegram.proxy import PROXY_TYPES, parse_proxy_link
        t, n = self.t, self.gui.settings.network
        w, lay = self._section("network")
        f = self._form_card(lay, t("settings.proxy"))
        kind = self._combo(n, "proxy_type", [(k, t(f"settings.proxy_{k}")) for k in PROXY_TYPES], "restart")
        f.addRow(t("settings.proxy_type"), kind)
        host = self._text(n, "proxy_host")
        f.addRow(t("settings.proxy_host"), host)
        f.addRow(t("settings.proxy_port"), self._spin(n, "proxy_port", 0, 65535))
        user = self._text(n, "proxy_username")
        f.addRow(t("settings.proxy_username"), user)
        pw = self._text(n, "proxy_password")
        pw.setEchoMode(QLineEdit.EchoMode.Password)  # type: ignore[attr-defined]
        f.addRow(t("settings.proxy_password"), pw)
        secret = self._text(n, "proxy_secret")
        f.addRow(t("settings.proxy_secret"), secret)
        link = QLineEdit()
        link.setPlaceholderText("tg://proxy?server=…&port=…&secret=…  ·  socks5://user:pass@host:port")

        def apply_link() -> None:
            data = parse_proxy_link(link.text())
            if not data:
                self.gui.notify(t("settings.proxy"), t("settings.proxy_link_invalid"), "warning")
                return
            for k, v in data.items():
                setattr(n, k, v)
            self._save("restart")
            QTimer.singleShot(50, self.gui.controller.rebuild)
        f.addRow(t("settings.proxy_link"), hbox(link, button(t("settings.proxy_apply"), on_click=apply_link)))
        lay.addWidget(label(t("settings.proxy_note"), "Subtle", wrap=True))
        lay.addStretch(1)
        return w

    def _sec_shortcuts(self) -> QWidget:
        t, s = self.t, self.gui.settings
        w, lay = self._section("shortcuts")
        c = Card()
        tb = QTableWidget(len(DEFAULT_SHORTCUTS), 2)
        tb.setHorizontalHeaderLabels([t("settings.action"), t("settings.shortcut")])
        tb.verticalHeader().setVisible(False)
        tb.horizontalHeader().setStretchLastSection(True)
        tb.setColumnWidth(0, 300)
        tb.verticalHeader().setDefaultSectionSize(40)
        tb.setMinimumHeight(560)
        self._seq_edits: dict[str, QKeySequenceEdit] = {}
        for i, (action, default) in enumerate(DEFAULT_SHORTCUTS.items()):
            it = QTableWidgetItem(t(f"shortcuts.{action}"))
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tb.setItem(i, 0, it)
            ed = QKeySequenceEdit(QKeySequence(s.shortcuts.get(action, default)))
            ed.editingFinished.connect(lambda a=action, e=ed: self._set_shortcut(a, e))
            tb.setCellWidget(i, 1, ed)
            self._seq_edits[action] = ed
        c.add(tb)
        c.add(button(t("settings.reset_shortcuts"), self.gui.icons.icon("rotate-ccw", size=14), on_click=self._reset_shortcuts))
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _set_shortcut(self, action: str, ed: QKeySequenceEdit) -> None:
        seq = ed.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        clash = [a for a, v in self.gui.settings.shortcuts.items() if v == seq and a != action and seq]
        if clash:
            self.gui.notify(self.t("settings.shortcut_conflict"), self.t(f"shortcuts.{clash[0]}"), "warning")
            ed.setKeySequence(QKeySequence(self.gui.settings.shortcuts.get(action, "")))
            return
        self.gui.settings.shortcuts[action] = seq
        self._save()
        if self.gui.window is not None:
            self.gui.window.apply_shortcuts()

    def _reset_shortcuts(self) -> None:
        self.gui.settings.shortcuts = dict(DEFAULT_SHORTCUTS)
        for a, ed in self._seq_edits.items():
            ed.setKeySequence(QKeySequence(DEFAULT_SHORTCUTS[a]))
        self._save()
        if self.gui.window is not None:
            self.gui.window.apply_shortcuts()

    def _sec_data(self) -> QWidget:
        t, g = self.t, self.gui
        w, lay = self._section("data")
        self.db_info = KeyValueGrid()
        c = Card(t("settings.database"), t("settings.database_sub"))
        c.add(self.db_info)
        row = QHBoxLayout()
        for text, icon, fn in ((t("settings.db_check"), "shield-check", self._db_check), (t("settings.db_optimize"), "sparkles", self._db_optimize),
                               (t("settings.db_vacuum"), "archive", self._db_vacuum), (t("settings.db_backup"), "download", self._db_backup),
                               (t("settings.open_folder"), "folder-open", lambda: g.open_path(str(g.ctx.paths.database_dir)))):
            row.addWidget(button(text, g.icons.icon(icon, size=14), on_click=fn))
        row.addStretch(1)
        c.add(row)
        lay.addWidget(c)
        self.cache_info = KeyValueGrid()
        c = Card(t("settings.cache"), t("settings.cache_sub"))
        c.add(self.cache_info)
        row = QHBoxLayout()
        row.addWidget(button(t("settings.clear_thumbs"), g.icons.icon("image", size=14), on_click=lambda: self._clear_cache("thumb")))
        row.addWidget(button(t("settings.clear_cache"), g.icons.icon("trash-2", size=14), on_click=lambda: self._clear_cache(None)))
        row.addStretch(1)
        c.add(row)
        lay.addWidget(c)
        c = Card(t("settings.danger_zone"), t("settings.danger_zone_sub"))
        c.add(button(t("settings.reset_index"), g.icons.icon("triangle-alert", "#FFFFFF", 14), "danger", on_click=self._reset_index))
        lay.addWidget(c)
        lay.addStretch(1)
        self._load_data_info()
        return w

    def _load_data_info(self) -> None:
        t, g = self.t, self.gui
        self.db_info.clear()
        self.db_info.add(t("account.db_path"), str(g.ctx.db.path))
        self.db_info.add(t("account.db_size"), t.size(g.ctx.db.size_bytes()))
        self.db_info.add(t("settings.schema"), str(current_version(g.ctx.db)))
        aid = g.account_id
        self.db_info.add(t("account.messages"), t.num(g.ctx.messages.total(aid) if aid else 0))
        st = g.ctx.cache.stats()
        self.cache_info.clear()
        self.cache_info.add(t("settings.cache_path"), st["path"])
        self.cache_info.add(t("settings.cache_used"), f"{t.size(st['disk_bytes'])} / {t.size(st['limit_bytes'])}")
        self.cache_info.add(t("settings.cache_files"), t.num(st["disk_files"]))

    def _db_check(self) -> None:
        r = self.gui.ctx.db.integrity_check()
        self.gui.notify(self.t("settings.db_check"), r, "success" if r == "ok" else "error")

    def _db_optimize(self) -> None:
        self.gui.ctx.db.optimize_fts()
        self.gui.notify(self.t("settings.db_optimized"), "", "success")

    def _db_vacuum(self) -> None:
        before = self.gui.ctx.db.size_bytes()
        self.gui.ctx.db.vacuum()
        self.gui.notify(self.t("settings.db_vacuumed"), f"{self.t.size(before)} → {self.t.size(self.gui.ctx.db.size_bytes())}", "success")
        self._load_data_info()

    def _db_backup(self) -> None:
        default = str(self.gui.ctx.paths.database_dir / "backups" / f"arcivo-{datetime.now():%Y%m%d-%H%M%S}.db")
        path, _ = QFileDialog.getSaveFileName(self, self.t("settings.db_backup"), default, "SQLite (*.db)")
        if path:
            self.gui.ctx.db.backup_to(Path(path))
            self.gui.notify(self.t("settings.db_backed_up"), path, "success")

    def _clear_cache(self, kind: str | None) -> None:
        n = self.gui.ctx.cache.clear(kind)
        self.gui.notify(self.t("settings.cache_cleared", n=n), self.t("settings.cache_safe"), "success")
        self._load_data_info()

    def _reset_index(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, self.t("settings.reset_index"), self.t("settings.reset_index_text"))
        if not ok or text.strip().upper() != "RESET":
            return
        with self.gui.ctx.db.transaction() as c:
            c.execute("DELETE FROM messages")
            c.execute("DELETE FROM links")
            c.execute("UPDATE sync_state SET initial_complete = 0, checkpoint_id = 0, max_message_id = 0, total_synced = 0")
        self.gui.ctx.audit.add("reset_index")
        self.gui.ctx.bus.publish("data.changed", reason="reset")
        self.gui.notify(self.t("settings.index_reset"), self.t("settings.index_reset_text"), "success")
        self._load_data_info()

    def _sec_advanced(self) -> QWidget:
        t, s, g = self.t, self.gui.settings, self.gui
        w, lay = self._section("advanced")
        f = self._form_card(lay)
        f.addRow(t("settings.log_level"), self._combo(s, "log_level", [(x, x) for x in ("DEBUG", "INFO", "WARNING", "ERROR")], "restart"))
        f.addRow(t("settings.credential_backend"), self._combo(s, "credential_backend", [
            ("auto", t("settings.cred_auto")), ("keyring", t("settings.cred_keyring")), ("dpapi", t("settings.cred_dpapi")),
            ("file", t("settings.cred_file"))], "restart"))
        f.addRow(t("settings.selection_on_filter"), self._combo(s, "selection_on_filter_change", [
            ("ask", t("settings.sel_ask")), ("keep", t("settings.sel_keep")), ("clear", t("settings.sel_clear"))]))
        f.addRow("", self._check(s, "confirm_destructive_twice", t("settings.confirm_twice")))
        row = QHBoxLayout()
        row.addWidget(button(t("settings.open_config"), g.icons.icon("folder-open", size=14), on_click=lambda: g.open_path(str(g.ctx.paths.config_dir))))
        row.addWidget(button(t("settings.reset_all"), g.icons.icon("rotate-ccw", size=14), on_click=self._reset_all))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(label(t("settings.paths_info", config=str(g.ctx.paths.config_file), data=str(g.ctx.paths.data_dir)), "Subtle",
                            wrap=True, selectable=True))
        lay.addStretch(1)
        return w

    def _reset_all(self) -> None:
        if QMessageBox.question(self, self.t("settings.reset_all"), self.t("settings.reset_all_text")) != QMessageBox.StandardButton.Yes:
            return
        from ...core.config import Settings
        cfg = self.gui.ctx.config
        keep_db = cfg.settings.database_path
        cfg.settings = Settings()
        cfg.settings.database_path = keep_db
        cfg.save()
        QTimer.singleShot(50, self.gui.controller.rebuild)

    def open(self, **kw: Any) -> None:
        sec = kw.get("section")
        keys = [k for k, _ in SECTIONS]
        if sec in keys:
            self.nav.setCurrentRow(keys.index(sec))

    def refresh(self) -> None:
        self._load_data_info()


# ============================================================================ logs
class LogsPage(Page):
    key = "logs"
    scrollable = False

    def build(self) -> None:
        g, t = self.gui, self.t
        self.level = QComboBox()
        for lv in ("ALL", "DEBUG", "INFO", "WARNING", "ERROR"):
            self.level.addItem(t(f"logs.level_{lv.lower()}"), lv)
        self.level.currentIndexChanged.connect(lambda _i: self.refresh())
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("logs.filter"))
        self.filter.textChanged.connect(lambda _x: self.refresh())
        self.follow = QCheckBox(t("logs.follow"))
        self.follow.setChecked(True)
        for w in (self.level, self.filter, self.follow):
            self.actions.addWidget(w)
        self.actions.addWidget(button(t("logs.copy"), g.icons.icon("copy", size=14), on_click=lambda: g.copy(self.view.toPlainText())))
        self.actions.addWidget(button(t("logs.open_folder"), g.icons.icon("folder-open", size=14),
                                      on_click=lambda: g.open_path(str(g.ctx.paths.logs_dir))))
        self.view = QPlainTextEdit()
        self.view.setObjectName("LogView")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.root.addWidget(self.view, 1)
        self.root.addWidget(label(t("logs.redaction_note"), "Subtle", wrap=True))
        self.timer = QTimer(self, interval=1500)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() and self.follow.isChecked() else None)
        self.timer.start()
        self._last = ""

    def refresh(self) -> None:
        lv = self.level.currentData()
        needle = self.filter.text().lower().strip()
        order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        lines = []
        for ln in recent_lines():
            if lv != "ALL":
                hit = next((x for x in order if f" {x} " in ln or f"[{x}]" in ln), "INFO")
                if order.index(hit) < order.index(lv):
                    continue
            if needle and needle not in ln.lower():
                continue
            lines.append(ln)
        text = "\n".join(lines)
        if text != self._last:
            self._last = text
            self.view.setPlainText(text)
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())


# ============================================================================ about
CREDITS = [
    ("Telethon", "MIT", "https://github.com/LonamiWebs/Telethon"),
    ("Qt for Python (PySide6)", "LGPL-3.0", "https://doc.qt.io/qtforpython/"),
    ("Lucide icons", "ISC", "https://lucide.dev"),
    ("Inter typeface", "SIL OFL 1.1", "https://rsms.me/inter/"),
    ("platformdirs", "MIT", "https://github.com/platformdirs/platformdirs"),
    ("keyring", "MIT", "https://github.com/jaraco/keyring"),
    ("python-socks", "Apache-2.0", "https://github.com/romis2012/python-socks"),
    ("SQLite (FTS5)", "Public domain", "https://sqlite.org"),
]


class AboutPage(Page):
    key = "about"

    def title(self) -> str:
        return ""

    def build(self) -> None:
        g, t = self.gui, self.t
        self.title_label.setVisible(False)
        hero = QWidget()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(0, 18, 0, 6)
        hl.setSpacing(6)
        logo = QLabel()
        px = QPixmap(str(resource_path("assets", "brand", "arcivo-256.png")))
        if not px.isNull():
            px = px.scaled(192, 192, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            px.setDevicePixelRatio(2)
            logo.setPixmap(px)
        else:
            logo.setPixmap(g.icons.pixmap("archive", g.pal.accent, 96))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(logo)
        hl.addSpacing(6)
        for text, obj in ((APP_NAME, "PageTitle"), (t("about.version", version=__version__, build=BUILD), "Muted"),
                          (t("about.tagline", tagline=APP_TAGLINE), None), (t("about.made_by", author=AUTHOR), "Subtle")):
            lb = label(text, obj)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.addWidget(lb)
        hl.addSpacing(10)
        links = QHBoxLayout()
        links.setSpacing(8)
        links.addStretch(1)
        links.addWidget(button(t("about.telegram", handle=TELEGRAM_HANDLE), g.icons.icon("send", "#FFFFFF", 14), "primary",
                               on_click=lambda: g.open_url(TELEGRAM_URL)))
        links.addWidget(button(t("about.github"), g.icons.icon("github", g.pal.text, 14), on_click=lambda: g.open_url(REPO_URL)))
        links.addWidget(button(t("about.report_issue"), g.icons.icon("circle-alert", g.pal.text, 14),
                               on_click=lambda: g.open_url(REPO_URL + "/issues")))
        links.addStretch(1)
        hl.addLayout(links)
        self.root.addWidget(hero)

        wrap = QHBoxLayout()
        wrap.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(14)
        notice = Card(padding=16)
        nl = QHBoxLayout()
        nl.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(g.icons.pixmap("shield-check", g.pal.warning, 20))
        nl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        tc = QVBoxLayout()
        tc.setSpacing(2)
        tc.addWidget(label(t("about.unofficial"), "CardTitle"))
        tc.addWidget(label(t("about.unofficial_text"), "Muted", wrap=True))
        nl.addLayout(tc, 1)
        notice.add(nl)
        col.addWidget(notice)
        c = Card(t("about.privacy"))
        c.add(label(t("about.privacy_text"), "Muted", wrap=True))
        col.addWidget(c)
        c = Card(t("about.credits"))
        credits = InsetListLike()
        for name, lic, url in CREDITS:
            credits.add(name, lic, lambda u=url: g.open_url(u), g.icons.pixmap("external-link", g.pal.text_subtle, 13))
        c.add(credits)
        col.addWidget(c)
        c = Card(t("about.system"))
        kv = KeyValueGrid([(t("about.python"), sys.version.split()[0]), (t("about.qt"), f"Qt {qVersion()} · PySide6 {PYSIDE_VERSION}"),
                           (t("about.os"), f"{platform.system()} {platform.release()}"), (t("about.data_dir"), str(g.ctx.paths.data_dir))])
        c.add(kv)
        c.add(hbox(button(t("about.copy_diag"), g.icons.icon("copy", g.pal.text, 14), on_click=lambda: g.copy(self._diag())), None))
        col.addWidget(c)
        foot = label(t("about.license_line"), "Subtle", wrap=True)
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(foot)
        holder = QWidget()
        holder.setLayout(col)
        holder.setMaximumWidth(760)
        wrap.addWidget(holder, 10)
        wrap.addStretch(1)
        self.root.addLayout(wrap)
        self.root.addStretch(1)

    def _diag(self) -> str:
        return (f"{APP_NAME} {__version__} ({BUILD})\nPython {sys.version.split()[0]} · Qt {qVersion()} · PySide6 {PYSIDE_VERSION}\n"
                f"{platform.platform()}\ntheme={self.gui.pal.name} portable={self.gui.ctx.paths.portable} "
                f"proxy={self.gui.settings.network.describe()}")


class InsetListLike(QWidget):
    """Credits list: name · licence · link glyph, hairline separated."""

    def __init__(self) -> None:
        super().__init__()
        from ..widgets.common import InsetList
        self._list = InsetList()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)

    def add(self, name: str, lic: str, on_click, glyph) -> None:  # type: ignore[no-untyped-def]
        from ..widgets.common import InsetRow
        row = InsetRow(None, name, trailing=lic, chevron_px=glyph)
        row.clicked.connect(on_click)
        self._list.add(row)



