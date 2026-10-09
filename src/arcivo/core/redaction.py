"""Redaction helpers so secrets never reach logs, reports or the UI."""

from __future__ import annotations

import logging
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(api[_-]?hash['\"=:\s]+)([0-9a-fA-F]{32})"), r"\1<redacted>"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "<hex32-redacted>"),
    (re.compile(r"(\+\d[\d\s\-]{7,}\d)"), lambda m: mask_phone(m.group(1))),  # type: ignore[list-item]
    (re.compile(r"\b1[A-Za-z0-9_\-]{200,}={0,2}"), "<session-redacted>"),  # Telethon StringSession
    (re.compile(r"((?:password|passwd|pwd|code|token|secret)['\"=:\s]+)(\S+)", re.I), r"\1<redacted>"),
]


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "•" * len(digits)
    return f"+{digits[:2]}{'•' * (len(digits) - 4)}{digits[-2:]}"


def mask_secret(value: str | None, keep: int = 0) -> str:
    if not value:
        return ""
    if keep <= 0 or len(value) <= keep * 2:
        return "•" * min(len(value), 12)
    return f"{value[:keep]}{'•' * 8}{value[-keep:]}"


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)  # type: ignore[arg-type]
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs secrets from every record (message + args)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True
