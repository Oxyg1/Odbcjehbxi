"""
Площадь: главный экран, соседи, карточка, забота в одно нажатие, Связь
с подтверждением разрыва, поход и рыбалка через общий выбор соседа.

Запуск из корня репозитория:
    python3 tools/test_plaza.py
    SHOW=1 python3 tools/test_plaza.py   # ещё и напечатать экраны

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="plaza_test_"), "test.db")
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

    A, F1, F2, F3, S = 501, 502, 503, 504, 505
    await make_frog(A)
    await make_frog(F1, hunger=40, cleanliness=30, energy=30)
    await make_frog(F2, hunger=95, cleanliness=95, energy=95, last_seen=_time.time() - 5 * 86400)
    await make_frog(F3, hunger=50)
    await make_frog(S)
    befriend(A, F1, level=0)
    befriend(A, F2, level=1, xp=5)
    x_db("INSERT INTO friendships(user_id,friend_id,level,xp,created_at,pending) VALUES(?,?,0,0,?,1)",
         F3, A, _time.time())

    print("1. Главный экран: только то, что требует внимания")
    q, m = await press(A, "plaza")
    text, kb = m.last
    t = plain(text)
    ok("1 заявка в соседи" in t, f"видна заявка: {t!r}")
    ok("Можно позаботиться о 2 соседях" in t, f"видно, о ком позаботиться: {t!r}")
    ok("Болото сейчас" not in t, "ленты летописи на главном больше нет")
    ok("plaza_care_all" in cbs(kb), "кнопка «Позаботиться обо всех»")
    for cb in ("plaza_sosedi", "plaza_staya", "plaza_pohod", "plaza_fish_invite", "plaza_bond",
               "plaza_expedition", "letopis_view", "refresh"):
        ok(cb in cbs(kb), f"на главном есть {cb}")

    print("2. Список соседей: сначала те, кому нужна забота")
    q, m = await press(A, "plaza_sosedi")
    text, kb = m.last
    friend_btns = [l for l, c in zip(labels(kb), cbs(kb)) if c.startswith("plaza_friend_")]
    ok(len(friend_btns) == 2, f"двое соседей: {friend_btns}")
    ok("plaza_requests" in cbs(kb), "кнопка заявок")
    ok(friend_btns and "🟢" in friend_btns[0], f"заходивший сегодня помечен: {friend_btns}")
    ok(friend_btns and "🟢" not in friend_btns[-1], "давно не заходивший — без отметки")

    print("3. Карточка соседа: доступные действия кнопками, остальное — строкой «Позже»")
    q, m = await press(A, f"plaza_friend_{F1}")
    text, kb = m.last
    c = cbs(kb)
    ok(f"social_all_{F1}" in c, "кнопка «Всё сразу»")
    ok(f"social_treat_{F1}" in c and f"social_wash_{F1}" in c and f"social_lullaby_{F1}" in c,
       f"голодной, грязной, уставшей — угостить, помыть, убаюкать: {c}")
    ok(f"plaza_invite_adv_{F1}" not in c, "«Знакомым» поход ещё закрыт")
    ok("Приятелями" in plain(text), "подсказка, что откроет дружба")

    print("4. Одно действие — карточка перерисована той же функцией")
    q, m = await press(A, f"social_hug_{F1}")
    ok(q.answers and q.answers[0][0] and not q.answers[0][1], f"короткое уведомление без окна: {q.answers}")
    text, kb = m.last
    ok(f"social_hug_{F1}" not in cbs(kb), "«Обнять» ушло в откат")
    ok("обнять — через" in plain(text), f"откат виден текстом: {plain(text)!r}")
    ok(any(cid == F1 for cid, *_ in BOT.sent), "соседу пришло сообщение")
    q, m = await press(A, f"social_hug_{F1}")
    ok(q.answers and q.answers[0][1] and "через" in (q.answers[0][0] or ""), f"повтор — объяснение: {q.answers}")

    print("5. «Всё сразу» и рост дружбы")
    sent_before = len(BOT.sent)
    q, m = await press(A, f"social_all_{F1}")
    fr = q_db("SELECT level, xp, last_treat, last_wash, last_lullaby FROM friendships WHERE user_id=? AND friend_id=?", A, F1)[0]
    ok(all(fr[2:]), f"все откаты проставлены: {fr}")
    ok(fr[0] >= 1, f"дружба выросла до «Приятелей»: {fr}")
    ok(q.answers and "Приятели" in (q.answers[0][0] or ""), f"о росте дружбы сказано: {q.answers}")
    ok(len(BOT.sent) == sent_before, "второе сообщение соседу в течение 30 минут не шлём")
    f1 = await B.db_get(F1)
    ok(f1["hunger"] >= 60 and f1["cleanliness"] >= 50, f"параметры соседа выросли: {f1['hunger']}, {f1['cleanliness']}")
    text, kb = m.last
    ok(f"plaza_invite_adv_{F1}" in cbs(kb), "у «Приятелей» появился поход")

    print("6. Сытого не угощаем, чистого не моем")
    st = B.social_state({}, {"alive": 1, "hunger": 95, "cleanliness": 95, "energy": 95}, _time.time())
    ok(st["treat"] is None and st["wash"] is None and st["lullaby"] is None, f"не нужно: {st}")
    ok(st["hug"] == 0, "обнять можно всегда")

    print("7. Позаботиться обо всех с главного")
    q, m = await press(A, "plaza_care_all")
    ok(q.answers and "соседе" in (q.answers[0][0] or ""), f"итог: {q.answers}")
    fr2 = q_db("SELECT last_hug FROM friendships WHERE user_id=? AND friend_id=?", A, F2)[0][0]
    ok(fr2 > 0, "второго соседа тоже обняли")
    text, kb = m.last
    ok("plaza_care_all" not in cbs(kb), "после — кнопка пропала")

    print("8. Поход и рыбалка: общий выбор соседа")
    q, m = await press(A, "plaza_pohod")
    ok(f"plaza_invite_adv_{F1}" in cbs(m.last[1]) and f"plaza_invite_adv_{F2}" in cbs(m.last[1]),
       f"в поход зовём «Приятелей»: {cbs(m.last[1])}")
    q, m = await press(A, "plaza_fish_invite")
    ok("35%" in plain(m.last[0]) and f"plaza_invite_fish_{F1}" in cbs(m.last[1]), "рыбалка: шансы и выбор")
    x_db("UPDATE frogs SET last_fish=? WHERE user_id=?", _time.time(), A)
    B._user_cache.clear()
    q, m = await press(A, "plaza_fish_invite")
    ok(q.answers and q.answers[0][1] and "Снова" in (q.answers[0][0] or ""), f"откат рыбалки виден: {q.answers}")

    print("9. Связь: предложение и разрыв только с подтверждением")
    x_db("UPDATE friendships SET level=2, xp=25 WHERE user_id=? AND friend_id=?", A, F1)
    q, m = await press(A, "plaza_bond")
    ok(f"plaza_bond_invite_{F1}" in cbs(m.last[1]), "Друзьям можно предложить Связь")
    ok("ежедневный бонус" in plain(m.last[0]), "правило серии описано как есть")
    q, m = await press(A, f"plaza_bond_invite_{F1}")
    ok("отправлено" in plain(m.last[0]), "отправителю видно, что предложение ушло")
    q, m = await press(F1, f"bond_accept_{A}")
    ok(q_db("SELECT COUNT(*) FROM user_bonds WHERE user_id=? AND partner_id=?", A, F1)[0][0] == 1, "Связь создана")
    q, m = await press(A, "plaza_bond")
    ok(f"plaza_bond_view_{F1}" in cbs(m.last[1]), "Связь в списке")
    ok(not any(c.startswith("plaza_bond_break_") for c in cbs(m.last[1])), "в списке нет «разорвать» одним нажатием")
    q, m = await press(A, f"plaza_bond_break_{F1}")
    ok(q_db("SELECT COUNT(*) FROM user_bonds WHERE user_id=? AND partner_id=?", A, F1)[0][0] == 1,
       "первое нажатие — только вопрос")
    ok(f"plaza_bondbreak_ok_{F1}" in cbs(m.last[1]), "кнопка подтверждения")
    q, m = await press(A, f"plaza_bondbreak_ok_{F1}")
    ok(q_db("SELECT COUNT(*) FROM user_bonds WHERE user_id=? AND partner_id=?", A, F1)[0][0] == 0, "разорвано")

    print("10. Чужая карточка: добавить, встречная заявка, принять")
    q, m = await press(A, f"plaza_friend_{S}")
    ok(f"plaza_add_{S}" in cbs(m.last[1]), "у чужого — «В соседи»")
    ok(not any(c.startswith("social_") for c in cbs(m.last[1])), "у чужого нет кнопок заботы")
    q, m = await press(A, f"plaza_add_{S}")
    ok("noop" in cbs(m.last[1]) and "Заявка отправлена" in " ".join(labels(m.last[1])), "после заявки карточка обновилась")
    q, m = await press(A, f"plaza_friend_{F3}")
    ok(f"friend_accept_{F3}" in cbs(m.last[1]), "встречная заявка — кнопка «Принять»")
    q, m = await press(A, f"friend_accept_{F3}")
    ok(q_db("SELECT pending FROM friendships WHERE user_id=? AND friend_id=?", F3, A)[0][0] == 0, "принято")
    ok(f"plaza_friend_{F3}" in cbs(m.last[1]), "после принятия — кнопка на карточку")
    q, m = await press(S, "friend_accept_999999")
    ok(q.answers and q.answers[0][1], "чужая/отозванная заявка не создаёт дружбу")
    ok(not q_db("SELECT 1 FROM friendships WHERE user_id=? AND friend_id=999999", S), "односторонней дружбы нет")

    print("11. Пустая площадь у новичка")
    N = 506
    await make_frog(N)
    q, m = await press(N, "plaza")
    ok("Добавь соседей" in plain(m.last[0]), "новичку объясняем, зачем соседи")
    q, m = await press(N, "plaza_sosedi")
    ok("plaza_find" in cbs(m.last[1]), "пустой список — сразу «Найти игрока»")
    q, m = await press(N, "plaza_pohod")
    ok("Приятели" in plain(m.last[0]), "некого позвать — сказано почему")

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
