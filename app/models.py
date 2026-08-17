"""Модель кэшируемого сообщения и извлечение данных из объектов Telegram."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Типы вложений: атрибут объекта Message -> человекочитаемое имя.
MEDIA_KINDS: dict[str, str] = {
    "photo": "фото",
    "video": "видео",
    "video_note": "видеосообщение (кружок)",
    "voice": "голосовое сообщение",
    "audio": "аудио",
    "animation": "GIF",
    "document": "документ",
    "sticker": "стикер",
    "story": "история",
    "contact": "контакт",
    "location": "геолокация",
    "venue": "место",
    "poll": "опрос",
    "dice": "игральная кость",
    "game": "игра",
    "invoice": "счёт",
    "paid_media": "платное медиа",
}

# Для каких типов имеет смысл пересылать файл обратно владельцу.
DOWNLOADABLE = {
    "photo",
    "video",
    "video_note",
    "voice",
    "audio",
    "animation",
    "document",
    "sticker",
}


@dataclass
class StoredMessage:
    """Снимок сообщения, который бот держит у себя, пока оно живо."""

    connection_id: str
    chat_id: int
    message_id: int
    chat_title: str
    chat_username: str | None
    sender_id: int | None
    sender_name: str
    sender_username: str | None
    outgoing: bool
    text: str
    media_type: str | None
    file_id: str | None
    file_unique_id: str | None
    file_size: int | None
    local_path: str | None
    date: int
    edited_at: int | None = None
    edits: int = 0
    deleted_at: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_media(self) -> bool:
        return self.media_type is not None


def user_display_name(user: Any) -> str:
    """Имя пользователя без username: 'Имя Фамилия' или 'ID 123'."""

    if user is None:
        return "неизвестный отправитель"
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    name = " ".join(part for part in parts if part)
    return name or f"ID {getattr(user, 'id', '?')}"


def chat_display_title(chat: Any) -> str:
    if chat is None:
        return "неизвестный чат"
    title = getattr(chat, "title", None)
    if title:
        return title
    parts = [getattr(chat, "first_name", None), getattr(chat, "last_name", None)]
    name = " ".join(part for part in parts if part)
    if name:
        return name
    username = getattr(chat, "username", None)
    if username:
        return f"@{username}"
    return f"чат {getattr(chat, 'id', '?')}"


def extract_media(message: Any) -> tuple[str | None, str | None, str | None, int | None]:
    """Возвращает (тип, file_id, file_unique_id, размер) первого найденного вложения."""

    for kind in MEDIA_KINDS:
        value = getattr(message, kind, None)
        if not value:
            continue
        if kind == "photo":
            # photo — список размеров, берём самый крупный.
            largest = value[-1]
            return kind, largest.file_id, largest.file_unique_id, largest.file_size
        file_id = getattr(value, "file_id", None)
        return (
            kind,
            file_id,
            getattr(value, "file_unique_id", None),
            getattr(value, "file_size", None),
        )
    return None, None, None, None


def extract_text(message: Any) -> str:
    """Текст сообщения либо подпись к медиа, либо краткое описание вложения."""

    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if text:
        return text

    poll = getattr(message, "poll", None)
    if poll is not None:
        options = ", ".join(option.text for option in poll.options)
        return f"Опрос: {poll.question}\nВарианты: {options}"

    contact = getattr(message, "contact", None)
    if contact is not None:
        name = " ".join(
            part for part in (contact.first_name, contact.last_name) if part
        )
        return f"Контакт: {name} {contact.phone_number}".strip()

    location = getattr(message, "location", None)
    if location is not None:
        return f"Геолокация: {location.latitude}, {location.longitude}"

    venue = getattr(message, "venue", None)
    if venue is not None:
        return f"Место: {venue.title}, {venue.address}"

    dice = getattr(message, "dice", None)
    if dice is not None:
        return f"{dice.emoji} — {dice.value}"

    sticker = getattr(message, "sticker", None)
    if sticker is not None and sticker.emoji:
        return f"Стикер {sticker.emoji}"

    return ""


def message_to_record(message: Any, owner_user_id: int | None) -> StoredMessage:
    """Собирает StoredMessage из aiogram-объекта Message бизнес-чата."""

    media_type, file_id, file_unique_id, file_size = extract_media(message)
    sender = message.from_user
    sender_id = getattr(sender, "id", None)

    return StoredMessage(
        connection_id=message.business_connection_id or "",
        chat_id=message.chat.id,
        message_id=message.message_id,
        chat_title=chat_display_title(message.chat),
        chat_username=getattr(message.chat, "username", None),
        sender_id=sender_id,
        sender_name=user_display_name(sender),
        sender_username=getattr(sender, "username", None),
        outgoing=bool(owner_user_id and sender_id == owner_user_id),
        text=extract_text(message),
        media_type=media_type,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_size=file_size,
        local_path=None,
        date=int(message.date.timestamp()) if message.date else 0,
        extra={
            "has_media_spoiler": bool(getattr(message, "has_media_spoiler", False)),
            "reply_to": getattr(getattr(message, "reply_to_message", None), "message_id", None),
            "forwarded": bool(getattr(message, "forward_origin", None)),
        },
    )
