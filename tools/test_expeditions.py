"""
Проверка экспедиций на тестовой базе: соло, команда, голоса и ничья,
молчание, личные находки, возврат при пустом запасе, простой бота,
находки и облик за набор, сбор, экраны и все кнопки.

Запуск из корня репозитория:
    python3 tools/test_expeditions.py

Боевую базу не трогает: работает во временном каталоге. Часы подменены —
двухчасовая экспедиция проходит за секунды.
"""
import os, sys, asyncio, sqlite3, types, json, re, random, time as _time

import tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="ex_test_"), "test.db")
for suf in ("", "-wal", "-shm"):
    try:
        os.remove(DB + suf)
    except FileNotFoundError:
        pass
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import logging
logging.disable(logging.WARNING)
import bot as B
from msgwidth import width_w

# ── Часы ─────────────────────────────────────────────────────────────────────
class Clock:
    t = _time.time()
CLOCK = Clock()
B.time.time = lambda: CLOCK.t
def tick(sec):
    CLOCK.t += sec

# ── Бот ──────────────────────────────────────────────────────────────────────
class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.mid = 1000
        self.log = []          # (kind, chat, mid, text, kb)
        self.msgs = {}         # (chat, mid) -> (text, kb)
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self.mid += 1
        self.log.append(("send", chat_id, self.mid, text, reply_markup))
        self.msgs[(chat_id, self.mid)] = (text, reply_markup)
        check_html(text)
        return Sent(self.mid)
    async def edit_message_text(self, text, chat_id=None, message_id=None, parse_mode=None,
                                reply_markup=None, **kw):
        self.log.append(("edit", chat_id, message_id, text, reply_markup))
        self.msgs[(chat_id, message_id)] = (text, reply_markup)
        check_html(text)
    async def edit_message_reply_markup(self, chat_id=None, message_id=None, reply_markup=None):
        t, _ = self.msgs.get((chat_id, message_id), ("", None))
        self.msgs[(chat_id, message_id)] = (t, reply_markup)
        self.log.append(("markup", chat_id, message_id, None, reply_markup))
    async def send_invoice(self, **kw):
        self.log.append(("invoice", kw.get("chat_id"), 0, kw.get("payload"), None))
    def last_to(self, uid, kind=None):
        for e in reversed(self.log):
            if e[1] == uid and (kind is None or e[0] == kind):
                return e
    def sends_to(self, uid):
        return [e for e in self.log if e[1] == uid and e[0] == "send"]

ANN = []
async def fake_announce(bot, text, reply_markup=None, **kw):
    ANN.append(text); check_html(text)
B.announce = fake_announce

TAG = re.compile(r"<(/?)([a-z\-]+)[^>]*>")
def check_html(text):
    stack = []
    for close, tag in TAG.findall(text):
        if close:
            assert stack and stack[-1] == tag, f"HTML: </{tag}> без пары в:\n{text}"
            stack.pop()
        else:
            stack.append(tag)
    assert not stack, f"HTML: незакрыто {stack} в:\n{text}"
    assert "{" not in re.sub(r"<[^>]+>", "", text), f"неподставленный шаблон:\n{text}"

def kb_data(kb):
    return [b.callback_data for row in (kb.inline_keyboard if kb else []) for b in row]

def plain(t):
    return re.sub(r"<[^>]+>", "", t)

# ── База ─────────────────────────────────────────────────────────────────────
def setup_db():
    B.run_sync_migration()
    asyncio.get_event_loop().run_until_complete(B.init_db())
    B.run_sync_migration()

def add_frog(uid, name, level=5, coins=100):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO frogs(user_id, frog_name, first_name, level, coins, alive, last_expedition) "
                "VALUES(?,?,?,?,?,1,0)", (uid, name, name, level, coins))
    con.commit(); con.close()

def q(sql, *a):
    con = sqlite3.connect(DB)
    r = con.execute(sql, a).fetchall()
    con.close()
    return r

async def coins(uid):
    B._user_cache.invalidate(uid)
    return (await B.db_get(uid))["coins"]


