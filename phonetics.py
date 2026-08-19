"""Phonetic building blocks used by the generator to keep usernames pronounceable."""

import random

# Soft, pleasant-sounding consonants preferred across all styles.
SOFT_CONSONANTS = ["l", "m", "n", "s", "r", "v", "z"]

# Additional consonants allowed for variety, still easy to pronounce.
EXTRA_CONSONANTS = ["b", "c", "d", "f", "g", "k", "p", "t", "x"]

VOWELS = ["a", "e", "i", "o", "u"]

# Consonant clusters that remain easy to say (max 2 consonants together).
ALLOWED_ONSET_CLUSTERS = ["bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "st", "sn", "sk"]

# Style-specific syllable/root banks used to color the generated names.
STYLE_ROOTS: dict[str, list[str]] = {
    "elegant": ["lum", "vio", "nex", "sil", "aur", "cel", "ely", "ori", "vel", "sen"],
    "brand": ["pix", "zen", "aur", "nov", "vex", "lux", "qub", "dyn", "syn", "rok"],
    "mythic": ["zeph", "thal", "nyx", "orin", "sylv", "drak", "elun", "morg", "vael", "thys"],
    "tech": ["neu", "bit", "lux", "quant", "cyb", "vec", "byte", "sys", "log", "cor"],
    "vibes": ["blis", "sol", "lum", "joy", "vel", "har", "mira", "kai", "lira", "wave"],
}

# Style-specific suffixes to close out the name.
STYLE_SUFFIXES: dict[str, list[str]] = {
    "elegant": ["a", "o", "en", "is", "ora"],
    "brand": ["ora", "ix", "trix", "on", "ify"],
    "mythic": ["ra", "ion", "yra", "ael", "oth"],
    "tech": ["on", "ix", "lux", "core", "byte"],
    "vibes": ["o", "a", "x", "ly", "ova"],
}


def is_pronounceable(word: str) -> bool:
    """Reject words with awkward consonant clusters (more than 2 consonants in a row)."""
    run = 0
    for ch in word:
        if ch in VOWELS:
            run = 0
        else:
            run += 1
            if run > 2:
                return False
    return True


def random_syllable(rng: random.Random) -> str:
    """Build a single CV or CVC syllable from pleasant sounds."""
    consonant_pool = SOFT_CONSONANTS + EXTRA_CONSONANTS
    onset = rng.choice(consonant_pool)
    vowel = rng.choice(VOWELS)
    syllable = onset + vowel
    if rng.random() < 0.35:
        coda = rng.choice(SOFT_CONSONANTS)
        syllable += coda
    return syllable
