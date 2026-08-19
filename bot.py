"""Telegram bot entrypoint (aiogram 3.x)."""

import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from checker import Availability, CheckResult, checker
from config import config, validate_config
from database import db
from generator import MAX_LENGTH, MIN_LENGTH, VALID_STYLES, generate_usernames, is_valid_telegram_username
from utils import (
    STYLE_LABELS,
    build_results_message,
    count_selection_keyboard,
    export_to_csv,
    export_to_json,
    format_result_line,
    length_selection_keyboard,
    overall_status,
    result_actions_keyboard,
    style_selection_keyboard,
)

logger = logging.getLogger("bot")
router = Router()

# In-memory cache of each user's last result set, used for export/favorite buttons.
_last_results: dict[int, list[CheckResult]] = {}

# Only genuinely free usernames are shown to the user (taken and Fragment-for-sale
# candidates are discarded), so we generate+check in batches until we have `count`
# free ones. There's no cap tied to the requested count -- it keeps going as long as
# the generator can still produce new, not-yet-checked candidates for this style and
# length. _MAX_CANDIDATES_HARD_CAP is only a sanity backstop against a pathological
# run (e.g. a style/length pool that's effectively unbounded and never yields a free
# hit); it's high enough that no realistic request should ever reach it.
_GENERATE_BATCH_SIZE = 20
_MAX_CANDIDATES_HARD_CAP = 5000


async def _generate_and_check(
    style: str, count: int, min_length: int, max_length: int, progress: Message | None = None
) -> list[CheckResult]:
    free_results: list[CheckResult] = []
    seen: set[str] = set()

    while len(free_results) < count and len(seen) < _MAX_CANDIDATES_HARD_CAP:
        batch_count = min(_GENERATE_BATCH_SIZE, _MAX_CANDIDATES_HARD_CAP - len(seen))
        candidates = [
            name for name in generate_usernames(style, batch_count, min_length, max_length) if name not in seen
        ]
        if not candidates:
            # The generator can't produce anything new for this style/length -- the
            # whole pool of possible usernames has been exhausted and checked.
            break
        seen.update(candidates)

        checked = await checker.check_many(candidates)
        free_results.extend(r for r in checked if overall_status(r) == Availability.FREE)

        if progress is not None:
            try:
                await progress.edit_text(
                    f"🔄 Проверено {len(seen)} вариантов, найдено {len(free_results)} свободных из {count}..."
                )
            except Exception:
                pass  # message text unchanged or edited too often -- not critical

    return free_results[:count]


async def _send_results(
    message: Message, user_id: int, style: str, min_length: int, max_length: int, results: list[CheckResult]
) -> None:
    _last_results[user_id] = results
    await db.add_history_batch(
        user_id,
        [(r.username, style, overall_status(r).value) for r in results],
    )
    text = build_results_message(style, results)
    await message.answer(
        text, reply_markup=result_actions_keyboard(style, min_length, max_length), parse_mode="HTML"
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я генерирую красивые, легко произносимые @username для Telegram "
        "и сразу проверяю их доступность на t.me и fragment.com.\n\n"
        "Выбери стиль генерации, чтобы начать:",
        reply_markup=style_selection_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Команды</b>\n"
        "/start — приветствие и выбор стиля\n"
        "/generate [стиль] [длина] [количество] — генерация username, например: "
        "<code>/generate mythic 9-12 10</code> (диапазон) или "
        "<code>/generate mythic 5 20</code> (ровно 5 символов, 20 штук)\n"
        "/check @username — проверить конкретный username\n"
        "/favorites — сохранённые username (добавить: <code>/favorites add username</code>, "
        "удалить: <code>/favorites remove username</code>)\n"
        "/history — история генераций\n"
        "/help — это сообщение\n\n"
        f"Доступные стили: {', '.join(STYLE_LABELS.values())}\n"
        f"Длина username: от {MIN_LENGTH} до {MAX_LENGTH} символов (например {MIN_LENGTH}-8 или 9-12)",
        parse_mode="HTML",
    )


_LENGTH_SPEC_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


@router.message(Command("generate"))
async def cmd_generate(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    style = args[0].lower() if args else None
    count = 5
    min_length, max_length = MIN_LENGTH, MAX_LENGTH

    rest = args[1:]
    # A length spec is only recognized when a count follows it too, so that the old
    # two-arg form "/generate style count" keeps meaning length=default, count=N.
    if len(rest) >= 2:
        length_match = _LENGTH_SPEC_RE.match(rest[0])
        if length_match:
            lo = int(length_match.group(1))
            hi = int(length_match.group(2)) if length_match.group(2) else lo
            min_length, max_length = lo, hi
            rest = rest[1:]

    if rest and rest[0].isdigit():
        count = int(rest[0])

    if style not in VALID_STYLES:
        await message.answer(
            "Выбери стиль генерации:",
            reply_markup=style_selection_keyboard(),
        )
        return

    if not 1 <= count <= 20:
        await message.answer("Количество должно быть от 1 до 20.")
        return

    if not MIN_LENGTH <= min_length <= max_length <= MAX_LENGTH:
        await message.answer(f"Длина должна быть в диапазоне {MIN_LENGTH}-{MAX_LENGTH}, например 9-12.")
        return

    await _run_generation(message, message.from_user.id, style, min_length, max_length, count)


async def _run_generation(
    message: Message, user_id: int, style: str, min_length: int, max_length: int, count: int
) -> None:
    progress = await message.answer(
        f"🔄 Ищу {count} свободных username ({min_length}-{max_length} симв.) в стиле "
        f"{STYLE_LABELS[style]}... Короткие имена почти все заняты, это может занять время."
    )
    try:
        results = await _generate_and_check(style, count, min_length, max_length, progress)
    except Exception:
        logger.exception(
            "Generation failed for style=%s length=%s-%s count=%s", style, min_length, max_length, count
        )
        await progress.edit_text("⚠️ Не удалось выполнить проверку. Попробуй ещё раз чуть позже.")
        return

    await progress.delete()

    if len(results) < count:
        note = (
            "😔 Не нашлось ни одного свободного username с такими параметрами."
            if not results
            else f"⚠️ Нашёл только {len(results)} свободных из {count} запрошенных."
        )
        await message.answer(
            f"{note} Перебрал все варианты, которые может выдать этот стиль для длины "
            f"{min_length}-{max_length} — они закончились. Попробуй другую длину или стиль."
        )
        if not results:
            return

    await _send_results(message, user_id, style, min_length, max_length, results)


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery) -> None:
    style = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        f"Стиль: {STYLE_LABELS[style]}\nВыбери длину username:",
        reply_markup=length_selection_keyboard(style),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("length:"))
