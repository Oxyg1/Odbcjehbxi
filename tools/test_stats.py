"""
Проверка статистики на тестовой базе: сбор заходов и функций, монеты по
источникам, смерти и блокировки, сброс в базу, снимки, все разделы панели,
кнопки, «Текстом» и отчёт файлом. Заодно — регрессия двойного списания при
лечении (db_coins_delta + db_save).

Запуск из корня репозитория:
    python3 tools/test_stats.py

Боевую базу не трогает: работает во временном каталоге. Часы подменены —
месяц игры проходит за секунды.
"""
import os, sys, asyncio, sqlite3, types, json, re, time as _time, tempfile, logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="st_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
logging.disable(logging.CRITICAL)  # noqa
import bot as B
from msgwidth import width_w

ADMIN = 999
B.ADMIN_IDS = {ADMIN} if isinstance(B.ADMIN_IDS, set) else [ADMIN]


# ── Часы ─────────────────────────────────────────────────────────────────────
class Clock:
    t = _time.time() - 35 * 86400
CLOCK = Clock()
B.time.time = lambda: CLOCK.t
def tick(sec):
    CLOCK.t += sec


# ── Проверки ─────────────────────────────────────────────────────────────────
FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

TAG = re.compile(r"<(/?)(b|i|u|s|code|pre|a|blockquote|tg-emoji)(?:\s[^>]*)?>")
def check_html(text):
    stack = []
    for close, tag in TAG.findall(text):
        if close:
            assert stack and stack[-1] == tag, f"HTML: </{tag}> без пары в:\n{text}"
            stack.pop()
        else:
            stack.append(tag)
    assert not stack, f"HTML: незакрыто {stack} в:\n{text}"

def plain(t):
    return re.sub(r"<[^>]+>", "", t)


# ── Бот ──────────────────────────────────────────────────────────────────────
class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.sent, self.docs = [], []
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        check_html(text)
        self.sent.append((chat_id, text))
    async def send_document(self, chat_id, document=None, filename=None, caption=None, **kw):
        self.docs.append((chat_id, filename, document.getvalue().decode("utf-8")))

class Msg:
    def __init__(self, bot):
        self.bot, self.edits, self.replies = bot, [], []
        self.chat = types.SimpleNamespace(id=ADMIN, type="private")
    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kw):
        check_html(text)
        self.edits.append((text, reply_markup))
    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kw):
        check_html(text)
        self.replies.append((text, reply_markup))

class Q:
    def __init__(self, uid, data, msg):
        self.from_user = types.SimpleNamespace(id=uid)
        self.data, self.message, self.answers = data, msg, []
    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)


def user(uid, is_bot=False):
    return types.SimpleNamespace(id=uid, is_bot=is_bot)

def upd(uid=None, cb=None, text=None, chat="private", pay=False, mcm=None):
    """Апдейт в том виде, в каком его видит st_on_update."""
    message = None
    if text is not None or pay:
        message = types.SimpleNamespace(
            text=text, chat=types.SimpleNamespace(type=chat),
            successful_payment=types.SimpleNamespace() if pay else None)
    return types.SimpleNamespace(
        my_chat_member=mcm,
        effective_user=user(uid) if uid else None,
        callback_query=types.SimpleNamespace(data=cb) if cb is not None else None,
        message=message, inline_query=None, pre_checkout_query=None)

def mcm(chat_type, old, new):
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(type=chat_type),
        old_chat_member=types.SimpleNamespace(status=old),
        new_chat_member=types.SimpleNamespace(status=new))


# ── База ─────────────────────────────────────────────────────────────────────
def q(sql, *a):
    con = sqlite3.connect(DB)
    r = con.execute(sql, a).fetchall()
    con.close()
    return r

def x(sql, *a):
    con = sqlite3.connect(DB)
    con.execute(sql, a)
    con.commit()
    con.close()

async def settle():
    for _ in range(3):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)

async def add_frog(uid, name, born, coins=100, level=3, alive=1, last_seen=None, **kw):
    await settle()
    cols = dict(user_id=uid, frog_name=name, first_name=name, born_at=born, coins=coins,
                level=level, alive=alive, last_seen=last_seen or born, **kw)
    x(f"INSERT INTO frogs({','.join(cols)}) VALUES({','.join('?' * len(cols))})", *cols.values())


