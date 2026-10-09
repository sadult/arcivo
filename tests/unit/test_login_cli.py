"""Regression tests for `arcivo login`: provider registration and the terminal UI."""

from __future__ import annotations

import subprocess
import sys

from arcivo.cli import tui


def test_phone_provider_registered_without_importing_phone_module() -> None:
    # Fresh interpreter: importing only the service must register the "phone" provider (KeyError: 'phone' bug).
    code = "from arcivo.auth.service import PROVIDERS; assert 'phone' in PROVIDERS, PROVIDERS"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_tui_renders_without_colour(capsys, monkeypatch) -> None:
    monkeypatch.setattr(tui.out, "_COLOR", False)
    tui.banner()
    tui.steps("code", skipped={"api"})
    tui.panel("Login code", ["A login code was sent to +98••••67."])
    text = capsys.readouterr().out
    assert "Your Saved Messages, organised." in text
    assert "Login code" in text and "+98••••67" in text
    assert "\033[" not in text


def test_run_uses_runner(monkeypatch) -> None:
    from arcivo.cli.main import run

    async def answer() -> int:
        return 42

    assert run(answer()) == 42
