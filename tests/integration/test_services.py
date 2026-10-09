from arcivo.services.analytics import TimeRange
from arcivo.services.search import SearchSpec
from arcivo.services.storage import keep_selection


async def test_search_combinations(synced, records):
    aid = synced.require_account()
    audio = [r for r in records if r.media_type.value == "audio"]
    assert synced.search.count(aid, "type:audio") == len(audio)
    big_audio = [r for r in audio if (r.file_size or 0) >= 20 * 1024**2]
    assert synced.search.count(aid, "type:music size:>=20MB") == len(big_audio)
    pdf_chat = [r for r in records if r.extension == "pdf" and r.chat_name == "Design Weekly"]
    assert synced.search.count(aid, 'ext:pdf chat:"Design Weekly"') == len(pdf_chat)
    sara = [r for r in records if r.sender_username == "sara_a" and r.media_type.value in ("audio", "voice")]
    assert synced.search.count(aid, "type:audio,voice sender:@sara_a") == len(sara)
    assert synced.search.count(aid, "-type:text") == len(records) - sum(r.media_type.value == "text" for r in records)
    assert synced.search.count(aid, "type:audio OR type:voice") == sum(r.media_type.value in ("audio", "voice") for r in records)
    assert synced.search.count(aid, "checklist") == sum("checklist" in r.text.lower() for r in records)


async def test_spec_to_query(synced):
    spec = SearchSpec(query="report", types=["document"], ext=["pdf"], chat="Design Weekly", min_size="1MB", flagged=True)
    q = spec.to_query()
    assert q == 'report type:document chat:"Design Weekly" ext:pdf size:1MB.. is:flagged'
    assert synced.search.validate(q) is None


async def test_paging_and_sorting(synced):
    aid = synced.require_account()
    rows = synced.search.page(aid, "type:file", 0, 20, "size", True)
    sizes = [r["file_size"] for r in rows]
    assert sizes == sorted(sizes, reverse=True)
    p2 = synced.search.page(aid, "type:file", 20, 20, "size", True)
    assert not {r["id"] for r in rows} & {r["id"] for r in p2}


async def test_analytics(synced, records):
    aid = synced.require_account()
    ov = synced.analytics.overview(aid)
    assert ov["messages"] == len(records)
    assert ov["total_bytes"] == sum(r.file_size or 0 for r in records)
    assert sum(x["n"] for x in synced.analytics.timeline(aid, "month")) == len(records)
    assert sum(synced.analytics.hours(aid)) == len(records)
    assert sum(sum(row) for row in synced.analytics.heatmap(aid)) == len(records)
    assert sum(b["n"] for b in synced.analytics.size_distribution(aid)) == sum(1 for r in records if r.file_size is not None)
    top = synced.analytics.top(aid, "extensions", 5)
    assert top and top[0]["n"] >= top[-1]["n"]
    assert synced.analytics.growth(aid)[-1]["messages"] == len(records)
    assert synced.analytics.overview(aid, TimeRange(start_ts=2**40))["messages"] == 0


async def test_storage_and_duplicates(synced):
    aid = synced.require_account()
    b = synced.storage.breakdown(aid)
    assert b["total_bytes"] == sum(c["bytes"] for c in b["categories"])
    groups = synced.storage.duplicates(aid, "media_id")
    assert groups, "sample data contains identical uploads"
    g = groups[0]
    sel = keep_selection(g, "oldest")
    assert len(sel) == len(g.members) - 1 and g.members[0]["id"] not in sel
    assert synced.messages.total(aid) == len(synced.messages.all_ids(aid))  # nothing deleted


async def test_tags_flags_undo_collections(synced):
    aid = synced.require_account()
    org = synced.org
    tag = org.create_tag("Receipts", "#123456")
    ids = synced.search.ids(aid, "type:document")[:10]
    assert org.tag(aid, tag.id, ids) == 10
    assert synced.search.count(aid, "tag:receipts") == 10
    org.undo.undo()
    assert synced.search.count(aid, "tag:Receipts") == 0
    org.undo.redo()
    assert synced.search.count(aid, "tag:Receipts") == 10
    org.set_flag(aid, ids[:3], True)
    assert synced.search.count(aid, "is:flagged") == 3
    org.undo.undo()
    assert synced.search.count(aid, "is:flagged") == 0
    c = org.save_collection("Big docs", "type:document size:>1MB")
    cols = org.list_collections(aid)
    assert any(x.id == c.id and x.count is not None for x in cols)
    try:
        org.save_collection("bad", "size:>>>")
        raise AssertionError("expected validation error")
    except ValueError:
        pass
