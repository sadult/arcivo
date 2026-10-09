"""Headless GUI smoke test: build the window with demo data and visit every page in both themes.

Runs in a subprocess so a native Qt crash fails the test instead of killing pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

SCRIPT = textwrap.dedent(
    """
    import logging, sys, time, traceback
    from arcivo.cli.main import demo_context
    from arcivo.gui.app import Controller, create_app
    from arcivo.gui.main_window import NAV
    from arcivo.gui.runtime import CoreRuntime

    errors = []

    class Catch(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    app = create_app()
    ctx = demo_context()
    logging.getLogger().addHandler(Catch())
    ctx.config.settings.appearance.theme = sys.argv[1]
    ctx.config.settings.onboarding_done = True
    ctl = Controller(app, ctx, CoreRuntime(ctx.bus), demo=True)
    win = ctl.build()
    win.resize(1280, 800)
    win.show()

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    ctl.gui.sync("initial")
    for _ in range(400):
        pump(0.05)
        if ctx.account_id and not ctl.gui.jobs(lambda m: m.active()):
            break
    assert ctx.account_id and ctx.messages.total(ctx.account_id) > 0, "demo sync produced no messages"
    for _section, items in NAV:
        for key, _icon in items:
            try:
                win.navigate(key, {})
                pump(0.15)
            except Exception:
                errors.append(traceback.format_exc())
    ctl.shutdown()
    if errors:
        print("\\n".join(errors))
        sys.exit(1)
    print("OK")
    """
)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_page_renders(tmp_path, theme: str) -> None:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", ARCIVO_HOME=str(tmp_path), ARCIVO_DEMO_SIZE="600",
               ARCIVO_NO_ANIMATIONS="1")
    proc = subprocess.run([sys.executable, "-c", SCRIPT, theme], env=env, capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    assert "OK" in proc.stdout
