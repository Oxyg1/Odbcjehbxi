"""Выкладка готовых картинок в канал стикерами.

Берёт все PNG/WebP/JPG из папки, приводит к стикеру Telegram
(WebP, 512 px по длинной стороне, не больше 512 КБ) и отправляет
в канал через бота. Ссылки на посты пишет в links.csv рядом с картинками.

Бот должен быть админом канала с правом публиковать сообщения.

Запуск (Windows):
    pip install pillow requests
    set BOT_TOKEN=...
    python post_stickers.py "C:\\Users\\admin\\Downloads\\combo"

Если прервать, повторный запуск продолжит с того места:
уже выложенные файлы из links.csv пропускаются.
"""
import csv
import getpass
import io
import os
import sys
import time

import requests
from PIL import Image

CHANNEL = os.environ.get("CHANNEL", "@skinsforfroggame")
MAX_BYTES = 512 * 1024
DELAY = 3.2  # каналы: не больше ~20 сообщений в минуту
EXTS = (".png", ".webp", ".jpg", ".jpeg")


def to_sticker(path: str) -> bytes:
    im = Image.open(path).convert("RGBA")
    im.thumbnail((512, 512), Image.LANCZOS)
    if max(im.size) != 512:  # мелкие тоже растягиваем: одна сторона ровно 512
        k = 512 / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    for q in (95, 90, 85, 80, 70, 60, 50):
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    raise ValueError("не удалось ужать до 512 КБ")


def send(token: str, data: bytes) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendSticker"
    while True:
        r = requests.post(
            url,
            data={"chat_id": CHANNEL},
            files={"sticker": ("s.webp", data, "image/webp")},
            timeout=60,
        ).json()
        if r.get("ok"):
            return r["result"]
        wait = (r.get("parameters") or {}).get("retry_after")
        if wait:
            print(f"  Telegram просит подождать {wait} с…")
            time.sleep(wait + 1)
            continue
        raise RuntimeError(r.get("description"))


def main():
    if len(sys.argv) < 2:
        sys.exit("Укажи папку с картинками: python post_stickers.py <папка>")
    folder = sys.argv[1]
    token = os.environ.get("BOT_TOKEN") or getpass.getpass("Токен бота: ").strip()

    out = os.path.join(folder, "links.csv")
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            done = {row[0] for row in csv.reader(f) if row}

    files = sorted(n for n in os.listdir(folder) if n.lower().endswith(EXTS))
    todo = [n for n in files if n not in done]
    print(f"Всего {len(files)}, уже выложено {len(done)}, осталось {len(todo)}")

    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for i, name in enumerate(todo, 1):
            try:
                msg = send(token, to_sticker(os.path.join(folder, name)))
            except Exception as e:
                print(f"[{i}/{len(todo)}] {name}: ОШИБКА {e}")
                continue
            chat = msg["chat"]
            if chat.get("username"):
                link = f"https://t.me/{chat['username']}/{msg['message_id']}"
            else:
                link = f"https://t.me/c/{str(chat['id'])[4:]}/{msg['message_id']}"
            w.writerow([name, msg["message_id"], link])
            f.flush()
            print(f"[{i}/{len(todo)}] {name} → {link}")
            time.sleep(DELAY)

    print(f"Готово. Ссылки в {out}")


if __name__ == "__main__":
    main()
