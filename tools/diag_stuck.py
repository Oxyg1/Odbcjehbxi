"""
Почему у лягушек «застывают» параметры — разбор боевой базы. Только читает.

Запуск на сервере (из каталога бота):
    venv/bin/python tools/diag_stuck.py frog_game.db
    venv/bin/python tools/diag_stuck.py frog_game.db 123456789   # одна лягушка подробно
"""
import sqlite3
import sys
import time

STATS = ("hunger", "happiness", "cleanliness", "energy", "health")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    now = time.time()
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]

    if len(sys.argv) > 2:
        r = con.execute("SELECT * FROM frogs WHERE user_id=?", (int(sys.argv[2]),)).fetchone()
        if not r:
            sys.exit("нет такой лягушки")
        r = dict(r)
        for k in STATS:
            print(f"{k:12} {r.get(k)!r}  ({type(r.get(k)).__name__})")
        for k in ("alive", "onboard_step", "born_at", "last_decay", "decay_frac", "hibernation_until",
                  "last_seen", "subscription_type", "subscription_until", "subscription_auto",
                  "staya_id", "personality"):
            v = r.get(k)
            extra = ""
            if k in ("born_at", "last_decay", "hibernation_until", "last_seen", "subscription_until") and v:
                extra = f"  ({(now - float(v)) / 3600:+.1f} ч назад)" if float(v) <= now \
                    else f"  (В БУДУЩЕМ на {(float(v) - now) / 3600:.1f} ч)"
            print(f"{k:12} {v!r}{extra}")
        return

    alive = "alive=1"
    seen = f"{alive} AND last_seen>{now - 86400}"
    print(f"Живых: {q(f'SELECT COUNT(*) FROM frogs WHERE {alive}')}, "
          f"заходили за сутки: {q(f'SELECT COUNT(*) FROM frogs WHERE {seen}')}\n")
    rows = [
        ("знакомство не закончено (onboard_step>0)",
         f"{alive} AND onboard_step>0"),
        ("  …из них старше часа (затухание стояло)",
         f"{alive} AND onboard_step>0 AND COALESCE(born_at,0)<{now - 3600}"),
        ("отметка затухания в будущем",
         f"{alive} AND last_decay>{now + 60}"),
        ("анабиоз сейчас",
         f"{alive} AND hibernation_until>{now}"),
        ("заходили за сутки, а затухания не было больше суток",
         f"{seen} AND last_decay<{now - 86400}"),
        ("параметр больше 100",
         f"{alive} AND (" + " OR ".join(f"{s}>100" for s in STATS) + ")"),
        ("параметр не числом (строка/NULL)",
         f"{alive} AND (" + " OR ".join(f"typeof({s}) NOT IN ('integer','real')" for s in STATS) + ")"),
        ("Няня активна (держит до 85%)",
         f"{alive} AND subscription_type>=1 AND subscription_until>{now} AND subscription_auto=1"),
        ("здоровье 100 при сытости > 0 (так задумано)",
         f"{seen} AND health>=100 AND hunger>0"),
        ("  …из них в стае ур. 2+ (лечение стаи, до 23.10 — без условий)",
         f"{seen} AND health>=100 AND hunger>0 AND staya_id IN (SELECT id FROM stayas WHERE level>=2)"),
    ]
    for label, where in rows:
        n = q(f"SELECT COUNT(*) FROM frogs WHERE {where}")
        ids = [r[0] for r in con.execute(f"SELECT user_id FROM frogs WHERE {where} LIMIT 5")]
        print(f"{n:7}  {label}" + (f"   напр. {', '.join(map(str, ids))}" if n else ""))
    print("\nСколько у заходивших за сутки каждый параметр стоит ровно на 100:")
    for s in STATS:
        print(f"{q(f'SELECT COUNT(*) FROM frogs WHERE {seen} AND {s}>=100'):7}  {s}")

    # В базе лежит значение на момент последнего сохранения: затухание
    # применяется при заходе. Поэтому считаем, сколько было бы СЕЙЧАС, и
    # отдельно — у кого 100 в базе, хотя затухание прошло давно, а действия,
    # поднимающего этот параметр, давно не было. Вот это и есть «застрял».
    rate = {"hunger": 7.0, "happiness": 7.0, "cleanliness": 2.8, "energy": 2.1}
    act = {"hunger": ("last_feed", "last_fly_feed"), "happiness": ("last_play",),
           "cleanliness": ("last_wash",), "energy": ("last_sleep",)}
    cols = {r[1] for r in con.execute("PRAGMA table_info(frogs)")}
    print("\nСейчас (с учётом затухания) на 99–100 / из них подозрительных:")
    print("  подозрительно = в базе 100, затухание было > 2 ч назад, а поднимающего действия не было > 2 ч")
    rows = [dict(r) for r in con.execute(f"SELECT * FROM frogs WHERE {seen}")]
    for s, rt in rate.items():
        now_full, sus = 0, []
        for r in rows:
            v = float(r.get(s) or 0)
            hrs = max(0.0, (now - float(r.get("last_decay") or now)) / 3600)
            if v - rt * hrs >= 99:
                now_full += 1
            last_act = max([float(r.get(c) or 0) for c in act[s] if c in cols] or [0])
            if v >= 100 and hrs > 2 and now - last_act > 2 * 3600:
                sus.append(r["user_id"])
        print(f"{now_full:7} / {len(sus):<4} {s}" + (f"   напр. {', '.join(map(str, sus[:5]))}" if sus else ""))


if __name__ == "__main__":
    main()
