"""
Ежедневное напоминание (по образцу Duolingo): время игрока, один раз в день,
серия, «спаси серию» вечером, реже при молчании и прощание, учёт возвратов
по текстам.

Запуск из корня репозитория:
    python3 tools/test_remind.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, types, tempfile, logging, sqlite3, time as _time, re
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="remind_test_"), "test.db")
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

TAG = re.compile(r"<(/?)(b|i|u|s|code|pre|a|blockquote|tg-emoji|span)(?:\s[^>]*)?>")
def check_html(text):
    stack = []
    for close, tag in TAG.findall(text or ""):
        if close:
            assert stack and stack[-1] == tag, f"HTML: </{tag}> без пары:\n{text}"
            stack.pop()
        else:
            stack.append(tag)
    assert not stack, f"HTML: незакрыто {stack}:\n{text}"


class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.sent = []
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.sent.append((chat_id, text, reply_markup))
        return Sent(len(self.sent))
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return Sent(1)
        return _noop


def x_db(sql, *a):
    con = sqlite3.connect(DB, timeout=30)
    con.execute(sql, a)
    con.commit()
    con.close()

def q_db(sql, *a):
    con = sqlite3.connect(DB, timeout=30)
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()


def uncache():
    if hasattr(B._user_cache, "clear"):
        B._user_cache.clear()


async def make_frog(uid, **fields):
    user = types.SimpleNamespace(id=uid, first_name=f"Игрок{uid}", username="", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    sets = {"onboard_step": 0, "frog_name": f"Ква{uid}", "last_decay": _time.time(), **fields}
    x_db(f"UPDATE frogs SET {','.join(k + '=?' for k in sets)} WHERE user_id=?", *sets.values(), uid)
    uncache()
    return await B.db_get(uid)


def msk_ts(day_offset, h, m=0):
    """Отметка времени: день (0 — сегодня по МСК), час и минута по Москве."""
    d = datetime.now(B.ST_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return (d + timedelta(days=day_offset, hours=h, minutes=m)).timestamp()


async def run_at(ts, uids=None):
    """Прогнать job_daily_remind так, будто сейчас ts. Возвращает отправленное."""
    bot = FakeBot()
    real = B.time.time
    B.time.time = lambda: ts
    try:
        await B.job_daily_remind(types.SimpleNamespace(bot=bot))
    finally:
        B.time.time = real
    uncache()
    return [s for s in bot.sent if uids is None or s[0] in uids]


def btns(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row] if kb else []


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    born = msk_ts(-30, 12)

    print("1. Любимый час игрока")
    def mask(*hs):
        return sum(1 << h for h in hs)
    fav = B.remind_hours([(1, mask(20, 21)), (1, mask(20)), (1, mask(13)),
                          (2, mask(2, 3)), (2, mask(1)),
                          (3, mask(7)), (3, mask(6))])
    ok(fav[1] == 20, f"чаще всего в 20 — в 20 ({fav[1]})")
    ok(fav[2] == B.REMIND_WINDOW[0], f"играет ночью — пишем в начале окна, а не ночью ({fav[2]})")
    ok(fav[3] == B.REMIND_WINDOW[0], "ранняя пташка — к началу окна")
    ok(B.remind_hours([]) == {}, "нет данных — пусто (будет час по умолчанию)")

    print("2. Повод написать")
    now = msk_ts(0, 15)
    day0 = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    base = {"health": 90, "hunger": 80, "streak": 0, "last_daily": 0, "last_seen": now - 20 * 3600}
    ok(B.remind_situation({**base, "health": 15}, now, 0) == "danger", "лягушке плохо — первым делом это")
    ok(B.remind_situation({**base, "streak": 8, "last_daily": day0 - 3600}, now, 0) == "streak",
       "живая серия и бонус не забран — про серию")
    ok(B.remind_situation({**base, "streak": 8, "last_daily": day0 - 3 * 86400}, now, 0) == "bonus",
       "серия уже сгорела — про бонус, не про серию")
    ok(B.remind_situation({**base, "last_seen": now - 3 * 86400}, now, 1) == "miss", "давно не был — «ждала»")
    ok(B.remind_situation({**base, "hunger": 30, "last_daily": day0 + 60}, now, 0) == "hungry", "голодна")
    ok(B.remind_situation(base, now, B.REMIND_GIVE_UP) == "last", "долго молчит — прощание")
    _, nxt, coins = B._remind_bonus({"streak": 8, "last_daily": day0 - 3600}, now)
    ok(nxt == 9 and coins == 20 + 45, f"бонус считается как в /daily ({nxt}, {coins})")

    print("3. Тексты: все собираются, кнопка по делу, без повторов подряд")
    f = {**base, "user_id": 1, "frog_name": "Ква", "streak": 8, "last_daily": day0 - 3600}
    for sit, vs in B.REMIND_TEXTS.items():
        for key, *_ in vs:
            text, kb = B.remind_message({**f, "health": 15} if sit == "danger" else f, key, now)
            check_html(text)
            ok("{" not in re.sub(r"<[^>]+>", "", text), f"{key}: все поля подставлены")
            ok(len(btns(kb)) == 1, f"{key}: одна кнопка")
            if sit in ("danger", "hungry"):
                ok(btns(kb) == ["menu_care"], f"{key}: кнопка ухода")
            if sit in ("streak", "saver", "bonus"):
                ok(btns(kb) == ["daily"], f"{key}: кнопка бонуса")
    stats = {"streak_lose": (1000, 500), "streak_count": (1000, 50), "streak_proud": (1000, 60)}
    picks = [B.remind_pick("streak", stats) for _ in range(200)]
    ok(picks.count("streak_lose") > 180, "лучший текст берётся чаще")
    ok(all(B.remind_pick("streak", stats, "streak_lose") != "streak_lose" for _ in range(50)),
       "тот же текст подряд не повторяется")
    fresh = [B.remind_pick("bonus", {}) for _ in range(300)]
    ok(len(set(fresh)) == len(B.REMIND_TEXTS["bonus"]), "без статистики пробуются все тексты")

    print("4. Время и один раз в день")
    await make_frog(101, born_at=born, last_seen=msk_ts(-1, 20), hunger=80, health=90)
    await make_frog(102, born_at=born, last_seen=msk_ts(0, 10), hunger=80, health=90)   # сегодня был
    await make_frog(103, born_at=msk_ts(0, 8), last_seen=msk_ts(0, 8))                   # новичок
    await make_frog(104, born_at=born, last_seen=msk_ts(-1, 20), hibernation_until=msk_ts(5, 0))
    for d in range(1, 8):
        x_db("INSERT OR REPLACE INTO st_active(day,user_id,hits,hours) VALUES(?,?,?,?)",
             B.st_day(msk_ts(-d, 12)), 101, 5, 1 << 20)
    mine = {101, 102, 103, 104}
    ok(await run_at(msk_ts(0, 19, 50), mine) == [], "до любимого часа (20) — молчим")
    s = await run_at(msk_ts(0, 20, 5), mine)
    ok([x[0] for x in s] == [101], f"в 20:05 — только 101 ({[x[0] for x in s]})")
    ok(await run_at(msk_ts(0, 20, 30), mine) == [], "второй раз за день — нет")
    ok(await run_at(msk_ts(1, 2), mine) == [], "ночью — нет")
    r = q_db("SELECT remind_day, remind_variant, remind_credited FROM frogs WHERE user_id=101")[0]
    ok(r[0] == B.st_day(msk_ts(0, 12)) and r[1] and r[2] == 0, "записано: день, текст, ждём возврата")
    ok(q_db("SELECT sent FROM remind_ab WHERE variant=?", r[1])[0][0] == 1, "отправка посчитана в тексте")

    print("5. Вернулся — текст засчитан")
    g = await B.db_get(101)
    g["last_seen"] = msk_ts(0, 21)
    await B.db_save(g)
    uncache()
    await run_at(msk_ts(0, 21, 15), mine)
    ok(q_db("SELECT back FROM remind_ab WHERE variant=?", r[1])[0][0] == 1, "возврат за 12 ч засчитан")
    ok(q_db("SELECT remind_credited, remind_ignored FROM frogs WHERE user_id=101")[0] == (1, 0),
       "второй раз не засчитывается, счёт молчания сброшен")

    print("6. Молчит — реже, потом прощание, потом тишина")
    await make_frog(201, born_at=born, last_seen=msk_ts(-1, 12), hunger=80, health=90)
    sent_days = []
    for d in range(0, 16):
        s = await run_at(msk_ts(d, 20), {201})
        if s:
            sent_days.append((d, s[0][1]))
        g = await B.db_get(201)
        g.update(hunger=80, health=90, last_decay=msk_ts(d, 20))
        await B.db_save(g)
        uncache()
    days = [d for d, _ in sent_days]
    ok(days[:3] == [0, 1, 2], f"первые три дня — каждый день ({days})")
    gaps = [b - a for a, b in zip(days, days[1:])]
    ok(all(g >= 2 for g in gaps[2:]), f"дальше — через день ({days})")
    ok(len(days) == B.REMIND_GIVE_UP + 1, f"всего {B.REMIND_GIVE_UP + 1} писем ({len(days)})")
    ok("больше не будет" in sent_days[-1][1], "последнее — прощание")

    print("7. Вечером — «спаси серию», даже если заходил, но бонус не забрал")
    utc0 = datetime.fromtimestamp(msk_ts(0, 21, 10), timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    await make_frog(301, born_at=born, last_seen=msk_ts(0, 11), streak=12, last_daily=utc0 - 3600,
                    hunger=80, health=90)
    await make_frog(302, born_at=born, last_seen=msk_ts(0, 11), streak=12, last_daily=utc0 + 3600,
                    hunger=80, health=90)
    await make_frog(303, born_at=born, last_seen=msk_ts(0, 11), streak=1, last_daily=utc0 - 3600,
                    hunger=80, health=90)
    s = await run_at(msk_ts(0, 21, 10), {301, 302, 303})
    ok([x[0] for x in s] == [301], f"только у кого серия 3+ и бонус не забран ({[x[0] for x in s]})")
    if s:
        ok("12" in s[0][1] and btns(s[0][2]) == ["daily"], "серия в тексте, кнопка — бонус")
    ok(await run_at(msk_ts(0, 21, 40), {301}) == [], "«спаси серию» — раз за вечер")

    print("8. Звук: со звуком, но не больше двух в день")
    async def cls():
        B._PUSH_ACTOR.set(0); B._ST_SRC.set("job:daily_remind")
        return B.push_classify(5)
    ok(await asyncio.create_task(cls()) == "remind", "напоминание — свой вид")
    B._push_loud.clear()
    t = msk_ts(0, 15)
    ok([B._push_loud_ok(9, "remind", t) for _ in range(3)] == [True, True, False],
       "со звуком до двух в сутки")

    print("9. Старые напоминалки не дублируют")
    await make_frog(401, born_at=born, hunger=30, health=20, last_remind=0, remind_at=_time.time() - 3600,
                    last_seen=_time.time())
    await make_frog(402, born_at=born, hunger=0, health=50, last_remind=0, remind_at=0,
                    last_seen=_time.time())
    bot = FakeBot()
    real = B.db_all_alive
    async def only():
        return [await B.db_get(401), await B.db_get(402)]
    B.db_all_alive = only
    try:
        await B.job_reminders(types.SimpleNamespace(bot=bot))
    finally:
        B.db_all_alive = real
    to = [c for c, *_ in bot.sent]
    ok(401 not in to, "«расклеилась» больше не шлётся — это теперь ежедневное")
    ok(402 in to, "«голодает» (0%) — шлётся")
    ok(all(seg[0] >= 7 for seg in B._WINBACK_SEGMENTS), "winback начинается с 7 дней")

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
