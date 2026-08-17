"""Команды в личном чате с ботом: помощь, статус, настройки, статистика."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from ..formatters import fmt_time
from ..tracker import Tracker

SETTING_LABELS = {
    "notify_deletes": "🗑 Уведомлять об удалении",
    "notify_edits": "✏️ Уведомлять о правках",
    "include_own": "🙋 Учитывать мои сообщения",
    "backup_media": "📎 Сохранять вложения",
    "silent": "🔕 Без звука",
}

HELP_TEXT = (
    "🤖 <b>Бот-сторож для Telegram Business</b>\n\n"
    "Я слежу за перепиской вашего бизнес-аккаунта и присылаю сюда уведомление, если "
    "собеседник удалил сообщение, изменил его или удалил всю переписку.\n\n"
    "<b>Как подключить:</b>\n"
    "1. Telegram → Настройки → <b>Telegram для бизнеса</b> → <b>Чат-боты</b>\n"
    "2. Впишите юзернейм этого бота и подтвердите.\n"
    "3. Готово — я пришлю сюда сообщение о подключении.\n\n"
    "<b>Команды:</b>\n"
    "/status — состояние подключения\n"
    "/settings — что и как уведомлять\n"
    "/stats — сколько сообщений в кэше\n"
    "/purge — стереть кэш сообщений\n"
    "/help — эта справка\n\n"
    "⚠️ Важно: Telegram отдаёт боту только сообщения, пришедшие <b>после</b> подключения, "
    "и не отдаёт содержимое исчезающих сообщений. Всё, что я показываю после удаления, — "
    "это моя собственная копия, поэтому кэш и надо хранить."
)


def settings_keyboard(settings: dict[str, bool]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if settings.get(key) else '❌'} {label}",
                callback_data=f"toggle:{key}",
            )
        ]
        for key, label in SETTING_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_router() -> Router:
    router = Router(name="commands")
    router.message.filter(F.chat.type == "private")

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            HELP_TEXT, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message, tracker: Tracker) -> None:
        connections = await tracker.storage.get_connections_for_owner(message.from_user.id)
        if not connections:
            await message.answer(
                "🔌 Бизнес-подключение не найдено.\n\n"
                "Подключите бота: Telegram → Настройки → Telegram для бизнеса → Чат-боты."
            )
            return

        lines = ["🔌 <b>Подключения</b>"]
        for connection in connections:
            state = "включено ✅" if connection["is_enabled"] else "выключено ⛔"
            lines += [
                "",
                f"• ID: <code>{escape(connection['connection_id'])}</code>",
                f"  Состояние: {state}",
                f"  Ответы от вашего имени: {'да' if connection['can_reply'] else 'нет'}",
                f"  Обновлено: {fmt_time(connection['updated_at'], tracker.config.timezone)}",
            ]

        settings = await tracker.settings_for(message.from_user.id)
        lines += [
            "",
            "<b>Настройки:</b> "
            + ", ".join(
                f"{label.split(' ', 1)[1]} — {'вкл' if settings.get(key) else 'выкл'}"
                for key, label in SETTING_LABELS.items()
            ),
        ]
        await message.answer("\n".join(lines))

    @router.message(Command("settings"))
    async def cmd_settings(message: Message, tracker: Tracker) -> None:
        settings = await tracker.settings_for(message.from_user.id)
        await message.answer(
            "⚙️ <b>Настройки уведомлений</b>\nНажмите, чтобы переключить.",
            reply_markup=settings_keyboard(settings),
        )

    @router.callback_query(F.data.startswith("toggle:"))
    async def on_toggle(callback: CallbackQuery, tracker: Tracker) -> None:
        key = callback.data.split(":", 1)[1]
        if key not in SETTING_LABELS:
            await callback.answer("Неизвестная настройка")
            return

        settings = await tracker.settings_for(callback.from_user.id)
        new_value = not settings.get(key, False)
        await tracker.storage.set_setting(callback.from_user.id, key, new_value)
        settings[key] = new_value

        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=settings_keyboard(settings)
            )
        await callback.answer(
            f"{SETTING_LABELS[key]}: {'включено' if new_value else 'выключено'}"
        )

    @router.message(Command("stats"))
    async def cmd_stats(message: Message, tracker: Tracker) -> None:
        stats = await tracker.storage.stats(message.from_user.id)
        retention = tracker.config.retention_days
        await message.answer(
            "📊 <b>Статистика кэша</b>\n"
            f"Сообщений сохранено: <b>{stats['total']}</b>\n"
            f"Из них удалено собеседниками: <b>{stats['deleted']}</b>\n"
            f"Редактировалось: <b>{stats['edited']}</b>\n"
            f"Чатов: <b>{stats['chats']}</b>\n\n"
            + (
                f"Срок хранения: {retention} дн."
                if retention > 0
                else "Срок хранения: без ограничения."
            )
        )

    @router.message(Command("purge"))
    async def cmd_purge(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🗑 Да, стереть", callback_data="purge:yes"),
                    InlineKeyboardButton(text="Отмена", callback_data="purge:no"),
                ]
            ]
        )
        await message.answer(
            "Стереть весь кэш сообщений и сохранённые вложения?\n"
            "После этого я не смогу показать содержимое сообщений, удалённых ранее.",
            reply_markup=keyboard,
        )

    @router.callback_query(F.data.startswith("purge:"))
    async def on_purge(callback: CallbackQuery, tracker: Tracker) -> None:
        if callback.data.endswith(":no"):
            if isinstance(callback.message, Message):
                await callback.message.edit_text("Отменено — кэш на месте.")
            await callback.answer()
            return

        removed, paths = await tracker.storage.purge_owner(callback.from_user.id)
        files = tracker.vault.remove_files(paths)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"🧹 Готово. Удалено записей: <b>{removed}</b>, файлов: <b>{files}</b>."
            )
        await callback.answer("Кэш очищен")

    return router
