"""Thumbnail/preview cache. Clearing it never touches the index DB or session."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from ..core.paths import AppPaths
from ..repositories.system import CacheRepository

log = logging.getLogger(__name__)


class CacheService:
    def __init__(self, paths: AppPaths, repo: CacheRepository, gateway_provider, limit_mb: int = 512) -> None:  # type: ignore[no-untyped-def]
        self.paths = paths
        self.repo = repo
        self._gw = gateway_provider
        self.limit_bytes = limit_mb * 1024 * 1024

    def stats(self) -> dict[str, Any]:
        by_kind = {r["kind"]: {"files": r["files"], "bytes": r["bytes"], "last_used": r["last_used"]} for r in self.repo.stats()}
        disk = 0
        files = 0
        for p in self.paths.cache_dir.rglob("*"):
            if p.is_file():
                files += 1
                disk += p.stat().st_size
        return {"by_kind": by_kind, "disk_bytes": disk, "disk_files": files, "limit_bytes": self.limit_bytes,
                "path": str(self.paths.cache_dir)}

    def thumbnail_path(self, account_id: int, message_id: int) -> Path | None:
        row = self.repo.get(account_id, message_id, "thumb")
        if row and Path(row["path"]).exists():
            self.repo.touch(account_id, message_id, "thumb")
            return Path(row["path"])
        return None

    async def fetch_thumbnail(self, account_id: int, message_id: int) -> Path | None:
        existing = self.thumbnail_path(account_id, message_id)
        if existing:
            return existing
        data = await self._gw().download_thumbnail(message_id)
        if not data:
            return None
        target = self.paths.thumbnails_dir / str(account_id) / f"{message_id}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.repo.put(account_id, message_id, "thumb", str(target), len(data))
        self.enforce_limit()
        return target

    def enforce_limit(self) -> int:
        total = sum(r["bytes"] for r in self.repo.stats())
        removed = 0
        while total > self.limit_bytes:
            rows = self.repo.oldest(200)
            if not rows:
                break
            for r in rows:
                Path(r["path"]).unlink(missing_ok=True)
                total -= r["size"]
                removed += 1
            self.repo.remove(rows)
        return removed

    def clear(self, kind: str | None = None) -> int:
        """Delete cached files only (thumbnails/previews). Index DB and session are untouched."""
        rows = self.repo.clear(kind)
        for r in rows:
            Path(r["path"]).unlink(missing_ok=True)
        targets = [self.paths.thumbnails_dir, self.paths.previews_dir] if kind is None else (
            [self.paths.thumbnails_dir] if kind == "thumb" else [self.paths.previews_dir])
        for d in targets:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        log.info("Cache cleared (%s entries)", len(rows))
        return len(rows)
