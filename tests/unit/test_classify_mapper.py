from types import SimpleNamespace as NS

from arcivo.domain.classify import MediaFacts, classify
from arcivo.domain.models import Category, MediaType, MessageRecord
from arcivo.telegram.mapper import extract_links, to_record


def test_classify_documents():
    assert classify(MediaFacts(kind="document", is_audio=True, is_voice=True)) == MediaType.VOICE
    assert classify(MediaFacts(kind="document", is_audio=True)) == MediaType.AUDIO
    assert classify(MediaFacts(kind="document", is_video=True, is_round=True)) == MediaType.VIDEO_NOTE
    assert classify(MediaFacts(kind="document", is_animated=True, is_video=True)) == MediaType.ANIMATION
    assert classify(MediaFacts(kind="document", is_sticker=True)) == MediaType.STICKER
    assert classify(MediaFacts(kind="document", mime="application/pdf")) == MediaType.DOCUMENT
    assert classify(MediaFacts(kind="document", file_name="song.flac")) == MediaType.AUDIO
    assert classify(MediaFacts(kind=None, has_links=True)) == MediaType.LINK
    assert classify(MediaFacts(kind="webpage")) == MediaType.LINK


def test_category_for_image_document():
    r = MessageRecord(id=1, date_ts=0, media_type=MediaType.DOCUMENT, mime_type="image/png", file_name="a.PNG")
    assert r.category == Category.IMAGES and r.extension == "png"


def test_extract_links():
    links = extract_links("see https://a.com/x, and www.b.org! t.me/c", [NS(url="https://hidden.example")])
    assert links == ["https://hidden.example", "https://a.com/x", "www.b.org", "t.me/c"]


class PeerChannel:
    def __init__(self, channel_id):
        self.channel_id = channel_id


class MessageMediaDocument:
    def __init__(self, document):
        self.document = document


class DocumentAttributeAudio:
    def __init__(self, voice=False):
        self.voice = voice


class DocumentAttributeFilename:
    def __init__(self, file_name):
        self.file_name = file_name


def test_to_record_forwarded_channel_audio():
    from datetime import UTC, datetime
    doc = NS(id=55, dc_id=4, mime_type="audio/mpeg", thumbs=None,
             attributes=[DocumentAttributeAudio(), DocumentAttributeFilename("x.mp3")])
    msg = NS(id=9, date=datetime(2026, 1, 2, tzinfo=UTC), edit_date=None, message="nice https://x.io", entities=None,
             media=MessageMediaDocument(doc),
             file=NS(name="x.mp3", mime_type="audio/mpeg", size=1234, duration=61, width=None, height=None,
                     performer="P", title="T", ext=".mp3"),
             fwd_from=NS(from_id=PeerChannel(42), from_name=None, date=datetime(2025, 1, 1, tzinfo=UTC), channel_post=7,
                         saved_from_msg_id=None, saved_from_peer=None, post_author="Ed"),
             forward=NS(sender=None, chat=NS(title="Music Archive", username="musicarc")),
             saved_peer_id=None, reply_to=None, grouped_id=None, views=10, via_bot_id=None, noforwards=False, ttl_period=None)
    r = to_record(msg, me_id=1, me_name="Me")
    assert r.media_type == MediaType.AUDIO and r.file_size == 1234 and r.duration == 61
    assert r.chat_id == 42 and r.chat_name == "Music Archive" and r.chat_type == "channel"
    assert r.sender_name == "Ed" and r.is_forward and r.fwd_msg_id == 7
    assert r.links == ["https://x.io"] and r.media_id == 55
