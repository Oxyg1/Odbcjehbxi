"""
Опросы-рассылки на тестовой базе: конструктор, ввод с HTML и премиум-эмодзи,
предпросмотр, аудитория, отправка с продолжением после перезапуска,
голосование (один, несколько, без смены ответа), награда, закрытие по кнопке
и по сроку, итоги.

Запуск из корня репозитория:
    python3 tools/test_polls.py

Боевую базу и Telegram не трогает.
"""
import os, sys, asyncio, re, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="poll_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B
from telegram.error import BadRequest, Forbidden
from telegram.ext import ApplicationHandlerStop

ADMIN = 1
B.ADMIN_IDS = {ADMIN} if isinstance(B.ADMIN_IDS, set) else [ADMIN]
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

def kb_rows(kb):
    return [[(b.text, b.callback_data, b.to_dict().get("icon_custom_emoji_id"), b.to_dict().get("style"))
             for b in row] for row in kb.inline_keyboard] if kb else []

def cbs(kb):
    return [c for row in kb_rows(kb) for _, c, _, _ in row]


class Sent:
    def __init__(self, mid): self.message_id = mid

class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.mid = 100
        self.sent = []            # (chat, kind, text, kb)
        self.edits = []           # (chat, mid, kb)
        self.docs = []
        self.blocked = set()
        self.parse_fail = False
    def _check(self, chat, text):
        if chat in self.blocked:
            raise Forbidden("bot was blocked by the user")
        if self.parse_fail:
            raise BadRequest("Can't parse entities: unsupported start tag")
        check_html(text)
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self._check(chat_id, text)
        self.mid += 1
        self.sent.append((chat_id, "text", text, reply_markup))
        return Sent(self.mid)
    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None, **kw):
        self._check(chat_id, caption)
        self.mid += 1
        self.sent.append((chat_id, "photo", caption, reply_markup))
        return Sent(self.mid)
    async def edit_message_reply_markup(self, chat_id=None, message_id=None, reply_markup=None, **kw):
        self.edits.append((chat_id, message_id, reply_markup))
    async def edit_message_text(self, text, chat_id=None, message_id=None, **kw):
        pass
    async def send_document(self, chat_id, document=None, filename=None, caption=None, **kw):
        self.docs.append((chat_id, filename, document.getvalue().decode("utf-8")))
    def to(self, uid):
        return [e for e in self.sent if e[0] == uid]


class Msg:
    """Сообщение-экран, на котором нажимают кнопки."""
    def __init__(self, chat=ADMIN, mid=1):
        self.chat = types.SimpleNamespace(id=chat, type="private")
        self.message_id = mid
        self.screens = []         # (text, kb)
        self.replies = []
        self.markups = []
    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.screens.append((text, reply_markup))
    async def edit_reply_markup(self, reply_markup=None, **kw):
        self.markups.append(reply_markup)
    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kw):
        if parse_mode:
            check_html(text)
        self.replies.append((text, reply_markup))
        return self
    @property
    def last(self):
        return (self.replies + self.screens)[-1] if (self.replies or self.screens) else ("", None)


class Q:
    def __init__(self, uid, data, msg):
        self.from_user = types.SimpleNamespace(id=uid)
        self.data, self.message, self.answers = data, msg, []
    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


def in_msg(text=None, html=None, photo=None, caption=None, caption_html=None):
    """Входящее сообщение админа: text_html — то, что отдал бы Telegram."""
    m = Msg()
    m.text, m.caption = text, caption
    m.text_html = html if html is not None else (B._html.escape(text) if text else None)
    m.caption_html = caption_html if caption_html is not None else (B._html.escape(caption) if caption else None)
    m.photo = [types.SimpleNamespace(file_id=photo)] if photo else None
    return m


BOT = FakeBot()
CTX = types.SimpleNamespace(bot=BOT, user_data={})
SCREEN = Msg()

async def press(data, uid=ADMIN, msg=None):
    q = Q(uid, data, msg or SCREEN)
    router = B.poll_admin_router if data.startswith("pla|") else B.poll_vote_router
    await router(types.SimpleNamespace(callback_query=q), CTX)
    return q

