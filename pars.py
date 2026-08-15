"""
Kissed Frog NFT Scanner
=======================
Два режима работы:
  1) FAST  — GetResaleStarGiftsRequest: только NFT на продаже (быстро)
  2) FULL  — GetUniqueStarGiftRequest:  перебор всех 15 000 slug'ов (~2.5 ч)

По умолчанию — FAST.  Для полного перебора:  python kissed_frog_scanner.py --full

Требования:
    pip install telethon python-dotenv

.env файл:
    API_ID=12345678
    API_HASH=abcdef1234567890abcdef1234567890
    PHONE_NUMBER=+79001234567
"""

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from telethon import TelegramClient, functions, types

# ── Настройки ────────────────────────────────────────────────────────────────

# find_dotenv ищет .env от каталога самого скрипта вверх по дереву, а не от
# текущего каталога. То есть настройки берутся из файла рядом с pars.py —
# на сервере это /opt/frogbot/.env. Путь запоминаем, чтобы при незаполненных
# ключах показать в ошибке именно его, а не гадать.
ENV_PATH = find_dotenv(usecwd=False)
load_dotenv(ENV_PATH or None)

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")
SESSION_NAME = "kissed_frog_session"

COLLECTION_PREFIX = "KissedFrog"
MAX_NUM = 15_000          # Полный тираж
DELAY_SECONDS = 0.6       # Пауза между запросами
OUTPUT_FILE = "kissed_frog_on_sale.json"

# Для тестирования FULL-режима — раскомментируйте:
# MAX_NUM = 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Утилиты ──────────────────────────────────────────────────────────────────


def parse_price(resell_amount_list) -> tuple[int, float]:
    """
    Извлекает цену из resell_amount (Vector<StarsAmount>).

    Возвращает (звёзды, тоны). Ноль означает «в этой валюте лот не выставлен» —
    цена бывает в одной валюте, в другой или сразу в обеих.

    По TL-схеме в векторе лежат два разных типа:
        starsAmount#bbb6b4a3    amount:long nanos:int  — цена в звёздах
        starsTonAmount#74aee3e0 amount:long            — цена в нанотонах

    Прежняя версия делила на 1e9 обе: у starsAmount есть поле nanos, и проверка
    `hasattr(item, "nanos")` уводила звёзды в ветку тонов. Хуже того, при цене
    сразу в двух валютах звёзды шли в векторе вторыми и затирали уже посчитанный
    TON — 12.5 TON + 5000 звёзд давали 0.0. Каталог заполнялся нулями.
    """
    stars = 0
    ton = 0.0

    for item in resell_amount_list or []:
        class_name = type(item).__name__
        amount = getattr(item, "amount", 0) or 0

        if "Ton" in class_name:
            ton = amount / 1_000_000_000
        else:
            # nanos — дробная часть звезды (1e-9), на целую цену почти не влияет,
            # но учитываем, чтобы 0.5 звезды не превращались в ноль.
            nanos = getattr(item, "nanos", 0) or 0
            stars = int(amount) + int(nanos) // 1_000_000_000

    return stars, round(ton, 4)


def serialize_resell_amount(resell_amount_list) -> list:
    """Сериализует resell_amount в JSON."""
    if not resell_amount_list:
        return []
    result = []
    for item in resell_amount_list:
        entry = {"_": type(item).__name__}
        for attr in ("amount", "nanos", "crypto_currency", "currency"):
            val = getattr(item, attr, None)
            if val is not None:
                entry[attr] = val
        result.append(entry)
    return result