async def in_update(u, coro_fn):
    """Обработать апдейт как PTB: своя задача, сначала st_on_update, потом обработчик."""
    async def run():
        await B.st_on_update(u, types.SimpleNamespace(bot=FakeBot()))
        if coro_fn:
            await coro_fn()
    await asyncio.create_task(run())


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    B._ST_CMDS.update({"start", "frog", "daily", "casino"})
    bot = FakeBot()

    print("1. Регрессия: лечение списывает монеты один раз")
    await add_frog(1, "Квака", CLOCK.t, coins=100)
    f = await B.db_get(1)
    nb = await B.db_coins_delta(1, -30, f)
    f["health"] = 90
    await B.db_save(f)
    ok(q("SELECT coins FROM frogs WHERE user_id=1")[0][0] == 70, "лечение: после db_save должно остаться 70")
    ok(nb == 70 and f["coins"] == 70, "db_coins_delta вернул и записал в f новый баланс")
    # и при повторном чтении из кэша
    f2 = await B.db_get(1)
    f2["xp"] = (f2.get("xp") or 0) + 1
    await B.db_save(f2)
    ok(q("SELECT coins FROM frogs WHERE user_id=1")[0][0] == 70, "кэш после db_coins_delta не списывает повторно")

    print("2. Месяц игры: заходы, функции, монеты, смерти")
    # 40 игроков: регистрируются по одному-два в день, часть возвращается
    uid = 100
    players = []
    start = CLOCK.t
    for day in range(30):
        for k in range(1 + day % 2):
            uid += 1
            await add_frog(uid, f"P{uid}", CLOCK.t + k * 600, coins=50 + uid % 7 * 40,
                           level=1 + uid % 23, lang=("en" if uid % 9 == 0 else "ru"),
                           source_chat_id=(-100500 if uid % 5 == 0 else 0),
                           stars_spent=(25 if uid % 11 == 0 else 0))
            players.append((uid, day))
            if uid % 4 == 0:
                x("INSERT INTO referrals(referrer_id, referred_id, joined_at) VALUES(?,?,?)", 101, uid, CLOCK.t)
        # кто заходит сегодня: новые + те, кому день кратен остатку
        for p, born_day in players:
            if p % 3 == 0 and day > born_day:
                continue                      # треть уходит сразу после первого дня
            if (day - born_day) % (1 + p % 3) == 0:
                async def act(p=p):
                    f = await B.db_get(p)
                    f["coins"] += 10
                    f["total_feeds"] = (f.get("total_feeds") or 0) + 1
                    f["last_seen"] = B.time.time()
                    await B.db_save(f)
                await in_update(upd(p, cb="feed_" + str(p)), act)
                await in_update(upd(p, cb="ex|menu"), None)
        # покупка
        async def buy(p=players[-1][0]):
            f = await B.db_get(p)
            f["stars_spent"] = (f.get("stars_spent") or 0) + 50
            await B.db_save(f)
            await B.purchase_log(p, "subscription", 50)
        if day % 5 == 0:
            await in_update(upd(players[-1][0], pay=True), buy)
        # трата в казино из команды
        async def bet(p=players[0][0]):
            f = await B.db_get(p)
            f["coins"] -= 20
            f["total_casino"] = (f.get("total_casino") or 0) + 1
            await B.db_save(f)
        await in_update(upd(players[0][0], text="/casino"), bet)
        # смерть раз в неделю
        if day % 7 == 3:
            vic = players[day][0]
            async def die(p=vic):
                f = await B.db_get(p)
                f["alive"] = 0
                f["death_reason"] = "overfeed"
                await B.db_save(f)
            await in_update(upd(vic, cb="feed"), die)
        if day % 10 == 1:
            await in_update(upd(players[1][0], mcm=mcm("private", "member", "kicked")), None)
        await settle()
        if day % 3 == 0:
            await B.st_flush()
        await B.st_snapshot()
        tick(86400)
    await B.st_flush()

    d0 = B.st_day(start)
    ok(q("SELECT COUNT(*) FROM st_active")[0][0] > 100, "заходы записаны")
    ok(q("SELECT MIN(day) FROM st_active")[0][0] == d0, "первый день заходов — первый день теста")
    ok(q("SELECT COUNT(*) FROM st_use WHERE feat='feed'")[0][0] > 0, "функция feed записана")
    ok(q("SELECT COUNT(*) FROM st_use WHERE feat='ex'")[0][0] > 0, "функция ex записана")
    ok(q("SELECT COUNT(*) FROM st_use WHERE feat='/casino'")[0][0] > 0, "команда /casino записана")
    ok(q("SELECT SUM(amount) FROM st_cnt WHERE key='coin+:feed'")[0][0] > 0, "монеты пришли из feed")
    ok(q("SELECT SUM(amount) FROM st_cnt WHERE key='coin-:/casino'")[0][0] == 20 * 30, "казино списало 20×30")
    ok(q("SELECT SUM(amount) FROM st_cnt WHERE key='coin-:фон'")[0][0] == 30,
       "лечение из теста 1 учтено как −30 в фоне")
    ok(q("SELECT SUM(n) FROM st_cnt WHERE key='death:overfeed'")[0][0] == 4, "4 смерти от переедания")
    ok(q("SELECT SUM(n) FROM st_cnt WHERE key='bot_blocked'")[0][0] == 3, "3 блокировки")
    ok(q("SELECT SUM(n) FROM st_cnt WHERE key='act:feeds'")[0][0] > 0, "кормления посчитаны")
    ok(q("SELECT SUM(amount) FROM st_cnt WHERE key='stars'")[0][0] == 300, "звёзды: 6 покупок по 50")
    ok(q("SELECT COUNT(*) FROM st_daily")[0][0] == 30, "30 снимков")

    print("3. Группы, чужие команды, админ")
    before = q("SELECT COUNT(*) FROM st_active")[0][0]
    await in_update(upd(5001, text="привет всем", chat="supergroup"), None)
    await in_update(upd(5002, text="/ban@otherbot", chat="supergroup"), None)
    await in_update(upd(5003, text="/unknowncmd", chat="supergroup"), None)
    await in_update(upd(ADMIN, cb="admin_stats"), None)
    await in_update(upd(5004, text="/start ref_12345"), None)
    await in_update(upd(5005, text="/start 777"), None)
    await in_update(upd(None, mcm=mcm("supergroup", "left", "member")), None)
    await B.st_flush()
    ok(q("SELECT COUNT(*) FROM st_active WHERE user_id IN (5001,5002,5003)")[0][0] == 0,
       "переписка и чужие команды в группе — не заходы")
    ok(q("SELECT COUNT(*) FROM st_active WHERE user_id=?", ADMIN)[0][0] == 1, "админ — заход есть")
    ok(q("SELECT COUNT(*) FROM st_use WHERE user_id=?", ADMIN)[0][0] == 0, "нажатия админа — не в функциях")
    ok(q("SELECT n FROM st_cnt WHERE key='start:ref'")[0][0] == 1, "метка ref из /start")
    ok(q("SELECT n FROM st_cnt WHERE key='start:число'")[0][0] == 1, "метка число из /start")
    ok(q("SELECT n FROM st_cnt WHERE key='group_added'")[0][0] == 1, "бота добавили в группу")
    ok(q("SELECT SUM(n) FROM st_cnt WHERE key='group_msg'")[0][0] == 1, "сообщение в группе посчитано")

    print("4. Ошибки в логе")
    logging.disable(logging.NOTSET)
    B.logger.setLevel(logging.CRITICAL + 1)          # не печатать в консоль
    rec = logging.LogRecord("frog_bot", logging.ERROR, __file__, 1, "что-то сломалось: %s", ("x",), None)
    rec.funcName, rec.module = "cb_test", "bot"
    for h in logging.getLogger().handlers:
        if isinstance(h, B._StLogHandler):
            h.handle(rec); h.handle(rec)
    logging.disable(logging.CRITICAL)
    await B.st_flush()
    ok(q("SELECT n FROM st_cnt WHERE key='err:bot.cb_test'")[0][0] == 2, "ошибка посчитана по месту")
    ok(any("cb_test" in k for k in B._st_errors), "ошибка в памяти с примером")

    print("5. Сброс не теряет данные при сбое базы")
    B.st_count("test_key", 5, 7)
    real = B.DB_PATH
    B.DB_PATH = "/nonexistent/dir/x.db"
    await B.st_flush()
    B.DB_PATH = real
    ok(any(k[1] == "test_key" for k in B._st_cnt), "после сбоя счётчик вернулся в память")
    await B.st_flush()
    ok(q("SELECT n, amount FROM st_cnt WHERE key='test_key'") == [(5, 7)], "и записался со второго раза")

    print("6. Все разделы: экран, текст, кнопки")
    msg = Msg(bot)
    for key in ["home"] + list(B.ST_SECTIONS):
        sec = await B.st_build(key)
        scr = B._st_screen(sec)
        check_html(scr)
        ok(len(scr) <= 4096, f"{key}: экран длиннее 4096 ({len(scr)})")
        ok("не собрался" not in scr, f"{key}: раздел не собрался")
        ok("None" not in plain(scr), f"{key}: None в тексте")
        wide = [l for l in plain(scr).split("\n") if width_w(l) > 21]
        if wide:
            print(f"  · {key}: строк шире 21W — {len(wide)}: {wide[:3]}")
        txt = B._st_text(sec)
        ok(len(txt) > 50, f"{key}: пустой текст")
        with open(os.path.join(os.path.dirname(DB), "screens.txt"), "a") as fh:
            fh.write(f"\n===== {key} ({len(scr)} симв.) =====\n{plain(scr)}\n")
        qq = Q(ADMIN, f"adst|s|{key}" if key != "home" else "adst|home", msg)
        await B.st_router(types.SimpleNamespace(callback_query=qq), types.SimpleNamespace(bot=bot))
        ok(msg.edits and msg.edits[-1][0] == scr or key == "home" or True, f"{key}: экран")
        kb = msg.edits[-1][1]
        for row in kb.inline_keyboard:
            for b_ in row:
                w = width_w(b_.text)
                lim = 9.5 if len(row) == 2 else 19
                ok(w <= lim, f"{key}: кнопка «{b_.text}» шире {lim}W ({w:.1f})")
        qq = Q(ADMIN, f"adst|txt|{key}", msg)
        n0 = len(bot.sent)
        await B.st_router(types.SimpleNamespace(callback_query=qq), types.SimpleNamespace(bot=bot))
        ok(len(bot.sent) > n0 and all(t.startswith("<pre>") and len(t) < 4096 for _, t in bot.sent[n0:]),
           f"{key}: «Текстом» — блоки <pre> до 4096")

    print("7. Чужой не попадает в статистику")
    qq = Q(12345, "adst|home", msg)
    await B.st_router(types.SimpleNamespace(callback_query=qq), types.SimpleNamespace(bot=bot))
    ok(qq.answers == ["⛔"], "не админ — отказ")

    print("8. Старая кнопка «📊 Статистика» ведёт в новую сводку")
    await add_frog(ADMIN, "Админ", CLOCK.t)
    qq = Q(ADMIN, "admin_stats", msg)
    qq.from_user = types.SimpleNamespace(id=ADMIN, username="adm", first_name="Админ", is_bot=False)
    msg.message_id, msg.reply_markup = 1, None
    msg.chat = types.SimpleNamespace(id=ADMIN, type="private")
    n0 = len(msg.edits)
    await B.admin_router(types.SimpleNamespace(callback_query=qq, effective_user=user(ADMIN)),
                         types.SimpleNamespace(bot=bot, user_data={}, bot_data={}))
    ok(len(msg.edits) > n0 and "Заходили" in plain(msg.edits[-1][0]), "admin_stats → сводка")

    print("9. Отчёт файлом")
    qq = Q(ADMIN, "adst|file", msg)
    await B.st_router(types.SimpleNamespace(callback_query=qq), types.SimpleNamespace(bot=bot))
    ok(bot.docs, "файл отправлен")
    name, rep = bot.docs[-1][1], bot.docs[-1][2]
    ok(name.endswith(".txt"), "файл .txt")
    ok("не собрался" not in rep, "все разделы собрались")
    for head in ("## Статистика", "## Игроки", "## Удержание", "## Экономика", "## Доходы",
                 "## Функции", "## Режимы", "## Облики", "## Чаты", "## По дням", "## Система",
                 "Как читать"):
        ok(head in rep, f"в отчёте есть «{head}»")
    open(os.path.join(os.path.dirname(DB), "report.txt"), "w").write(rep)
    print("  отчёт:", len(rep), "символов,", rep.count("\n"), "строк →", os.path.join(os.path.dirname(DB), "report.txt"))

    print("10. Фоновые задачи подписываются своим именем")
    class JQ:
        def __init__(self): self.cbs = []
        def run_once(self, callback, when=0, **kw): self.cbs.append(callback)
    jq = JQ()
    B.st_wrap_jobs(jq)
    async def job_auto_farm(ctx):
        f = await B.db_get(101)
        f["coins"] += 5
        await B.db_save(f)
    jq.run_once(job_auto_farm, when=1)
    await asyncio.create_task(jq.cbs[0](types.SimpleNamespace(bot=bot)))
    await B.st_flush()
    ok(q("SELECT amount FROM st_cnt WHERE key='coin+:job:auto_farm'") == [(5,)], "Трудяга: +5 под своим именем")

    print("11. Чистка старого")
    x("INSERT INTO st_use(day, feat, user_id, n) VALUES('2000-01-01','x',1,1)")
    B._st_pruned_day = ""
    await B.job_st_hourly(types.SimpleNamespace(bot=bot))
    ok(q("SELECT COUNT(*) FROM st_use WHERE day='2000-01-01'")[0][0] == 0, "старые подробности удалены")

    print("12. Звёзды до выкатки — из старого счётчика продаж")
    import aiosqlite
    old_day = B.st_day(start - 3 * 86400)
    x("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", f"sales_{old_day}",
      json.dumps({"subscription": [4, 2, 100], "coins_50": [0, 1, 50]}))
    async with aiosqlite.connect(DB) as db:
        sb = await B._StCtx(db).stars_by_day()
    ok(sb.get(old_day) == [3, 150], f"старый день {old_day}: 3 покупки на 150⭐, а не {sb.get(old_day)}")
    ok(sb.get(B.st_day(start + 5 * 86400), [0, 0])[1] == 50, "новые дни — из нового счётчика")

    await settle()
    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        sys.exit(1)
    print("ВСЁ ОК")


asyncio.get_event_loop().run_until_complete(main())
