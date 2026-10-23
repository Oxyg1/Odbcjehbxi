"""
Здоровье падает от плохого ухода, а не только при нулевой сытости
(раньше у 81% активных игроков оно стояло на 100 вечно).

Запуск из корня репозитория:
    python3 tools/test_health.py
"""
import os, sys, tempfile, logging, time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="hp_test_"), "test.db")
os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, ROOT)
logging.disable(logging.CRITICAL)
import bot as B

FAILS = []
def ok(cond, what):
    if not cond:
        FAILS.append(what)
        print("  ✗", what)

B._get_today_weather = lambda: {}          # погода не должна влиять на проверку


def frog(**kw):
    f = {"user_id": 1, "alive": 1, "hunger": 100, "happiness": 100, "cleanliness": 100,
         "energy": 100, "health": 100, "last_decay": _time.time(), "decay_frac": "",
         "hibernation_until": 0, "born_at": 0, "onboard_step": 0, "personality": "", "staya_id": 0}
    f.update(kw)
    return f


def run_hours(f, hours, keep=None):
    """Прогнать затухание по часу; keep — параметры, которые игрок поддерживает."""
    for _ in range(hours):
        f["last_decay"] -= 3600
        f = B.decay(f)
        for k, v in (keep or {}).items():
            f[k] = max(f[k], v)
    return f


async def main():
    # decay() при смерти пишет журнал через create_task — нужен цикл
    print("1. Сколько отнимает уход")
    ok(B.health_drain(frog())[0] == 0, "всё в порядке — здоровье не падает")
    ok(B.health_drain(frog(hunger=50, cleanliness=31))[0] == 0, "выше 30 — не падает")
    r, why = B.health_drain(frog(hunger=20))
    ok(r == B.HEALTH_RATE_LOW and why == ["голодная"], f"сытость 20% — понемногу ({r}, {why})")
    r, why = B.health_drain(frog(cleanliness=5))
    ok(r == B.HEALTH_RATE_VERYLOW and why == ["грязная"], "грязь 5% — быстрее")
    r, why = B.health_drain(frog(hunger=0, energy=5))
    ok(r == B.DECAY_RATES["health"] and why == ["голодная", "устала"],
       "голод 0 — как раньше, не быстрее, но причины названы обе")
    r, _ = B.health_drain(frog(hunger=20, energy=5))
    ok(abs(r - (B.HEALTH_RATE_LOW + B.HEALTH_RATE_VERYLOW)) < 1e-9, "без нулевого голода — складываются")

    print("2. Время")
    f = run_hours(frog(), 48, keep={"hunger": 60, "happiness": 60, "cleanliness": 60, "energy": 60})
    ok(f["health"] == 100, f"заботливый игрок 2 суток — здоровье 100 ({f['health']})")
    f = run_hours(frog(), 24, keep={"hunger": 60})
    ok(f["health"] < 100, f"кормят, но не играют/не моют/не укладывают — падает ({f['health']})")
    ok(f["health"] > 50, f"и не обваливается за сутки ({f['health']})")
    f = run_hours(frog(health=40, hunger=25), 1)
    ok(f["health"] == 40, "меньше единицы за час — копится, не теряется")
    f = run_hours(f, 4)
    ok(f["health"] < 40, "…а за несколько часов списывается")
    f = run_hours(frog(), 36)
    ok(f["health"] > 0, f"брошенная лягушка за 36 ч ещё жива, как и раньше ({f['health']})")
    f = run_hours(f, 24)
    ok(f["health"] == 0, "а за 2,5 суток — нет")

    print("3. Подсказка в карточке")
    ok(B.health_note(frog()) == "", "всё хорошо — подсказки нет")
    n = B.health_note(frog(hunger=10, cleanliness=20))
    ok("голодная" in n and "грязная" in n, f"называет причины: {n}")
    ok(B.health_note(frog(hunger=0, alive=0)) == "", "мёртвой — не показываем")
    ok("Здоровье падает" in B.status_text({**B.decay(frog()), **frog(cleanliness=5), "skin": next(iter(B.SKINS)),
                                            "level": 1, "xp": 0, "coins": 0, "frog_name": "К"}),
       "в карточке лягушки подсказка видна")

    print()
    if FAILS:
        print(f"ОШИБОК: {len(FAILS)}")
        os._exit(1)
    print("ВСЁ ОК")
    os._exit(0)


import asyncio
asyncio.run(main())
