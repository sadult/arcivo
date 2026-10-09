"""Lightweight, JSON-based string catalog.

All user-facing text lives in ``i18n/locales/en.json`` as nested objects; keys
are addressed with dots (``dashboard.title``). Missing keys are logged once and
rendered from the key name. ``{name}`` placeholders are formatted with kwargs
and numbers get thousands separators.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

from ..domain.formatting import human_duration, human_size

log = logging.getLogger(__name__)
LANGUAGES = {"en": "English"}


@lru_cache(maxsize=8)
def load_catalog(lang: str) -> dict[str, str]:
    raw = json.loads(resources.files("arcivo.i18n.locales").joinpath(f"{lang}.json").read_text(encoding="utf-8"))
    flat: dict[str, str] = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        else:
            flat[prefix] = str(node)

    walk("", raw)
    return flat


class Translator:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang if lang in LANGUAGES else "en"
        self._cat = load_catalog(self.lang)
        self._missing: set[str] = set()

    def __call__(self, key: str, **kw: Any) -> str:
        text = self._cat.get(key)
        if text is None:
            if key not in self._missing:
                self._missing.add(key)
                log.debug("Missing translation key %s", key)
            text = key.rsplit(".", 1)[-1].replace("_", " ")
        if kw:
            safe = {k: (self.num(v) if isinstance(v, int | float) and not isinstance(v, bool) else v) for k, v in kw.items()}
            try:
                text = text.format(**safe)
            except (KeyError, IndexError, ValueError):
                pass
        return text

    def has(self, key: str) -> bool:
        return key in self._cat

    # ---- formatting
    def num(self, n: int | float | None) -> str:
        if n is None:
            return "—"
        return f"{n:,}" if isinstance(n, int) else f"{n:,.1f}"

    def size(self, n: int | float | None) -> str:
        return human_size(n)

    def duration(self, s: float | None) -> str:
        return human_duration(s)

    def date(self, ts: int | float | None, with_time: bool = False) -> str:
        if not ts:
            return "—"
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")

    def date_long(self, ts: int | float) -> str:
        return datetime.fromtimestamp(ts).strftime("%d %B %Y").lstrip("0")

    def bucket_label(self, bucket: str) -> str:
        """Human label for a timeline bucket such as ``2026-03`` (month) or ``2026-03-14`` (day)."""
        try:
            if len(bucket) == 7:
                return datetime.strptime(bucket, "%Y-%m").strftime("%b %Y")
            if len(bucket) == 10:
                return datetime.strptime(bucket, "%Y-%m-%d").strftime("%b %d").replace(" 0", " ")
        except ValueError:
            pass
        return bucket

    def relative(self, ts: int | float | None) -> str:
        if not ts:
            return self("common.never")
        delta = datetime.now().timestamp() - ts
        if delta < 60:
            return self("common.just_now")
        if delta < 3600:
            return self("common.minutes_ago", n=int(delta // 60))
        if delta < 86400:
            return self("common.hours_ago", n=int(delta // 3600))
        return self("common.days_ago", n=int(delta // 86400))


_current = Translator("en")


def set_translator(t: Translator) -> None:
    global _current
    _current = t


def tr(key: str, **kw: Any) -> str:
    return _current(key, **kw)


def T() -> Translator:
    return _current
