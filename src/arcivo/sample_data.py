"""Deterministic synthetic Saved Messages for tests, CI, screenshots and demo mode.

No real Telegram data is used. Names are fictional.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from .domain.models import MediaType, MessageRecord

SENDERS = [(1001, "Sarah Chen", "sarahc"), (1002, "Alex Morgan", "alexm"), (1003, "Ryan Brooks", "rbrooks"),
           (1004, "Emma Wilson", None), (1005, "Daniel Kim", "dkim")]
CHATS = [(-1001, "Design Weekly", "channel"), (-1002, "Podcast Picks", "channel"), (-1003, "Dev Notes", "channel"),
         (-1004, "Family Group", "group"), (-1005, "Music Archive", "channel"), (-1006, "Tech Digest", "channel")]
TEXTS = ["Meeting notes for Q3 planning", "Remember to renew the domain", "Kickoff checklist for the new project",
         "Recipe: lemon herb risotto", "Invoice for September", "Ideas for the next release",
         "Grocery list for the week", "Book recommendations: Deep Work, Atomic Habits", "Flight PNR and hotel booking",
         "Bookstore discount code: READMORE", "Workout plan — week 4", "Quote: Simplicity is the ultimate sophistication."]
LINKS = ["https://github.com/sadult/arcivo", "https://core.telegram.org/api", "https://www.figma.com/community",
         "https://news.ycombinator.com/item?id=1", "https://en.wikipedia.org/wiki/Typography", "https://youtu.be/dQw4w9WgXcQ"]
DOCS = [("Annual_Report_2025.pdf", "application/pdf", "pdf"), ("contract-final.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
        ("budget.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
        ("backup.zip", "application/zip", "zip"), ("slides.pptx", "application/vnd.ms-powerpoint", "pptx"),
        ("ebook_field_guide.pdf", "application/pdf", "pdf"), ("setup.exe", "application/x-msdownload", "exe")]
SONGS = [("Hania Rani", "Eden"), ("Nils Frahm", "Says"), ("Ólafur Arnalds", "saman"),
         ("Brian Eno", "An Ending (Ascent)"), ("Max Richter", "On the Nature of Daylight")]
WEIGHTS = [(MediaType.TEXT, 24), (MediaType.LINK, 9), (MediaType.PHOTO, 22), (MediaType.VIDEO, 9), (MediaType.DOCUMENT, 12),
           (MediaType.AUDIO, 8), (MediaType.VOICE, 7), (MediaType.STICKER, 3), (MediaType.ANIMATION, 3),
           (MediaType.VIDEO_NOTE, 1), (MediaType.LOCATION, 1), (MediaType.CONTACT, 1), (MediaType.POLL, 0.5)]


def generate(n: int = 2000, seed: int = 7, end: datetime | None = None, years: float = 3.0) -> list[MessageRecord]:
    rnd = random.Random(seed)
    end = end or datetime(2026, 10, 1, tzinfo=UTC)
    start = end - timedelta(days=int(365 * years))
    span = (end - start).total_seconds()
    types = [t for t, _ in WEIGHTS]
    weights = [w for _, w in WEIGHTS]
    out: list[MessageRecord] = []
    stamps = sorted(start.timestamp() + span * (rnd.random() ** 0.7) for _ in range(n))
    group_id = None
    for i, ts in enumerate(stamps, start=1):
        dt = datetime.fromtimestamp(ts, tz=UTC)
        hour = int(rnd.triangular(7, 24, 21)) % 24  # people save more in the evening
        dt = dt.replace(hour=hour, minute=rnd.randrange(60))
        t = rnd.choices(types, weights)[0]
        fwd = rnd.random() < 0.55
        sender = rnd.choice(SENDERS) if fwd and rnd.random() < 0.45 else None
        chat = rnd.choice(CHATS) if fwd and sender is None else None
        rec = MessageRecord(id=i, date_ts=int(dt.timestamp()), media_type=t, is_forward=fwd)
        if sender:
            rec.sender_id, rec.sender_name, rec.sender_username, rec.chat_type = sender[0], sender[1], sender[2], "user"
        elif chat:
            rec.chat_id, rec.chat_name, rec.chat_type = chat
        else:
            rec.sender_id, rec.sender_name, rec.sender_username = 777000001, "Demo User", "arcivo_demo"
        if t in (MediaType.TEXT, MediaType.LINK):
            rec.text = rnd.choice(TEXTS)
            if t == MediaType.LINK:
                url = rnd.choice(LINKS)
                rec.text = f"{rec.text}\n{url}"
                rec.links = [url]
        elif t == MediaType.PHOTO:
            rec.file_size, rec.width, rec.height = rnd.randint(60_000, 4_500_000), rnd.choice([1280, 1920, 2560]), rnd.choice([720, 1080, 1440])
            rec.mime_type, rec.extension, rec.media_id = "image/jpeg", "jpg", 9_000_000 + rnd.randint(0, n * 3)
            rec.text = rnd.choice(["", "", "Sunset at the lake", "Whiteboard from today", "Important screenshot"])
            rec.has_thumb = True
            if rnd.random() < 0.15:
                group_id = group_id or rnd.randint(10**12, 10**13)
                rec.grouped_id = group_id
            else:
                group_id = None
        elif t in (MediaType.VIDEO, MediaType.VIDEO_NOTE, MediaType.ANIMATION):
            rec.duration = float(rnd.choice([8, 35, 95, 300, 780, 1800, 3600])) if t != MediaType.ANIMATION else float(rnd.randint(2, 9))
            rec.file_size = int(rec.duration * rnd.randint(60_000, 400_000))
            rec.width, rec.height = (640, 640) if t == MediaType.VIDEO_NOTE else (1920, 1080)
            rec.mime_type, rec.extension = "video/mp4", "mp4"
            rec.file_name = f"video_{i}.mp4" if t == MediaType.VIDEO and rnd.random() < 0.6 else None
            rec.media_id, rec.has_thumb = 8_000_000 + rnd.randint(0, n * 3), True
        elif t == MediaType.DOCUMENT:
            name, mime, ext = rnd.choice(DOCS)
            rec.file_name, rec.mime_type, rec.extension = name, mime, ext
            rec.file_size = rnd.randint(40_000, 180_000_000 if ext in ("zip", "exe") else 25_000_000)
            rec.media_id = 7_000_000 + rnd.randint(0, n // 4)
        elif t == MediaType.AUDIO:
            perf, title = rnd.choice(SONGS)
            rec.performer, rec.audio_title, rec.duration = perf, title, float(rnd.randint(150, 720))
            rec.file_name, rec.mime_type, rec.extension = f"{perf} - {title}.mp3", "audio/mpeg", "mp3"
            rec.file_size = int(rec.duration * 40_000)
            rec.media_id = 6_000_000 + rnd.randint(0, n // 5)
        elif t == MediaType.VOICE:
            rec.duration = float(rnd.randint(2, 240))
            rec.file_size, rec.mime_type, rec.extension = int(rec.duration * 4_000), "audio/ogg", "ogg"
        elif t == MediaType.STICKER:
            rec.file_size, rec.mime_type, rec.extension, rec.file_name = rnd.randint(8_000, 60_000), "image/webp", "webp", "sticker.webp"
            rec.media_id = 5_000_000 + rnd.randint(0, 40)
        elif t == MediaType.LOCATION:
            rec.extra = {"geo": {"lat": 35.6892, "long": 51.389}}
        elif t == MediaType.CONTACT:
            rec.extra = {"contact": {"first_name": "Support", "last_name": "Desk"}}
        elif t == MediaType.POLL:
            rec.extra = {"poll_question": "Which logo do you prefer?"}
        if rec.file_size and rec.mime_type is None:
            rec.mime_type = "application/octet-stream"
        rec.__post_init__()
        out.append(rec)
    return out
