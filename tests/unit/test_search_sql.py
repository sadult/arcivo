from datetime import UTC

import pytest

from arcivo.core.errors import SearchSyntaxError
from arcivo.search.query import parse
from arcivo.search.sql import SqlBuilder


def compile_(q):
    return SqlBuilder(UTC).compile(parse(q))


def test_size_and_dates():
    cq = compile_("size:>50MB before:2026-01-01 after:2025-06")
    assert "file_size > ?" in cq.where and "date_ts < ?" in cq.where and "date_ts >= ?" in cq.where
    assert cq.params[0] == 50 * 1024**2
    assert cq.params[1] == 1767225600  # 2026-01-01T00:00Z
    assert cq.params[2] == 1748736000  # 2025-06-01T00:00Z


def test_ranges():
    cq = compile_("size:1MB..10MB duration:1:30..5m id:10..20")
    assert cq.params == [1024**2, 10 * 1024**2, 90.0, 300.0, 10, 20]


def test_injection_safe():
    cq = compile_("sender:\"x'; DROP TABLE messages; --\"")
    assert "DROP" not in cq.where
    assert any("DROP" in str(p) for p in cq.params)


def test_unknown_type():
    with pytest.raises(SearchSyntaxError):
        compile_("type:hologram")


def test_invalid_size():
    with pytest.raises(SearchSyntaxError):
        compile_("size:>lots")


def test_order_clause():
    cq = compile_("sort:size")
    assert cq.order_by.startswith("(m.file_size IS NULL), m.file_size DESC")
