# CryptexBot

A single-message interactive puzzle box for Telegram: a locked vault with three
dials, built on **aiogram 3.x** and **Gemini** (`google-genai`).

Every vault is generated at run time. The combination exists nowhere in the
source — Gemini invents the code, the theme and the riddle when you type
`/vault`, and narrates what is inside when you crack it, streamed into the
message as it writes.

The bot sends **exactly one message per vault**. Every interaction after that —
turning a dial, resetting, opening the safe, revealing the prize — edits that
same message. No replies, no follow-ups, no notification spam.

```
/vault  ->  [photo: locked safe]
            🔒 THE CRYPTEX VAULT
            Steel is cooling, tumblers are being set…      <- Gemini is working
            (no keyboard yet: there is no combination to tap)

            ... same message, edited once the quest lands ...

            🔒 A DROWNED OBSERVATORY
            Salt has eaten the brass, but the tide still keeps time.
            Dials: 0 0 0
            [0️⃣] [0️⃣] [0️⃣]
            [🔄 Reset dials]

            ... taps edit the keyboard in place ...

            [photo swaps to open safe]
            🔓 A DROWNED OBSERVATORY
            Combination 4-0-8 accepted after 31 turns.
            You step into green light, and the telescope is still▌   <- streaming
            [🔓 VAULT OPEN]
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # BOT_TOKEN from @BotFather, GEMINI_API_KEY from AI Studio
python main.py
```

Get a Gemini key at <https://aistudio.google.com/apikey>. Without one the bot
still runs: codes are generated locally and the reveal falls back to
`STATIC_REWARD`, so you can develop the Telegram side offline.

Send `/vault` to start. The artwork is generated with Pillow on first run into
`assets/generated/` — no image assets to ship.

Run the tests (no token, no API key, no network):

```bash
python tests/test_flow.py      # the Telegram interaction, against a stub Bot
python tests/test_gemini.py    # the Gemini providers, against a fake SDK client
```

## How the Zero-Spam loop works

| Event | Bot API call | Why |
|---|---|---|
| `/vault` | `sendPhoto` | The only message ever sent. Goes out **before** the Gemini call, with no keyboard — an instant sealed vault beats a silent bot. |
| Quest arrives | `editMessageCaption` | Riddle in, dials attached. Still the same message. |
| Dial tap | `editMessageReplyMarkup` | Markup-only: the dial face flips with **no media reload and no flash**. Editing the caption or media here is what makes other bots blink. |
| Correct code | `editMessageMedia` | Swaps to the open-safe photo and the reveal caption, once. |
| Reward text | `editMessageCaption` | One edit for static text; a throttled stream for LLM text. |

The first `sendPhoto` returns a `file_id`, which is cached in
`ArtworkProvider`. Every later vault sends that string instead of re-uploading
the PNG, so spawning a vault is a pure metadata call.

## Layout

```
main.py                        entrypoint
cryptexbot/
  config.py                    env-backed settings (token, code, backends)
  state.py                     VaultState + StateStore (memory / Redis)
  keyboards.py                 the combination lock keyboard
  bot.py                       wiring and dependency injection
  handlers/
    vault.py                   /vault, dial turns, reset, the unlock event
    errors.py                  catch-all so one bad update can't stop polling
  services/
    artwork.py                 Pillow safe frames + file_id cache
    quests.py                  Quest interface, validation, offline generator
    rewards.py                 reveal interface, static + fallback providers
    gemini.py                  <- both Gemini calls live here, and only here
    safe_calls.py              CallbackQuery / edit error handling
tests/
  test_flow.py                 Telegram interaction, stub Bot
  test_gemini.py               Gemini providers, fake SDK client
```

## The two Gemini calls

Both live in `services/gemini.py`. They are deliberately different shapes.

### 1. Quest generation — one blocking call, JSON mode

`GeminiQuestProvider.generate()` sends a `response_schema`, so the model
returns parseable JSON rather than prose we would have to regex out of a
code fence:

```python
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    response_mime_type="application/json",
    response_schema=_quest_schema(dial_count),   # {"code": [x,y,z], "theme", "riddle"}
    temperature=1.4,                              # vaults must not converge
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)
```

Two things worth keeping:

* **`thinking_budget=0`.** `gemini-2.5-flash` thinks by default. For a short
  creative generation it buys nothing and costs the player seconds of staring
  at a sealed safe.
