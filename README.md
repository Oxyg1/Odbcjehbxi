# CryptexBot

A single-message interactive puzzle box for Telegram: a locked vault with three
dials, built on **aiogram 3.x** and **Gemini** (`google-genai`).

The bot speaks **English and Russian**, switchable mid-game with one button.

Every vault is generated at run time, and **the riddle is actually solvable**:
Python picks the combination, Gemini writes one clue per dial pointing at those
exact digits, and a second model pass solves the clues cold to prove they
resolve. Crack it and the reveal is streamed into the message as it is written.

The bot sends **exactly one message per vault**. Every interaction after that —
turning a dial, resetting, opening the safe, revealing the prize — edits that
same message. No replies, no follow-ups, no notification spam.

```
/vault  ->  [photo: locked safe]
            🔒 THE CRYPTEX VAULT
            Choose your language to begin.
            Выберите язык, чтобы начать.
            [🇬🇧 English] [🇷🇺 Русский]        <- quest already generating

            ... same message, edited ...

            🔒 THE CRYPTEX VAULT
            Steel is cooling, tumblers are being set…      <- Gemini is working
            (no keyboard yet: there is no combination to tap)

            ... same message, edited once the quest lands ...

            🔒 A DROWNED OBSERVATORY
            Salt has eaten the brass, but the tide still keeps time.

            First  — Count the days the almanac gives a week.
            Second — Count the legs of the milking stool by the door.
            Third  — Count the oars a rower pulls.

            Dials: 0 0 0
            [0️⃣] [0️⃣] [0️⃣]
            [🔄 Reset dials]

            ... taps edit the keyboard in place ...

            [photo swaps to open safe]
            🔓 A DROWNED OBSERVATORY
            Combination 7-3-2 accepted after 31 turns.
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

Needs Python 3.10 or newer. Note that `aiogram` below 3.17 caps `pydantic`
under 2.10, which `google-genai` cannot satisfy — `requirements.txt` carries a
floor rather than an exact pin for that reason, and a clean install resolves to
aiogram 3.31 / google-genai 2.23 / pydantic 2.13.

Get a Gemini key at <https://aistudio.google.com/apikey>. Without one the bot
still runs: codes are generated locally and the reveal falls back to
`STATIC_REWARD`, so you can develop the Telegram side offline.

Send `/vault` to start. The artwork is generated with Pillow on first run into
`assets/generated/` — no image assets to ship.

Run the tests (no token, no API key, no network):

```bash
python tests/test_flow.py      # the Telegram interaction, against a stub Bot
python tests/test_gemini.py    # the Gemini providers, against a fake SDK client
python tests/test_riddle.py    # code generation, leak scanning, clue repair (both languages)
```

## How the Zero-Spam loop works

| Event | Bot API call | Why |
|---|---|---|
| `/vault` | `sendPhoto` | The only message ever sent. Goes out **before** the Gemini call — an instant sealed vault beats a silent bot. |
| Language picked | `editMessageCaption` | The quest was generating the whole time the picker was on screen, so this usually costs no waiting. |
| Quest arrives | `editMessageCaption` | Riddle in, dials attached. Still the same message. |
| Language switched | `editMessageCaption` | Same puzzle, other language. No regeneration — see below. |
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
    quests.py                  code generation, leak scanning, clue repair
    rewards.py                 reveal interface, static + fallback providers
    gemini.py                  <- both Gemini calls live here, and only here
    safe_calls.py              CallbackQuery / edit error handling
tests/
  test_flow.py                 Telegram interaction, stub Bot
  test_gemini.py               Gemini providers, fake SDK client
```

## The two Gemini calls

Both live in `services/gemini.py`. They are deliberately different shapes.

### 1. Riddle authoring — one blocking call, JSON mode

**Python owns the answer.** `random.randint` picks the digits before the model
is called, and the response schema has no `code` field to return one in:

```python
code = random_code(ctx.dial_count)      # the answer, decided here
...
response_schema=_quest_schema(dial_count)   # {"theme", "riddle", "clues": [...]}
```

