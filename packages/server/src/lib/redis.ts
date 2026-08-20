import { randomUUID } from 'node:crypto';
import { Redis } from 'ioredis';
import { RedisKeys } from '@tgdonate/shared';
import { env } from '../config/env.js';
import { logger } from './logger.js';

/**
 * Three connections by design: ioredis puts a connection into subscriber mode
 * permanently, so publishing and regular commands each need their own.
 */
function createClient(role: string): Redis {
  const client = new Redis(env.REDIS_URL, {
    maxRetriesPerRequest: null,
    enableReadyCheck: true,
    lazyConnect: false,
    retryStrategy: (times) => Math.min(times * 200, 5_000),
  });
  client.on('error', (error) => logger.error({ err: error, role }, 'redis error'));
  client.on('reconnecting', () => logger.warn({ role }, 'redis reconnecting'));
  return client;
}

export const redis = createClient('command');
export const redisPublisher = createClient('publisher');
export const redisSubscriber = createClient('subscriber');

export async function disconnectRedis(): Promise<void> {
  await Promise.allSettled([
    redis.quit(),
    redisPublisher.quit(),
    redisSubscriber.quit(),
  ]);
}

/* ---------------------------------------------------------------------- */
/*                          Distributed mutex                             */
/* ---------------------------------------------------------------------- */

/**
 * Release only if we still own the lock. Comparing-then-deleting from the
 * client would be racy: the TTL can expire between GET and DEL, and we would
 * delete a lock another worker has since acquired.
 */
const RELEASE_SCRIPT = `
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end`;

export interface LockHandle {
  resource: string;
  token: string;
  release(): Promise<boolean>;
}

export class LockAcquisitionError extends Error {
  constructor(resource: string) {
    super(`Could not acquire lock for "${resource}"`);
    this.name = 'LockAcquisitionError';
  }
}

/**
 * Acquire a mutex over `resource`. Used to serialise inventory-sensitive work:
 * a single NFT gift must not be sold twice even if two buyers pay in the same
 * millisecond against two different API nodes.
 */
export async function acquireLock(
  resource: string,
  options: { ttlMs?: number; retries?: number; retryDelayMs?: number } = {},
): Promise<LockHandle> {
  const { ttlMs = 10_000, retries = 12, retryDelayMs = 120 } = options;
  const key = RedisKeys.lock(resource);
  const token = randomUUID();

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const result = await redis.set(key, token, 'PX', ttlMs, 'NX');
    if (result === 'OK') {
      return {
        resource,
        token,
        release: async () => {
          const released = await redis.eval(RELEASE_SCRIPT, 1, key, token);
          return released === 1;
        },
      };
    }
    if (attempt < retries) {
      // Jitter avoids a thundering herd when many buyers hit one listing.
      const jitter = Math.floor(Math.random() * retryDelayMs);
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs + jitter));
    }
  }
  throw new LockAcquisitionError(resource);
}

/** Run `fn` while holding the lock, releasing it even if `fn` throws. */
export async function withLock<T>(
  resource: string,
  fn: () => Promise<T>,
  options?: { ttlMs?: number; retries?: number; retryDelayMs?: number },
): Promise<T> {
  const lock = await acquireLock(resource, options);
  try {
    return await fn();
  } finally {
    const released = await lock.release().catch(() => false);
    if (!released) {
      logger.warn({ resource }, 'lock expired before release');
    }
  }
}

/* ---------------------------------------------------------------------- */
/*                        Token-bucket rate limiter                       */
/* ---------------------------------------------------------------------- */

/**
 * Fixed-window counter with a single round-trip. INCR then conditionally
 * PEXPIRE, so the window starts on the first hit and the key self-reaps.
 */
const RATE_LIMIT_SCRIPT = `
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("PTTL", KEYS[1])
return { current, ttl }`;

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  retryAfterMs: number;
}

export async function consumeRateLimit(
  bucket: string,
  identifier: string,
  limit: { points: number; durationMs: number },
): Promise<RateLimitResult> {
  const key = RedisKeys.rateLimit(bucket, identifier);
  const [current, ttl] = (await redis.eval(
    RATE_LIMIT_SCRIPT,
    1,
    key,
    limit.durationMs.toString(),
  )) as [number, number];

  const allowed = current <= limit.points;
  return {
    allowed,
    remaining: Math.max(0, limit.points - current),
    retryAfterMs: allowed ? 0 : Math.max(ttl, 0),
  };
}

/* ---------------------------------------------------------------------- */
/*                              Idempotency                               */
/* ---------------------------------------------------------------------- */

/**
 * Claim a one-shot key. Returns false when the key was already claimed, which
 * is how replayed Telegram/TON webhook deliveries are dropped before they can
 * double-credit anyone.
 */
export async function claimOnce(key: string, ttlSeconds = 86_400): Promise<boolean> {
  const result = await redis.set(RedisKeys.idempotency(key), '1', 'EX', ttlSeconds, 'NX');
  return result === 'OK';
}

/** Release a claim so a failed operation can be retried. */
export async function releaseClaim(key: string): Promise<void> {
  await redis.del(RedisKeys.idempotency(key));
}
