/**
 * Deployment doctor.
 *
 * Checks the whole chain a Mini App request travels — environment, database,
 * schema, seed, Redis, bot identity, webhook — and names the fix for whatever
 * it finds. Written because diagnosing these one shell command at a time is
 * slow and easy to get subtly wrong (quoting a token through `tr` especially).
 *
 * Read-only: it never writes to the database or changes bot configuration.
 */
import 'dotenv/config';
import { PrismaClient } from '@prisma/client';
import { Redis } from 'ioredis';

type Status = 'ok' | 'warn' | 'fail';

interface Result {
  label: string;
  status: Status;
  detail: string;
  fix?: string;
}

/**
 * Telegram API base. Overridable so this can run behind an egress proxy, and
 * so the identity checks below are testable without reaching the real API.
 */
const TELEGRAM_API = (process.env.TELEGRAM_API_BASE ?? 'https://api.telegram.org').replace(
  /\/$/,
  '',
);

const results: Result[] = [];
const add = (label: string, status: Status, detail: string, fix?: string): void => {
  results.push({ label, status, detail, ...(fix ? { fix } : {}) });
};

/** Never print a secret. Show only enough to tell two values apart. */
function mask(secret: string): string {
  if (secret.length <= 8) return '***';
  return `${secret.slice(0, 4)}…${secret.slice(-4)}`;
}

