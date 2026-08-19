"""Generates pronounceable, memorable @username candidates in different styles."""

import random
import re

from phonetics import (
    STYLE_ROOTS,
    STYLE_SUFFIXES,
    VOWELS,
    is_pronounceable,
    random_syllable,
)

VALID_STYLES = ("elegant", "brand", "mythic", "tech", "vibes")

MIN_LENGTH = 5
MAX_LENGTH = 20

# Preset length ranges offered to the user, all within [MIN_LENGTH, MAX_LENGTH].
LENGTH_PRESETS: list[tuple[str, int, int]] = [
    ("5-8", 5, 8),
    ("9-12", 9, 12),
    ("13-16", 13, 16),
    ("17-20", 17, 20),
]

_VALID_USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$")


def _build_candidate(style: str, min_length: int, max_length: int, rng: random.Random) -> str:
    root = rng.choice(STYLE_ROOTS[style])
    suffix = rng.choice(STYLE_SUFFIXES[style])

    name = root + suffix
    if name[-1] not in VOWELS and rng.random() < 0.3:
        name += rng.choice(VOWELS)

    # Splice in extra syllables (accumulating, not replacing) until long enough.
    while len(name) < min_length:
        name = root + random_syllable(rng) + name[len(root):]

    while len(name) < max_length and rng.random() < 0.5:
        name += random_syllable(rng)

    return name.lower()


def generate_username(
    style: str,
    rng: random.Random | None = None,
    min_length: int = MIN_LENGTH,
    max_length: int = MAX_LENGTH,
) -> str:
    if style not in VALID_STYLES:
        raise ValueError(f"Unknown style '{style}'. Valid styles: {', '.join(VALID_STYLES)}")
    if not MIN_LENGTH <= min_length <= max_length <= MAX_LENGTH:
        raise ValueError(f"Invalid length range {min_length}-{max_length}")

    rng = rng or random.Random()
    for _ in range(50):
        candidate = _build_candidate(style, min_length, max_length, rng)
        if min_length <= len(candidate) <= max_length and is_pronounceable(candidate):
            return candidate

    # Fallback: trim/pad so we always return something valid.
    candidate = _build_candidate(style, min_length, max_length, rng)
    return candidate[:max_length].ljust(min_length, "o")


def generate_usernames(
    style: str,
    count: int,
    min_length: int = MIN_LENGTH,
    max_length: int = MAX_LENGTH,
    seed: int | None = None,
) -> list[str]:
    if not 1 <= count <= 20:
        raise ValueError("count must be between 1 and 20")

    rng = random.Random(seed)
    seen: set[str] = set()
    results: list[str] = []

    attempts = 0
    max_attempts = count * 20
    while len(results) < count and attempts < max_attempts:
        attempts += 1
        name = generate_username(style, rng, min_length, max_length)
        if name in seen:
            continue
        seen.add(name)
        results.append(name)

    # If phonetic generation couldn't produce enough unique names, pad with numeric variants.
    base_index = 0
    bases = list(results) or [generate_username(style, rng, min_length, max_length)]
    while len(results) < count:
        base = bases[base_index % len(bases)]
        variant = f"{base}{rng.randint(1, 99)}"
        if variant not in seen and len(variant) <= max_length:
            seen.add(variant)
            results.append(variant)
        base_index += 1

    return results


def is_valid_telegram_username(username: str) -> bool:
    return bool(_VALID_USERNAME_RE.match(username))
