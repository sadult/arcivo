"""Composition root: builds every core component once and wires dependencies.

The CLI, GUI and tests all create an :class:`AppContext`; no business logic
lives in front-ends.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .auth.credentials import CredentialStore, MemoryStore, open_store
from .auth.service import AuthService
from .core.config import ConfigStore
from .core.events import EventBus
from .core.logging_setup import setup_logging
from .core.paths import AppPaths, resolve_paths
from .db.database import Database
from .db.migrator import migrate
from .jobs.manager import JobManager
from .repositories.messages import MessageRepository
from .repositories.organization import CollectionRepository, MarksRepository, TagRepository
from .repositories.system import (
    AccountRepository,
    AuditRepository,
    CacheRepository,
    JobRepository,
    ReportRepository,
    SyncStateRepository,
)
from .services.analytics import AnalyticsService
from .services.cache import CacheService
from .services.delete import DeleteService
from .services.export import ExportService
from .services.organization import OrganizationService
from .services.search import SearchService
from .services.storage import StorageService
from .services.sync import SyncService

log = logging.getLogger(__name__)


def telethon_factory(settings_getter, max_flood_wait: float | None = None):  # type: ignore[no-untyped-def]
    """Build gateways lazily so proxy/flood settings changed at runtime apply to the next connection."""
    def make(api_id: int, api_hash: str, session: str | None, on_session) -> Any:  # type: ignore[no-untyped-def]
        from .telegram.telethon_gateway import TelethonGateway
        s = settings_getter()
        return TelethonGateway(api_id, api_hash, session, max_flood_wait=max_flood_wait or s.sync.max_flood_wait_s,
                               on_session_changed=on_session, network=s.network)
    return make


class AppContext:
    def __init__(self, paths: AppPaths | None = None, *, gateway: Any = None, store: CredentialStore | None = None,
                 database: str | Path | None = None, log_console: bool = False, configure_logging: bool = True) -> None:
        self.paths = (paths or resolve_paths()).ensure()
        self.config = ConfigStore(self.paths)
        self.config.load()
        s = self.config.settings
        if configure_logging:
            self.log_file = setup_logging(self.paths.logs_dir, s.log_level, console=log_console)
        self.bus = EventBus()
        self.db = Database(database or s.database_path)
        applied = migrate(self.db, backup_dir=self.paths.database_dir / "backups")

        self.store = store or (MemoryStore() if gateway is not None else open_store(s.credential_backend, self.paths.secure_dir))
        self._fixed_gateway = gateway
        if gateway is not None:
            self.auth = AuthService(self.store, lambda *a: gateway)
        else:
            self.auth = AuthService(self.store, telethon_factory(lambda: self.config.settings))

        # repositories
        self.messages = MessageRepository(self.db)
        self.tags = TagRepository(self.db)
        self.marks = MarksRepository(self.db)
        self.collections = CollectionRepository(self.db)
        self.accounts = AccountRepository(self.db)
        self.sync_state = SyncStateRepository(self.db)
        self.jobs_repo = JobRepository(self.db)
        self.reports = ReportRepository(self.db)
        self.cache_repo = CacheRepository(self.db)
        self.audit = AuditRepository(self.db)

        # services
        self.search = SearchService(self.messages)
        self.analytics = AnalyticsService(self.db)
        self.storage = StorageService(self.db)
        self.org = OrganizationService(self.tags, self.marks, self.collections, self.search, self.bus)
        self.sync = SyncService(self.gateway, self.messages, self.sync_state, self.accounts, self.audit, self.bus, s)
        self.deleter = DeleteService(self.gateway, self.messages, self.audit, self.reports, self.bus, self.paths.reports_dir)
        self.exporter = ExportService(self.gateway, self.messages, self.tags, self.search, self.cache_repo, self.reports,
                                      self.paths.reports_dir, concurrency=s.performance.download_concurrency)
        if 2 in applied:
            self.org.seed_default_collections()
        self.cache = CacheService(self.paths, self.cache_repo, self.gateway, s.performance.thumbnail_cache_mb)
        self._jobs: JobManager | None = None

    # The job manager needs a running loop for its tasks; it is created lazily on that loop.
    @property
    def jobs(self) -> JobManager:
        if self._jobs is None:
            self._jobs = JobManager(self.jobs_repo, self.bus, concurrency=2)
            self._jobs.register("sync", self.sync.runner)
            self._jobs.register("export", self.exporter.runner)
            self._jobs.register("delete", self.deleter.runner)
        return self._jobs

    def gateway(self) -> Any:
        if self._fixed_gateway is not None:
            return self._fixed_gateway
        return self.auth.gateway()

    @property
    def account_id(self) -> int | None:
        row = self.accounts.first()
        return int(row["id"]) if row else None

    def require_account(self) -> int:
        aid = self.account_id
        if aid is None:
            from .core.errors import NotAuthenticatedError
            raise NotAuthenticatedError("no synced account yet — run a sync first")
        return aid

    async def aclose(self) -> None:
        if self._jobs is not None:
            await self._jobs.shutdown()
        try:
            gw = self.gateway()
            await gw.disconnect()
        except Exception:
            pass
        self.db.close()