function cleanSecret(value: string): string {
  return value.trim().replace(/^["']|["']$/g, '');
}

async function checkEnvironment(): Promise<{ token: string; botIdFromToken: string } | null> {
  // Report on every variable before returning: a doctor that stops at the
  // first fault makes the operator fix one thing and run it again.
  for (const [name, value] of [
    ['DATABASE_URL', process.env.DATABASE_URL],
    ['REDIS_URL', process.env.REDIS_URL],
  ] as const) {
    if (!value) add(name, 'fail', 'not set', 'Add it to packages/server/.env.');
  }

  const webappUrl = process.env.PUBLIC_WEBAPP_URL;
  if (webappUrl && !webappUrl.startsWith('https://')) {
    add(
      'PUBLIC_WEBAPP_URL',
      'warn',
      `${webappUrl} is not https`,
      'Telegram only opens Mini Apps over https.',
    );
  }

  const raw = process.env.TELEGRAM_BOT_TOKEN;
  if (!raw) {
    add(
      'TELEGRAM_BOT_TOKEN',
      'fail',
      'not set',
      'Add it to packages/server/.env — the server reads that file, not the repo root.',
    );
    return null;
  }

  const token = cleanSecret(raw);
  if (token !== raw) {
    add(
      'TELEGRAM_BOT_TOKEN',
      'warn',
      'had surrounding whitespace or quotes (auto-cleaned)',
      'Tidy the line in .env. Untrimmed, this breaks initData while the bot keeps working.',
    );
  }

  const parts = token.split(':');
  const botIdFromToken = parts[0] ?? '';
  if (parts.length !== 2 || !/^\d+$/.test(botIdFromToken)) {
    add(
      'TELEGRAM_BOT_TOKEN',
      'fail',
      `malformed (${mask(token)}) — expected <digits>:<secret>`,
      'Copy the token again from @BotFather.',
    );
    return null;
  }

  add('TELEGRAM_BOT_TOKEN', 'ok', `bot id ${botIdFromToken}, token ${mask(token)}`);
  return { token, botIdFromToken };
}

async function checkBot(token: string, botIdFromToken: string): Promise<void> {
  let payload: {
    ok?: boolean;
    result?: { id?: number; username?: string };
    description?: string;
  };
  try {
    const response = await fetch(`${TELEGRAM_API}/bot${token}/getMe`);
    const body = await response.text();
    try {
      payload = JSON.parse(body) as typeof payload;
    } catch {
      // A non-JSON body means something answered instead of Telegram — a proxy,
      // a captive portal, a firewall page. Say that, rather than surfacing a
      // JSON parse error the operator has to decode.
      add(
        'Telegram getMe',
        'fail',
        `got a non-JSON reply (HTTP ${response.status}) — something other than Telegram answered`,
        'Check outbound HTTPS to api.telegram.org (proxy or firewall in the way?).',
      );
      return;
    }
  } catch (error) {
    add(
      'Telegram getMe',
      'fail',
      `could not reach api.telegram.org: ${(error as Error).message}`,
      'Check outbound network access from this host.',
    );
    return;
  }

  if (!payload.ok || !payload.result) {
    add(
      'Telegram getMe',
      'fail',
      payload.description ?? 'rejected',
      'Telegram does not accept this token. Re-issue it with @BotFather.',
    );
    return;
  }

  const { id, username } = payload.result;
  add('Telegram getMe', 'ok', `token belongs to @${username} (id ${id})`);

  // The id inside the token must match the account Telegram reports. A
  // mismatch means the token was edited or spliced together.
  if (String(id) !== botIdFromToken) {
    add(
      'Bot identity',
      'fail',
      `token prefix is ${botIdFromToken} but Telegram reports ${id}`,
      'The token is corrupted. Copy it again from @BotFather.',
    );
    return;
  }

  add(
    'Bot identity',
    'warn',
    `>>> Open the Mini App from @${username} — initData signed by any OTHER bot fails BAD_SIGNATURE`,
    `In @BotFather: /mybots → @${username} → Bot Settings → Menu Button → set ${
      process.env.PUBLIC_WEBAPP_URL ?? 'your https URL'
    }`,
  );

  if (process.env.BOT_MODE === 'webhook') {
    try {
      const response = await fetch(`${TELEGRAM_API}/bot${token}/getWebhookInfo`);
      const info = (await response.json()) as {
        result?: { url?: string; last_error_message?: string; pending_update_count?: number };
      };
      const url = info.result?.url;
      if (!url) {
        add('Webhook', 'warn', 'BOT_MODE=webhook but no webhook is registered',
          'Restart the server — it registers the webhook at boot.');
      } else {
        add('Webhook', 'ok', url);
        if (info.result?.last_error_message) {
          add('Webhook delivery', 'fail', info.result.last_error_message,
            'Telegram cannot reach the webhook. Check TLS and that nginx proxies /telegram/webhook/.');
        }
      }
    } catch {
      add('Webhook', 'warn', 'could not read webhook info');
    }
  }
}

async function checkDatabase(): Promise<void> {
  if (!process.env.DATABASE_URL) return;
  const prisma = new PrismaClient();
  try {
    await prisma.$queryRaw`SELECT 1`;
    add('PostgreSQL', 'ok', 'reachable');
  } catch (error) {
    add('PostgreSQL', 'fail', (error as Error).message.split('\n')[0] ?? 'unreachable',
      'Is postgres running, and does DATABASE_URL match its user/database?');
    await prisma.$disconnect();
    return;
  }

  try {
    const themes = await prisma.standTheme.count();
    const rooms = await prisma.room.count();
    add('Schema', 'ok', 'tables present');

    if (themes === 0) {
      add('Seed', 'fail', 'no stand themes',
        'Run `npm run db:seed`. Stands cannot be created without a free theme.');
    } else {
      add('Seed', 'ok', `${themes} themes, ${rooms} rooms`);
    }
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === 'P2021' || code === 'P2022') {
      add('Schema', 'fail', 'tables are missing',
        'Run `npm run prisma:deploy`, then `npm run db:seed`.');
    } else {
      add('Schema', 'fail', (error as Error).message.split('\n')[0] ?? 'unknown');
    }
  } finally {
    await prisma.$disconnect();
  }
}

async function checkRedis(): Promise<void> {
  if (!process.env.REDIS_URL) return;
  const redis = new Redis(process.env.REDIS_URL, {
    maxRetriesPerRequest: 1,
    retryStrategy: () => null,
    lazyConnect: true,
  });
  try {
    await redis.connect();
    await redis.ping();
    add('Redis', 'ok', 'reachable');
  } catch (error) {
    add('Redis', 'fail', (error as Error).message,
      'Is redis-server running, and does REDIS_URL point at it?');
  } finally {
    redis.disconnect();
  }
}

function report(): number {
  const icon: Record<Status, string> = { ok: '  OK  ', warn: ' WARN ', fail: ' FAIL ' };
  const width = Math.max(...results.map((r) => r.label.length));

  console.log('\nTgDonate deployment check\n' + '='.repeat(58));
  for (const r of results) {
    console.log(`[${icon[r.status]}] ${r.label.padEnd(width)}  ${r.detail}`);
    if (r.fix) console.log(`${' '.repeat(width + 11)}→ ${r.fix}`);
  }

  const failures = results.filter((r) => r.status === 'fail');
  console.log('='.repeat(58));
  if (failures.length === 0) {
    console.log('No blocking problems found.');
    console.log('If the Mini App still returns BAD_SIGNATURE, it is being opened');
    console.log('from a different bot than the one named above.\n');
    return 0;
  }
  console.log(`${failures.length} blocking problem(s):`);
  for (const f of failures) console.log(`  - ${f.label}: ${f.detail}`);
  console.log('');
  return 1;
}

async function main(): Promise<void> {
  const env = await checkEnvironment();
  if (env) await checkBot(env.token, env.botIdFromToken);
  await checkDatabase();
  await checkRedis();
  process.exit(report());
}

void main();
