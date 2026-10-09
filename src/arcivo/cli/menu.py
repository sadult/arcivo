"""Interactive console home screen – what ``Arcivo.exe`` shows when started without arguments.

Arrow keys / number keys to choose, Enter to run, Esc/Q/0 to quit. Every action returns to the
menu. Works in Windows Terminal, the classic console host, macOS Terminal and Linux terminals;
falls back to numbered input when keys can't be read (e.g. redirected stdin).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME, AUTHOR, REPO_URL, TELEGRAM_URL, __version__
from ..core.errors import ArcivoError
from . import output as out
from . import tui

MENU = [  # key, label, description
    ("1", "Sign in", "connect your Telegram account"),
    ("2", "Open dashboard", "launch the desktop app"),
    ("3", "Check connection", "test the route to Telegram step by step"),
    ("4", "Sync now", "update your local archive"),
    ("5", "Account & storage", "session, database and sync details"),
    ("6", "Proxy settings", "SOCKS5 · HTTP · MTProto"),
    ("7", "Sign out", "remove the session from this computer"),
    ("8", "About & privacy", "what Arcivo does with your data"),
    ("0", "Exit", ""),
]


# ----------------------------------------------------------------------------- keyboard
def read_key() -> str:
    """Return 'up', 'down', 'enter', 'esc', or a single character."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right", "G": "home", "O": "end"}.get(code, "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            return "esc"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode(errors="ignore")
        if ch == "\x1b":
            seq = ""
            while select.select([fd], [], [], 0.03)[0]:
                seq += os.read(fd, 1).decode(errors="ignore")
            if not seq:
                return "esc"
            return {"[A": "up", "[B": "down", "[C": "right", "[D": "left", "OA": "up", "OB": "down", "[H": "home", "[F": "end"}.get(seq, "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def pause(msg: str = "Press any key to return to the menu") -> None:
    print()
    print("  " + tui.dim(msg + "…"))
    try:
        if interactive():
            read_key()
        else:
            input()
    except (EOFError, KeyboardInterrupt):
        pass


def ask(question: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        ans = tui.prompt(f"{question} {tui.dim(suffix)}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return default if not ans else ans in ("y", "yes")


# ----------------------------------------------------------------------------- status
def _status(ctx: Any) -> list[str]:
    uni = tui._unicode_ok()
    dot_on, dot_off = ("●", "○") if uni else ("*", "o")
    acc = ctx.accounts.first()
    signed = ctx.auth.has_session() or getattr(ctx, "_fixed_gateway", None) is not None
    rows: list[tuple[str, str]] = []
    if signed:
        name = (acc["display_name"] if acc else None) or "Telegram account"
        user = f" @{acc['username']}" if acc and acc["username"] else ""
        rows.append(("Account", tui.teal(f"{dot_on} ", True) + name + tui.dim(user)))
    else:
        rows.append(("Account", out.c(f"{dot_off} ", "33") + "not signed in " + tui.dim("– choose 1 to start")))
    aid = ctx.account_id
    total = ctx.messages.total(aid) if aid else 0
    rows.append(("Archive", f"{total:,} messages indexed"))
    last = None
    if aid:
        st = ctx.sync_state.get(aid)
        last = max(st.get("last_incremental") or 0, st.get("last_full_sync") or 0) or None
    rows.append(("Last sync", datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M") if last else "never"))
    net = ctx.config.settings.network
    rows.append(("Network", f"proxy {net.describe()}" if net.enabled else "direct connection"))
    return [tui.dim(k.ljust(11)) + v for k, v in rows]


def render(ctx: Any, selected: int) -> None:
    tui.clear()
    tui.banner()
    tui.panel("Status", _status(ctx), tone="accent")
    uni = tui._unicode_ok()
    pointer = "›" if uni else ">"
    for i, (key, label, desc) in enumerate(MENU):
        if key == "0":
            print()
        body = f" {key}  {label.ljust(20)} "
        tail = " " + tui.dim(desc) if desc else ""
        if i == selected:
            body = f"\033[7m{body}\033[27m" if out._COLOR else body
            print(f"  {tui.accent(pointer)} {tui.accent(body)}{tail}")
        else:
            print(f"    {tui.dim(body[:3])}{body[3:]}{tail}")
    print()
    arrows = "↑/↓" if uni else "Up/Down"
    print("  " + tui.dim(f"{arrows} move · Enter select · 0-8 shortcut · Esc quit"))


# ----------------------------------------------------------------------------- actions
def _ns(**kw: Any) -> argparse.Namespace:
    base = {"demo": os.environ.get("ARCIVO_DEMO") == "1", "verbose": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _header(title: str) -> None:
    tui.clear()
    tui.banner()
    print("  " + tui.accent(title))
    print()


def act_login(ctx: Any) -> None:
    from .main import cmd_login
    if ctx.auth.has_session():
        acc = ctx.accounts.first()
        _header("Sign in")
        tui.note(f"You're already signed in{' as ' + acc['display_name'] if acc else ''}.")
        if not ask("Sign in again (replaces the current session)?"):
            return
    cmd_login(_ns(api_id=None, phone=None, reset_api=False, open_gui=False, from_menu=True))
    pause()


def gui_command() -> list[str]:
    """Command that starts the windowed desktop app (frozen build or source checkout)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for name in ("ArcivoDashboard.exe", "ArcivoDashboard", "Arcivo Dashboard.exe"):
            cand = exe_dir / name
            if cand.exists():
                return [str(cand)]
        return [sys.executable, "gui"]
    py = Path(sys.executable)
    if os.name == "nt":
        pyw = py.with_name("pythonw.exe")
        if pyw.exists():
            py = pyw
    return [str(py), "-m", "arcivo.gui.app"]


def launch_gui(extra: list[str] | None = None) -> bool:
    cmd = gui_command() + (extra or [])
    kw: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kw)
        return True
    except OSError as exc:
        out.err(f"Could not start the dashboard: {exc}")
        return False


def act_dashboard(ctx: Any) -> None:
    _header("Open dashboard")
    if launch_gui(["--demo"] if os.environ.get("ARCIVO_DEMO") == "1" else None):
        tui.success("The dashboard is opening in a new window.")
        tui.note("You can keep using this console – or close it, the dashboard keeps running.")
    pause()


def act_doctor(ctx: Any) -> None:
    from .doctor import run_checks
    from .main import run
    _header("Check connection")
    tui.note("Testing each step of the route from this computer to Telegram…")
    print()
    try:
        run(run_checks(ctx))
    finally:
        ctx.auth.reset_gateway()
    pause()


def act_sync(ctx: Any) -> None:
    from .main import cmd_sync
    _header("Sync now")
    if not ctx.auth.has_session() and os.environ.get("ARCIVO_DEMO") != "1":
        tui.error("You're not signed in yet. Choose 1 · Sign in first.")
    else:
        cmd_sync(_ns(mode="auto"))
    pause()


def act_status(ctx: Any) -> None:
    from .main import cmd_status
    _header("Account & storage")
    tui.note("Contacting Telegram for live session details (offline values are shown if that fails)…")
    print()
    cmd_status(_ns(json=False))
    pause()


def act_proxy(ctx: Any) -> None:
    from ..telegram.proxy import parse_proxy_link
    cfg = ctx.config
    while True:
        cfg.load()
        n = cfg.settings.network
        _header("Proxy settings")
        tui.panel("Current", [
            tui.dim("Type      ") + (n.proxy_type if n.enabled else "none (direct connection)"),
            tui.dim("Server    ") + (f"{n.proxy_host}:{n.proxy_port}" if n.enabled else "—"),
            tui.dim("Login     ") + (n.proxy_username or "—"),
            "",
            tui.dim("Useful when Telegram is blocked or slow on your network. Applies to the console and the dashboard."),
        ])
        for key, label in (("1", "SOCKS5 proxy"), ("2", "HTTP proxy"), ("3", "MTProto proxy (Telegram)"),
                           ("4", "Paste a proxy link (tg://proxy, t.me/proxy, socks5://)"), ("5", "Turn proxy off"),
                           ("6", "Test connection"), ("0", "Back")):
            print(f"    {tui.dim(key)}  {label}")
        print()
        choice = _choice("0123456")
        if choice in ("0", "esc"):
            return
        try:
            if choice in ("1", "2", "3"):
                kind = {"1": "socks5", "2": "http", "3": "mtproto"}[choice]
                host = tui.prompt("Server (host or IP)").strip()
                port = int(tui.prompt("Port").strip() or "0")
                n.proxy_type, n.proxy_host, n.proxy_port = kind, host, port
                if kind == "mtproto":
                    n.proxy_secret = tui.prompt("Secret", secret=True, hint="(hex, hidden)").strip()
                    n.proxy_username = n.proxy_password = ""
                else:
                    n.proxy_username = tui.prompt("Username", hint="(optional)").strip()
                    n.proxy_password = tui.prompt("Password", secret=True, hint="(optional, hidden)").strip() if n.proxy_username else ""
                    n.proxy_secret = ""
                cfg.save()
                tui.success(f"Saved: {n.describe()}")
                pause("Press any key")
            elif choice == "4":
                data = parse_proxy_link(tui.prompt("Link"))
                if not data:
                    tui.error("That link wasn't recognised.")
                else:
                    for k, v in data.items():
                        setattr(n, k, v)
                    cfg.save()
                    tui.success(f"Saved: {n.describe()}")
                pause("Press any key")
            elif choice == "5":
                n.proxy_type = "none"
                cfg.save()
                tui.success("Proxy turned off – Arcivo connects directly.")
                pause("Press any key")
            elif choice == "6":
                act_doctor(ctx)
        except ValueError:
            tui.error("The port must be a number.")
            pause("Press any key")
        except (EOFError, KeyboardInterrupt):
            return


def act_logout(ctx: Any) -> None:
    from .main import cmd_logout
    _header("Sign out")
    if not ctx.auth.has_session():
        tui.note("You're not signed in.")
        pause()
        return
    tui.note("This removes the session from this computer and ends it on Telegram's servers.")
    tui.note("Your local archive (index) is kept.")
    print()
    if ask("Sign out now?"):
        cmd_logout(_ns(yes=True, local_only=False, forget_api=False))
    pause()


def act_about(ctx: Any) -> None:
    _header("About & privacy")
    tui.panel(f"{APP_NAME} {__version__}", [
        "A local-first archive manager for your Telegram Saved Messages:",
        "search, organise, analyse storage, export and tidy up – fast.",
        "",
        tui.teal("Privacy", True),
        "• Your index lives only on this computer (SQLite database).",
        "• No servers, no accounts, no telemetry, no analytics.",
        "• Arcivo talks only to Telegram, with your own API key.",
        "• Session & keys are kept in the OS credential vault.",
        "• Nothing is deleted without a preview and your confirmation.",
        "",
        tui.dim("Unofficial app – not affiliated with Telegram. Uses the official Telegram API."),
        "",
        tui.dim("Developer  ") + tui.teal(AUTHOR, True),
        tui.dim("Telegram   ") + tui.link(TELEGRAM_URL),
        tui.dim("Source     ") + tui.link(REPO_URL),
        tui.dim("Data       ") + str(ctx.paths.data_dir),
    ])
    pause()


ACTIONS = {"1": act_login, "2": act_dashboard, "3": act_doctor, "4": act_sync, "5": act_status, "6": act_proxy, "7": act_logout,
           "8": act_about}


def _choice(valid: str) -> str:
    if not interactive():
        try:
            return input("  Choose: ").strip()[:1] or "0"
        except EOFError:
            return "0"
    while True:
        k = read_key()
        if k in ("esc", "q", "Q"):
            return "esc"
        if k in valid:
            return k


def run_menu(ctx_factory: Any = None) -> int:
    from ..context import AppContext
    tui.set_title(f"{APP_NAME} {__version__}")
    if os.environ.get("ARCIVO_DEMO") == "1":
        from .main import demo_context
        ctx = demo_context()
    else:
        ctx = (ctx_factory or AppContext)()
    selected = 0
    try:
        while True:
            ctx.config.load()
            render(ctx, selected)
            key = read_key() if interactive() else _choice("012345678")
            if key == "up":
                selected = (selected - 1) % len(MENU)
                continue
            if key == "down":
                selected = (selected + 1) % len(MENU)
                continue
            if key == "home":
                selected = 0
                continue
            if key == "end":
                selected = len(MENU) - 1
                continue
            if key == "enter":
                key = MENU[selected][0]
            if key in ("esc", "q", "Q", "0"):
                break
            action = ACTIONS.get(key)
            if action is None:
                continue
            selected = next(i for i, m in enumerate(MENU) if m[0] == key)
            try:
                action(ctx)
            except KeyboardInterrupt:
                print()
                tui.note("Cancelled.")
                pause()
            except ArcivoError as exc:
                tui.error(f"{exc}")
                pause()
            except Exception as exc:  # keep the console alive whatever happens
                import logging
                logging.getLogger(__name__).exception("Menu action failed")
                tui.error(f"Something went wrong: {exc}")
                pause()
            ctx.auth.reset_gateway()  # fresh connection (and proxy settings) for the next action
    except KeyboardInterrupt:
        pass
    finally:
        tui.clear()
        print("  " + tui.accent(f"Thanks for using {APP_NAME}.") + "  " + tui.dim(f"{TELEGRAM_URL} · {REPO_URL}"))
        print()
    return 0
