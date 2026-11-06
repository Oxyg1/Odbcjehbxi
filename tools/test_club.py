"""
Болотный клуб: подписка Telegram Stars, которую Telegram продлевает сам.
Весь путь игрока — экран, оплата, воскрешение, защита от смерти, клубная
крутка, продление, напоминание до списания, отмена, конец клуба и возврат,
переход с Трудяги, пробные дни, стаж в группах, отчёт. Плюс учёт платежей
и проверки до оплаты.

Запуск из корня репозитория:
    python3 tools/test_club.py
    SHOW=1 python3 tools/test_club.py   # ещё и напечатать экраны и письма

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="club_test_"), "test.db")
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
        self.mid, self.sent, self.links, self.subs_edits, self.invoices = 100, [], [], [], []
        self.edit_ok = True
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.mid += 1
        self.sent.append((chat_id, text, reply_markup, kw))
        if os.environ.get("SHOW"):
            print(f"\n── письмо {chat_id}\n{plain(text)}")
        return Sent(self.mid)
    async def create_invoice_link(self, **kw):
        self.links.append(kw)
        return "https://t.me/$club_invoice"
    async def edit_user_star_subscription(self, user_id, charge_id, is_canceled, **kw):
        if not self.edit_ok:
            raise B.BadRequest("SUBSCRIPTION_NOT_FOUND")
        self.subs_edits.append((user_id, charge_id, is_canceled))
        return True
    async def send_invoice(self, *a, **kw):
        self.invoices.append(kw)
        return Sent(1)
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
    r = router or (B.club_router if data.startswith("club|") else
                   B.shop_router if data.startswith(("shop_", "sub_")) else B.on_callback)
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





_charge = [0]

async def pay(uid, payload, stars, recurring=False, first=False, exp=None, charge=None):
    """Оплата так, как её присылает Telegram: сервисное сообщение successful_payment."""
    if charge is None:
        _charge[0] += 1
        charge = f"ch{_charge[0]}"
    sp = types.SimpleNamespace(invoice_payload=payload, total_amount=stars, telegram_payment_charge_id=charge,
                               is_recurring=recurring, is_first_recurring=first,
                               subscription_expiration_date=exp, currency="XTR")
    m = Msg(chat=uid)
    m.successful_payment = sp
    upd = types.SimpleNamespace(message=m, effective_user=types.SimpleNamespace(id=uid, first_name="Т", username=""),
                                effective_chat=m.chat)
    await asyncio.create_task(B.successful_payment(upd, ctx_for(uid)))
    await asyncio.sleep(0.05)
    B._user_cache.clear()
    return m, charge


def exp_in(days):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(_time.time() + days * 86400, tz=timezone.utc)


def sent_to(uid, since=0):
    return [(plain(t), kb, kw) for cid, t, kb, kw in BOT.sent[since:] if cid == uid]


async def run_decay(uid, hours):
    f = await B.db_get(uid)
    for _ in range(hours):
        f["last_decay"] -= 3600
        f = B.decay(f)
    await B.db_save(f)
    B._user_cache.clear()
    return await B.db_get(uid)


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    B._get_today_weather = lambda: {}
    B.announce = lambda *a, **k: asyncio.sleep(0)
    now = _time.time()
    D, A, W, T, G = 801, 802, 803, 804, 805     # мёртвая, живая, с Трудягой, пробник, групповой

    print("1. Экран клуба для того, кто не в нём")
    await make_frog(D, alive=0, health=0, hunger=0, last_decay=now - 5 * 86400, stars_spent=40)
    q, m = await press(D, "club|menu")
    t, kb = plain(m.last[0]), m.last[1]
    ok("Болотный клуб" in t and f"{B.CLUB_STARS}⭐" in t, "название и цена")
    ok("вернётся сразу" in t, "мёртвой — что вернётся")
    ok("Легендарный" in t and "Стаж" in t and "Автоуход" in t, "всё, что даёт клуб")
    ok("отменить" in t.lower(), "сказано, что можно отменить")
    urls = [b.url for row in kb.inline_keyboard for b in row if b.url]
    ok(urls and BOT.links and BOT.links[-1]["subscription_period"] == 30 * 86400
       and BOT.links[-1]["prices"][0].amount == B.CLUB_STARS, "кнопка — подписка Telegram на 30 дней")
    ok("club|trial" not in cbs(kb), "мёртвой пробные дни не дают — вернуть её можно вступлением")
    ok("Вернуть в клубе" in " ".join(labels(B.dead_kb(await B.db_get(D)))), "на экране смерти есть клуб")

    print("2. Старые кнопки подписок ведут в клуб, счетов не выставляют")
    for old in ("sub_buy_worker", "sub_buy_nanny", "sub_buy_nanny_7", "sub_renew",
                "sub_renewal_offer_worker", "sub_trial_worker", "shop_sub"):
        q, m = await press(D, old)
        ok("Болотный клуб" in plain(m.last[0]), f"{old} → клуб")
    ok(not BOT.invoices, "ни одного счёта по старым ценам")
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    ok("sale_price  = 640" not in src and "640 if is_worker" not in src, "оффера за 640⭐ больше нет")

    print("3. Проверки до оплаты")
    newbie = next(i for i, p in enumerate(B.STAR_PACKAGES) if p.get("newbie"))
    ok("Новичок" in await B.precheckout_problem(D, f"coins_{newbie}"), "«Новичок» второй раз — отказ до оплаты")
    await make_frog(A, coins=100)
    ok(await B.precheckout_problem(A, f"coins_{newbie}") == "", "первая покупка — можно")
    ok(await B.precheckout_problem(A, B.CLUB_PAYLOAD) == "", "в клуб — можно")

    print("4. Вступление: мёртвая лягушка возвращается")
    before = len(BOT.sent)
    m, ch1 = await pay(D, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30))
    f = await B.db_get(D)
    ok(f["alive"] == 1 and all(f[k] == 100 for k in ("health", "hunger", "happiness", "cleanliness", "energy")),
       "жива, все показатели 100")
    ok(now - 60 < f["last_decay"] <= _time.time(), "отметка затухания — сейчас (иначе умерла бы снова)")
    ok(f["club_months"] == 1 and f["club_charge_id"] == ch1, "1-й месяц, номер списания сохранён")
    ok(abs(f["club_until"] - (now + 30 * 86400 + B.CLUB_BUFFER)) < 120, "срок — от даты Telegram")
    ok(B.sub_active(f) == 1 and f["subscription_until"] >= f["club_until"] - 1, "автоуход включён")
    ok(f["stars_spent"] == 40 + B.CLUB_STARS, "звёзды учтены")
    txt = plain(m.last[0])
    ok("Добро пожаловать" in txt and "снова с тобой" in txt and "не умрёт" in txt, f"приветствие: {txt[:80]!r}")
    ok("club|spin" in cbs(m.last[1]), "сразу — кнопка клубной крутки")
    ok(q_db("SELECT COUNT(*) FROM payments WHERE user_id=?", D)[0][0] == 1, "платёж записан")
    ok("уже в клубе" in await B.precheckout_problem(D, B.CLUB_PAYLOAD), "второй раз оплатить нельзя")

    print("5. Повтор того же платежа от Telegram ничего не начисляет")
    await pay(D, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30), charge=ch1)
    f = await B.db_get(D)
    ok(f["club_months"] == 1 and f["stars_spent"] == 40 + B.CLUB_STARS, "месяц и звёзды не задвоились")

    print("6. В клубе лягушка не умирает")
    x_db("UPDATE frogs SET hunger=0, happiness=0, cleanliness=0, energy=0, health=5 WHERE user_id=?", D)
    B._user_cache.clear()
    f = await run_decay(D, 48)
    ok(f["alive"] == 1 and f["health"] >= 1, f"двое суток без ухода — жива (здоровье {f['health']})")
    g = dict(f, overfeed_total=B.OVERFEED_DEATH_THRESHOLD + 50)
    ok(not B.check_overfeed(g) and g["alive"] == 1, "не лопается от переедания")
    x_db("UPDATE frogs SET hunger=50, happiness=50, cleanliness=50, energy=50, health=60 WHERE user_id=?", D)

    print("7. Клубная крутка: раз в день и без обычных обликов")
    rolls = [B.club_roll() for _ in range(3000)]
    ok(all(B.SKINS[s]["rarity"] not in ("common", "secret") for s in rolls), "обычных и секретных нет")
    leg = sum(B.SKINS[s]["rarity"] in ("legendary", "mythic") for s in rolls) / len(rolls)
    ok(0.015 < leg < 0.06, f"легендарный — примерно раз в месяц ({leg * 30:.1f} за 30 дней)")
    f = await B.db_get(D)
    ok("club|spin" in cbs(B.main_kb(f)), "в главном меню — кнопка крутки")
    coll0 = len(await B.db_coll(D))
    q, m = await press(D, "club|spin")
    t = plain(m.last[0])
    ok("Клубная крутка" in t and "завтра" in t, f"результат: {t[:70]!r}")
    ok(len(await B.db_coll(D)) >= coll0 and q_db("SELECT COUNT(*) FROM gacha_log WHERE user_id=? AND source='club'", D)[0][0] == 1,
       "облик выдан и записан в журнал гачи")
    q, m = await press(D, "club|spin")
    ok(q.answers and q.answers[0][1] and "завтра" in q.answers[0][0], "второй раз за день — нет")
    ok("club|spin" not in cbs(B.main_kb(await B.db_get(D))), "кнопка из меню пропала до завтра")

    print("8. Экран участника")
    await B.job_auto_care(types.SimpleNamespace(bot=BOT))
    q, m = await press(D, "club|menu")
    t, kb = plain(m.last[0]), m.last[1]
    ok("Росток" in t and "1-й месяц" in t, "ступень и месяц")
    ok("Побег — через 1 месяц" in t, "что дальше")
    ok("Следующее списание" in t and f"{B.CLUB_STARS}⭐" in t, "когда и сколько спишется")
    ok("club|cancel" in cbs(kb), "отмена продления на виду")

    print("9. За сутки до списания — итог месяца, один раз и без звука")
    x_db("UPDATE frogs SET club_until=? WHERE user_id=?", _time.time() + 20 * 3600 + B.CLUB_BUFFER, D)
    B._user_cache.clear()
    before = len(BOT.sent)
    await B.job_club(types.SimpleNamespace(bot=BOT))
    await B.job_club(types.SimpleNamespace(bot=BOT))
    w = [x for x in sent_to(D, before) if "Месяц в клубе" in x[0]]
    ok(len(w) == 1, f"одно письмо ({len(w)})")
    ok(w and "Завтра продление" in w[0][0] and "2-й месяц" in w[0][0] and "Побег" in w[0][0],
       "сказано, что спишется и что будет")
    ok(w and "клубных круток — 1" in w[0][0], f"итог месяца: {w[0][0] if w else ''!r}")
    ok(w and w[0][2].get("disable_notification"), "без звука")

    print("10. Продление от Telegram: новая ступень")
    before = len(BOT.sent)
    await pay(D, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=False, exp=exp_in(30))
    f = await B.db_get(D)
    ok(f["club_months"] == 2 and f["club_charge_id"] == ch1, "2-й месяц, номер подписки прежний")
    r = sent_to(D, before)
    ok(r and "Новая ступень клуба — Побег" in r[-1][0] and r[-1][2].get("disable_notification"),
       "письмо о новой ступени, без звука")

    print("11. Отмена продления — честно и обратимо")
    q, m = await press(D, "club|cancel")
    t = plain(m.last[0])
    ok("доработает" in t and "снова сможет умереть" in t and "сохранится ещё 3 дня" in t,
       "перед отменой сказано, что будет")
    q, m = await press(D, "club|cancel_yes")
    ok(BOT.subs_edits[-1] == (D, ch1, True), "Telegram получил отмену по номеру подписки")
    ok((await B.db_get(D))["club_canceled"] == 1 and "Продление выключено" in plain(m.last[0]), "экран это показывает")
    ok("включи продление" in (await B.precheckout_problem(D, B.CLUB_PAYLOAD)).lower(),
       "платить второй раз не даём — подсказываем включить")
    q, m = await press(D, "club|resume")
    ok(BOT.subs_edits[-1] == (D, ch1, False) and (await B.db_get(D))["club_canceled"] == 0, "и включение назад")
    BOT.edit_ok = False
    q, m = await press(D, "club|cancel_yes")
    ok(q.answers and "Подписки" in (q.answers[0][0] or ""), "если Telegram не принял — где отменить вручную")
    ok((await B.db_get(D))["club_canceled"] == 0, "и флаг не врёт")
    BOT.edit_ok = True

    print("12. Клуб закончился: одно письмо, стаж ждёт 3 дня")
    x_db("UPDATE frogs SET club_until=? WHERE user_id=?", _time.time() - 3600, D)
    B._user_cache.clear()
    before = len(BOT.sent)
    await B.job_club(types.SimpleNamespace(bot=BOT))
    await B.job_club(types.SimpleNamespace(bot=BOT))
    r = [x for x in sent_to(D, before) if "Клуб закончился" in x[0]]
    ok(len(r) == 1 and "Побег" in r[0][0] and "сохранится до" in r[0][0], "одно письмо про стаж")
    f = await B.db_get(D)
    ok(not B.club_on(f) and B.club_chat_note(f) == "", "в чатах стажа больше не видно")
    await pay(D, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30))
    f = await B.db_get(D)
    ok(f["club_months"] == 3, f"вернулся в отсрочку — стаж продолжился ({f['club_months']})")
    x_db("UPDATE frogs SET club_until=? WHERE user_id=?", _time.time() - 4 * 86400, D)
    B._user_cache.clear()
    m, _ = await pay(D, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30))
    ok((await B.db_get(D))["club_months"] == 1, "после 3 дней — стаж с начала")

    print("13. Участник с Трудягой: Трудягу даром не продлеваем")
    await make_frog(W, subscription_type=2, subscription_until=now + 5 * 86400, subscription_auto=1)
    await pay(W, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30))
    f = await B.db_get(W)
    ok(f["subscription_type"] == 2 and abs(f["subscription_until"] - (now + 5 * 86400)) < 5, "срок Трудяги прежний")
    x_db("UPDATE frogs SET subscription_until=? WHERE user_id=?", _time.time() - 60, W)
    B._user_cache.clear()
    await B.job_club(types.SimpleNamespace(bot=BOT))
    f = await B.db_get(W)
    ok(f["subscription_type"] == 1 and f["subscription_until"] >= f["club_until"] - 1,
       "Трудяга кончилась — присмотр перешёл на клуб")
    before = len(BOT.sent)
    await B.job_sub_expiry_offer(types.SimpleNamespace(bot=BOT))
    ok(not any("закончилась" in x[0] for x in sent_to(W, before)), "участнику клуба — без письма про старую подписку")

    print("14. Старая подписка кончилась у не-участника — одно честное письмо")
    await make_frog(805, subscription_type=2, subscription_until=now - 3600)
    before = len(BOT.sent)
    await B.job_sub_expiry_offer(types.SimpleNamespace(bot=BOT))
    await B.job_sub_expiry_offer(types.SimpleNamespace(bot=BOT))
    r = sent_to(805, before)
    ok(len(r) == 1 and "Болотный клуб" in r[0][0] and "скидк" not in r[0][0].lower(), "без фальшивых скидок")

    print("15. Пробные дни")
    await make_frog(T)
    q, m = await press(T, "club|menu")
    ok("club|trial" in cbs(m.last[1]), "живой — предложены")
    q, m = await press(T, "club|trial")
    f = await B.db_get(T)
    ok(B.club_on(f) and not B.club_member(f) and B.sub_active(f) == 1, "клуб работает, автоуход включён, стажа нет")
    ok(B.club_chat_note(f) == "", "в чатах пробник не виден")
    ok("Пробные дни до" in plain(m.last[0]), "экран пробных дней")
    q, m = await press(T, "club|spin")
    ok("Клубная крутка" in plain(m.last[0]), "крутка в пробные дни есть")
    q, m = await press(T, "club|trial")
    ok(q.answers and q.answers[0][1], "второй раз — нет")
    x_db("UPDATE frogs SET club_until=? WHERE user_id=?", _time.time() - 60, T)
    B._user_cache.clear()
    before = len(BOT.sent)
    await B.job_club(types.SimpleNamespace(bot=BOT))
    ok(any("Пробные дни клуба закончились" in x[0] for x in sent_to(T, before)), "конец пробных дней — письмо")
    await pay(T, B.CLUB_PAYLOAD, B.CLUB_STARS, recurring=True, first=True, exp=exp_in(30))
    ok((await B.db_get(T))["club_months"] == 1, "вступил после пробника — 1-й месяц")

    print("16. Стаж в группах — словами")
    f = await B.db_get(D)
    x_db("UPDATE frogs SET club_months=4 WHERE user_id=?", D)
    B._user_cache.clear()
    f = await B.db_get(D)
    ok(B.club_chat_note(f) == "в клубе 4-й месяц", "в топе чата")
    ok("В Болотном клубе 4-й месяц" in B.group_frog_text(f), "в карточке /frog в группе")

    print("17. Платное воскрешение больше не убивает снова")
    await make_frog(G, alive=0, health=0, hunger=0, last_decay=now - 4 * 86400)
    await pay(G, "revive_stars_instant", 15)
    f = await B.db_get(G)
    f = B.decay(f)
    ok(f["alive"] == 1 and f["hunger"] >= 99, f"после оплаты жива и сыта ({f['hunger']})")

    print("18. Отчёт")
    import aiosqlite
    async with aiosqlite.connect(DB) as db:
        sec = await B._sts_money(B._StCtx(db))
    body = B._st_text(sec)
    if os.environ.get("SHOW"):
        print(body)
    ok("Болотный клуб" in body and "Повторные платежи" in body, "клуб и повторные платежи в отчёте")
    ok("автоуход не на паузе" in body and "с автопродлением" not in body, "метка больше не врёт про продление")

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
