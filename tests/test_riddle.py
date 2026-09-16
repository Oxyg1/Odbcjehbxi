"""The solvability guarantees: local code, leak scanning, clue repair.

Run with:  python tests/test_riddle.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptexbot.i18n import LANGS  # noqa: E402
from cryptexbot.services.quests import (  # noqa: E402
    DIGIT_CLUES,
    coerce_quest,
    leaks_digit,
    local_clue,
    local_quest,
    random_code,
    sanitize_clues,
    strip_numerals,
)


def main() -> None:
    # --- the code comes from Python, and it is uniform --------------------- #
    codes = [random_code(3) for _ in range(3000)]
    assert all(len(c) == 3 and all(0 <= d <= 9 for d in c) for c in codes)
    spread = Counter(d for c in codes for d in c)
    assert len(spread) == 10, spread
    assert min(spread.values()) > 600, spread  # ~900 expected per digit
    print("ok  codes are generated locally and cover all ten digits")

    # --- the local clue bank passes its own leak scan, in every language --- #
    for lang in LANGS:
        assert set(DIGIT_CLUES[lang]) == set(range(10)), lang
        for digit, clues in DIGIT_CLUES[lang].items():
            for clue in clues:
                assert not leaks_digit(clue, digit), (lang, digit, clue)
                assert not any(ch.isdigit() for ch in clue), clue
    print("ok  every local clue is leak-free for its own digit, in both languages")

    # --- Russian number names are caught in their case forms ---------------- #
    assert leaks_digit("Сосчитайте семь ламп.", 7)
    assert leaks_digit("Седьмая лампа горит.", 7)
    assert leaks_digit("Не хватает семи ламп.", 7)
    assert leaks_digit("Пять пальцев в перчатке.", 5)
    assert leaks_digit("Вторая дверь заперта.", 2)
    assert leaks_digit("Комната 12 запечатана.", 3), "любая цифра — утечка"
    assert leaks_digit("Сосчитайте дни недели.", 7) is False
    assert leaks_digit("Пара перчаток лежит там.", 2) is False, "приёмы счёта разрешены"
    print("ok  Russian cardinals and ordinals register as leaks in their case forms")

    # --- leak detection ---------------------------------------------------- #
    assert leaks_digit("Count the 7 lamps.", 7)
    assert leaks_digit('The tag reads "7".', 7)
    assert leaks_digit("Count the seven lamps.", 7)
    assert leaks_digit("The seventh lamp is lit.", 7)
    assert leaks_digit("SEVEN lamps burn.", 7)
    assert leaks_digit("Room 12 is sealed.", 3), "any numeral is a leak"
    assert leaks_digit("Nothing remains.", 0) is False
    assert leaks_digit("Count the days in a week.", 7) is False
    assert leaks_digit("A pair of gloves lies there.", 2) is False, "devices are allowed"
    assert leaks_digit("None survived.", 0), "naming zero counts"
    print("ok  numerals, quoted digits, names and ordinals all register as leaks")

    # --- cleaning where cleaning is possible ------------------------------- #
    assert strip_numerals("Room 12 is sealed.") == "Room is sealed."
    assert strip_numerals('The tag reads "7".') == "The tag reads."
    cleaned, replaced = sanitize_clues(["Count the 4 seasons the almanac names."], [4], "en")
    assert replaced == [], "a stray numeral should be cleaned, not replaced"
    assert "4" not in cleaned[0] and "seasons" in cleaned[0]
    print("ok  an incidental numeral is stripped, keeping the model's prose")

    # --- replacement where cleaning cannot save it ------------------------- #
    cleaned, replaced = sanitize_clues(["Count the seven days.", ""], [7, 3], "en")
    assert replaced == [0, 1], replaced
    assert cleaned[0] in DIGIT_CLUES["en"][7], "a named digit is replaced by a correct clue"
    assert cleaned[1] in DIGIT_CLUES["en"][3], "a missing clue is filled in"

    ru_cleaned, ru_replaced = sanitize_clues(["Сосчитайте семь дней.", ""], [7, 3], "ru")
    assert ru_replaced == [0, 1]
    assert ru_cleaned[0] in DIGIT_CLUES["ru"][7], "the replacement matches the language"
    assert ru_cleaned[1] in DIGIT_CLUES["ru"][3]
    print("ok  a clue that names its digit is replaced by a known-correct one")

    # --- the list is always the right length ------------------------------- #
    for raw in ([], ["a"], ["a", "b", "c", "d", "e"], "not a list"):
        clues, _ = sanitize_clues(
            list(raw) if isinstance(raw, list) else [], [1, 2, 3], "ru"
        )
        assert len(clues) == 3, raw
    print("ok  clue count always matches the dial count")

    # --- coerce_quest never takes the code from the model ------------------ #
    code = [7, 3, 2]
    quest = coerce_quest(
        {
            "code": [9, 9, 9],
            "theme_en": "a vault", "riddle_en": "Dust.",
            "clues_en": ["Count the days in a week.", "Count the stool's legs.", "Count the oars."],
            "theme_ru": "сейф", "riddle_ru": "Пыль.",
            "clues_ru": ["Сосчитайте дни недели.", "Сосчитайте ножки табурета.", "Сосчитайте вёсла."],
        },
        code,
    )
    assert quest.code == [7, 3, 2], "a model-supplied code must be ignored"
    for lang in LANGS:
        assert len(quest.clues[lang]) == 3, lang
        assert quest.theme[lang] and quest.riddle[lang], lang
    assert quest.theme["ru"] == "сейф"
    assert quest.clues["ru"][0] == "Сосчитайте дни недели."
    print("ok  a 'code' field is ignored; both languages are carried through")

    # --- one language can be broken without harming the other -------------- #
    quest = coerce_quest(
        {
            "theme_en": "a vault", "riddle_en": "Dust.",
            "clues_en": ["Count the days in a week.", "Count the legs.", "Count the oars."],
            "clues_ru": ["Сосчитайте семь дней.", "", None],   # leaks, empty, junk
        },
        [7, 3, 2],
    )
    assert quest.clues["en"][0] == "Count the days in a week.", "English survives intact"
    for clue, digit in zip(quest.clues["ru"], [7, 3, 2]):
        assert clue in DIGIT_CLUES["ru"][digit], "Russian is repaired from the local bank"
    print("ok  a broken clue set in one language leaves the other untouched")

    # --- the framing line is scrubbed too ---------------------------------- #
    quest = coerce_quest(
        {"theme_en": "t", "riddle_en": "The safe holds 3 ledgers.", "clues_en": ["a", "b", "c"],
         "riddle_ru": "В сейфе 3 гроссбуха."},
        [1, 2, 3],
    )
    assert "3" not in quest.riddle["en"] and "3" not in quest.riddle["ru"]
    quest = coerce_quest(
        {"theme_en": "t", "riddle_en": "Three ledgers, all burned.", "clues_en": ["a", "b", "c"],
         "riddle_ru": "Три гроссбуха, все сгорели."},
        [1, 2, 3],
    )
    assert "Three" not in quest.riddle["en"], "framing that names a code digit is swapped"
    assert "Три" not in quest.riddle["ru"], "same rule applies to Russian framing"
    print("ok  the framing riddle cannot leak the combination in either language")

    # --- garbage still yields a playable vault ----------------------------- #
    for raw in ("", "prose", ["a"], {"clues_en": "not a list"}, None):
        quest = coerce_quest(raw, [4, 0, 8])
        assert quest.code == [4, 0, 8]
        for lang in LANGS:
            assert len(quest.clues[lang]) == 3 and all(quest.clues[lang]), (raw, lang)
            assert quest.theme[lang] and quest.riddle[lang], (raw, lang)
            for clue, digit in zip(quest.clues[lang], quest.code):
                assert not leaks_digit(clue, digit)
    print("ok  any malformed response still yields a leak-free, solvable vault")

    # --- offline quests are solvable by construction ------------------------ #
    for _ in range(200):
        quest = local_quest(random_code(3))
        for lang in LANGS:
            for clue, digit in zip(quest.clues[lang], quest.code):
                assert clue in DIGIT_CLUES[lang][digit], (lang, clue, digit)
    assert local_clue(5, "en", avoid=DIGIT_CLUES["en"][5][0]) == DIGIT_CLUES["en"][5][1]
    assert local_clue(5, "ru", avoid=DIGIT_CLUES["ru"][5][0]) == DIGIT_CLUES["ru"][5][1]
    print("ok  offline quests draw correct clues in both languages")

    # --- both languages describe the same combination ---------------------- #
    for _ in range(50):
        quest = local_quest(random_code(3))
        assert len(quest.clues["en"]) == len(quest.clues["ru"]) == len(quest.code)
    print("ok  the two languages always describe the same vault")

    print("\nall checks passed")


if __name__ == "__main__":
    main()
