import { createHmac, timingSafeEqual } from 'node:crypto';
import { z } from 'zod';

/**
 * Telegram Mini App `initData` verification.
 *
 * Telegram signs the launch payload with
 *   secret = HMAC_SHA256(key = "WebAppData", data = bot_token)
 *   hash   = HMAC_SHA256(key = secret, data = data_check_string)
 * where data_check_string is every field except `hash`, sorted by key and
 * joined with "\n" as `key=value`, with values URL-decoded.
 *
 * `hash` is the ONLY excluded field. `signature` — the Ed25519 payload added
 * for third-party validation in Bot API 7.10 — participates in this HMAC like
 * any other field. Excluding it (an easy assumption, since it is a signature
 * of its own) makes every real launch fail while tests that sign payloads
 * without a `signature` field still pass, because the exclusion is a no-op
 * there. Cross-checked against @telegram-apps/init-data-node.
 *
 * Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
 */

const TelegramUserSchema = z.object({
  id: z.number().int().positive(),
  is_bot: z.boolean().optional(),
  first_name: z.string(),
  last_name: z.string().optional(),
  username: z.string().optional(),
  language_code: z.string().optional(),
  is_premium: z.boolean().optional(),
  allows_write_to_pm: z.boolean().optional(),
  photo_url: z.string().url().optional(),
});

export type TelegramUser = z.infer<typeof TelegramUserSchema>;

export interface VerifiedInitData {
  user: TelegramUser;
  authDate: Date;
  /** `startapp` parameter, used for deep links into a stand or room. */
  startParam: string | null;
  chatInstance: string | null;
  queryId: string | null;
  raw: string;
}

export type InitDataFailureReason =
  | 'MISSING'
  | 'MALFORMED'
  | 'NO_HASH'
  | 'BAD_SIGNATURE'
  | 'EXPIRED'
  | 'NO_USER';

export class InitDataError extends Error {
  readonly reason: InitDataFailureReason;

  constructor(reason: InitDataFailureReason, message: string) {
    super(message);
    this.name = 'InitDataError';
    this.reason = reason;
  }
}

/** Cache the derived secret: HMAC over a constant token on every request is waste. */
const secretKeyCache = new Map<string, Buffer>();

function deriveSecretKey(botToken: string): Buffer {
  const cached = secretKeyCache.get(botToken);
  if (cached) return cached;
  const secret = createHmac('sha256', 'WebAppData').update(botToken).digest();
  secretKeyCache.set(botToken, secret);
  return secret;
}

function safeCompareHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let bufA: Buffer;
  let bufB: Buffer;
  try {
    bufA = Buffer.from(a, 'hex');
    bufB = Buffer.from(b, 'hex');
  } catch {
    return false;
  }
  if (bufA.length !== bufB.length || bufA.length === 0) return false;
  return timingSafeEqual(bufA, bufB);
}

export interface VerifyOptions {
  botToken: string;
  /** Reject payloads whose `auth_date` is older than this. */
  maxAgeSeconds: number;
  /** Injectable for deterministic tests. */
  now?: () => number;
}

export function verifyInitData(initData: string, options: VerifyOptions): VerifiedInitData {
  if (!initData || initData.length === 0) {
    throw new InitDataError('MISSING', 'initData is empty');
  }
  // Guard against pathological inputs before we do any crypto work.
  if (initData.length > 8_192) {
    throw new InitDataError('MALFORMED', 'initData exceeds the maximum accepted length');
  }

  let params: URLSearchParams;
  try {
    params = new URLSearchParams(initData);
  } catch {
    throw new InitDataError('MALFORMED', 'initData is not a valid query string');
  }

  const hash = params.get('hash');
  if (!hash) {
    throw new InitDataError('NO_HASH', 'initData carries no hash');
  }

  const pairs: string[] = [];
  for (const [key, value] of params.entries()) {
    if (key === 'hash') continue;
    pairs.push(`${key}=${value}`);
  }
  pairs.sort();
  const dataCheckString = pairs.join('\n');

  const expected = createHmac('sha256', deriveSecretKey(options.botToken))
    .update(dataCheckString)
    .digest('hex');

  if (!safeCompareHex(expected, hash)) {
    throw new InitDataError('BAD_SIGNATURE', 'initData signature mismatch');
  }

  const authDateRaw = params.get('auth_date');
  const authDateSeconds = Number(authDateRaw);
  if (!authDateRaw || !Number.isFinite(authDateSeconds)) {
    throw new InitDataError('MALFORMED', 'initData has no usable auth_date');
  }

  const nowMs = (options.now ?? Date.now)();
  const ageSeconds = Math.floor(nowMs / 1000) - authDateSeconds;
  if (ageSeconds > options.maxAgeSeconds) {
    throw new InitDataError(
      'EXPIRED',
      `initData is ${ageSeconds}s old, limit is ${options.maxAgeSeconds}s`,
    );
  }
  // A payload dated meaningfully in the future indicates a forged auth_date.
  if (ageSeconds < -300) {
    throw new InitDataError('EXPIRED', 'initData auth_date is in the future');
  }

  const userRaw = params.get('user');
  if (!userRaw) {
    throw new InitDataError('NO_USER', 'initData carries no user payload');
  }

  let userJson: unknown;
  try {
    userJson = JSON.parse(userRaw);
  } catch {
    throw new InitDataError('MALFORMED', 'initData user payload is not valid JSON');
  }

  const user = TelegramUserSchema.safeParse(userJson);
  if (!user.success) {
    throw new InitDataError('MALFORMED', 'initData user payload failed validation');
  }

  return {
    user: user.data,
    authDate: new Date(authDateSeconds * 1000),
    startParam: params.get('start_param'),
    chatInstance: params.get('chat_instance'),
    queryId: params.get('query_id'),
    raw: initData,
  };
}
