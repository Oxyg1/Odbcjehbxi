-- ═══════════════════════════════════════════════════════════════════════
-- 📊 ОТЧЁТ ИСПОЛЬЗОВАНИЯ АКТИВНОСТЕЙ — frog_game.db
-- ═══════════════════════════════════════════════════════════════════════
-- Запуск:
--   sqlite3 -header -column frog_game.db < usage_report.sql
-- или (если хочешь CSV для таблички/графика):
--   sqlite3 -header -csv frog_game.db < usage_report.sql > usage_report.csv
--
-- ВАЖНО про сроки хранения — иначе цифры введут в заблуждение:
--   • player_action_log  — чистится каждые 7 дней  (plog_purge_old, вызов L56621)
--   • chat_activity_log  — чистится старше 30 дней  (L18375, но только для
--                           записей ТОГО чата, откуда пришло новое событие —
--                           чат без активности может копить записи дольше)
--   • game_logs, coin_log, gacha_log, gift_log     — НЕ чистятся, полная история
--   • duels/battles/expeditions/staya_*/auctions/…  — основные игровые таблицы,
--                           тоже без чистки, надёжный источник за любой период
--
-- Поэтому "за последний месяц" из player_action_log показывает только то,
-- что попало в текущее 7-дневное окно на момент запроса, — не полагайся на
-- него как на месячный срез. Для активностей, у которых есть собственная
-- таблица (дуэли, экспедиции, стаи, аукционы...), используй её напрямую —
-- секции 3+ ниже так и делают.
-- ═══════════════════════════════════════════════════════════════════════


-- ── 0. БАЗОВАЯ ЛИНИЯ: сколько всего живых игроков и сколько реально живых ──
-- "Живой" = заходил за последние 30 дней. Все % ниже считай от этого числа,
-- не от общего count(*) — там будут годы заброшенных аккаунтов.
SELECT
    (SELECT COUNT(*) FROM frogs)                                            AS всего_аккаунтов,
    (SELECT COUNT(*) FROM frogs WHERE last_seen > strftime('%s','now') - 30*86400) AS активны_30дн,
    (SELECT COUNT(*) FROM frogs WHERE last_seen > strftime('%s','now') - 7*86400)  AS активны_7дн;


-- ── 1. GAME_LOGS: казино и парные мини-игры — распределение по game_type ──
-- Полная история, чистки нет. group_type — это то, что передаётся в
-- log_game(user_id, game_type, ...) из каждого места вызова, реальные
-- значения увидишь после запуска (в коде это разбросано по ~15 функциям).
SELECT
    game_type,
    COUNT(*)                    AS всего_партий,
    COUNT(DISTINCT user_id)     AS уникальных_игроков,
    COUNT(*) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS партий_30дн,
    COUNT(DISTINCT user_id) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS игроков_30дн,
    MAX(ts)                     AS последний_раз_epoch,
    datetime(MAX(ts), 'unixepoch') AS последний_раз
FROM game_logs
GROUP BY game_type
ORDER BY игроков_30дн DESC;


-- ── 2. COIN_LOG: на что вообще тратятся/приходят монеты — по reason ──────
-- reason — свободная строка (например "stars_payment kva_retry_stars_10"),
-- сгруппировано по точному значению; если хочешь укрупнённо — смотри
-- секцию 2b с группировкой по первому слову.
SELECT
    reason,
    COUNT(*)                AS операций,
    COUNT(DISTINCT user_id) AS уникальных_игроков,
    SUM(amount)             AS сумма_чистая,
    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS начислено,
    SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS списано
FROM coin_log
GROUP BY reason
ORDER BY операций DESC
LIMIT 40;

-- 2b. То же, но укрупнённо по первому слову reason (обычно это тип операции)
SELECT
    substr(reason, 1, instr(reason || ' ', ' ') - 1) AS reason_тип,
    COUNT(*)                AS операций,
    COUNT(DISTINCT user_id) AS уникальных_игроков,
    COUNT(*) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS операций_30дн
FROM coin_log
GROUP BY reason_тип
ORDER BY операций_30дн DESC;


-- ── 3. ДУЭЛИ / БИТВЫ — сколько реально играют против других людей ────────
SELECT 'duels' AS активность,
    COUNT(*) AS всего,
    COUNT(*) FILTER (WHERE status NOT IN ('pending','declined')) AS завершённых,
    COUNT(DISTINCT challenger_id) + 0 AS уникальных_инициаторов,
    COUNT(*) FILTER (WHERE created_at > strftime('%s','now') - 30*86400) AS за_30дн
FROM duels
UNION ALL
SELECT 'battles',
    COUNT(*),
    COUNT(*) FILTER (WHERE status NOT IN ('pending','declined')),
    COUNT(DISTINCT challenger_id),
    COUNT(*) FILTER (WHERE created_at > strftime('%s','now') - 30*86400)
FROM battles;


-- ── 4. ЭКСПЕДИЦИИ — самая дорогая в коде механика, проверим отдачу ───────
SELECT
    COUNT(*)                          AS всего_экспедиций,
    COUNT(*) FILTER (WHERE status = 'finished') AS завершённых,
    COUNT(*) FILTER (WHERE started_at > strftime('%s','now') - 30*86400) AS начато_30дн,
    (SELECT COUNT(DISTINCT user_id) FROM expedition_members em
       JOIN expeditions e ON e.id = em.expedition_id
      WHERE e.started_at > strftime('%s','now') - 30*86400)              AS уникальных_участников_30дн,
    (SELECT AVG(cnt) FROM (
        SELECT expedition_id, COUNT(*) AS cnt FROM expedition_members GROUP BY expedition_id
     ))                                AS средний_размер_группы
