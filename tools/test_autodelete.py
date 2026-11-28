"""
Автоудаление в группах: считается от последнего нажатия кнопки, слушает
настройку чата «автоудаление», «ваниль» удаляет всегда, итог можно оставить.

Запуск из корня репозитория:
    python3 tools/test_autodelete.py
"""
import os, sys, asyncio, types, tempfile, logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="autodel_test_"), "test.db")
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

CHAT, OFF = -1001, -1002


class FakeBot:
    def __init__(self):
        self.deleted = []
    async def delete_message(self, chat_id, message_id, **kw):
        self.deleted.append((chat_id, message_id))


def press(chat, mid):
    q = types.SimpleNamespace(message=types.SimpleNamespace(chat=types.SimpleNamespace(id=chat), message_id=mid))
    return B.msg_touch_on_update(types.SimpleNamespace(callback_query=q), None)


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    await B.save_chat_settings(OFF, auto_delete_enabled=0)
    bot = FakeBot()

    print("1. Без нажатий — через delay")
    t = asyncio.create_task(B.schedule_delete(bot, CHAT, 1, 1))
    await asyncio.sleep(1.4)
    ok((CHAT, 1) in bot.deleted, "удалено вовремя")

    print("2. Нажимали кнопку — ждём delay от последнего нажатия")
    t = asyncio.create_task(B.schedule_delete(bot, CHAT, 2, 1))
    await asyncio.sleep(0.7); await press(CHAT, 2)
    await asyncio.sleep(0.7)
    ok((CHAT, 2) not in bot.deleted, "через 1,4 с от отправки ещё висит — нажимали в 0,7")
    await asyncio.sleep(0.4); await press(CHAT, 2)
    await asyncio.sleep(0.8)
    ok((CHAT, 2) not in bot.deleted, "снова нажали — снова ждём")
    await asyncio.sleep(0.6)
    ok((CHAT, 2) in bot.deleted, "перестали нажимать — удалено")

    print("3. Настройка чата «автоудаление выкл»")
    await asyncio.gather(B.schedule_delete(bot, OFF, 3, 0), B.schedule_delete(bot, OFF, 4, 0, force=True))
    ok((OFF, 3) not in bot.deleted, "выключено — не удаляем")
    ok((OFF, 4) in bot.deleted, "но «ваниль» (force) удаляет")
    await B._auto_delete(bot, OFF, 5, B.MSG_LOW)
    ok((OFF, 5) not in bot.deleted, "send_group_msg тоже слушается")

    print("4. keep_message — итог остаётся")
    t = asyncio.create_task(B.schedule_delete(bot, CHAT, 6, 1))
    B.keep_message(CHAT, 6)
    await t
    ok((CHAT, 6) not in bot.deleted, "оставлено")

    print("5. Личка — настройки чата не нужны")
    await B.schedule_delete(bot, 42, 7, 0)
    ok((42, 7) in bot.deleted, "в личке удаляется как раньше")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


asyncio.run(main())
