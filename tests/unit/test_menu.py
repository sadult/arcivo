import sys

from arcivo.cli import menu


def test_menu_has_requested_entries():
    keys = [k for k, _, _ in menu.MENU]
    labels = [label for _, label, _ in menu.MENU]
    assert keys[:3] == ["1", "2", "3"] and keys[-1] == "0"
    assert labels[:3] == ["Sign in", "Open dashboard", "Check connection"] and labels[-1] == "Exit"
    assert set(menu.ACTIONS) == {k for k in keys if k != "0"}


def test_gui_command_from_source():
    cmd = menu.gui_command()
    assert cmd[-2:] == ["-m", "arcivo.gui.app"]
    assert "python" in cmd[0].lower() or cmd[0] == sys.executable
