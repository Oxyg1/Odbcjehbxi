"""
/nft проверяет владельца по подаркам в профиле Telegram (getUserGifts),
без See.tg и без ручной модерации.

Запуск из корня репозитория:
    python3 tools/test_nft_profile.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, types, tempfile, logging, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="nft_test_"), "test.db")
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["SEETG_TGAUTH"] = ""
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B
from telegram.error import NetworkError

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

MODEL = next(iter(B.SKINS))
OTHER = "Модель, которой нет в боте"


def ugift(num, model, slug="KissedFrog"):
    part = lambda n, r: types.SimpleNamespace(name=n, rarity_per_mille=r)
    return types.SimpleNamespace(gift=types.SimpleNamespace(
        name=f"{slug}-{num}", number=num, is_burned=False,
        model=part(model, 15), symbol=part("Узор", 4), backdrop=part("Фон", 20)))


class FakeBot:
    def __init__(self):
        self.profiles, self.sent, self.fail = {}, [], False
    async def get_user_gifts(self, user_id, offset=None, limit=None, **kw):
        if self.fail:
            raise NetworkError("нет связи")
        gifts = self.profiles.get(user_id, [])
        start = int(offset or 0)
        page = gifts[start:start + 2]                    # мелкие страницы — проверить листание
        nxt = str(start + 2) if start + 2 < len(gifts) else None
        return types.SimpleNamespace(gifts=page, next_offset=nxt, total_count=len(gifts))
    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return types.SimpleNamespace(message_id=1, chat=types.SimpleNamespace(id=chat_id))
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return types.SimpleNamespace(message_id=1)
        return _noop


class Reply:
    def __init__(self, log, text):
        self.log, self.text = log, text
        log.append(text)
    async def edit_text(self, text, **kw):
        self.log.append(text)


def update_for(uid):
    log = []
    user = types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}",
                                 last_name="", language_code="ru", is_bot=False, is_premium=False)
    async def reply_text(text, **kw):
        return Reply(log, text)
    msg = types.SimpleNamespace(reply_text=reply_text, chat=types.SimpleNamespace(id=uid, type="private"),
                                from_user=user, message_id=1)
    upd = types.SimpleNamespace(effective_user=user, message=msg, effective_message=msg,
                                effective_chat=msg.chat)
    return upd, log


async def make_frog(uid):
    user = types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    await asyncio.sleep(0.1)


async def rows(num):
    import aiosqlite
    async with aiosqlite.connect(B.DB_PATH) as db:
        async with db.execute("SELECT user_id, verified FROM nft_frogs WHERE nft_number=? ORDER BY id",
                              (str(num),)) as c:
            return await c.fetchall()


async def run(bot, uid, *args):
    upd, log = update_for(uid)
    ctx = types.SimpleNamespace(bot=bot, args=list(args))
    await B.cmd_nft(upd, ctx)
    return log[-1] if log else ""


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    bot = FakeBot()
    for uid in (1, 2, 3, 4):
        await make_frog(uid)
    B.announce = lambda *a, **k: asyncio.sleep(0)       # заявки админу не нужны

    print("1. /nft без аргументов — всё из профиля, с листанием")
    bot.profiles[1] = [ugift(101, MODEL), ugift(5, MODEL, slug="PlushPepe"), ugift(102, MODEL),
                       ugift(103, MODEL)]
    out = await run(bot, 1)
    ok("Добавлено 3" in out, f"три жабы из профиля добавлены: {out!r}")
    ok(await rows(101) == [(1, 1)] and await rows(103) == [(1, 1)], "записаны подтверждёнными")
    ok(await rows(5) == [], "чужие коллекции не трогаем")
    ok(B.nft_attrs(101).get("model") == MODEL and B.nft_attrs(101).get("model_r") == 15,
       "редкость сохранена без See.tg")
    out = await run(bot, 1)
    ok("Уже зарегистрировано ранее: 3" in out, f"повтор — без дублей: {out!r}")
    ok(len(await rows(101)) == 1, "строка одна")

    print("2. /nft <ссылка> — подтверждение по профилю")
    bot.profiles[2] = [ugift(201, MODEL)]
    out = await run(bot, 2, "https://t.me/nft/KissedFrog-201")
    ok("Нашёл в твоём профиле" in out, f"подтверждено сразу: {out!r}")
    ok(await rows(201) == [(2, 1)], "без заявки админу")

    print("3. Висящая заявка закрывается сама")
    import aiosqlite
    async with aiosqlite.connect(B.DB_PATH) as db:
        await db.execute("INSERT INTO nft_frogs(user_id,nft_url,nft_number,model_name,verified,added_at)"
                         " VALUES(3,'',  '301', '', 0, ?)", (_time.time(),))
        await db.commit()
    bot.profiles[3] = [ugift(301, MODEL)]
    await run(bot, 3)
    ok(await rows(301) == [(3, 1)], f"заявка заменена подтверждением: {await rows(301)}")

    print("4. Гифт продали — переходит к тому, у кого он в профиле")
    bot.profiles[1] = [g for g in bot.profiles[1] if g.gift.number != 101]
    bot.profiles[4] = [ugift(101, MODEL)]
    out = await run(bot, 4, "https://t.me/nft/KissedFrog-101")
    ok(await rows(101) == [(4, 1)], f"прежний владелец снят, новый записан: {await rows(101)}")
    ok("Нашёл в твоём профиле" in out, "новому — сразу облик")

    print("5. Не в профиле — как раньше, с подсказкой")
    out = await run(bot, 2, "https://t.me/nft/KissedFrog-777")
    ok("покажи подарок в профиле" in out.lower(), f"подсказка про профиль: {out!r}")
    out = await run(bot, 2, "https://t.me/nft/KissedFrog-103")
    ok("другим игроком" in out and "профиле" in out, f"занята другим — подсказка: {out!r}")
    bot.profiles[2] = []
    out = await run(bot, 2)
    ok("Показать в профиле" in out, f"пустой профиль — как показать: {out!r}")

    print("6. Модели нет в боте — к админу, Telegram не ответил — не падаем")
    bot.profiles[2] = [ugift(401, OTHER)]
    out = await run(bot, 2)
    ok(await rows(401) == [(2, 0)], "неизвестная модель — заявка")
    bot.fail = True
    out = await run(bot, 2, "https://t.me/nft/KissedFrog-402")
    ok("проверку" in out or "профиле" in out, f"без связи — обычный путь: {out!r}")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


try:
    asyncio.run(main())
except BaseException:
    import traceback
    traceback.print_exc()
    os._exit(2)
