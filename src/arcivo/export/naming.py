"""File-name and folder templates with Windows-safe sanitisation.

Placeholders: {id} {date} {time} {datetime} {year} {month} {day} {type} {category}
{sender} {chat} {filename} {name} {ext} {size} {tag}
Example: ``{chat}/{year}/{month}/{type}`` + ``{date}_{sender}_{filename}``.
"""

from __future__ import annotations

import re
import string
import unicodedata
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
PLACEHOLDERS = ["id", "date", "time", "datetime", "year", "month", "day", "type", "category", "sender", "chat",
                "filename", "name", "ext", "size", "tag"]
MAX_COMPONENT = 120
DEFAULT_EXT = {"photo": "jpg", "video": "mp4", "video_note": "mp4", "animation": "mp4", "voice": "ogg", "audio": "mp3",
               "sticker": "webp", "document": "bin"}


def sanitize_component(value: str, fallback: str = "_") -> str:
    value = unicodedata.normalize("NFC", str(value))
    value = INVALID.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    if not value:
        value = fallback
    stem = value.split(".")[0].upper()
    if stem in RESERVED:
        value = "_" + value
    if len(value) > MAX_COMPONENT:
        if "." in value[-12:]:
            stem, ext = value.rsplit(".", 1)
            value = stem[: MAX_COMPONENT - len(ext) - 1].rstrip(". ") + "." + ext
        else:
            value = value[:MAX_COMPONENT].rstrip(". ")
    return value


def validate_template(template: str) -> list[str]:
    """Return unknown placeholders (empty list = valid)."""
    unknown = []
    for _, field, _, _ in string.Formatter().parse(template):
        if field is not None and field not in PLACEHOLDERS:
            unknown.append(field)
    return unknown


def context_for(row: Any, tz: tzinfo | None = None, tag: str | None = None) -> dict[str, str]:
    def get(k: str) -> Any:
        if hasattr(row, "keys"):
            return row[k] if k in row.keys() else None  # noqa: SIM118 (sqlite3.Row)
        return getattr(row, k, None)
    dt = datetime.fromtimestamp(get("date_ts"), tz=tz) if get("date_ts") else datetime.now(tz)
    media_type = str(get("media_type") or "file")
    ext = (get("extension") or DEFAULT_EXT.get(media_type, "bin")).lower()
    raw_name = get("file_name")
    if raw_name:
        filename = raw_name if "." in raw_name else f"{raw_name}.{ext}"
    else:
        filename = f"{media_type}_{get('id')}.{ext}"
    name = filename.rsplit(".", 1)[0]
    sender = get("sender_name") or get("sender_username") or "me"
    chat = get("chat_name") or ("Saved Messages" if not get("is_forward") else "Unknown")
    return {
        "id": str(get("id")), "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H-%M-%S"),
        "datetime": dt.strftime("%Y-%m-%d_%H-%M-%S"), "year": dt.strftime("%Y"), "month": dt.strftime("%m"),
        "day": dt.strftime("%d"), "type": media_type, "category": str(get("category") or "other"), "sender": sender,
        "chat": chat, "filename": filename, "name": name, "ext": ext, "size": str(get("file_size") or 0),
        "tag": tag or "untagged",
    }


def render(template: str, ctx: dict[str, str]) -> str:
    class Safe(dict):
        def __missing__(self, key: str) -> str:
            return "_"

    return template.format_map(Safe({k: v.replace("/", "_").replace("\\", "_") for k, v in ctx.items()}))


def build_relative_path(folder_template: str, file_template: str, ctx: dict[str, str]) -> Path:
    folder = render(folder_template, ctx) if folder_template.strip() else ""
    parts = [sanitize_component(p) for p in re.split(r"[\\/]+", folder) if p.strip()]
    file_name = render(file_template, ctx) if file_template.strip() else ctx["filename"]
    if "." not in file_name.rsplit("/", 1)[-1] or (not file_name.lower().endswith("." + ctx["ext"]) and "{filename}" not in file_template and "{ext}" not in file_template):
        file_name = f"{file_name}.{ctx['ext']}"
    parts.append(sanitize_component(file_name, fallback=f"file_{ctx['id']}.{ctx['ext']}"))
    return Path(*parts)


def unique_path(path: Path, taken: set[str] | None = None) -> Path:
    """Avoid collisions: ``name.ext`` → ``name (1).ext``."""
    taken = taken if taken is not None else set()
    candidate, i = path, 1
    while candidate.exists() or str(candidate).lower() in taken:
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        i += 1
    taken.add(str(candidate).lower())
    return candidate
