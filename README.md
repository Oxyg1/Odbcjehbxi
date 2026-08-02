# tgmarket

An autonomous **Telegram Star gift** monitor and buyer. It polls the gift
catalogue over the MTProto user API, filters lots by your rules, and pays for
matches with Telegram Stars — unattended, on a VPS, with hard spending limits.

There is no Bot API for browsing or buying gifts, so this is a *userbot*: it
logs into a regular Telegram account and calls the same methods an official
client does.

```
payments.getStarGifts        →  catalogue scan
payments.getResaleStarGifts  →  secondary-market scan (optional)
payments.getPaymentForm      →  price confirmation
payments.sendStarsForm       →  payment
```

## Read this first

- **This automates your personal account.** Telegram's anti-automation systems
  can rate-limit or ban accounts; automated purchasing is not an officially
  supported use of the API. You are accepting that risk on your own account.
- **Purchases are irreversible.** Stars leave your balance and the gift is
  yours. That is why the bot ships in dry-run mode and refuses to run live
  without an explicit spending ceiling.
- **The session file is a full login.** Anyone who copies
  `sessions/*.session` (or `TG_SESSION_STRING`) controls the account. It is
  git-ignored; keep it that way.
- **The MTProto surface moves.** `payments.*` methods are internal; Telegram
  changes them without notice. If a scan starts failing, update Telethon first.

## Quick start

On a fresh Ubuntu VDS, `scripts/install.sh` installs Docker, clones the repo
and seeds `.env`/`config.yaml` in one pass — see "Deployment → Docker" below.

```bash
git clone <this repo> && cd tgmarket
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # put TG_API_ID / TG_API_HASH here
cp config.example.yaml config.yaml

python -m tgmarket login        # one-time interactive login (SMS code, 2FA)
python -m tgmarket catalog      # what is on sale, and what your filters do to it
python -m tgmarket watch        # monitor and report — never spends anything
python -m tgmarket run          # same loop, but buys (dry-run until you say otherwise)
python -m tgmarket run --live   # actually spend Stars
```

`TG_API_ID` / `TG_API_HASH` come from <https://my.telegram.org> → *API
development tools*. They identify the app, not the account.

## Commands

| Command | What it does |
| --- | --- |
| `login` | Interactive login; writes `sessions/<name>.session`. Run once. |
| `whoami` | Prints the logged-in account — a quick session health check. |
| `balance` | Prints the Stars balance. |
| `catalog [--all]` | Prints the catalogue; `--all` also shows rejected lots *and the reason*. |
| `watch [--once]` | Monitor loop that never buys. |
| `run [--once] [--live] [--max-cycles N]` | Monitor and buy. |

Global flags: `-c/--config` (default `config.yaml`), `--log-level`.

## How a cycle works

1. `payments.getStarGifts` — the catalogue, sent with the previous response
   hash so an unchanged catalogue costs almost nothing.
2. Optional resale scan (`payments.getResaleStarGifts`), per gift id, sorted by
   price so page one holds the cheapest copies.
3. New lots are recorded in `data/state.json` and announced once.
4. Filters select candidates, cheapest first.
5. For each candidate the budget guard checks per-gift, per-cycle, lifetime and
   balance limits. Live runs read the balance first and refuse to buy blind.
6. `payments.getPaymentForm` → **the form price is re-checked against your
   ceiling** → `payments.sendStarsForm`.
7. Result is logged, persisted, and pushed to your notification bot.

## Configuration

Two files, split by sensitivity:

- `.env` — secrets only: API credentials, session string, notification token.
- `config.yaml` — everything else. See `config.example.yaml`; every option is
  commented there.

Environment always wins over YAML, so `DRY_RUN=true` in the container
environment is a brake nothing in the config file can release.

### Filters

`max_price` / `min_price`, `gift_ids`, `exclude_gift_ids`, `titles`,
`limited_only`, `unlimited_only`, `skip_sold_out`, `skip_premium_required`,
`min_supply` / `max_supply`, `min_available`.

Typical "snipe cheap limited gifts" setup:

```yaml
filters:
  max_price: 100
  limited_only: true
  max_supply: 10000
  min_available: 1
```

