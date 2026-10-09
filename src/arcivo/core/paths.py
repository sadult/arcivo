"""Standard, secure filesystem locations.

Windows layout (installed mode)::

    %APPDATA%\\Arcivo\\config.json          user configuration (roaming)
    %LOCALAPPDATA%\\Arcivo\\database\\       SQLite index + backups
    %LOCALAPPDATA%\\Arcivo\\cache\\          thumbnails / previews (safe to clear)
    %LOCALAPPDATA%\\Arcivo\\logs\\           rotating, redacted logs
    %LOCALAPPDATA%\\Arcivo\\reports\\        job reports (JSON/HTML)
    %LOCALAPPDATA%\\Arcivo\\secure\\         DPAPI-encrypted secrets fallback

Portable mode is enabled when a file named ``portable.flag`` sits next to the
executable or ``ARCIVO_PORTABLE=1``; everything then lives in ``./ArcivoData``.
``ARCIVO_HOME`` overrides the root (used by tests and advanced users).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

APP = "Arcivo"


def _executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def is_portable() -> bool:
    if os.environ.get("ARCIVO_PORTABLE") == "1":
        return True
    return (_executable_dir() / "portable.flag").exists()


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    portable: bool = False

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def default_database(self) -> Path:
        return self.database_dir / "arcivo.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def thumbnails_dir(self) -> Path:
        return self.cache_dir / "thumbnails"

    @property
    def previews_dir(self) -> Path:
        return self.cache_dir / "previews"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def secure_dir(self) -> Path:
        return self.data_dir / "secure"

    def ensure(self) -> AppPaths:
        for p in (self.config_dir, self.data_dir, self.database_dir, self.cache_dir, self.thumbnails_dir,
                  self.previews_dir, self.logs_dir, self.reports_dir, self.secure_dir):
            p.mkdir(parents=True, exist_ok=True)
        _restrict(self.secure_dir)
        return self


def _restrict(path: Path) -> None:
    """Best-effort: make a directory private to the current user."""
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    # On Windows %LOCALAPPDATA% is already ACL-restricted to the user profile.


def resolve_paths() -> AppPaths:
    home = os.environ.get("ARCIVO_HOME")
    if home:
        root = Path(home).expanduser().resolve()
        return AppPaths(config_dir=root / "config", data_dir=root / "data", portable=True)
    if is_portable():
        root = _executable_dir() / "ArcivoData"
        return AppPaths(config_dir=root / "config", data_dir=root / "data", portable=True)
    dirs = PlatformDirs(appname=APP, appauthor=False, roaming=True)
    local = PlatformDirs(appname=APP, appauthor=False, roaming=False)
    return AppPaths(config_dir=Path(dirs.user_config_dir), data_dir=Path(local.user_data_dir))


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / APP


def default_export_dir() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.exists() else Path.home()) / f"{APP} Exports"


def resource_path(*parts: str) -> Path:
    """Locate bundled resources both from source and from a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidate = base.joinpath(*parts)
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parents[1].joinpath(*parts)
