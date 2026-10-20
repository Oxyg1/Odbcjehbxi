"""
Обновление «по статистике»: переедание, экран смерти и бесплатное
возвращение, Кувшинки, Кваквордл, приглашение из групп, статистика, чистка
журналов, фильтр шума миграций.

Запуск из корня репозитория:
    python3 tools/test_update.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time, random
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="upd_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop

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

def urls(kb):
    return [b.url for row in kb.inline_keyboard for b in row if b.url] if kb else []


class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.mid = 100
        self.sent = []
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.mid += 1
        self.sent.append((chat_id, text, reply_markup))
        return Sent(self.mid)
    async def delete_message(self, *a, **kw):
        return True
    async def send_sticker(self, *a, **kw):
        return Sent(1)
    async def send_animation(self, *a, **kw):
        return Sent(1)
    def __getattr__(self, name):          # прочие методы бота — тихие заглушки
        async def _noop(*a, **kw):
            return Sent(1)
        return _noop


class Msg:
    def __init__(self, chat=1, kind="private", text=None, mid=1):
        self.chat = types.SimpleNamespace(id=chat, type=kind)
        self.message_id = mid
        self.text = text
        self.screens = []
        self.replies = []
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
    async def delete(self):
        return True
    @property
    def last(self):
        allm = self.screens + self.replies
        return allm[-1] if allm else ("", None)


class Q:
    def __init__(self, uid, data, msg, first_name="Тест"):
        self.from_user = types.SimpleNamespace(id=uid, first_name=first_name, username="", is_bot=False)
        self.data, self.message, self.answers = data, msg, []
    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append((text, show_alert))
    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kw):
        return await self.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)


BOT = FakeBot()

def ctx_for(uid):
    if not hasattr(ctx_for, "store"):
        ctx_for.store = {}
    ud = ctx_for.store.setdefault(uid, {})
    return types.SimpleNamespace(bot=BOT, user_data=ud, bot_data=ctx_for.__dict__.setdefault("bd", {}),
                                 args=[], application=None)

async def press(uid, data, msg=None, router=None):
    msg = msg or Msg(chat=uid)
    q = Q(uid, data, msg)
    upd = types.SimpleNamespace(callback_query=q, effective_user=q.from_user,
                                effective_chat=msg.chat, message=None)
    r = router or (B.lily_router if data.startswith("lily|") else
                   B.kw_router if data.startswith("kw|") else B.on_callback)
    # Отдельная задача на нажатие — как в боте: лок игрока снимается по её завершении
    await asyncio.create_task(r(upd, ctx_for(uid)))
    await asyncio.sleep(0.05)
    return q, msg

async def say(uid, text):
    """Сообщение игрока в личку: сначала обработчик Кваквордла, как в боте."""
    m = Msg(chat=uid, text=text)
    upd = types.SimpleNamespace(message=m, effective_user=types.SimpleNamespace(id=uid, first_name="Т"),
                                effective_chat=m.chat)
    stopped = False
    try:
        await asyncio.create_task(B.kw_input(upd, ctx_for(uid)))
    except ApplicationHandlerStop:
        stopped = True
    await asyncio.sleep(0.05)
    return m, stopped


def q_db(sql, *a):
    con = sqlite3.connect(DB, timeout=30)
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()

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
    cols = ",".join(f"{k}=?" for k in sets)
    x_db(f"UPDATE frogs SET {cols} WHERE user_id=?", *sets.values(), uid)
    B._user_cache.clear() if hasattr(B._user_cache, "clear") else None
    return await B.db_get(uid)


async def fresh(uid):
    if hasattr(B._user_cache, "clear"):
        B._user_cache.clear()
    return await B.db_get(uid)


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)

    # ─────────────────────────────────────────────────────────────────────
    print("1. Переедание: считается только лишнее, и оно переваривается")
    f = {"hunger": 40, "overfeed_total": 0, "alive": 1}
    ok(B.overfeed_add(f, 30) == 0 and f["overfeed_total"] == 0, "голодная — лишнего нет")
    f["hunger"] = 90
    ok(B.overfeed_add(f, 30) == 20 and f["overfeed_total"] == 20, "90+30 — лишних 20")
    # Старое правило убивало после 2500 единиц любой еды: 200 мух голодной лягушке
    f = {"hunger": 0, "overfeed_total": 0, "alive": 1, "user_id": 0}
    for _ in range(200):
        B.overfeed_add(f, 15)
        f["hunger"] = min(100, f["hunger"] + 15)
        f["hunger"] = max(0, f["hunger"] - 15)       # между кормлениями проголодалась
    ok(not B.check_overfeed(f) and f["alive"] == 1, "200 кормлений голодной лягушки — жива")
    f = {"hunger": 100, "overfeed_total": 0, "alive": 1, "user_id": 0}
    ok(B.overfeed_note(f) == "", "без лишнего — без предупреждения")
    B.overfeed_add(f, 160)
    note = B.overfeed_note(f)
    check_html(note)
    ok("Живот полный" in note, "после 160 лишних — предупреждение")
    B.overfeed_add(f, 150)
    ok(B.check_overfeed(f) and f["alive"] == 0 and f["death_reason"] == "overfeed" and f["died_at"] > 0,
       "310 лишних — лопнула, время смерти записано")

    fr = await make_frog(501, hunger=100, overfeed_total=200, last_decay=_time.time() - 4 * 3600)
    fr = B.decay(fr)
    ok(fr["overfeed_total"] == 100, f"за 4 ч переварено 100, осталось {fr['overfeed_total']}")
    fr["last_decay"] = _time.time() - 60
    before = fr["overfeed_total"]
    fr = B.decay(fr)
    fr["last_decay"] = _time.time() - 60
    fr = B.decay(fr)
    ok(fr["overfeed_total"] <= before, "частые вызовы не теряют переваривание")

    print("2. Старые счётчики обнуляются один раз")
    x_db("DELETE FROM settings WHERE key='overfeed_v2'")
    x_db("UPDATE frogs SET overfeed_total=2400 WHERE user_id=501")
    B.run_sync_migration()
    ok(q_db("SELECT overfeed_total FROM frogs WHERE user_id=501") == [(0,)], "обнулено")
    x_db("UPDATE frogs SET overfeed_total=120 WHERE user_id=501")
    B.run_sync_migration()
    ok(q_db("SELECT overfeed_total FROM frogs WHERE user_id=501") == [(120,)], "повторно не трогает")

    print("3. «Скормить всё» останавливается на сытости")
    fr = await make_frog(502, hunger=50, overfeed_total=0)
    await B.inv_add(502, "fly", 20)
    q, m = await press(502, "feed_all")
    fr = await fresh(502)
    left = q_db("SELECT qty FROM shop_inventory WHERE user_id=502 AND item_id='fly'")
    ok(fr["alive"] == 1, "жива")
    ok(fr["hunger"] == 100 and fr["overfeed_total"] <= 15, f"сыта, лишнего {fr['overfeed_total']}")
    ok(left and left[0][0] == 16, f"съела 4 мухи, в запасе {left}")
    q, m = await press(502, "feed_all")
    ok(any("сыта" in (a or "") for a, _ in q.answers), f"сытая не ест: {q.answers}")

    # ─────────────────────────────────────────────────────────────────────
    print("4. Экран смерти и бесплатное возвращение")
    fr = await make_frog(503, alive=0, health=0, coins=40, level=12, death_reason="",
                         died_at=_time.time() - 3 * 86400)
    card = B.status_text(fr)
    check_html(card)
    ok("не дождалась еды" in card and "3 дня назад" in card, "причина и когда")
    ok("бесплатно" in plain(card), "предложено бесплатное возвращение")
    kb = B.main_kb(fr)
    ok(cbs(kb)[0] == "return_revive" and "trial_start" in cbs(kb) and "revive_stars" in cbs(kb),
       f"кнопки мёртвой: {cbs(kb)}")
    ok("menu_care" not in cbs(kb), "обычного меню у мёртвой нет")
    # любая старая кнопка ведёт на экран смерти, а не в тупик
    q, m = await press(503, "menu_care")
    ok(m.last[1] is not None and "return_revive" in cbs(m.last[1]), "старая кнопка → экран смерти")
    # /revive тоже начинает с бесплатного
    rm = Msg(chat=503)
    upd = types.SimpleNamespace(message=rm, effective_user=types.SimpleNamespace(id=503, first_name="Т"),
                                effective_chat=rm.chat)
    await B.cmd_revive(upd, ctx_for(503))
    ok(rm.replies and "return_revive" in cbs(rm.replies[-1][1]), "/revive предлагает бесплатное")
    q, m = await press(503, "return_revive")
    fr = await fresh(503)
    ok(fr["alive"] == 1 and fr["return_revival_used"] == 1, "вернулась")
    ok(fr["subscription_until"] > _time.time() + 2.5 * 86400, "3 дня Няни")
    ok(fr["level"] == 12 and fr["coins"] == 40, "уровень и монеты на месте")
    # второй раз — уже за монеты
    x_db("UPDATE frogs SET alive=0, health=0, death_reason='overfeed', died_at=? WHERE user_id=503", _time.time())
    fr = await fresh(503)
    card = B.status_text(fr)
    ok("объелась" in card and "сегодня" in card, "вторая смерть: причина, сегодня")
    kb = B.main_kb(fr)
    ok("return_revive" not in cbs(kb) and cbs(kb)[0] == "revive_confirm", "второй раз — за монеты")
    ok(f"{B.OVERFEED_REVIVE_COST}" in kb.inline_keyboard[0][0].text, "цена после переедания — 50")
    q, m = await press(503, "revive_confirm")
    ok(q.answers and "Нужно 50" in (q.answers[-1][0] or ""), "денег мало — честный ответ")
    x_db("UPDATE frogs SET coins=100 WHERE user_id=503")
    await fresh(503)
    q, m = await press(503, "revive_confirm")
    fr = await fresh(503)
    ok(fr["alive"] == 1 and fr["coins"] == 100 - B.OVERFEED_REVIVE_COST, f"воскрешена за 50: {fr['coins']}")
    # испытание: обычное меню испытания, не экран смерти
    fr2 = await make_frog(504, alive=0, health=0, trial_active=1, trial_quests="[]", trial_progress="{}")
    ok("menu_care" in cbs(B.main_kb(fr2)), "на испытании — обычное меню")

    # ─────────────────────────────────────────────────────────────────────
    print("5. Кувшинки")
    fr = await make_frog(510, coins=0, last_lily=0)
    q, m = await press(510, "lily|menu")
    ok("lily|go" in cbs(m.last[1]), "вступление с кнопкой")
    random.seed(1)
    # Подменяем щуку: никогда не под выбранной — проходим 3 ряда и забираем
    real_rr = B.random.randrange
    B.random.randrange = lambda n: 1 if n > 1 else 0
    await press(510, "lily|go", m)
    ok(len([c for c in cbs(m.last[1]) if c.startswith("lily|j|")]) == 5, "в первом ряду 5 кувшинок")
    for _ in range(3):
        await press(510, "lily|j|0", m)
    ok("lily|take" in cbs(m.last[1]), "можно забрать")
    await press(510, "lily|take", m)
    fr = await fresh(510)
    bank3 = B.LILY_ROWS[2][1]
    ok(fr["coins"] == bank3, f"забрала {bank3}: {fr['coins']}")
    ok("+" in plain(m.last[0]), "итог с наградой")
    # второй заход на перезарядке — без награды
    await press(510, "lily|go", m)
    await press(510, "lily|j|0", m)
    await press(510, "lily|take", m)
    fr = await fresh(510)
    ok(fr["coins"] == bank3 and "перезарядка" in plain(m.last[0]), "на перезарядке без награды")
    # щука
    x_db("UPDATE frogs SET last_lily=0 WHERE user_id=510")
    await fresh(510)
    B.random.randrange = lambda n: 0
    await press(510, "lily|go", m)
    await press(510, "lily|j|2", m)
    fr = await fresh(510)
    ok("Щука" in plain(m.last[0]) and fr["coins"] == bank3, "щука — банк сгорел")
    # весь пруд
    x_db("UPDATE frogs SET last_lily=0 WHERE user_id=510")
    await fresh(510)
    B.random.randrange = lambda n: n - 1
    before = (await fresh(510))["coins"]
    await press(510, "lily|go", m)
    for _ in B.LILY_ROWS:
        await press(510, "lily|j|0", m)
    fr = await fresh(510)
    ok(fr["coins"] - before >= B.LILY_ROWS[-1][1] and f"+{B.LILY_ROWS[-1][1]}" in plain(m.last[0])
       and "Весь пруд" in plain(m.last[0]),
       f"весь пруд — главный банк: {fr['coins']} {plain(m.last[0])[:200]}")
    B.random.randrange = real_rr
    # нажатие по старой кнопке без игры
    ctx_for(510).user_data.pop("lily", None)
    q, m2 = await press(510, "lily|j|0")
    ok(q.answers and q.answers[-1][1], "старая кнопка — подсказка начать заново")
    # мёртвая не прыгает
    x_db("UPDATE frogs SET alive=0 WHERE user_id=510")
    await fresh(510)
    q, _ = await press(510, "lily|go")
    ok(q.answers and "верни" in (q.answers[-1][0] or ""), "мёртвая не играет")
    # матожидание при игре «до N-го ряда»
    evs = []
    surv = 1.0
    for n, bank in B.LILY_ROWS:
        surv *= (n - 1) / n
        evs.append(surv * bank)
    print(f"  · матожидание по рядам: {[round(e, 1) for e in evs]}")
    ok(8 <= max(evs) <= 15, "лучшая стратегия даёт 8–15🪙")

    # ─────────────────────────────────────────────────────────────────────
    print("6. Кваквордл")
    ok(len(B.KW_WORDS) >= 365 and len(set(B.KW_WORDS)) == len(B.KW_WORDS), "слов больше года, без повторов")
    ok(all(len(w) == 5 and re.fullmatch("[а-я]{5}", w) for w in B.KW_WORDS), "все — 5 букв без ё")
    ok(B.kw_score("канат", "катер") == "ggbby", B.kw_score("канат", "катер"))
    ok(B.kw_score("ааааа", "банка") == "bgbbg", f"повторы: {B.kw_score('ааааа', 'банка')}")
    ok(B.kw_score("лапка", "палка") == "ygygg", B.kw_score("лапка", "палка"))
    ok(B.kw_word("2026-10-21") == B.KW_WORDS[0] and B.kw_word("2026-10-22") == B.KW_WORDS[1], "слова по порядку")
    ok(B.kw_word("2026-10-21") != B.kw_word("2026-10-22"), "каждый день новое")

    fr = await make_frog(520, coins=0, xp=0, level=5)
    answer = B.kw_word()
    q, m = await press(520, "kw|open")
    check_html(m.last[0])
    ok("▫️" in m.last[0] and "kw|help" in cbs(m.last[1]), "пустое поле и правила")
    q, _ = await press(520, "kw|help")
    ok(q.answers and len(q.answers[-1][0]) <= 200 and q.answers[-1][1], "правила алертом ≤200")
    # обычный разговор не перехватывается
    _, stopped = await say(520, "привет как дела")
    ok(not stopped, "фраза из нескольких слов идёт дальше")
    m, stopped = await say(520, "кот")
    ok(stopped and "5 букв" in plain(m.last[0]), "короткое слово — подсказка")
    m, stopped = await say(520, "hello")
    ok(stopped and "русские" in plain(m.last[0]), "латиница — подсказка")
    wrong = next(w for w in B.KW_WORDS if w != answer)
    m, stopped = await say(520, wrong.upper())
    ok(stopped and "🟩" in m.last[0] or "⬛" in m.last[0] or "🟨" in m.last[0], "ход принят, сетка есть")
    m, _ = await say(520, wrong)
    ok("уже было" in plain(m.last[0]), "повтор не считается")
    fr = await fresh(520)
    ok(len(B.kw_load(fr)["g"]) == 1, "в базе одна попытка")
    m, _ = await say(520, answer.replace("е", "ё", 1) if "е" in answer else answer)
    fr = await fresh(520)
    ok(B.kw_load(fr)["done"] == 1, "угадано (ё = е)")
    ok(fr["coins"] == B.KW_REWARD[1] and fr["kw_streak"] == 1, f"награда за 2-ю попытку: {fr['coins']}")
    share = urls(m.last[1])
    ok(share and "start%3Dkw" in share[0] and "2/6" in unquote(share[0]), f"кнопка «Поделиться» со ссылкой kw: {share}")
    txt = unquote(share[0].split("&text=")[1])
    ok(answer not in txt.lower() and "🟩🟩🟩🟩🟩" in txt, "в сетке нет букв, последняя строка зелёная")
    _, stopped = await say(520, answer)
    ok(not stopped, "после победы слова не ловятся")
    fr = await fresh(520)
    ok(fr["coins"] == B.KW_REWARD[1], "второй раз не награждает")
    # серия: вчерашняя победа + сегодня
    fr2 = await make_frog(521, coins=0, kw_streak=4,
                          kw_last_win=(B.datetime.now(B.ST_TZ) - B.timedelta(days=1)).strftime("%Y-%m-%d"))
    await press(521, "kw|open")
    await say(521, answer)
    fr2 = await fresh(521)
    ok(fr2["kw_streak"] == 5 and fr2["coins"] == B.KW_REWARD[0], "серия продолжилась, награда за 1-ю")
    # проигрыш: 6 мимо
    fr3 = await make_frog(522, coins=0, kw_streak=3)
    await press(522, "kw|open")
    misses = [w for w in B.KW_WORDS if w != answer][:6]
    for w in misses:
        m, _ = await say(522, w)
    fr3 = await fresh(522)
    ok(B.kw_load(fr3)["done"] == 2 and fr3["kw_streak"] == 0 and fr3["coins"] == 0, "6 мимо — проигрыш")
    ok(answer.upper() in m.last[0], "показано слово")
    # сдаться
    fr4 = await make_frog(523)
    await press(523, "kw|open")
    await say(523, misses[0])
    q, m = await press(523, "kw|give")
    fr4 = await fresh(523)
    ok(B.kw_load(fr4)["done"] == 2 and answer.upper() in m.last[0], "сдался — слово показано")
    # в группе — нельзя
    q, _ = await press(520, "kw|open", Msg(chat=-100, kind="supergroup"))
    ok(q.answers and "личке" in (q.answers[-1][0] or ""), "в группе — только в личке")
    # без открытой игры слова не ловятся
    fr5 = await make_frog(524)
    _, stopped = await say(524, "кочка")
    ok(not stopped, "без открытой игры — обычное сообщение")
    # завтра — новая игра
    fr = await fresh(520)
    fr["kw_day"] = "2000-01-01"
    ok(B.kw_load(fr) == {"g": [], "done": 0}, "вчерашняя игра не мешает сегодняшней")
    # кнопка в меню игр
    t_, kb = await B.games_screen(await fresh(520), True)
    ok("kw|open" in cbs(kb) and "lily|menu" in cbs(kb), "обе игры в меню")
    t_, kb = await B.games_screen(await fresh(520), False)
    ok("kw|open" not in cbs(kb) and "lily|menu" in cbs(kb), "в группе — только Кувшинки")

    # ─────────────────────────────────────────────────────────────────────
    print("7. Без лягушки в группе — приглашение")
    BOT.sent.clear()
    gm = Msg(chat=-1001, kind="supergroup", mid=7)
    q = Q(9999, "mosquito_catch_1", gm, first_name="Новичок")
    upd = types.SimpleNamespace(callback_query=q, effective_user=q.from_user, effective_chat=gm.chat)
    r = await asyncio.create_task(B.cb_guard(upd, ctx_for(9999)))
    ok(r is None, "дальше не пускает")
    inv = [s for s in BOT.sent if s[0] == -1001]
    ok(len(inv) == 1 and "start=chat_-1001" in urls(inv[0][2])[0], "приглашение со ссылкой чата")
    ok("Новичок" in inv[0][1], "по имени")
    await asyncio.create_task(B.cb_guard(upd, ctx_for(9999)))
    ok(len([s for s in BOT.sent if s[0] == -1001]) == 1, "второй раз за сутки — без сообщения")
    pm = Msg(chat=9998, kind="private")
    q = Q(9998, "refresh", pm)
    await asyncio.create_task(B.cb_guard(types.SimpleNamespace(
        callback_query=q, effective_user=q.from_user, effective_chat=pm.chat), ctx_for(9998)))
    ok(q.answers and "/start" in q.answers[-1][0], "в личке — как раньше")

    # ─────────────────────────────────────────────────────────────────────
    print("8. Статистика: разделы собираются, новые строки на месте")
    now = _time.time()
    x_db("UPDATE frogs SET stars_spent=500, last_seen=? WHERE user_id=503", now)
    x_db("UPDATE frogs SET stars_spent=900, last_seen=? WHERE user_id=504", now - 40 * 86400)
    await make_frog(530, source_chat_id=-1001, born_at=now)
    for key in ["home"] + list(B.ST_SECTIONS):
        sec = await B.st_build(key)
        scr = B._st_screen(sec)
        check_html(scr)
        txt = B._st_text(sec)
        ok("не собрался" not in scr and "None" not in plain(scr), f"{key}: раздел собрался")
        if key == "money":
            ok("Платившие: заходят ли" in txt and "топ-20" in txt, "доходы: заходят ли платившие")
            ok("40 дн назад" in txt and "мертва" in txt or "жива" in txt, "в топе — когда заходил")
        if key == "modes":
            ok("Кваквордл: сыграли" in txt and "Кувшинки: игр" in txt, "режимы: новые игры")
        if key == "chats":
            ok("без лягушки нажали кнопку" in txt, "чаты: новички из групп")
        if key == "players":
            m_ = re.search(r"из групп\s+(\d+)", txt)
            ok(m_ and int(m_.group(1)) >= 1, f"из групп считается: {m_ and m_.group(0)}")
    ok(B.st_label("menu_feed") == "Меню: еда" and B.st_label("plaza") == "Площадь", "подписи без сырых ключей")
    labels = [v for k, v in B.ST_FEAT_LABELS.items() if not k.startswith(("job:", "/"))]
    dups = {v for v in labels if labels.count(v) > 1} - {"Воскрешение", "Пустая кнопка", "Рефералка",
                                                         "Облики", "Игры", "Чужое кормление", "Комар",
                                                         "Память", "Соседи"}
    ok(not {"Задания", "Достижения", "Настройки"} & dups, f"одинаковые подписи: {dups}")

    print("9. Авторежим казино пишется в журнал")
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    loop_src = src[src.index("async def _casino_auto_loop"):src.index("_CASINO_ANIM_SLEEP = ")]
    ok("log_game(" in src[src.index("async def _casino_auto_loop"):][:12000], "в авторежиме есть log_game")

    print("10. Чистка старых журналов")
    old = now - 200 * 86400
    x_db("INSERT INTO game_logs(user_id, game_type, bet_amount, win_amount, result, details, ts) "
         "VALUES(1,'casino',10,0,'loss','{}',?)", old)
    x_db("INSERT INTO game_logs(user_id, game_type, bet_amount, win_amount, result, details, ts) "
         "VALUES(1,'casino',10,0,'loss','{}',?)", now)
    x_db("INSERT INTO gacha_log(user_id, skin, rarity, cost, source, ts) VALUES(1,'Brownie','common',50,'coins',?)", old)
    n = await B.logs_purge_old()
    ok(n == 2, f"удалено {n}")
    ok(q_db("SELECT COUNT(*) FROM game_logs WHERE ts>=?", now - 10) == [(1,)], "свежие остались")

    print("11. Шум миграций не считается ошибкой")
    rec = logging.LogRecord("frog_bot", logging.ERROR, __file__, 1, "подавлено исключение: %s",
                            (sqlite3.OperationalError("duplicate column name: x"),), None)
    ok(not B._MIGRATION_NOISE.filter(rec), "duplicate column отфильтрован")
    rec2 = logging.LogRecord("frog_bot", logging.ERROR, __file__, 1, "настоящая ошибка %s", ("x",), None)
    ok(B._MIGRATION_NOISE.filter(rec2), "настоящая ошибка проходит")

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