* **Validate anyway.** Structured output guarantees the *shape*, never the
  *values* — a model can still return four digits, a `12`, or an empty theme.
  `quests.coerce_quest()` repairs rather than rejects, because a bad digit
  would otherwise make the safe literally unopenable. The tests feed it empty
  strings, prose, a JSON array and a short code; all four produce a playable
  vault.

It plugs into `spawn_vault` (`handlers/vault.py`) between the `sendPhoto` and
the caption edit.

### 2. The reveal — streaming, buffered on our side

`GeminiRewardProvider.stream()` yields the **cumulative** text so the renderer
can drop it straight into `editMessageCaption`, and is deliberately
un-throttled. Buffering lives in `_stream_reward()`, the only layer that knows
Telegram's limits: chunks accumulate freely, an edit goes out at most once per
`STREAM_EDIT_INTERVAL` (1.2s), and the final text is always flushed. A test
feeds 60 chunks and asserts they collapse into a handful of edits rather than
60 `429`s. A `▌` cursor rides the streaming edits and is stripped from the
last one.

Telegram has no native token streaming for bot messages — `editMessageCaption`
is the mechanism, so the throttle is the feature, not a workaround.

## State management

State is keyed by `(chat_id, message_id)`, so one chat can hold many
independent vaults and each message always re-renders itself correctly.

* `MemoryStateStore` — bounded LRU dict, single worker, state dies on restart.
* `RedisStateStore` — shared across workers, TTL'd, survives restarts.

Pick one with `STATE_BACKEND=memory|redis`; nothing else in the code changes.

Both expose a per-vault `asyncio.Lock`. This is not optional: Telegram delivers
rapid taps concurrently, and without the mutex two handlers read the same
dials, both increment, and one write silently loses a turn. The smoke test
fires 20 simultaneous taps and asserts all 20 are counted. For multiple
workers, promote that lock to a Redis lock — the interface is unchanged.

The critical section covers the state mutation only. The unlock sequence runs
*outside* it, because streaming a reward can take seconds and must not block
the vault.

## Error handling

`services/safe_calls.py` wraps every Bot API call and absorbs the three races
that are normal in a callback-driven bot, while letting real errors surface:

* **`query is too old` / `query ID is invalid`** — the 15-second window to
  answer a `CallbackQuery` expired. The tap is lost; the edit still landed.
  Note the ordering in the handlers: **edit first, `answer()` last**. The
  visible dial turn matters more than the spinner, and answering first spends
  part of the window on a round trip.
* **`message is not modified`** — identical markup re-rendered, which happens
  whenever two taps race. Harmless.
* **`TelegramRetryAfter`** — flood control; sleeps exactly as long as told,
  then retries once.

A stale cached `file_id` on the unlock swap is retried once with a real upload.
`handlers/errors.py` catches anything else, logs it, and releases the user's
spinner instead of leaving it turning.

## Swapping models or going offline

`QuestProvider` and `RewardProvider` are the only interfaces the handlers know:

```python
quest = await provider.generate(ctx)      # -> Quest(code, theme, riddle)

async for partial in provider.stream(ctx):  # -> the full text so far
    ...
```

Both Gemini providers are wrapped in a fallback (`FallbackQuestProvider`,
`FallbackRewardProvider`). This is not defensive padding: a player who cracked
the code has earned a prize, and a 500 from the API is not their problem. A
dead key means locally generated codes and canned flavour — the game still
runs. Swapping in another model means writing one class in
`services/gemini.py`'s place; nothing in `handlers/` changes.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | — | Required. From @BotFather. |
| `GEMINI_API_KEY` | — | From AI Studio. Absent ⇒ offline mode (local codes, static reveal). |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Any `google-genai` model id. |
| `SECRET_CODE` | *(unset)* | Normally empty — codes are generated per vault. Set it only to pin one for a demo. |
| `DIAL_COUNT` | `3` | 1–8 dials; the keyboard adapts. |
| `STATE_BACKEND` | `memory` | `memory` or `redis`. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis backend only. |
| `STATE_TTL` | `86400` | Seconds a vault stays alive (Redis only). |
| `STATIC_REWARD` | noir one-liner | Offline fallback. Supports `{user_name}`, `{code}`, `{attempts}`, `{theme}`. |

A `SECRET_CODE` whose length disagrees with `DIAL_COUNT` fails at startup, not
at unlock time.

## Notes for group chats

Any member can turn the dials of a vault — a shared safe is more fun than a
private one. `VaultState.owner_id` records who spawned it, so gating taps to
the owner is a two-line check in `turn_dial` if you want solo play.
