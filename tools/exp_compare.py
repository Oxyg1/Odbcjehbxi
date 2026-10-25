"""
Экспедиции до и после обновления 4 октября — по неделям.

Старые лежат в expeditions / expedition_members (код удалён, таблицы
остались), новые — в ex_runs / ex_members. База не меняется.

    venv/bin/python tools/exp_compare.py frog_game.db
    venv/bin/python tools/exp_compare.py frog_game.db --weeks 12

Колонки:
  вышли     — экспедиций, которые реально стартовали (не отменённый сбор)
  игроков   — разных людей за неделю
  участий   — сумма составов (один человек в трёх походах = 3)
  команда   — средний состав
  сборов    — сколько раз открывали сбор, включая отменённые
  доля DAU  — игроков от заходивших за неделю (есть с 5 октября)
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
SWITCH = datetime(2026, 10, 4, tzinfo=MSK).timestamp()


def week_of(ts: float) -> str:
    y, w, _ = datetime.fromtimestamp(ts, MSK).isocalendar()
    return f"{y}-{w:02d}"


def week_start(wk: str) -> str:
    y, w = map(int, wk.split("-"))
    return datetime.fromisocalendar(y, w, 1).strftime("%d.%m")


def has(con, table: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def collect(con, runs_sql: str, lobbies_sql: str, since: float) -> dict:
    """{неделя: {вышли, игроков, участий, сборов}}"""
    out = {}
    people = {}
    for run_id, ts, uid in con.execute(runs_sql, (since,)):
        wk = week_of(ts)
        b = out.setdefault(wk, {"runs": set(), "part": 0, "lob": 0})
        b["runs"].add(run_id)
        if uid is not None:
            b["part"] += 1
            people.setdefault(wk, set()).add(uid)
    for (ts,) in con.execute(lobbies_sql, (since,)):
        out.setdefault(week_of(ts), {"runs": set(), "part": 0, "lob": 0})["lob"] += 1
    return {wk: {"runs": len(b["runs"]), "people": len(people.get(wk, ())), "part": b["part"], "lob": b["lob"]}
            for wk, b in out.items()}


def dau_people(con, since: float) -> dict:
    """{неделя: разных заходивших} — из сбора статистики (есть с 5 октября)."""
    if not has(con, "st_active"):
        return {}
    res = {}
    day0 = datetime.fromtimestamp(since, MSK).date().isoformat()
    for day, uid in con.execute("SELECT day, user_id FROM st_active WHERE day>=?", (day0,)):
        wk = week_of(datetime.fromisoformat(day).replace(tzinfo=MSK).timestamp())
        res.setdefault(wk, set()).add(uid)
    return {wk: len(s) for wk, s in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--weeks", type=int, default=10, help="сколько недель до обновления показать")
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=30)
    since = SWITCH - a.weeks * 7 * 86400

    old = {}
    if has(con, "expeditions"):
        old = collect(
            con,
            "SELECT e.id, e.started_at, m.user_id FROM expeditions e "
            "LEFT JOIN expedition_members m ON m.expedition_id=e.id "
            "WHERE e.started_at>=? AND e.started_at>0",
            "SELECT gather_until FROM expeditions WHERE gather_until>=?", since)
    else:
        print("Таблицы старых экспедиций нет — сравнивать не с чем.")
    new = {}
    if has(con, "ex_runs"):
        new = collect(
            con,
            "SELECT r.id, r.started_at, m.user_id FROM ex_runs r "
            "LEFT JOIN ex_members m ON m.run_id=r.id "
            "WHERE r.started_at>=? AND r.started_at>0 AND r.status!='cancelled'",
            "SELECT created_at FROM ex_runs WHERE created_at>=?", since)
    dau = dau_people(con, since)

    print(f"{'неделя':8} {'с':6} {'какие':7} {'вышли':>6} {'игроков':>8} {'участий':>8} "
          f"{'команда':>8} {'сборов':>7} {'доля DAU':>9}")
    totals = {"старые": [0, 0, 0], "новые": [0, 0, 0]}
    for wk in sorted(set(old) | set(new)):
        for kind, src in (("старые", old), ("новые", new)):
            b = src.get(wk)
            if not b:
                continue
            team = f"{b['part'] / b['runs']:.1f}" if b["runs"] else "—"
            share = f"{b['people'] / dau[wk]:.0%}" if kind == "новые" and dau.get(wk) else ""
            print(f"{wk:8} {week_start(wk):6} {kind:7} {b['runs']:6} {b['people']:8} {b['part']:8} "
                  f"{team:>8} {b['lob']:7} {share:>9}")
            t = totals[kind]
            t[0] += 1
            t[1] += b["runs"]
            t[2] += b["people"]

    print()
    for kind, (weeks, runs, people) in totals.items():
        if weeks:
            print(f"{kind}: в среднем за неделю — {runs / weeks:.1f} экспедиций, {people / weeks:.1f} игроков "
                  f"(недель с данными: {weeks})")
    print("\nНеделя 4 октября — переходная: в ней могут быть и старые, и новые.")


if __name__ == "__main__":
    main()
