"""Synchronisation of Saved Messages into the local index.

* **Initial sync** — oldest → newest, checkpointed per batch; resumable.
* **Incremental sync** — only messages newer than the highest synced id, then
  re-verifies the N newest messages to pick up edits and deletions.
* **Full reconcile** — re-reads everything; detects remote deletions/edits.

Telegram stays the source of truth for messages/media; tags, flags, notes,
collections, jobs and settings are local-only and never overwritten by sync.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..core.events import DATA_CHANGED, SYNC_FINISHED, SYNC_PROGRESS, EventBus
from ..jobs.manager import JobContext
from ..repositories.messages import MessageRepository
from ..repositories.system import AccountRepository, AuditRepository, SyncStateRepository

log = logging.getLogger(__name__)


class SyncService:
    def __init__(self, gateway_provider, messages: MessageRepository, state: SyncStateRepository,  # type: ignore[no-untyped-def]
                 accounts: AccountRepository, audit: AuditRepository, bus: EventBus, settings) -> None:
        self._gw = gateway_provider
        self.messages = messages
        self.state = state
        self.accounts = accounts
        self.audit = audit
        self.bus = bus
        self.settings = settings

    async def ensure_account(self) -> int:
        me = await self._gw().get_me()
        return self.accounts.ensure(me.user_id, me.display_name, me.username)

    def runner(self, params: dict[str, Any]):  # type: ignore[no-untyped-def]
        async def run(ctx: JobContext) -> dict[str, Any]:
            return await self.sync(params.get("mode", "auto"), ctx)
        return run

    async def sync(self, mode: str = "auto", ctx: JobContext | None = None) -> dict[str, Any]:
        account_id = await self.ensure_account()
        st = self.state.get(account_id)
        if mode == "auto":
            mode = "incremental" if st["initial_complete"] else "initial"
        started = time.time()
        s = self.settings.sync
        result: dict[str, Any] = {"mode": mode, "account_id": account_id, "fetched": 0, "deleted": 0, "updated": 0}
        if ctx:
            ctx.p.phase = mode
        gw = self._gw()

        if mode in ("initial", "full"):
            start_from = st["checkpoint_id"] if (mode == "initial" and not st["initial_complete"]) else 0
            seen: set[int] = set()
            async for batch in gw.history(min_id=start_from, batch=s.batch_size, delay=s.request_delay_s):
                if ctx:
                    await ctx.checkpoint()
                self.messages.upsert_many(account_id, batch)
                result["fetched"] += len(batch)
                seen.update(r.id for r in batch)
                top = max(r.id for r in batch)
                self.state.update(account_id, checkpoint_id=top, max_message_id=max(top, st["max_message_id"]))
                st["max_message_id"] = max(top, st["max_message_id"])
                self._progress(ctx, result["fetched"], mode)
            if mode == "full":
                missing = self.messages.all_ids(account_id) - seen
                result["deleted"] = self._handle_deleted(account_id, sorted(missing))
                self.state.update(account_id, last_reconcile=int(time.time()))
            self.state.update(account_id, initial_complete=1, last_full_sync=int(time.time()))
        else:
            async for batch in gw.history(min_id=st["max_message_id"], batch=s.batch_size, delay=s.request_delay_s):
                if ctx:
                    await ctx.checkpoint()
                self.messages.upsert_many(account_id, batch)
                result["fetched"] += len(batch)
                top = max(r.id for r in batch)
                self.state.update(account_id, max_message_id=top)
                self._progress(ctx, result["fetched"], mode)
            recent = self.messages.recent_ids(account_id, s.recheck_recent)
            if recent:
                if ctx:
                    ctx.p.phase = "verify"
                    await ctx.checkpoint()
                remote = await gw.get_by_ids(recent)
                gone = [mid for mid, rec in remote.items() if rec is None]
                changed = [rec for rec in remote.values() if rec is not None]
                if changed:
                    self.messages.upsert_many(account_id, changed)
                    result["updated"] = len(changed)
                result["deleted"] = self._handle_deleted(account_id, gone)
            self.state.update(account_id, last_incremental=int(time.time()))

        total = self.messages.total(account_id)
        self.state.update(account_id, total_synced=total)
        result["total"] = total
        result["duration_s"] = round(time.time() - started, 2)
        self.audit.add("sync", **{k: v for k, v in result.items() if k != "account_id"})
        log.info("Sync %s finished: fetched=%s deleted=%s total=%s", mode, result["fetched"], result["deleted"], total)
        self.bus.publish(SYNC_FINISHED, **result)
        self.bus.publish(DATA_CHANGED, reason="sync")
        return result

    def _handle_deleted(self, account_id: int, ids: list[int]) -> int:
        if not ids:
            return 0
        if getattr(self.settings.sync, "keep_remote_deleted", False):
            return self.messages.mark_remote_deleted(account_id, ids)
        return self.messages.delete_local(account_id, ids)

    def _progress(self, ctx: JobContext | None, fetched: int, mode: str) -> None:
        if ctx:
            ctx.p.done = fetched
            ctx.p.total = max(ctx.p.total, fetched)
            ctx.p.current = f"{fetched}"
            ctx.emit()
        self.bus.publish(SYNC_PROGRESS, fetched=fetched, mode=mode)