def extract_attributes(gift_obj) -> dict:
    """
    Извлекает модель (model), фон (backdrop) и паттерн (pattern)
    из gift.attributes (Vector<StarGiftAttribute>).

    TL-схема атрибутов:
      starGiftAttributeModel    — name, document, rarity_permille
      starGiftAttributeBackdrop — name, backdrop_id, center_color, edge_color,
                                  pattern_color, text_color, rarity_permille
      starGiftAttributePattern  — name, document, rarity_permille
    """
    attrs = getattr(gift_obj, "attributes", None) or []

    model = None
    backdrop = None
    pattern = None

    for attr in attrs:
        cls_name = type(attr).__name__

        if "Model" in cls_name:
            model = {
                "name": getattr(attr, "name", ""),
                "rarity_permille": getattr(attr, "rarity_permille", 0),
            }
            # document_id стикера модели (если нужен)
            doc = getattr(attr, "document", None)
            if doc:
                model["document_id"] = getattr(doc, "id", None)

        elif "Backdrop" in cls_name:
            backdrop = {
                "name": getattr(attr, "name", ""),
                "backdrop_id": getattr(attr, "backdrop_id", None),
                "center_color": _color_hex(getattr(attr, "center_color", 0)),
                "edge_color": _color_hex(getattr(attr, "edge_color", 0)),
                "pattern_color": _color_hex(getattr(attr, "pattern_color", 0)),
                "text_color": _color_hex(getattr(attr, "text_color", 0)),
                "rarity_permille": getattr(attr, "rarity_permille", 0),
            }

        elif "Pattern" in cls_name:
            pattern = {
                "name": getattr(attr, "name", ""),
                "rarity_permille": getattr(attr, "rarity_permille", 0),
            }
            doc = getattr(attr, "document", None)
            if doc:
                pattern["document_id"] = getattr(doc, "id", None)

    return {
        "model": model,
        "backdrop": backdrop,
        "pattern": pattern,
    }


def _color_hex(color_int) -> str:
    """Конвертирует целочисленный цвет в hex-строку (#RRGGBB)."""
    if not color_int:
        return "#000000"
    return f"#{color_int & 0xFFFFFF:06X}"


def gift_to_dict(gift_obj) -> dict | None:
    """
    Преобразует StarGiftUnique в dict для JSON.
    Возвращает None если подарок не на продаже.
    """
    resell = getattr(gift_obj, "resell_amount", None)

    # Фильтр: только если resell_amount непустой
    if not resell:
        return None

    slug = getattr(gift_obj, "slug", "")
    num = getattr(gift_obj, "num", 0)
    stars, ton = parse_price(resell)
    attributes = extract_attributes(gift_obj)

    return {
        "num": num,
        "slug": slug,
        "marketplace_url": f"https://t.me/nft/{slug}",
        # Обе валюты по отдельности — бот показывает ту, в которой лот выставлен
        "price_stars": stars,
        "price_ton": ton,
        # Старые поля оставлены: их читают прежние версии загрузчика
        "price": stars or ton,
        "currency": "Stars" if stars else ("TON" if ton else "unknown"),
        "model": attributes["model"],
        "backdrop": attributes["backdrop"],
        "pattern": attributes["pattern"],
        "resell_amount_raw": serialize_resell_amount(resell),
    }


# ── Режим FAST: GetResaleStarGiftsRequest ────────────────────────────────────


async def get_gift_id(client: TelegramClient) -> int | None:
    """
    Получаем gift_id коллекции Kissed Frog.
    Запрашиваем любой известный slug и берём gift_id из ответа.
    """
    test_slugs = ["KissedFrog-1", "KissedFrog-100", "KissedFrog-1000"]

    for slug in test_slugs:
        try:
            result = await client(
                functions.payments.GetUniqueStarGiftRequest(slug=slug)
            )
            gift = result.gift
            gift_id = getattr(gift, "gift_id", None) or getattr(gift, "id", None)

            log.info("Объект: %s", type(gift).__name__)
            log.info("  slug=%s, num=%s, gift_id=%s",
                     getattr(gift, "slug", "?"),
                     getattr(gift, "num", "?"),
                     gift_id)

            # Для отладки — выведем все атрибуты первого подарка
            attrs = getattr(gift, "attributes", [])
            for a in attrs:
                log.info("  attr: %s → name=%s, rarity=%s‰",
                         type(a).__name__,
                         getattr(a, "name", "?"),
                         getattr(a, "rarity_permille", "?"))

            if gift_id:
                log.info("gift_id коллекции %s: %d", COLLECTION_PREFIX, gift_id)
                return gift_id
        except Exception as e:
            log.warning("Не удалось получить %s: %s", slug, e)
            await asyncio.sleep(1)

    return None


