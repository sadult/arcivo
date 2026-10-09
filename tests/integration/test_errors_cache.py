from arcivo.core import errors as E


async def test_session_invalid_fails_sync_cleanly(ctx, gateway):
    gateway.authorized = False
    try:
        await ctx.sync.sync()
        raise AssertionError("expected NotAuthenticatedError")
    except E.NotAuthenticatedError:
        pass


async def test_cache_clear_never_touches_db_or_session(synced, paths):
    aid = synced.require_account()
    synced.store.set("session", "keep-me")
    f = paths.thumbnails_dir / "1" / "5.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * 100)
    synced.cache_repo.put(aid, 5, "thumb", str(f), 100)
    st = synced.cache.stats()
    assert st["by_kind"]["thumb"]["files"] == 1
    total = synced.messages.total(aid)
    synced.cache.clear()
    assert not f.exists()
    assert synced.messages.total(aid) == total and synced.store.get("session") == "keep-me"


async def test_partial_file_is_not_renamed(synced, gateway, tmp_path):
    from arcivo.jobs.manager import JobStatus
    from arcivo.services.export import ExportSpec
    aid = synced.require_account()
    mid = synced.search.ids(aid, "type:document")[0]
    real = gateway.expected_size
    gateway.expected_size = lambda m: real(m) + 1  # simulate truncated download
    out = tmp_path / "out"
    spec = ExportSpec(output_dir=str(out), ids=[mid], formats=["json"], download_media=True)
    j = await synced.jobs.wait(synced.jobs.submit("export", "x", {**spec.to_params(), "account_id": aid}).id)
    assert j.status == JobStatus.PARTIAL and j.progress.failed == 1
    files = [p for p in out.rglob("*") if p.is_file()]
    assert any(p.suffix == ".part" for p in files)
    assert all(p.suffix in (".part", ".json", ".html") for p in files)  # the unverified file was never published
