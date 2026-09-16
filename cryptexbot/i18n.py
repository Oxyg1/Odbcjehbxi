"""Interface strings in every language the bot speaks.

Only chrome lives here — buttons, labels, status lines. The puzzle text
(theme, riddle, clues) is generated per vault in *both* languages at once and
carried in the vault's own state, because a translation made after the fact
would not be guaranteed to point at the same digits.
"""

from __future__ import annotations

LANGS = ("en", "ru")
DEFAULT_LANG = "en"

LANG_NAMES = {"en": "🇬🇧 English", "ru": "🇷🇺 Русский"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "choose_language": (
            "🔒 <b>THE CRYPTEX VAULT</b>\n\n"
            "Choose your language to begin.\n"
            "Выберите язык, чтобы начать."
        ),
        "sealing_title": "🔒 <b>THE CRYPTEX VAULT</b>",
        "sealing_body": (
            "<i>Steel is cooling, tumblers are being set…</i>\n\n"
            "A new vault is being sealed for you, and a riddle is being "
            "written around its combination."
        ),
        "tap_hint": (
            "Tap a dial to turn it one notch. Line up the right combination "
            "and the vault opens."
        ),
        "dials": "Dials",
        "turns": "Turns",
        "reset_button": "🔄 Reset dials",
        "reset_done": "Dials spun back to zero.",
        "lang_button": "🌐 Русский",
        "lang_switched": "Language switched to English.",
        "open_button": "🔓 VAULT OPEN",
        "already_open": "Already open.",
        "still_sealing": "The vault is still being sealed. One moment.",
        "rusted_shut": "This vault has rusted shut. Send /vault for a new one.",
        "click": "🔓 Click.",
        "accepted": "Combination <code>{code}</code> accepted after {turns} turns.",
        "reaching_inside": "<i>Reaching inside…</i>",
        "empty_vault": (
            "The vault is empty. Whatever was here, someone got to it first."
        ),
        "static_reward": (
            "The door gives, and {theme} exhales dust into the light. "
            "Whatever was worth guarding is still here, and it is yours."
        ),
        "lang_prompt_done": "English it is.",
        "cmd_vault": "Open a fresh vault",
        "cmd_lang": "Change language",
    },
    "ru": {
        "choose_language": (
            "🔒 <b>СЕЙФ «КРИПТЕКС»</b>\n\n"
            "Выберите язык, чтобы начать.\n"
            "Choose your language to begin."
        ),
        "sealing_title": "🔒 <b>СЕЙФ «КРИПТЕКС»</b>",
        "sealing_body": (
            "<i>Сталь остывает, штифты встают на место…</i>\n\n"
            "Для вас запирают новый сейф, а вокруг его комбинации "
            "пишут загадку."
        ),
        "tap_hint": (
            "Нажмите на диск, чтобы повернуть его на щелчок. Соберите верную "
            "комбинацию — и сейф откроется."
        ),
        "dials": "Диски",
        "turns": "Поворотов",
        "reset_button": "🔄 Сбросить диски",
        "reset_done": "Диски отмотаны на ноль.",
        "lang_button": "🌐 English",
        "lang_switched": "Язык переключён на русский.",
        "open_button": "🔓 СЕЙФ ОТКРЫТ",
        "already_open": "Уже открыт.",
        "still_sealing": "Сейф ещё запирают. Секунду.",
        "rusted_shut": "Этот сейф заржавел. Отправьте /vault, чтобы получить новый.",
        "click": "🔓 Щелчок.",
        "accepted": "Комбинация <code>{code}</code> принята после {turns} поворотов.",
        "reaching_inside": "<i>Тянетесь внутрь…</i>",
        "empty_vault": "Сейф пуст. Что бы здесь ни лежало, до него добрались раньше.",
        "static_reward": (
            "Дверь поддаётся, и {theme} выдыхает пыль на свет. "
            "То, что стоило беречь, всё ещё здесь — и теперь оно ваше."
        ),
        "lang_prompt_done": "Отлично, говорим по-русски.",
        "cmd_vault": "Открыть новый сейф",
        "cmd_lang": "Сменить язык",
    },
}

# Dial labels. Never digits: printing "1." beside a puzzle whose answer is a
# digit is asking to be misread.
ORDINALS: dict[str, list[str]] = {
    "en": ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"],
    "ru": ["Первый", "Второй", "Третий", "Четвёртый", "Пятый", "Шестой", "Седьмой", "Восьмой"],
}


def normalize(lang: str | None) -> str:
    """Any unknown or missing language falls back to the default."""
    return lang if lang in LANGS else DEFAULT_LANG


def t(lang: str | None, key: str, **kwargs) -> str:
    """Look up a string, falling back to English if a key is ever missing."""
    code = normalize(lang)
    text = STRINGS[code].get(key) or STRINGS[DEFAULT_LANG].get(key, key)
    return text.format(**kwargs) if kwargs else text


def ordinal(lang: str | None, index: int) -> str:
    names = ORDINALS[normalize(lang)]
    return names[index] if index < len(names) else f"#{index + 1}"


def other_lang(lang: str | None) -> str:
    """The language the toggle button switches to (two languages, so: the other)."""
    return "ru" if normalize(lang) == "en" else "en"
