"""
Полоски статов из премиум-эмодзи: кусочки, сборка пака, карточка лягушки.

Запуск из корня репозитория:
    python3 tools/test_bars.py

Боевую базу и Telegram не трогает: временная база, поддельный бот.
"""
import os, sys, asyncio, re, types, tempfile, logging, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="bars_test_"), "test.db")
os.environ["DB_PATH"] = DB
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B
from PIL import Image
from telegram.error import BadRequest

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

TAG = re.compile(r"<(/?)(b|i|u|s|code|pre|a|blockquote|tg-emoji)(?:\s[^>]*)?>")
def check_html(text):
    stack = []
    for close, tag in TAG.findall(text):
        if close:
            assert stack and stack[-1] == tag, f"HTML: </{tag}> без пары:\n{text}"
            stack.pop()
        else:
            stack.append(tag)
    assert not stack, f"HTML: незакрыто {stack}:\n{text}"


class FakeBot:
    username = "frogbot"
    def __init__(self):
        self.sets = {}           # имя -> список (emoji, data)
        self.fail_at = None      # на каком по счёту add_sticker_to_set упасть
        self.adds = 0
        self.sent = []
    async def get_sticker_set(self, name):
        if name not in self.sets:
            raise BadRequest("Stickerset_invalid")
        return types.SimpleNamespace(stickers=[
            types.SimpleNamespace(custom_emoji_id=f"{9000 + i}") for i in range(len(self.sets[name]))])
    async def create_new_sticker_set(self, user_id, name, title, stickers, sticker_type=None, needs_repainting=None):
        assert name not in self.sets and name.endswith("_by_frogbot") and sticker_type == "custom_emoji"
        assert len(stickers) <= 50
        self.sets[name] = [self._check(s) for s in stickers]
        return True
    async def add_sticker_to_set(self, user_id, name, sticker):
        self.adds += 1
        if self.fail_at and self.adds == self.fail_at:
            raise BadRequest("Too Many Requests")
        assert len(self.sets[name]) < 200
        self.sets[name].append(self._check(sticker))
        return True
    async def delete_sticker_set(self, name):
        del self.sets[name]
        return True
    def _check(self, s):
        assert s.format == "static" and len(s.emoji_list) == 1
        data = getattr(s.sticker, "input_file_content", s.sticker)   # PTB заворачивает байты в InputFile
        return (s.emoji_list[0], data)


