"""
Бот в группах: только настоящее «ква», откат молча, ответы короткие и без
смайлов-украшений, личное — кнопкой в личку с меткой чата, новичку —
приглашение раз в сутки, «батл» ответом (решают уровень и уход), лягушка дня,
/top — лягушки чата, приветствие при добавлении.

Запуск из корня репозитория:
    python3 tools/test_groups.py
    SHOW=1 python3 tools/test_groups.py   # ещё и напечатать, что бот пишет в чат

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="groups_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B
from telegram.ext import ApplicationHandlerStop

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

def plain(t):
    return re.sub(r"<[^>]+>", "", t or "")

CHAT = -100777


class Sent:
    def __init__(self, mid, chat=None):
        self.message_id, self.chat = mid, types.SimpleNamespace(id=chat)

class FakeBot:
    username, id = "frogbot", 999
    def __init__(self):
        self.out, self.mid, self.deleted = [], 500, []
    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.mid += 1
        self.out.append(("send", chat_id, text, reply_markup))
        return Sent(self.mid, chat_id)
    async def get_me(self):
        return types.SimpleNamespace(username="frogbot", id=999)
    async def set_message_reaction(self, chat_id, message_id, reaction=None, **kw):
        self.out.append(("reaction", chat_id, reaction[0].emoji, None))
    async def delete_message(self, chat_id, message_id, **kw):
        self.deleted.append((chat_id, message_id))
    async def get_chat_member(self, *a, **k):
        return types.SimpleNamespace(status="member", can_delete_messages=False)
    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return Sent(1)
        return _noop

BOT = FakeBot()
_mid = [1000]

def tg_user(uid):
    return types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}", is_bot=False,
                                 last_name="", language_code="ru", is_premium=False)

class Msg:
    def __init__(self, uid, text, chat=CHAT, reply_to=None):
        _mid[0] += 1
        self.chat = types.SimpleNamespace(id=chat, type="supergroup" if chat < 0 else "private", title="Тест", username="")
        self.text, self.message_id = text, _mid[0]
        self.from_user = tg_user(uid)
        self.sticker = self.dice = self.caption = self.photo = None
        self.reply_to_message = types.SimpleNamespace(from_user=tg_user(reply_to), message_id=1) if reply_to else None
        self.entities, self.message_thread_id, self.is_topic_message = [], None, False
        self.forward_origin = None
    async def reply_text(self, text, reply_markup=None, **kw):
        BOT.mid += 1
        BOT.out.append(("reply", self.chat.id, text, reply_markup))
        return Sent(BOT.mid, self.chat.id)
    async def delete(self):
        return True
    def get_bot(self):
        return BOT

UD, BD = {}, {}
def ctx(uid):
    return types.SimpleNamespace(bot=BOT, user_data=UD.setdefault(uid, {}), bot_data=BD, args=[], application=None)

ALL_OUT = []

async def say(uid, text, handler=None, chat=CHAT, reply_to=None):
    """Сообщение в группу — по тем же ступеням, что в боте: перехватчик команд,
    перехватчик остальных сообщений, потом обычный обработчик."""
    m = Msg(uid, text, chat, reply_to)
    upd = types.SimpleNamespace(message=m, effective_message=m, effective_user=m.from_user,
                                effective_chat=m.chat, callback_query=None, get_bot=lambda: BOT)
    n = len(BOT.out)
    stopped = False
    try:
        if text.startswith("/"):
            await asyncio.create_task(B.group_cmd_router(upd, ctx(uid)))
        elif chat < 0:
            await asyncio.create_task(B.group_text_hook(upd, ctx(uid)))
    except ApplicationHandlerStop:
        stopped = True
    if not stopped:
        await asyncio.create_task((handler or B.on_message)(upd, ctx(uid)))
    await asyncio.sleep(0.05)
    out = BOT.out[n:]
    ALL_OUT.extend(out)
    if os.environ.get("SHOW"):
        print(f"\n>>> [{uid}] {text}")
        for kind, cid, t, kb in out:
            print(f"  <{kind}> " + plain(t).replace("\n", "\n    "))
            if kb:
                print("    [" + "] [".join(b.text for r in kb.inline_keyboard for b in r) + "]")
    return out, stopped

def lines(t):
    return plain(t).strip().count("\n") + 1

# Эмодзи в тексте, кроме премиум-значков <tg-emoji> (один в заголовке — правило бота)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")

def raw_emoji(t):
    return _EMOJI.findall(plain(re.sub(r"<tg-emoji[^>]*>.*?</tg-emoji>", "", t or "")))

def urls(kb):
    return [b.url for r in kb.inline_keyboard for b in r if b.url] if kb else []


def db1(sql, *args):
    con = sqlite3.connect(DB)
    row = con.execute(sql, args).fetchone()
    con.close()
    return row


async def make_frog(uid, **fields):
    user = types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    await asyncio.sleep(0.2)
    sets = {"onboard_step": 0, "frog_name": f"Ква{uid}", "level": 12, "last_decay": _time.time(),
            "hunger": 90, "happiness": 90, "health": 90, "cleanliness": 90, "energy": 90, **fields}
    con = sqlite3.connect(DB, timeout=30)
    con.execute(f"UPDATE frogs SET {','.join(k + '=?' for k in sets)} WHERE user_id=?", (*sets.values(), uid))
    con.commit()
    con.close()
    B._user_cache.clear()


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    P, Q, N, R = 11, 33, 22, 44          # с лягушкой, с голодной лягушкой, новичок, ещё один
    await make_frog(P, frog_name="Ква&Ко")
    await make_frog(Q, hunger=8, energy=8, happiness=10, health=20, cleanliness=10)
    await make_frog(R, level=30)

    print("1. Какие слова — «ква»")
    for w in ("ква", "Квак!", "кваааа", "ква-ква", "ну ква всем"):
        ok(B.is_kva(w), f"«{w}» — ква")
    for w in ("квартира", "квас", "Кваквордл", "квадрат", "акваланг"):
        ok(not B.is_kva(w), f"«{w}» — не ква")

    print("2. Ква в группе: коротко, повтор — молча")
    out, _ = await say(P, "ква")
    ok(len(out) == 1 and out[0][0] == "reply", "один ответ")
    ok(lines(out[0][2]) <= 2, f"не больше двух строк: {plain(out[0][2])!r}")
    ok("Ква&amp;Ко" in out[0][2] and "&amp;amp;" not in out[0][2], "имя лягушки не экранируется дважды")
    out, _ = await say(P, "ква")
    ok(not out, f"откат — ни сообщения, ни реакции: {out}")
    for w in ("квартира на продажу", "квас холодный", "играю в Кваквордл"):
        out, _ = await say(P, w)
        ok(not out, f"«{w}» — бот молчит")

    print("3. Новичок пишет «ква» — приглашение раз в сутки, со ссылкой на чат")
    out, _ = await say(N, "ква")
    ok(len(out) == 1 and any(f"start=chat_{CHAT}" in u for u in urls(out[0][3])), f"приглашение с меткой чата: {out}")
    out, _ = await say(N, "ква")
    ok(not out, "второй раз за сутки — молча")

    print("4. Команды в группе — коротко, личное — в личку")
    for cmd in ("/frog", "/start", "/mystats"):
        out, stopped = await say(P, cmd)
        ok(stopped and len(out) == 1 and lines(out[0][2]) <= 3, f"{cmd}: карточка до 3 строк ({out and plain(out[0][2])!r})")
        ok(any(f"start=chat_{CHAT}" in u for u in urls(out[0][3])), f"{cmd}: кнопка в личку с меткой чата")
    out, _ = await say(P, "/frog")
    ok("В хорошей форме" in plain(out[0][2]), "ухоженная лягушка — «в хорошей форме»")
    out, _ = await say(Q, "/frog")
    ok("Голодная" in plain(out[0][2]) and "пора в личку" in plain(out[0][2]),
       f"голодная лягушка — словами, а не значками: {plain(out[0][2])!r}")
    out, stopped = await say(N, "/start")
    ok(stopped and "нет лягушки" in plain(out[0][2]), "новичку /start в группе — без знакомства в чате")
    out, stopped = await say(P, "/daily")
    grp = [o for o in out if o[1] == CHAT]
    ok(stopped and len(grp) == 1 and lines(grp[0][2]) == 1, f"/daily — одна строка: {grp}")
    out, _ = await say(P, "/help")
    ok(lines(out[0][2]) <= 9, f"помощь для группы — короткая ({lines(out[0][2])} строк)")
    for cmd in ("/games", "/casino", "/staya", "/expedition"):
        out, stopped = await say(P, cmd)
        ok(stopped and len(out) == 1 and lines(out[0][2]) == 1 and urls(out[0][3]), f"{cmd} — одной строкой в личку")
    out, stopped = await say(P, "/frog@otherbot", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped and not out, "команда другому боту — не наша")
    out, stopped = await say(P, "/duel", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped, "игры на двоих идут своими обработчиками")

    print("5. Батл ответом на сообщение: решают уровень и уход")
    _uniform = B.random.uniform
    B.random.uniform = lambda a, b: (a + b) / 2       # без удачи — исход по силе
    await say(Q, "всем привет")
    out, stopped = await say(P, "батл", reply_to=Q)
    t = plain(out[0][2]) if out else ""
    ok(stopped and len(out) == 1, f"один ответ, дальше не передаём: {out}")
    ok("Победа: U11" in t, f"ухоженная лягушка того же уровня бьёт голодную: {t!r}")
    ok("голодная" in t and "сил было меньше" in t, f"причина — настоящая, из состояния лягушки: {t!r}")
    ok("Счёт" not in t, "счёт после первого же батла не нужен")
    ok(db1("SELECT wins FROM chat_members WHERE chat_id=? AND user_id=?", CHAT, P) == (1,)
       and db1("SELECT losses FROM chat_members WHERE chat_id=? AND user_id=?", CHAT, Q) == (1,),
       "победа и поражение записаны чату")
    coins = db1("SELECT coins FROM frogs WHERE user_id=?", P)
    out, _ = await say(P, "батл", reply_to=Q)
    ok(len(out) == 1 and "Следующий батл" in plain(out[0][2]), "повтор сразу — «следующий через …»")
    B._battle_last.clear()
    out, _ = await say(P, "Батл!", reply_to=Q)
    ok(out and "Счёт: U11 2 — 0 U33" in plain(out[0][2]), f"счёт между двумя: {out and plain(out[0][2])!r}")
    ok(db1("SELECT coins FROM frogs WHERE user_id=?", P) == coins, "батл монет не печатает")
    out, _ = await say(P, "батл", reply_to=N)
    ok(len(out) == 1 and "без лягушки" in plain(out[0][2]) and any(f"start=chat_{CHAT}" in u for u in urls(out[0][3])),
       "соперник без лягушки — ему приглашение")
    out, _ = await say(R, "батл", reply_to=N)
    ok(not out, "второе приглашение тому же новичку в течение часа — молча")
    out, stopped = await say(N, "батл", reply_to=P)
    ok(stopped and len(out) <= 1, "новичок зовёт на батл — приглашение (или тишина, если уже звали)")
    out, stopped = await say(P, "батл", reply_to=P)
    ok(stopped and not out, "батл самому себе — молча")
    out, stopped = await say(P, "батл как дела", reply_to=Q)
    ok(not stopped, "«батл» внутри фразы — не команда")
    out, _ = await say(P, "/vs")
    ok(out and "Ответь словом «батл»" in plain(out[0][2]), "/vs без ответа — подсказка")
    B._battle_last.clear()
    out, stopped = await say(R, "/vs", reply_to=P)
    ok(stopped and out and "Победа: U44" in plain(out[0][2]), "/vs ответом — тот же батл; ур. 30 против 12 побеждает")
    await B.save_chat_settings(CHAT, allow_duels=0)
    B._chat_settings_cache.invalidate(CHAT)
    B._battle_last.clear()
    out, stopped = await say(P, "батл", reply_to=Q)
    ok(not stopped and not out, "админ выключил дуэли — батлов нет")
    await B.save_chat_settings(CHAT, allow_duels=1)
    B._chat_settings_cache.invalidate(CHAT)

    B.random.uniform = _uniform
    wins = 0
    for _ in range(400):
        B._battle_last.clear()
        out, _ = await say(R, "батл", reply_to=Q)          # ур. 30 и ухоженная против ур. 12 голодной
        wins += "Победа: U44" in plain(out[0][2])
    ok(wins == 400, f"сильная и ухоженная против слабой и голодной — всегда: {wins}/400")
    upsets = 0
    await make_frog(77, level=30, hunger=20, energy=20, happiness=20, health=30, cleanliness=20)
    for _ in range(400):
        B._battle_last.clear()
        out, _ = await say(77, "батл", reply_to=P)          # запущенная 30-я против ухоженной 12-й
        upsets += "Победа: U77" in plain(out[0][2])
    ok(80 < upsets < 220, f"запущенная лягушка высокого уровня проигрывает ухоженной чаще: {upsets}/400 побед")
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM chat_members WHERE user_id=77")
    con.execute("UPDATE chat_members SET wins=1, losses=0 WHERE user_id=44")
    con.execute("UPDATE chat_members SET wins=2, losses=1 WHERE user_id=11")
    con.commit()
    con.close()

    print("6. Топ чата — по уровню, с победами")
    out, _ = await say(P, "/top")
    t = plain(out[0][2])
    ok("Лягушки чата" in t and t.index("U44") < t.index("U11") < t.index("U33"), f"порядок по уровню: {t!r}")
    ok("2 победы" in t, "победы в строке игрока")
    ok("U22" not in t, "без лягушки в топ не попадаешь")
    out, _ = await say(P, "/frog")
    ok("В этом чате: 2 победы, 1 поражение" in plain(out[0][2]), f"в карточке — счёт в этом чате: {plain(out[0][2])!r}")

    print("7. Лягушка дня")
    out, _ = await say(P, "/frogday")
    t = out[0][2] if out else ""
    ok("Лягушка дня" in plain(t) and "tg://user?id=" in t and "Первая корона" in plain(t), f"выбор с упоминанием: {plain(t)!r}")
    ok(db1("SELECT SUM(days) FROM chat_members WHERE chat_id=?", CHAT) == (1,), "корона записана")
    out, _ = await say(Q, "/frogday")
    ok(out and "Сегодня лягушка дня" in plain(out[0][2]), "второй раз за день — уже выбрана")
    out, _ = await say(P, "/frogday", chat=-100555)
    ok(out and "меньше двух" in plain(out[0][2]), "в чате, где лягушка одна, — объяснение")

    print("8. Режимы чата уважаются")
    await B.save_chat_settings(CHAT, mode="vanilla")
    B._chat_settings_cache.invalidate(CHAT)
    out, stopped = await say(P, "/frog", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped, "в «ванильном» режиме чата — его собственные правила")
    out, stopped = await say(P, "батл", reply_to=Q, handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped and not out, "и батлов там нет")
    await B.save_chat_settings(CHAT, mode="full")
    B._chat_settings_cache.invalidate(CHAT)

    print("9. Приветствие при добавлении в группу")
    BOT.out.clear()
    ev = types.SimpleNamespace(
        chat=types.SimpleNamespace(id=-100888, type="supergroup", username="", title="Новый чат"),
        old_chat_member=types.SimpleNamespace(status="left"),
        new_chat_member=types.SimpleNamespace(status="member"),
        from_user=types.SimpleNamespace(id=P))
    await B.on_my_chat_member(types.SimpleNamespace(my_chat_member=ev), ctx(P))
    hello = [o for o in BOT.out if o[1] == -100888]
    if os.environ.get("SHOW") and hello:
        print("\n>>> бота добавили в чат\n  <send> " + plain(hello[0][2]).replace("\n", "\n    "))
    ok(len(hello) == 1 and "батл" in plain(hello[0][2]), "сразу короткое приветствие, без /activate")
    ok(lines(hello[0][2]) <= 6 and any("start=chat_-100888" in u for u in urls(hello[0][3])), "с кнопкой и меткой чата")
    ALL_OUT.extend(hello)

    print("10. Никаких смайлов-украшений в чате")
    for kind, cid, t, kb in ALL_OUT:
        if kind not in ("reply", "send") or cid > 0:
            continue                      # личные уведомления — по правилам лички
        ok(not raw_emoji(t), f"в тексте только премиум-значок заголовка: {raw_emoji(t)} в {plain(t)[:60]!r}")
        for b in (b for r in (kb.inline_keyboard if kb else []) for b in r):
            ok(not raw_emoji(b.text), f"кнопка без смайла: {b.text!r}")

    print("11. Личка: /start, /frog, /mymenu, /help, /cooldowns отвечают (group_reply не перекрыта)")
    import inspect
    ok("kwargs" in inspect.signature(B.group_reply).parameters, "group_reply — прежняя, с **kwargs")
    for cmd, fn in (("/start", B.cmd_start), ("/frog", B.cmd_frog), ("/mymenu", B.cmd_mymenu),
                    ("/help", B.cmd_help), ("/cooldowns", B.cmd_cooldowns)):
        m = Msg(P, cmd, chat=P)
        upd = types.SimpleNamespace(message=m, effective_message=m, effective_user=m.from_user,
                                    effective_chat=m.chat, callback_query=None, get_bot=lambda: BOT)
        n = len(BOT.out)
        try:
            await fn(upd, ctx(P))
            err = None
        except Exception as e:
            err = e
        ok(err is None and len(BOT.out) > n, f"{cmd} в личке: {err!r}")

    print("12. В личке — «добавить в свой чат»")
    m = Msg(P, "/frogday", chat=P)
    await B.cmd_chat_only(types.SimpleNamespace(message=m, effective_chat=m.chat, effective_user=m.from_user),
                          ctx(P))
    ok(any("startgroup=add" in u for u in urls(BOT.out[-1][3])), "/frogday в личке — кнопка добавить бота в чат")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


try:
    asyncio.run(main())
except BaseException:
    import traceback
    traceback.print_exc()
    os._exit(2)
