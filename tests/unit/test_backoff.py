import pytest

from arcivo.core import errors as E
from arcivo.telegram.backoff import translate, with_retry


async def test_flood_wait_is_respected():
    slept = []
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise E.RateLimitError("x", retry_after=5)
        return "ok"

    async def fake_sleep(s):
        slept.append(s)

    assert await with_retry(fn, sleep=fake_sleep) == "ok"
    assert len(slept) == 2 and all(s >= 5 for s in slept)


async def test_long_flood_wait_surfaces():
    async def fn():
        raise E.RateLimitError("x", retry_after=5000)

    async def no_sleep(s):
        raise AssertionError("must not sleep for very long waits")

    with pytest.raises(E.RateLimitError):
        await with_retry(fn, max_flood_wait=900, sleep=no_sleep)


async def test_network_retry_then_fail():
    async def fn():
        raise ConnectionError("down")

    async def fake_sleep(s):
        pass

    with pytest.raises(E.NetworkError):
        await with_retry(fn, attempts=3, sleep=fake_sleep)


async def test_non_recoverable_not_retried():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise E.SessionInvalidError("revoked")

    with pytest.raises(E.SessionInvalidError):
        await with_retry(fn)
    assert calls["n"] == 1


def test_translate_telethon_errors():
    from telethon import errors as te
    assert isinstance(translate(te.FloodWaitError(request=None, capture=17)), E.RateLimitError)
    assert translate(te.FloodWaitError(request=None, capture=17)).retry_after == 17
    assert isinstance(translate(te.AuthKeyUnregisteredError(request=None)), E.SessionInvalidError)
    assert isinstance(translate(te.PhoneCodeInvalidError(request=None)), E.InvalidCodeError)
    assert isinstance(translate(OSError("x")), E.NetworkError)