The prompt hands the model those digits dial by dial ("First dial: the answer
is 7") and asks for one clue each, naming a countable set whose size is common
knowledge. This ordering is the whole fix: when the model invented the code and
the riddle together, nothing tied them to each other and the clues were
decoration. Now the digits are an input, so a clue that fails to resolve is a
detectable defect.

A model-supplied `code` field, if one ever appears, is ignored outright — a
tested guarantee, and the reason a prompt injection in a user's display name
cannot talk its way to the combination.

**`thinking_budget=0`.** Flash models think by default. For a short
creative generation it buys nothing and costs the player seconds of staring at
a sealed safe.

### 1a. Two guarantees on the clue text

**Leak scan** (`quests.leaks_digit`, no API call). A clue may not contain a
digit character — `7`, `"7"`, `07` — nor name its own digit in words
("seven lamps", "the seventh lamp"). Counting *devices* like "a pair of gloves"
are the intended mechanism and are left alone. An incidental numeral ("Room 12")
is stripped and the model's prose kept; a sentence built around naming the
answer is replaced outright. The framing line is scanned too.

**Solver round-trip** (`GeminiQuestProvider.verify_clues`, one extra call). The
leak scan proves a clue does not *state* the answer. It says nothing about
whether the clue *reaches* it. So the clue text alone — no code, no theme —
goes back to the model at `temperature=0` with a `{"digits": [...]}` schema,
and anything that does not solve back to its digit is swapped for a clue from
`DIGIT_CLUES`, a local bank that is correct by construction. Set
`QUEST_VERIFY=false` to skip it and save the round trip.

Both repairs degrade the same way: you lose atmosphere, never solvability. And
because the local bank is the floor, a dead API key still produces a playable
vault.

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

## When the model id stops working

Google retires model ids and closes older ones to new API keys. That surfaces
as a 404 whose message names the replacement:

```
404 NOT_FOUND ... This model models/gemini-2.5-flash is no longer available
to new users. Please update your code to use models/gemini-3.6-flash
```

Ask your own key what it can reach rather than guessing:

```bash
python -m cryptexbot.models
```

It prints every model the key can call `generateContent` on, marks the one in
your `.env`, and warns if that one is missing. Then set `GEMINI_MODEL`.

The code is built to survive the next such change. Config is passed as a plain
dict, and a 400 that names an unknown or unsupported field retries once without
the optional knobs (`thinking_config` being the likely casualty), caching that
decision for later calls. A genuine error is *not* retried — a test asserts a
`500` falls back locally on the first attempt instead of burning a second call.
Retired-model, bad-key and quota errors are each logged as a sentence telling
you what to change.

## Language

Both languages are authored **in the same Gemini call** (`theme_en`, `riddle_en`,
`clues_en`, `theme_ru`, …). That is the whole design decision: translating on
demand would mean regenerating the riddle mid-game, and a regenerated riddle is
a different puzzle with a different answer. Carrying both means switching is a
caption edit — the dials keep their positions, the turn count survives, and the
combination never moves. A test asserts exactly that.

The leak scan runs per language and knows Russian inflection: `семь`, `семи`,
`седьмой` and `Седьмая` all give the answer away as plainly as `7` does, and are
caught. The solver round-trip checks every language in one call, because the
English clues being sound tells you nothing about the Russian ones — a test
feeds it a set where only the third Russian clue is wrong and asserts only that
one is replaced.

The local clue bank (`DIGIT_CLUES`) exists in both languages, so offline play
and every repair path stay fully bilingual.

Three ways to change language:

* the picker on a fresh vault, shown until a player chooses once;
* the 🌐 button on the vault, which switches to the other language in place;
* `/lang`, which opens a new vault and always asks.

The choice is remembered per player, so the picker appears once. The reveal is
generated in whatever language was on screen when the vault opened, and there is
no language button afterwards — a toggle that switched the heading but not the
prize would look broken.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | — | Required. From @BotFather. |
| `GEMINI_API_KEY` | — | From AI Studio. Absent ⇒ offline mode (local codes, static reveal). |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Any id your key can reach — see below. |
| `QUEST_VERIFY` | `true` | Solve each clue cold and replace the ones that fail. One extra call per vault. |
| `DEFAULT_LANG` | `en` | `en` or `ru`. Used before a player has chosen. |
| `ASK_LANGUAGE` | `true` | `false` skips the picker and starts in `DEFAULT_LANG`. |
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
