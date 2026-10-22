"""
Звук уведомлений: что звенит, что приходит тихо, сколько раз в сутки.
Плюс урезанная рассылка: Трудяга одним сообщением, без «заскучала»,
столовая без отчётов, комар только недавним игрокам.

Запуск из корня репозитория:
    python3 tools/test_push.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, types, tempfile, logging, sqlite3, time as _time, json
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="push_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)


class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.sent, self.deleted, self.mid = [], [], 100
    async def send_message(self, chat_id, text, **kw):
        self.mid += 1
        self.sent.append((chat_id, text))
        return Sent(self.mid)
    async def delete_message(self, chat_id, mid, **kw):
        self.deleted.append((chat_id, mid))
        return True
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return Sent(1)
        return _noop


def x_db(sql, *a):
    con = sqlite3.connect(DB, timeout=30)
    con.execute(sql, a)
    con.commit()
    con.close()


async def make_frog(uid, **fields):
    user = types.SimpleNamespace(id=uid, first_name=f"Игрок{uid}", username="", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    sets = {"onboard_step": 0, "frog_name": f"Ква{uid}", "last_decay": _time.time(), **fields}
    x_db(f"UPDATE frogs SET {','.join(k + '=?' for k in sets)} WHERE user_id=?", *sets.values(), uid)
    if hasattr(B._user_cache, "clear"):
        B._user_cache.clear()
    return await B.db_get(uid)


def at_msk(h):
    """Отметка времени: сегодня, h часов по Москве."""
    d = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.timestamp() + (h - 3) * 3600


async def govern(chat, actor=0, src="фон", kind=""):
    """Прогнать одну отправку через фильтр в заданном контексте."""
    async def run():
        B._PUSH_ACTOR.set(actor)
        B._ST_SRC.set(src)
        if kind:
            B._PUSH_KIND.set(kind)
        data = {"chat_id": chat, "text": "x"}
        await B.push_govern("sendMessage", data)
        return not data.get("disable_notification")
    return await asyncio.create_task(run())


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    day = at_msk(14)
    real_time = B.time.time

    print("1. Кто это: ответ, уведомление, группа")
    async def cls(chat, actor=0, src="фон", kind=""):
        async def run():
            B._PUSH_ACTOR.set(actor); B._ST_SRC.set(src)
            if kind:
                B._PUSH_KIND.set(kind)
            return B.push_classify(chat)
        return await asyncio.create_task(run())
    ok(await cls(5, actor=5) == "", "ответ самому игроку — не уведомление")
    ok(await cls(-100123, actor=0) == "", "группа — не трогаем")
    ok(await cls("@chan") == "", "канал по имени — не трогаем")
    ok(await cls(5, actor=7) == "personal", "другой игрок что-то сделал — личное")
    ok(await cls(5, src="job:reminders") == "alert", "напоминание о лягушке — тревога")
    ok(await cls(5, src="job:mosquito") == "quiet", "комар — тихо")
    ok(await cls(5, src="job:auto_farm") == "quiet", "Трудяга — тихо")
    ok(await cls(5, src="job:background_decay", kind="alert") == "alert", "push_as перекрывает")
    with B.push_as("alert"):
        pass
    ok(B._PUSH_KIND.get() == "", "push_as возвращает как было")

    print("2. Сколько звенит за сутки")
    B._push_loud.clear()
    ok([B._push_loud_ok(1, "alert", day) for _ in range(5)] == [True] * B.PUSH_LOUD_ALERT + [False] * (5 - B.PUSH_LOUD_ALERT),
       "тревога — не больше PUSH_LOUD_ALERT в сутки")
    ok(B._push_loud_ok(1, "personal", day), "у личного свой счёт")
    ok(B._push_loud_ok(1, "alert", day + 86400), "на следующий день счёт заново")
    ok(not B._push_loud_ok(2, "quiet", day), "«тихое» не звенит никогда")
    ok(not B._push_loud_ok(3, "alert", at_msk(2)), "ночью тихо")
    ok(not B._push_loud_ok(3, "alert", at_msk(23) + 60), "23:01 — уже ночь")
    ok(B._push_loud_ok(3, "alert", at_msk(9) + 60), "9:01 — уже можно")

    print("3. Фильтр на настоящей отправке и режимы игрока")
    await make_frog(11)
    await make_frog(12, push_mode=1)
    await make_frog(13, push_mode=2)
    B._push_loud.clear()
    B._push_mode_cache.clear()
    B.time.time = lambda: day
    try:
        ok(await govern(11, src="job:reminders"), "важные: тревога звенит")
        ok(not await govern(11, src="job:mosquito"), "важные: комар тихо")
        ok(not await govern(11, src="job:events"), "важные: событие тихо")
        ok(await govern(11, actor=99), "важные: подарок от игрока звенит")
        ok(await govern(12, src="job:mosquito"), "режим «все»: звенит всё")
        ok(not await govern(13, src="job:reminders"), "режим «без звука»: даже тревога тихо")
        d = {"chat_id": 11, "text": "x"}
        async def as_actor():
            B._PUSH_ACTOR.set(11)
            await B.push_govern("sendMessage", d)
        await asyncio.create_task(as_actor())
        ok("disable_notification" not in d, "ответ на нажатие не трогаем")
        d = {"chat_id": 11, "message_id": 1, "text": "x"}
        await B.push_govern("editMessageText", d)
        ok("disable_notification" not in d, "правка сообщения не трогаем")
    finally:
        B.time.time = real_time

    print("4. Переключатель в настройках")
    f = await B.db_get(11)
    text, kb = B.settings_screen(f)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    ok(any("Звук" in l and "важные" in l for l in labels), "в настройках «Звук · важные»")
    B.push_mode_set(11, 2)
    ok(await B._push_mode(11) == 2, "смена режима сразу видна фильтру")

    print("5. Трудяга: один отчёт вечером вместо трёх")
    bot = FakeBot()
    await make_frog(21, subscription_type=2, subscription_until=_time.time() + 86400 * 5,
                    worker_phase=0, last_worker_report=0)
    real_elig = B._worker_get_eligible
    async def elig(now):
        return [21]
    B._worker_get_eligible = elig
    try:
        now = _time.time()
        await B._work_phase_morning(now, bot)
        await B._work_phase_midday(now, bot)
        ok(bot.sent == [], f"утром и в обед молчит ({len(bot.sent)})")
        if hasattr(B._user_cache, "clear"):
            B._user_cache.clear()
        f = await B.db_get(21)
        scene = json.loads(f.get("worker_scene_json") or "{}")
        ok(f.get("worker_phase") == 2 and scene, "день всё равно идёт по фазам")
        await B._work_phase_evening(now, bot)
        ok(len(bot.sent) == 1, f"вечером одно сообщение ({len(bot.sent)})")
        if bot.sent and scene:
            t = bot.sent[0][1]
            name = B.fname(f)
            ok(scene["story"].format(name=name) in t and scene["event"].format(name=name) in t,
               "в вечернем отчёте вся история дня")
    finally:
        B._worker_get_eligible = real_elig

    print("6. Напоминания: только когда лягушке плохо")
    bot = FakeBot()
    now = _time.time()
    await make_frog(31, hunger=35, happiness=20, health=90, last_remind=0, last_seen=now)
    await make_frog(32, hunger=0, health=50, last_remind=0, last_seen=now)
    real_all = B.db_all_alive
    async def only_mine():
        return [await B.db_get(31), await B.db_get(32)]
    B.db_all_alive = only_mine
    try:
        await B.job_reminders(types.SimpleNamespace(bot=bot))
    finally:
        B.db_all_alive = real_all
    to = [c for c, _ in bot.sent]
    ok(31 not in to, "«заскучала» больше не шлётся")
    ok(32 in to, "голодает — напоминание пришло")

    print("7. Комар: окно рассылки и уборка")
    ok(B.MOSQUITO_ACTIVE_HOURS == 48, "в личку — только заходившим за двое суток")
    ok(B.INTERACTIVE_EVENT_COOLDOWN >= 20 * 3600, "случайные события — раз в сутки")
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    ok("подкормила твою лягушку" not in src, "столовая не отчитывается о каждой кормёжке")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


try:
    asyncio.get_event_loop().run_until_complete(main())
except BaseException:
    import traceback
    traceback.print_exc()
    os._exit(2)
