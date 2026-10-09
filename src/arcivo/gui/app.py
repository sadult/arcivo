"""GUI entry point and application controller (build/rebuild/login/shutdown)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__
from ..i18n.translator import Translator, set_translator
from . import native
from .facade import Gui
from .runtime import CoreRuntime
from .theme.style import app_font, load_fonts, stylesheet
from .theme.tokens import palette

log = logging.getLogger(__name__)


def resolve_theme(name: str) -> str:
    if name == "system":
        try:
            return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "dark"
    return "light" if name == "light" else "dark"


class Controller:
    def __init__(self, app: QApplication, ctx: Any, runtime: CoreRuntime, demo: bool = False) -> None:
        self.app = app
        self.ctx = ctx
        self.runtime = runtime
        self.demo = demo
        self.gui: Gui | None = None
        self.window = None
        self.rebuilding = False
        self._closed = False

    def build(self) -> Any:
        from .main_window import MainWindow
        a = self.ctx.config.settings.appearance
        t = Translator()
        set_translator(t)
        from .widgets import charts
        charts.ANIMATIONS = a.animations and not os.environ.get("ARCIVO_NO_ANIMATIONS")
        pal = palette(resolve_theme(a.theme))
        native.set_palette(pal)
        self.app.setFont(app_font(a.font_scale))
        self.app.setStyleSheet(stylesheet(pal, a.font_scale))
        self.gui = Gui(self, self.ctx, self.runtime, t, pal, self.demo)
        self.window = MainWindow(self.gui)
        return self.window

    def rebuild(self) -> None:
        old, old_gui = self.window, self.gui
        page = old.current if old else "dashboard"
        geo = old.saveGeometry() if old else QByteArray()
        maximized = old.isMaximized() if old else False
        sel = set(old_gui.selection.ids) if old_gui else set()
        self.rebuilding = True
        try:
            if old_gui is not None:
                try:
                    old_gui.runtime.event.disconnect(old._on_event)  # type: ignore[union-attr]
                except (RuntimeError, TypeError):
                    pass
            win = self.build()
            win.restoreGeometry(geo)
            if sel:
                self.gui.selection.set(sel)  # type: ignore[union-attr]
            win.navigate(page, {})
            win.showMaximized() if maximized else win.show()
            if old is not None:
                old.close()
                old.deleteLater()
        finally:
            self.rebuilding = False

    def login(self, parent=None) -> bool:  # type: ignore[no-untyped-def]
        from .login_dialog import LoginDialog
        gui = self.gui
        dlg = LoginDialog(gui, parent or self.window)
        ok = bool(dlg.exec())
        if ok and gui is not None:
            gui.reload_account()
            gui.sync("auto")
        return ok

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.ctx.config.save()
        except Exception:
            log.exception("Saving settings on exit failed")
        self.runtime.stop(self.ctx.aclose())


def create_app(argv: list[str] | None = None) -> QApplication:
    native.set_app_user_model_id()
    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(native.app_icon())
    app.setDesktopFileName("arcivo")
    load_fonts()
    native.install_window_styler(app)
    if not hasattr(app, "_arcivo_gc"):
        from .runtime import UiThreadGarbageCollector
        app._arcivo_gc = UiThreadGarbageCollector()  # type: ignore[attr-defined]
    return app  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arcivo-gui", description=f"{APP_NAME} desktop app")
    parser.add_argument("--demo", action="store_true", help="explore the app with synthetic data (no Telegram account needed)")
    parser.add_argument("--page", default=None, help="page to open on start (e.g. explorer)")
    args, _qt = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    demo = args.demo or os.environ.get("ARCIVO_DEMO") == "1"
    app = create_app()
    if demo:
        from ..cli.main import demo_context
        ctx = demo_context()
    else:
        from ..context import AppContext
        ctx = AppContext()
    runtime = CoreRuntime(ctx.bus)
    ctl = Controller(app, ctx, runtime, demo)
    win = ctl.build()
    app.aboutToQuit.connect(ctl.shutdown)

    if not os.environ.get("ARCIVO_SKIP_WELCOME"):
        from .welcome import show_welcome_if_needed
        show_welcome_if_needed(ctx, ctl.gui.pal, ctl.gui.icons)  # type: ignore[union-attr]

    authorized = demo
    if not demo:
        try:
            authorized = bool(runtime.submit(ctx.auth.is_authorized()).result(timeout=25))
        except Exception as exc:
            log.warning("Authorization check failed: %s", exc)
            authorized = False
            if ctx.auth.has_session():
                ctl.gui.notify(ctl.gui.t("app.offline_title"), ctl.gui.t("app.offline_text"), "warning")  # type: ignore[union-attr]
        if not authorized and not ctx.auth.has_session():
            if not ctl.login(win) and ctx.account_id is None:
                ctl.shutdown()
                return 0
            authorized = True
    win.show()
    if args.page:
        win.navigate(args.page, {})
    gui = ctl.gui
    if authorized and gui is not None:
        if demo and (gui.account_id is None or ctx.messages.total(gui.account_id) == 0):
            gui.sync("initial")
        elif ctx.config.settings.sync.auto_sync_on_start:
            gui.sync("auto")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
