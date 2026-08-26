# Установка сайта на Ubuntu-сервер (VPS) с доменом DuckDNS

Пошаговая инструкция: от чистого сервера до работающего сайта на
`https://ваш-поддомен.duckdns.org` с бесплатным SSL-сертификатом.

Занимает 15–20 минут. Опыт администрирования не нужен — все команды можно
копировать целиком.

**Что получится в итоге**

- Сайт открывается по адресу `https://ваш-поддомен.duckdns.org`
- Замочек в адресной строке (сертификат Let's Encrypt, продлевается сам)
- Обновление сайта одной командой `deploy-kondyrev`
- IP-адрес в DuckDNS обновляется автоматически

---

## Обозначения

По ходу инструкции заменяйте на свои значения:

| В командах | Что подставить | Пример |
|---|---|---|
| `ВАШ_ПОДДОМЕН` | имя, которое вы завели на duckdns.org (**без** `.duckdns.org`) | `kondyrev` |
| `ВАШ_ТОКЕН` | токен из личного кабинета DuckDNS | `a1b2c3d4-...` |
| `IP_СЕРВЕРА` | IP-адрес вашего VPS | `203.0.113.10` |
| `ВАША_ПОЧТА` | почта для уведомлений о сертификате | `ivan@mail.ru` |

Полный адрес сайта будет `ВАШ_ПОДДОМЕН.duckdns.org` — дальше он встречается
именно в таком виде.

---

## Шаг 1. Завести домен на DuckDNS

1. Откройте <https://www.duckdns.org> и войдите (через Google, GitHub и т. п.).
2. В поле **sub domain** впишите желаемое имя, например `kondyrev`, и нажмите
   **add domain**.
3. В строке появившегося домена в поле **current ip** впишите IP вашего VPS
   и нажмите **update ip**.
4. Скопируйте **token** — он показан вверху страницы, понадобится на шаге 8.

**Проверьте, что домен указывает на сервер** (команду выполняйте на своём
компьютере, не на сервере):

```bash
nslookup ВАШ_ПОДДОМЕН.duckdns.org
```

В ответе должен быть IP вашего VPS. Если адрес другой или ответа нет —
подождите 2–5 минут и повторите. Дальше идти нет смысла: без этого не выдастся
SSL-сертификат.

---

## Шаг 2. Подключиться к серверу

```bash
ssh root@IP_СЕРВЕРА
```

Если провайдер дал не `root`, а обычного пользователя — подключайтесь им и
дописывайте `sudo` в начало каждой команды ниже.

Обновите систему:

```bash
apt update && apt upgrade -y
```

---

## Шаг 3. Установить нужные программы

```bash
apt install -y nginx git rsync curl
```

- **nginx** — веб-сервер, он будет отдавать сайт посетителям
- **git** — чтобы скачивать сайт из репозитория и обновлять его
- **rsync** — копирование файлов при обновлении
- **curl** — для обновления IP в DuckDNS

Проверьте, что nginx запустился:

```bash
systemctl status nginx --no-pager
```

Должно быть `active (running)`. Теперь откройте в браузере `http://IP_СЕРВЕРА` —
увидите заглушку «Welcome to nginx!». Если страница не открывается, смотрите
раздел «Если что-то не работает» в конце.

---

## Шаг 4. Настроить файрвол

> ⚠️ **Важно:** сначала разрешите SSH, потом включайте файрвол. Если сделать
> наоборот, вы потеряете доступ к серверу.

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

На вопрос `Command may disrupt existing ssh connections. Proceed?` ответьте `y`.

Проверка:

```bash
ufw status
```

В списке должны быть `OpenSSH` и `Nginx Full` со статусом `ALLOW`.

---

## Шаг 5. Скачать сайт на сервер

Держим две папки: в одной исходники из Git, в другую попадает то, что видят
посетители. Так папка `.git` со служебными данными никогда не окажется в
открытом доступе.

```bash
# исходники
git clone --branch claude/kondyrev-banquet-hall-site-mvet2n \
  https://github.com/Oxyg1/Odbcjehbxi.git /srv/kondyrev

# то, что отдаётся посетителям
mkdir -p /var/www/kondyrev
rsync -a --delete --exclude '.git' /srv/kondyrev/ /var/www/kondyrev/
chown -R www-data:www-data /var/www/kondyrev
```

Проверка — должен появиться список файлов сайта:

```bash
ls /var/www/kondyrev
```

> Когда изменения вольют в ветку `main`, замените в команде `git clone`
> название ветки на `main`.

---

## Шаг 6. Настроить nginx

Создайте файл настроек:

```bash
nano /etc/nginx/sites-available/kondyrev
```

Вставьте текст ниже (в `nano` вставка — правая кнопка мыши или `Ctrl+Shift+V`),
**заменив `ВАШ_ПОДДОМЕН`**:

```nginx
server {
    listen 80;
    listen [::]:80;

    server_name ВАШ_ПОДДОМЕН.duckdns.org;

    root /var/www/kondyrev;
    index index.html;

    # Кодировка в заголовке ответа — чтобы русский текст точно не превратился
    # в кракозябры, даже если браузер не заглянет в <meta charset>
    charset utf-8;

    # Обычная выдача файлов; если файла нет — страница 404
    location / {
        try_files $uri $uri/ =404;
    }

    # Сжатие: страница и стили передаются в 3–4 раза быстрее
    gzip on;
    gzip_vary on;
    gzip_min_length 512;
    gzip_types text/css application/javascript application/json image/svg+xml;

    # Кэширование картинок, стилей и скриптов.
    # must-revalidate: браузер каждый раз спрашивает сервер, не изменился ли
    # файл. Ответ «не изменился» весит байты, зато заменённые фотографии
    # посетители видят сразу, а не через месяц.
    location ~* \.(jpg|jpeg|png|webp|gif|svg|ico|css|js|woff2)$ {
        add_header Cache-Control "public, max-age=3600, must-revalidate";
        access_log off;
    }

    # Запрет на служебные файлы, начинающиеся с точки (.git, .env и подобные)
    location ~ /\. {
        deny all;
    }
}
```

Сохраните: `Ctrl+O`, `Enter`, затем `Ctrl+X`.

> ⚠️ **Не пропускайте эту вставку.** Следующий шаг создаёт на файл выше
> символическую ссылку — если файла ещё нет, ссылка получится «битой»
> (указывает в никуда), и `nginx -t` откажется стартовать с ошибкой
> `open() "/etc/nginx/sites-enabled/kondyrev" failed (2: No such file or
> directory)`. Проверить, что файл действительно сохранился:
> ```bash
> cat /etc/nginx/sites-available/kondyrev
> ```
> Если команда ничего не вывела или выдала ошибку — повторите вставку конфига.

Включите сайт и отключите заглушку nginx:

```bash
ln -s /etc/nginx/sites-available/kondyrev /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
```

`nginx -t` должен ответить `syntax is ok` и `test is successful`. Если есть
ошибка — вы увидите номер строки; откройте файл заново и поправьте.

Применяем:

```bash
systemctl reload nginx
```

**Проверьте:** откройте в браузере `http://ВАШ_ПОДДОМЕН.duckdns.org` —
сайт уже должен работать. Пока без замочка, это нормально.

---

## Шаг 7. Включить HTTPS (замочек в браузере)

Сертификат бесплатный, от Let's Encrypt, выдаётся автоматически.

```bash
apt install -y certbot python3-certbot-nginx

certbot --nginx \
  -d ВАШ_ПОДДОМЕН.duckdns.org \
  --agree-tos \
  -m ВАША_ПОЧТА \
  --redirect \
  --no-eff-email
```

Что делают ключи:

- `--redirect` — посетители с `http://` автоматически переходят на `https://`
- `--agree-tos` — согласие с условиями Let's Encrypt
- `--no-eff-email` — не подписываться на рассылку

Certbot сам допишет нужные строки в конфиг nginx и перезапустит его.

**Проверьте автопродление** (сертификат живёт 90 дней и продлевается сам):

```bash
certbot renew --dry-run
systemctl list-timers | grep certbot
```

Первая команда должна закончиться без ошибок, вторая — показать таймер
`snap.certbot.renew.timer` или `certbot.timer`.

Теперь `https://ВАШ_ПОДДОМЕН.duckdns.org` открывается с замочком.

---

## Шаг 8. Автообновление IP в DuckDNS

Если у сервера постоянный IP, шаг можно пропустить — но лишним он не будет.
Если IP меняется, без этого сайт однажды перестанет открываться.

Создайте скрипт:

```bash
mkdir -p /opt/duckdns
nano /opt/duckdns/duck.sh
```

Вставьте, подставив **свой поддомен и токен**:

```bash
#!/bin/bash
# Сообщает DuckDNS текущий адрес сервера.
# Пустой ip= означает «возьми адрес, с которого пришёл запрос».
curl -fsS "https://www.duckdns.org/update?domains=ВАШ_ПОДДОМЕН&token=ВАШ_ТОКЕН&ip=" \
  -o /var/log/duckdns.log
```

Сохраните (`Ctrl+O`, `Enter`, `Ctrl+X`) и разрешите запуск:

```bash
chmod 700 /opt/duckdns/duck.sh
/opt/duckdns/duck.sh
cat /var/log/duckdns.log
```

В логе должно быть слово `OK`. Если `KO` — перепроверьте токен и имя поддомена.

> В файле лежит ваш токен, поэтому `chmod 700` обязателен: он закрывает файл
> от всех, кроме root.

Запуск каждые 5 минут:

```bash
crontab -e
```

(при первом запуске выберите редактор `nano` — вариант 1). В конец файла
добавьте строку:

```
*/5 * * * * /opt/duckdns/duck.sh >/dev/null 2>&1
```

Сохраните и закройте.

---

## Шаг 9. Команда для обновления сайта

Чтобы не повторять шаг 5 руками, сделаем команду обновления:

```bash
nano /usr/local/bin/deploy-kondyrev
```

Вставьте:

```bash
#!/usr/bin/env bash
# Забирает свежую версию сайта из Git и выкладывает её посетителям.
set -euo pipefail

SRC=/srv/kondyrev
WEB=/var/www/kondyrev

BRANCH="$(git -C "$SRC" rev-parse --abbrev-ref HEAD)"
echo "Обновляю ветку $BRANCH…"

git -C "$SRC" fetch --prune origin
git -C "$SRC" reset --hard "origin/$BRANCH"

rsync -a --delete --exclude '.git' "$SRC"/ "$WEB"/
chown -R www-data:www-data "$WEB"

echo "Готово: $(date '+%d.%m.%Y %H:%M')"
```

Сохраните и разрешите запуск:

```bash
chmod +x /usr/local/bin/deploy-kondyrev
```

Теперь после любых изменений в репозитории достаточно выполнить на сервере:

```bash
deploy-kondyrev
```

> ⚠️ **Не редактируйте файлы прямо в `/srv/kondyrev` или `/var/www/kondyrev`.**
> Команда `deploy-kondyrev` перезаписывает их содержимым из Git, и ваши правки
> пропадут. Все изменения вносите в репозиторий, затем запускайте
> `deploy-kondyrev` на сервере.

---

## Шаг 10. Дописать домен в настройки сайта

В коде сайта в нескольких местах стоит заглушка `https://example.com` — из-за
неё не будет работать превью ссылки в WhatsApp, Telegram и ВКонтакте.

Правки делаем **в репозитории** (на своём компьютере или прямо на GitHub),
а не на сервере. В файле `index.html` замените все `https://example.com`
на `https://ВАШ_ПОДДОМЕН.duckdns.org` — это теги `canonical`, `og:url`,
`og:image` и два поля в блоке микроразметки.

Если удобнее сделать это через командную строку в папке с репозиторием:

```bash
sed -i 's|https://example.com|https://ВАШ_ПОДДОМЕН.duckdns.org|g' index.html
git commit -am "Прописан реальный домен сайта"
git push
```

Затем на сервере:

```bash
deploy-kondyrev
```

Заодно посмотрите остальные пометки `TODO` — цены, отзывы, почта для заявок.
Что и где менять, подробно расписано в `README.md`.

---

## Проверка, что всё в порядке

| Что проверить | Как |
|---|---|
| Сайт открывается по HTTPS | `https://ВАШ_ПОДДОМЕН.duckdns.org` в браузере |
| HTTP перекидывает на HTTPS | `curl -I http://ВАШ_ПОДДОМЕН.duckdns.org` → строка `301` |
| Служебная папка закрыта | `curl -I https://ВАШ_ПОДДОМЕН.duckdns.org/.git/config` → `403` |
| Страница «Спасибо» работает | откройте `/thanks.html` |
| Сертификат продлится сам | `certbot renew --dry-run` без ошибок |
| Вид с телефона | откройте сайт со смартфона |

---

## Если что-то не работает

**Сайт не открывается вообще, браузер долго думает**

Скорее всего закрыты порты. Проверьте файрвол на сервере (`ufw status`) и,
отдельно, панель управления VPS: у многих провайдеров (Selectel, Timeweb,
Yandex Cloud, Hetzner) есть свой сетевой фильтр, где 80 и 443 порты нужно
открыть вручную.

**Certbot пишет `Timeout during connect` или `unauthorized`**

Let's Encrypt не смог достучаться до сервера по 80 порту. Причины: домен
указывает на другой IP (перепроверьте шаг 1), закрыт 80 порт, либо nginx не
запущен (`systemctl status nginx`).

**`nginx -t` пишет `open() "/etc/nginx/sites-enabled/kondyrev" failed (2: No
such file or directory)`**

Symlink на шаге 6 создали раньше, чем сохранили сам конфиг — ссылка указывает
в никуда. Чинится так:

```bash
rm -f /etc/nginx/sites-enabled/kondyrev
nano /etc/nginx/sites-available/kondyrev
```

Вставьте конфиг из шага 6, сохраните (`Ctrl+O`, `Enter`, `Ctrl+X`), затем:

```bash
cat /etc/nginx/sites-available/kondyrev   # убедитесь, что файл не пустой
ln -s /etc/nginx/sites-available/kondyrev /etc/nginx/sites-enabled/
nginx -t
```

**`nginx -t` пишет `Address family not supported by protocol`**

На сервере отключён IPv6, а в конфиге есть строка для него. Откройте
`/etc/nginx/sites-available/kondyrev`, удалите строку

```
    listen [::]:80;
```

и повторите `nginx -t`. На работу сайта это никак не влияет.

**Ошибка 403 Forbidden**

Права на файлы. Выполните:

```bash
chown -R www-data:www-data /var/www/kondyrev
chmod -R u=rwX,go=rX /var/www/kondyrev
systemctl reload nginx
```

**Ошибка 404 Not Found на главной**

Не на месте `index.html`. Проверьте `ls /var/www/kondyrev/index.html` — файл
должен существовать. Если нет, повторите шаг 5.

**Заменил фотографии, а на сайте старые**

Кэш браузера. Обновите страницу через `Ctrl+F5` (на Mac — `Cmd+Shift+R`).
У обычных посетителей всё обновится в течение часа.

**Где посмотреть ошибки nginx**

```bash
tail -n 50 /var/log/nginx/error.log
```

**Проверить, что nginx вообще отвечает**

```bash
curl -I http://127.0.0.1
```

---

## Рекомендуется: базовая защита сервера

Не обязательно для работы сайта, но сильно снижает шанс, что сервер взломают.

**Вход по SSH-ключу вместо пароля.** На своём компьютере:

```bash
ssh-copy-id root@IP_СЕРВЕРА
```

Убедитесь, что вход по ключу работает (`ssh root@IP_СЕРВЕРА` не спрашивает
пароль), и только после этого отключите вход по паролю на сервере:

```bash
nano /etc/ssh/sshd_config
```

Найдите и приведите к виду:

```
PasswordAuthentication no
```

```bash
systemctl restart ssh
```

**Защита от перебора паролей:**

```bash
apt install -y fail2ban
systemctl enable --now fail2ban
```

**Автоматические обновления безопасности:**

```bash
apt install -y unattended-upgrades
dpkg-reconfigure --priority=low unattended-upgrades
```

---

## Приложение: вариант проще — Caddy вместо nginx

Если nginx кажется громоздким, есть альтернатива: веб-сервер **Caddy** сам
получает и продлевает сертификаты, настройка занимает три строки. Шаги 6 и 7
заменяются на следующее (шаги 1–5, 8, 9 остаются как есть, только nginx
устанавливать не нужно).

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

Настройка:

```bash
nano /etc/caddy/Caddyfile
```

Содержимое целиком:

```
ВАШ_ПОДДОМЕН.duckdns.org {
    root * /var/www/kondyrev
    file_server
    encode gzip
    @dotfiles path /.*
    respond @dotfiles 403
}
```

```bash
systemctl reload caddy
```

Всё: HTTPS включится сам через несколько секунд, отдельный сертбот не нужен.
В файрволе (шаг 4) вместо `ufw allow 'Nginx Full'` используйте
`ufw allow 80,443/tcp`.
