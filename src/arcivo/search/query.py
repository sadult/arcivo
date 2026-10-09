"""Arcivo search syntax → AST.

Grammar (informal)::

    query   := clause (("OR" | "|") clause | clause)*
    clause  := ["-"] (field ":" value | term)
    value   := word | "quoted text" | op number unit | range
    op      := > | >= | < | <= | =
    range   := A..B

Examples::

    invoice type:document ext:pdf chat:"Design Team" after:2026-01-01
    type:audio,voice size:>20MB sort:size
    -tag:archive has:link before:2025-06
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.errors import SearchSyntaxError
from ..domain.formatting import TO_ASCII_DIGITS

FIELD_ALIASES: dict[str, str] = {
    "type": "type", "t": "type", "kind": "type",
    "category": "category", "cat": "category",
    "sender": "sender", "from": "sender", "author": "sender", "user": "sender",
    "chat": "chat", "channel": "chat", "group": "chat", "in": "chat", "source": "chat",
    "ext": "ext", "extension": "ext",
    "mime": "mime",
    "before": "before", "after": "after", "on": "date", "date": "date", "during": "date",
    "size": "size",
    "duration": "duration", "dur": "duration", "length": "duration",
    "tag": "tag", "tags": "tag", "label": "tag",
    "has": "has", "is": "is",
    "filename": "filename", "name": "filename", "file": "filename",
    "text": "text", "caption": "text",
    "id": "id",
    "domain": "domain", "site": "domain",
    "sort": "sort", "order": "order",
    "width": "width", "height": "height",
}

SORT_FIELDS = {"date", "size", "name", "type", "sender", "chat", "duration", "id", "ext", "edited"}
_TOKEN_RE = re.compile(r'\s*(-?)(?:([A-Za-z_]+):("(?:[^"\\]|\\.)*"|\S*)|("(?:[^"\\]|\\.)*")|(\S+))')


@dataclass
class Clause:
    field: str  # canonical field name or "text*" for free text
    value: str
    negate: bool = False
    phrase: bool = False


@dataclass
class OrGroup:
    clauses: list[Clause | OrGroup] = field(default_factory=list)
    negate: bool = False


Node = Clause | OrGroup


@dataclass
class ParsedQuery:
    nodes: list[Node] = field(default_factory=list)
    sort_key: str | None = None
    sort_desc: bool | None = None
    raw: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.nodes

    def free_text(self) -> list[str]:
        out: list[str] = []

        def walk(n: Node) -> None:
            if isinstance(n, OrGroup):
                for c in n.clauses:
                    walk(c)
            elif n.field == "text*" and not n.negate:
                out.append(n.value)

        for n in self.nodes:
            walk(n)
        return out


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return re.sub(r"\\(.)", r"\1", s[1:-1])
    return s


def parse(query: str) -> ParsedQuery:
    result = ParsedQuery(raw=query)
    text = query.translate(TO_ASCII_DIGITS) if query else ""
    pos = 0
    pending_or = False
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        neg, fname, fval, quoted, word = m.groups()
        if fname is None and quoted is None and word is None:
            continue
        if word is not None and word in ("OR", "|") and not neg:
            if not result.nodes:
                raise SearchSyntaxError("OR without a left operand", position=m.start())
            pending_or = True
            continue
        node: Clause | None = None
        if fname is not None:
            canonical = FIELD_ALIASES.get(fname.lower())
            if canonical is None:
                node = Clause("text*", f"{fname}:{fval}", negate=bool(neg))
            else:
                value = _unquote(fval)
                if value == "":
                    raise SearchSyntaxError(f"missing value for '{fname}:'", position=m.start(), field=fname)
                if canonical == "sort":
                    _apply_sort(result, value)
                    continue
                if canonical == "order":
                    if value.lower() not in ("asc", "desc"):
                        raise SearchSyntaxError("order must be asc or desc", field="order")
                    result.sort_desc = value.lower() == "desc"
                    continue
                node = Clause(canonical, value, negate=bool(neg), phrase=fval.startswith('"'))
        elif quoted is not None:
            node = Clause("text*", _unquote(quoted), negate=bool(neg), phrase=True)
        else:
            node = Clause("text*", word, negate=bool(neg))
        if pending_or and result.nodes:
            prev = result.nodes.pop()
            if isinstance(prev, OrGroup) and not prev.negate:
                prev.clauses.append(node)
                result.nodes.append(prev)
            else:
                result.nodes.append(OrGroup([prev, node]))
            pending_or = False
        else:
            result.nodes.append(node)
    if pending_or:
        raise SearchSyntaxError("OR without a right operand")
    return result


def _apply_sort(result: ParsedQuery, value: str) -> None:
    v = value.lower()
    desc: bool | None = None
    for suffix, d in (("-desc", True), ("-asc", False), (":desc", True), (":asc", False)):
        if v.endswith(suffix):
            v, desc = v[: -len(suffix)], d
    if v not in SORT_FIELDS:
        raise SearchSyntaxError(f"unknown sort field '{value}'", field="sort")
    result.sort_key = v
    if desc is not None:
        result.sort_desc = desc
