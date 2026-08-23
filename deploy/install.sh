#!/usr/bin/env bash
#
# Установка Frog Tamagotchi на Ubuntu VDS.
#
#   sudo bash deploy/install.sh
#
# Скрипт идемпотентный: можно запускать повторно для обновления. База, .env,
# автобэкапы и логи при этом не трогаются.
#
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/frogbot}
APP_USER=${APP_USER:-frogbot}
UNIT_DIR=${UNIT_DIR:-/etc/systemd/system}
SERVICE=frogbot
PYTHON_MIN="3.12"

say()  { printf "\n\033[1;32m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m  %s\n" "$*"; }
die()  { printf "\n\033[1;31m✗\033[0m  %s\n" "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Запусти через sudo: sudo bash deploy/install.sh"

# Каталог с исходниками — тот, откуда запущен скрипт
SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ -f "${SRC_DIR}/bot.py" ]] || die "Рядом со скриптом нет bot.py — запускай из клона репозитория"

# ── 1. Python 3.12 ────────────────────────────────────────────────────────────
# На 3.11 файл не компилируется: в коде есть f-строки с вложенными кавычками.
say "Проверяю Python ${PYTHON_MIN}+"
if ! command -v python3.12 >/dev/null 2>&1; then
    say "Ставлю Python 3.12"
    apt-get update -qq
    if ! apt-get install -y -qq python3.12 python3.12-venv 2>/dev/null; then
        warn "В репозиториях нет python3.12, подключаю deadsnakes"
        apt-get install -y -qq software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update -qq
        apt-get install -y -qq python3.12 python3.12-venv
    fi
fi
PY=$(command -v python3.12)
"${PY}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    || die "Нужен Python ${PYTHON_MIN}+, найден $(${PY} -V)"
say "$(${PY} -V) — подходит"

# venv отдельным пакетом есть не всегда, проверяем что модуль на месте
"${PY}" -m venv --help >/dev/null 2>&1 || apt-get install -y -qq python3.12-venv

# ── 2. Пользователь и каталог ─────────────────────────────────────────────────
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    say "Завожу системного пользователя ${APP_USER}"
    useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi
mkdir -p "${APP_DIR}"

# ── 3. Код ────────────────────────────────────────────────────────────────────
# Копируем всё, кроме .env, базы, автобэкапов и логов — они живут на сервере
# и переживают обновление. Каталог назначения может совпадать с исходным
# (обновление на месте).
#
# db_backups исключается отдельно от *.db: сами файлы бэкапов (frog_*.db)
# и так защищены паттерном *.db, но rsync --delete всё равно пытался снести
# опустевший с его точки зрения каталог db_backups и падал с "cannot delete
# non-empty directory" — внутри оставались те самые защищённые файлы.
#
# *.session — сессия Telethon для pars.py. Создаётся один раз вручную вводом
# кода из Telegram; снесём её деплоем — парсер снова попросит код, ответить
# ему будет некому, и витрина NFT встанет. Каталог лотов тоже живёт на
# сервере: его пересобирает парсер, в репозитории его нет.
EXCLUDES=(.git .env venv '*.db' '*.db-*' logs db_backups
          '*.session' '*.session-journal' kissed_frog_on_sale.json)
if [[ "${SRC_DIR}" != "${APP_DIR}" ]]; then
    say "Копирую код в ${APP_DIR}"
    if command -v rsync >/dev/null 2>&1; then
        rsync_excludes=()
        for pat in "${EXCLUDES[@]}"; do rsync_excludes+=(--exclude "${pat}"); done
        rsync -a --delete "${rsync_excludes[@]}" "${SRC_DIR}/" "${APP_DIR}/"
    else
        find_excludes=()
        for pat in "${EXCLUDES[@]}"; do find_excludes+=(! -name "${pat}"); done
        find "${SRC_DIR}" -maxdepth 1 -mindepth 1 "${find_excludes[@]}" \
            -exec cp -a {} "${APP_DIR}/" \;
    fi
fi

# ── 4. Зависимости ────────────────────────────────────────────────────────────
say "Ставлю зависимости в venv"
[[ -x "${APP_DIR}/venv/bin/python" ]] || "${PY}" -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade -r "${APP_DIR}/requirements.txt"
"${APP_DIR}/venv/bin/python" -c 'import telegram; print("python-telegram-bot", telegram.__version__)'

# Файл должен компилироваться до того, как systemd попробует его запустить
"${APP_DIR}/venv/bin/python" -m py_compile "${APP_DIR}/bot.py" \
    || die "bot.py не компилируется — смотри ошибку выше"

# ── 5. Настройки ──────────────────────────────────────────────────────────────
if [[ ! -f "${APP_DIR}/.env" ]]; then
    say "Создаю .env"
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    if [[ -n "${BOT_TOKEN:-}" ]]; then
        sed -i "s|^#\?\s*BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" "${APP_DIR}/.env"
        say "Токен взят из переменной окружения"
    else
        warn "Впиши токен: nano ${APP_DIR}/.env  (строка BOT_TOKEN=)"
    fi
else
    say ".env уже есть, не трогаю"
fi

# В .env лежит токен бота — читать его может только сам бот
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"
chmod 750 "${APP_DIR}"

# ── 6. systemd ────────────────────────────────────────────────────────────────
say "Ставлю сервис ${SERVICE}"
sed -e "s|/opt/frogbot|${APP_DIR}|g" \
    -e "s|^User=.*|User=${APP_USER}|" \
    -e "s|^Group=.*|Group=${APP_USER}|" \
    "${APP_DIR}/deploy/frogbot.service" > "${UNIT_DIR}/${SERVICE}.service"
systemctl daemon-reload
systemctl enable --quiet "${SERVICE}"

if grep -qE '^BOT_TOKEN=.+' "${APP_DIR}/.env"; then
    systemctl restart "${SERVICE}"
    sleep 3
    if systemctl is-active --quiet "${SERVICE}"; then
        say "Бот запущен"
    else
        warn "Сервис не поднялся, последние строки лога:"
        journalctl -u "${SERVICE}" -n 30 --no-pager
        exit 1
    fi
else
    warn "Токен не задан — сервис включён, но не запущен."
    warn "Впиши BOT_TOKEN в ${APP_DIR}/.env и выполни: systemctl start ${SERVICE}"
fi

cat <<EOF

  Каталог      ${APP_DIR}
  Настройки    ${APP_DIR}/.env
  База         ${APP_DIR}/frog_game.db

  Логи         journalctl -u ${SERVICE} -f
  Перезапуск   systemctl restart ${SERVICE}
  Остановить   systemctl stop ${SERVICE}
  Обновить     git pull && sudo bash deploy/install.sh

EOF