async def scan_fast(client: TelegramClient) -> list[dict]:
    """
    FAST: GetResaleStarGiftsRequest — только NFT на продаже, с пагинацией.
    """
    log.info("=== FAST режим: GetResaleStarGiftsRequest ===")

    gift_id = await get_gift_id(client)
    if not gift_id:
        log.error("Не удалось определить gift_id! Попробуйте --full режим.")
        return []

    on_sale = []
    offset = ""
    page = 0
    LIMIT = 100

    while True:
        page += 1
        log.info("Страница %d (offset='%s')...", page, offset[:30] if offset else "начало")

        try:
            result = await client(
                functions.payments.GetResaleStarGiftsRequest(
                    gift_id=gift_id,
                    offset=offset,
                    limit=LIMIT,
                    sort_by_price=True,
                )
            )
        except Exception as e:
            log.error("Ошибка GetResaleStarGifts: %s", e)
            break

        total_count = getattr(result, "count", 0)
        gifts = getattr(result, "gifts", [])
        next_offset = getattr(result, "next_offset", None)

        if page == 1:
            log.info("Всего на продаже в коллекции: %d", total_count)

        for gift in gifts:
            entry = gift_to_dict(gift)
            if entry:
                on_sale.append(entry)
                model_name = entry["model"]["name"] if entry["model"] else "?"
                backdrop_name = entry["backdrop"]["name"] if entry["backdrop"] else "?"
                if len(on_sale) <= 5 or len(on_sale) % 100 == 0:
                    log.info(
                        "  #%d %s — %s %s | модель: %s | фон: %s",
                        entry["num"], entry["slug"],
                        entry["price"], entry["currency"],
                        model_name, backdrop_name,
                    )

        log.info("  Получено %d, всего: %d / %d", len(gifts), len(on_sale), total_count)

        if not next_offset or not gifts:
            break

        offset = next_offset
        await asyncio.sleep(DELAY_SECONDS)

    return on_sale


# ── Режим FULL: перебор по slug ──────────────────────────────────────────────


async def fetch_gift_by_slug(client: TelegramClient, slug: str):
    """Запрашивает один NFT по slug. Возвращает StarGiftUnique или None."""
    try:
        result = await client(
            functions.payments.GetUniqueStarGiftRequest(slug=slug)
        )
        return result.gift
    except Exception as e:
        err_msg = str(e)
        if "NOT_FOUND" in err_msg.upper() or "INVALID" in err_msg.upper():
            return None
        if "flood" in err_msg.lower():
            wait = 30
            try:
                from telethon.errors import FloodWaitError
                if isinstance(e, FloodWaitError):
                    wait = e.seconds + 2
            except ImportError:
                pass
            log.warning("FloodWait — ждём %d сек...", wait)
            await asyncio.sleep(wait)
            return await fetch_gift_by_slug(client, slug)
        log.error("Ошибка для %s: %s", slug, err_msg)
        return None


