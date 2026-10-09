"""Pure domain objects. No Telethon, Qt or SQLite imports here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MediaType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
    ANIMATION = "animation"  # GIF
    AUDIO = "audio"  # music
    VOICE = "voice"
    DOCUMENT = "document"  # generic file
    STICKER = "sticker"
    LINK = "link"  # text whose main payload is a URL / web preview
    CONTACT = "contact"
    LOCATION = "location"
    VENUE = "venue"
    POLL = "poll"
    DICE = "dice"
    GAME = "game"
    INVOICE = "invoice"
    STORY = "story"
    OTHER = "other"


class Category(StrEnum):
    """Storage categories (coarser than MediaType)."""

    IMAGES = "images"
    VIDEOS = "videos"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENTS = "documents"
    STICKERS = "stickers"
    TEXT = "text"
    OTHER = "other"


MEDIA_TYPE_CATEGORY: dict[MediaType, Category] = {
    MediaType.TEXT: Category.TEXT,
    MediaType.LINK: Category.TEXT,
    MediaType.PHOTO: Category.IMAGES,
    MediaType.VIDEO: Category.VIDEOS,
    MediaType.VIDEO_NOTE: Category.VIDEOS,
    MediaType.ANIMATION: Category.VIDEOS,
    MediaType.AUDIO: Category.AUDIO,
    MediaType.VOICE: Category.VOICE,
    MediaType.DOCUMENT: Category.DOCUMENTS,
    MediaType.STICKER: Category.STICKERS,
}

FILE_BEARING = {
    MediaType.PHOTO, MediaType.VIDEO, MediaType.VIDEO_NOTE, MediaType.ANIMATION, MediaType.AUDIO,
    MediaType.VOICE, MediaType.DOCUMENT, MediaType.STICKER,
}


def category_for(media_type: MediaType, mime: str | None = None) -> Category:
    if media_type == MediaType.DOCUMENT and mime:
        if mime.startswith("image/"):
            return Category.IMAGES
        if mime.startswith("video/"):
            return Category.VIDEOS
        if mime.startswith("audio/"):
            return Category.AUDIO
    return MEDIA_TYPE_CATEGORY.get(media_type, Category.OTHER)


@dataclass
class MessageRecord:
    """A normalized Saved Messages entry (local index row)."""

    id: int
    date_ts: int
    media_type: MediaType = MediaType.TEXT
    text: str = ""
    edit_ts: int | None = None
    category: Category | None = None
    file_name: str | None = None
    extension: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    performer: str | None = None
    audio_title: str | None = None
    media_id: int | None = None  # Telegram photo/document id (stable for identical uploads)
    dc_id: int | None = None
    sender_id: int | None = None
    sender_name: str | None = None
    sender_username: str | None = None
    chat_id: int | None = None
    chat_name: str | None = None
    chat_type: str | None = None  # user | group | channel | hidden
    is_forward: bool = False
    fwd_date_ts: int | None = None
    fwd_msg_id: int | None = None
    reply_to_id: int | None = None
    grouped_id: int | None = None
    saved_peer_id: int | None = None
    links: list[str] = field(default_factory=list)
    views: int | None = None
    has_thumb: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.media_type, str):
            self.media_type = MediaType(self.media_type)
        if self.category is None:
            self.category = category_for(self.media_type, self.mime_type)
        if self.file_name and not self.extension:
            self.extension = extension_of(self.file_name)

    @property
    def has_file(self) -> bool:
        return self.media_type in FILE_BEARING


def extension_of(name: str | None) -> str | None:
    if not name or "." not in name:
        return None
    ext = name.rsplit(".", 1)[-1].lower().strip()
    return ext if 0 < len(ext) <= 10 and ext.isalnum() else None


@dataclass
class AccountInfo:
    user_id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    phone: str | None = None
    is_premium: bool = False
    dc_id: int | None = None
    lang_code: str | None = None

    @property
    def display_name(self) -> str:
        return (f"{self.first_name} {self.last_name}").strip() or (self.username or str(self.user_id))


@dataclass
class Tag:
    id: int
    name: str
    color: str = "#7C83FD"
    description: str = ""
    count: int = 0


@dataclass
class SmartCollection:
    id: int
    name: str
    query: str
    icon: str = "sparkles"
    color: str = "#7C83FD"
    pinned: bool = True
    sort_key: str = "date"
    sort_desc: bool = True
    description: str = ""
    count: int | None = None
