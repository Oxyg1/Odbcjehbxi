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
  logger.info('database and redis reachable');

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

main().catch((error) => {
  logger.fatal({ err: error }, 'failed to start');
  process.exit(1);
});
