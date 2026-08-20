/**
 * Platform-wide economic and gameplay constants.
 * Shared by the server (authoritative) and the client (optimistic previews only).
 */

/** Platform fee, in basis points, taken from every Stars donation/purchase. 500 bp = 5%. */
export const PLATFORM_FEE_BPS = 500;

/** Basis-point denominator. */
export const BPS_DENOMINATOR = 10_000;

/** Minimum amount, in Telegram Stars, that a single donation may carry. */
export const MIN_STARS_AMOUNT = 1;

/**
 * Telegram caps a single Stars invoice at 100_000 XTR. We stay one order of
 * magnitude below to keep refunds manageable.
 */
export const MAX_STARS_AMOUNT = 100_000;

/** Maximum number of listings a single stand may expose at once. */
export const MAX_LISTINGS_PER_STAND = 8;

/** Maximum number of stands rendered inside one room. */
export const ROOM_CAPACITY = 50;

/** Soft capacity: above this the room is flagged "busy" in the room picker. */
export const ROOM_BUSY_THRESHOLD = 40;

/** Heartbeat interval for room presence, in milliseconds. */
export const PRESENCE_HEARTBEAT_MS = 20_000;

/** A presence record older than this is reaped by the presence sweeper. */
export const PRESENCE_TTL_SECONDS = 60;

/** Donation VFX tier thresholds, expressed in Telegram Stars. */
export const VFX_TIER_THRESHOLDS = {
  /** 1..50 — local confetti on the receiving stand card. */
  micro: { min: 1, max: 50 },
  /** 51..1000 — room-wide banner + shake + haptics. */
  major: { min: 51, max: 1_000 },
  /** >1000 — global full-screen broadcast to every online user. */
  whale: { min: 1_001, max: Number.MAX_SAFE_INTEGER },
} as const;

/**
 * Star-equivalent valuation used to tier NFT gift donations. A "legendary"
 * gift is treated as a whale-tier event regardless of its floor price.
 */
export const GIFT_RARITY_STAR_EQUIVALENT = {
  COMMON: 25,
  RARE: 250,
  EPIC: 900,
  LEGENDARY: 5_000,
} as const;

/** Rate limits enforced on the realtime gateway, per connection. */
export const WS_RATE_LIMITS = {
  /** Generic inbound envelope budget. */
  inbound: { points: 40, durationMs: 10_000 },
  /** Stand edit broadcasts are the most expensive fan-out we allow. */
  standUpdate: { points: 6, durationMs: 10_000 },
  /** Reactions/cheers are cheap but spammable. */
  reaction: { points: 20, durationMs: 10_000 },
  /** Room hops. */
  joinRoom: { points: 10, durationMs: 30_000 },
} as const;

/** How long a global whale broadcast stays pinned on every client, in ms. */
export const GLOBAL_BROADCAST_DURATION_MS = 7_000;

/** Room-level major broadcast duration, in ms. */
export const ROOM_BROADCAST_DURATION_MS = 4_500;

/** Redis key factory. Keeping these in one place avoids key-space drift. */
export const RedisKeys = {
  roomPresence: (roomId: string) => `room:${roomId}:presence`,
  roomStands: (roomId: string) => `room:${roomId}:stands`,
  roomSnapshot: (roomId: string) => `room:${roomId}:snapshot`,
  standCache: (standId: string) => `stand:${standId}`,
  socketSession: (socketId: string) => `ws:${socketId}`,
  userSockets: (userId: string) => `user:${userId}:sockets`,
  leaderboard: (scope: string, bucket: string) => `lb:${scope}:${bucket}`,
  onlineCount: () => `presence:online`,
  rateLimit: (bucket: string, key: string) => `rl:${bucket}:${key}`,
  lock: (resource: string) => `lock:${resource}`,
  invoicePayload: (payload: string) => `invoice:${payload}`,
  idempotency: (key: string) => `idem:${key}`,
} as const;

/** Redis Pub/Sub channels. */
export const RedisChannels = {
  /** Fan-out for a single room. */
  room: (roomId: string) => `bcast:room:${roomId}`,
  /** Fan-out to every gateway node (whale broadcasts, maintenance notices). */
  global: 'bcast:global',
  /** Direct-to-user delivery (payment confirmations, gift receipts). */
  user: (userId: string) => `bcast:user:${userId}`,
} as const;
