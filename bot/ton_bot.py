"""Telegram-бот для управления вашим TON-кошельком (v5R1 / v4R2): баланс, пополнение, отправка, история.

Запуск:  python ton_bot.py          (настройки читаются из .env рядом с файлом)
Проверка настроек без запуска бота:  python ton_bot.py --check
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import html
import logging
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

NANO = 10**9
FEE_RESERVE = 20_000_000          # 0.02 TON запас на комиссию при отправке
CONFIRM_TTL = 120                 # секунд на подтверждение перевода
MAX_COMMENT = 120

log = logging.getLogger("ton_bot")


# ---------------------------------------------------------------- настройки

def load_env(path: Path) -> None:
    """Минимальный разбор .env (KEY=VALUE); переменные окружения имеют приоритет."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


class ConfigError(Exception):
    pass


@dataclass
class Config:
    bot_token: str
    owner_id: int
    seed: bytes
    version: str                    # "v5" | "v4"
    expected_address: str
    network: str                    # "mainnet" | "testnet"
    api_key: Optional[str]
    max_send: Optional[int]         # в нанотонах

    @classmethod
    def from_env(cls, need_bot: bool = True) -> "Config":
        env = os.environ.get
        token = (env("BOT_TOKEN") or "").strip()
        if need_bot and not re.fullmatch(r"\d+:[\w-]{20,}", token):
            raise ConfigError("BOT_TOKEN не задан или выглядит неверно (получите токен у @BotFather)")
        owner = (env("OWNER_ID") or "").strip()
        if need_bot and not owner.isdigit():
            raise ConfigError("OWNER_ID должен быть числом - ваш Telegram ID (узнать у @userinfobot)")
        seed_hex = (env("WALLET_SEED") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", seed_hex):
            raise ConfigError("WALLET_SEED должен быть 64 hex-символа (строка 'private seed' из found.txt)")
        version = (env("WALLET_VERSION") or "v5").strip().lower()
        if version not in ("v4", "v5"):
            raise ConfigError("WALLET_VERSION: v5 или v4")
        addr = (env("WALLET_ADDRESS") or "").strip()
        if not addr:
            raise ConfigError("WALLET_ADDRESS не задан (нужен для проверки, что seed даёт ваш адрес)")
        network = (env("NETWORK") or "mainnet").strip().lower()
        if network not in ("mainnet", "testnet"):
            raise ConfigError("NETWORK: mainnet или testnet")
        max_send = None
        if (env("MAX_SEND_TON") or "").strip():
            try:
                max_send = parse_amount(env("MAX_SEND_TON"))
            except ValueError as e:
                raise ConfigError(f"MAX_SEND_TON: {e}")
        return cls(token, int(owner or 0), bytes.fromhex(seed_hex), version, addr, network,
                   (env("TONCENTER_API_KEY") or "").strip() or None, max_send)


# ---------------------------------------------------------------- чистые функции

def parse_amount(text: str) -> int:
    """'1.5' / '1,5' -> нанотоны. ValueError с понятным текстом при ошибке."""
    t = text.strip().replace(",", ".").replace(" ", "")
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise ValueError("не число. Пример: 1.5")
    if not d.is_finite() or d <= 0:
        raise ValueError("сумма должна быть больше нуля")
    if d.as_tuple().exponent < -9:
        raise ValueError("не более 9 знаков после запятой")
    if d > 1_000_000_000:
        raise ValueError("слишком большая сумма")
    return int(d * NANO)


def fmt_ton(nano: int) -> str:
    sign = "-" if nano < 0 else ""
    nano = abs(nano)
    s = f"{nano // NANO}.{nano % NANO:09d}".rstrip("0").rstrip(".")
    return sign + s


def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass
class ParsedAddress:
    workchain: int
    hash: bytes
    bounceable: Optional[bool]      # None для raw-формата
    testnet: bool

    def friendly(self, bounceable: bool, testnet: Optional[bool] = None) -> str:
        flag = 0x11 if bounceable else 0x51
        if self.testnet if testnet is None else testnet:
            flag |= 0x80
        body = bytes([flag, self.workchain & 0xFF]) + self.hash
        raw = body + crc16(body).to_bytes(2, "big")
        return base64.urlsafe_b64encode(raw).decode()

    def raw(self) -> str:
        return f"{self.workchain}:{self.hash.hex()}"


def parse_address(text: str) -> ParsedAddress:
    """Разбор адреса TON (EQ../UQ.. или raw 0:hex) с проверкой CRC. ValueError с понятным текстом."""
    t = text.strip()
    if re.fullmatch(r"-?\d+:[0-9a-fA-F]{64}", t):
        wc, h = t.split(":")
        return ParsedAddress(int(wc), bytes.fromhex(h), None, False)
    if len(t) != 48:
        raise ValueError("адрес должен состоять из 48 символов (EQ... или UQ...)")
    try:
        raw = base64.urlsafe_b64decode(t.replace("+", "-").replace("/", "_"))
    except (binascii.Error, ValueError):
        raise ValueError("в адресе есть недопустимые символы")
    if len(raw) != 36:
        raise ValueError("неверная длина адреса")
    if crc16(raw[:34]) != int.from_bytes(raw[34:], "big"):
        raise ValueError("контрольная сумма не сходится - в адресе опечатка")
    flag = raw[0]
    testnet = bool(flag & 0x80)
    tag = flag & 0x7F
    if tag not in (0x11, 0x51):
        raise ValueError("неизвестный тип адреса")
    wc = raw[1] - 256 if raw[1] > 127 else raw[1]
    return ParsedAddress(wc, raw[2:34], tag == 0x11, testnet)


def short(addr: str) -> str:
    return f"{addr[:5]}…{addr[-5:]}" if len(addr) > 12 else addr


# ---------------------------------------------------------------- работа с кошельком

class WalletService:
    """Тонкая обёртка над tonutils: всё, что бот делает с блокчейном, проходит здесь."""

    def __init__(self, client: Any, cfg: Config):
        from ton_core import PrivateKey
        from tonutils.contracts import WalletV4R2, WalletV5R1

        cls = WalletV5R1 if cfg.version == "v5" else WalletV4R2
        self.client = client
        self.cfg = cfg
        self.wallet = cls.from_private_key(client, PrivateKey(cfg.seed))
        self.testnet = cfg.network == "testnet"
        raw = self.wallet.address.to_str(is_user_friendly=False)
        self.addr = parse_address(raw)
        self._price: tuple[float, Optional[float]] = (0.0, None)

    # адреса
    def address_forms(self) -> tuple[str, str]:
        return (self.addr.friendly(True, self.testnet), self.addr.friendly(False, self.testnet))

    def check_expected(self) -> None:
        exp = parse_address(self.cfg.expected_address)
        if exp.hash != self.addr.hash or exp.workchain != self.addr.workchain:
            eq, uq = self.address_forms()
            raise ConfigError(
                "WALLET_SEED даёт ДРУГОЙ адрес, чем WALLET_ADDRESS.\n"
                f"  из seed ({self.cfg.version}): {eq}\n  в WALLET_ADDRESS:   {self.cfg.expected_address}\n"
                "Проверьте seed и WALLET_VERSION (v5/v4). Бот не запущен, чтобы не работать с чужим кошельком.")

    # чтение
    async def info(self) -> dict:
        await self.wallet.refresh()
        return {"balance": int(self.wallet.balance), "active": bool(self.wallet.is_active)}

    async def usd_price(self) -> Optional[float]:
        if time.time() - self._price[0] < 120:
            return self._price[1]
        price = None
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get("https://tonapi.io/v2/rates", params={"tokens": "ton", "currencies": "usd"}) as r:
                    price = float((await r.json())["rates"]["TON"]["prices"]["USD"])
        except Exception:  # курс - необязательная мелочь
            price = self._price[1]
        self._price = (time.time(), price)
        return price

    async def history(self, limit: int = 8) -> list[dict]:
        out = []
        for tx in await self.wallet.get_transactions(limit=limit):
            items = []
            im = tx.in_msg
            info = getattr(im, "info", None)
            if info is not None and getattr(info, "src", None) is not None and hasattr(info, "value_coins"):
                v = int(info.value_coins)
                if v > 0:
                    items.append(("in", v, str(info.src.to_str(is_bounceable=False)), bool(getattr(info, "bounced", False))))
            for m in tx.out_msgs:
                oi = getattr(m, "info", None)
                if oi is not None and getattr(oi, "dest", None) is not None and hasattr(oi, "value_coins"):
                    items.append(("out", int(oi.value_coins), str(oi.dest.to_str(is_bounceable=False)), False))
            out.append({"now": int(tx.now), "fee": int(getattr(tx.total_fees, "grams", 0) or 0), "items": items})
        return out

    # отправка
    async def send(self, dest: ParsedAddress, amount: int, comment: Optional[str], bounce: Optional[bool]) -> str:
        from ton_core import Address
        destination = Address((dest.workchain, dest.hash))
        ext = await self.wallet.transfer(destination=destination, amount=amount, body=comment or None, bounce=bounce)
        return ext.normalized_hash.hex() if isinstance(ext.normalized_hash, (bytes, bytearray)) else str(ext.normalized_hash)


# ---------------------------------------------------------------- бот

def build_dispatcher(cfg: Config, svc: Any):
    from aiogram import BaseMiddleware, Dispatcher, F, Router
    from aiogram.filters import Command
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

    class SendFlow(StatesGroup):
        address = State()
        amount = State()
        comment = State()
        confirm = State()

    class OwnerOnly(BaseMiddleware):
        """Все, кроме владельца, молча игнорируются - бот для посторонних не существует."""

        async def __call__(self, handler: Callable, event: Any, data: dict) -> Any:
            user = getattr(event, "from_user", None)
            if user is None or user.id != cfg.owner_id:
                log.warning("чужой пользователь %s проигнорирован", getattr(user, "id", None))
                return None
            return await handler(event, data)

    router = Router()
    router.message.outer_middleware(OwnerOnly())
    router.callback_query.outer_middleware(OwnerOnly())

    def menu() -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(inline_keyboard=[
            [b(text="💰 Баланс", callback_data="m:balance"), b(text="📥 Пополнить", callback_data="m:deposit")],
            [b(text="📤 Отправить", callback_data="m:send"), b(text="🕘 История", callback_data="m:history")],
        ])

    def cancel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])

    explorer = "https://tonviewer.com/" if cfg.network == "mainnet" else "https://testnet.tonviewer.com/"

    async def do_balance(msg: Message) -> None:
        try:
            info = await svc.info()
        except Exception as e:
            log.exception("balance")
            return await msg.answer(f"Не удалось получить баланс: {html.escape(str(e))[:200]}", reply_markup=menu())
        text = f"💰 <b>{fmt_ton(info['balance'])} TON</b>"
        price = await svc.usd_price()
        if price:
            text += f"  ≈ ${info['balance'] / NANO * price:,.2f}"
        if not info["active"]:
            text += ("\n\nКошелёк ещё не активирован: он активируется первой исходящей транзакцией "
                     "(бот сделает это сам при первой отправке).")
        eq, _ = svc.address_forms()
        await msg.answer(text + f"\n\n<a href=\"{explorer}{eq}\">Открыть в обозревателе</a>", reply_markup=menu(),
                         disable_web_page_preview=True)

    async def do_deposit(msg: Message) -> None:
        eq, uq = svc.address_forms()
        try:
            active = (await svc.info())["active"]
        except Exception:
            active = False
        if active:
            text = (f"📥 <b>Адрес для пополнения</b> (нажмите, чтобы скопировать):\n\n<code>{eq}</code>\n\n"
                    f"Та же запись в виде UQ (non-bounceable):\n<code>{uq}</code>")
        else:
            text = (f"📥 <b>Адрес для пополнения</b> (нажмите, чтобы скопировать):\n\n<code>{uq}</code>\n\n"
                    "⚠️ Кошелёк ещё не активирован, поэтому <b>первый</b> перевод шлите именно на эту форму (UQ…): "
                    "перевод на форму EQ… к неактивированному кошельку может вернуться отправителю.\n\n"
                    f"После активации основным станет красивый адрес:\n<code>{eq}</code>")
        await msg.answer(text, reply_markup=menu())

    async def do_history(msg: Message) -> None:
        try:
            txs = await svc.history(8)
        except Exception as e:
            log.exception("history")
            return await msg.answer(f"Не удалось получить историю: {html.escape(str(e))[:200]}", reply_markup=menu())
        if not txs:
            return await msg.answer("Транзакций пока нет.", reply_markup=menu())
        lines = ["🕘 <b>Последние операции</b> (UTC)\n"]
        for t in txs:
            when = datetime.fromtimestamp(t["now"], timezone.utc).strftime("%d.%m %H:%M")
            if not t["items"]:
                lines.append(f"{when}  ⚙️ служебная операция (комиссия {fmt_ton(t['fee'])})")
            for kind, val, addr, bounced in t["items"]:
                arrow = "⬇️ +" if kind == "in" else "⬆️ −"
                who = "от" if kind == "in" else "→"
                extra = " (возврат)" if bounced else ""
                lines.append(f"{when}  {arrow}{fmt_ton(val)} TON {who} <code>{short(addr)}</code>{extra}")
        await msg.answer("\n".join(lines), reply_markup=menu())

    async def start_send(msg: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(SendFlow.address)
        await msg.answer("📤 Введите адрес получателя (EQ… или UQ…):", reply_markup=cancel_kb())

    @router.message(Command("start", "menu"))
    async def cmd_start(msg: Message, state: FSMContext) -> None:
        await state.clear()
        eq, _ = svc.address_forms()
        await msg.answer(f"Кошелёк TON ({cfg.version.upper()}, {cfg.network})\n<code>{eq}</code>", reply_markup=menu())

    @router.message(Command("balance"))
    async def cmd_balance(msg: Message) -> None:
        await do_balance(msg)

    @router.message(Command("deposit"))
    async def cmd_deposit(msg: Message) -> None:
        await do_deposit(msg)

    @router.message(Command("history"))
    async def cmd_history(msg: Message) -> None:
        await do_history(msg)

    @router.message(Command("send"))
    async def cmd_send(msg: Message, state: FSMContext) -> None:
        await start_send(msg, state)

    @router.message(Command("cancel"))
    async def cmd_cancel(msg: Message, state: FSMContext) -> None:
        await state.clear()
        await msg.answer("Отменено.", reply_markup=menu())

    @router.callback_query(F.data == "cancel")
    async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer("Отменено")
        if cb.message:
            await cb.message.answer("Отменено.", reply_markup=menu())

    @router.callback_query(F.data.startswith("m:"))
    async def cb_menu(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        if cb.message is None:
            return
        action = (cb.data or "")[2:]
        if action == "balance":
            await do_balance(cb.message)
        elif action == "deposit":
            await do_deposit(cb.message)
        elif action == "history":
            await do_history(cb.message)
        elif action == "send":
            await start_send(cb.message, state)

    @router.message(SendFlow.address, F.text)
    async def got_address(msg: Message, state: FSMContext) -> None:
        try:
            p = parse_address(msg.text or "")
        except ValueError as e:
            return await msg.answer(f"❌ {e}. Введите адрес ещё раз или /cancel", reply_markup=cancel_kb())
        if p.workchain != 0:
            return await msg.answer("❌ Поддерживается только основной воркчейн (адреса, начинающиеся с EQ/UQ).")
        if p.testnet != (cfg.network == "testnet"):
            return await msg.answer("❌ Это адрес другой сети (тестовой/основной).", reply_markup=cancel_kb())
        await state.update_data(dest=p.raw(), bounce=p.bounceable, dest_text=p.friendly(bool(p.bounceable) if p.bounceable is not None else False, p.testnet))
        await state.set_state(SendFlow.amount)
        try:
            bal = (await svc.info())["balance"]
            avail = f"\nДоступно: {fmt_ton(max(bal - FEE_RESERVE, 0))} TON (с запасом на комиссию)"
        except Exception:
            avail = ""
        await msg.answer(f"Сколько TON отправить?{avail}", reply_markup=cancel_kb())

    @router.message(SendFlow.amount, F.text)
    async def got_amount(msg: Message, state: FSMContext) -> None:
        try:
            amount = parse_amount(msg.text or "")
        except ValueError as e:
            return await msg.answer(f"❌ {e}. Введите сумму ещё раз или /cancel", reply_markup=cancel_kb())
        if cfg.max_send is not None and amount > cfg.max_send:
            return await msg.answer(f"❌ Больше лимита MAX_SEND_TON ({fmt_ton(cfg.max_send)} TON).", reply_markup=cancel_kb())
        try:
            bal = (await svc.info())["balance"]
        except Exception as e:
            return await msg.answer(f"Не удалось проверить баланс: {html.escape(str(e))[:200]}")
        if amount + FEE_RESERVE > bal:
            return await msg.answer(
                f"❌ Недостаточно средств: баланс {fmt_ton(bal)} TON, нужно сумма + ≈0.02 TON на комиссию.",
                reply_markup=cancel_kb())
        await state.update_data(amount=amount)
        await state.set_state(SendFlow.comment)
        await msg.answer("Комментарий к переводу? Отправьте текст или «-», чтобы пропустить.\n"
                         "(Биржам обычно нужен комментарий/MEMO - не забудьте его.)", reply_markup=cancel_kb())

    @router.message(SendFlow.comment, F.text)
    async def got_comment(msg: Message, state: FSMContext) -> None:
        text = (msg.text or "").strip()
        comment = None if text in ("-", "—", "") else text
        if comment and len(comment) > MAX_COMMENT:
            return await msg.answer(f"❌ Комментарий длиннее {MAX_COMMENT} символов.", reply_markup=cancel_kb())
        data = await state.get_data()
        nonce = secrets.token_hex(4)
        await state.update_data(comment=comment, nonce=nonce, ts=time.time())
        await state.set_state(SendFlow.confirm)
        try:
            active = (await svc.info())["active"]
        except Exception:
            active = True
        lines = [
            "<b>Проверьте перевод</b>",
            f"Кому: <code>{data['dest_text']}</code>",
            f"Сумма: <b>{fmt_ton(data['amount'])} TON</b> (+ комиссия ≈0.01 TON)",
            f"Комментарий: {html.escape(comment) if comment else '—'}",
        ]
        if data.get("bounce"):
            lines.append("ℹ️ Адрес получателя в форме EQ (bounceable): если его кошелёк не активирован, деньги вернутся.")
        if not active:
            lines.append("ℹ️ Эта транзакция заодно активирует ваш кошелёк.")
        lines.append(f"\nПодтверждение действует {CONFIRM_TTL // 60} мин.")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Отправить", callback_data=f"ok:{nonce}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]])
        await msg.answer("\n".join(lines), reply_markup=kb)

    @router.callback_query(F.data.startswith("ok:"))
    async def confirm_send(cb: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        nonce = (cb.data or "")[3:]
        # подтверждение работает один раз: состояние сбрасывается ДО отправки (защита от двойного нажатия)
        if await state.get_state() != SendFlow.confirm.state or data.get("nonce") != nonce:
            return await cb.answer("Это подтверждение уже недействительно", show_alert=True)
        await state.clear()
        if time.time() - float(data.get("ts", 0)) > CONFIRM_TTL:
            await cb.answer("Время подтверждения вышло", show_alert=True)
            if cb.message:
                await cb.message.answer("⌛ Время вышло, перевод не отправлен. Начните заново: /send", reply_markup=menu())
            return
        await cb.answer("Отправляю…")
        dest = parse_address(data["dest"])
        try:
            h = await svc.send(dest, int(data["amount"]), data.get("comment"), data.get("bounce"))
        except Exception as e:
            log.exception("send failed")
            if cb.message:
                await cb.message.answer(f"❌ Не удалось отправить: {html.escape(str(e))[:300]}\n"
                    "Перед повторной попыткой загляните в «🕘 История»: при сбое связи перевод мог всё же уйти.",
                                        reply_markup=menu())
            return
        if cb.message:
            await cb.message.answer(
                f"✅ Отправлено в сеть: {fmt_ton(int(data['amount']))} TON\n"
                "Обычно перевод проходит за 5–30 секунд - проверьте в «🕘 История».\n"
                f"<code>{html.escape(h)}</code>", reply_markup=menu())

    @router.message(F.text)
    async def fallback(msg: Message) -> None:
        await msg.answer("Выберите действие:", reply_markup=menu())

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp["svc"] = svc
    return dp


# ---------------------------------------------------------------- запуск

async def run(check_only: bool) -> None:
    from ton_core import NetworkGlobalID
    from tonutils.clients import ToncenterClient

    load_env(Path(__file__).with_name(".env"))
    try:
        cfg = Config.from_env(need_bot=not check_only)
    except ConfigError as e:
        sys.exit(f"Ошибка настройки: {e}")
    net = NetworkGlobalID.MAINNET if cfg.network == "mainnet" else NetworkGlobalID.TESTNET
    async with ToncenterClient(net, api_key=cfg.api_key) as client:
        svc = WalletService(client, cfg)
        try:
            svc.check_expected()
        except ConfigError as e:
            sys.exit(f"Ошибка настройки: {e}")
        eq, uq = svc.address_forms()
        info = await svc.info()
        print(f"Кошелёк {cfg.version.upper()} ({cfg.network}): адрес совпал с WALLET_ADDRESS.")
        print(f"  EQ: {eq}\n  UQ: {uq}")
        print(f"  баланс: {fmt_ton(info['balance'])} TON, активирован: {'да' if info['active'] else 'нет'}")
        if check_only:
            return

        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.types import BotCommand

        bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = build_dispatcher(cfg, svc)
        await bot.set_my_commands([
            BotCommand(command="menu", description="Меню"),
            BotCommand(command="balance", description="Баланс"),
            BotCommand(command="deposit", description="Адрес для пополнения"),
            BotCommand(command="send", description="Отправить TON"),
            BotCommand(command="history", description="История"),
            BotCommand(command="cancel", description="Отмена"),
        ])
        me = await bot.get_me()
        print(f"Бот @{me.username} запущен. Доступ только у пользователя {cfg.owner_id}. Остановка: Ctrl+C")
        try:
            await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
        finally:
            await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    try:
        asyncio.run(run(check_only="--check" in sys.argv))
    except KeyboardInterrupt:
        pass
