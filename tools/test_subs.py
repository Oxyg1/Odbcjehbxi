"""
Подписки: один экран вместо трёх, «Автоуход» вместо «Няни», один пробник,
цены везде из STAR_PACKAGES, счётчик того, что сделал автоуход.

Запуск из корня репозитория:
    python3 tools/test_subs.py
    SHOW=1 python3 tools/test_subs.py   # ещё и напечатать экраны

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="subs_test_"), "test.db")
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

def plain(t):
    return re.sub(r"<[^>]+>", "", t or "")

def cbs(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row] if kb else []

def labels(kb):
    return [b.text for row in kb.inline_keyboard for b in row] if kb else []


class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.mid, self.sent = 100, []
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.mid += 1
        self.sent.append((chat_id, text, reply_markup))
        return Sent(self.mid)
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return Sent(1)
        return _noop


class Msg:
    def __init__(self, chat=1, text=None):
        self.chat = types.SimpleNamespace(id=chat, type="private")
        self.message_id, self.text = 1, text
        self.screens, self.replies = [], []
    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.screens.append((text, reply_markup))
        return self
    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.replies.append((text, reply_markup))
        return self
    async def edit_reply_markup(self, reply_markup=None, **kw):
        return self
    async def delete(self):
        return True
    @property
    def last(self):
        allm = self.screens + self.replies
        return allm[-1] if allm else ("", None)


class Q:
    def __init__(self, uid, data, msg):
        self.from_user = types.SimpleNamespace(id=uid, first_name="Т", username="", is_bot=False)
        self.data, self.message, self.answers = data, msg, []
    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append((text, show_alert))


BOT = FakeBot()
STORE, BD = {}, {}

def ctx_for(uid):
    return types.SimpleNamespace(bot=BOT, user_data=STORE.setdefault(uid, {}), bot_data=BD,
                                 args=[], application=None)

async def press(uid, data, router=None):
    msg = Msg(chat=uid)
    q = Q(uid, data, msg)
    upd = types.SimpleNamespace(callback_query=q, effective_user=q.from_user,
                                effective_chat=msg.chat, message=None)
    r = router or (B.shop_router if data.startswith(("shop_", "sub_")) else B.on_callback)
    await asyncio.create_task(r(upd, ctx_for(uid)))
    await asyncio.sleep(0.05)
    if os.environ.get("SHOW") and msg.last[0]:
        print(f"\n── {data}\n{plain(msg.last[0])}")
        for row in (msg.last[1].inline_keyboard if msg.last[1] else []):
            print("   " + " | ".join(f"[{b.text}]" for b in row))
    ok(len(q.answers) <= 1, f"{data}: на нажатие ответили {len(q.answers)} раз(а) — второй ответ Telegram не покажет")
    return q, msg


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


async def make_frog(uid, **fields):
    user = types.SimpleNamespace(id=uid, first_name=f"Игрок{uid}", username=f"user{uid}", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    await asyncio.sleep(0.2)
    sets = {"onboard_step": 0, "frog_name": f"Ква{uid}", "last_decay": _time.time(), "level": 5,
            "last_seen": _time.time(), **fields}
    x_db(f"UPDATE frogs SET {','.join(k + '=?' for k in sets)} WHERE user_id=?", *sets.values(), uid)
    B._user_cache.clear()


def befriend(a, b, level=0, xp=0):
    now = _time.time()
    for u, v in ((a, b), (b, a)):
        x_db("INSERT OR REPLACE INTO friendships(user_id,friend_id,level,xp,created_at,pending) "
             "VALUES(?,?,?,?,?,0)", u, v, level, xp, now)


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    now = _time.time()
    U, P = 701, 702
    await make_frog(U, coins=100)

    print("1. Экран без подписки")
    q, m = await press(U, "shop_sub")
    t, kb = plain(m.last[0]), m.last[1]
    ok("Автоуход" in t and "Трудяга" in t, "обе подписки описаны")
    ok("Няня" not in t and "Тётя" not in t, "без «Няни» и «Тёти Жабы»")
    ok(f"{B.SUB_NANNY_STARS}⭐" in t and f"{B.SUB_WORKER_STARS}⭐" in t, "цены из пакетов")
    ok(str(B.WORKER_AVG_DAY) in t, "сколько приносит Трудяга")
    ok("sub_trial_worker" in cbs(kb), "пробник")
    ok(any(f"{B.sub_price('nanny', 7)}⭐" in l for l in labels(kb)), "неделя — по настоящей цене")
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    ok("75⭐" not in src.replace("стояла цена 75⭐", ""), "цены 75⭐, которой нет, больше нигде нет")
    w = B._work_build_scene
    import statistics
    avg = statistics.mean(w()["earned"] for _ in range(5000))
    ok(abs(avg - B.WORKER_AVG_DAY) < 40, f"обещанное среднее совпадает с реальным ({avg:.0f})")

    print("2. /subscribe показывает тот же экран")
    m = Msg(chat=U, text="/subscribe")
    upd = types.SimpleNamespace(message=m, effective_user=types.SimpleNamespace(id=U, first_name="Т"),
                                effective_chat=m.chat)
    await B.cmd_subscribe(upd, ctx_for(U))
    ok(m.replies and "Трудяга" in plain(m.replies[-1][0]), "одинаковый экран")

    print("3. Пробник: 3 дня, и экран сразу показывает подписку")
    q, m = await press(U, "sub_trial_worker")
    g = await B.db_get(U)
    ok(abs(g["subscription_until"] - now - B.SUB_TRIAL_DAYS * 86400) < 120, "3 дня")
    t, kb = plain(m.last[0]), m.last[1]
    ok("Трудяга до" in t and "sub_renew" in cbs(kb), f"экран подписчика: {t!r}")
    ok(any(cid == U and "Завтра в 7:00" in plain(tx) for cid, tx, _ in BOT.sent), "в сообщении — что будет дальше")
    q, m = await press(U, "sub_trial_worker")
    ok(q.answers and q.answers[0][1], "второй пробник не дают")

    print("4. Счётчик автоухода")
    x_db("UPDATE frogs SET hunger=30, happiness=30, cleanliness=30, energy=30, last_decay=? WHERE user_id=?", now, U)
    B._user_cache.clear()
    await B.job_auto_care(types.SimpleNamespace(bot=BOT))
    q, m = await press(U, "shop_sub")
    t = plain(m.last[0])
    ok("покормил 1 раз" in t and "искупал 1 раз" in t, f"подписчик видит, что сделано: {t!r}")

    print("5. Пауза автоухода перерисовывает экран")
    q, m = await press(U, "sub_toggle_auto")
    ok("на паузе" in plain(m.last[0]), "пауза видна")
    q, m = await press(U, "sub_toggle_auto")
    ok("на паузе" not in plain(m.last[0]), "и снимается")

    print("6. Новая подписка после перерыва — счётчик заново")
    g = await B.db_get(U)
    g["subscription_until"] = now - 10
    B.auto_care_reset_if_new(g, now)
    ok(B.json.loads(g["auto_care_stats"]).get("feed") is None, "сброшен")

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
