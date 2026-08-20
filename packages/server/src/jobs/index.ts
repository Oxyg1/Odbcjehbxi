import { PRESENCE_TTL_SECONDS } from '@tgdonate/shared';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { donationService } from '../services/donation.service.js';
import { giftService } from '../services/gift.service.js';
import { leaderboardService } from '../services/leaderboard.service.js';

/**
 * Background maintenance. Each job is defensive: a failure logs and the next
 * tick retries, because none of this sits on a user's critical path.
 */
const timers: NodeJS.Timeout[] = [];

function every(intervalMs: number, name: string, job: () => Promise<unknown>): void {
  const timer = setInterval(() => {
    void job().catch((error) => logger.error({ err: error, job: name }, 'background job failed'));
  }, intervalMs);
  // Do not hold the process open for a maintenance timer.
  timer.unref();
  timers.push(timer);
}

export function startBackgroundJobs(): void {
  // The badge index drives the crown on every avatar; refresh often enough to
  // feel live, not so often that it hammers Redis.
  every(60_000, 'refresh-badges', () => leaderboardService.refreshBadges());

  // Invoices the user opened but never paid.
  every(5 * 60_000, 'expire-intents', async () => {
    const expired = await donationService.expireStaleIntents();
    if (expired > 0) logger.info({ expired }, 'expired stale payment intents');
  });

  // Gifts locked for a purchase that never completed.
  every(10 * 60_000, 'reclaim-escrow', async () => {
    const reclaimed = await giftService.reclaimStaleEscrow();
    if (reclaimed > 0) logger.info({ reclaimed }, 'reclaimed stale gift escrow');
  });

  // Room sessions whose socket died without a clean close.
  every(2 * 60_000, 'sweep-sessions', async () => {
    const cutoff = new Date(Date.now() - PRESENCE_TTL_SECONDS * 1000 * 3);
    const result = await prisma.roomSession.updateMany({
      where: { leftAt: null, lastHeartbeat: { lt: cutoff } },
      data: { leftAt: new Date() },
    });
    if (result.count > 0) logger.debug({ closed: result.count }, 'closed dead room sessions');
  });

  logger.info({ jobs: timers.length }, 'background jobs started');
}

export function stopBackgroundJobs(): void {
  for (const timer of timers) clearInterval(timer);
  timers.length = 0;
}
