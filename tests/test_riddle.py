"""The solvability guarantees: local code, leak scanning, clue repair.

Run with:  python tests/test_riddle.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

    # --- the local clue bank passes its own leak scan ---------------------- #
    for digit, clues in DIGIT_CLUES.items():
        for clue in clues:
            assert not leaks_digit(clue, digit), (digit, clue)
            # and must not leak any other digit's numeral either
            assert not any(ch.isdigit() for ch in clue), clue
    print("ok  every local clue is leak-free for its own digit")

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
    cleaned, replaced = sanitize_clues(["Count the 4 seasons the almanac names."], [4])
    assert replaced == [], "a stray numeral should be cleaned, not replaced"
    assert "4" not in cleaned[0] and "seasons" in cleaned[0]
    print("ok  an incidental numeral is stripped, keeping the model's prose")

    # --- replacement where cleaning cannot save it ------------------------- #
    cleaned, replaced = sanitize_clues(["Count the seven days.", ""], [7, 3])
    assert replaced == [0, 1], replaced
    assert cleaned[0] in DIGIT_CLUES[7], "a named digit is replaced by a correct clue"
    assert cleaned[1] in DIGIT_CLUES[3], "a missing clue is filled in"
    print("ok  a clue that names its digit is replaced by a known-correct one")

    # --- the list is always the right length ------------------------------- #
    for raw in ([], ["a"], ["a", "b", "c", "d", "e"], "not a list"):
        clues, _ = sanitize_clues(list(raw) if isinstance(raw, list) else [], [1, 2, 3])
        assert len(clues) == 3, raw
    print("ok  clue count always matches the dial count")

    # --- coerce_quest never takes the code from the model ------------------ #
    code = [7, 3, 2]
    quest = coerce_quest(
        {"code": [9, 9, 9], "theme": "a vault", "riddle": "Dust.",
         "clues": ["Count the days in a week.", "Count the stool's legs.", "Count the oars."]},
        code,
    )
    assert quest.code == [7, 3, 2], "a model-supplied code must be ignored"
    assert len(quest.clues) == 3
    print("ok  a 'code' field in the model's output is ignored outright")

    # --- the framing line is scrubbed too ---------------------------------- #
    quest = coerce_quest(
        {"theme": "t", "riddle": "The safe holds 3 ledgers.", "clues": ["a", "b", "c"]},
        [1, 2, 3],
    )
    assert "3" not in quest.riddle
    quest = coerce_quest(
        {"theme": "t", "riddle": "Three ledgers, all burned.", "clues": ["a", "b", "c"]},
        [1, 2, 3],
    )
    assert "Three" not in quest.riddle, "framing that names a code digit is swapped"
    print("ok  the framing riddle cannot leak the combination either")

    # --- garbage still yields a playable vault ----------------------------- #
    for raw in ("", "prose", ["a"], {"clues": "not a list"}, None):
        quest = coerce_quest(raw, [4, 0, 8])
        assert quest.code == [4, 0, 8]
        assert len(quest.clues) == 3 and all(quest.clues)
        assert quest.theme and quest.riddle
        for clue, digit in zip(quest.clues, quest.code):
            assert not leaks_digit(clue, digit)
    print("ok  any malformed response still yields a leak-free, solvable vault")

    # --- offline quests are solvable by construction ------------------------ #
    for _ in range(200):
        quest = local_quest(random_code(3))
        for clue, digit in zip(quest.clues, quest.code):
            assert clue in DIGIT_CLUES[digit], (clue, digit)
    assert local_clue(5, avoid=DIGIT_CLUES[5][0]) == DIGIT_CLUES[5][1]
    print("ok  offline quests draw correct clues, avoiding repeats where it can")

    print("\nall checks passed")


if __name__ == "__main__":
    main()
