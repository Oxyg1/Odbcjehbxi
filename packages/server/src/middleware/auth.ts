import type { FastifyReply, FastifyRequest } from 'fastify';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { consumeRateLimit } from '../lib/redis.js';
import { InitDataError, verifyInitData, type VerifiedInitData } from '../telegram/init-data.js';
import { userService } from '../services/user.service.js';
import type { AuthenticatedUser } from '../services/user.service.js';

declare module 'fastify' {
  interface FastifyRequest {
    /** Set by `requireTelegramAuth`; absent on public routes. */
    auth?: AuthContext;
  }
}

export interface AuthContext {
  user: AuthenticatedUser;
  initData: VerifiedInitData;
}

const INIT_DATA_HEADER = 'x-telegram-init-data';

/** Per-identity request budget, applied after the signature checks out. */
const API_RATE_LIMIT = { points: 120, durationMs: 60_000 };

export function extractInitData(request: FastifyRequest): string | null {
  const header = request.headers[INIT_DATA_HEADER];
  if (typeof header === 'string' && header.length > 0) return header;
  if (Array.isArray(header) && header[0]) return header[0];

  // Fall back to the `Authorization: tma <initData>` convention used by the
  // Telegram Apps SDK ecosystem.
  const authorization = request.headers.authorization;
  if (typeof authorization === 'string' && authorization.startsWith('tma ')) {
    return authorization.slice(4).trim();
  }
  return null;
}

/**
 * Verifies the Mini App launch signature and resolves it to a local user.
 * Every mutating endpoint sits behind this — the Mini App has no other
 * credential, so an unsigned request is an anonymous request.
 */
export async function requireTelegramAuth(
  request: FastifyRequest,
  reply: FastifyReply,
): Promise<void> {
  const raw = extractInitData(request);
  if (!raw) {
    await reply.code(401).send({
      error: 'UNAUTHORIZED',
      message: 'Missing Telegram initData',
    });
    return;
  }

  let verified: VerifiedInitData;
  try {
    verified = verifyInitData(raw, {
      botToken: env.TELEGRAM_BOT_TOKEN,
      maxAgeSeconds: env.INITDATA_MAX_AGE_SECONDS,
    });
  } catch (error) {
    const reason = error instanceof InitDataError ? error.reason : 'MALFORMED';

    /*
     * A BAD_SIGNATURE is almost always the server holding a different bot's
     * token than the bot the user launched the Mini App from, and there is no
     * way to tell that apart from the reason code alone. Log the bot id — the
     * part of the token before the colon, which is not a secret — so it can be
     * compared against the launching bot. The initData itself is never logged:
     * it carries the user's profile and the signature.
     */
    logger.warn(
      {
        reason,
        ip: request.ip,
        expectedBotId: env.TELEGRAM_BOT_TOKEN.split(':')[0] ?? 'unknown',
        initDataLength: raw.length,
        initDataKeys: describeInitDataKeys(raw),
      },
      'initData verification failed',
    );
    await reply.code(401).send({
      error: 'UNAUTHORIZED',
      message: 'Invalid Telegram initData',
      reason,
    });
    return;
  }

  const limit = await consumeRateLimit('api', verified.user.id.toString(), API_RATE_LIMIT);
  if (!limit.allowed) {
    await reply
      .code(429)
      .header('retry-after', Math.ceil(limit.retryAfterMs / 1000).toString())
      .send({
        error: 'RATE_LIMITED',
        message: 'Too many requests',
        retryAfterMs: limit.retryAfterMs,
      });
    return;
  }

  const user = await userService.upsertFromTelegram(verified.user);
  if (user.isBanned) {
    await reply.code(403).send({ error: 'FORBIDDEN', message: 'Account suspended' });
    return;
  }

  request.auth = { user, initData: verified };
}

/**
 * Field names present in an initData payload, for diagnostics. Names only —
 * never values, which include the user profile and the signature.
 */
function describeInitDataKeys(raw: string): string {
  try {
    return [...new URLSearchParams(raw).keys()].sort().join(',');
  } catch {
    return 'unparseable';
  }
}

/** Narrowing helper for handlers that ran behind `requireTelegramAuth`. */
export function getAuth(request: FastifyRequest): AuthContext {
  if (!request.auth) {
    // Unreachable when the preHandler is wired correctly; throwing here turns a
    // routing mistake into a loud 500 rather than a silent auth bypass.
    throw new Error('Route is missing the requireTelegramAuth preHandler');
  }
  return request.auth;
}
