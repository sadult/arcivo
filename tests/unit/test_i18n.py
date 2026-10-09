"""Every user-facing string must exist in the catalog."""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest

from arcivo.core import errors
from arcivo.core.config import DEFAULT_SHORTCUTS
from arcivo.domain.models import Category, MediaType
from arcivo.i18n.translator import Translator, load_catalog
from arcivo.jobs.manager import JobStatus

SRC = Path(__file__).resolve().parents[2] / "src" / "arcivo"
KEY_RE = re.compile(r"""(?:\bt|\btr|self\.t|gui\.t|T\(\))\(\s*["']([a-z_]+\.[a-zA-Z0-9_.]+)["']""")


def used_keys() -> set[str]:
    keys: set[str] = set()
    for p in SRC.rglob("*.py"):
        keys |= set(KEY_RE.findall(p.read_text(encoding="utf-8")))
    return keys


def fields(s: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


EN = load_catalog("en")


@pytest.mark.parametrize("key", sorted(used_keys()))
def test_static_keys_exist(key: str) -> None:
    assert key in EN, f"missing en key {key}"


def test_dynamic_families_complete() -> None:
    expected = {f"types.{m.value}" for m in MediaType} | {f"categories.{c.value}" for c in Category}
    expected |= {f"jobs.status_{s.value}" for s in JobStatus} | {f"shortcuts.{a}" for a in DEFAULT_SHORTCUTS}
    expected |= {f"common.weekday_{i}" for i in range(7)}
    codes = {c.code for c in vars(errors).values() if isinstance(c, type) and issubclass(c, errors.ArcivoError)}
    expected |= {f"errors.{c}" for c in codes}
    from arcivo.gui.main_window import NAV
    for section, items in NAV:
        expected.add(f"nav.section_{section}")
        for key, _icon in items:
            expected |= {f"nav.{key}", f"{key}.subtitle"}
    missing = sorted(expected - set(EN))
    assert not missing, missing


def test_number_formatting() -> None:
    t = Translator("en")
    assert t.num(1234) == "1,234"
    assert t("explorer.results_n", n=1200) == "1,200 results"
    assert t.bucket_label("2026-03") == "Mar 2026"
