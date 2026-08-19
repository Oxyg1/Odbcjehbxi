"""Formatting helpers, keyboards, and export utilities for the bot layer."""

import csv
import io
import json

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from checker import Availability, CheckResult
from generator import LENGTH_PRESETS, VALID_STYLES

STYLE_LABELS = {
    "elegant": "✨ Elegant",
    "brand": "🏷 Brand",
    "mythic": "🐉 Mythic",
    "tech": "🤖 Tech",
    "vibes": "💫 Vibes",
}

STATUS_EMOJI = {
    Availability.FREE: "✅",
    Availability.TAKEN: "❌",
    Availability.FRAGMENT_FOR_SALE: "💎",
    Availability.UNKNOWN: "❔",
}

STATUS_TEXT = {
    Availability.FREE: "Свободен",
    Availability.TAKEN: "Занят",
    Availability.FRAGMENT_FOR_SALE: "Доступен на Fragment",
    Availability.UNKNOWN: "Не удалось проверить",
}


def overall_status(result: CheckResult) -> Availability:
    # A username taken on *either* source is taken -- t.me and fragment.com track
    # independent states, so a "free" telegram result doesn't override a taken/
    # for-sale fragment result (and vice versa for TAKEN).
    if result.telegram.availability == Availability.TAKEN or result.fragment.availability == Availability.TAKEN:
        return Availability.TAKEN
    if result.fragment.availability == Availability.FRAGMENT_FOR_SALE:
        return Availability.FRAGMENT_FOR_SALE
    if result.telegram.availability == Availability.FREE and result.fragment.availability in (
        Availability.FREE,
        Availability.UNKNOWN,
    ):
        return Availability.FREE
    return Availability.UNKNOWN


def format_result_line(index: int, result: CheckResult) -> str:
    status = overall_status(result)
    emoji = STATUS_EMOJI[status]
    text = STATUS_TEXT[status]

    def _source_text(source) -> str:
        base = STATUS_TEXT[source.availability]
        if source.availability == Availability.FRAGMENT_FOR_SALE and source.detail:
            return f"{base} (~{source.detail})"
        if source.availability == Availability.UNKNOWN and source.detail:
            return f"{base} ({source.detail})"
        return base

    details = f"t.me: {_source_text(result.telegram)} | fragment: {_source_text(result.fragment)}"
    return f"{index}. @{result.username}    {emoji} {text}\n    {details}"


def build_results_message(style: str, results: list[CheckResult]) -> str:
    header = f"✨ Сгенерировано {len(results)} username в стиле {STYLE_LABELS.get(style, style)}:\n"
    lines = [format_result_line(i, r) for i, r in enumerate(results, start=1)]
    footer = "\n💡 Нажми на @username чтобы скопировать. Используй /check @username для повторной проверки."
    return header + "\n" + "\n".join(lines) + footer


def style_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for style in VALID_STYLES:
        builder.button(text=STYLE_LABELS[style], callback_data=f"style:{style}")
    builder.adjust(2)
    return builder.as_markup()


def length_selection_keyboard(style: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, min_length, max_length in LENGTH_PRESETS:
        builder.button(text=label, callback_data=f"length:{style}:{min_length}:{max_length}")
    builder.adjust(4)
    return builder.as_markup()


def count_selection_keyboard(style: str, min_length: int, max_length: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for count in (5, 10, 15, 20):
        builder.button(text=str(count), callback_data=f"count:{style}:{min_length}:{max_length}:{count}")
    builder.adjust(4)
    return builder.as_markup()


def result_actions_keyboard(style: str, min_length: int, max_length: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Ещё", callback_data=f"count:{style}:{min_length}:{max_length}:5")
    builder.button(text="📤 Экспорт CSV", callback_data=f"export:csv:{style}")
    builder.button(text="📤 Экспорт JSON", callback_data=f"export:json:{style}")
    builder.adjust(1)
    return builder.as_markup()


def export_to_csv(results: list[CheckResult]) -> io.BytesIO:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["username", "status", "telegram_detail", "fragment_detail"])
    for r in results:
        writer.writerow([r.username, overall_status(r).value, r.telegram.detail, r.fragment.detail])
    data = io.BytesIO(buf.getvalue().encode("utf-8"))
    data.name = "usernames.csv"
    return data


def export_to_json(results: list[CheckResult]) -> io.BytesIO:
    payload = [
        {
            "username": r.username,
            "status": overall_status(r).value,
            "telegram": {"status": r.telegram.availability.value, "detail": r.telegram.detail},
            "fragment": {"status": r.fragment.availability.value, "detail": r.fragment.detail},
            "checked_at": r.checked_at,
        }
        for r in results
    ]
    data = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    data.name = "usernames.json"
    return data
