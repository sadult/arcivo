"""Typed application configuration persisted as JSON (no secrets here).

Secrets (API hash, session) live in the credential store, never in this file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .paths import AppPaths, default_download_dir, default_export_dir

log = logging.getLogger(__name__)

DEFAULT_SHORTCUTS: dict[str, str] = {
    "focus_search": "Ctrl+F",
    "command_palette": "Ctrl+K",
    "refresh": "F5",
    "sync": "Ctrl+R",
    "select_all": "Ctrl+A",
    "clear_selection": "Esc",
    "bulk_delete": "Del",
    "export": "Ctrl+E",
    "tag": "Ctrl+T",
    "flag": "Ctrl+D",
    "toggle_sidebar": "Ctrl+B",
    "toggle_theme": "Ctrl+Shift+L",
    "toggle_details": "Ctrl+I",
    "settings": "Ctrl+,",
    "search_help": "F1",
    "nav_dashboard": "Ctrl+1",
    "nav_explorer": "Ctrl+2",
    "nav_search": "Ctrl+3",
    "nav_media": "Ctrl+4",
    "nav_statistics": "Ctrl+5",
    "nav_storage": "Ctrl+6",
    "nav_export": "Ctrl+7",
    "nav_jobs": "Ctrl+8",
    "nav_collections": "Ctrl+9",
}


@dataclass
class AppearanceSettings:
    theme: str = "dark"  # dark | light | system
    font_scale: float = 1.0
    animations: bool = True
    compact_rows: bool = False


@dataclass
class SyncSettings:
    auto_sync_on_start: bool = True
    auto_sync_interval_min: int = 0  # 0 = disabled
    recheck_recent: int = 300  # re-verify N newest messages for edits/deletions on incremental sync
    batch_size: int = 100
    request_delay_s: float = 0.6  # politeness delay between history pages
    max_flood_wait_s: int = 900  # wait automatically if Telegram asks for <= this many seconds
    keep_remote_deleted: bool = False  # keep messages deleted on Telegram in the local archive (marked)


@dataclass
class PerformanceSettings:
    download_concurrency: int = 2
    page_size: int = 400
    thumbnail_cache_mb: int = 512
    preview_max_mb: int = 25


@dataclass
class ExportDefaults:
    format: str = "json"
    folder_template: str = "{type}/{year}/{month}"
    file_template: str = "{date}_{id}_{filename}"
    include_metadata: bool = True
    include_text: bool = True
    download_media: bool = True


@dataclass
class NotificationSettings:
    toasts: bool = True
    job_finished: bool = True
    sync_finished: bool = True
    errors: bool = True


@dataclass
class PrivacySettings:
    mask_phone: bool = True
    hide_previews_in_screenshots: bool = False
    clear_cache_on_logout: bool = True


@dataclass
class NetworkSettings:
    """Optional proxy used for every Telegram connection (useful where Telegram is filtered)."""

    proxy_type: str = "none"  # none | socks5 | http | mtproto
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_username: str = ""
    proxy_password: str = ""
    proxy_secret: str = ""  # MTProto proxies only
    proxy_rdns: bool = True

    @property
    def enabled(self) -> bool:
        return self.proxy_type in ("socks5", "http", "mtproto") and bool(self.proxy_host) and self.proxy_port > 0

    def describe(self) -> str:
        return f"{self.proxy_type}://{self.proxy_host}:{self.proxy_port}" if self.enabled else "none"


@dataclass
class Settings:
    database_path: str = ""
    download_dir: str = ""
    export_dir: str = ""
    log_level: str = "INFO"
    selection_on_filter_change: str = "ask"  # keep | clear | ask
    confirm_destructive_twice: bool = True
    credential_backend: str = "auto"  # auto | keyring | dpapi | file
    onboarding_done: bool = False  # first-run welcome sheet shown
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    sync: SyncSettings = field(default_factory=SyncSettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    export: ExportDefaults = field(default_factory=ExportDefaults)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    privacy: PrivacySettings = field(default_factory=PrivacySettings)
    network: NetworkSettings = field(default_factory=NetworkSettings)
    shortcuts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    schema: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        return _build(cls, data)


def _build(klass: type, data: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    defaults = klass()
    for f in fields(klass):
        if f.name not in data:
            continue
        value = data[f.name]
        current = getattr(defaults, f.name)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            kwargs[f.name] = _build(type(current), value)
        elif isinstance(current, dict) and isinstance(value, dict):
            merged = dict(current)
            merged.update({str(k): str(v) for k, v in value.items()})
            kwargs[f.name] = merged
        elif current is None or isinstance(value, type(current)) or (isinstance(current, float) and isinstance(value, int)):
            kwargs[f.name] = value
        else:
            log.warning("Ignoring invalid config value for %s", f.name)
    return klass(**kwargs)


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.settings = Settings()

    def load(self) -> Settings:
        path = self.paths.config_file
        if path.exists():
            try:
                self.settings = Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                log.error("Config file is unreadable (%s); using defaults and keeping a backup", exc)
                path.replace(path.with_suffix(".broken.json"))
                self.settings = Settings()
        self._fill_defaults()
        return self.settings

    def _fill_defaults(self) -> None:
        s = self.settings
        if not s.database_path:
            s.database_path = str(self.paths.default_database)
        if not s.download_dir:
            s.download_dir = str(default_download_dir())
        if not s.export_dir:
            s.export_dir = str(default_export_dir())

    def save(self) -> None:
        path = self.paths.config_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.settings.to_dict(), indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)

    @property
    def database_path(self) -> Path:
        return Path(self.settings.database_path)
