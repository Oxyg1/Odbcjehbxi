"""Тесты бота: чистые функции и весь диалог через настоящий aiogram-диспетчер (без сети и без Telegram)."""
import asyncio
import time
import unittest
from datetime import datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import ton_bot as tb

OWNER, STRANGER = 111, 222
WALLET_HASH = bytes(range(32))
MY = tb.ParsedAddress(0, WALLET_HASH, True, False)
DEST = tb.ParsedAddress(0, bytes([7] * 32), False, False)  # UQ-адрес получателя
DEST_UQ, DEST_EQ = DEST.friendly(False), DEST.friendly(True)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.n = 0

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            self.n += 1
            return Message(message_id=self.n, date=datetime.now(), chat=Chat(id=OWNER, type="private"), text=method.text)
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass

    def texts(self):
        return [c.text for c in self.calls if isinstance(c, SendMessage)]


class FakeService:
    def __init__(self, balance=5 * tb.NANO, active=True):
        self.balance, self.active, self.sent = balance, active, []

    def address_forms(self):
        return MY.friendly(True), MY.friendly(False)

    async def info(self):
        return {"balance": self.balance, "active": self.active}

    async def usd_price(self):
        return 3.0

    async def history(self, limit=8):
        return [{"now": 1790000000, "fee": 5000, "items": [("in", tb.NANO, DEST_UQ, False), ("out", 2 * tb.NANO, DEST_UQ, False)]}]

    async def send(self, dest, amount, comment, bounce):
        self.sent.append((dest.raw(), amount, comment, bounce))
        return "ab" * 32


def make_cfg(max_send=None, network="mainnet"):
    return tb.Config("1:x", OWNER, bytes(32), "v5", "x", network, None, max_send)


class Harness:
    def __init__(self, svc=None, cfg=None):
        self.session = FakeSession()
        self.bot = Bot("1:" + "A" * 30, session=self.session)
        self.svc = svc or FakeService()
        self.cfg = cfg or make_cfg()
        self.dp = tb.build_dispatcher(self.cfg, self.svc)
        self.uid = 0

    def _msg(self, text, user):
        self.uid += 1
        return Message(message_id=self.uid, date=datetime.now(), chat=Chat(id=user, type="private"),
                       from_user=User(id=user, is_bot=False, first_name="x"), text=text)

    async def say(self, text, user=OWNER):
        self.uid += 1
        await self.dp.feed_update(self.bot, Update(update_id=self.uid, message=self._msg(text, user)))

    async def press(self, data, user=OWNER):
        self.uid += 1
        cb = CallbackQuery(id=str(self.uid), from_user=User(id=user, is_bot=False, first_name="x"),
                           chat_instance="c", data=data, message=self._msg("btn", user))
        await self.dp.feed_update(self.bot, Update(update_id=self.uid, callback_query=cb))

    def last_nonce(self):
        for c in reversed(self.session.calls):
            if isinstance(c, SendMessage) and c.reply_markup:
                for row in c.reply_markup.inline_keyboard:
                    for b in row:
                        if b.callback_data and b.callback_data.startswith("ok:"):
                            return b.callback_data
        return None

    async def full_flow(self, addr=DEST_UQ, amount="1.5", comment="-"):
        await self.say("/send")
        await self.say(addr)
        await self.say(amount)
        await self.say(comment)


def run(coro):
    return asyncio.run(coro)


class PureTests(unittest.TestCase):
    def test_amount(self):
        self.assertEqual(tb.parse_amount("1.5"), 1_500_000_000)
        self.assertEqual(tb.parse_amount("0,25"), 250_000_000)
        self.assertEqual(tb.parse_amount("0.000000001"), 1)
        for bad in ["0", "-1", "abc", "1.0000000001", "nan", "inf", "", "1e30"]:
            with self.assertRaises(ValueError, msg=bad):
                tb.parse_amount(bad)

    def test_fmt(self):
        self.assertEqual(tb.fmt_ton(1_500_000_000), "1.5")
        self.assertEqual(tb.fmt_ton(1), "0.000000001")
        self.assertEqual(tb.fmt_ton(3 * tb.NANO), "3")
        self.assertEqual(tb.fmt_ton(0), "0")

    def test_address_roundtrip_and_errors(self):
        # известные реальные адреса (из tonsdk/tonutils)
        a = tb.parse_address("UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8My")
        self.assertEqual(a.bounceable, False)
        self.assertEqual(a.hash.hex(), "7c380f242a59749f692f522934c3dd60ff1def38555349861702bb1ca9258623")
        self.assertEqual(a.friendly(False), "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8My")
        self.assertEqual(tb.parse_address(a.friendly(True)).hash, a.hash)
        self.assertEqual(tb.parse_address(a.raw()).hash, a.hash)
        for bad in ["", "UQB8OA8k", "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8Mz",  # опечатка -> CRC
                    "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8M!"]:
            with self.assertRaises(ValueError, msg=bad):
                tb.parse_address(bad)
        t = a.friendly(False, testnet=True)
        self.assertTrue(tb.parse_address(t).testnet)

    def test_config(self):
        import os
        keep = dict(os.environ)
        try:
            for k in ("BOT_TOKEN", "OWNER_ID", "WALLET_SEED", "WALLET_VERSION", "WALLET_ADDRESS", "NETWORK", "MAX_SEND_TON"):
                os.environ.pop(k, None)
            with self.assertRaises(tb.ConfigError):
                tb.Config.from_env()
            os.environ.update(BOT_TOKEN="123456:" + "A" * 30, OWNER_ID="5", WALLET_SEED="ab" * 32, WALLET_ADDRESS="x")
            c = tb.Config.from_env()
            self.assertEqual((c.owner_id, c.version, c.network, c.max_send), (5, "v5", "mainnet", None))
            os.environ["MAX_SEND_TON"] = "2.5"
            self.assertEqual(tb.Config.from_env().max_send, 2_500_000_000)
            os.environ["WALLET_SEED"] = "zz"
            with self.assertRaises(tb.ConfigError):
                tb.Config.from_env()
        finally:
            os.environ.clear(); os.environ.update(keep)