class Msg:
    def __init__(self):
        self.texts = []
    async def reply_text(self, text, **kw):
        self.texts.append(text)
        return self
    async def edit_text(self, text, parse_mode=None, **kw):
        if parse_mode:
            check_html(text)
        self.texts.append(text)
        return self


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)
    admin = 777
    B.ADMIN_IDS = {admin} if isinstance(B.ADMIN_IDS, set) else [admin]

    print("1. Кусочки на месте и подходят для эмодзи")
    order = B._bars_order()
    ok(len(order) == 144, f"кусочков 144, а не {len(order)}")
    for key, tile in order:
        p = os.path.join(B.BAR_DIR, key, f"{tile}.png")
        if not os.path.isfile(p):
            ok(False, f"нет файла {p}")
            continue
        im = Image.open(p)
        ok(im.size == (100, 100) and im.mode == "RGBA", f"{p}: {im.size} {im.mode}")
        ok(os.path.getsize(p) < 512 * 1024, f"{p}: больше 512 КБ")
    # полный и пустой отличаются, половина — левая часть от полного, правая от пустого
    f = Image.open(os.path.join(B.BAR_DIR, "food", "3f.png")).tobytes()
    e = Image.open(os.path.join(B.BAR_DIR, "food", "3e.png")).tobytes()
    ok(f != e, "полный и пустой кусочек одинаковые")

    print("2. Какие кусочки ставятся для значения")
    ok(B.bar_states(0) == ["0e"] + [f"{i}e" for i in range(1, 8)], "0% — все пустые")
    ok(B.bar_states(100) == [f"{i}f" for i in range(8)], "100% — все полные")
    ok(B.bar_states(50) == ["0f", "1f", "2f", "3f", "4e", "5e", "6e", "7e"], "50% — ровно половина")
    ok(B.bar_states(1)[0] == "0h", "1% — не пустая полоска")
    ok(B.bar_states(99)[-1] == "7h", "99% — не полная полоска")
    ok(B.bar_states(83) == ["0f", "1f", "2f", "3f", "4f", "5f", "6h", "7e"], f"83%: {B.bar_states(83)}")
    spec = importlib.util.spec_from_file_location("make_bars", os.path.join(ROOT, "tools", "make_bars.py"))
    try:
        mb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mb)
        ok(all(mb.bar_states(v) == B.bar_states(v) for v in range(0, 101)),
           "make_bars.bar_states и bot.bar_states считают одинаково")
    except ImportError:
        print("  · make_bars не проверен: нет numpy/scipy")

    print("3. Без пака — обычная полоска")
    B.BAR_EMOJI = {}
    ok(B.stat_bar("food", 50) == f"<code>{B.bar(50)}</code>", "без пака — █░ в <code>")

    print("4. Сборка пака: обрыв посередине и продолжение")
    bot = FakeBot()
    bot.fail_at = 40
    try:
        await B.bars_build(bot, admin)
        ok(False, "обрыв должен был выбросить ошибку")
    except BadRequest:
        pass
    name = "frogbars_by_frogbot"
    ok(len(bot.sets[name]) == 50 + 39, f"до обрыва в паке {len(bot.sets[name])}")
    bot.fail_at = None
    await B.bars_build(bot, admin)
    ok(len(bot.sets[name]) == 144, f"после продолжения в паке {len(bot.sets[name])}")
    # порядок: файл i-го по счёту кусочка = i-я наклейка
    k0, t0 = order[100]
    with open(os.path.join(B.BAR_DIR, k0, f"{t0}.png"), "rb") as fh:
        ok(bot.sets[name][100][1] == fh.read(), "кусочки загружены по порядку")
    ok(bot.sets[name][100][0] == B.BAR_EMOJI_OF[k0], "эмодзи кусочка — эмодзи его полоски")
    ok(B.BAR_EMOJI["xp"]["0f"] == "9000" and B.BAR_EMOJI["energy"]["7e"] == "9143", "номера по порядку")

    print("5. Карточка лягушки с полосками из эмодзи")
    await B.settle() if hasattr(B, "settle") else None
    import sqlite3
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO frogs(user_id, frog_name, first_name, alive, level, xp, hunger, happiness, "
                "health, cleanliness, energy, coins) VALUES(1,'Ква','Ква',1,42,8183,83,87,100,81,80,500)")
    con.commit(); con.close()
    f = await B.db_get(1)
    card = B.status_text(f)
    check_html(card)
    tiles = re.findall(r'<tg-emoji emoji-id="(9\d\d\d)">', card)
    ok(len(tiles) == 48, f"в карточке 6×8 кусочков, а не {len(tiles)}")
    ok("<code>" not in card.split("Уровень")[1], "в карточке не осталось старых полосок")
    ok(len(re.findall(r"<tg-emoji", card)) < 100, "премиум-эмодзи в карточке меньше 100")
    f["hibernation_until"] = B.time.time() + 3600
    frozen = B.status_text(f)
    check_html(frozen)
    ok(len(re.findall(r'emoji-id="9\d\d\d"', frozen)) == 24, "в анабиозе — 3 полоски")

    print("6. Перезапуск: номера берутся из базы")
    B.BAR_EMOJI = {}
    await B.bars_load()
    ok(B.BAR_EMOJI.get("health", {}).get("3h"), "после bars_load номера на месте")

    print("7. /adminbars: выкл, вкл, заново")
    upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=admin), message=Msg())
    await B.cmd_adminbars(upd, types.SimpleNamespace(args=["выкл"], bot=bot))
    ok(B.BAR_EMOJI == {} and "<code>" in B.status_text(f), "выкл — обычные полоски")
    await B.cmd_adminbars(upd, types.SimpleNamespace(args=["вкл"], bot=bot))
    ok(B.BAR_EMOJI.get("xp"), "вкл — снова эмодзи")
    m = Msg()
    upd2 = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=admin), message=m)
    await B.cmd_adminbars(upd2, types.SimpleNamespace(args=["заново"], bot=bot))
    ok(len(bot.sets[name]) == 144 and "готов" in m.texts[-1], "заново — пак пересобран")
    stranger = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=5), message=Msg())
    await B.cmd_adminbars(stranger, types.SimpleNamespace(args=[], bot=bot))
    ok(stranger.message.texts == [], "не админ — молчание")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


asyncio.get_event_loop().run_until_complete(main())
