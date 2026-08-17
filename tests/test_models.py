from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import Chat, Contact, Message, PhotoSize, User, Voice

from app.models import extract_media, extract_text, message_to_record

CHAT = Chat(id=-100, type="private", first_name="Иван", username="ivan")
SENDER = User(id=555, is_bot=False, first_name="Иван", username="ivan")
OWNER = User(id=42, is_bot=False, first_name="Владелец")


def build(**kwargs) -> Message:
    payload = dict(
        message_id=1,
        date=datetime.now(tz=timezone.utc),
        chat=CHAT,
        from_user=SENDER,
        business_connection_id="conn",
    )
    payload.update(kwargs)
    return Message(**payload)


def test_extract_text_prefers_text_then_caption():
    assert extract_text(build(text="привет")) == "привет"
    photo = [PhotoSize(file_id="F", file_unique_id="U", width=1, height=1, file_size=10)]
    assert extract_text(build(photo=photo, caption="подпись")) == "подпись"


def test_extract_text_describes_contact():
    contact = Contact(phone_number="+79990000000", first_name="Пётр")
    assert "Пётр" in extract_text(build(contact=contact))


def test_extract_media_picks_largest_photo():
    photo = [
        PhotoSize(file_id="small", file_unique_id="u1", width=90, height=90, file_size=1),
        PhotoSize(file_id="big", file_unique_id="u2", width=1280, height=720, file_size=99),
    ]
    kind, file_id, unique, size = extract_media(build(photo=photo))
    assert (kind, file_id, unique, size) == ("photo", "big", "u2", 99)


def test_extract_media_none_for_plain_text():
    assert extract_media(build(text="привет")) == (None, None, None, None)


def test_message_to_record_marks_outgoing():
    incoming = message_to_record(build(text="привет"), owner_user_id=42)
    assert incoming.outgoing is False
    assert incoming.sender_name == "Иван"
    assert incoming.chat_title == "Иван"

    outgoing = message_to_record(build(text="ответ", from_user=OWNER), owner_user_id=42)
    assert outgoing.outgoing is True


def test_message_to_record_keeps_media_fields():
    voice = Voice(file_id="V", file_unique_id="UV", duration=3, file_size=1024)
    record = message_to_record(build(voice=voice), owner_user_id=42)
    assert record.media_type == "voice"
    assert record.file_id == "V"
    assert record.file_size == 1024
    assert record.is_media is True
