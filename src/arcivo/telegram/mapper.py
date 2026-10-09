"""Convert Telethon ``Message`` objects into :class:`MessageRecord`."""

from __future__ import annotations

import re
from typing import Any

from ..domain.classify import MediaFacts, classify
from ..domain.models import MessageRecord, extension_of

URL_RE = re.compile(r"(?i)\b((?:https?://|www\.|t\.me/)[^\s<>\"'«»“”]+)")


def extract_links(text: str, entities: list[Any] | None = None) -> list[str]:
    links: list[str] = []
    if entities:
        for e in entities:
            url = getattr(e, "url", None)
            if url:
                links.append(url)
    for m in URL_RE.finditer(text or ""):
        links.append(m.group(1).rstrip(").,;!?»"))
    return list(dict.fromkeys(links))


def _peer_kind(peer: Any) -> tuple[int | None, str | None]:
    if peer is None:
        return None, None
    name = type(peer).__name__
    if name == "PeerUser":
        return peer.user_id, "user"
    if name == "PeerChannel":
        return peer.channel_id, "channel"
    if name == "PeerChat":
        return peer.chat_id, "group"
    return None, None


def _display(entity: Any) -> tuple[str | None, str | None]:
    if entity is None:
        return None, None
    title = getattr(entity, "title", None)
    if title:
        return title, getattr(entity, "username", None)
    first = getattr(entity, "first_name", "") or ""
    last = getattr(entity, "last_name", "") or ""
    return (f"{first} {last}".strip() or None), getattr(entity, "username", None)


def media_facts(msg: Any) -> MediaFacts:
    media = getattr(msg, "media", None)
    facts = MediaFacts()
    if media is None:
        return facts
    kind = type(media).__name__
    mapping = {
        "MessageMediaPhoto": "photo", "MessageMediaDocument": "document", "MessageMediaWebPage": "webpage",
        "MessageMediaContact": "contact", "MessageMediaGeo": "geo", "MessageMediaGeoLive": "geo",
        "MessageMediaVenue": "venue", "MessageMediaPoll": "poll", "MessageMediaDice": "dice",
        "MessageMediaGame": "game", "MessageMediaInvoice": "invoice", "MessageMediaStory": "story",
    }
    facts.kind = mapping.get(kind, "other")
    if facts.kind == "photo" and getattr(media, "photo", None) is None:
        facts.kind = "other"  # expired self-destructing photo
    doc = getattr(media, "document", None)
    if facts.kind == "document":
        if doc is None:
            facts.kind = "other"
            return facts
        facts.mime = getattr(doc, "mime_type", None)
        for a in getattr(doc, "attributes", []) or []:
            an = type(a).__name__
            if an == "DocumentAttributeSticker" or an == "DocumentAttributeCustomEmoji":
                facts.is_sticker = True
            elif an == "DocumentAttributeAnimated":
                facts.is_animated = True
            elif an == "DocumentAttributeVideo":
                facts.is_video = True
                facts.is_round = bool(getattr(a, "round_message", False))
            elif an == "DocumentAttributeAudio":
                facts.is_audio = True
                facts.is_voice = bool(getattr(a, "voice", False))
            elif an == "DocumentAttributeFilename":
                facts.file_name = a.file_name
    return facts


