// Must run before any other import: config/env.ts reads process.env at module
// load time, and process managers like pm2 do not source .env files on their
// own the way `npm run` / the Prisma CLI do.
import 'dotenv/config';
import { env } from './config/env.js';
import { buildApp } from './app.js';
import { logger } from './lib/logger.js';
import { disconnectPrisma, prisma } from './lib/prisma.js';
import { disconnectRedis, redis } from './lib/redis.js';
import { startBackgroundJobs, stopBackgroundJobs } from './jobs/index.js';
import { RealtimeGateway, setGateway } from './realtime/gateway.js';
import { leaderboardService } from './services/leaderboard.service.js';
import { startBot, stopBot } from './telegram/bot.js';
import { tonWatcher } from './ton/watcher.js';

async function main(): Promise<void> {
  // Fail fast on a dependency that is down: a half-alive node that accepts
  // payments it cannot record is worse than a node that never starts.
  await prisma.$queryRaw`SELECT 1`;
  await redis.ping();

  // `SELECT 1` succeeds against an empty database, so it does not prove the
  // schema is there. Without this check an unmigrated deployment boots happily
  // and then returns 500 from every data route, which is far harder to diagnose
  // than a refusal to start.
  await assertSchemaReady();

  logger.info('database and redis reachable, schema ready');

  const app = await buildApp();
  await app.listen({ port: env.PORT, host: env.HOST });

  const gateway = new RealtimeGateway(app.server);
  setGateway(gateway);
  await gateway.start();

  await startBot();
  await tonWatcher.start();
  await leaderboardService.refreshBadges().catch(() => undefined);
  startBackgroundJobs();

  logger.info(
    { port: env.PORT, mode: env.BOT_MODE, env: env.NODE_ENV },
    'TgDonate API is up',
  );

  const shutdown = async (signal: string): Promise<void> => {
    logger.info({ signal }, 'shutting down');
    stopBackgroundJobs();
    tonWatcher.stop();
    await stopBot().catch(() => undefined);
    await gateway.stop().catch(() => undefined);
    await app.close().catch(() => undefined);
    await disconnectRedis().catch(() => undefined);
    await disconnectPrisma().catch(() => undefined);
    process.exit(0);
  };

  process.on('SIGTERM', () => void shutdown('SIGTERM'));
  process.on('SIGINT', () => void shutdown('SIGINT'));

  process.on('unhandledRejection', (reason) => {
    logger.error({ reason }, 'unhandled promise rejection');
  });
  process.on('uncaughtException', (error) => {
    logger.fatal({ err: error }, 'uncaught exception, exiting');
    process.exit(1);
  });
}

/**
 * Verify the database has been migrated and seeded before serving traffic.
 *
 * Two distinct failures get two distinct messages, because the fixes differ:
 * missing tables means migrations were never applied, while empty tables mean
 * the seed never ran. A stand cannot be created without a free theme, so an
 * unseeded database breaks the app's very first screen.
 */
async function assertSchemaReady(): Promise<void> {
  let themeCount: number;
  try {
    themeCount = await prisma.standTheme.count();
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === 'P2021' || code === 'P2022') {
      throw new Error(
        'Database schema is missing. Run `npm run prisma:deploy` (then `npm run db:seed`) before starting the server.',
      );
    }
    throw error;
  }

  if (themeCount === 0) {
    throw new Error(
      'Database has no stand themes. Run `npm run db:seed` — stands cannot be created without a free theme.',
    );
  }

  const roomCount = await prisma.room.count();
  if (roomCount === 0) {
    logger.warn('no rooms are seeded; the room picker will be empty until `npm run db:seed` runs');
  }
}

main().catch((error) => {
  logger.fatal({ err: error }, 'failed to start');
  process.exit(1);
});
