import asyncio
import json
from pathlib import Path

import pytest

from arcivo.core.errors import ConfirmationRequired, NetworkError
from arcivo.jobs.manager import JobStatus
from arcivo.services.export import ExportSpec


async def test_metadata_export_all_formats(synced, tmp_path):
    aid = synced.require_account()
    spec = ExportSpec(output_dir=str(tmp_path), query="type:document", formats=["json", "jsonl", "csv", "txt", "html", "md"])
    job = synced.jobs.submit("export", "Docs", {**spec.to_params(), "account_id": aid})
    job = await synced.jobs.wait(job.id)
    assert job.status == JobStatus.COMPLETED, job.error
    out = Path(job.result["output_dir"])
    data = json.loads((out / "messages.json").read_text(encoding="utf-8"))
    assert len(data["messages"]) == synced.search.count(aid, "type:document")
    assert (out / "messages.csv").read_text(encoding="utf-8-sig").splitlines()[0].startswith("id,date")
    assert "<article" in (out / "messages.html").read_text(encoding="utf-8")
    assert (out / "manifest.json").exists() and list((out / "_report").glob("*.html"))


async def test_media_export_with_templates_and_delete_proposal(synced, gateway, tmp_path):
    aid = synced.require_account()
    spec = ExportSpec(output_dir=str(tmp_path), query="type:voice", formats=["json"], download_media=True,
                      folder_template="{type}/{year}", file_template="{date}_{id}", propose_delete=True)
    job = await synced.jobs.wait(synced.jobs.submit("export", "Voice", {**spec.to_params(), "account_id": aid}).id)
    assert job.status == JobStatus.COMPLETED, job.error
    out = Path(job.result["output_dir"])
    files = [p for p in out.rglob("*.ogg")]
    assert len(files) == synced.search.count(aid, "type:voice")
    assert not list(out.rglob("*.part"))
    assert files[0].read_bytes().startswith(b"ARCIVO-FAKE-")
    candidates = job.result["delete_candidates"]
    assert len(candidates) == len(files)
    # Nothing was deleted automatically
    assert gateway.deleted == []
    # Explicit confirmation with the plan token is required
    plan = synced.deleter.plan(aid, candidates)
    with pytest.raises(ConfirmationRequired):
        synced.deleter.job_params(aid, plan, "wrong-token")
    params = synced.deleter.job_params(aid, plan, plan.token, reason="post-export", source_job=job.id)
    djob = await synced.jobs.wait(synced.jobs.submit("delete", "Delete exported", params).id)
    assert djob.status == JobStatus.COMPLETED
    assert sorted(gateway.deleted) == sorted(candidates)
    assert synced.search.count(aid, "type:voice") == 0
    assert Path(djob.result["report_json"]).exists()


async def test_export_resume_skips_existing(synced, tmp_path):
    aid = synced.require_account()
    spec = ExportSpec(output_dir=str(tmp_path), query="type:sticker", formats=[], download_media=True)
    j1 = await synced.jobs.wait(synced.jobs.submit("export", "S", {**spec.to_params(), "account_id": aid}).id)
    spec.resume_dir = j1.result["output_dir"]
    j2 = await synced.jobs.wait(synced.jobs.submit("export", "S2", {**spec.to_params(), "account_id": aid}).id)
    assert j2.progress.skipped == j1.progress.done and j2.progress.done == 0


async def test_failed_downloads_then_retry(synced, gateway, tmp_path):
    aid = synced.require_account()
    ids = synced.search.ids(aid, "type:photo")[:5]
    spec = ExportSpec(output_dir=str(tmp_path), ids=ids, formats=["json"], download_media=True)
    gateway.fail_next = [NetworkError("offline"), NetworkError("offline")]
    j = await synced.jobs.wait(synced.jobs.submit("export", "P", {**spec.to_params(), "account_id": aid}).id)
    assert j.status == JobStatus.PARTIAL and j.progress.failed == 2 and j.progress.done == 3
    r = await synced.jobs.wait(synced.jobs.retry(j.id).id)
    assert r.status == JobStatus.COMPLETED and r.progress.done == 2


async def test_pause_resume_cancel(synced, tmp_path):
    aid = synced.require_account()
    spec = ExportSpec(output_dir=str(tmp_path), query="", formats=["jsonl"], download_media=True)
    job = synced.jobs.submit("export", "All", {**spec.to_params(), "account_id": aid})
    await asyncio.sleep(0.05)
    assert synced.jobs.pause(job.id)
    await asyncio.sleep(0.1)
    assert job.status == JobStatus.PAUSED
    frozen = job.progress.done
    await asyncio.sleep(0.1)
    assert job.progress.done == frozen
    assert synced.jobs.resume(job.id)
    await asyncio.sleep(0.05)
    assert synced.jobs.cancel(job.id)
    job = await synced.jobs.wait(job.id)
    assert job.status == JobStatus.CANCELLED


async def test_delete_partial_failure(synced, gateway):
    aid = synced.require_account()
    ids = synced.search.ids(aid, "type:text,link")[:150]
    assert len(ids) == 150
    gateway.fail_delete_ids = {sorted(ids)[120]}
    plan = synced.deleter.plan(aid, ids)
    assert plan.count == 150 and set(plan.by_type) <= {"text", "link"}
    j = await synced.jobs.wait(synced.jobs.submit("delete", "D", synced.deleter.job_params(aid, plan, plan.token)).id)
    assert j.status == JobStatus.PARTIAL
    assert j.progress.done == 100 and j.progress.failed == 50  # second batch failed as a whole
    assert len(synced.messages.rows_by_ids(aid, ids)) == 50
    audit = [r["action"] for r in synced.audit.list()]
    assert "delete.start" in audit and "delete.finish" in audit


async def test_sync_as_job(ctx):
    j = await ctx.jobs.wait(ctx.jobs.submit("sync", "Sync", {"mode": "auto"}).id)
    assert j.status == JobStatus.COMPLETED and j.result["fetched"] > 0
