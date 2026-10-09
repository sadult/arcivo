"""Render real screenshots of the GUI with demo data (headless).

    python scripts/screenshots.py [--out docs/images/screenshots] [--themes dark,light] [--pages ...]

Uses the synthetic demo dataset, so no Telegram account is needed and no
personal data can leak into the images.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGES = ["dashboard", "explorer", "search", "media", "statistics", "storage", "export", "jobs", "collections", "settings",
                 "account", "about", "login", "welcome"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "images" / "screenshots"))
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--pages", default=",".join(DEFAULT_PAGES))
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--messages", type=int, default=4000)
    args = ap.parse_args()
    home = Path(tempfile.mkdtemp(prefix="arcivo-shots-"))
    os.environ.update({"QT_QPA_PLATFORM": "offscreen", "ARCIVO_HOME": str(home), "ARCIVO_DEMO_SIZE": str(args.messages),
                       "QT_SCALE_FACTOR": "1", "ARCIVO_NO_ANIMATIONS": "1"})
    from PySide6.QtCore import QEvent

    from arcivo.cli.main import demo_context
    from arcivo.gui.app import Controller, create_app
    from arcivo.gui.runtime import CoreRuntime

    app = create_app()
    ctx = demo_context()
    rt = CoreRuntime(ctx.bus)
    ctl = Controller(app, ctx, rt, demo=True)
    w, h = (int(x) for x in args.size.split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            app.processEvents()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            time.sleep(0.015)

    win = ctl.build()
    win.resize(w, h)
    win.show()
    gui = ctl.gui
    gui.sync("initial")
    for _ in range(600):
        pump(0.1)
        if ctx.account_id and not gui.jobs(lambda m: m.active()):
            break
    # some organisation so tags/collections/jobs look alive
    aid = ctx.account_id
    tags = {t.name: t.id for t in ctx.org.list_tags()}
    ids = ctx.search.ids(aid, "type:audio")[:60]
    ctx.org.tag(aid, tags["Music"], ids)
    ctx.org.tag(aid, tags["Work"], ctx.search.ids(aid, "type:document")[:90])
    ctx.org.tag(aid, tags["Important"], ctx.search.ids(aid, "has:link")[:25])
    ctx.org.set_flag(aid, ctx.search.ids(aid, "type:video size:>50MB")[:20], True)
    ctx.org.seed_default_collections()
    exp_dir = home / "exports"
    params = {"account_id": aid, "output_dir": str(exp_dir), "query": "tag:Work", "formats": ["json", "html"], "download_media": True,
              "name": "Work documents"}
    gui.submit_job("export", "Export · Work documents", params)
    for _ in range(300):
        pump(0.1)
        if not gui.jobs(lambda m: m.active()):
            break
    gui.toasts.enabled = False  # type: ignore[union-attr]

    themes = args.themes.split(",")
    pages = args.pages.split(",")
    for theme in themes:
        for _once in (0,):
            a = ctx.config.settings.appearance
            a.theme = theme
            ctl.rebuild()
            win = ctl.window
            win.resize(w, h)
            gui = ctl.gui
            gui.toasts.enabled = False  # type: ignore[union-attr]
            pump(0.4)
            for page in pages:
                shot = out / f"{theme}-{page}.png"
                if page == "welcome":
                    from arcivo.gui.welcome import WelcomeSheet
                    dlg = WelcomeSheet(gui.pal, gui.icons, win)
                    dlg.show()
                    dlg.adjustSize()
                    pump(0.4)
                    dlg.grab().save(str(shot))
                    dlg.close()
                    continue
                if page == "login":
                    from arcivo.gui.login_dialog import LoginDialog
                    dlg = LoginDialog(gui, win)
                    dlg._show("api")
                    dlg.resize(680, 560)
                    dlg.show()
                    pump(0.4)
                    dlg.grab().save(str(shot))
                    dlg.close()
                    continue
                kw: dict = {}
                if page == "storage":
                    kw = {"tab": "duplicates"}
                win.navigate(page, kw)
                p = win.pages[page]
                if page == "explorer":
                    p.browser.set_text("")
                    sel = ctx.search.ids(aid, "type:audio")[:7]
                    gui.selection.set(sel)
                    p.browser.details_btn.setChecked(True)
                    p.browser.table.view.selectRow(2)
                    p.browser.details.show_message(p.browser.table.model.id_at(2))
                elif page == "search":
                    p.browser.set_text("type:audio size:>8MB sort:size")
                    p.help.setVisible(True)
                elif page == "media":
                    gui.selection.clear()
                    p.kind.set("photos")
                    p.apply()
                    pump(2.5)
                    p.view.viewport().update()
                elif page == "export":
                    p.source.set("query")
                    p.query.setText("tag:Work")
                    p.download.setChecked(True)
                    p._update_preview()
                if page != "explorer":
                    gui.selection.clear()
                pump(1.2)
                win.grab().save(str(shot))
                print("saved", shot.name, flush=True)
    ctl.shutdown()
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
