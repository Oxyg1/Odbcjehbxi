"""
Проверка экспедиций на тестовой базе: соло, команда, голоса и ничья,
молчание, личные находки, возврат при пустом запасе, простой бота,
находки и облик за набор, сбор, экраны и все кнопки.

Запуск из корня репозитория:
    python3 tools/test_expeditions.py

Боевую базу не трогает: работает во временном каталоге. Часы подменены —
двухчасовая экспедиция проходит за секунды.
"""
import os, sys, asyncio, sqlite3, types, json, re, time as _time

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
        self.fail = {}         # uid -> исключение, которое бросать при отправке
        self.mid = 1000
        self.log = []          # (kind, chat, mid, text, kb)
        self.msgs = {}         # (chat, mid) -> (text, kb)
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if chat_id in self.fail:
            raise self.fail[chat_id]
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

async def settle():
    """Дождаться фоновых задач бота (журнал действий и т.п.): синхронная запись
    в базу из теста иначе упрётся в их незакоммиченную транзакцию."""
    for _ in range(3):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


async def add_frog(uid, name, level=5, coins=100):
    await settle()
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO frogs(user_id, frog_name, first_name, level, coins, alive, last_expedition) "
                "VALUES(?,?,?,?,?,1,0)", (uid, name, name, level, coins))
    con.commit(); con.close()

def q_(sql, *a):
    return q(sql, *a)


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
    assert set(B.EX_ROUTES) == {"reeds", "bog", "mill"}
    for route in B.EX_ROUTES.values():
        n = route["stops"]
        assert route["skin"] in B.SKINS and B.SKINS[route["skin"]].get("chance") == 0
        for c in route["cards"] + [route["finale"]]:
            head = f"{route['emoji']} {c['title']} · {n}/{n}"
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
    await add_frog(1, "Квака", level=1, coins=100)
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
    await B.ex_vote(bot, rid, 0, 1, risky)
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
        await add_frog(uid, name, level=3)
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
    # Личная находка Жабы — на третьей стоянке, чтобы сценарий был повторяемым
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_members SET pers_step=3 WHERE run_id=? AND user_id=2", (rid,))
    con.commit(); con.close()
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
    await add_frog(6, "Осока", level=1)
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
    await add_frog(7, "Ил", level=1)
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
    await add_frog(8, "Ряска2", level=1); await add_frog(9, "Тина2", level=1)
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
    await add_frog(10, "Лист", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(10), "reeds", 5)
    for uid in (11, 12, 13, 14):
        await add_frog(uid, f"Л{uid}", level=1)
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
    await add_frog(20, "Экран", level=1)
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
    await add_frog(101, "Квака", level=1); await add_frog(102, "Жаба", level=1); await add_frog(103, "Ряска", level=1)
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
    await add_frog(104, "Тина", level=1)
    q, (t, kb) = await press(104, "ex|solo|reeds", 40)
    run = await B.ex_user_run(104)
    assert run and run["status"] == "active"
    print(plain(bot.msgs[(104, 40)][0]))
    # отмена сбора
    await add_frog(105, "Осока", level=1)
    await press(105, "ex|make|reeds|10", 50)
    r5 = await B.ex_user_run(105)
    q, (t, kb) = await press(105, f"ex|cancel|{r5['id']}", 50)
    assert (await B.ex_run_get(r5["id"]))["status"] == "cancelled"
    print(plain(bot.msgs[(105, 50)][0]))
    # мусорные кнопки не роняют
    for d in ("ex|", "ex|v|x|y|z", "ex|join|abc", "ex|route|nope", "ex|make|reeds|7", "ex|p|1|steal"):
        await press(105, d, 51)
    print("роутер: ок")



# ══ Пограничные случаи и сбои ══
from telegram.error import Forbidden, RetryAfter

async def go_stop(rid, idx):
    """Довести экспедицию до открытой стоянки idx, двигая часы."""
    while True:
        run = await B.ex_run_get(rid)
        if run["status"] != "active" or (run["step"] == idx and run["resolved"] < idx):
            return run
        plan = json.loads(run["plan_json"])
        nxt = plan[min(run["step"] + 1, len(plan) - 1)]["at"]
        CLOCK.t = max(CLOCK.t + 1, nxt, run["closes_at"] if run["step"] > run["resolved"] else 0)
        await tick_job()


