# Деплой на сервере

Боту не нужен домен, белый IP и открытые порты: он работает через long-polling, то есть сам
ходит к Telegram по исходящему HTTPS. Достаточно самого дешёвого VPS.

**Минимальные требования:** Linux (Ubuntu 22.04/24.04 или Debian 12), 1 vCPU, 512 МБ RAM,
диск от 10 ГБ (вложения занимают место — см. раздел «Диск»).

⚠️ **Один токен — один запущенный процесс.** Если бот поднят в двух местах (например, на
сервере и у вас на ноутбуке), Telegram будет отдавать `409 Conflict`, и уведомления начнут
теряться. Перед запуском на сервере остановите локальную копию.

---

## Вариант A. Docker (рекомендую)

```bash
# 1. Docker, если его ещё нет
curl -fsSL https://get.docker.com | sh

# 2. Код и настройки
sudo mkdir -p /opt/tg-watcher && sudo chown "$USER" /opt/tg-watcher
git clone <адрес репозитория> /opt/tg-watcher
cd /opt/tg-watcher
cp .env.example .env
nano .env                 # впишите BOT_TOKEN, при желании TIMEZONE и RETENTION_DAYS
chmod 600 .env

# 3. Запуск
docker compose up -d --build
docker compose logs -f    # в логе должно быть «Бот @имя запущен»
```

`restart: unless-stopped` в `docker-compose.yml` поднимает контейнер после перезагрузки
сервера и после падения. База и вложения лежат в `./data` на хосте — контейнер можно
пересобирать без потери кэша.

Обновление:

```bash
cd /opt/tg-watcher
git pull
docker compose up -d --build
```

---

## Вариант B. systemd + venv (без Docker)

```bash
# 1. Пользователь и код
sudo adduser --system --group --home /opt/tg-watcher botuser
sudo -u botuser git clone <адрес репозитория> /opt/tg-watcher
cd /opt/tg-watcher

# 2. Зависимости
sudo apt update && sudo apt install -y python3-venv
sudo -u botuser python3 -m venv .venv
sudo -u botuser .venv/bin/pip install -r requirements.txt

# 3. Настройки
sudo -u botuser cp .env.example .env
sudo -u botuser nano .env          # BOT_TOKEN
sudo chmod 600 .env

# 4. Сервис
sudo cp deploy/tg-business-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tg-business-watcher
```

Юнит уже лежит в репозитории (`deploy/tg-business-watcher.service`) и рассчитан на пути
выше. Если каталог или имя пользователя другие — поправьте `WorkingDirectory`, `User` и
`ExecStart`.

Проверка и логи:

```bash
systemctl status tg-business-watcher
journalctl -u tg-business-watcher -f
```

Обновление:

```bash
cd /opt/tg-watcher
sudo -u botuser git pull
sudo -u botuser .venv/bin/pip install -r requirements.txt
sudo systemctl restart tg-business-watcher
```

---

## После запуска

1. В `@BotFather`: `/mybots` → бот → **Bot Settings** → **Business Mode** → **Enable**.
2. В Telegram: Настройки → Telegram для бизнеса → Чат-боты → добавить бота.
3. В личке с ботом должно прийти «✅ Бот подключён к бизнес-аккаунту».
4. Проверьте вживую: напишите себе с другого аккаунта и удалите сообщение — уведомление
   придёт через пару секунд (окно склейки `DELETE_DEBOUNCE`).

Если уведомлений нет — смотрите «Если что-то не работает» ниже.

---

## Диск и данные

Всё состояние — в каталоге `data/`: `tracker.db` (SQLite) и `media/` (скачанные вложения).

- Вложения — основной потребитель места. Оценка: активная переписка с фото легко даёт
  1–3 ГБ в месяц. Регулируется тремя параметрами: `RETENTION_DAYS` (по умолчанию 30 дней,
  чистка идёт раз в 6 часов), `MAX_MEDIA_MB` (по умолчанию 20 МБ — это и есть потолок
  Bot API на скачивание) и `BACKUP_MEDIA=false`, если бэкап файлов не нужен вовсе.
- Место на диске: `df -h /` и `du -sh /opt/tg-watcher/data`.
- Бэкап (SQLite нельзя копировать «на живую» — используйте `.backup`):

```bash
sudo -u botuser /opt/tg-watcher/.venv/bin/python - <<'PY'
import sqlite3
src = sqlite3.connect("/opt/tg-watcher/data/tracker.db")
dst = sqlite3.connect("/opt/tg-watcher/data/backup.db")
with dst:
    src.backup(dst)
PY
```

- Стереть весь кэш можно прямо из Telegram — команда `/purge`.

## Безопасность

В `data/` лежит копия вашей деловой переписки, а в `.env` — токен, дающий полный контроль
над ботом. Разумный минимум:

```bash
chmod 600 /opt/tg-watcher/.env
chmod 700 /opt/tg-watcher/data
```

Держите SSH по ключам, а не по паролю, и не запускайте бота от root — оба варианта выше
этого и не делают (`botuser` в systemd, непривилегированный процесс в контейнере). Если
токен утёк — отзовите его в `@BotFather` (`/revoke`) и впишите новый в `.env`.

---

## Если что-то не работает

| Симптом | Причина и что делать |
|---|---|
| Нет уведомлений вообще, в логе тихо | Не включён **Business Mode** в @BotFather либо бот не добавлен в Настройки → Telegram для бизнеса → Чат-боты |
| В логе `TelegramConflictError` / `409` | Тот же токен запущен ещё где-то. Оставьте один процесс |
| В логе `Unauthorized` / `401` | Неверный или отозванный `BOT_TOKEN` |
| Приходят уведомления, но без фото | Вложение больше `MAX_MEDIA_MB`, либо `BACKUP_MEDIA=false` и Telegram уже не отдаёт файл по `file_id`, либо это исчезающее медиа — их Bot API не отдаёт |
| Уведомления о ваших же удалениях | Включён тумблер «Учитывать мои сообщения» в `/settings` |
| Неверное время в отчётах | Поправьте `TIMEZONE` в `.env` и перезапустите |
| Бот молчит после перезагрузки сервера | `systemctl enable tg-business-watcher` (или `restart: unless-stopped` в compose) |

Полезное для диагностики: `LOG_LEVEL=DEBUG` в `.env` плюс `journalctl -u tg-business-watcher -f`
(или `docker compose logs -f`). При старте бот пишет, какие апдейты слушает — там должны быть
`business_message`, `edited_business_message`, `deleted_business_messages`.