async def send_input(m):
    upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=ADMIN), message=m)
    try:
        await B.poll_input(upd, CTX)
        return False
    except ApplicationHandlerStop:
        return True

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


async def wait_tasks():
    for t in list(B._POLL_TASKS.values()):
        await t


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    now = _time.time()
    # 60 игроков: 1–40 заходили сегодня, 41–50 неделю назад, 51–58 месяц назад,
    # 59 забанен, 60 — бот; 55–58 мёртвые
    for uid in range(1, 61):
        seen = now - (3600 if uid <= 40 else 5 * 86400 if uid <= 50 else 25 * 86400)
        x("INSERT INTO frogs(user_id, first_name, frog_name, alive, last_seen, banned, is_bot, coins) "
          "VALUES(?,?,?,?,?,?,?,100)", uid, f"P{uid}", f"P{uid}", 0 if 55 <= uid <= 58 else 1, seen,
          1 if uid == 59 else 0, 1 if uid == 60 else 0)

    print("1. Аудитория")
    ok(await B.poll_audience_count("all") == 58, "все игроки без банов и ботов — 58")
    ok(await B.poll_audience_count("alive") == 54, "живые — 54")
    ok(await B.poll_audience_count("d1") == 40, "за сутки — 40")
    ok(await B.poll_audience_count("d7") == 50, "за неделю — 50")
    ok(await B.poll_audience_count("d30") == 58, "за месяц — 58")

    print("2. Черновик и текст с HTML и премиум-эмодзи")
    await press("pla|list")
    await press("pla|new")
    pid = q("SELECT MAX(id) FROM polls")[0][0]
    ok(q("SELECT status FROM polls WHERE id=?", pid) == [("draft",)], "создан черновик")
    await press(f"pla|in|{pid}|text")
    ok(CTX.user_data.get("poll_in", {}).get("what") == "text", "ждём текст")
    # Telegram отдал: премиум-эмодзи тегом, руками набранные теги — экранированными
    html_in = ('<tg-emoji emoji-id="5368">🐸</tg-emoji> &lt;b&gt;Какой режим&lt;/b&gt; добавить? '
               '5 &lt; 6 &amp; <i>курсив</i> &lt;a href=&quot;https://t.me/x?a=1&amp;b=2&quot;&gt;ссылка&lt;/a&gt;')
    stopped = await send_input(in_msg("x", html=html_in))
    ok(stopped, "ввод остановил общий обработчик")
    t = q("SELECT text FROM polls WHERE id=?", pid)[0][0]
    ok('<tg-emoji emoji-id="5368">' in t, "премиум-эмодзи в тексте сохранились")
    ok("<b>Какой режим</b>" in t, "набранные руками теги стали тегами")
    ok("5 &lt; 6 &amp;" in t, "одиночные < и & остались экранированными")
    ok('<a href="https://t.me/x?a=1&amp;b=2">ссылка</a>' in t, "ссылка с параметрами")
    check_html(t)
    ok("poll_in" not in CTX.user_data, "режим ввода снят")
    # битый HTML не принимается
    await press(f"pla|in|{pid}|text")
    stopped = await send_input(in_msg("x", html="&lt;b&gt;без закрытия"))
    ok(stopped and "poll_in" in CTX.user_data, "битый тег — ошибка, ввод ждёт дальше")
    ok(q("SELECT text FROM polls WHERE id=?", pid)[0][0] == t, "битый текст не записан")
    await press(f"pla|ed|{pid}")
    ok("poll_in" not in CTX.user_data, "отмена снимает режим ввода")
    # без режима ввода сообщение админа идёт дальше, в игру
    ok(not await send_input(in_msg("просто текст")), "без режима ввода не перехватываем")

    print("3. Варианты: несколько строк, иконки, цвет, порядок")
    await press(f"pla|in|{pid}|opt")
    await send_input(in_msg("x", html='<tg-emoji emoji-id="777">🗺</tg-emoji> Экспедиции\nБега\n\n  Квиз  '))
    opts = B.json.loads(q("SELECT options FROM polls WHERE id=?", pid)[0][0])
    ok([o["t"] for o in opts] == ["Экспедиции", "Бега", "Квиз"], f"варианты: {opts}")
    ok(opts[0]["icon"] == "777" and opts[1]["icon"] == "", "премиум-эмодзи в начале строки — иконка")
    await press(f"pla|sty|{pid}|1")
    await press(f"pla|mv|{pid}|2|-1")
    opts = B.json.loads(q("SELECT options FROM polls WHERE id=?", pid)[0][0])
    ok(opts[1]["t"] == "Квиз" and opts[2]["t"] == "Бега" and opts[2]["style"] == "primary", "цвет и порядок")
    pal = B.poll_palette()
    ok(len(pal) > 50, f"палитра иконок из бота: {len(pal)}")
    await press(f"pla|ico|{pid}|1|1")
    ok(any(r for r in kb_rows(SCREEN.last[1]) if r[0][2]), "в палитре кнопки с иконками")
    await press(f"pla|icoset|{pid}|1|5")
    ok(B.json.loads(q("SELECT options FROM polls WHERE id=?", pid)[0][0])[1]["icon"] == pal[5], "иконка из палитры")
    await press(f"pla|in|{pid}|icon|2")
    await send_input(in_msg("x", html="🙂 обычный"))
    ok("poll_in" in CTX.user_data, "обычный эмодзи вместо премиум — просим ещё")
    await send_input(in_msg("x", html='<tg-emoji emoji-id="999">🏃</tg-emoji>'))
    ok(B.json.loads(q("SELECT options FROM polls WHERE id=?", pid)[0][0])[2]["icon"] == "999", "своя иконка")
    await press(f"pla|in|{pid}|edit|2")
    await send_input(in_msg("Лягушачьи бега"))
    o2 = B.json.loads(q("SELECT options FROM polls WHERE id=?", pid)[0][0])[2]
    ok(o2["t"] == "Лягушачьи бега" and o2["icon"] == "999", "правка текста не теряет иконку")

    print("4. Настройки и аудитория")
    await press(f"pla|tg|{pid}|reward")
    await press(f"pla|tg|{pid}|reward")      # 0 → 10 → 25
    await press(f"pla|tg|{pid}|anon")
    await press(f"pla|auds|{pid}|d7")
    p = await B.poll_load(pid)
    ok(p["settings"]["reward"] == 25 and p["settings"]["anon"] is False and p["audience"] == "d7", "настройки")
    text, kb = await B.poll_editor_view(p)
    check_html(text)
    ok("50" in text, "в редакторе — число получателей")

    print("5. Предпросмотр")
    n0 = len(BOT.sent)
    await press(f"pla|prev|{pid}")
    prev = BOT.sent[-1]
    ok(len(BOT.sent) == n0 + 1 and prev[0] == ADMIN, "предпросмотр пришёл админу")
    ok(all(c.endswith("|p") for c in cbs(prev[3])), "кнопки предпросмотра помечены")
    ok(kb_rows(prev[3])[0][0][2] == "777", "иконка на кнопке у игрока")
    pm = Msg(mid=500)
    await press(f"plv|{pid}|0|p", msg=pm)
    ok(q("SELECT COUNT(*) FROM poll_votes")[0][0] == 0, "голос в предпросмотре не засчитан")
    ok(pm.markups and "✅" in kb_rows(pm.markups[-1])[0][0][0], "предпросмотр показывает вид после голоса")

    print("6. Отправка: заблокировавшие, продолжение после перезапуска")
    BOT.blocked = {3, 45}
    await press(f"pla|send|{pid}")
    await press(f"pla|go|{pid}")
    await wait_tasks()
    ok(q("SELECT status FROM polls WHERE id=?", pid) == [("open",)], "опрос идёт")
    st = dict(q("SELECT state, COUNT(*) FROM poll_sent WHERE poll_id=? GROUP BY state", pid))
    ok(st == {"ok": 48, "blocked": 2}, f"доставка: {st}")
    ok(all(len(BOT.to(u)) <= 2 for u in range(2, 61)), "никому не ушло дважды")
    q2 = await press(f"pla|go|{pid}")
    ok(q2.answers and "менять нельзя" in (q2.answers[-1][0] or ""), "повторная отправка отказана")
    ok(any("разослан" in (e[2] or "") for e in BOT.sent if e[0] == ADMIN), "админу пришёл итог отправки")

    print("7. Голоса")
    def m_of(uid):
        return Msg(chat=uid, mid=1000 + uid)
    m5 = m_of(5)
    await press(f"plv|{pid}|0", uid=5, msg=m5)
    ok(q("SELECT opt FROM poll_votes WHERE poll_id=? AND user_id=5", pid) == [(0,)], "голос записан")
    ok(q("SELECT coins FROM frogs WHERE user_id=5")[0][0] == 125, "награда 25")
    rows = kb_rows(m5.markups[-1])
    ok(rows[0][0][0].startswith("✅ Экспедиции") and "100%" in rows[0][0][0], f"✅ и проценты: {rows[0][0][0]}")
    ok(rows[-1][0][0] == "Ответили: 1", "строка «ответили»")
    await press(f"plv|{pid}|1", uid=5, msg=m5)
    ok(q("SELECT opt FROM poll_votes WHERE poll_id=? AND user_id=5", pid) == [(1,)], "ответ поменян")
    ok(q("SELECT coins FROM frogs WHERE user_id=5")[0][0] == 125, "награда не повторилась")
    for u in (6, 7, 8):
        await press(f"plv|{pid}|2", uid=u, msg=m_of(u))
    counts, voters = await B.poll_tally(pid)
    ok(voters == 4 and counts == {1: 1, 2: 3}, f"подсчёт: {counts} {voters}")
    await press(f"plv|{pid}|0", uid=57, msg=m_of(57))
    ok(q("SELECT coins FROM frogs WHERE user_id=57")[0][0] == 100, "не получателю награды нет")
    text, kb = await B.poll_results_view(await B.poll_load(pid))
    check_html(text)
    ok("Ответили <b>5</b>" in text and "Дошло <b>48</b>" in text, "итоги для админа")
    await press(f"pla|txt|{pid}")
    ok("Квиз: 1" in BOT.sent[-1][2], "итоги текстом")
    await press(f"pla|who|{pid}")
    ok(BOT.docs and "P6" in BOT.docs[-1][2], "кто как ответил — файлом")
    q3 = await press(f"pla|tg|{pid}|multi")
    ok("менять нельзя" in (q3.answers[-1][0] or ""), "разосланный опрос не редактируется")
    q4 = await press(f"pla|list", uid=77)
    ok(q4.answers[-1] == ("⛔", True), "чужой в админку опросов не попадает")

    print("8. Закрытие: кнопки у получателей меняются на итоги")
    n_edits = len(BOT.edits)
    await press(f"pla|close|{pid}")
    await press(f"pla|closego|{pid}")
    await wait_tasks()
    ok(q("SELECT status FROM polls WHERE id=?", pid) == [("closed",)], "закрыт")
    fin = BOT.edits[n_edits:]
    ok(len(fin) == 48, f"итоги поставлены всем получившим: {len(fin)}")
    e5 = next(e for e in fin if e[0] == 5)
    ok("✅" in kb_rows(e5[2])[1][0][0] and all(c.endswith("|x") for c in cbs(e5[2])), "у голосовавшего — его выбор")
    m9 = m_of(9)
    q5 = await press(f"plv|{pid}|0", uid=9, msg=m9)
    ok(q5.answers[-1] == ("Опрос закрыт", True), "после закрытия голосовать нельзя")
    ok(q("SELECT COUNT(*) FROM poll_votes WHERE poll_id=? AND user_id=9", pid)[0][0] == 0, "голос не записан")

    print("9. Один ответ без смены, несколько ответов, итоги не показывать, срок")
    await press(f"pla|copy|{pid}")
    pid2 = q("SELECT MAX(id) FROM polls")[0][0]
    p2 = await B.poll_load(pid2)
    ok(p2["status"] == "draft" and len(p2["options"]) == 3, "копия в черновик")
    s = p2["settings"]
    s.update(revote=False, show="never", hours=6, reward=0)
    await B.poll_update(pid2, settings=s, audience="d1")
    await press(f"pla|go|{pid2}")
    await wait_tasks()
    await press(f"plv|{pid2}|0", uid=10, msg=m_of(10))
    q6 = await press(f"plv|{pid2}|1", uid=10, msg=m_of(10))
    ok(q6.answers[-1][0] == "Ответ уже принят, поменять нельзя", "без смены ответа")
    m11 = m_of(11)
    await press(f"plv|{pid2}|1", uid=11, msg=m11)
    ok(not any("%" in t for t, *_ in kb_rows(m11.markups[-1])[0]), "итоги не показываются")
    s["multi"] = True
    await B.poll_update(pid2, settings=s)
    m12 = m_of(12)
    await press(f"plv|{pid2}|0", uid=12, msg=m12)
    await press(f"plv|{pid2}|2", uid=12, msg=m12)
    await press(f"plv|{pid2}|0", uid=12, msg=m12)
    ok(q("SELECT opt FROM poll_votes WHERE poll_id=? AND user_id=12", pid2) == [(2,)], "несколько: выбор и снятие")
    # срок вышел
    x("UPDATE polls SET closes_at=? WHERE id=?", _time.time() - 1, pid2)
    n_edits = len(BOT.edits)
    await B.job_poll_tick(types.SimpleNamespace(bot=BOT))
    await wait_tasks()
    ok(q("SELECT status FROM polls WHERE id=?", pid2) == [("closed",)], "закрыт по сроку")
    ok(all(e[2] is None for e in BOT.edits[n_edits:]) and len(BOT.edits) > n_edits,
       "итоги не показываем — кнопки убраны")

    print("10. Перезапуск посреди отправки — без повторов")
    await press(f"pla|copy|{pid}")
    pid3 = q("SELECT MAX(id) FROM polls")[0][0]
    await B.poll_update(pid3, status="sending", sent_at=_time.time())
    x("INSERT INTO poll_sent(poll_id, user_id, state, msg_id) SELECT ?, user_id, "
      "CASE WHEN user_id<=20 THEN 'ok' ELSE 'wait' END, CASE WHEN user_id<=20 THEN 1 ELSE 0 END "
      "FROM frogs WHERE banned=0 AND is_bot=0", pid3)
    before = {u: len(BOT.to(u)) for u in range(1, 61)}
    await B.poll_resume(BOT)
    await wait_tasks()
    got = [u for u in range(2, 61) if len(BOT.to(u)) > before[u]]     # 1 — админ, ему итог
    ok(got and min(got) == 21 and all(len(BOT.to(u)) - before[u] == 1 for u in got),
       "дослано только тем, кому не ушло, и по одному разу")
    ok(q("SELECT status FROM polls WHERE id=?", pid3) == [("open",)], "после досылки опрос идёт")

    print("11. Telegram не разобрал текст — опрос возвращается в черновик")
    await press(f"pla|copy|{pid}")
    pid4 = q("SELECT MAX(id) FROM polls")[0][0]
    BOT.parse_fail = True
    await press(f"pla|go|{pid4}")
    await wait_tasks()
    BOT.parse_fail = False
    ok(q("SELECT status FROM polls WHERE id=?", pid4) == [("draft",)], "вернулся в черновик")
    ok(q("SELECT COUNT(*) FROM poll_sent WHERE poll_id=? AND state='wait'", pid4)[0][0] > 0, "получатели ждут")

    print("12. Удаление черновика и экраны")
    await press(f"pla|new")
    pid5 = q("SELECT MAX(id) FROM polls")[0][0]
    q7 = await press(f"pla|prev|{pid5}")
    ok("Нет ни текста" in q7.answers[-1][0], "пустой опрос не отправить")
    await press(f"pla|delgo|{pid5}")
    ok(q("SELECT COUNT(*) FROM polls WHERE id=?", pid5)[0][0] == 0, "черновик удалён")
    for v in (await B.poll_list_view(), B.poll_settings_view(await B.poll_load(pid)),
              await B.poll_audience_view(await B.poll_load(pid)), B.poll_options_view(await B.poll_load(pid)),
              B.poll_option_view(await B.poll_load(pid), 0), B.poll_icon_view(await B.poll_load(pid), 0, 0)):
        check_html(v[0])
    ok(True, "")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


asyncio.get_event_loop().run_until_complete(main())
