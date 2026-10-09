"""Rotating, redacted application logging."""

from __future__ import annotations

import logging
import logging.handlers
from collections import deque
from pathlib import Path

from .redaction import RedactingFilter

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_memory: deque[str] = deque(maxlen=5000)


class MemoryHandler(logging.Handler):
    """Keeps the most recent lines in memory for the in-app Logs page."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _memory.append(self.format(record))
        except Exception:
            pass


def recent_lines() -> list[str]:
    return list(_memory)


def setup_logging(logs_dir: Path, level: str = "INFO", console: bool = False) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "arcivo.log"
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(LOG_FORMAT)
    redact = RedactingFilter()

    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handlers: list[logging.Handler] = [file_handler, MemoryHandler()]
    if console:
        handlers.append(logging.StreamHandler())
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(redact)
        root.addHandler(h)
    # Telethon is chatty at DEBUG and may include raw payloads — cap it.
    logging.getLogger("telethon").setLevel(max(logging.INFO, root.level))
    return log_file