# ══ Движок ══
R = B.EX_ROUTES["reeds"]
N = R["stops"]
GAP = R["hours"] * 3600 / N

async def tick_job():
    await B.job_ex_tick(types.SimpleNamespace(bot=bot))

def run_row(rid):
    return asyncio.get_event_loop().run_until_complete(B.ex_run_get(rid))

async def suite_engine():
    # ── 0. Данные маршрутов ──────────────────────────────────────────────────
    errs = B.ex_validate_content()
    assert not errs, errs
    for c in R["cards"] + [R["finale"]]:
        head = f"{R['emoji']} {c['title']} · 6/6"
        assert width_w(head) <= 19, (head, width_w(head))
        for o in c["options"]:
            assert width_w(o["label"]) <= 19, (o["label"], width_w(o["label"]))
            hint = f"{B._ex_opt_emoji(o)} {B.ex_option_hint(o, html=False)}"
            assert width_w(hint) <= 21, (hint, width_w(hint))
    for k, fd in B.EX_FINDS.items():
        line = f"{fd['emoji']} {fd['name']} · новая, 6/6"
        assert width_w(line) <= 21, (line, width_w(line))
    print("0 данные: ок")

    # ── 1. Соло: голос сразу закрывает стоянку, молчание — осторожный вариант ──
    add_frog(1, "Квака", level=1, coins=100)
    f1 = await B.db_get(1)
    rid, why = await B.ex_lobby_create(f1, "reeds", 0)
    assert rid and not why
    await B.ex_set_msg(rid, 1, 555)
    assert await B.ex_start(bot, rid)
    run = await B.ex_run_get(rid)
    assert run["status"] == "active" and run["step"] == 0, run
    stop0 = bot.last_to(1, "send")
    assert "1/6" in plain(stop0[3]) and kb_data(stop0[4])
    assert (await B.db_get(1))["last_expedition"] == CLOCK.t
    # голос
    plan = json.loads(run["plan_json"])
    card0 = B.ex_card("reeds", plan[0]["card"])
    risky = card0["options"][1]["key"]
    msg = await B.ex_vote(bot, rid, 0, 1, risky)
    run = await B.ex_run_get(rid)
    assert run["resolved"] == 0, run
    ed = bot.msgs[(1, stop0[2])]
    assert ed[1] is None and "Голоса" not in plain(ed[0]), ed
    # повторный голос после закрытия
    assert "позади" in await B.ex_vote(bot, rid, 0, 1, risky)
    # стоянки 2..5 — молчание
    for i in range(1, N):
        tick(GAP)
        await tick_job()
        run = await B.ex_run_get(rid)
        assert run["step"] == i, (i, run["step"])
        if i < N - 1:
            tick(GAP - 5)
            await tick_job()  # ещё открыта
            assert (await B.ex_run_get(rid))["resolved"] == i - 1
            tick(5)
            await tick_job()  # закрылась и открылась следующая (если пора)
            tick(-GAP)
    # финал: ждём закрытия
    tick(GAP + 1)
    await tick_job()
    run = await B.ex_run_get(rid)
    assert run["status"] == "finished" and run["outcome"] in ("done", "turned_back"), run
    log = json.loads(run["log_json"])
    assert len(log) == N or run["outcome"] == "turned_back"
    assert all(e["why"] == "silence" for e in log[1:]), log
    final = bot.last_to(1, "send")
    assert "итог" in plain(final[3]), final[3]
    m = (await B.ex_members_get(rid))[0]
    assert await coins(1) == 100 + m["coins"], (await coins(1), m["coins"])
    print("1 соло: ок", run["outcome"], "loot", run["loot"], "supply", run["supply"], "coins", m["coins"])
    print(plain(final[3]))

    # второй раз за сутки нельзя
    f1 = await B.db_get(1)
    assert await B.ex_cant_go(f1, "reeds") == "today"

    # ── 2. Команда из трёх: сбор, голоса, ничья, личные находки ──────────────
    for uid, name in ((2, "Жаба"), (3, "Ряска"), (4, "Тина"), (5, "Кувшинка")):
        add_frog(uid, name, level=3)
    f2 = await B.db_get(2)
    rid, _ = await B.ex_lobby_create(f2, "reeds", 10)
    await B.ex_set_msg(rid, 2, 777)
    assert await B.ex_lobby_join(await B.db_get(3), rid) == ""
    await B.ex_set_msg(rid, 3, 778)
    assert await B.ex_lobby_join(await B.db_get(4), rid) == ""
    await B.ex_set_msg(rid, 4, 779)
    # двойной вход не дублирует
    assert "уже" in await B.ex_lobby_join(await B.db_get(4), rid)
    await B.ex_lobby_refresh(bot, rid)
    lob = bot.msgs[(2, 777)]
    assert "3/4" in plain(lob[0]) and "ex|go|%d" % rid in kb_data(lob[1]), lob
    assert "ex|leave|%d" % rid in kb_data(bot.msgs[(3, 778)][1])
    # Тина выходит, Кувшинка входит
    assert await B.ex_lobby_leave(bot, rid, 4) == ""
    assert await B.ex_lobby_join(await B.db_get(5), rid) == ""
    await B.ex_set_msg(rid, 5, 780)
    # создатель не выходит
    assert "отменяет" in await B.ex_lobby_leave(bot, rid, 2)
    # сбор истёк — тик стартует
    tick(10 * 60 + 1)
    await tick_job()
    run = await B.ex_run_get(rid)
    assert run["status"] == "active" and run["step"] == 0
    members = await B.ex_members_get(rid)
    assert [m["user_id"] for m in members] == [2, 3, 5]
    pers = {m["user_id"]: m["pers_step"] for m in members}
    assert all(1 <= s <= N - 2 for s in pers.values()), pers
    # стоянка 0: 2 за рискованный, 1 за осторожный — побеждает рискованный
    plan = json.loads(run["plan_json"])
    card = B.ex_card("reeds", plan[0]["card"])
    o0, o1 = card["options"][0]["key"], card["options"][1]["key"]
    await B.ex_vote(bot, rid, 0, 2, o1)
    s2 = bot.last_to(2, "edit")
    assert "Ещё не ответили" in plain(s2[3]), plain(s2[3])
    await B.ex_vote(bot, rid, 0, 3, o0)
    await B.ex_vote(bot, rid, 0, 3, o1)   # передумала
    await B.ex_vote(bot, rid, 0, 5, o0)
    run = await B.ex_run_get(rid)
    e = json.loads(run["log_json"])[0]
    assert e["opt"] == o1 and e["votes"] == {o1: 2, o0: 1}, e
    # чужой не голосует
    tick(GAP); await tick_job()
    _c1 = B.ex_card("reeds", plan[1]["card"])["options"][0]["key"]
    assert "не в этой" in await B.ex_vote(bot, rid, 1, 99, _c1)
    # стоянка 1: ничья 1:1, третий молчит → осторожный
    plan_card = B.ex_card("reeds", plan[1]["card"])
    a, b_ = plan_card["options"][0]["key"], plan_card["options"][1]["key"]
    await B.ex_vote(bot, rid, 1, 2, b_)
    await B.ex_vote(bot, rid, 1, 3, a)
    tick(GAP); await tick_job()
    e = json.loads((await B.ex_run_get(rid))["log_json"])[1]
    assert e["opt"] == a and e["why"] == "tie", e
    # личные находки: Жаба берёт себе, как только её находка открылась
    keep_done = False
    for i in range(2, N):
        run = await B.ex_run_get(rid)
        if run["status"] != "active":
            break
        for m in await B.ex_members_get(rid):
            if m["user_id"] == 2 and m["pers_step"] == run["step"] and not keep_done:
                assert await B.ex_personal_choose(bot, rid, 2, "keep") == "Себе"
                assert "Уже" in await B.ex_personal_choose(bot, rid, 2, "share")
                keep_done = True
        tick(GAP); await tick_job()
    tick(GAP); await tick_job()
    run = await B.ex_run_get(rid)
    assert run["status"] == "finished", run
    members = await B.ex_members_get(rid)
    ch = {m["user_id"]: m["pers_choice"] for m in members}
    if run["outcome"] == "done":
        assert ch[2] == "keep" and ch[3] == "share" and ch[5] == "share", ch
    for m in members:
        p = B.ex_payout(run, members, m)
        assert m["coins"] == p["total"]
    p2 = B.ex_payout(run, members, members[0])
    print("2 команда: ок", run["outcome"], "loot", run["loot"], "mult", p2["mult"],
          "выплаты", [m["coins"] for m in members])
    print(plain(bot.last_to(2, "send")[3]))

    # ── 3. Запас кончился — домой с половиной ────────────────────────────────
    add_frog(6, "Осока", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(6), "reeds", 0)
    real_roll = B._ex_roll
    B._ex_roll = lambda opt: len(opt["outcomes"]) - 1   # всегда худший исход
    await B.ex_start(bot, rid)
    for i in range(N):
        run = await B.ex_run_get(rid)
        if run["status"] != "active":
            break
        plan = json.loads(run["plan_json"])
        card = B.ex_card("reeds", plan[run["step"]]["card"])
        # самый «дорогой по запасу» худший исход
        worst = min(card["options"], key=lambda o: o["outcomes"][-1].get("supply", 0))
        await B.ex_vote(bot, rid, run["step"], 6, worst["key"])
        tick(GAP); await tick_job()
    B._ex_roll = real_roll
    run = await B.ex_run_get(rid)
    m = (await B.ex_members_get(rid))[0]
    p = B.ex_payout(run, [m], m)
    print("3 запас:", run["outcome"], "supply", run["supply"], "loot", run["loot"], "выплата", m["coins"])
    if run["outcome"] == "turned_back":
        assert p["loot_paid"] == run["loot"] // 2 and p["supply_bonus"] == 0
        assert "повернула домой" in plain(bot.last_to(6, "send")[3])

    # ── 4. Простой бота: стоянка после долгого перерыва открыта ≥10 мин ─────
    add_frog(7, "Ил", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(7), "reeds", 0)
    await B.ex_start(bot, rid)
    B._EX_LOCKS.clear()                       # «перезапуск»
    tick(3 * GAP + 60)                         # бот лежал
    await tick_job()                           # закрыть 0, открыть 1
    run = await B.ex_run_get(rid)
    assert run["resolved"] == 0 and run["step"] == 1, run
    assert run["closes_at"] >= CLOCK.t + B.EX_MIN_WINDOW_S - 1, (run["closes_at"] - CLOCK.t)
    await tick_job()
    assert (await B.ex_run_get(rid))["step"] == 1  # окно ещё идёт
    tick(B.EX_MIN_WINDOW_S); await tick_job()
    run = await B.ex_run_get(rid)
    assert run["resolved"] == 1 and run["step"] == 2, run
    print("4 простой: ок")
    await B.ex_stop(bot, rid)
    assert (await B.ex_run_get(rid))["outcome"] == "stopped"

    # ── 5. Находки: каждому, повтор — монетами, полный набор — облик ─────────
    add_frog(8, "Ряска2", level=1); add_frog(9, "Тина2", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(8), "reeds", 5)
    await B.ex_lobby_join(await B.db_get(9), rid)
    await B.ex_start(bot, rid)
    run = await B.ex_run_get(rid)
    members = await B.ex_members_get(rid)
    names = await B._ex_names(members)
    keys = [k for k, v in B.EX_FINDS.items() if v["route"] == "reeds"]
    for k in keys[:-1]:
        await B._ex_grant_find(bot, run, members, k, names)
    await B._ex_grant_find(bot, run, members, keys[0], names)     # повтор
    assert not ANN
    await B._ex_grant_find(bot, run, members, keys[-1], names)    # набор
    assert len(ANN) == 2, ANN
    assert q("SELECT COUNT(*) FROM collections WHERE user_id=8 AND skin='Reed Rambler'")[0][0] == 1
    await B._ex_grant_find(bot, run, members, keys[-1], names)    # снова — облик не дублируется
    assert len(ANN) == 2
    members = await B.ex_members_get(rid)
    p = B.ex_payout(run, members, members[0])
    assert p["dup"] == 2 * B.EX_DUP_FIND_COINS, p
    await B.ex_stop(bot, rid)
    print("5 находки: ок")
    text, _ = await B.ex_finds_view(8)
    print(plain(text))

    # ── 6. Проверки сбора ───────────────────────────────────────────────────
    add_frog(10, "Лист", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(10), "reeds", 5)
    for uid in (11, 12, 13, 14):
        add_frog(uid, f"Л{uid}", level=1)
    for uid in (11, 12, 13):
        assert await B.ex_lobby_join(await B.db_get(uid), rid) == ""
    assert "уже 4" in await B.ex_lobby_join(await B.db_get(14), rid)
    # создатель отменяет
    assert await B.ex_lobby_cancel(bot, rid)
    assert (await B.ex_run_get(rid))["status"] == "cancelled"
    assert await B.ex_user_run(11) is None
    # день не сгорел — сбор не стартовал
    assert await B.ex_cant_go(await B.db_get(11), "reeds") == ""
    print("6 сбор: ок")

    # ── 7. Экраны ───────────────────────────────────────────────────────────
    add_frog(20, "Экран", level=1)
    f20 = await B.db_get(20)
    for view in (B.ex_menu_view(f20), B.ex_route_view(f20, "reeds"), B.ex_finds_view(20),
                 B.ex_admin_view()):
        text, kb = await view
        check_html(text)
    text, kb = B.ex_gather_view("reeds"); check_html(text)
    text, kb = await B.ex_menu_view(f20)
    print(plain(text)); print(kb_data(kb))
    text, kb = await B.ex_route_view(f20, "reeds")
    print(plain(text)); print(kb_data(kb))
    text, kb = await B.ex_admin_view()
    print(plain(text))
    print("7 экраны: ок")



