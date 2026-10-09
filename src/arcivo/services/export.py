"""Export engine: metadata in several formats + optional media download.

Media downloads are streamed to ``*.part`` files (resumable), verified by size
and only then renamed. A successful export can *propose* deleting the exported
messages; deletion is a separate, explicitly confirmed job — never automatic.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME, __version__
from ..core.errors import ArcivoError, ExportError
from ..export.naming import (
    build_relative_path,
    context_for,
    sanitize_component,
    unique_path,
    validate_template,
)
from ..export.writers import ALL_FIELDS, FORMATS, WRITERS, record_from_row
from ..jobs.manager import JobContext
from ..jobs.reports import build_summary, write_report
from ..repositories.messages import MessageRepository
from ..repositories.organization import TagRepository
from ..repositories.system import CacheRepository, ReportRepository
from .search import SearchService

log = logging.getLogger(__name__)
FILE_TYPES = {"photo", "video", "video_note", "animation", "audio", "voice", "document", "sticker"}


@dataclass
class ExportSpec:
    output_dir: str
    query: str | None = ""
    ids: list[int] | None = None
    exclude_ids: list[int] | None = None
    name: str = "Arcivo Export"
    formats: list[str] = field(default_factory=lambda: ["json"])
    fields: list[str] | None = None  # None = all metadata
    include_text: bool = True
    include_metadata: bool = True
    download_media: bool = False
    media_types: list[str] | None = None  # restrict downloads to these media types
    folder_template: str = "{type}/{year}/{month}"
    file_template: str = "{date}_{id}_{filename}"
    skip_existing: bool = True
    hash_files: bool = True
    propose_delete: bool = False
    sort_key: str = "date"
    sort_desc: bool = False
    resume_dir: str | None = None
    language: str = "en"

    def validate(self) -> None:
        bad = [f for f in self.formats if f not in FORMATS]
        if bad:
            raise ExportError(f"unknown format(s): {', '.join(bad)}")
        if not self.formats and not self.download_media:
            raise ExportError("nothing to export: choose a format or enable media download")
        for t in (self.folder_template, self.file_template):
            unknown = validate_template(t)
            if unknown:
                raise ExportError(f"unknown placeholder(s): {', '.join(unknown)}")
        if not self.include_metadata and not self.include_text and self.formats:
            raise ExportError("metadata and content are both excluded")

    def to_params(self) -> dict[str, Any]:
        return asdict(self)


class ExportService:
    def __init__(self, gateway_provider, messages: MessageRepository, tags: TagRepository, search: SearchService,  # type: ignore[no-untyped-def]
                 cache: CacheRepository, reports: ReportRepository, reports_dir: Path, concurrency: int = 2) -> None:
        self._gw = gateway_provider
        self.messages = messages
        self.tags = tags
        self.search = search
        self.cache = cache
        self.reports = reports
        self.reports_dir = reports_dir
        self.concurrency = concurrency

    def preview(self, account_id: int, spec: ExportSpec) -> dict[str, Any]:
        ids = self._resolve_ids(account_id, spec)
        rows = self.messages.rows_by_ids(account_id, ids[:5000])
        files = [r for r in rows if r["media_type"] in FILE_TYPES and self._wanted(spec, r)]
        est = sum(r["file_size"] or 0 for r in files)
        if len(ids) > 5000 and rows:
            est = int(est * len(ids) / len(rows))
        return {"messages": len(ids), "files": len(files) if len(ids) <= 5000 else int(len(files) * len(ids) / max(1, len(rows))),
                "estimated_bytes": est if spec.download_media else 0,
                "sample_paths": [str(build_relative_path(spec.folder_template, spec.file_template, context_for(r)))
                                 for r in files[:5]]}

    def _resolve_ids(self, account_id: int, spec: ExportSpec) -> list[int]:
        if spec.ids:
            ids = list(dict.fromkeys(spec.ids))
        else:
            ids = self.search.ids(account_id, spec.query or "", spec.sort_key, spec.sort_desc)
        if spec.exclude_ids:
            ex = set(spec.exclude_ids)
            ids = [i for i in ids if i not in ex]
        return ids

    @staticmethod
    def _wanted(spec: ExportSpec, row: Any) -> bool:
        return not spec.media_types or row["media_type"] in spec.media_types or row["category"] in spec.media_types

    def runner(self, params: dict[str, Any]):  # type: ignore[no-untyped-def]
        spec = ExportSpec(**{k: v for k, v in params.items() if k in ExportSpec.__dataclass_fields__})
        account_id = int(params["account_id"])

        async def run(ctx: JobContext) -> dict[str, Any]:
            return await self._run(ctx, account_id, spec)
        return run

    async def _run(self, ctx: JobContext, account_id: int, spec: ExportSpec) -> dict[str, Any]:
        spec.validate()
        ctx.p.phase = "prepare"
        ids = self._resolve_ids(account_id, spec)
        ctx.p.total = len(ids)
        if spec.resume_dir and Path(spec.resume_dir).exists():
            out = Path(spec.resume_dir)
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            out = Path(spec.output_dir) / sanitize_component(f"{spec.name}_{stamp}")
        out.mkdir(parents=True, exist_ok=True)
        ctx.job.result["output_dir"] = str(out)

        fields = list(spec.fields or ALL_FIELDS)
        if not spec.include_text:
            fields = [f for f in fields if f != "text"]
        if not spec.include_metadata:
            fields = [f for f in fields if f in ("id", "date", "text", "exported_file")]
        writers = []
        for fmt in spec.formats:
            cls = WRITERS[fmt]
            path = out / f"messages.{cls.ext}"
            writers.append(cls(path, fields, spec.name, lang=spec.language) if fmt == "html" else cls(path, fields, spec.name))

        verified: list[int] = []
        taken: set[str] = set()
        sem = asyncio.Semaphore(max(1, self.concurrency))
        tag_names = {t.id: t.name for t in self.tags.list()}
        try:
            if spec.download_media:
                rows_for_size = self.messages.rows_by_ids(account_id, ids)
                ctx.p.bytes_total = sum((r["file_size"] or 0) for r in rows_for_size
                                        if r["media_type"] in FILE_TYPES and self._wanted(spec, r))
                del rows_for_size
            ctx.p.phase = "export"
            for start in range(0, len(ids), 100):
                await ctx.checkpoint()
                rows = self.messages.rows_by_ids(account_id, ids[start:start + 100])
                results = await asyncio.gather(*(self._export_one(ctx, sem, account_id, spec, out, r, taken) for r in rows))
                for r, (status, rel, err) in zip(rows, results, strict=True):
                    if status == "failed":
                        ctx.item(r["id"], "failed", error=err)
                        continue
                    tags = [t.name for t in self.tags.tags_for(account_id, r["id"])] if tag_names else []
                    rec = record_from_row(r, links=self.messages.links_for(account_id, r["id"]), tags=tags,
                                          exported_file=rel.replace("\\", "/") if rel else None)
                    for w in writers:
                        w.write(rec)
                    verified.append(r["id"])
                    ctx.item(r["id"], status, path=rel, bytes_=r["file_size"])
        finally:
            for w in writers:
                try:
                    w.close()
                except Exception:
                    log.exception("closing writer failed")
        ctx.p.phase = "report"
        manifest = {"generator": f"{APP_NAME} {__version__}", "created_at": datetime.now().astimezone().isoformat(),
                    "spec": {k: v for k, v in asdict(spec).items() if k not in ("ids", "exclude_ids")},
                    "messages": len(ids), "verified": len(verified), "failed": ctx.p.failed, "skipped": ctx.p.skipped,
                    "files": [f"messages.{WRITERS[f].ext}" for f in spec.formats]}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        summary = build_summary(ctx.job, ctx, {"output_dir": str(out), "verified_count": len(verified),
                                               "propose_delete": spec.propose_delete})
        jpath, hpath = write_report(summary, out / "_report", self.reports)
        result = {"output_dir": str(out), "verified": len(verified), "report_json": str(jpath), "report_html": str(hpath)}
        if spec.propose_delete:
            # Only fully verified messages are ever proposed; the user must still confirm in a separate step.
            result["delete_candidates"] = verified
        return result

    def _expected_size(self, row: Any) -> int | None:
        gw = self._gw()
        # gateways may know the exact byte count better than the index (e.g. FakeGateway, re-encoded photos)
        if hasattr(gw, "expected_size"):
            return gw.expected_size(row["id"])
        return row["file_size"] if row["media_type"] != "photo" else None

    async def _export_one(self, ctx: JobContext, sem: asyncio.Semaphore, account_id: int, spec: ExportSpec, out: Path,
                          row: Any, taken: set[str]) -> tuple[str, str | None, str | None]:
        if not (spec.download_media and row["media_type"] in FILE_TYPES and self._wanted(spec, row)):
            return "done", None, None
        rel = build_relative_path(spec.folder_template, spec.file_template, context_for(row))
        target = out / rel
        expected = self._expected_size(row)
        if spec.skip_existing and target.exists() and (expected is None or target.stat().st_size == expected):
            ctx.add_bytes(target.stat().st_size)
            return "skipped", str(rel), None
        if target.exists():
            target = unique_path(target, taken)
            rel = target.relative_to(out)
        else:
            taken.add(str(target).lower())
        part = target.with_name(target.name + ".part")
        async with sem:
            await ctx.checkpoint()
            ctx.p.current = row["file_name"] or f"#{row['id']}"
            offset = part.stat().st_size if part.exists() else 0
            last = [offset]

            def progress(done: int, total: int | None) -> None:
                ctx.add_bytes(done - last[0])
                last[0] = done

            try:
                size = await self._gw().download(row["id"], part, offset=offset, progress=progress, pause_check=ctx.checkpoint)
            except ArcivoError as exc:
                if exc.code in ("cancelled", "session_invalid"):
                    raise
                return "failed", None, f"{exc.code}: {exc}"
            except OSError as exc:
                return "failed", None, f"io: {exc}"
        if expected is not None and size != expected:
            return "failed", None, f"size mismatch: got {size}, expected {expected}"
        part.replace(target)
        if spec.hash_files:
            digest = await asyncio.to_thread(_sha256, target)
            self.cache.set_hash(account_id, row["id"], digest, size)
        try:
            ts = row["date_ts"]
            import os
            os.utime(target, (time.time(), ts))
        except OSError:
            pass
        return "done", str(rel), None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
