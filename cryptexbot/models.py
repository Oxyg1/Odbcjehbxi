"""List the Gemini models this API key can actually reach.

    python -m cryptexbot.models

Model ids move: Google retires them, and closes older ones to new keys, which
surfaces as a 404 naming a replacement. Rather than guessing from a changelog,
ask the key itself.
"""

from __future__ import annotations

import sys

from .config import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set in .env — nothing to list.")
        return 1

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        models = list(client.models.list())
    except Exception as error:  # noqa: BLE001 - this IS the diagnostic
        print(f"Could not list models: {error}")
        return 1

    usable = []
    for model in models:
        actions = getattr(model, "supported_actions", None) or []
        # Keep the ones this bot can actually call; some entries are
        # embedding-only or tuning-only.
        if actions and "generateContent" not in actions:
            continue
        usable.append(model)

    configured = settings.gemini_model
    print(f"Configured GEMINI_MODEL: {configured}\n")
    print(f"{len(usable)} model(s) available to this key for generateContent:\n")

    found = False
    for model in sorted(usable, key=lambda m: m.name or ""):
        name = (model.name or "").removeprefix("models/")
        mark = "  <- configured" if name == configured else ""
        if mark:
            found = True
        label = getattr(model, "display_name", "") or ""
        print(f"  {name:<40} {label}{mark}")

    if not found:
        print(
            f"\n⚠  {configured!r} is not in this list. Set GEMINI_MODEL in .env "
            "to one of the names above."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
