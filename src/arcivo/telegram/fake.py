"""In-memory gateway used by tests, CI and the offline demo mode."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from ..core.errors import DownloadError, NetworkError, NotAuthenticatedError, RateLimitError
from ..domain.models import AccountInfo, MessageRecord
from .gateway import ConnectionInfo, ProgressCallback


class FakeGateway:
    def __init__(self, records: list[MessageRecord] | None = None, *, authorized: bool = True,
                 me: AccountInfo | None = None) -> None:
        self.records: dict[int, MessageRecord] = {r.id: r for r in (records or [])}
        self.authorized = authorized
        self.me = me or AccountInfo(user_id=777000001, first_name="Demo", last_name="User", username="arcivo_demo",
                                    phone="989120000000", dc_id=4)
        self.connected = False
        self.fail_next: list[BaseException] = []  # exceptions injected into the next calls
        self.deleted: list[int] = []
        self.calls: list[str] = []
        self.fail_delete_ids: set[int] = set()
        self.files: dict[int, bytes] = {}

    def _maybe_fail(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_next:
            raise self.fail_next.pop(0)

    async def connect(self) -> None:
        self._maybe_fail("connect")
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def is_authorized(self) -> bool:
        return self.authorized

    async def get_me(self) -> AccountInfo:
        if not self.authorized:
            raise NotAuthenticatedError()
        return self.me

    async def connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(connected=self.connected, dc_id=self.me.dc_id, server="149.154.167.91", port=443, layer=229,
                              library="FakeGateway", latency_ms=42.0)

    async def history(self, *, min_id: int = 0, batch: int = 100, delay: float = 0.0) -> AsyncIterator[list[MessageRecord]]:
        ids = sorted(i for i in self.records if i > min_id)
        for i in range(0, len(ids), batch):
            self._maybe_fail("history")
            yield [self.records[x] for x in ids[i:i + batch]]
            await asyncio.sleep(0)

    async def get_by_ids(self, ids: list[int]) -> dict[int, MessageRecord | None]:
        self._maybe_fail("get_by_ids")
        return {i: self.records.get(i) for i in ids}

    async def delete(self, ids: list[int]) -> list[int]:
        self._maybe_fail("delete")
        bad = [i for i in ids if i in self.fail_delete_ids]
        if bad:
            raise NetworkError("injected delete failure")
        for i in ids:
            self.records.pop(i, None)
        self.deleted.extend(ids)
        return list(ids)

    def _payload(self, message_id: int) -> bytes:
        if message_id in self.files:
            return self.files[message_id]
        r = self.records.get(message_id)
        if r is None or not r.has_file:
            raise DownloadError("no media")
        size = min(r.file_size or 1024, 256 * 1024)  # keep demo/test downloads small
        return (f"ARCIVO-FAKE-{message_id}-".encode() * (size // 16 + 1))[:size]

    async def download(self, message_id: int, dest: Path, *, offset: int = 0, progress: ProgressCallback | None = None,
                       pause_check: Callable[[], Awaitable[None]] | None = None) -> int:
        self._maybe_fail("download")
        data = self._payload(message_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = offset
        with open(dest, "ab" if offset else "wb") as fh:
            for i in range(offset, len(data), 64 * 1024):
                if pause_check:
                    await pause_check()
                chunk = data[i:i + 64 * 1024]
                fh.write(chunk)
                written += len(chunk)
                if progress:
                    r = progress(written, len(data))
                    if asyncio.iscoroutine(r):
                        await r
                await asyncio.sleep(0)
        return written

    async def download_thumbnail(self, message_id: int) -> bytes | None:
        """Procedural gradient preview (PPM) so the demo media grid has imagery."""
        rec = self.records.get(message_id)
        if rec is None or rec.media_type not in ("photo", "video", "animation", "video_note"):
            return None
        return _gradient_ppm(message_id)

    def expected_size(self, message_id: int) -> int:
        return len(self._payload(message_id))


def flood(seconds: int) -> RateLimitError:
    return RateLimitError("injected flood", retry_after=float(seconds))


_HUES = [(124, 131, 253), (54, 194, 180), (245, 165, 36), (242, 84, 91), (76, 141, 255), (176, 106, 255), (43, 182, 115)]


def _gradient_ppm(seed: int, w: int = 120, h: int = 90) -> bytes:
    a = _HUES[seed % len(_HUES)]
    b = _HUES[(seed * 7 + 3) % len(_HUES)]
    out = bytearray(f"P6 {w} {h} 255\n".encode())
    cx, cy = (seed * 37) % w, (seed * 53) % h
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            glow = max(0.0, 1 - (((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) / 70)
            out += bytes(min(255, int(a[i] * (1 - t) + b[i] * t + 60 * glow)) for i in range(3))
    return bytes(out)
