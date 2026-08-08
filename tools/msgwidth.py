"""
Ширина сообщений бота: помещается ли строка на экран телефона без переноса.

Мерка снята с реального устройства: в строку без переноса влезает 21 самая
широкая буква — 21×W. Всё меряется в этих W-единицах, потому что абсолютные
пиксели зависят от устройства и шрифта, а отношение ширины строки к ширине W
почти нет.

Таблица ширин снята в Chromium на Liberation Sans (метрически совместим с
Arial; отношение W к среднему символу близко к Roboto и SF Pro, которыми
Telegram рисует сообщения на Android и iOS).

Запуск:
    python3 tools/msgwidth.py            проверить все тексты bot.py
    python3 tools/msgwidth.py "строка"   померить одну строку
"""
import json
import re
import sys
import unicodedata

# ── Мерка ────────────────────────────────────────────────────────────────────
HARD_LIMIT = 21.0   # больше — гарантированный перенос
SAFE_LIMIT = 19.0   # рабочий предел: запас на другие шрифты и отступы пузыря
BTN_FULL_LIMIT = 19.0  # кнопка на всю ширину ряда
BTN_HALF_LIMIT = 9.5   # кнопка в ряду из двух — обрезается многоточием

# Ширина символа в долях W
CHAR_W = {
    0.202: "'",
    0.235: 'ijl',
    0.275: '|',
    0.276: 'f',
    0.294: ' !,./:;I[\\]t',
    0.353: '()-r·',
    0.354: '{}',
    0.376: '"',
    0.386: 'г',
    0.412: '*',
    0.464: 'к',
    0.474: 'з',
    0.485: 'т',
    0.514: '1',
    0.53: 'Jcksvxyzсух',
    0.541: 'э',
    0.552: 'чь',
    0.563: 'в',
    0.574: 'Гпя',
    0.582: '÷',
    0.585: 'н',
    0.589: '#023456789?Labdeghnopqu«»аеорё–',
    0.592: 'ий',
    0.607: 'бц',
    0.617: 'К',
    0.618: 'дл',
    0.619: '+=×',
    0.64: 'З',
    0.647: 'FTZТ',
    0.662: 'ъ',
    0.673: 'У',
    0.695: 'БЛЬ',
    0.706: 'Ч',
    0.707: 'ABEKPSVXYЁАВЕРХ',
    0.709: 'ж',
    0.718: 'Д',
    0.728: 'м',
    0.751: '█░▒',
    0.761: 'ИЙПЭы',
    0.765: 'CDHNRUwНСЯ',
    0.772: '▓',
    0.784: 'Ц',
    0.794: 'ю',
    0.805: 'Ф',
    0.824: 'GOQО',
    0.839: 'Ъ',
    0.85: 'ш',
    0.872: 'фщ',
    0.882: 'MmМ',
    0.938: 'Ы',
    0.942: '%',
    0.971: 'Ш',
    0.978: 'Ж',
    0.993: 'Щ',
    1.0: 'W',
    1.059: '—…',
    1.07: 'Ю',
    1.075: '@',
    1.137: '№',
}

BOLD_FACTOR = 1.049      # <b> шире обычного начертания
MONO_W      = 0.64       # символ в <code> (моноширинный)
EMOJI_W     = 1.32       # цветная эмодзи, включая ZWJ-последовательности
DEFAULT_W   = 0.60       # неизвестный символ — по средней кириллице

# Раскрываем таблицу групп в посимвольный словарь
_W = {}
for _val, _chars in CHAR_W.items():
    for _c in _chars:
        _W[_c] = _val

_TAG = re.compile(r"<(/?)(\w[\w-]*)[^>]*>")
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return (
        0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
        or 0x1F000 <= o <= 0x1F2FF or o in (0x2B50, 0x2B55, 0x203C, 0x2049)
        or 0xFE00 <= o <= 0xFE0F or o == 0x200D
    )


def width_w(text: str, placeholder_len: int = 4) -> float:
    """
    Ширина строки в W-единицах.

    HTML-теги не рисуются и в ширину не идут, но <b> и <code> меняют
    начертание внутри. Подстановки {...} считаются как placeholder_len
    обычных символов — точную длину статически знать нельзя.
    """
    text = _PLACEHOLDER.sub("\uE000" * placeholder_len, text)

    total = 0.0
    bold = 0
    mono = 0
    i = 0
    while i < len(text):
        m = _TAG.match(text, i)
        if m:
            closing, name = m.group(1), m.group(2).lower()
            if name in ("b", "strong"):
                bold += -1 if closing else 1
            elif name in ("code", "pre"):
                mono += -1 if closing else 1
            i = m.end()
            continue

        ch = text[i]

        # Эмодзи может быть склейкой из нескольких кодовых точек
        if _is_emoji(ch):
            j = i + 1
            while j < len(text) and _is_emoji(text[j]):
                j += 1
            total += EMOJI_W
            i = j
            continue

        if ch == "\uE000":            # подстановка
            total += DEFAULT_W
        elif mono > 0:
            total += MONO_W
        else:
            w = _W.get(ch, DEFAULT_W)
            total += w * (BOLD_FACTOR if bold > 0 else 1.0)
        i += 1
    return total


