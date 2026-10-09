"""The ``Gui`` facade handed to every page and widget.

It bundles the core context, the async runtime, theme/icon helpers, the shared
message selection and high-level actions (tag, flag, export, delete), so pages
never talk to each other directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QWidget

from ..core.errors import ArcivoError
from ..i18n.translator import Translator
from .runtime import CoreRuntime
from .theme.style import Icons
from .theme.tokens import Palette
from .widgets.messages_model import SelectionManager

log = logging.getLogger(__name__)


class Gui(QObject):
    navigateRequested = Signal(str, dict)
    accountChanged = Signal()

    def __init__(self, controller, ctx, runtime: CoreRuntime, t: Translator, pal: Palette, demo: bool = False) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.controller = controller
        self.ctx = ctx
        self.runtime = runtime
        self.t = t
        self.pal = pal
        self.icons = Icons(pal)
        self.demo = demo
        self.window: QWidget | None = None
        self.toasts = None  # set by MainWindow
        self.selection = SelectionManager()
        self._account_id: int | None = None
        self._account_loaded = False
        self.actions = Actions(self)

    # ------------------------------------------------------------- state
    @property
    def settings(self):  # type: ignore[no-untyped-def]
        return self.ctx.config.settings

    def save_settings(self) -> None:
        self.ctx.config.save()

    @property
    def account_id(self) -> int | None:
        if not self._account_loaded or self._account_id is None:
            self._account_id = self.ctx.account_id
            self._account_loaded = True
        return self._account_id

    def reload_account(self) -> None:
        self._account_loaded = False
        self.accountChanged.emit()

    # ------------------------------------------------------------- feedback
    def notify(self, title: str, text: str = "", kind: str = "info",
               action: tuple[str, Callable[[], None]] | None = None) -> None:
        if self.toasts is not None and (self.settings.notifications.toasts or kind == "error"):
            self.toasts.show(title, text, kind, action)

    def error_text(self, exc: BaseException) -> str:
        if isinstance(exc, ArcivoError):
            key = exc.i18n_key
            if self.t.has(key) or self.t._en.get(key):
                return self.t(key, seconds=int(exc.retry_after or 0), detail=str(exc), **{k: str(v) for k, v in exc.args_map.items()})
            return str(exc)
        return f"{type(exc).__name__}: {exc}"

    def show_error(self, exc: BaseException, title: str | None = None) -> None:
        log.warning("UI error: %s", exc)
        self.notify(title or self.t("errors.title"), self.error_text(exc), "error")

    # ------------------------------------------------------------- async helpers
    def run(self, coro: Coroutine[Any, Any, Any], on_ok: Callable[[Any], None] | None = None,
            on_err: Callable[[BaseException], None] | None = None) -> None:
        self.runtime.submit(coro, on_ok, on_err or self.show_error)

    def jobs(self, fn: Callable[[Any], Any]) -> Any:
        """Call ``fn(job_manager)`` on the core loop thread and return its result."""
        return self.runtime.call_sync(lambda: fn(self.ctx.jobs))

    def submit_job(self, kind: str, title: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            job = self.jobs(lambda m: m.submit(kind, title, params).to_dict())
        except Exception as exc:
            self.show_error(exc)
            return None
        self.notify(self.t("jobs.started"), title, "info", (self.t("jobs.view"), lambda: self.navigate("jobs")))
        return job

    def sync(self, mode: str = "auto") -> None:
        active = self.jobs(lambda m: [j.id for j in m.active() if j.kind == "sync"])
        if active:
            self.notify(self.t("sync.already_running"), "", "info")
            return
        self.submit_job("sync", self.t(f"sync.job_{mode}"), {"mode": mode})

    # ------------------------------------------------------------- navigation
    def navigate(self, key: str, **kw: Any) -> None:
        self.navigateRequested.emit(key, kw)

    def explore(self, query: str = "") -> None:
        self.navigate("explorer", query=query)

    def open_path(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.notify(self.t("common.copied"), "", "success")


class Actions:
    """Bulk operations shared by explorer, media, storage and collections."""

    def __init__(self, gui: Gui) -> None:
        self.gui = gui

    def _undo_action(self) -> tuple[str, Callable[[], None]]:
        def undo() -> None:
            label = self.gui.ctx.org.undo.undo()
            if label:
                self.gui.notify(self.gui.t("common.undone"), label, "info")
        return (self.gui.t("common.undo"), undo)

    def tag(self, ids: list[int]) -> None:
        from .widgets.dialogs import TagPickerDialog
        aid = self.gui.account_id
        if not ids or aid is None:
            return
        dlg = TagPickerDialog(self.gui.window, self.gui, len(ids))
        if dlg.exec() and dlg.selected_tag() is not None:
            remove = dlg.remove.isChecked()
            n = self.gui.ctx.org.tag(aid, dlg.selected_tag(), ids, remove=remove)
            key = "tags.removed_n" if remove else "tags.applied_n"
            self.gui.notify(self.gui.t(key, n=n), "", "success", self._undo_action())

    def tag_with(self, tag_id: int, ids: list[int]) -> None:
        aid = self.gui.account_id
        if ids and aid is not None:
            n = self.gui.ctx.org.tag(aid, tag_id, ids)
            self.gui.notify(self.gui.t("tags.applied_n", n=n), "", "success", self._undo_action())

    def flag(self, ids: list[int], value: bool = True) -> None:
        aid = self.gui.account_id
        if ids and aid is not None:
            self.gui.ctx.org.set_flag(aid, ids, value)
            self.gui.notify(self.gui.t("explorer.flagged_n" if value else "explorer.unflagged_n", n=len(ids)), "", "success",
                            self._undo_action())

    def export(self, ids: list[int] | None = None, query: str | None = None) -> None:
        self.gui.navigate("export", ids=ids or [], query=query or "")

    def delete(self, ids: list[int], reason: str = "manual", context: str = "", source_job: str | None = None) -> None:
        from .widgets.dialogs import DeleteConfirmDialog
        aid = self.gui.account_id
        if not ids or aid is None:
            return
        if self.gui.demo is False and not self.gui.ctx.auth.has_session():
            self.gui.notify(self.gui.t("errors.title"), self.gui.t("errors.not_authenticated"), "error")
            return
        plan = self.gui.ctx.deleter.plan(aid, ids)
        dlg = DeleteConfirmDialog(self.gui.window, self.gui, plan, two_step=self.gui.settings.confirm_destructive_twice,
                                  context=context)
        if dlg.exec() and dlg.confirmed_token:
            params = self.gui.ctx.deleter.job_params(aid, plan, dlg.confirmed_token, reason=reason, source_job=source_job)
            if self.gui.submit_job("delete", self.gui.t("delete.job_title", n=plan.count), params):
                self.gui.selection.remove(plan.ids)

    def copy_text(self, ids: list[int]) -> None:
        aid = self.gui.account_id
        if not ids or aid is None:
            return
        rows = self.gui.ctx.messages.rows_by_ids(aid, ids[:500])
        self.gui.copy("\n\n".join((r["text"] or r["file_name"] or "") for r in rows))