Use `catalog --all` to see exactly why a lot was rejected before you go live.

### Budget

```yaml
buy:
  budget:
    max_stars_total: 1000        # lifetime, tracked in the state file
    max_stars_per_cycle: 250
    max_stars_per_gift: 100
    max_purchases_per_cycle: 1
    max_purchases_per_gift: 1    # never buy the same gift id twice
    min_balance_reserve: 0
```

`run --live` refuses to start unless `max_stars_total` or
`max_stars_per_cycle` is set. Deleting `data/state.json` resets the lifetime
counter — that file *is* the spending record.

### Notifications

Set `NOTIFY_BOT_TOKEN` (from @BotFather) and `NOTIFY_CHAT_ID` and the bot
reports starts, new matches, purchases and errors to that chat. It uses a
*separate* bot on purpose: if the userbot account gets limited, the reporting
path still works. Delivery failures are logged, never fatal.

## Rate limits and FLOOD_WAIT

The most common way to lose an account is mishandled `FLOOD_WAIT`: crash,
restart, immediately re-issue the same request, earn a longer penalty, repeat.
Every MTProto call here goes through one guard (`src/tgmarket/ratelimit.py`)
that

- paces calls with a minimum interval (`runtime.min_api_interval`),
- on `FLOOD_WAIT` sleeps exactly the number of seconds the server asked for
  (plus one second of slack) and holds back every other caller meanwhile,
- **stops the process** if the demanded wait exceeds `runtime.max_flood_wait`,
  instead of grinding, and
- retries only transient server/network errors, with exponential backoff.

`runtime.poll_interval` defaults to 60s and values below 15s are rejected.
Faster polling does not win races that are decided by Telegram's servers; it
mostly buys flood errors.

## Deployment

### Docker

On a fresh Ubuntu server, one script does the unattended part (installs
Docker, clones the repo, seeds `.env` with your API credentials):

```bash
curl -fsSL https://raw.githubusercontent.com/Oxyg1/Odbcjehbxi/claude/new-session-m867oe/scripts/install.sh | bash
```

It stops where a human is required — review `config.yaml`, then:

```bash
cd ~/tgmarket
docker compose --profile tools run --rm login   # one-time, interactive
docker compose up -d                            # dry-run by default
docker compose logs -f
```

`sessions/` and `data/` are volumes, so rebuilds neither force a re-login nor
lose the purchase ledger. Switch to live by editing `command: ["run", "--live"]`.

### systemd

See `examples/systemd/tgmarket.service`.

### Proxy

`TG_PROXY` accepts `mtproxy://host:port?secret=<hex>` (no extra dependency) or
`socks5://user:pass@host:port` (`pip install 'telethon[socks]'`). An MTProto
proxy only changes how traffic reaches Telegram — it grants no additional API
access and does not make an account harder to rate-limit.

## Development

```bash
pip install -e '.[dev]'
pytest                # 100+ tests, no network and no Telegram account needed
```

The API boundary is deliberately thin: `market.py` converts TL objects into
`GiftLot`, and everything downstream (filters, budget, runner) is pure Python
that tests drive with fakes.

```
src/tgmarket/
  cli.py          command line entry points
  config.py       YAML + env loading and validation
  client.py       session/proxy handling, Telethon client
  market.py       payments.getStarGifts / getResaleStarGifts / getStarsStatus
  filters.py      lot selection rules
  purchase.py     payment form → sendStarsForm, plus the budget guard
  ratelimit.py    pacing, FLOOD_WAIT handling, backoff
  state.py        durable ledger (seen lots, purchases, spend)
  runner.py       the monitor → filter → buy loop
  notify.py       Bot API status messages
```

## Not implemented, on purpose

The source research suggested running pools of accounts across IPs and
randomising behaviour so the activity blends in. This project does neither: it
is one account, one configured transport, and a fixed polling interval. Those
techniques exist to evade a platform's anti-abuse systems rather than to work
within their limits, and they raise the stakes of a ban from one account to
several. Everything here is aimed at staying inside Telegram's published
limits, not at hiding from them.

Background on the research this project came from: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## License

MIT — see [`LICENSE`](LICENSE).
