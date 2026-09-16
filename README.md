# CryptexBot

A single-message interactive puzzle box for Telegram: a locked vault with three
dials, built on **aiogram 3.x**.

The bot sends **exactly one message per vault**. Every interaction after that —
turning a dial, resetting, opening the safe, revealing the prize — edits that
same message. No replies, no follow-ups, no notification spam.

```
/vault  ->  [photo: locked safe]
            🔒 THE CRYPTEX VAULT
            Dials: 0 0 0
            [0️⃣] [0️⃣] [0️⃣]
            [🔄 Reset dials]

            ... taps edit the keyboard in place ...

            [photo swaps to open safe]
            🔓 THE VAULT IS OPEN
            Promo code: CRYPTEX-732-OPEN
            [🔓 VAULT OPEN]
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # put your BotFather token in BOT_TOKEN
python main.py
```

Then send `/vault` to the bot. The artwork is generated with Pillow on first
run into `assets/generated/` — no image assets to ship.

Run the offline smoke test (no token, no network needed):

```bash
python tests/test_flow.py
```

## How the Zero-Spam loop works

| Event | Bot API call | Why |
|---|---|---|
| `/vault` | `sendPhoto` | The only message ever sent. |
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
    rewards.py                 what the vault reveals  <- the LLM swap point
    safe_calls.py              CallbackQuery / edit error handling
tests/test_flow.py             offline smoke test with a stub Bot
```

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

## Swapping the static prize for an LLM call

Everything about the reveal lives in `services/rewards.py`. Providers share one
streaming interface, where each yielded item is the **full text so far**:

```python
async for partial in provider.stream(ctx):
    ...
```

`StaticRewardProvider` yields once. `LLMRewardProvider` yields as tokens
arrive. The renderer in `handlers/vault.py` is already written against the
streaming shape, so turning on native text streaming is a config change:

```bash
REWARD_PROVIDER=llm
ANTHROPIC_API_KEY=sk-ant-...
REWARD_MODEL=claude-sonnet-5
```

plus `pip install anthropic` (a lazy import, so it stays optional).

Two things worth keeping when you write your own provider:

* **Do not throttle inside the provider.** Yield as fast as tokens land; the
  renderer throttles caption edits to one per `STREAM_EDIT_INTERVAL` (1.2s),
  because Telegram rate-limits edits at roughly 1/sec per chat.
* **Keep the fallback.** `FallbackRewardProvider` wraps the LLM so an API
  failure mid-generation still hands the player a prize instead of an empty
  vault.

Captions are capped at Telegram's 1024 characters and truncated safely.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | — | Required. From @BotFather. |
| `SECRET_CODE` | `732` | Digits only; length must equal `DIAL_COUNT`. |
| `DIAL_COUNT` | `3` | 1–8 dials; the keyboard adapts. |
| `STATE_BACKEND` | `memory` | `memory` or `redis`. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis backend only. |
| `STATE_TTL` | `86400` | Seconds a vault stays alive (Redis only). |
| `REWARD_PROVIDER` | `static` | `static` or `llm`. |
| `STATIC_REWARD` | promo string | Supports `{user_name}`, `{code}`, `{attempts}`. |

Mismatched `SECRET_CODE` / `DIAL_COUNT` fails at startup, not at unlock time.

## Notes for group chats

Any member can turn the dials of a vault — a shared safe is more fun than a
private one. `VaultState.owner_id` records who spawned it, so gating taps to
the owner is a two-line check in `turn_dial` if you want solo play.