async def suite_edge():
    # E1. Вступление в ту же секунду, что и старт
    for order in (0, 1):
        a, b = 300 + order * 2, 301 + order * 2
        await add_frog(a, f"А{a}", level=1); await add_frog(b, f"Б{b}", level=1)
        rid, _ = await B.ex_lobby_create(await B.db_get(a), "reeds", 10)
        fb = await B.db_get(b)
        jobs = [B.ex_lobby_join(fb, rid), B.ex_start(bot, rid)]
        if order:
            jobs.reverse()
        await asyncio.gather(*jobs)
        members = [m["user_id"] for m in await B.ex_members_get(rid)]
        B._user_cache.invalidate(b)
        used = (await B.db_get(b))["last_expedition"] > 0
        assert (b in members) == used, (order, members, used)
        await B.ex_stop(bot, rid)
    print("E1 гонка старта и вступления: ок")

    # E2. Сбой выплаты одному не задевает других; падение посреди выплат — доплата
    await add_frog(310, "Пятак", level=1, coins=0); await add_frog(311, "Грош", level=1, coins=0)
    rid, _ = await B.ex_lobby_create(await B.db_get(310), "reeds", 5)
    await B.ex_lobby_join(await B.db_get(311), rid)
    await B.ex_start(bot, rid)
    real_levelup = B.levelup
    async def bad_levelup(f, bot=None):
        if f["user_id"] == 310:
            raise RuntimeError("levelup сломан")
        return await real_levelup(f, bot)
    B.levelup = bad_levelup
    await B.ex_stop(bot, rid)
    B.levelup = real_levelup
    paid = {m["user_id"]: (m["paid"], m["coins"]) for m in await B.ex_members_get(rid)}
    assert all(v[0] == 1 for v in paid.values()), paid
    assert await coins(310) == paid[310][1] and await coins(311) == paid[311][1], paid
    # «упал» сразу после смены статуса
    await add_frog(312, "Медяк", level=1, coins=0)
    rid, _ = await B.ex_lobby_create(await B.db_get(312), "reeds", 0)
    await B.ex_start(bot, rid)
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_runs SET status='finished', outcome='stopped', finished_at=?, loot=30 WHERE id=?",
                (CLOCK.t, rid))
    con.commit(); con.close()
    await tick_job()
    m = (await B.ex_members_get(rid))[0]
    assert m["paid"] == 1 and await coins(312) == m["coins"] > 0, (m, await coins(312))
    before = await coins(312)
    await tick_job()
    assert await coins(312) == before
    assert "итог" in plain(bot.last_to(312, "send")[3])
    print("E2 выплаты: ок, доплата после падения", m["coins"])

    # E3. Стоянку убрали из маршрута посреди экспедиции
    await add_frog(320, "Правка", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(320), "reeds", 0)
    await B.ex_start(bot, rid)
    run = await B.ex_run_get(rid)
    plan = json.loads(run["plan_json"])
    gone = plan[1]["card"]
    saved = list(R["cards"])
    R["cards"][:] = [c for c in saved if c["key"] != gone]
    run = await go_stop(rid, 1)
    stop = bot.last_to(320, "send")
    assert "Стоянка" in plain(stop[3]) and kb_data(stop[4]) == [f"ex|v|{rid}|1|_"], kb_data(stop[4])
    await B.ex_vote(bot, rid, 1, 320, "_")
    # и вариант, за который голосовали на стоянке 0, тоже пропал
    con = sqlite3.connect(DB)
    log = json.loads(con.execute("SELECT log_json FROM ex_runs WHERE id=?", (rid,)).fetchone()[0])
    log[0]["opt"] = "нет_такого"; log[0]["o"] = 7
    con.execute("UPDATE ex_runs SET log_json=? WHERE id=?", (json.dumps(log), rid))
    con.commit(); con.close()
    await B.ex_stop(bot, rid)
    R["cards"][:] = saved
    assert "итог" in plain(bot.last_to(320, "send")[3])
    print("E3 правка маршрута на ходу: ок")

    # E4. Участник заблокировал бота — его не ждём
    await add_frog(330, "Есть", level=1); await add_frog(331, "Нет", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(330), "reeds", 5)
    await B.ex_lobby_join(await B.db_get(331), rid)
    bot.fail[331] = Forbidden("bot was blocked by the user")
    await B.ex_start(bot, rid)
    run = await B.ex_run_get(rid)
    card = B._ex_card("reeds", json.loads(run["plan_json"])[0]["card"])
    await B.ex_vote(bot, rid, 0, 330, card["options"][0]["key"])
    assert (await B.ex_run_get(rid))["resolved"] == 0
    del bot.fail[331]
    await B.ex_stop(bot, rid)
    print("E4 недоступный участник: ок")

    # E5. Личная находка держит стоянку открытой, пока на неё не ответили
    await add_frog(340, "Лич", level=1); await add_frog(341, "Ная", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(340), "reeds", 5)
    await B.ex_lobby_join(await B.db_get(341), rid)
    await B.ex_start(bot, rid)
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_members SET pers_step=1 WHERE run_id=? AND user_id=340", (rid,))
    con.execute("UPDATE ex_members SET pers_step=2 WHERE run_id=? AND user_id=341", (rid,))
    con.commit(); con.close()
    # E6. Раньше своей стоянки не выбрать
    assert "впереди" in await B.ex_personal_choose(bot, rid, 341, "keep")
    run = await go_stop(rid, 1)
    card = B._ex_card("reeds", json.loads(run["plan_json"])[1]["card"])
    k = card["options"][0]["key"]
    await B.ex_vote(bot, rid, 1, 340, k); await B.ex_vote(bot, rid, 1, 341, k)
    assert (await B.ex_run_get(rid))["resolved"] == 0, "закрылась, не дождавшись личной находки"
    assert await B.ex_personal_choose(bot, rid, 340, "keep") == "Себе"
    assert (await B.ex_run_get(rid))["resolved"] == 1
    print("E5–E6 личная находка: ок")

    # E7. «К стоянке» снимает кнопки со старого сообщения
    run = await go_stop(rid, 2)
    old = next(m["msg_id"] for m in await B.ex_members_get(rid) if m["user_id"] == 340)
    q = types.SimpleNamespace(from_user=types.SimpleNamespace(id=340), data=f"ex|here|{rid}",
                              message=types.SimpleNamespace(message_id=1), answers=[])
    async def ans(*a, **k): pass
    q.answer = ans
    f340 = await B.db_get(340)
    async def guard(update, ctx): return (q, 340, q.data, f340)
    B.cb_guard = guard
    await B.ex_router(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=bot))
    assert bot.msgs[(340, old)][1] is None, "старые кнопки остались"
    print("E7 «К стоянке»: ок")

    # E8. Telegram ответил «слишком часто» одному — остальным всё дошло
    bot.fail[341] = RetryAfter(30)
    run = await go_stop(rid, 3)
    assert bot.last_to(340, "send")[3] and "4/6" in plain(bot.last_to(340, "send")[3])
    del bot.fail[341]
    # недоставленному ответить не на что — стоянку закрывает голос второго
    await B.ex_vote(bot, rid, 3, 340, B._ex_card("reeds", json.loads(run["plan_json"])[3]["card"])["options"][0]["key"])
    assert (await B.ex_run_get(rid))["resolved"] == 3
    # E14. Переголосование туда-сюда: пока второй не ответил, стоянка открыта
    run = await go_stop(rid, 4)
    card = B._ex_card("reeds", json.loads(run["plan_json"])[4]["card"])
    keys = [o["key"] for o in card["options"]]
    for i in range(7):
        await B.ex_vote(bot, rid, 4, 340, keys[i % len(keys)])
    assert (await B.ex_run_get(rid))["resolved"] == 3
    await B.ex_stop(bot, rid)
    print("E8 сбой отправки, E14 переголосование: ок")

    # E9. Запас кончился на предпоследней — домой; на финале в ноль — всё равно дошли
    await add_frog(350, "Ноль", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(350), "reeds", 0)
    await B.ex_start(bot, rid)
    run = await go_stop(rid, N - 2)
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_runs SET supply=1, loot=40 WHERE id=?", (rid,)); con.commit(); con.close()
    card = B._ex_card("reeds", json.loads(run["plan_json"])[N - 2]["card"])
    worst = min(card["options"], key=lambda o: o["outcomes"][-1].get("supply", 0))
    if worst["outcomes"][-1].get("supply", 0) < 0:
        real_roll = B._ex_roll
        B._ex_roll = lambda opt: len(opt["outcomes"]) - 1
        await B.ex_vote(bot, rid, N - 2, 350, worst["key"])
        B._ex_roll = real_roll
        run = await B.ex_run_get(rid)
        assert run["outcome"] == "turned_back" and len(json.loads(run["log_json"])) == N - 1, run
        m = (await B.ex_members_get(rid))[0]
        assert m["coins"] == 20, m          # 40 пополам, без бонуса запаса
    else:
        await B.ex_stop(bot, rid)
    await add_frog(351, "Финал", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(351), "reeds", 0)
    await B.ex_start(bot, rid)
    run = await go_stop(rid, N - 1)
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_runs SET supply=1 WHERE id=?", (rid,)); con.commit(); con.close()
    real_roll = B._ex_roll
    B._ex_roll = lambda opt: len(opt["outcomes"]) - 1
    await B.ex_vote(bot, rid, N - 1, 351, R["finale"]["options"][-1]["key"])
    B._ex_roll = real_roll
    run = await B.ex_run_get(rid)
    assert run["outcome"] == "done" and run["supply"] == 0, run
    print("E9 запас в ноль: ок")

    # E10. Сбор истёк, никто не пришёл — выход в одиночку
    await add_frog(360, "Один", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(360), "reeds", 5)
    CLOCK.t += 5 * 60 + 1
    await tick_job()
    run = await B.ex_run_get(rid)
    assert run["status"] == "active" and run["step"] == 0
    await B.ex_stop(bot, rid)
    print("E10 пустой сбор: ок")

    # E11. Сборы маршрутов не своего уровня в меню не видны
    await add_frog(370, "Старший", level=20); await add_frog(371, "Младший", level=1)
    R["level"] = 10
    rid, _ = await B.ex_lobby_create(await B.db_get(370), "reeds", 10)
    _, kb = await B.ex_menu_view(await B.db_get(371))
    assert f"ex|join|{rid}" not in kb_data(kb)
    _, kb = await B.ex_menu_view(await B.db_get(372 - 2))  # сам создатель свой сбор не видит
    R["level"] = 1
    _, kb = await B.ex_menu_view(await B.db_get(371))
    assert f"ex|join|{rid}" in kb_data(kb)
    await B.ex_lobby_cancel(bot, rid)
    print("E11 сборы по уровню: ок")

    # E12. Экспедицию ничто не двигало 6 часов — завершается с выплатой
    await add_frog(380, "Сон", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(380), "reeds", 0)
    await B.ex_start(bot, rid)
    CLOCK.t += 6 * 3600
    await tick_job()
    run = await B.ex_run_get(rid)
    assert run["status"] == "finished" and run["outcome"] == "stopped", run
    # E13. Остановка админом при открытой стоянке снимает кнопки
    open_msg = bot.sends_to(380)[0]
    assert bot.msgs[(380, open_msg[2])][1] is None
    print("E12 зависшая, E13 остановка: ок")

    # E15. Сутки — по UTC
    await add_frog(390, "Полночь", level=1)
    f = await B.db_get(390)
    mid = CLOCK.t - CLOCK.t % 86400
    f["last_expedition"] = mid - 60
    assert not B.ex_today_used(f)
    f["last_expedition"] = mid + 60
    assert B.ex_today_used(f)
    print("E15 сутки: ок")

    # E16. Проверка данных: сломанный маршрут не прячет ошибки соседнего
    B.EX_ROUTES["broken"] = {"name": "x"}
    B.EX_ROUTES["bad2"] = dict(R, cards=[dict(R["cards"][0], text="a < b")], stops=2)
    errs = B.ex_validate_content()
    del B.EX_ROUTES["broken"], B.EX_ROUTES["bad2"]
    assert any(e.startswith("broken:") for e in errs) and any("bad2" in e and "<" in e for e in errs) \
        and any("bad2" in e and "трёх" in e for e in errs), errs
    assert not B.ex_validate_content()
    print("E16 проверка данных: ок")

    # E17. В поход нельзя, пока лягушка в экспедиции
    await add_frog(400, "Занята", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(400), "reeds", 10)
    replies = []
    class M:
        text = "/pohod @x"
        async def reply_text(self, t, **k): replies.append(t)
    upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=400), message=M())
    await B.cmd_pohod(upd, types.SimpleNamespace(args=["@x"], bot=bot))
    assert "экспедиции" in replies[-1], replies
    # E18. /m — команде, без разметки
    await add_frog(401, "Слушает", level=1)
    await B.ex_lobby_join(await B.db_get(401), rid)
    M.text = "/m привет <b>жирный"
    await B.cmd_m_new(upd, types.SimpleNamespace(args=["привет"], bot=bot))
    got = bot.last_to(401, "send")[3]
    assert "&lt;b&gt;" in got and "Занята" in got, got
    assert "Доставлено: 1 из 1" in replies[-1], replies
    await B.ex_lobby_cancel(bot, rid)
    print("E17 поход занят, E18 /m: ок")

    # E19. Бот «упал» посреди рассылки стоянки: недоставленным старое сообщение
    # не переписывается, и их не ждут
    await add_frog(430, "Дошло", level=1); await add_frog(431, "НеДошло", level=1)
    rid, _ = await B.ex_lobby_create(await B.db_get(430), "reeds", 5)
    await B.ex_lobby_join(await B.db_get(431), rid)
    await B.ex_start(bot, rid)
    con = sqlite3.connect(DB)   # личные находки здесь ни при чём
    con.execute("UPDATE ex_members SET pers_key='' WHERE run_id=?", (rid,))
    con.commit(); con.close()
    prev = next(m["msg_id"] for m in await B.ex_members_get(rid) if m["user_id"] == 431)
    bot.fail[431] = RuntimeError("процесс остановлен посреди рассылки")
    try:
        await go_stop(rid, 1)
    except RuntimeError:
        pass
    del bot.fail[431]
    run = await B.ex_run_get(rid)
    assert run["step"] == 1, run
    card = B._ex_card("reeds", json.loads(run["plan_json"])[1]["card"])
    await B.ex_vote(bot, rid, 1, 430, card["options"][0]["key"])
    assert (await B.ex_run_get(rid))["resolved"] == 1
    old_text = plain(bot.msgs[(431, prev)][0])
    assert "1/6" in old_text and "2/6" not in old_text, "в сообщение прошлой стоянки вписана новая"
    # E20. Остановка при открытой личной находке снимает и её кнопки
    con = sqlite3.connect(DB)
    con.execute("UPDATE ex_members SET pers_step=2, pers_key='coin' WHERE run_id=? AND user_id=430", (rid,))
    con.commit(); con.close()
    await go_stop(rid, 2)
    pm = next(m["pers_msg_id"] for m in await B.ex_members_get(rid) if m["user_id"] == 430)
    assert pm and kb_data(bot.msgs[(430, pm)][1])
    await B.ex_stop(bot, rid)
    assert bot.msgs[(430, pm)][1] is None
    print("E19 обрыв рассылки, E20 остановка с находкой: ок")

    # E21. Команда в группе — кнопка в личку; /start exp до переключения — только админам
    await add_frog(440, "Группа", level=1)
    replies = []
    class GM:
        async def reply_text(self, t, reply_markup=None, **k): replies.append((t, reply_markup))
    grp = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=440), message=GM(),
                                effective_chat=types.SimpleNamespace(type="supergroup"))
    await B.cmd_ex(grp, types.SimpleNamespace(bot=bot, args=[]))
    t, kb = replies[-1]
    assert "личке" in t and kb.inline_keyboard[0][0].url.endswith("start=exp"), replies
    dm = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=440), message=GM(),
                               effective_chat=types.SimpleNamespace(type="private"))
    B.EX_LIVE = False
    assert await B.ex_start_deeplink(dm, types.SimpleNamespace(bot=bot), "exp") is False
    B.EX_LIVE = True
    assert await B.ex_start_deeplink(dm, types.SimpleNamespace(bot=bot), "exp") is True
    assert "Экспедиции" in plain(replies[-1][0])
    # ссылки из анонсов старых экспедиций ведут в раздел
    assert await B.ex_start_deeplink(dm, types.SimpleNamespace(bot=bot), "exp_join_17") is True
    print("E21 группа и ссылка: ок")


