# TgDonate

A viral Web3 donation and micro-marketplace platform for Telegram + TON, built
on the mechanics that made Roblox's *PLS DONATE* work: you set up a booth, you
stand in a public room, and when someone drops a big number **everybody sees it
happen**.

Visual language is lifted from the reference Portals Mini App builds — near-black
`#141414` canvas, a six-step elevation ramp, "liquid glass" inner-shadow bevels,
16px squircle corners, SF Pro Text.

---

## What it does

| Feature | How it works |
| --- | --- |
| **Digital booths** | One stand per user: title, goal, target, theme, banner style, up to 8 listings. |
| **Listings** | Donation tiers (fixed Stars), service offers (Stars or TON), and NFT Gift sales through escrow. |
| **Live rooms** | Up to 50 stand cards per room, synced over WebSockets. Counters move because a frame moved them — nothing polls. |
| **Tiered VFX** | 1–50 ⭐ → confetti on the card. 51–1000 ⭐ → room banner + card shake + haptics. >1000 ⭐ or a legendary gift → **full-screen global broadcast to every online user**. |
| **Whale ranks** | Daily / weekly / all-time leaderboards on Redis sorted sets, mirrored to Postgres, with glowing rank badges on avatars. |
| **Theme market** | Premium stand themes (PS1 Low-Poly, Cyberpunk, CRT, Aurora, Gold Royalty) bought with Telegram Stars. |
| **Platform fee** | Configurable, 5% by default, integer-only so rounding never mints or burns a Star. |

## Architecture

```
packages/
├── shared/     Protocol contract, domain types, design tokens, money math
├── server/     Fastify + ws + Redis + Prisma + grammY + TON
└── web/        Vite + React + TS + Tailwind v4 + Framer Motion + TON Connect
```

### Backend

```
src/
├── config/env.ts            Zod-validated environment; a bad var fails at boot
├── lib/                     Prisma, Redis (locks + rate limits), logger
├── middleware/auth.ts       initData HMAC verification on every endpoint
├── telegram/                initData crypto, bot, Stars invoices, commands
├── ton/                     TON Connect proof verification, escrow watcher
├── realtime/                WS gateway + Redis Pub/Sub broadcaster
├── services/                stand, listing, donation, gift, room, leaderboard, user
├── controllers/             REST routes + error mapping
└── jobs/                    Badge refresh, intent expiry, escrow reclaim, session sweep
```

The gateway is horizontally scalable: every frame goes out through Redis Pub/Sub
and each node writes it to the sockets it owns, stamped with `originNodeId`.

### Frontend

```
src/
├── lib/          Telegram bridge, API client, socket client, cn()
├── hooks/        useRealtime, useMainButton, useBackButton
├── store/        Zustand app store (rooms, stands, VFX queue)
├── components/   StandCard, MegaphoneOverlay, Confetti, TabBar, ui/primitives
└── screens/      Rooms, Room, Stand, Editor, Leaderboard, Profile
```

---

## Getting started

> The server refuses to boot against a database that has not been migrated and
> seeded, and says which of the two is missing. `SELECT 1` succeeds on an empty
> database, so without that check an unmigrated deployment starts fine and then
> returns 500 from every data route.

```bash
# 1. Dependencies
npm install

# 2. Environment
cp .env.example packages/server/.env
cp .env.example packages/web/.env
#    Fill in TELEGRAM_BOT_TOKEN, DATABASE_URL, REDIS_URL at minimum.

# 3. Database
npm run prisma:generate
npm run prisma:deploy      # applies prisma/migrations — creates the schema
npm run db:seed            # 5 rooms + 7 stand themes

# 4. Run
npm run dev:server         # :3000  (API + /ws)
npm run dev:web            # :5173  (Mini App)
```

Point @BotFather's Mini App URL at your tunnelled `:5173`, then open the bot.

### Verify

```bash
npm run typecheck          # all three packages
npm run build
```

### Diagnosing a deployment

```bash
npm run doctor
```

Checks the whole chain a Mini App request travels — environment variables,
PostgreSQL, schema, seed, Redis, and the bot's identity as Telegram reports it —
and names the fix for each fault it finds. It is read-only.

The bot identity line matters most: `initData` is signed with the bot token, so
opening the Mini App from any bot other than the one the server holds fails with
`BAD_SIGNATURE` no matter how correct everything else is.

Set `TELEGRAM_API_BASE` if outbound traffic to `api.telegram.org` goes through a
proxy.

---

## Deployment note: the client's API address

