"""Locale-independent formatting & parsing helpers (sizes, durations, dates)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

_UNITS = {"b": 1, "kb": 1024, "k": 1024, "mb": 1024**2, "m": 1024**2, "gb": 1024**3, "g": 1024**3, "tb": 1024**4}
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?b?)?\s*$", re.I)
_DUR_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?$", re.I)

TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_size(text: str) -> int:
    m = _SIZE_RE.match(text.translate(TO_ASCII_DIGITS))
    if not m:
        raise ValueError(f"invalid size: {text!r}")
    unit = (m.group(2) or "b").lower()
    return int(float(m.group(1)) * _UNITS[unit])


def human_size(n: int | float | None, digits: int = 1) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.{digits}f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def parse_duration(text: str) -> float:
    t = text.strip().lower().translate(TO_ASCII_DIGITS)
    if ":" in t:
        parts = [float(p) for p in t.split(":")]
        total = 0.0
        for p in parts:
            total = total * 60 + p
        return total
    m = _DUR_RE.match(t)
    if not m or not any(m.groups()):
        raise ValueError(f"invalid duration: {text!r}")
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = round(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def ts_to_dt(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


def parse_date(text: str) -> tuple[date, date]:
    """Parse ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` into an inclusive (start, end) range."""
    t = text.strip().translate(TO_ASCII_DIGITS).replace("/", "-")
    parts = t.split("-")
    try:
        if len(parts) == 1:
            y = int(parts[0])
            return date(y, 1, 1), date(y, 12, 31)
        if len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
            nxt = date(y + (m // 12), m % 12 + 1, 1)
            return date(y, m, 1), date.fromordinal(nxt.toordinal() - 1)
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return d, d
    except (ValueError, IndexError) as exc:
        raise ValueError(f"invalid date: {text!r}") from exc
