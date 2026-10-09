"""Search facade: syntax parsing, compilation, counting and paging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo

from ..core.errors import SearchSyntaxError
from ..repositories.messages import MessageRepository
from ..search.query import ParsedQuery, parse
from ..search.sql import CompiledQuery, SqlBuilder


@dataclass
class SearchSpec:
    """Structured filters from the UI, merged with the free-form query."""

    query: str = ""
    types: list[str] | None = None
    tags: list[str] | None = None
    sender: str | None = None
    chat: str | None = None
    ext: list[str] | None = None
    after: str | None = None
    before: str | None = None
    min_size: str | None = None
    max_size: str | None = None
    min_duration: str | None = None
    max_duration: str | None = None
    flagged: bool = False
    sort_key: str = "date"
    sort_desc: bool = True

    def to_query(self) -> str:
        def q(v: str) -> str:
            return f'"{v}"' if any(c.isspace() for c in v) else v

        parts = [self.query.strip()] if self.query.strip() else []
        if self.types:
            parts.append("type:" + ",".join(self.types))
        if self.tags:
            parts.append("tag:" + ",".join(q(t) for t in self.tags))
        if self.sender:
            parts.append(f"sender:{q(self.sender)}")
        if self.chat:
            parts.append(f"chat:{q(self.chat)}")
        if self.ext:
            parts.append("ext:" + ",".join(self.ext))
        if self.after:
            parts.append(f"after:{self.after}")
        if self.before:
            parts.append(f"before:{self.before}")
        if self.min_size or self.max_size:
            parts.append(f"size:{self.min_size or ''}..{self.max_size or ''}")
        if self.min_duration or self.max_duration:
            parts.append(f"duration:{self.min_duration or ''}..{self.max_duration or ''}")
        if self.flagged:
            parts.append("is:flagged")
        return " ".join(parts)


class SearchService:
    def __init__(self, repo: MessageRepository, tz: tzinfo | None = None) -> None:
        self.repo = repo
        self.builder = SqlBuilder(tz)

    def compile(self, query: str, sort_key: str = "date", sort_desc: bool = True) -> CompiledQuery:
        pq: ParsedQuery = parse(query or "")
        return self.builder.compile(pq, sort_key, sort_desc)

    def validate(self, query: str) -> str | None:
        try:
            self.compile(query)
            return None
        except SearchSyntaxError as exc:
            return str(exc)

    def count(self, account_id: int, query: str) -> int:
        return self.repo.count(account_id, self.compile(query))

    def page(self, account_id: int, query: str, offset: int, limit: int, sort_key: str = "date", sort_desc: bool = True):  # type: ignore[no-untyped-def]
        return self.repo.page(account_id, self.compile(query, sort_key, sort_desc), offset, limit)

    def ids(self, account_id: int, query: str, sort_key: str = "date", sort_desc: bool = True) -> list[int]:
        return self.repo.ids(account_id, self.compile(query, sort_key, sort_desc))