# ══ Переключение со старых экспедиций ══

async def suite_switch():
    # E22. Кнопка «Экспедиция» на площади ведёт в новые экспедиции,
    # E25. кнопки старых экспедиций из истории — внятный ответ
    await add_frog(500, "Площадь", level=1)
    for d, expect in (("plaza_expedition", "Экспедиции"), ("exp_vote_3_1_a", None)):
        answers = []
        class PM:
            message_id = 77
            chat = types.SimpleNamespace(id=500, type="private")
            async def edit_text(self, text, parse_mode=None, reply_markup=None, **k):
                bot.msgs[(500, 77)] = (text, reply_markup)
        q = types.SimpleNamespace(from_user=types.SimpleNamespace(id=500, username="", first_name="Площадь"),
                                  data=d, message=PM())
        async def ans(text=None, show_alert=False, **k): answers.append(text)
        q.answer = ans
        f500 = await B.db_get(500)
        async def guard(update, ctx): return (q, 500, d, f500)
        B.cb_guard = guard
        await B.on_callback(types.SimpleNamespace(callback_query=q, effective_user=q.from_user,
                                                  effective_chat=PM.chat),
                            types.SimpleNamespace(bot=bot, bot_data={}, user_data={}))
        if expect:
            assert expect in plain(bot.msgs[(500, 77)][0]), bot.msgs.get((500, 77))
        else:
            assert answers and "обновились" in (answers[-1] or ""), answers
    print("E22 площадь, E25 старые кнопки: ок")

    # E23. Разовый перенос: шедшие старые экспедиции и припасы
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS expeditions (id INTEGER PRIMARY KEY, biome TEXT, status TEXT,
            creator_id INTEGER, started_at REAL DEFAULT 0, finished_at REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS expedition_members (expedition_id INTEGER, user_id INTEGER,
            coins_taken INTEGER DEFAULT 0, supplies_json TEXT DEFAULT '{}', status TEXT DEFAULT 'active');
    """)
    for uid, name in ((510, "Создатель"), (511, "Вступил"), (512, "Ушёл"), (513, "Запасливая"),
                      (514, "Выжила"), (515, "Погибла"), (516, "Давно")):
        con.close(); await add_frog(uid, name, level=1, coins=0); con = sqlite3.connect(DB)
    con.execute("INSERT INTO expeditions VALUES (1, 'swamp', 'active', 510, 0, 0)")
    con.execute("INSERT INTO expedition_members VALUES (1, 510, 100, '{\"food\": 2}', 'active')")
    con.execute("INSERT INTO expedition_members VALUES (1, 511, 50, '{\"potion\": 1, \"torch\": 2}', 'dead')")
    con.execute("INSERT INTO expedition_members VALUES (1, 512, 70, '{}', 'left')")
    con.execute("UPDATE frogs SET adventure_locked_until=? WHERE user_id IN (510, 511)", (CLOCK.t + 3600,))
    con.execute("UPDATE frogs SET inventory=? WHERE user_id=513",
                (json.dumps({"food": 3, "amulet": 1, "чужое": 5}),))
    # для E24: старые завершённые, ставки выживших не вернулись
    con.execute("INSERT INTO expeditions VALUES (2, 'forest', 'finished', 514, ?, ?)", (CLOCK.t - 100, CLOCK.t - 50))
    con.execute("INSERT INTO expedition_members VALUES (2, 514, 200, '{}', 'active')")
    con.execute("INSERT INTO expedition_members VALUES (2, 515, 300, '{}', 'dead')")
    con.execute("INSERT INTO expeditions VALUES (3, 'forest', 'finished', 516, 10, 20)")
    con.execute("INSERT INTO expedition_members VALUES (3, 516, 400, '{}', 'active')")
    con.commit(); con.close()
    for uid in range(510, 517):
        B._user_cache.invalidate(uid)
    await B.ex_migrate_old(bot)
    assert await coins(510) == 100                       # создателю — только монеты
    assert await coins(511) == 50 + 60 + 2 * 50          # вступившему — и припасы
    assert await coins(512) == 0                         # ушедшему уже вернули
    assert await coins(513) == 3 * 30 + 100              # припасы из инвентаря
    inv = json.loads((await B.db_get(513))["inventory"])
    assert inv == {"чужое": 5}, inv
    assert (await B.db_get(510))["adventure_locked_until"] == 0
    assert q_("SELECT status FROM expeditions WHERE id=1")[0][0] == "cancelled"
    assert "обновились" in plain(bot.last_to(511, "send")[3])
    before = await coins(510)
    await B.ex_migrate_old(bot)                          # второй раз — ничего
    assert await coins(510) == before
    print("E23 перенос: ок")

    # E24. Возврат ставок выживших: за сезон или за всё время, один раз
    await B.db_setting("season_started_at", str(CLOCK.t - 1000))
    season = await B.ex_lost_stakes(await B.season_started_at())
    total = await B.ex_lost_stakes(0)
    assert season == {514: 200} and total == {514: 200, 516: 400}, (season, total)
    text, kb = await B.ex_refund_view()
    assert kb_data(kb)[:2] == ["ex|adm|refund|1", "ex|adm|refund|0"], kb_data(kb)
    print(plain(text))
    assert "Вернули 200" in await B.ex_refund_do(bot, season_only=True)
    assert await coins(514) == 200 and await coins(516) == 0 and await coins(515) == 0
    assert "уже" in await B.ex_refund_do(bot, season_only=False)
    assert await coins(516) == 0
    text, _ = await B.ex_admin_view()
    assert "Старые ставки" not in plain(text)
    print("E24 возврат ставок: ок")

    # E26. Топь и мельница целиком: своё число стоянок и свой запас
    for rk, lvl in (("bog", 5), ("mill", 10)):
        route = B.EX_ROUTES[rk]
        uid = 600 + lvl
        await add_frog(uid, f"Тест{rk}", level=lvl)
        assert "уровня" in await B.ex_cant_go(await B.db_get(uid) | {"level": lvl - 1}, rk)
        rid, why = await B.ex_lobby_create(await B.db_get(uid), rk, 0)
        assert rid, why
        await B.ex_start(bot, rid)
        run = await B.ex_run_get(rid)
        assert run["supply"] == route["supply"] and len(json.loads(run["plan_json"])) == route["stops"]
        assert f"{route['supply']}/{route['supply']}" in plain(bot.last_to(uid, "send")[3])
        for _ in range(route["stops"] + 2):
            run = await B.ex_run_get(rid)
            if run["status"] != "active":
                break
            CLOCK.t = max(CLOCK.t, run["closes_at"]) + 1
            await tick_job()
        run = await B.ex_run_get(rid)
        assert run["status"] == "finished" and run["outcome"] == "done", run
        final = plain(bot.last_to(uid, "send")[3])
        assert route["name"] in final and "итог" in final
        m = (await B.ex_members_get(rid))[0]
        assert m["xp"] == route["xp"]
    print("E26 топь и мельница: ок")


if __name__ == "__main__":
    setup_db()
    bot = FakeBot()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(suite_engine())
    loop.run_until_complete(suite_router())
    loop.run_until_complete(suite_edge())
    loop.run_until_complete(suite_switch())
    loop.run_until_complete(settle())   # журнал действий пишется фоновыми задачами
    print("ВСЁ ОК")
