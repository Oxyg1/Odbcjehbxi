"""Сборка текстов уведомлений (HTML-разметка Telegram)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import MEDIA_KINDS, StoredMessage

TELEGRAM_LIMIT = 4096
CHUNK_LIMIT = 3800  # запас на служебные строки


def tzinfo(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return timezone.utc


def fmt_time(ts: int | None, tz_name: str) -> str:
    if not ts:
        return "неизвестно когда"
    return datetime.fromtimestamp(ts, tzinfo(tz_name)).strftime("%d.%m.%Y %H:%M:%S")


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def sender_label(record: StoredMessage) -> str:
    name = escape(record.sender_name or "неизвестный отправитель")
    if record.sender_username:
        name += f" (@{escape(record.sender_username)})"
    if record.outgoing:
        name += " — это ваше сообщение"
    return name


def chat_label(title: str, username: str | None) -> str:
    label = escape(title or "неизвестный чат")
    if username:
        label += f" (@{escape(username)})"
    return label


def media_label(record: StoredMessage) -> str:
    if not record.media_type:
        return ""
    human = MEDIA_KINDS.get(record.media_type, record.media_type)
    suffix = " 🔒(скрытое)" if record.extra.get("has_media_spoiler") else ""
    return f"📎 {escape(human)}{suffix}"


def quote_block(text: str, limit: int, empty: str = "<i>(без текста)</i>") -> str:
    if not text.strip():
        return empty
    return f"<blockquote>{escape(truncate(text, limit))}</blockquote>"


def message_block(record: StoredMessage, tz_name: str, preview_limit: int) -> str:
    """Один блок отчёта: кто, когда, что было в сообщении."""

    lines = [f"👤 <b>{sender_label(record)}</b> · {fmt_time(record.date, tz_name)}"]
    media = media_label(record)
    if media:
        lines.append(media)
    if record.edits:
        lines.append(f"✏️ было отредактировано ({record.edits})")
    lines.append(quote_block(record.text, preview_limit))
    return "\n".join(lines)


def edit_report(
    before: StoredMessage | None,
    after: StoredMessage,
    tz_name: str,
    preview_limit: int,
) -> str:
    """Уведомление об изменённом сообщении."""

    header = "✏️ <b>Сообщение изменено</b>"
    lines = [
        header,
        f"💬 Чат: <b>{chat_label(after.chat_title, after.chat_username)}</b>",
        f"👤 Автор: <b>{sender_label(after)}</b>",
        f"🕓 Отправлено: {fmt_time(after.date, tz_name)}",
        f"🕓 Изменено: {fmt_time(after.edited_at, tz_name)}",
    ]
    media = media_label(after)
    if media:
        lines.append(media)

    lines.append("\n<b>Было:</b>")
    if before is None:
        lines.append("<i>(бот не видел исходную версию)</i>")
    else:
        lines.append(quote_block(before.text, preview_limit))
    lines.append("<b>Стало:</b>")
    lines.append(quote_block(after.text, preview_limit))
    return "\n".join(lines)


def deletion_report(
    *,
    chat_title: str,
    chat_username: str | None,
    records: list[StoredMessage],
    unknown_count: int,
    hidden_own: int,
    chat_deleted: bool,
    tz_name: str,
    preview_limit: int,
    max_messages: int,
) -> list[str]:
    """Уведомление об удалении. Возвращает список сообщений (учитывая лимит Telegram)."""

    total = len(records) + unknown_count + hidden_own
    if chat_deleted:
        header = "🧨 <b>Похоже, удалена вся переписка</b>"
    elif total > 1:
        header = f"🗑 <b>Удалено сообщений: {total}</b>"
    else:
        header = "🗑 <b>Сообщение удалено</b>"

    intro = [
        header,
        f"💬 Чат: <b>{chat_label(chat_title, chat_username)}</b>",
    ]
    if hidden_own:
        intro.append(f"➕ из них ваших собственных: {hidden_own} (скрыты настройкой)")
    if unknown_count:
        intro.append(
            f"❔ ещё {unknown_count} сообщ. бот не видел — содержимое неизвестно"
        )

    shown = records[:max_messages]
    skipped = len(records) - len(shown)

    blocks = [message_block(record, tz_name, preview_limit) for record in shown]
    if skipped > 0:
        blocks.append(f"… и ещё {skipped} сообщ. не показаны, чтобы не спамить.")

    return _pack("\n".join(intro), blocks)


def _pack(intro: str, blocks: list[str]) -> list[str]:
    """Склеивает блоки в сообщения, не превышающие лимит Telegram."""

    messages: list[str] = []
    current = intro
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > CHUNK_LIMIT and current:
            messages.append(current)
            current = block if len(block) <= CHUNK_LIMIT else truncate(block, CHUNK_LIMIT)
        else:
            current = candidate
    if current:
        messages.append(current)
    return [m[:TELEGRAM_LIMIT] for m in messages]


def connection_report(
    *, enabled: bool, can_reply: bool, owner_name: str, tz_name: str
) -> str:
    if not enabled:
        return (
            "🔌 <b>Бот отключён от бизнес-аккаунта</b>\n"
            "Пока подключение выключено, уведомления об удалении и правках не приходят.\n"
            "Кэш сообщений сохранён — команда /purge удалит его."
        )
    lines = [
        "✅ <b>Бот подключён к бизнес-аккаунту</b>",
        f"👤 Владелец: <b>{escape(owner_name)}</b>",
        f"🕓 Время сервера: {fmt_time(int(datetime.now(tz=timezone.utc).timestamp()), tz_name)}",
        "",
        "Теперь я слежу за перепиской и пришлю сюда уведомление, если собеседник:",
        "• удалит сообщение — покажу текст и вложение;",
        "• изменит сообщение — покажу «было/стало»;",
        "• удалит всю переписку — пришлю сводку.",
        "",
        "⚠️ Я вижу только те сообщения, которые пришли <b>после</b> подключения — "
        "историю переписки Telegram боту не отдаёт.",
        "",
        "Команды: /status, /settings, /stats, /purge, /help",
    ]
    if not can_reply:
        lines.insert(
            2,
            "ℹ️ Права на ответ от вашего имени не выданы — для слежения это не нужно.",
        )
    return "\n".join(lines)
