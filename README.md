# Username Generator Bot

Telegram-бот на aiogram 3.x, который генерирует благозвучные @username и асинхронно
проверяет их доступность на t.me и fragment.com.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Скопируй `.env.example` в `.env` и впиши токен бота, полученный у [@BotFather](https://t.me/BotFather):

```bash
copy .env.example .env
```

Открой `.env` и заполни `BOT_TOKEN=`.

## Запуск

```bash
python bot.py
```

При первом запуске автоматически создастся `data/usernames.db` (SQLite) и `data/bot.log`.

## Команды

| Команда | Описание |
|---|---|
| `/start` | Приветствие и выбор стиля → длины → количества через кнопки |
| `/generate [стиль] [длина] [количество]` | Генерация username, напр. `/generate mythic 9-12 10` |
| `/check @username` | Проверка конкретного username |
| `/favorites` | Список избранного; `/favorites add name`, `/favorites remove name` |
| `/history` | Последние 20 сгенерированных/проверенных username |
| `/help` | Справка |

Стили: `elegant`, `brand`, `mythic`, `tech`, `vibes`.

Длина: диапазон от 5 до 20 символов (пресеты в кнопках: `5-8`, `9-12`, `13-16`, `17-20`,
либо произвольный диапазон в `/generate`, например `/generate tech 6-9 5`).

Результаты генерации можно экспортировать в CSV/JSON кнопками под сообщением.

## Структура проекта

```
bot.py          — точка входа, обработчики команд и колбэков aiogram
generator.py    — фонетический генератор username по стилям
phonetics.py    — слоги, звуки, правила произносимости
checker.py      — асинхронная проверка t.me и fragment.com (aiohttp)
database.py     — SQLite (aiosqlite): история, избранное
utils.py        — форматирование сообщений, клавиатуры, экспорт CSV/JSON
config.py       — конфигурация из .env
```

## Как работает проверка доступности

- **t.me/{username}** — если страница содержит карточку профиля
  (`tgme_page_extra_info` / `tgme_page_title`) → занят; 404 или фраза
  "If you have Telegram" без карточки → свободен.
- **fragment.com/username/{username}** — "Username not found" → свободен;
  "already taken" → занят; блок с ценой → доступен для покупки на аукционе.

Итоговый статус учитывает **оба** источника независимо: username считается занятым,
если он занят хотя бы на одном из них (даже если на другом — свободен), а свободным —
только если свободен на обоих (или второй источник не удалось проверить). В карточке
результата отдельно показывается статус t.me и fragment, чтобы было видно, из-за
какого источника username помечен занятым.

Запросы идут с ротацией из 10 User-Agent, таймаутом 10 сек, тремя попытками
с экспоненциальной задержкой и rate-limit по умолчанию 5 запросов/сек на домен
(настраивается через `RATE_LIMIT_PER_SECOND` в `.env`). Результаты кэшируются
на 5 минут (`CACHE_TTL_SECONDS`), чтобы не долбить одни и те же домены повторно.

Прокси: список задаётся через `PROXIES` в `.env` (через запятую), запросы
идут по кругу (round-robin) между ними.

## Известные ограничения (сознательно не реализовано)

Полный ТЗ включал ряд пунктов, которые здесь оставлены как точки расширения,
а не реализованы "для галочки":

- **Обход Cloudflare / headless-рендеринг для Fragment.** Если fragment.com
  отдаёт JS-челлендж, `checker.py` честно возвращает статус `unknown`, а не
  пытается его обмануть через `cloudscraper`/`Flaresolverr`/Playwright.
  Добавить можно как отдельный fallback-путь в `_check_fragment`.
- **LLM-генерация вариантов и NLP-рейтинг "красивости".** Текущий генератор —
  чисто фонетический (правила CVCV, банки корней/суффиксов по стилям), без
  обращения к внешним LLM API.
- **Мультиязычные генераторы (яп/кор/лат).** Реализована только
  латиница/английские корни.
- **Redis-кэш.** Используется process-local dict с TTL — этого достаточно
  для одного инстанса бота; для горизонтального масштабирования нужно
  вынести в Redis.

Всё это можно добавлять инкрементально поверх текущей структуры без
переписывания ядра.

## Деплой на сервер

Бот работает через polling (не webhook), поэтому не нужен домен/SSL/входящий
порт — достаточно, чтобы процесс постоянно был запущен и мог достучаться до
api.telegram.org.

### Вариант 1: Docker (проще всего)

```bash
git clone -b claude/bot-length-selection-statuses-azdl13 https://github.com/Oxyg1/Odbcjehbxi.git nftea-bot
cd nftea-bot
cp .env.example .env   # заполнить BOT_TOKEN
docker compose up -d --build
docker compose logs -f   # посмотреть логи
```

`data/` (SQLite база и лог) монтируется как volume — переживает пересборки
и рестарты контейнера. Обновление после `git pull`:

```bash
docker compose up -d --build
```

### Вариант 2: systemd на голом VPS (без Docker)

```bash
sudo useradd -r -m -d /opt/nftea-bot nftea
sudo -u nftea git clone -b claude/bot-length-selection-statuses-azdl13 https://github.com/Oxyg1/Odbcjehbxi.git /opt/nftea-bot
cd /opt/nftea-bot
sudo -u nftea python3 -m venv .venv
sudo -u nftea .venv/bin/pip install -r requirements.txt
sudo -u nftea cp .env.example .env   # заполнить BOT_TOKEN
sudo cp deploy/nftea-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nftea-bot
sudo systemctl status nftea-bot
journalctl -u nftea-bot -f   # логи
```

Обновление:

```bash
cd /opt/nftea-bot
sudo -u nftea git pull
sudo -u nftea .venv/bin/pip install -r requirements.txt
sudo systemctl restart nftea-bot
```

В обоих случаях `.env` с токеном не должен попадать в git (уже в `.gitignore`).

## Примечание об использовании

Проверка доступности username через публичные страницы t.me и fragment.com —
это то же самое, что делает браузер при обычном посещении этих страниц.
Fragment — официальная площадка Telegram для аукциона username, так что сама
идея бота не нарушает условия использования. Тем не менее не стоит агрессивно
обходить их же собственные меры защиты (Cloudflare-челленджи и т.п.) —
уважай `RATE_LIMIT_PER_SECOND` и не выставляй его слишком высоким.
