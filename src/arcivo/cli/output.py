"""Minimal, dependency-free terminal output helpers (tables, colours, prompts)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import unicodedata
from typing import Any

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if os.name == "nt" and _COLOR:
    os.system("")  # enable VT100 escape processing on Windows 10+


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def ok(msg: str) -> None:
    print(c("✔ ", "32") + msg)


def warn(msg: str) -> None:
    print(c("! ", "33") + msg, file=sys.stderr)


def err(msg: str) -> None:
    print(c("✖ ", "31") + msg, file=sys.stderr)


def title(msg: str) -> None:
    print(c(msg, "1;35"))


def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 0 if unicodedata.combining(ch) else 1 for ch in s)


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_width: int | None = None) -> None:
    if not rows:
        print(c("(no results)", "2"))
        return
    max_width = max_width or shutil.get_terminal_size((120, 20)).columns
    cells = [[("" if r.get(k) is None else str(r.get(k))).replace("\n", " ") for k, _ in columns] for r in rows]
    widths = [max(_w(h), *(_w(row[i]) for row in cells)) for i, (_, h) in enumerate(columns)]
    while sum(widths) + 2 * len(widths) > max_width and max(widths) > 12:
        widths[widths.index(max(widths))] -= 1

    def fit(s: str, w: int) -> str:
        if _w(s) > w:
            while _w(s) > w - 1:
                s = s[:-1]
            s += "…"
        return s + " " * (w - _w(s))

    print(c("  ".join(fit(h, widths[i]) for i, (_, h) in enumerate(columns)), "1"))
    print(c("  ".join("─" * w for w in widths), "2"))
    for row in cells:
        print("  ".join(fit(v, widths[i]) for i, v in enumerate(row)))


def dump_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def progress_line(text: str) -> None:
    if sys.stdout.isatty():
        width = shutil.get_terminal_size((100, 20)).columns
        sys.stdout.write("\r" + text[: width - 1].ljust(width - 1))
        sys.stdout.flush()


def bar(fraction: float, width: int = 28) -> str:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return c("█" * filled, "35") + c("░" * (width - filled), "2")
