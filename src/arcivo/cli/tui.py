"""Terminal UI building blocks: gradient banner, step indicator, panels, prompts, links.

Dependency-free (ANSI escapes only). Degrades gracefully: no colours when NO_COLOR is set or output
is redirected, and an ASCII-only banner when the console can't encode block characters.
"""

from __future__ import annotations

import getpass
import os
import shutil
import sys

from .. import APP_TAGLINE, AUTHOR, REPO_URL, TELEGRAM_URL, __version__
from . import output as out

BANNER = [
    " █████╗ ██████╗  ██████╗██╗██╗   ██╗ ██████╗ ",
    "██╔══██╗██╔══██╗██╔════╝██║██║   ██║██╔═══██╗",
    "███████║██████╔╝██║     ██║██║   ██║██║   ██║",
    "██╔══██║██╔══██╗██║     ██║╚██╗ ██╔╝██║   ██║",
    "██║  ██║██║  ██║╚██████╗██║ ╚████╔╝ ╚██████╔╝",
    "╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═══╝   ╚═════╝ ",
]
BANNER_ASCII = [
    "    _    ____   ____ _____     _____  ",
    "   / \\  |  _ \\ / ___|_ _\\ \\   / / _ \\ ",
    "  / _ \\ | |_) | |    | | \\ \\ / / | | |",
    " / ___ \\|  _ <| |___ | |  \\ V /| |_| |",
    "/_/   \\_\\_| \\_\\\\____|___|  \\_/  \\___/ ",
]
# brand gradient: primary #7C83FD → deep #5B5FEF → secondary #36C2B4
GRADIENT = [(124, 131, 253), (91, 95, 239), (54, 194, 180)]
STEPS = [("api", "API keys"), ("phone", "Phone"), ("code", "Code"), ("password", "2FA"), ("done", "Done")]


def _color() -> bool:
    return out._COLOR


def _unicode_ok() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "█╗✔●─╭".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _rgb(text: str, rgb: tuple[int, int, int], bold: bool = False) -> str:
    if not _color():
        return text
    r, g, b = rgb
    return f"\033[{'1;' if bold else ''}38;2;{r};{g};{b}m{text}\033[0m"


def _lerp(t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    seg = 0 if t < 0.5 else 1
    lt = t * 2 if seg == 0 else (t - 0.5) * 2
    a, b = GRADIENT[seg], GRADIENT[seg + 1]
    return tuple(round(a[i] + (b[i] - a[i]) * lt) for i in range(3))  # type: ignore[return-value]


def dim(text: str) -> str:
    return out.c(text, "2")


def accent(text: str, bold: bool = True) -> str:
    return _rgb(text, GRADIENT[0], bold)


def teal(text: str, bold: bool = False) -> str:
    return _rgb(text, GRADIENT[2], bold)


def clear() -> None:
    if not sys.stdout.isatty():
        return
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()


def _width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def banner() -> None:
    uni = _unicode_ok()
    art = BANNER if uni and _width() >= 50 else BANNER_ASCII
    pad = "  "
    print()
    for line in art:
        n = max(1, len(line) - 1)
        print(pad + "".join(_rgb(ch, _lerp(i / n), bold=True) if ch != " " else " " for i, ch in enumerate(line)))
    print(pad + accent(APP_TAGLINE, bold=False) + "  " + dim(f"v{__version__}"))
    dot = " · " if uni else " - "
    print(pad + dim("by ") + teal(AUTHOR, True) + dim(dot + "Telegram ") + link(TELEGRAM_URL, "t.me/Bitologist")
          + dim(dot) + link(REPO_URL, REPO_URL.removeprefix("https://")))
    print()


def link(url: str, text: str | None = None) -> str:
    """Clickable OSC-8 hyperlink where supported (Windows Terminal, iTerm2, GNOME…); plain text otherwise."""
    text = text or url
    styled = _rgb(text, (160, 165, 255))
    if not _color() or os.environ.get("ARCIVO_NO_HYPERLINKS"):
        return styled
    return f"\033]8;;{url}\033\\{styled}\033]8;;\033\\"


def set_title(title: str) -> None:
    if not sys.stdout.isatty():
        return
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def steps(current: str, skipped: set[str] | None = None) -> None:
    skipped = skipped or set()
    keys = [k for k, _ in STEPS]
    idx = keys.index(current)
    uni = _unicode_ok()
    done_m, cur_m, todo_m, sep = ("✔", "●", "○", " ── ") if uni else ("x", "*", "o", " -- ")
    parts = []
    for i, (key, label) in enumerate(STEPS):
        if key in skipped and i != idx:
            parts.append(dim(f"{'–'if uni else '-'} {label}"))
        elif i < idx:
            parts.append(teal(f"{done_m} {label}"))
        elif i == idx:
            parts.append(accent(f"{cur_m} {label}"))
        else:
            parts.append(dim(f"{todo_m} {label}"))
    print("  " + dim(sep).join(parts))
    print()


def panel(title: str, lines: list[str], tone: str = "accent") -> None:
    """Rounded box with a title; ``lines`` may contain ANSI codes (width computed on plain text)."""
    uni = _unicode_ok()
    tl, tr, bl, br, h, v = ("╭", "╮", "╰", "╯", "─", "│") if uni else ("+", "+", "+", "+", "-", "|")
    width = min(max(78, max((_plain_len(x) for x in lines), default=0) + 4, len(title) + 6), max(40, _width() - 4))
    paint = {"accent": accent, "teal": teal, "error": lambda s, bold=True: out.c(s, "1;31"),
             "warn": lambda s, bold=True: out.c(s, "1;33")}[tone]
    import textwrap
    wrapped: list[str] = []
    for line in lines:
        if _plain_len(line) > width - 4 and "\033" not in line:
            wrapped += textwrap.wrap(line, width - 4) or [""]
        else:
            wrapped.append(line)
    lines = wrapped
    top = f"{tl}{h} {title} " + h * max(0, width - len(title) - 5) + tr
    print("  " + paint(top, False))
    for line in lines:
        fill = " " * max(0, width - 4 - _plain_len(line))
        print("  " + paint(v, False) + " " + line + fill + " " + paint(v, False))
    print("  " + paint(bl + h * (width - 2) + br, False))
    print()


def _plain_len(s: str) -> int:
    import re

    s = re.sub(r"\033\]8;;[^\033]*\033\\", "", s)  # OSC-8 hyperlinks
    return out._w(re.sub(r"\033\[[0-9;]*m", "", s))


def prompt(label: str, secret: bool = False, hint: str = "") -> str:
    arrow = "›" if _unicode_ok() else ">"
    hint_s = f" {dim(hint)}" if hint else ""
    text = f"  {accent(arrow)} {out.c(label, '1')}{hint_s}: "
    if secret:
        return getpass.getpass(text)
    return input(text)


def note(msg: str) -> None:
    print("  " + dim(msg))


def error(msg: str) -> None:
    print("  " + out.c(("✖ " if _unicode_ok() else "x ") + msg, "31"))
    print()


def success(msg: str) -> None:
    print("  " + teal(("✔ " if _unicode_ok() else "OK ") + msg, bold=True))