def to_record(msg: Any, me_id: int | None = None, me_name: str | None = None, me_username: str | None = None) -> MessageRecord:
    text = getattr(msg, "message", "") or ""
    links = extract_links(text, getattr(msg, "entities", None))
    facts = media_facts(msg)
    facts.has_links = bool(links)
    media_type = classify(facts)

    f = getattr(msg, "file", None) if facts.kind in ("photo", "document") else None
    file_name = getattr(f, "name", None) if f else None
    mime = getattr(f, "mime_type", None) if f else None
    size = getattr(f, "size", None) if f else None
    duration = getattr(f, "duration", None) if f else None
    width = getattr(f, "width", None) if f else None
    height = getattr(f, "height", None) if f else None
    performer = getattr(f, "performer", None) if f else None
    title = getattr(f, "title", None) if f else None
    ext = extension_of(file_name) or ((getattr(f, "ext", "") or "").lstrip(".").lower() or None if f else None)

    media = getattr(msg, "media", None)
    obj = getattr(media, "photo", None) or getattr(media, "document", None)
    media_id = getattr(obj, "id", None)
    dc_id = getattr(obj, "dc_id", None)
    has_thumb = bool(getattr(obj, "thumbs", None) or (facts.kind == "photo"))

    fwd = getattr(msg, "fwd_from", None)
    sender_id, sender_name, sender_username = me_id, me_name, me_username
    chat_id = chat_name = chat_type = None
    is_forward = fwd is not None
    fwd_date_ts = fwd_msg_id = None
    if fwd is not None:
        fwd_date = getattr(fwd, "date", None)
        fwd_date_ts = int(fwd_date.timestamp()) if fwd_date else None
        fwd_msg_id = getattr(fwd, "channel_post", None) or getattr(fwd, "saved_from_msg_id", None)
        pid, ptype = _peer_kind(getattr(fwd, "from_id", None))
        forward = getattr(msg, "forward", None)
        ent_sender = getattr(forward, "sender", None) if forward else None
        ent_chat = getattr(forward, "chat", None) if forward else None
        if ptype == "user":
            sender_id = pid
            sender_name, sender_username = _display(ent_sender)
        elif ptype in ("channel", "group"):
            chat_id, chat_type = pid, ptype
            chat_name, _ = _display(ent_chat)
            sender_id, sender_name, sender_username = None, getattr(fwd, "post_author", None), None
        else:
            sender_id, sender_name, sender_username = None, getattr(fwd, "from_name", None), None
            chat_type = "hidden"
        saved_from = getattr(fwd, "saved_from_peer", None)
        if saved_from is not None and chat_id is None:
            cid, ctype = _peer_kind(saved_from)
            if ctype in ("channel", "group"):
                chat_id, chat_type = cid, ctype
        if sender_name is None and getattr(fwd, "from_name", None):
            sender_name = fwd.from_name
    saved_peer_id, _ = _peer_kind(getattr(msg, "saved_peer_id", None))
    reply = getattr(msg, "reply_to", None)
    edit_date = getattr(msg, "edit_date", None)
    extra: dict[str, Any] = {}
    webpage = getattr(media, "webpage", None) if facts.kind == "webpage" else None
    if webpage is not None and getattr(webpage, "url", None):
        extra["webpage"] = {"url": webpage.url, "site": getattr(webpage, "site_name", None), "title": getattr(webpage, "title", None)}
        if webpage.url not in links:
            links.append(webpage.url)
    if getattr(msg, "via_bot_id", None):
        extra["via_bot_id"] = msg.via_bot_id
    if getattr(msg, "noforwards", False):
        extra["noforwards"] = True
    if getattr(msg, "ttl_period", None):
        extra["ttl_period"] = msg.ttl_period
    if fwd is not None and getattr(fwd, "from_name", None):
        extra["fwd_from_name"] = fwd.from_name
    if media_type.value == "poll":
        poll = getattr(getattr(media, "poll", None), "question", None)
        q = getattr(poll, "text", poll)
        if q:
            extra["poll_question"] = str(q)
    if media_type.value in ("location", "venue"):
        geo = getattr(media, "geo", None)
        if geo is not None and hasattr(geo, "lat"):
            extra["geo"] = {"lat": geo.lat, "long": geo.long}
    if media_type.value == "contact":
        extra["contact"] = {"first_name": getattr(media, "first_name", ""), "last_name": getattr(media, "last_name", "")}

    return MessageRecord(
        id=msg.id, date_ts=int(msg.date.timestamp()), edit_ts=int(edit_date.timestamp()) if edit_date else None,
        media_type=media_type, text=text, file_name=file_name, extension=ext, mime_type=mime, file_size=size,
        duration=float(duration) if duration is not None else None, width=width, height=height, performer=performer,
        audio_title=title, media_id=media_id, dc_id=dc_id, sender_id=sender_id, sender_name=sender_name,
        sender_username=sender_username, chat_id=chat_id, chat_name=chat_name, chat_type=chat_type, is_forward=is_forward,
        fwd_date_ts=fwd_date_ts, fwd_msg_id=fwd_msg_id, reply_to_id=getattr(reply, "reply_to_msg_id", None),
        grouped_id=getattr(msg, "grouped_id", None), saved_peer_id=saved_peer_id, links=links,
        views=getattr(msg, "views", None), has_thumb=has_thumb, extra=extra,
    )
