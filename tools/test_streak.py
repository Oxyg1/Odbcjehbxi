"""
Серия ежедневного бонуса: московские сутки (а не UTC с границей в 03:00)
и дни простоя бота, которые серию не сжигают.

Запуск из корня репозитория:
    python3 tools/test_streak.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, types, tempfile, logging, json, time as _time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="streak_test_"), "test.db")
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


class FakeBot:
    username = "frogbot"
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return types.SimpleNamespace(message_id=1)
        return _noop


def msk(day, h, m=0):
    """День 0 — сегодня по Москве, час и минута по Москве."""
    d = datetime.now(B.ST_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return (d + timedelta(days=day, hours=h, minutes=m)).timestamp()


async def claim_at(uid, ts):
    real = B.time.time
    B.time.time = lambda: ts
    try:
        if hasattr(B._user_cache, "clear"):
            B._user_cache.clear()
        f = await B.db_get(uid)
        user = types.SimpleNamespace(id=uid, first_name="Т", is_premium=False)
        ctx = types.SimpleNamespace(bot=FakeBot(), user_data={}, bot_data={})
        okc, _ = await B.daily_claim(user, f, ctx)
        if hasattr(B._user_cache, "clear"):
            B._user_cache.clear()
        return okc, (await B.db_get(uid))["streak"]
    finally:
        B.time.time = real


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    user = types.SimpleNamespace(id=1, first_name="Т", username="", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    B._streak_excused.clear()

    print("1. Московские сутки: ночной бонус не рвёт серию")
    ok(await claim_at(1, msk(-3, 1)) == (True, 1), "первый бонус в 01:00")
    # По старым UTC-суткам 01:00 МСК — ещё «позавчера», и тут серия слетала
    ok(await claim_at(1, msk(-2, 14)) == (True, 2), "на следующий день в 14:00 — серия 2")
    ok((await claim_at(1, msk(-2, 23, 30)))[0] is False, "в тот же день второй раз нельзя")
    ok(await claim_at(1, msk(-1, 0, 20)) == (True, 3), "00:20 — уже новые сутки, серия 3")
    ok((await claim_at(1, msk(-1, 2, 30)))[0] is False, "02:30 того же дня — уже забрал (раньше было можно)")
    ok(await claim_at(1, msk(1, 12)) == (True, 1), "пропустил день — серия заново")

    print("2. Дни простоя бота")
    ok(B.streak_outage_days(msk(0, 10), msk(0, 10, 10)) == [], "10 минут — не простой для серии")
    days = B.streak_outage_days(msk(0, 22), msk(2, 1))
    ok(days == [B.st_day(msk(0, 12)), B.st_day(msk(1, 12)), B.st_day(msk(2, 12))],
       f"22:00 → через сутки 01:00: три дня задеты ({days})")
    ok(B.streak_outage_days(msk(0, 23, 45), msk(1, 0, 40)) == [B.st_day(msk(1, 12))],
       "на вчера пришлось 15 мин — не считаем, на сегодня 40 — считаем")
    ok(not B.streak_continues(msk(0, 12), msk(2, 12)), "без простоя пропуск рвёт серию")
    B._streak_excused.add(B.st_day(msk(1, 12)))
    ok(B.streak_continues(msk(0, 12), msk(2, 12)), "пропущенный день — день простоя: серия жива")
    ok(not B.streak_continues(msk(0, 12), msk(3, 12)), "а лишний пропуск кроме него — нет")
    B._streak_excused.clear()

    print("3. Простой при старте записывается и переживает перезапуск")
    now = _time.time()
    await B.db_setting(B.HEARTBEAT_KEY, str(now - 26 * 3600))
    await B.compensate_downtime()
    yday = B.st_day(now - 86400)
    ok(yday in B._streak_excused and B.st_day(now) in B._streak_excused,
       f"вчера и сегодня в списке ({sorted(B._streak_excused)})")
    B._streak_excused.clear()
    await B.streak_outage_load()
    ok(yday in B._streak_excused, "после перезапуска список читается из базы")
    saved = json.loads(await B.db_setting(B.STREAK_OUTAGE_KEY))
    ok(saved == sorted(saved), "хранится списком дат")
    # Серия после простоя
    B._streak_excused.clear()
    B._streak_excused.add(B.st_day(msk(-1, 12)))
    await B.new_frog(types.SimpleNamespace(id=2, first_name="Т", username="", last_name="",
                                           language_code="ru", is_bot=False))
    await claim_at(2, msk(-3, 18))
    ok(await claim_at(2, msk(-2, 18)) == (True, 2), "серия 2")
    ok(await claim_at(2, msk(0, 9)) == (True, 3), "вчера бот лежал — сегодня серия продолжается")
    B._streak_excused.clear()

    print("4. Отображение и сброс кулдаунов")
    f = {"streak": 9, "last_daily": _time.time() - 3 * 86400}
    ok(B.streak_now(f) == 0, "сгоревшую серию не показываем")
    f["last_daily"] = B.daily_day_start() - 60
    ok(B.streak_now(f) == 9, "вчерашняя — живая")
    ok(B.streak_continues(B.daily_day_start() - 60), "сброс кулдауна админом: «вчера» — серия цела")
    can, nxt, _ = B._remind_bonus(f, _time.time())
    ok(can and nxt == 10, "напоминание считает серию так же")

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
