"""
Параметры «застревали на 100%»: брошенное знакомство навсегда отключало
затухание (onboard_step > 0). Проверка, что через час после рождения
параметры падают, а флаг снимается и при старте бота.

Запуск из корня репозитория:
    python3 tools/test_onboard_decay.py
"""
import os, sys, asyncio, types, tempfile, logging, sqlite3, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(tempfile.mkdtemp(prefix="ob_test_"), "test.db")
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


def base(**kw):
    now = _time.time()
    f = {"user_id": 1, "alive": 1, "hunger": 100, "happiness": 100, "cleanliness": 100,
         "energy": 100, "health": 100, "last_decay": now - 5 * 3600, "decay_frac": "",
         "hibernation_until": 0, "born_at": now - 2 * 86400, "onboard_step": 0, "first_time": 0}
    f.update(kw)
    return f


async def main():
    B.run_sync_migration()
    await B.init_db()
    B.run_sync_migration()
    B._db_pool.init(size=2)

    print("1. Затухание и знакомство")
    f = B.decay(base(onboard_step=0))
    ok(f["hunger"] < 100 and f["happiness"] < 100, "обычная лягушка: за 5 ч параметры упали")
    f = B.decay(base(onboard_step=1, born_at=_time.time() - 600))
    ok(f["hunger"] == 100 and f["onboard_step"] == 1, "идёт знакомство (10 мин) — стоят, флаг на месте")
    f = B.decay(base(onboard_step=1))
    ok(f["hunger"] < 100 and f["energy"] < 100, "знакомство брошено 2 дня назад — параметры падают")
    ok(f["onboard_step"] == 0 and f["first_time"] == 0, "и флаг снят")
    for step in (2, 3, 4):
        f = B.decay(base(onboard_step=step))
        ok(f["hunger"] < 100, f"брошено на шаге {step} — тоже падают")
    # Тот самый случай: снизили вручную, накормили до 100 — и опять встало
    f = base(onboard_step=1, hunger=40)
    f = B.decay(f)
    f["hunger"] = 100
    f["last_decay"] = _time.time() - 3 * 3600
    f = B.decay(f)
    ok(f["hunger"] < 100, "после кормления до 100 снова падает")

    print("1б. Отметка затухания в будущем")
    f = base(last_decay=_time.time() + 30 * 86400)
    f = B.decay(f)
    ok(abs(f["last_decay"] - _time.time()) < 5, "отметку из будущего вернули в настоящее")
    f["last_decay"] = _time.time() - 3 * 3600
    f = B.decay(f)
    ok(f["hunger"] < 100, "и дальше параметры падают")

    print("2. Снятие флага при старте")
    user = types.SimpleNamespace(id=7, first_name="Т", username="", last_name="",
                                 language_code="ru", is_bot=False)
    await B.new_frog(user)
    await B.new_frog(types.SimpleNamespace(id=8, first_name="Н", username="", last_name="",
                                           language_code="ru", is_bot=False))
    await asyncio.sleep(0.2)
    con = sqlite3.connect(DB, timeout=30)
    con.execute("UPDATE frogs SET onboard_step=1, born_at=? WHERE user_id=7", (_time.time() - 86400,))
    con.execute("UPDATE frogs SET onboard_step=1, born_at=? WHERE user_id=8", (_time.time() - 60,))
    con.execute("UPDATE frogs SET last_decay=? WHERE user_id=8", (_time.time() + 86400 * 90,))
    con.commit()
    con.close()
    B.run_sync_migration()
    con = sqlite3.connect(DB, timeout=30)
    rows = dict(con.execute("SELECT user_id, onboard_step FROM frogs WHERE user_id IN (7,8)").fetchall())
    con.close()
    ok(rows.get(7) == 0, "застрявший сутки назад — флаг снят")
    ok(rows.get(8) == 1, "новичок, который знакомится прямо сейчас, — не тронут")
    con = sqlite3.connect(DB, timeout=30)
    ld = con.execute("SELECT last_decay FROM frogs WHERE user_id=8").fetchone()[0]
    con.close()
    ok(ld <= _time.time() + 1, "отметка из будущего исправлена при старте")

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