def fits(text: str, limit: float = SAFE_LIMIT) -> bool:
    """Помещается ли строка целиком, без переноса."""
    return all(width_w(line) <= limit for line in text.split("\n"))


def budget(text: str) -> str:
    """Человекочитаемый вердикт по строке."""
    w = width_w(text)
    if w > HARD_LIMIT:
        return f"{w:.1f}W ПЕРЕНОС (предел {HARD_LIMIT:.0f})"
    if w > SAFE_LIMIT:
        return f"{w:.1f}W впритык (запас {HARD_LIMIT - w:.1f}W)"
    return f"{w:.1f}W ок"


# ── Проверка исходника ───────────────────────────────────────────────────────
#
# Переносится не всё одинаково. Обычная фраза переносится и читается нормально —
# ломается только то, где положение символа несёт смысл:
#   • строки с разделителем « · » — это колонки, перенос рвёт их посередине;
#   • полосы прогресса в <code> — перенос ломает выравнивание столбика;
#   • заголовки со счётчиком — уезжает хвост;
#   • подписи кнопок — Telegram обрезает их многоточием, а не переносит.
# Поэтому проверяем именно такие строки, а повествовательные тексты пропускаем.

_SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|WHERE|FROM|JOIN)\b")
_ESCAPED = re.compile(r"\\u[0-9a-fA-F]{4}")
_BAR = re.compile(r"[█░▓▒]")


_SENTENCE = re.compile(r"[.!?]\s+[А-ЯЁA-Z]|[а-яё]{4,}\s+[а-яё]{4,}\s+[а-яё]{4,}")


def _is_structural(s: str) -> bool:
    """
    Строка, для которой перенос — дефект, а не норма.

    Колонка отличается от фразы тем, что в ней нет связного текста: подряд
    идущие длинные слова или граница предложения выдают прозу, и её перенос
    ничего не ломает.
    """
    plain = re.sub(r"<[^>]+>", "", s)
    if _SENTENCE.search(plain):
        return False
    return " · " in s or bool(_BAR.search(s))


def scan(path: str = "bot.py"):
    """
    Возвращает (структурные_переносы, длинные_кнопки).

    Кнопкам достаётся меньше места, чем сообщению: у ряда из двух кнопок
    на каждую приходится примерно половина ширины.
    """
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()

    struct, buttons = [], []
    for m in re.finditer(r'(?:f|rf|fr)?"((?:[^"\\\n]|\\.)*)"', src):
        raw = m.group(1)
        if len(raw) < 8 or _SQL.search(raw) or _ESCAPED.search(raw):
            continue
        line_no = src[: m.start()].count("\n") + 1
        ctx = lines[line_no - 1] if line_no <= len(lines) else ""

        # Подпись кнопки?
        is_btn = "InlineKeyboardButton(" in ctx or re.search(r"\bbtn\(", ctx)

        for part in raw.split("\\n"):
            part = part.strip()
            if not part:
                continue
            w = width_w(part)
            if is_btn:
                if w > BTN_HALF_LIMIT:
                    buttons.append((line_no, w, part))
                    continue
            elif w > HARD_LIMIT and _is_structural(part):
                struct.append((line_no, w, part))

    struct.sort(key=lambda x: -x[1])
    buttons.sort(key=lambda x: -x[1])
    return struct, buttons


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            print(f"{budget(arg):<28} {arg}")
        sys.exit(0)

    struct, buttons = scan()
    print(f"Мерка: {HARD_LIMIT:.0f}W — перенос, {SAFE_LIMIT:.0f}W — рабочий предел,")
    print(f"       {BTN_HALF_LIMIT:.1f}W — кнопка в ряду из двух\n")

    print(f"── Выровненные строки, которые порвёт переносом: {len(struct)}")
    for line_no, w, part in struct[:25]:
        print(f"   bot.py:{line_no:<6} {w:5.1f}W  {part[:74]}")

    hard = [b for b in buttons if b[1] > BTN_FULL_LIMIT]
    soft = [b for b in buttons if b[1] <= BTN_FULL_LIMIT]
    print(f"\n── Кнопки длиннее {BTN_FULL_LIMIT:.0f}W — обрежет в любом ряду: {len(hard)}")
    for line_no, w, part in hard[:15]:
        print(f"   bot.py:{line_no:<6} {w:5.1f}W  {part[:74]}")
    print(f"\n── Кнопки {BTN_HALF_LIMIT:.1f}–{BTN_FULL_LIMIT:.0f}W — только на всю ширину ряда: {len(soft)}")

    sys.exit(1 if struct else 0)
