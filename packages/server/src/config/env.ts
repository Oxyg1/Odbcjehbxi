import { randomUUID } from 'node:crypto';
import { z } from 'zod';

/**
 * Environment contract. Parsed once at boot — a missing or malformed variable
 * is a startup failure, never a runtime surprise mid-payment.
 */
/** Strip whitespace and any wrapping quotes from a secret read out of .env. */
function cleanSecret(value: string): string {
  return value.trim().replace(/^["']|["']$/g, '');
}

const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3000),
  HOST: z.string().default('0.0.0.0'),

  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),

  /*
   * Bot token — also the HMAC seed for initData verification.
   *
   * Trimmed deliberately: the token is hashed byte-for-byte, so a stray space
   * or a CR from a CRLF-saved .env changes the derived secret and every launch
   * fails BAD_SIGNATURE — while the bot itself keeps working, because the
   * Telegram API tolerates the same whitespace in a URL. Surrounding quotes are
   * stripped for the same reason; people copy tokens with them.
   */
  TELEGRAM_BOT_TOKEN: z.string().transform(cleanSecret).pipe(z.string().min(20)),
  /** Secret path segment for the Telegram webhook route. */
  TELEGRAM_WEBHOOK_SECRET: z.string().transform(cleanSecret).pipe(z.string().min(16)),
  /** Public https base of this API, used to register the webhook. */
  PUBLIC_API_URL: z.string().url(),
  /** Public https base of the Mini App, used for deep links. */
  PUBLIC_WEBAPP_URL: z.string().url(),
  /** Bot username without `@`, used to build `t.me` start links. */
  BOT_USERNAME: z.string().min(1),

  /** Comma-separated CORS allow-list. */
  CORS_ORIGINS: z.string().default(''),

  /** Rejects initData older than this many seconds. */
  INITDATA_MAX_AGE_SECONDS: z.coerce.number().int().positive().default(86_400),

  /** Platform fee in basis points. */
  PLATFORM_FEE_BPS: z.coerce.number().int().min(0).max(10_000).default(500),

  /** TON. */
  TON_API_ENDPOINT: z.string().url().default('https://toncenter.com/api/v2/jsonRPC'),
  TON_API_KEY: z.string().optional(),
  /** Escrow wallet that receives TON payments. */
  TON_ESCROW_ADDRESS: z.string().optional(),
  /** Poll interval for the chain watcher, in ms. */
  TON_POLL_INTERVAL_MS: z.coerce.number().int().min(2_000).default(8_000),

  /** Set false on read-replica/worker nodes that must not own the bot. */
  ENABLE_BOT: z
    .enum(['true', 'false'])
    .default('true')
    .transform((v) => v === 'true'),
  ENABLE_TON_WATCHER: z
    .enum(['true', 'false'])
    .default('false')
    .transform((v) => v === 'true'),
  /** `webhook` in production, `polling` for local development. */
  BOT_MODE: z.enum(['webhook', 'polling']).default('polling'),

  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
});

export type Env = z.infer<typeof EnvSchema> & {
  /** Unique per-process id; stamped on every Redis broadcast envelope. */
  NODE_ID: string;
  corsOrigins: string[];
};

function load(): Env {
  const parsed = EnvSchema.safeParse(process.env);
  if (!parsed.success) {
    const details = parsed.error.issues
      .map((issue) => `  - ${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('\n');
    throw new Error(`Invalid environment configuration:\n${details}`);
  }
  const corsOrigins = parsed.data.CORS_ORIGINS.split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);

  return {
    ...parsed.data,
    NODE_ID: process.env.NODE_ID ?? randomUUID(),
    corsOrigins,
  };
}

export const env: Env = load();

/**
 * True when the raw token carried characters that would have broken the
 * initData HMAC. Reported at boot so a silently-mistyped .env is visible.
 */
export const botTokenWasCleaned =
  (process.env.TELEGRAM_BOT_TOKEN ?? '') !== env.TELEGRAM_BOT_TOKEN;

/** Bot id — the part of the token before the colon. Not a secret. */
export const botId = env.TELEGRAM_BOT_TOKEN.split(':')[0] ?? 'unknown';

export const isProduction = env.NODE_ENV === 'production';