async def on_length_selected(callback: CallbackQuery) -> None:
    _, style, min_length_str, max_length_str = callback.data.split(":")
    min_length, max_length = int(min_length_str), int(max_length_str)
    await callback.message.edit_text(
        f"Стиль: {STYLE_LABELS[style]}\nДлина: {min_length}-{max_length}\nСколько username сгенерировать?",
        reply_markup=count_selection_keyboard(style, min_length, max_length),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("count:"))
async def on_count_selected(callback: CallbackQuery) -> None:
    _, style, min_length_str, max_length_str, count_str = callback.data.split(":")
    min_length, max_length, count = int(min_length_str), int(max_length_str), int(count_str)
    await callback.answer("Генерирую...")
    await _run_generation(callback.message, callback.from_user.id, style, min_length, max_length, count)


@router.callback_query(F.data.startswith("export:"))
async def on_export(callback: CallbackQuery) -> None:
    _, fmt, style = callback.data.split(":")
    results = _last_results.get(callback.from_user.id)
    if not results:
        await callback.answer("Нет данных для экспорта, сначала сгенерируй username.", show_alert=True)
        return

    if fmt == "csv":
        file_data = export_to_csv(results)
        filename = "usernames.csv"
    else:
        file_data = export_to_json(results)
        filename = "usernames.json"

    await callback.message.answer_document(BufferedInputFile(file_data.read(), filename=filename))
    await callback.answer()


@router.message(Command("check"))
async def cmd_check(message: Message, command: CommandObject) -> None:
    raw = (command.args or "").strip().lstrip("@")
    if not raw:
        await message.answer("Использование: /check @username")
        return

    if not is_valid_telegram_username(raw):
        await message.answer("Некорректный username. Разрешены буквы, цифры и _, длина 5-32 символа.")
        return

    progress = await message.answer(f"🔄 Проверяю @{raw}...")
    results = await checker.check_many([raw])
    result = results[0]

    await db.add_history(message.from_user.id, raw, "manual", overall_status(result).value)
    await progress.edit_text(format_result_line(1, result), parse_mode="HTML")


@router.message(Command("favorites"))
async def cmd_favorites(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()

    if len(args) >= 2 and args[0].lower() in ("add", "remove"):
        action, raw = args[0].lower(), args[1].lstrip("@")
        if not is_valid_telegram_username(raw):
            await message.answer("Некорректный username.")
            return
        if action == "add":
            added = await db.add_favorite(message.from_user.id, raw)
            await message.answer(f"⭐ @{raw} добавлен в избранное." if added else f"@{raw} уже в избранном.")
        else:
            await db.remove_favorite(message.from_user.id, raw)
            await message.answer(f"🗑 @{raw} удалён из избранного.")
        return

    favorites = await db.get_favorites(message.from_user.id)
    if not favorites:
        await message.answer(
            "У тебя пока нет избранных username. Сгенерируй что-нибудь через /generate, "
            "а затем добавь в избранное: <code>/favorites add username</code>",
            parse_mode="HTML",
        )
        return

    lines = [f"{i}. @{f['username']}" for i, f in enumerate(favorites, start=1)]
    await message.answer(
        "⭐ <b>Избранное</b>\n\n" + "\n".join(lines) + "\n\nУдалить: <code>/favorites remove username</code>",
        parse_mode="HTML",
    )


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    history = await db.get_history(message.from_user.id, limit=20)
    if not history:
        await message.answer("История пуста. Начни с /generate!")
        return

    lines = [f"{i}. @{h['username']} — {h['style']} — {h['status']}" for i, h in enumerate(history, start=1)]
    await message.answer("🕘 <b>История генераций</b>\n\n" + "\n".join(lines), parse_mode="HTML")


async def main() -> None:
    validate_config()
    os.makedirs(os.path.dirname(config.log_file) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(config.log_file, encoding="utf-8"), logging.StreamHandler()],
    )

    await db.init()

    session = AiohttpSession(proxy=config.bot_api_proxy) if config.bot_api_proxy else None
    bot = Bot(token=config.bot_token, session=session)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
