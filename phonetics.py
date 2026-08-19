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
# Kept fairly large (~3x the original set) so the root x suffix combinatorial space
# doesn't run dry quickly, especially at short requested lengths where most
# combinations get filtered out and only a handful of unique candidates remain.
STYLE_ROOTS: dict[str, list[str]] = {
    "elegant": [
        "lum", "vio", "nex", "sil", "aur", "cel", "ely", "ori", "vel", "sen",
        "lyr", "opa", "ser", "nov", "iri", "lun", "ari", "ver", "nor", "cyr",
        "amel", "brio", "cato", "desi", "ilva", "juno", "kira", "livi", "myra", "tera",
    ],
    "brand": [
        "pix", "zen", "aur", "nov", "vex", "lux", "qub", "dyn", "syn", "rok",
        "flux", "apex", "onyx", "echo", "axis", "kade", "nira", "zyra", "vira", "coro",
        "brix", "kalo", "moxa", "plux", "quix", "ravo", "solex", "trex", "unix", "voxa",
    ],
    "mythic": [
        "zeph", "thal", "nyx", "orin", "sylv", "drak", "elun", "morg", "vael", "thys",
        "wyrm", "fenr", "loki", "odin", "thor", "frey", "hela", "tyra", "gorn", "ymir",
        "azra", "bael", "corv", "dusk", "ekho", "grim", "ishtar", "krag", "luna", "sear",
    ],
    "tech": [
        "neu", "bit", "lux", "quant", "cyb", "vec", "byte", "sys", "log", "cor",
        "data", "pixl", "nano", "grid", "code", "node", "chip", "wire", "volt", "sig",
        "apex", "boot", "core", "flux", "kern", "link", "mesh", "proc", "stak", "vect",
    ],
    "vibes": [
        "blis", "sol", "lum", "joy", "vel", "har", "mira", "kai", "lira", "wave",
        "glow", "aura", "echo", "luma", "nova", "sere", "calm", "peac", "free", "brez",
        "cozy", "driz", "fizz", "hush", "loop", "mist", "puls", "rime", "tide", "zephy",
    ],
}

# Style-specific suffixes to close out the name.
STYLE_SUFFIXES: dict[str, list[str]] = {
    "elegant": ["a", "o", "en", "is", "ora", "elle", "ique", "ara", "ine", "yth"],
    "brand": ["ora", "ix", "trix", "on", "ify", "ity", "exa", "yze", "ara", "eo"],
    "mythic": ["ra", "ion", "yra", "ael", "oth", "wyn", "dor", "mir", "lok", "fen"],
    "tech": ["on", "ix", "lux", "core", "byte", "flow", "sync", "hub", "net", "dev"],
    "vibes": ["o", "a", "x", "ly", "ova", "ia", "ee", "oh", "ish", "y"],
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
