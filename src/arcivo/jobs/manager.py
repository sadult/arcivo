"""Background job queue running on the core asyncio loop.

Jobs never block the UI: front-ends only observe ``JOB_UPDATED`` events.
Pause/resume is cooperative (checked between items and between download
chunks); cancel is cooperative too, so files are never left half-written
without a ``.part`` marker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ..core.errors import ArcivoError, OperationCancelled
from ..core.events import JOB_FINISHED, JOB_UPDATED, EventBus
from ..repositories.system import JobRepository

log = logging.getLogger(__name__)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL = "partial"  # finished with some failed items
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # app closed while running — can be retried/resumed


FINAL = {JobStatus.COMPLETED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED}


@dataclass
class Progress:
    total: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    current: str = ""
    phase: str = ""
    speed_bps: float = 0.0
    eta_s: float | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.done - self.failed - self.skipped)

    @property
    def fraction(self) -> float:
        if self.bytes_total:
            return min(1.0, self.bytes_done / self.bytes_total)
        if self.total:
            return min(1.0, (self.done + self.failed + self.skipped) / self.total)
        return 0.0


@dataclass
class Job:
    id: str
    kind: str
    title: str
    params: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    progress: Progress = field(default_factory=Progress)
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["progress"]["remaining"] = self.progress.remaining
        d["progress"]["fraction"] = self.progress.fraction
        return d


Runner = Callable[["JobContext"], Awaitable[dict[str, Any]]]
RunnerFactory = Callable[[dict[str, Any]], Runner]


class JobContext:
    def __init__(self, manager: JobManager, job: Job) -> None:
        self.manager = manager
        self.job = job
        self._resume = asyncio.Event()
        self._resume.set()
        self.cancelled = False
        self._last_emit = 0.0
        self._last_persist = 0.0
        self._speed_t = time.monotonic()
        self._speed_b = 0
        self.item_errors: list[dict[str, Any]] = []

    @property
    def p(self) -> Progress:
        return self.job.progress

    async def checkpoint(self) -> None:
        """Call frequently: blocks while paused, raises when cancelled."""
        if self.cancelled:
            raise OperationCancelled()
        if not self._resume.is_set():
            self.job.status = JobStatus.PAUSED
            self.emit(force=True)
            await self._resume.wait()
            if self.cancelled:
                raise OperationCancelled()
            self.job.status = JobStatus.RUNNING
            self.emit(force=True)

    def add_bytes(self, n: int) -> None:
        self.p.bytes_done += n
        self._update_speed()
        self.emit()

    def item(self, message_id: int, status: str, *, bytes_: int | None = None, path: str | None = None,
             error: str | None = None) -> None:
        if status == "done":
            self.p.done += 1
        elif status == "failed":
            self.p.failed += 1
            self.item_errors.append({"id": message_id, "error": error})
        elif status == "skipped":
            self.p.skipped += 1
        self.manager.repo.set_item(self.job.id, message_id, status, bytes_=bytes_, path=path, error=error)
        self._update_speed()
        self.emit()

    def _update_speed(self) -> None:
        now = time.monotonic()
        dt = now - self._speed_t
        if dt >= 1.0:
            inst = (self.p.bytes_done - self._speed_b) / dt
            self.p.speed_bps = inst if not self.p.speed_bps else 0.7 * self.p.speed_bps + 0.3 * inst
            self._speed_t, self._speed_b = now, self.p.bytes_done
        if self.p.bytes_total and self.p.speed_bps > 0:
            self.p.eta_s = max(0.0, (self.p.bytes_total - self.p.bytes_done) / self.p.speed_bps)
        elif self.job.started_at and (self.p.done + self.p.failed + self.p.skipped) > 0:
            elapsed = time.time() - self.job.started_at
            processed = self.p.done + self.p.failed + self.p.skipped
            self.p.eta_s = elapsed / processed * self.p.remaining

    def emit(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_emit > 0.2:
            self._last_emit = now
            self.manager.bus.publish(JOB_UPDATED, job=self.job.to_dict())
        if force or now - self._last_persist > 2.0:
            self._last_persist = now
            self.manager.persist(self.job)


class JobManager:
    def __init__(self, repo: JobRepository, bus: EventBus, concurrency: int = 1) -> None:
        self.repo = repo
        self.bus = bus
        self._factories: dict[str, RunnerFactory] = {}
        self._jobs: dict[str, Job] = {}
        self._contexts: dict[str, JobContext] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._sem: asyncio.Semaphore | None = None
        self.concurrency = concurrency
        self.on_finished: list[Callable[[Job], None]] = []
        repo.mark_interrupted()
        self._load_history()

    def _load_history(self) -> None:
        for r in self.repo.list(100):
            try:
                prog = json.loads(r["progress_json"] or "{}")
                job = Job(r["id"], r["kind"], r["title"], json.loads(r["params_json"]), JobStatus(r["status"]),
                          Progress(**{k: v for k, v in prog.items() if k in Progress.__dataclass_fields__}), r["error"],
                          created_at=r["created_at"], started_at=r["started_at"], finished_at=r["finished_at"])
                self._jobs[job.id] = job
            except Exception:
                log.warning("Skipping unreadable job row %s", r["id"])

    def register(self, kind: str, factory: RunnerFactory) -> None:
        self._factories[kind] = factory

    def persist(self, job: Job) -> None:
        try:
            self.repo.save({"id": job.id, "kind": job.kind, "title": job.title, "status": job.status.value,
                            "params_json": json.dumps(job.params, ensure_ascii=False, default=str),
                            "progress_json": json.dumps(asdict(job.progress)), "error": job.error,
                            "created_at": int(job.created_at), "started_at": int(job.started_at) if job.started_at else None,
                            "finished_at": int(job.finished_at) if job.finished_at else None})
        except Exception:
            log.exception("Could not persist job %s", job.id)

    # ------------------------------------------------------------------ API
    def submit(self, kind: str, title: str, params: dict[str, Any], parent_id: str | None = None) -> Job:
        if kind not in self._factories:
            raise ValueError(f"unknown job kind {kind}")
        job = Job(uuid.uuid4().hex[:12], kind, title, params, parent_id=parent_id)
        self._jobs[job.id] = job
        self.persist(job)
        ctx = JobContext(self, job)
        self._contexts[job.id] = ctx
        self._tasks[job.id] = asyncio.get_running_loop().create_task(self._run(job, ctx))
        self.bus.publish(JOB_UPDATED, job=job.to_dict())
        return job

    async def _run(self, job: Job, ctx: JobContext) -> None:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.concurrency)
        async with self._sem:
            if ctx.cancelled:
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                ctx.emit(force=True)
                try:
                    runner = self._factories[job.kind](job.params)
                    job.result = await runner(ctx) or {}
                    job.status = JobStatus.PARTIAL if job.progress.failed else JobStatus.COMPLETED
                except OperationCancelled:
                    job.status = JobStatus.CANCELLED
                except asyncio.CancelledError:
                    job.status = JobStatus.CANCELLED
                except ArcivoError as exc:
                    job.status, job.error = JobStatus.FAILED, f"{exc.code}: {exc}"
                    log.error("Job %s failed: %s", job.id, job.error)
                except Exception as exc:  # unexpected bug: keep the app alive, record it
                    job.status, job.error = JobStatus.FAILED, f"internal: {type(exc).__name__}: {exc}"
                    log.exception("Job %s crashed", job.id)
        job.finished_at = time.time()
        job.progress.eta_s = 0
        self.persist(job)
        self.bus.publish(JOB_UPDATED, job=job.to_dict())
        self.bus.publish(JOB_FINISHED, job=job.to_dict())
        for cb in self.on_finished:
            try:
                cb(job)
            except Exception:
                log.exception("on_finished callback failed")

    def pause(self, job_id: str) -> bool:
        ctx = self._contexts.get(job_id)
        if ctx and self._jobs[job_id].status == JobStatus.RUNNING:
            ctx._resume.clear()
            return True
        return False

    def resume(self, job_id: str) -> bool:
        ctx = self._contexts.get(job_id)
        if ctx and not ctx._resume.is_set():
            ctx._resume.set()
            return True
        return False

    def cancel(self, job_id: str) -> bool:
        ctx = self._contexts.get(job_id)
        job = self._jobs.get(job_id)
        if not ctx or not job or job.status in FINAL:
            return False
        ctx.cancelled = True
        ctx._resume.set()
        return True

    def retry(self, job_id: str, failed_only: bool = True) -> Job:
        """Re-run a job. For item jobs, only failed/pending items are retried when possible."""
        old = self._jobs.get(job_id)
        if old is None:
            raise KeyError(job_id)
        params = dict(old.params)
        if failed_only and old.kind in ("export", "delete"):
            done = {r["message_id"] for r in self.repo.items(job_id, "done")} | {
                r["message_id"] for r in self.repo.items(job_id, "skipped")}
            failed = [r["message_id"] for r in self.repo.items(job_id, "failed")]
            if old.status == JobStatus.PARTIAL and failed:
                params["ids"], params["query"] = failed, None
            elif done:
                params["exclude_ids"] = sorted(done)
        params["resume_dir"] = old.result.get("output_dir") or old.params.get("resume_dir")
        return self.submit(old.kind, old.title, params, parent_id=old.id)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def active(self) -> list[Job]:
        return [j for j in self._jobs.values() if j.status not in FINAL]

    def clear_finished(self) -> int:
        n = self.repo.clear_finished()
        for jid in [j.id for j in self._jobs.values() if j.status in FINAL]:
            self._jobs.pop(jid, None)
            self._contexts.pop(jid, None)
        return n

    async def wait(self, job_id: str) -> Job:
        t = self._tasks.get(job_id)
        if t:
            await asyncio.shield(t)
        return self._jobs[job_id]

    async def shutdown(self) -> None:
        for jid in list(self._contexts):
            self.cancel(jid)
        tasks = [t for t in self._tasks.values() if not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=10)
