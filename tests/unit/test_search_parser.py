import pytest

from arcivo.core.errors import SearchSyntaxError
from arcivo.search.query import Clause, OrGroup, parse


def test_free_text_and_fields():
    q = parse('invoice type:document ext:pdf chat:"Design Team" -tag:archive')
    kinds = [(n.field, n.value, n.negate) for n in q.nodes]
    assert kinds == [("text*", "invoice", False), ("type", "document", False), ("ext", "pdf", False),
                     ("chat", "Design Team", False), ("tag", "archive", True)]


def test_or_groups():
    q = parse("type:audio OR type:voice report")
    assert isinstance(q.nodes[0], OrGroup)
    assert [c.value for c in q.nodes[0].clauses] == ["audio", "voice"]
    assert isinstance(q.nodes[1], Clause)


def test_sort_and_order():
    q = parse("type:video sort:size-asc")
    assert q.sort_key == "size" and q.sort_desc is False
    q = parse("sort:duration order:desc")
    assert q.sort_key == "duration" and q.sort_desc is True


def test_persian_digits_and_phrase():
    q = parse('"یادداشت مهم" after:۲۰۲۶-۰۱-۰۱')
    assert q.nodes[0].phrase and q.nodes[0].value == "یادداشت مهم"
    assert q.nodes[1].value == "2026-01-01"


def test_unknown_field_is_text():
    q = parse("https://example.com")
    assert q.nodes[0].field == "text*"


@pytest.mark.parametrize("bad", ["type:", "OR foo", "foo OR", "sort:banana", "order:sideways"])
def test_errors(bad):
    with pytest.raises(SearchSyntaxError):
        parse(bad)