# ══ Кнопки ══
B.ADMIN_IDS = set(B.ADMIN_IDS) | {101}

class Msg:
    def __init__(self, chat, mid):
        self.chat_id, self.message_id = chat, mid
        self.text = ""
    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kw):
        check_html(text)
        bot.msgs[(self.chat_id, self.message_id)] = (text, reply_markup)
        bot.log.append(("edit", self.chat_id, self.message_id, text, reply_markup))
class Q:
    def __init__(self, uid, d, mid=1):
        self.from_user = types.SimpleNamespace(id=uid); self.data = d
        self.message = Msg(uid, mid); self.answers = []
    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)

async def press(uid, d, mid=1):
    q = Q(uid, d, mid)
    f = await B.db_get(uid)
    async def guard(update, ctx): return (q, uid, d, f)
    B.cb_guard = guard
    await B.ex_router(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=bot))
    shown = bot.msgs.get((uid, mid), ("", None))
    return q, shown

async def suite_router():
    add_frog(101, "Квака", level=1); add_frog(102, "Жаба", level=1); add_frog(103, "Ряска", level=1)
    ann0 = len(ANN)
    q, (t, kb) = await press(101, "ex|menu", 10)
    assert "Экспедиции" in plain(t)
    q, (t, kb) = await press(101, "ex|route|reeds", 10)
    q, (t, kb) = await press(101, "ex|team|reeds", 10)
    assert kb_data(kb)[:4] == [f"ex|make|reeds|{m}" for m in B.EX_GATHER_MIN], kb_data(kb)
    q, (t, kb) = await press(101, "ex|make|reeds|5", 10)
    print(plain(t)); print(kb_data(kb), [b.url for row in kb.inline_keyboard for b in row if b.url])
    run = await B.ex_user_run(101)
    rid = run["id"]
    # двойное создание — отказ
    q, _ = await press(101, "ex|make|reeds|5", 11)
    assert "уже" in (q.answers[-1] or ""), q.answers
    # Жаба видит сбор в меню и вступает
    q, (t, kb) = await press(102, "ex|menu", 20)
    assert f"ex|join|{rid}" in kb_data(kb), kb_data(kb)
    q, (t, kb) = await press(102, f"ex|join|{rid}", 20)
    assert "2/4" in plain(bot.msgs[(101, 10)][0]), plain(bot.msgs[(101, 10)][0])
    # не создатель не стартует
    q, _ = await press(102, f"ex|go|{rid}", 20)
    assert "создатель" in q.answers[-1]
    # объявление в чат — один раз
    q, _ = await press(101, f"ex|call|{rid}", 10)
    q, _ = await press(101, f"ex|call|{rid}", 10)
    assert len(ANN) == ann0 + 1, ANN
    print("анонс:", plain(ANN[-1]))
    # Ряска вступает и выходит
    q, _ = await press(103, f"ex|join|{rid}", 30)
    q, (t, kb) = await press(103, f"ex|leave|{rid}", 30)
    assert "Экспедиции" in plain(t)
    # старт
    q, (t, kb) = await press(101, f"ex|go|{rid}", 10)
    print(plain(bot.msgs[(101, 10)][0]))
    run = await B.ex_run_get(rid)
    stop = bot.last_to(101, "send")
    print(plain(stop[3])); print(kb_data(stop[4]))
    # голос кнопкой
    vd = kb_data(stop[4])[1]
    q, _ = await press(101, vd, stop[2])
    print("всплывашка:", q.answers)
    s2 = bot.msgs[(101, stop[2])][0]
    print(plain(s2))
    # «К стоянке» из меню
    q, (t, kb) = await press(102, "ex|menu", 21)
    print(plain(t)); print(kb_data(kb))
    q, _ = await press(102, f"ex|here|{rid}", 21)
    resent = bot.last_to(102, "send")
    assert resent and kb_data(resent[4]), resent
    q, _ = await press(102, kb_data(resent[4])[0], resent[2])
    run = await B.ex_run_get(rid)
    assert run["resolved"] == 0, run
    print(plain(bot.msgs[(102, resent[2])][0]))
    # находки, звёзды, админ
    q, (t, kb) = await press(101, "ex|finds", 12)
    q, _ = await press(101, "ex|stars", 12)
    assert bot.last_to(101, "invoice")[3] == "exp_extra_slot"
    q, _ = await press(102, f"ex|adm|stop|{rid}", 22)
    assert "⛔" in q.answers[-1]
    q, (t, kb) = await press(101, f"ex|adm|stop|{rid}", 12)
    assert (await B.ex_run_get(rid))["outcome"] == "stopped"
    print(plain(t))
    # соло кнопкой: уже был сегодня → отказ со звёздами
    q, (t, kb) = await press(101, "ex|route|reeds", 13)
    assert "ex|stars" in kb_data(kb), kb_data(kb)
    add_frog(104, "Тина", level=1)
    q, (t, kb) = await press(104, "ex|solo|reeds", 40)
    run = await B.ex_user_run(104)
    assert run and run["status"] == "active"
    print(plain(bot.msgs[(104, 40)][0]))
    # отмена сбора
    add_frog(105, "Осока", level=1)
    await press(105, "ex|make|reeds|10", 50)
    r5 = await B.ex_user_run(105)
    q, (t, kb) = await press(105, f"ex|cancel|{r5['id']}", 50)
    assert (await B.ex_run_get(r5["id"]))["status"] == "cancelled"
    print(plain(bot.msgs[(105, 50)][0]))
    # мусорные кнопки не роняют
    for d in ("ex|", "ex|v|x|y|z", "ex|join|abc", "ex|route|nope", "ex|make|reeds|7", "ex|p|1|steal"):
        await press(105, d, 51)
    print("роутер: ок")



if __name__ == "__main__":
    setup_db()
    bot = FakeBot()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(suite_engine())
    loop.run_until_complete(suite_router())
    print("ВСЁ ОК")
