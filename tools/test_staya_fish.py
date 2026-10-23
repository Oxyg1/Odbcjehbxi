"""
Стаи и рыбалка: поиск стаи с вожаком и активностью, заявка в одно нажатие,
решение только у вожака и старейшин, свой экран стаи, котёл, голосование,
магазин; рыбалка — игра из трёх забросов на двоих.

Запуск из корня репозитория:
    python3 tools/test_staya_fish.py
    SHOW=1 python3 tools/test_staya_fish.py   # ещё и напечатать экраны

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="staya_test_"), "test.db")
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
        self.mid, self.sent, self.edits = 100, [], {}
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.mid += 1
        self.sent.append((chat_id, text, reply_markup))
        return Sent(self.mid)
    async def edit_message_text(self, text, chat_id=None, message_id=None, parse_mode=None,
                                reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.edits[chat_id] = (text, reply_markup)
        return Sent(message_id)
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

async def press(uid, data):
    msg = Msg(chat=uid)
    q = Q(uid, data, msg)
    upd = types.SimpleNamespace(callback_query=q, effective_user=q.from_user,
                                effective_chat=msg.chat, message=None)
    await asyncio.create_task(B.on_callback(upd, ctx_for(uid)))
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

    CH, EL, MB, NEW, OUT = 601, 602, 603, 604, 605
    for u in (CH, EL, MB, NEW, OUT):
        await make_frog(u, coins=5000)
    x_db("UPDATE frogs SET last_seen=? WHERE user_id=?", now - 10 * 86400, OUT)
    # Живая стая и «мёртвая» с уровнем выше
    sid = q_db("SELECT COALESCE(MAX(id),0)+1 FROM stayas")[0][0]
    x_db("INSERT INTO stayas(id,name,emoji,creator_id,level,cauldron,created_at,invite_text) VALUES(?,?,?,?,?,?,?,?)",
         sid, "Кваки", "🐸", CH, 2, 100, now, "Играем каждый день, котёл качаем вместе")
    x_db("INSERT INTO stayas(id,name,emoji,creator_id,level,cauldron,created_at) VALUES(?,?,?,?,?,?,?)",
         sid + 1, "Тишина", "🪦", OUT, 9, 0, now)
    for u, r in ((CH, "chief"), (EL, "elder"), (MB, "member")):
        x_db("INSERT INTO staya_members(staya_id,user_id,role,joined_at) VALUES(?,?,?,?)", sid, u, r, now)
        x_db("UPDATE frogs SET staya_id=? WHERE user_id=?", sid, u)
    x_db("INSERT INTO staya_members(staya_id,user_id,role,joined_at) VALUES(?,?,?,?)", sid + 1, OUT, "chief", now)
    x_db("UPDATE frogs SET staya_id=? WHERE user_id=?", sid + 1, OUT)
    B._user_cache.clear()

    print("1. Поиск стаи: вожак, активность, текст стаи; живые выше")
    q, m = await press(NEW, "plaza_staya_list_0")
    t = plain(m.last[0])
    ok("Вожак — Ква601" in t, f"виден вожак: {t!r}")
    ok("активны 3" in t, "видно, сколько живых")
    ok("Играем каждый день" in t, "текст стаи в списке")
    ok(t.find("Кваки") < t.find("Тишина"), "живая стая выше мёртвой, хоть у той уровень выше")
    ok(f"plaza_staya_view_{sid}" in cbs(m.last[1]), "кнопка на карточку")

    print("2. Карточка стаи и заявка в одно нажатие")
    q, m = await press(NEW, f"plaza_staya_view_{sid}")
    t = plain(m.last[0])
    ok("Ква601" in t and "Ква602" in t, f"вожак и старейшина: {t!r}")
    ok(f"plaza_apply_{sid}" in cbs(m.last[1]), "кнопка заявки")
    BOT.sent.clear()
    q, m = await press(NEW, f"plaza_apply_{sid}")
    ok(q_db("SELECT status FROM staya_applications WHERE staya_id=? AND user_id=?", sid, NEW) == [("pending",)],
       "заявка подана без ввода текста")
    to = {c for c, *_ in BOT.sent}
    ok(CH in to and EL in to and MB not in to, f"узнали вожак и старейшина, не рядовой: {to}")
    ok(f"plaza_applymsg_{sid}" in cbs(m.last[1]) and f"plaza_applycancel_{sid}" in cbs(m.last[1]),
       "можно написать вожаку или отозвать")
    q, m = await press(MB, f"plaza_apply_{sid + 1}")
    ok(q.answers and q.answers[0][1] and "выйди" in q.answers[0][0], "из своей стаи в чужую не подать")

    print("3. Решают только вожак и старейшины")
    q, m = await press(MB, f"staya_app_ok_{NEW}")
    ok(q.answers and q.answers[0][1], "рядовой не может принять")
    ok(not q_db("SELECT 1 FROM staya_members WHERE user_id=? AND staya_id=?", NEW, sid), "и не принял")
    q, m = await press(EL, "staya_applications")
    ok(f"staya_app_ok_{NEW}" in cbs(m.last[1]), "старейшина видит заявку")
    q, m = await press(EL, f"staya_app_ok_{NEW}")
    ok(q_db("SELECT 1 FROM staya_members WHERE user_id=? AND staya_id=?", NEW, sid) != [], "принят")
    ok("Новых заявок нет" in plain(m.last[0]), "список заявок обновился")
    q, m = await press(EL, f"staya_app_ok_{NEW}")
    ok(q.answers and q.answers[0][1], "повторное принятие — объяснение")

    print("4. Свой экран стаи")
    q, m = await press(NEW, "plaza_staya")
    t = plain(m.last[0])
    ok("Кваки" in t and "4/" in t, f"стая и участники: {t!r}")
    ok("staya_leave" in cbs(m.last[1]) and "staya_disband" not in cbs(m.last[1]), "«Выйти», а не «Распустить»")
    ok("staya_applications" not in cbs(m.last[1]), "рядовому — без заявок")
    q, m = await press(CH, "plaza_staya")
    ok("staya_manage" in cbs(m.last[1]), "вожаку — управление")
    q, m = await press(CH, "staya_manage")
    ok("staya_disband" in cbs(m.last[1]), "распустить — в управлении")
    q, m = await press(NEW, "plaza_staya_members")
    ok(B.staya_role_label({}, "chief") in plain(m.last[0]), "участники по ролям")

    print("5. Котёл")
    q, m = await press(NEW, "staya_cauldron")
    ok("staya_cauldron_200" in cbs(m.last[1]), "кнопки взноса")
    q, m = await press(NEW, "staya_cauldron_200")
    ok(q_db("SELECT cauldron FROM stayas WHERE id=?", sid)[0][0] == 300, "в котле прибавилось")
    ok("Больше всех вложили" in plain(m.last[0]), "экран котла обновился")
    coins = (await B.db_get(NEW))["coins"]
    q, m = await press(NEW, "staya_cauldron_-500")
    ok((await B.db_get(NEW))["coins"] == coins, "отрицательный взнос не добавляет монет")
    x_db("UPDATE stayas SET cauldron=? WHERE id=?", B.STAYA_UPGRADES[3]["cost"] - 50, sid)
    q, m = await press(NEW, "staya_cauldron_50")
    ok(q_db("SELECT level FROM stayas WHERE id=?", sid)[0][0] == 3, "котёл поднял уровень")
    ok(q.answers and "ур. 3" in (q.answers[0][0] or ""), f"о росте сказано: {q.answers}")
    q, m = await press(NEW, "staya_level_info")
    ok("Следующий — 4." in plain(m.last[0]), "экран уровней")

    print("6. Голосование стаи")
    ev = B.STAYA_EVENT_POOL[0]
    x_db("INSERT INTO staya_events(staya_id,event_json,started_at,ends_at,finished) VALUES(?,?,?,?,0)",
         sid, B.json.dumps(ev, ensure_ascii=False), now, now + 3600)
    q, m = await press(NEW, "staya_events_view")
    vote_cbs = [c for c in cbs(m.last[1]) if c.startswith("staya_vote_")]
    ok(len(vote_cbs) == len(ev["choices"]), "варианты кнопками")
    q, m = await press(NEW, vote_cbs[0])
    t = plain(m.last[0])
    ok("твой голос" in t and ev["choices"][0]["label"] in t, f"виден свой голос подписью, а не ключом: {t!r}")
    ok(not any(c.startswith("staya_vote_") for c in cbs(m.last[1])), "второй раз не голосуем")
    q, m = await press(OUT, vote_cbs[0].replace(f"_{ev['choices'][0]['key']}", "") + f"_{ev['choices'][0]['key']}")
    ok(q.answers and q.answers[0][1], "чужая стая не голосует")

    print("7. Магазин")
    q, m = await press(NEW, "staya_shop")
    ok(any(c.startswith("staya_shop_vote_") for c in cbs(m.last[1])), "участник голосует за бустер")
    q, m = await press(NEW, next(c for c in cbs(m.last[1]) if c.startswith("staya_shop_vote_")))
    ok("← твой" in plain(m.last[0]), "свой голос виден")
    x_db("UPDATE stayas SET cauldron=4000 WHERE id=?", sid)
    q, m = await press(CH, "staya_shop")
    ok("staya_shop_buy_0" in cbs(m.last[1]) and "staya_shop_buy_2" not in cbs(m.last[1]),
       "вожак запускает только то, на что хватает")
    q, m = await press(CH, "staya_shop_buy_0")
    ok(q_db("SELECT cauldron FROM stayas WHERE id=?", sid)[0][0] == 1000, "оплачено из котла")

    print("8. Топ стай ведёт на карточки")
    q, m = await press(NEW, "staya_top_inline")
    ok(f"plaza_staya_view_{sid}" in cbs(m.last[1]), "из топа — на карточку стаи")

    print("9. Рыбалка: приглашение, три заброса, итог")
    A, Bp = 611, 612
    await make_frog(A, coins=500)
    await make_frog(Bp, coins=500)
    befriend(A, Bp, level=1, xp=5)
    q, m = await press(A, "plaza_fish_invite")
    ok("Три заброса" in plain(m.last[0]), "правила на экране выбора")
    q, m = await press(A, f"plaza_invite_fish_{Bp}")
    ok("Ждём ответа" in plain(m.last[0]), "отправитель ждёт")
    inv = BOT.sent[-1]
    ok(inv[0] == Bp and "Три заброса" in plain(inv[1]), "в приглашении правила")
    q, m = await press(Bp, f"fish_accept_{A}_{B.FISH_COST}")
    gid = q_db("SELECT MAX(id) FROM fish_games")[0][0]
    ok(gid, "игра создана")
    ok((await B.db_get(A))["coins"] == 450 and (await B.db_get(Bp))["coins"] == 450, "ставки списаны")
    ok(A in BOT.edits or any(c == A for c, *_ in BOT.sent), "игра показана и пригласившему")
    q, m = await press(Bp, f"fish_accept_{A}_{B.FISH_COST}")
    ok(q_db("SELECT COUNT(*) FROM fish_games")[0][0] == 1, "двойное нажатие — одна игра")

    def screen(u):
        return BOT.edits.get(u) or next(((t, k) for c, t, k in reversed(BOT.sent) if c == u), ("", None))

    def show(u, what):
        if os.environ.get("SHOW"):
            t, k = screen(u)
            print(f"\n── рыбалка у {u}: {what}\n{plain(t)}")
            for row in (k.inline_keyboard if k else []):
                print("   " + " | ".join(f"[{b.text}]" for b in row))
    show(Bp, "начало")
    ok(f"fishg_{gid}_reeds" in cbs(screen(A)[1]), "у пригласившего — выбор места")
    ok(f"fishg_{gid}_deep" in cbs(screen(Bp)[1]), "у принявшего — выбор места")
    q, m = await press(A, f"fishg_{gid}_lilies")
    ok("Ждём" in plain(screen(A)[0]), "после выбора — ждём соседа")
    show(A, "выбрал, ждёт")
    q, m = await press(A, f"fishg_{gid}_deep")
    ok(q.answers and q.answers[0][1], "второй раз за заброс не выбрать")
    q, m = await press(Bp, f"fishg_{gid}_lilies")
    st = B.json.loads(q_db("SELECT state FROM fish_games WHERE id=?", gid)[0][0])
    ok(st["round"] == 2 and st["log"][0]["clash"], "оба в кувшинки — распугали, заброс 2")
    ok("распугали" in plain(screen(A)[0]), "это видно в журнале")
    show(A, "после первого заброса")
    q, m = await press(613, f"fishg_{gid}_reeds")
    ok(q.answers and q.answers[0][1], "чужой не ходит")
    # Заброс 2 — один молчит: через 5 минут удочка сама в камышах
    await press(A, f"fishg_{gid}_deep")
    st["turn_at"] = now - 1000
    g = await B.fish_load(gid)
    g["state"]["turn_at"] = now - 1000
    await B.fish_save(g)
    await B.job_fish_timeouts(types.SimpleNamespace(bot=BOT))
    st = B.json.loads(q_db("SELECT state FROM fish_games WHERE id=?", gid)[0][0])
    ok(st["round"] == 3 and st["log"][1]["b"][0] == "reeds", "молчавшему закинули в камыши")
    await press(A, f"fishg_{gid}_reeds")
    await press(Bp, f"fishg_{gid}_deep")
    row = q_db("SELECT finished, state FROM fish_games WHERE id=?", gid)[0]
    ok(row[0] == 1, "три заброса — игра окончена")
    show(A, "итог")
    show(Bp, "итог у второго")
    st = B.json.loads(row[1])
    ca, cb = (await B.db_get(A))["coins"], (await B.db_get(Bp))["coins"]
    team = B.FISH_TEAM_BONUS if st["w"]["a"] + st["w"]["b"] >= B.FISH_TEAM_GOAL else 0
    want = {"a": (550 + team, 450 + team), "b": (450 + team, 550 + team), "": (500 + team, 500 + team)}[st["winner"]]
    ok((ca, cb) == want, f"расчёт банка: {(ca, cb)} при {st['w']}, ждали {want}")
    ok("Банк" in plain(screen(A)[0]) or "Ничья" in plain(screen(A)[0]), "итог понятен")
    ok("plaza" in cbs(screen(A)[1]), "из итога — на площадь")
    q, m = await press(A, f"plaza_invite_fish_{Bp}")
    ok(q.answers and q.answers[0][1], "второй раз за день не позвать")

    print("9б. Лечение стаи — только ухоженной лягушке")
    H1, H2 = 621, 622
    await make_frog(H1, health=80, hunger=90, happiness=90, cleanliness=90, energy=90, staya_id=sid)
    await make_frog(H2, health=80, hunger=90, happiness=90, cleanliness=10, energy=90, staya_id=sid)
    for u in (H1, H2):
        x_db("INSERT INTO staya_members(staya_id,user_id,role,joined_at) VALUES(?,?,?,?)", sid, u, "member", now)
    B._user_cache.clear()
    await B.job_hp_regen(types.SimpleNamespace(bot=BOT))
    B._user_cache.clear()
    h1, h2 = (await B.db_get(H1))["health"], (await B.db_get(H2))["health"]
    ok(h1 > 80, f"ухоженная лечится ({h1})")
    ok(h2 <= 80, f"грязная — нет: лечение не перекрывает плохой уход ({h2})")

    print("10. Ни одна кнопка не отвечает дважды")
    ok(not [a for a in FAILS if "раз(а)" in a], "двойных ответов нет")

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
