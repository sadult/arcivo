from arcivo.core import errors as E
from arcivo.domain.models import MessageRecord
from arcivo.telegram.fake import flood


async def test_initial_then_incremental(ctx, gateway, records):
    r = await ctx.sync.sync()
    assert r["mode"] == "initial" and r["fetched"] == len(records)
    aid = ctx.require_account()
    assert ctx.messages.total(aid) == len(records)
    gateway.records[10_000] = MessageRecord(id=10_000, date_ts=1_790_000_000, text="brand new note")
    r2 = await ctx.sync.sync()
    assert r2["mode"] == "incremental" and r2["fetched"] == 1
    assert ctx.search.count(aid, "brand new") == 1


async def test_incremental_detects_remote_deletes_and_edits(synced, gateway):
    aid = synced.require_account()
    newest = max(gateway.records)
    gateway.records.pop(newest)
    second = sorted(gateway.records)[-1]
    gateway.records[second].text = "edited remotely xylophone"
    r = await synced.sync.sync("incremental")
    assert r["deleted"] == 1
    assert synced.messages.get(aid, newest) is None
    assert synced.search.count(aid, "xylophone") == 1


async def test_keep_remote_deleted_marks_instead(synced, gateway):
    synced.config.settings.sync.keep_remote_deleted = True
    aid = synced.require_account()
    gone = max(gateway.records)
    gateway.records.pop(gone)
    await synced.sync.sync("full")
    assert synced.messages.get(aid, gone)["remote_deleted"] == 1
    assert synced.search.count(aid, "is:deleted") == 1


async def test_initial_sync_resumes_after_network_failure(ctx, gateway, records):
    gateway.fail_next = [None]  # placeholder replaced below
    gateway.fail_next = []
    calls = {"n": 0}
    original = gateway.history

    async def flaky(**kw):
        async for batch in original(**kw):
            calls["n"] += 1
            if calls["n"] == 3:
                raise E.NetworkError("cable unplugged")
            yield batch

    gateway.history = flaky
    try:
        await ctx.sync.sync("initial")
    except E.NetworkError:
        pass
    aid = ctx.require_account()
    st = ctx.sync_state.get(aid)
    assert st["initial_complete"] == 0 and st["checkpoint_id"] > 0
    partial = ctx.messages.total(aid)
    gateway.history = original
    r = await ctx.sync.sync()
    assert r["mode"] == "initial"
    assert ctx.messages.total(aid) == len(records) and r["fetched"] == len(records) - partial


async def test_rate_limit_error_propagates(ctx, gateway):
    gateway.fail_next = [flood(30)]
    try:
        await ctx.sync.sync()
        raised = False
    except E.RateLimitError as exc:
        raised = exc.retry_after == 30
    assert raised
