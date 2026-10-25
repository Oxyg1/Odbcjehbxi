"""
Бот в группах: только настоящее «ква», откат молча, ответы в 1–2 строки,
личное — кнопкой в личку с меткой чата, новичку — приглашение раз в сутки,
/top — квакеры чата, приветствие при добавлении.

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

class Msg:
    def __init__(self, uid, text, chat=CHAT):
        _mid[0] += 1
        self.chat = types.SimpleNamespace(id=chat, type="supergroup" if chat < 0 else "private", title="Тест", username="")
        self.text, self.message_id = text, _mid[0]
        self.from_user = types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}", is_bot=False,
                                               last_name="", language_code="ru", is_premium=False)
        self.reply_to_message = self.sticker = self.dice = self.caption = self.photo = None
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

async def say(uid, text, handler=None, chat=CHAT):
    """Сообщение в группу; команды — сначала через перехватчик, как в боте."""
    m = Msg(uid, text, chat)
    upd = types.SimpleNamespace(message=m, effective_message=m, effective_user=m.from_user,
                                effective_chat=m.chat, callback_query=None, get_bot=lambda: BOT)
    n = len(BOT.out)
    stopped = False
    if text.startswith("/"):
        try:
            await asyncio.create_task(B.group_cmd_router(upd, ctx(uid)))
        except ApplicationHandlerStop:
            stopped = True
    if not stopped:
        await asyncio.create_task((handler or B.on_message)(upd, ctx(uid)))
    await asyncio.sleep(0.05)
    out = BOT.out[n:]
    if os.environ.get("SHOW"):
        print(f"\n>>> [{uid}] {text}")
        for kind, cid, t, kb in out:
            print(f"  <{kind}> " + plain(t).replace("\n", "\n    "))
            if kb:
                print("    [" + "] [".join(b.text for r in kb.inline_keyboard for b in r) + "]")
    return out, stopped

def lines(t):
    return plain(t).strip().count("\n") + 1

def urls(kb):
    return [b.url for r in kb.inline_keyboard for b in r if b.url] if kb else []


async def make_frog(uid, **fields):
    user = types.SimpleNamespace(id=uid, first_name=f"U{uid}", username=f"u{uid}", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    await asyncio.sleep(0.2)
    sets = {"onboard_step": 0, "frog_name": f"Ква{uid}", "level": 12, "last_decay": _time.time(), **fields}
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
    P, N = 11, 22
    await make_frog(P)

    print("1. Какие слова — «ква»")
    for w in ("ква", "Квак!", "кваааа", "ква-ква", "ну ква всем"):
        ok(B.is_kva(w), f"«{w}» — ква")
    for w in ("квартира", "квас", "Кваквордл", "квадрат", "акваланг"):
        ok(not B.is_kva(w), f"«{w}» — не ква")

    print("2. Ква в группе: коротко, повтор — молча")
    out, _ = await say(P, "ква")
    ok(len(out) == 1 and out[0][0] == "reply", "один ответ")
    ok(lines(out[0][2]) <= 2, f"не больше двух строк: {plain(out[0][2])!r}")
    out, _ = await say(P, "ква")
    ok(len(out) == 1 and out[0][0] == "reaction", f"откат — реакция, не сообщение: {out}")
    for w in ("квартира на продажу", "квас холодный", "играю в Кваквордл"):
        out, _ = await say(P, w)
        ok(not out, f"«{w}» — бот молчит")
    con = sqlite3.connect(DB)
    ok(con.execute("SELECT n FROM chat_kva WHERE chat_id=? AND user_id=?", (CHAT, P)).fetchone() == (1,),
       "ква засчитано чату")
    con.close()

    print("3. Новичок пишет «ква» — приглашение раз в сутки, со ссылкой на чат")
    out, _ = await say(N, "ква")
    ok(len(out) == 1 and any(f"start=chat_{CHAT}" in u for u in urls(out[0][3])), f"приглашение с меткой чата: {out}")
    out, _ = await say(N, "ква")
    ok(not out, "второй раз за сутки — молча")

    print("4. Команды в группе — коротко, личное — в личку")
    for cmd in ("/frog", "/start", "/mystats"):
        out, stopped = await say(P, cmd)
        ok(stopped and len(out) == 1 and lines(out[0][2]) <= 2, f"{cmd}: карточка в 2 строки ({out and plain(out[0][2])!r})")
        ok(any(f"start=chat_{CHAT}" in u for u in urls(out[0][3])), f"{cmd}: кнопка в личку с меткой чата")
    out, stopped = await say(N, "/start")
    ok(stopped and "нет лягушки" in plain(out[0][2]), "новичку /start в группе — без знакомства в чате")
    out, stopped = await say(P, "/daily")
    grp = [o for o in out if o[1] == CHAT]
    ok(stopped and len(grp) == 1 and lines(grp[0][2]) == 1, f"/daily — одна строка: {grp}")
    out, _ = await say(P, "/help")
    ok(lines(out[0][2]) <= 9, "помощь для группы — короткая")
    for cmd in ("/games", "/casino", "/staya", "/expedition"):
        out, stopped = await say(P, cmd)
        ok(stopped and len(out) == 1 and lines(out[0][2]) == 1 and urls(out[0][3]), f"{cmd} — одной строкой в личку")
    out, _ = await say(P, "/top")
    ok("Квакеры чата" in plain(out[0][2]) and "Ква11" in plain(out[0][2]), "/top — квакеры чата")
    out, stopped = await say(P, "/frog@otherbot", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped and not out, "команда другому боту — не наша")
    out, stopped = await say(P, "/duel", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped, "игры на двоих идут своими обработчиками")

    print("5. Режимы чата уважаются")
    await B.save_chat_settings(CHAT, mode="vanilla")
    B._chat_settings_cache.invalidate(CHAT)
    out, stopped = await say(P, "/frog", handler=lambda u, c: asyncio.sleep(0))
    ok(not stopped, "в «ванильном» режиме чата — его собственные правила")
    await B.save_chat_settings(CHAT, mode="full")
    B._chat_settings_cache.invalidate(CHAT)

    print("6. Приветствие при добавлении в группу")
    BOT.out.clear()
    ev = types.SimpleNamespace(
        chat=types.SimpleNamespace(id=-100888, type="supergroup", username="", title="Новый чат"),
        old_chat_member=types.SimpleNamespace(status="left"),
        new_chat_member=types.SimpleNamespace(status="member"),
        from_user=types.SimpleNamespace(id=P))
    await B.on_my_chat_member(types.SimpleNamespace(my_chat_member=ev), ctx(P))
    hello = [o for o in BOT.out if o[1] == -100888]
    ok(len(hello) == 1 and "ква" in plain(hello[0][2]).lower(), "сразу короткое приветствие, без /activate")
    ok(lines(hello[0][2]) <= 6 and any("start=chat_-100888" in u for u in urls(hello[0][3])), "с кнопкой и меткой чата")

    print("7. В личке — «добавить в свой чат»")
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    ok("?startgroup=add" in src, "кнопка добавления в чат есть")

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
