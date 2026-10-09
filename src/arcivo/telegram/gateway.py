"""Backend-agnostic contract for everything Arcivo needs from Telegram.

Services depend on this protocol only. ``TelethonGateway`` implements it on
top of the official MTProto API; ``FakeGateway`` implements it in memory for
tests and the offline demo. A future remote/server backend can implement the
same protocol (e.g. an RPC proxy) without touching services or UI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..domain.models import AccountInfo, MessageRecord

ProgressCallback = Callable[[int, int | None], Awaitable[None] | None]


@dataclass
class ConnectionInfo:
    connected: bool
    dc_id: int | None = None
    server: str | None = None
    port: int | None = None
    layer: int | None = None
    library: str = ""
    latency_ms: float | None = None


@runtime_checkable
class TelegramGateway(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def is_authorized(self) -> bool: ...
    async def get_me(self) -> AccountInfo: ...
    async def connection_info(self) -> ConnectionInfo: ...

    def history(self, *, min_id: int = 0, batch: int = 100, delay: float = 0.5) -> AsyncIterator[list[MessageRecord]]:
        """Yield Saved Messages in ascending id order, in batches, starting after ``min_id``."""
        ...

    async def get_by_ids(self, ids: list[int]) -> dict[int, MessageRecord | None]: ...
    async def delete(self, ids: list[int]) -> list[int]:
        """Delete messages from Saved Messages; returns ids reported as deleted."""
        ...

    async def download(self, message_id: int, dest: Path, *, offset: int = 0, progress: ProgressCallback | None = None,
                       pause_check: Callable[[], Awaitable[None]] | None = None) -> int:
        """Stream a message's media into ``dest`` (appending from ``offset``); returns total bytes."""
        ...

    async def download_thumbnail(self, message_id: int) -> bytes | None: ...