FROM expeditions;


-- ── 5. СТАИ: войны / набеги / стычки — социальный слой, ради которого чат ─
SELECT 'staya_raids (набеги)' AS активность,
    COUNT(*) AS всего,
    COUNT(DISTINCT attacker_uid) AS уникальных_участников,
    COUNT(*) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS за_30дн
FROM staya_raids
UNION ALL
SELECT 'staya_skirmishes (стычки)',
    COUNT(*),
    COUNT(DISTINCT attacker_staya) + COUNT(DISTINCT defender_staya),
    COUNT(*) FILTER (WHERE started_at > strftime('%s','now') - 30*86400)
FROM staya_skirmishes;

-- 5b. Сколько игроков вообще состоят в стае — если "война стай" ключевая
-- фича, а в стаях 5% игроков, это тоже симптом
SELECT
    (SELECT COUNT(*) FROM stayas)                                    AS всего_стай,
    (SELECT COUNT(DISTINCT user_id) FROM staya_members)              AS игроков_в_стаях,
    (SELECT COUNT(*) FROM frogs WHERE last_seen > strftime('%s','now') - 30*86400) AS активных_игроков_30дн;


-- ── 6. АУКЦИОНЫ / ЛОТЕРЕЯ / ГАЧА — платный контент, кто в него заходит ───
SELECT 'auctions' AS активность,
    COUNT(*) AS всего,
    COUNT(*) FILTER (WHERE status = 'finished' AND winner_id IS NOT NULL) AS с_победителем,
    COUNT(*) FILTER (WHERE started_at > strftime('%s','now') - 30*86400)  AS за_30дн
FROM auctions
UNION ALL
SELECT 'lottery_tickets',
    COUNT(*),
    COUNT(DISTINCT user_id),
    COUNT(*) FILTER (WHERE purchased_at > strftime('%s','now') - 30*86400)
FROM lottery_tickets;

SELECT
    rarity,
    COUNT(*)                AS выпадений,
    COUNT(DISTINCT user_id) AS уникальных_игроков,
    COUNT(*) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS за_30дн
FROM gacha_log
GROUP BY rarity
ORDER BY выпадений DESC;


-- ── 7. ПРЯЧЬ-ИЩИ / ДРУЖБА-РИТУАЛЫ — маленькие фичи, часто первыми под нож ─
SELECT
    COUNT(*)                                AS всего_событий,
    COUNT(*) FILTER (WHERE status='finished') AS завершено,
    COUNT(*) FILTER (WHERE created_at > strftime('%s','now') - 30*86400) AS за_30дн
FROM hideseek_events;

-- Ритуалы дружбы (last_hug/last_scratch/last_wash/last_praise/last_lullaby/
-- last_treat) — сколько пар вообще хоть раз это делали, а не только
-- добавили друг друга в друзья
SELECT
    COUNT(*)                                          AS всего_пар,
    COUNT(*) FILTER (WHERE pending = 0)                AS подтверждённых_пар,
    COUNT(*) FILTER (WHERE last_hug     > 0)           AS хоть_раз_обнял,
    COUNT(*) FILTER (WHERE last_scratch > 0)           AS хоть_раз_почесал,
    COUNT(*) FILTER (WHERE last_wash    > 0)           AS хоть_раз_помыл,
    COUNT(*) FILTER (WHERE last_praise  > 0)           AS хоть_раз_похвалил,
    COUNT(*) FILTER (WHERE last_lullaby > 0)           AS хоть_раз_колыбельную,
    COUNT(*) FILTER (WHERE last_treat   > 0)           AS хоть_раз_угостил
FROM friendships;


-- ── 8. ПОДАРКИ МЕЖДУ ИГРОКАМИ — насколько живой социальный слой ──────────
SELECT
    COUNT(*)                 AS всего_переводов,
    COUNT(DISTINCT from_id)  AS уникальных_отправителей,
    COUNT(DISTINCT to_id)    AS уникальных_получателей,
    COUNT(*) FILTER (WHERE ts > strftime('%s','now') - 30*86400) AS за_30дн
FROM gift_log;


-- ── 9. NFT: сколько игроков вообще подтвердили владение KissedFrog ───────
-- Это прямой ответ на вопрос из CONTENT.md — сколько людей уже прошли
-- верификацию, но не получают из неё почти ничего.
SELECT
    COUNT(*)                                       AS всего_записей_nft,
    COUNT(DISTINCT user_id)                        AS уникальных_владельцев,
    (SELECT COUNT(*) FROM frogs WHERE last_seen > strftime('%s','now') - 30*86400) AS активных_игроков_30дн
FROM nft_frogs
WHERE verified = 1;


-- ── 10. CHAT_ACTIVITY_LOG (окно 30 дней по конструкции таблицы) ─────────
SELECT
    action,
    COUNT(*)                AS событий,
    COUNT(DISTINCT user_id) AS уникальных_игроков,
    COUNT(DISTINCT chat_id) AS уникальных_чатов
FROM chat_activity_log
GROUP BY action
ORDER BY событий DESC
LIMIT 30;


-- ── 11. PLAYER_ACTION_LOG — только последние ≤7 дней, см. предупреждение ─
SELECT
    action,
    COUNT(*)                AS событий_за_7дн,
    COUNT(DISTINCT user_id) AS уникальных_игроков_за_7дн
FROM player_action_log
GROUP BY action
ORDER BY событий_за_7дн DESC
LIMIT 30;
