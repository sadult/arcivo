"""TelegramGateway implementation using Telethon (official MTProto API)."""

from __future__ import annotations

import asyncio
import logging
import platform
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from .. import __version__
from ..core.errors import DownloadError, NotAuthenticatedError
from ..domain.models import AccountInfo, MessageRecord
from .backoff import translate, with_retry
from .gateway import ConnectionInfo, ProgressCallback
from .mapper import to_record

log = logging.getLogger(__name__)
REQUEST_SIZE = 512 * 1024  # max chunk allowed by upload.getFile


class TelethonGateway:
    def __init__(self, api_id: int, api_hash: str, session_string: str | None = None, *, lang_code: str = "en",
                 max_flood_wait: float = 900, on_session_changed: Callable[[str], None] | None = None,
                 network: Any = None) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        from .proxy import telethon_proxy_kwargs

        self._session = StringSession(session_string or None)
        self.client = TelegramClient(
            self._session, api_id, api_hash,
            device_model="Arcivo Desktop", system_version=platform.system() or "Windows", app_version=__version__,
            lang_code=lang_code, system_lang_code=lang_code,
            flood_sleep_threshold=0,  # Arcivo handles FLOOD_WAIT itself (see backoff.with_retry)
            request_retries=3, connection_retries=5, retry_delay=2, auto_reconnect=True,
            receive_updates=False,  # we only need request/response; avoids background update traffic
            **telethon_proxy_kwargs(network),
        )
        self.proxy_description = network.describe() if network is not None else "none"
        self.max_flood_wait = max_flood_wait
        self._on_session_changed = on_session_changed
        self._me: Any = None

    # ------------------------------------------------------------------ session
    def session_string(self) -> str:
        return self.client.session.save()

    def _persist_session(self) -> None:
        if self._on_session_changed:
            try:
                self._on_session_changed(self.session_string())
            except Exception:
                log.exception("Could not persist session")

    async def _call(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        return await with_retry(fn, max_flood_wait=self.max_flood_wait)

    # ------------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        try:
            if not self.client.is_connected():
                await self.client.connect()
        except BaseException as exc:
            raise translate(exc) from exc

    async def disconnect(self) -> None:
        if self.client.is_connected():
            self._persist_session()
            await self.client.disconnect()

    async def is_authorized(self) -> bool:
        await self.connect()
        try:
            return bool(await self.client.is_user_authorized())
        except BaseException as exc:
            raise translate(exc) from exc

    async def _require_me(self) -> Any:
        if self._me is None:
            if not await self.is_authorized():
                raise NotAuthenticatedError()
            self._me = await self._call(lambda: self.client.get_me())
        return self._me

    async def get_me(self) -> AccountInfo:
        me = await self._require_me()
        return AccountInfo(user_id=me.id, first_name=me.first_name or "", last_name=me.last_name or "",
                           username=me.username, phone=me.phone, is_premium=bool(getattr(me, "premium", False)),
                           dc_id=self.client.session.dc_id, lang_code=getattr(me, "lang_code", None))

    async def connection_info(self) -> ConnectionInfo:
        from telethon import version as tv
        from telethon.tl.alltlobjects import LAYER

        connected = self.client.is_connected()
        latency = None
        if connected:
            from telethon.tl.functions.help import GetNearestDcRequest
            t0 = time.perf_counter()
            try:
                await self._call(lambda: self.client(GetNearestDcRequest()))
                latency = (time.perf_counter() - t0) * 1000
            except Exception:
                connected = False
        s = self.client.session
        return ConnectionInfo(connected=connected, dc_id=s.dc_id, server=s.server_address, port=s.port, layer=LAYER,
                              library=f"Telethon {tv.__version__}", latency_ms=latency)

    # ------------------------------------------------------------------ messages
    def _map(self, msgs: list[Any]) -> list[MessageRecord]:
        me = self._me
        name = (f"{me.first_name or ''} {me.last_name or ''}").strip() if me else None
        out = []
        for m in msgs:
            if m is None or type(m).__name__ == "MessageService":
                continue
            try:
                out.append(to_record(m, me.id if me else None, name, me.username if me else None))
            except Exception:
                log.exception("Failed to map message %s; skipping", getattr(m, "id", "?"))
        return out

    async def history(self, *, min_id: int = 0, batch: int = 100, delay: float = 0.5) -> AsyncIterator[list[MessageRecord]]:
        await self._require_me()
        last = min_id
        batch = max(1, min(batch, 100))  # messages.getHistory returns at most 100 per request
        while True:
            cursor = last
            msgs = await self._call(lambda c=cursor: self.client.get_messages("me", limit=batch, min_id=c, reverse=True))
            msgs = [m for m in msgs if m is not None]
            if not msgs:
                return
            last = max(m.id for m in msgs)
            records = self._map(msgs)
            yield records
            if len(msgs) < batch:
                return
            await asyncio.sleep(delay)

    async def get_by_ids(self, ids: list[int]) -> dict[int, MessageRecord | None]:
        await self._require_me()
        result: dict[int, MessageRecord | None] = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            msgs = await self._call(lambda chunk=chunk: self.client.get_messages("me", ids=chunk))
            mapped = {r.id: r for r in self._map([m for m in msgs if m is not None])}
            for mid in chunk:
                result[mid] = mapped.get(mid)
        return result

    async def delete(self, ids: list[int]) -> list[int]:
        await self._require_me()
        done: list[int] = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            await self._call(lambda chunk=chunk: self.client.delete_messages("me", chunk, revoke=True))
            done.extend(chunk)
        return done

    async def _message(self, message_id: int) -> Any:
        msg = await self._call(lambda: self.client.get_messages("me", ids=message_id))
        if msg is None or getattr(msg, "media", None) is None:
            raise DownloadError(f"message {message_id} has no downloadable media")
        return msg

    async def download(self, message_id: int, dest: Path, *, offset: int = 0, progress: ProgressCallback | None = None,
                       pause_check: Callable[[], Awaitable[None]] | None = None) -> int:
        await self._require_me()
        msg = await self._message(message_id)
        total = getattr(msg.file, "size", None)
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = offset
        # iter_download requires offsets aligned to 4 KB; realign and truncate the partial file if needed
        aligned = offset - (offset % 4096)
        if aligned != offset:
            with open(dest, "r+b") as fh:
                fh.truncate(aligned)
            written = aligned
        mode = "ab" if written else "wb"
        try:
            with open(dest, mode) as fh:
                async for chunk in self.client.iter_download(msg.media, offset=written, request_size=REQUEST_SIZE,
                                                             file_size=total):
                    if pause_check:
                        await pause_check()
                    fh.write(chunk)
                    written += len(chunk)
                    if progress:
                        r = progress(written, total)
                        if asyncio.iscoroutine(r):
                            await r
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            err = translate(exc)
            if err.code == "rate_limited":
                raise err from exc
            raise DownloadError(str(err)) from exc
        return written

    async def download_thumbnail(self, message_id: int) -> bytes | None:
        await self._require_me()
        msg = await self._call(lambda: self.client.get_messages("me", ids=message_id))
        if msg is None or msg.media is None:
            return None
        try:
            data = await self._call(lambda: self.client.download_media(msg, file=bytes, thumb=-1))
        except Exception:
            data = None
        return data if isinstance(data, bytes | bytearray) and data else None

    # ------------------------------------------------------------------ auth primitives (used by PhoneAuthProvider)
    async def send_code(self, phone: str) -> str:
        await self.connect()
        sent = await self._call(lambda: self.client.send_code_request(phone))
        return sent.phone_code_hash

    async def sign_in_code(self, phone: str, code: str, phone_code_hash: str) -> bool:
        """Returns True if logged in, False if a 2FA password is required."""
        from telethon.errors import SessionPasswordNeededError
        try:
            await self.client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            return False
        except BaseException as exc:
            raise translate(exc) from exc
        self._persist_session()
        return True

    async def sign_in_password(self, password: str) -> None:
        try:
            await self.client.sign_in(password=password)
        except BaseException as exc:
            raise translate(exc) from exc
        self._persist_session()

    async def password_hint(self) -> str | None:
        from telethon.tl.functions.account import GetPasswordRequest
        try:
            pwd = await self.client(GetPasswordRequest())
            return getattr(pwd, "hint", None)
        except Exception:
            return None

    async def log_out(self) -> None:
        try:
            await self.connect()
            await self.client.log_out()
        except BaseException as exc:
            log.warning("Server-side logout failed (%s); local session is removed anyway", type(exc).__name__)
