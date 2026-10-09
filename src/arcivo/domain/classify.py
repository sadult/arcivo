"""Media classification from simple, Telethon-agnostic facts (unit-testable)."""

from __future__ import annotations

from dataclasses import dataclass

from .models import MediaType

AUDIO_EXT = {"mp3", "m4a", "flac", "wav", "ogg", "opus", "aac", "wma", "alac", "ape"}
VIDEO_EXT = {"mp4", "mkv", "mov", "avi", "webm", "wmv", "flv", "m4v", "3gp"}


@dataclass
class MediaFacts:
    kind: str | None = None  # photo | document | webpage | contact | geo | venue | poll | dice | game | invoice | story | other
    mime: str | None = None
    is_sticker: bool = False
    is_animated: bool = False  # DocumentAttributeAnimated (GIF)
    is_video: bool = False
    is_round: bool = False
    is_audio: bool = False
    is_voice: bool = False
    file_name: str | None = None
    has_links: bool = False


def classify(f: MediaFacts) -> MediaType:
    if f.kind is None:
        return MediaType.LINK if f.has_links else MediaType.TEXT
    simple = {
        "photo": MediaType.PHOTO, "contact": MediaType.CONTACT, "geo": MediaType.LOCATION,
        "venue": MediaType.VENUE, "poll": MediaType.POLL, "dice": MediaType.DICE, "game": MediaType.GAME,
        "invoice": MediaType.INVOICE, "story": MediaType.STORY,
    }
    if f.kind in simple:
        return simple[f.kind]
    if f.kind == "webpage":
        return MediaType.LINK
    if f.kind != "document":
        return MediaType.OTHER
    mime = (f.mime or "").lower()
    if f.is_sticker or mime in ("application/x-tgsticker", "application/x-tgsticker+json"):
        return MediaType.STICKER
    if f.is_animated or mime == "image/gif":
        return MediaType.ANIMATION
    if f.is_video:
        return MediaType.VIDEO_NOTE if f.is_round else MediaType.VIDEO
    if f.is_audio:
        return MediaType.VOICE if f.is_voice else MediaType.AUDIO
    ext = (f.file_name or "").rsplit(".", 1)[-1].lower() if f.file_name and "." in f.file_name else ""
    if mime.startswith("audio/") or ext in AUDIO_EXT:
        return MediaType.AUDIO
    if mime.startswith("video/") or ext in VIDEO_EXT:
        return MediaType.VIDEO
    return MediaType.DOCUMENT
