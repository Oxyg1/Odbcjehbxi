"""
Массовые смерти: кто умер и вернуть лягушек тем, кто играет.

Повод — 23–24.10: правки затухания (знакомство больше не замораживает,
отметки в будущем, здоровье от плохого ухода) разом добили лягушек,
которые жили только благодаря этим ошибкам, а 24.10 бот 14 часов висел
без связи, продолжая списывать параметры, — игроки не могли покормить.

Только посмотреть (база не меняется):
    venv/bin/python tools/mass_death.py frog_game.db

Вернуть (бота на это время остановить — у него кэш лягушек):
    sudo systemctl stop frogbot
    sudo -u frogbot venv/bin/python tools/mass_death.py frog_game.db --revive --since 2026-10-23 --seen 30
    sudo systemctl start frogbot

--since    с какого дня (МСК) считать смерти
--seen     воскрешать, только если хозяин заходил за столько дней (0 — всех)
--outage   дни простоя для серий, через запятую (по умолчанию 2026-10-24)
"""
import argparse
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
REVIVED = {"alive": 1, "health": 80, "hunger": 70, "happiness": 70, "cleanliness": 70,
           "energy": 70, "overfeed_total": 0, "died_at": 0, "death_reason": ""}


def day_ts(day: str) -> float:
    return datetime.fromisoformat(day).replace(tzinfo=MSK).timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--since", default="2026-10-23")
    ap.add_argument("--seen", type=int, default=30)
    ap.add_argument("--revive", action="store_true")
    ap.add_argument("--outage", default="2026-10-24")
    a = ap.parse_args()

    now = time.time()
    since = day_ts(a.since)
    con = sqlite3.connect(a.db, timeout=30)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT user_id, frog_name, first_name, level, last_seen, died_at, death_reason, streak "
        "FROM frogs WHERE alive=0 AND died_at>=? AND COALESCE(banned,0)=0 AND COALESCE(is_bot,0)=0",
        (since,))]

    def bucket(r):
        d = (now - float(r["last_seen"] or 0)) / 86400
        return "до суток" if d < 1 else "1–7 дней" if d < 7 else "7–30 дней" if d < 30 else "больше 30"

    print(f"Умерло с {a.since}: {len(rows)}")
    by_day = {}
    for r in rows:
        k = (datetime.fromtimestamp(r["died_at"], MSK).date().isoformat(), bucket(r))
        by_day[k] = by_day.get(k, 0) + 1
    print("\nдень        хозяин заходил   смертей")
    for (d, b), n in sorted(by_day.items()):
        print(f"{d}  {b:15}  {n:7}")
    reasons = {}
    for r in rows:
        reasons[r["death_reason"] or "здоровье"] = reasons.get(r["death_reason"] or "здоровье", 0) + 1
    print("\nпричины:", ", ".join(f"{k} {v}" for k, v in reasons.items()))

    pick = [r for r in rows if r["death_reason"] != "overfeed"
            and (a.seen == 0 or now - float(r["last_seen"] or 0) < a.seen * 86400)]
    print(f"\nПод возврат (хозяин заходил за {a.seen or '∞'} дн, не переедание): {len(pick)}")
    for r in sorted(pick, key=lambda r: -float(r["last_seen"] or 0))[:15]:
        print(f"  {r['user_id']:>12}  {r['frog_name'] or r['first_name'] or '?':20}  ур. {r['level']}")

    if not a.revive:
        print("\nНичего не менял. Чтобы вернуть — добавь --revive (бот должен быть остановлен).")
        return

    sets = ", ".join(f"{k}=?" for k in REVIVED) + ", last_decay=?, decay_frac=''"
    for r in pick:
        con.execute(f"UPDATE frogs SET {sets} WHERE user_id=? AND alive=0",
                    (*REVIVED.values(), now, r["user_id"]))
    # Дни простоя: серия бонуса через них не сгорает (как после обычного простоя)
    row = con.execute("SELECT value FROM settings WHERE key='streak_outage_days'").fetchone()
    days = set(json.loads(row[0]) if row and row[0] else [])
    days |= {d.strip() for d in a.outage.split(",") if d.strip()}
    con.execute("INSERT OR REPLACE INTO settings VALUES('streak_outage_days', ?)", (json.dumps(sorted(days)),))
    con.commit()
    print(f"\nВозвращено: {len(pick)}. Дни простоя для серий: {', '.join(sorted(days))}")


if __name__ == "__main__":
    main()
