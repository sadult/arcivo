"""Safe, queued deletion of Saved Messages.

Workflow: ``plan()`` → user reviews counts/types/sizes → user explicitly
confirms with the plan token → ``runner`` deletes in batches of ≤100 with
backoff → local index is updated only for ids Telegram accepted → audit log
and report. Telegram has no API to restore deleted messages, so there is no
Undo for this operation (the UI says so explicitly).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import ArcivoError, ConfirmationRequired
from ..core.events import DATA_CHANGED, EventBus
from ..jobs.manager import JobContext
from ..jobs.reports import build_summary, write_report
from ..repositories.messages import MessageRepository
from ..repositories.system import AuditRepository, ReportRepository

log = logging.getLogger(__name__)
BATCH = 100  # messages.deleteMessages accepts up to 100 ids per call


@dataclass
class DeletePlan:
    ids: list[int]
    count: int
    by_type: dict[str, int]
    total_bytes: int
    first_ts: int | None
    last_ts: int | None
    token: str
    samples: list[dict[str, Any]] = field(default_factory=list)
    tagged: int = 0
    created_at: float = field(default_factory=time.time)


class DeleteService:
    def __init__(self, gateway_provider, messages: MessageRepository, audit: AuditRepository,  # type: ignore[no-untyped-def]
                 reports: ReportRepository, bus: EventBus, reports_dir) -> None:
        self._gw = gateway_provider
        self.messages = messages
        self.audit = audit
        self.reports = reports
        self.bus = bus
        self.reports_dir = reports_dir
        self.batch_delay = 0.4

    @staticmethod
    def token_for(ids: list[int]) -> str:
        return hashlib.sha256((",".join(map(str, sorted(set(ids))))).encode()).hexdigest()[:16]

    def plan(self, account_id: int, ids: list[int]) -> DeletePlan:
        ids = sorted(set(ids))
        rows = self.messages.rows_by_ids(account_id, ids)
        by_type: dict[str, int] = {}
        total = 0
        for r in rows:
            by_type[r["media_type"]] = by_type.get(r["media_type"], 0) + 1
            total += r["file_size"] or 0
        dates = [r["date_ts"] for r in rows]
        tagged = 0
        if ids:
            tagged = int(self.messages.db.scalar(
                f"SELECT count(DISTINCT message_id) FROM message_tags WHERE account_id = ? AND message_id IN "
                f"({','.join('?' * min(len(ids), 900))})", [account_id, *ids[:900]]) or 0)
        samples = [{"id": r["id"], "type": r["media_type"], "name": r["file_name"] or (r["text"] or "")[:80],
                    "size": r["file_size"], "date_ts": r["date_ts"]} for r in rows[:25]]
        return DeletePlan(ids=[r["id"] for r in rows], count=len(rows), by_type=by_type, total_bytes=total,
                          first_ts=min(dates) if dates else None, last_ts=max(dates) if dates else None,
                          token=self.token_for([r["id"] for r in rows]), samples=samples, tagged=tagged)

    def job_params(self, account_id: int, plan: DeletePlan, confirm_token: str, reason: str = "manual",
                   source_job: str | None = None) -> dict[str, Any]:
        if confirm_token != plan.token:
            raise ConfirmationRequired("deletion was not confirmed for this exact selection")
        return {"account_id": account_id, "ids": plan.ids, "token": plan.token, "reason": reason, "source_job": source_job}

    def runner(self, params: dict[str, Any]):  # type: ignore[no-untyped-def]
        async def run(ctx: JobContext) -> dict[str, Any]:
            ids = [i for i in params["ids"] if i not in set(params.get("exclude_ids") or [])]
            if self.token_for(params["ids"]) != params.get("token") and not params.get("exclude_ids"):
                raise ConfirmationRequired("confirmation token mismatch")
            account_id = params["account_id"]
            ctx.p.total = len(ids)
            ctx.p.phase = "delete"
            self.audit.add("delete.start", count=len(ids), reason=params.get("reason"), job=ctx.job.id)
            deleted: list[int] = []
            for i in range(0, len(ids), BATCH):
                await ctx.checkpoint()
                chunk = ids[i:i + BATCH]
                ctx.p.current = f"{chunk[0]}…{chunk[-1]}"
                try:
                    ok = await self._gw().delete(chunk)
                    self.messages.delete_local(account_id, ok)
                    deleted.extend(ok)
                    for mid in chunk:
                        ctx.item(mid, "done" if mid in set(ok) else "failed", error=None if mid in set(ok) else "not deleted")
                except ArcivoError as exc:
                    if exc.code == "session_invalid":
                        raise
                    for mid in chunk:
                        ctx.item(mid, "failed", error=f"{exc.code}: {exc}")
                await self._sleep(self.batch_delay)  # be gentle with the API between batches
            self.audit.add("delete.finish", deleted=len(deleted), failed=ctx.p.failed, job=ctx.job.id)
            self.bus.publish(DATA_CHANGED, reason="delete")
            summary = build_summary(ctx.job, ctx, {"deleted_ids_count": len(deleted), "reason": params.get("reason"),
                                                   "undo_available": False})
            jpath, hpath = write_report(summary, self.reports_dir, self.reports)
            return {"deleted": len(deleted), "report_json": str(jpath), "report_html": str(hpath)}
        return run

    @staticmethod
    async def _sleep(s: float) -> None:
        import asyncio
        await asyncio.sleep(s)