class FlowTests(unittest.TestCase):
    def test_stranger_is_ignored_completely(self):
        async def go():
            h = Harness()
            for t in ["/start", "/send", "/balance", "hello"]:
                await h.say(t, user=STRANGER)
            await h.press("m:send", user=STRANGER)
            await h.press("ok:deadbeef", user=STRANGER)
            self.assertEqual(h.session.calls, [])
            self.assertEqual(h.svc.sent, [])
        run(go())

    def test_menu_screens(self):
        async def go():
            h = Harness()
            await h.say("/start"); await h.say("/balance"); await h.say("/deposit"); await h.say("/history")
            await h.press("m:balance")
            t = "\n".join(h.session.texts())
            self.assertIn("5 TON", t); self.assertIn("$15.00", t)
            self.assertIn(MY.friendly(True), t)          # адрес показан
            self.assertIn("🕘", t); self.assertIn("+1 TON", t); self.assertIn("−2 TON", t)
        run(go())

    def test_deposit_shows_UQ_when_not_active(self):
        async def go():
            h = Harness(FakeService(active=False))
            await h.say("/deposit")
            t = h.session.texts()[-1]
            self.assertLess(t.index(MY.friendly(False)), t.index(MY.friendly(True)))  # UQ идёт первым
            self.assertIn("первый", t)
        run(go())

    def test_send_happy_path_and_double_confirm(self):
        async def go():
            h = Harness()
            await h.full_flow(comment="memo 42")
            confirm = h.session.texts()[-1]
            self.assertIn("1.5 TON", confirm); self.assertIn("memo 42", confirm); self.assertIn(DEST_UQ, confirm)
            self.assertEqual(h.svc.sent, [])              # до подтверждения ничего не ушло
            nonce = h.last_nonce()
            await h.press(nonce)
            await h.press(nonce)                          # двойное нажатие
            self.assertEqual(h.svc.sent, [(DEST.raw(), 1_500_000_000, "memo 42", False)])
            self.assertIn("Отправлено", h.session.texts()[-1])
        run(go())

    def test_stale_or_foreign_nonce_rejected(self):
        async def go():
            h = Harness()
            await h.full_flow()
            await h.press("ok:00000000")
            self.assertEqual(h.svc.sent, [])
            await h.press(h.last_nonce())                 # настоящий nonce всё ещё работает
            self.assertEqual(len(h.svc.sent), 1)
        run(go())

    def test_confirmation_expires(self):
        async def go():
            h = Harness()
            await h.full_flow()
            nonce = h.last_nonce()
            key = next(iter(h.dp.storage.storage))
            h.dp.storage.storage[key].data["ts"] = time.time() - tb.CONFIRM_TTL - 5
            await h.press(nonce)
            self.assertEqual(h.svc.sent, [])
            self.assertIn("Время вышло", h.session.texts()[-1])
        run(go())

    def test_validation_errors(self):
        async def go():
            h = Harness(cfg=make_cfg(max_send=2 * tb.NANO))
            await h.say("/send")
            await h.say("UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8Mz")       # опечатка
            self.assertIn("контрольная сумма", h.session.texts()[-1])
            await h.say(DEST.friendly(False, testnet=True))                        # тестовая сеть
            self.assertIn("другой сети", h.session.texts()[-1])
            await h.say(DEST_UQ)
            await h.say("abc"); self.assertIn("не число", h.session.texts()[-1])
            await h.say("3");   self.assertIn("лимита", h.session.texts()[-1])    # MAX_SEND_TON
            await h.say("2")                                                       # 2 + 0.02 <= 5 - ok
            self.assertIn("Комментарий", h.session.texts()[-1])
            self.assertEqual(h.svc.sent, [])
        run(go())

    def test_insufficient_funds_counts_fee_reserve(self):
        async def go():
            h = Harness(FakeService(balance=1 * tb.NANO))
            await h.say("/send"); await h.say(DEST_UQ)
            await h.say("1")                                                       # ровно весь баланс - без запаса на комиссию
            self.assertIn("Недостаточно", h.session.texts()[-1])
            await h.say("0.97")
            self.assertIn("Комментарий", h.session.texts()[-1])
        run(go())

    def test_cancel(self):
        async def go():
            h = Harness()
            await h.say("/send"); await h.say(DEST_UQ); await h.say("1")
            await h.say("/cancel")
            await h.say("-")                                                       # после отмены текст не продолжает перевод
            self.assertEqual(h.svc.sent, [])
            await h.full_flow()
            await h.press("cancel")
            await h.press(h.last_nonce())
            self.assertEqual(h.svc.sent, [])
        run(go())

    def test_bounceable_destination_warned_and_flag_passed(self):
        async def go():
            h = Harness()
            await h.full_flow(addr=DEST_EQ)
            self.assertIn("bounceable", h.session.texts()[-1])
            await h.press(h.last_nonce())
            self.assertEqual(h.svc.sent[0][3], True)
        run(go())

    def test_send_failure_reported(self):
        async def go():
            svc = FakeService()
            async def boom(*a, **k): raise RuntimeError("network down")
            svc.send = boom
            h = Harness(svc)
            await h.full_flow()
            await h.press(h.last_nonce())
            self.assertIn("Не удалось отправить", h.session.texts()[-1])
            self.assertIn("network down", h.session.texts()[-1])
        run(go())


if __name__ == "__main__":
    unittest.main(verbosity=2)