async def scan_full(client: TelegramClient) -> list[dict]:
    """FULL: перебирает все slug от 1 до MAX_NUM."""
    log.info("=== FULL режим: перебор slug 1..%d ===", MAX_NUM)

    on_sale = []
    total_found = 0

    for num in range(1, MAX_NUM + 1):
        slug = f"{COLLECTION_PREFIX}-{num}"
        gift = await fetch_gift_by_slug(client, slug)

        if gift is None:
            if num % 500 == 0 or num <= 5:
                log.info("[%5d/%d] %s — не найден", num, MAX_NUM, slug)
            await asyncio.sleep(DELAY_SECONDS)
            continue

        total_found += 1
        entry = gift_to_dict(gift)

        if entry:
            on_sale.append(entry)
            model_name = entry["model"]["name"] if entry["model"] else "?"
            backdrop_name = entry["backdrop"]["name"] if entry["backdrop"] else "?"
            log.info(
                "[%5d/%d] ✅ %s — %s %s | модель: %s | фон: %s",
                num, MAX_NUM, slug,
                entry["price"], entry["currency"],
                model_name, backdrop_name,
            )
        else:
            if num % 1000 == 0:
                log.info(
                    "[%5d/%d] %s — не продаётся (на продаже: %d)",
                    num, MAX_NUM, slug, len(on_sale),
                )

        await asyncio.sleep(DELAY_SECONDS)

    log.info("Найдено существующих: %d", total_found)
    return on_sale


# ── main ─────────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Kissed Frog NFT Scanner")
    parser.add_argument(
        "--full", action="store_true",
        help="Полный перебор всех 15000 slug. По умолчанию — быстрый режим.",
    )
    parser.add_argument(
        "--output", "-o", default=OUTPUT_FILE,
        help=f"Файл для результатов (по умолчанию: {OUTPUT_FILE})",
    )
    args = parser.parse_args()

    # Проверяем настройки до Telethon: без этого он падает невнятным
    # «API ID or Hash cannot be empty», и непонятно, какой именно .env пуст.
    # Промах здесь типовой: .env исключён из деплоя и живёт только рядом с
    # ботом, а правят его в каталоге с исходниками.
    missing = [n for n, v in (("API_ID", API_ID), ("API_HASH", API_HASH),
                              ("PHONE_NUMBER", PHONE_NUMBER)) if not v]
    if missing:
        log.error("Не заданы: %s", ", ".join(missing))
        if ENV_PATH:
            log.error("Прочитан файл: %s", ENV_PATH)
            log.error("Допишите в него недостающие строки.")
        else:
            log.error(".env не найден рядом с %s", Path(__file__).resolve().parent)
            log.error("Настройки берутся из файла рядом с pars.py, то есть из "
                      "каталога бота. Копия .env в исходниках на сервер не "
                      "попадает — она в исключениях деплоя.")
        raise SystemExit(2)

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE_NUMBER)
    log.info("Авторизация успешна.")

    start_time = time.monotonic()

    if args.full:
        on_sale = await scan_full(client)
    else:
        on_sale = await scan_fast(client)

    elapsed = time.monotonic() - start_time

    # ── Сохранение ────────────────────────────────────────────────────────
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(on_sale, f, ensure_ascii=False, indent=2)

    # ── Итоги ─────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("ГОТОВО!")
    log.info("Выставлено на продажу: %d", len(on_sale))
    log.info("Результат сохранён в: %s", output_path.resolve())
    log.info("Время работы: %.1f сек (%.1f мин)", elapsed, elapsed / 60)
    log.info("=" * 60)

    if on_sale:
        print(f"\n{'#':>6}  {'Slug':<22}  {'Цена':>10}  {'Вал.':<5}  "
              f"{'Модель':<20}  {'Фон':<18}  {'Паттерн':<15}")
        print("-" * 110)
        for item in sorted(on_sale, key=lambda x: (x["price_stars"] or 0, x["price_ton"] or 0)):
            m = item["model"]["name"] if item["model"] else "—"
            b = item["backdrop"]["name"] if item["backdrop"] else "—"
            p = item["pattern"]["name"] if item["pattern"] else "—"
            print(
                f"{item['num']:>6}  {item['slug']:<22}  "
                f"{item['price']:>10}  {item['currency']:<5}  "
                f"{m:<20}  {b:<18}  {p:<15}"
            )
        print(f"\nИтого на продаже: {len(on_sale)}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
