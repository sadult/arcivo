"""Respectful retry/backoff and Telethon → Arcivo error translation.

Arcivo never tries to work around Telegram limits: when the server asks us to
wait (FLOOD_WAIT_X) we wait exactly that long (plus small jitter) or surface a
clear "rate limited" error to the user if the wait is longer than allowed.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from ..core import errors as E

log = logging.getLogger(__name__)


def translate(exc: BaseException) -> E.ArcivoError:
    """Map Telethon/network exceptions to Arcivo errors (imported lazily)."""
    if isinstance(exc, E.ArcivoError):
        return exc
    try:
        from telethon import errors as te
    except ImportError:  # pragma: no cover
        te = None  # type: ignore[assignment]
    name = type(exc).__name__
    if te is not None:
        if isinstance(exc, te.FloodWaitError | getattr(te, "FloodPremiumWaitError", te.FloodWaitError)):
            return E.RateLimitError(f"Telegram asked to wait {exc.seconds}s", retry_after=float(exc.seconds))
        if isinstance(exc, te.SlowModeWaitError):
            return E.RateLimitError("slow mode", retry_after=float(exc.seconds))
        if isinstance(exc, te.PhoneCodeInvalidError | te.PhoneCodeExpiredError | te.PhoneCodeEmptyError):
            return E.InvalidCodeError(name)
        if isinstance(exc, te.PasswordHashInvalidError):
            return E.InvalidPasswordError(name)
        if isinstance(exc, te.PhoneNumberInvalidError | te.PhoneNumberBannedError | te.PhoneNumberUnoccupiedError):
            return E.InvalidPhoneError(name)
        if isinstance(exc, te.ApiIdInvalidError | te.ApiIdPublishedFloodError):
            return E.InvalidApiCredentialsError(name)
        if isinstance(exc, te.AuthKeyUnregisteredError | te.SessionRevokedError | te.SessionExpiredError
                      | te.AuthKeyDuplicatedError | te.UserDeactivatedError | te.UserDeactivatedBanError):
            return E.SessionInvalidError(name)
        if isinstance(exc, te.MessageDeleteForbiddenError | te.ChatAdminRequiredError | te.ChatWriteForbiddenError):
            return E.PermissionDeniedError(name)
        if isinstance(exc, te.FileReferenceExpiredError):
            return E.DownloadError("file reference expired", recoverable=True)
        if isinstance(exc, te.ServerError | te.TimedOutError):
            return E.NetworkError(name)
        if isinstance(exc, te.RPCError):
            return E.TelegramApiError(f"{name}: {getattr(exc, 'message', '')}")
    if isinstance(exc, ConnectionError | OSError | asyncio.TimeoutError | TimeoutError):
        return E.NetworkError(name)
    return E.TelegramApiError(name)


async def with_retry[T](fn: Callable[[], Awaitable[T]], *, attempts: int = 5, max_flood_wait: float = 900,
                     base_delay: float = 1.5, max_delay: float = 60, sleep=asyncio.sleep,
                     on_wait: Callable[[float, E.ArcivoError], None] | None = None) -> T:
    """Run ``fn`` retrying recoverable failures with exponential backoff + jitter."""
    delay = base_delay
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except asyncio.CancelledError:
            raise
        except BaseException as raw:
            err = translate(raw)
            if isinstance(err, E.RateLimitError):
                wait = (err.retry_after or 1) + random.uniform(0.5, 2.0)
                if (err.retry_after or 0) > max_flood_wait or attempt == attempts:
                    raise err from raw
                log.warning("Rate limited by Telegram, waiting %.0fs (attempt %d/%d)", wait, attempt, attempts)
                if on_wait:
                    on_wait(wait, err)
                await sleep(wait)
                continue
            if isinstance(err, E.NetworkError | E.TelegramApiError) and err.recoverable and attempt < attempts and not isinstance(
                    err, E.PermissionDeniedError):
                wait = min(max_delay, delay) * random.uniform(0.8, 1.2)
                log.warning("Transient error %s, retrying in %.1fs (attempt %d/%d)", err.code, wait, attempt, attempts)
                if on_wait:
                    on_wait(wait, err)
                await sleep(wait)
                delay *= 2
                continue
            raise err from raw
    raise E.TelegramApiError("retry attempts exhausted")  # pragma: no cover