For the standard single-host deployment — nginx serving the Mini App and
proxying `/api` and `/ws` to the backend — leave `VITE_API_URL` and
`VITE_WS_URL` **empty**. The client then uses its own origin, deriving `wss://`
from an `https://` page automatically.

These variables are inlined at build time, so setting them to `localhost`
produces a bundle that asks the *viewer's device* for the API. That build is
also blocked as mixed content on an https page. The client detects a loopback
value on a non-loopback page, logs the mismatch, and falls back to same-origin
rather than failing every request.

Set them only for a genuinely split deployment, to public `https://` / `wss://`
URLs.

## Security notes

**Every request is authenticated by `initData`.** The Mini App has no other
credential, so the HMAC is re-verified per call rather than exchanged for a
session token:

```
secret = HMAC_SHA256(key="WebAppData", data=bot_token)
hash   = HMAC_SHA256(key=secret, data=data_check_string)
```

`data_check_string` is every field except `hash` and `signature` (the latter
belongs to Telegram's separate Ed25519 scheme), sorted and `\n`-joined.
Comparison is timing-safe; payloads older than `INITDATA_MAX_AGE_SECONDS`, or
dated in the future, are rejected.

**Money never moves twice.** Four independent layers:

1. `invoicePayload` and `telegramChargeId` are unique columns.
2. A Redis one-shot claim on the charge / tx hash drops replayed webhooks.
3. A `ProcessedEvent` row is the durable audit of each delivery.
4. `donationService.settle` short-circuits on an already-`SETTLED` row, inside a
   per-transaction Redis mutex, with all balance writes in one SQL transaction.

**Inventory races are serialised.** Selling one NFT gift twice is prevented by a
Redis mutex per gift plus a conditional `updateMany` guard on limited-supply
listings; a failed invoice releases the reservation rather than shrinking supply
permanently.

**Rate limiting is layered.** A coarse IP/identity limiter in front of Fastify,
a per-user budget after the signature checks out, and per-frame budgets on the
WebSocket gateway (stand edits are the most expensive fan-out, so they get the
tightest budget).

**Prices are server-authoritative.** A client-supplied amount is only honoured
for free-form donations; anything with a listing takes its price from the
database, so a buyer cannot set their own.

---

## Payment flows

**Telegram Stars**

1. Client asks `POST /api/payments/stars/invoice`.
2. Server writes an `AWAITING_PAYMENT` transaction, reserves stock, and calls
   `createInvoiceLink` (currency `XTR`, one price component).
3. Client opens it with `openInvoice`.
4. `pre_checkout_query` → re-validate amount, listing status, terminal state, and
   answer inside Telegram's 10-second window. Failures fail *closed*.
5. `successful_payment` → settle once, credit the receiver net of fee, update the
   leaderboard, then broadcast at the tier's blast radius.

**TON**

1. `POST /api/payments/ton/intent` returns the escrow address plus a
   `tgdonate:<transactionId>` comment.
2. The wallet sends the transfer with that comment attached.
3. The watcher polls the escrow wallet, matches the comment, verifies the amount
   is not short, and settles.

**NFT Gifts** are mirrored from Telegram, locked into escrow behind a per-gift
mutex while a purchase is pending, and reclaimed automatically after 30 minutes
if the buyer never pays. A gift *sale* transfers to the buyer; a gift *donation*
transfers to the stand owner — the two directions are handled separately.

---

## Design tokens

Defined once in `packages/shared/src/design.ts` and mirrored into
`packages/web/src/styles/index.css`:

| Token | Value |
| --- | --- |
| Canvas | `#141414` |
| Elevation | `#191919` → `#1c1c1c` → `#212020` → `#282727` → `#363636` → `#3a3a3a` |
| Accent (donations) | `#49df64` |
| Primary | `#1689ff` |
| Gold (major tier) | `#f1aa05` |
| Tiffany (whale tier) | `#68fbdd` |
| Muted text | `#6d6d71` |
| Radius | 16px, squircle where `corner-shape` is supported |
| Glass | `blur(8px) saturate(140%)` + 10-layer inner-shadow bevel |

---

## Verified

- initData HMAC: accepts valid payloads; rejects tampered fields, foreign bot
  tokens, expired timestamps and missing hashes; correctly excludes `signature`
  from the data-check-string.
- Fee split conserves value across the full amount range and floors the fee so
  the receiver never loses a Star to rounding.
- Tier thresholds at every boundary (50/51, 1000/1001) and the legendary-gift
  override.
- Nanoton conversion round-trips exactly.
- All three packages typecheck and build clean; the Mini App renders with the
  correct tokens (`#141414` canvas, 62px tab bar, SF Pro Text, glass backdrop).
