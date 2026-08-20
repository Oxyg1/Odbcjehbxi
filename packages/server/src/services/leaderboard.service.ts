import {
  RedisKeys,
  dailyBucket,
  weeklyBucket,
  type Leaderboard,
  type LeaderboardRow,
  type LeaderboardScope,
  type WhaleBadge,
} from '@tgdonate/shared';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { redis } from '../lib/redis.js';
import { publicUserSelect, toPublicUser, userService } from './user.service.js';

const LEADERBOARD_SIZE = 100;
const BADGE_DEPTH = 10;
/** Daily/weekly sorted sets self-expire; all-time is kept indefinitely. */
const BUCKET_TTL_SECONDS: Record<LeaderboardScope, number | null> = {
  DAILY: 60 * 60 * 36,
  WEEKLY: 60 * 60 * 24 * 9,
  ALL_TIME: null,
};

export function bucketFor(scope: LeaderboardScope, now: Date = new Date()): string {
  switch (scope) {
    case 'DAILY':
      return dailyBucket(now);
    case 'WEEKLY':
      return weeklyBucket(now);
    case 'ALL_TIME':
      return 'all';
  }
}

export const leaderboardService = {
  /**
   * Credit a settled donation across all three scopes.
   *
   * Redis sorted sets are the hot path (O(log N) per increment, no lock), and
   * the Postgres rows are the durable mirror so a cache flush is recoverable.
   */
  async recordDonation(input: {
    donorId: string;
    starsDonated: number;
    giftsDonated: number;
    at?: Date;
  }): Promise<void> {
    const now = input.at ?? new Date();
    const scopes: LeaderboardScope[] = ['DAILY', 'WEEKLY', 'ALL_TIME'];

    const pipeline = redis.pipeline();
    for (const scope of scopes) {
      const bucket = bucketFor(scope, now);
      const key = RedisKeys.leaderboard(scope, bucket);
      // Gifts count toward rank at their star-equivalent, already folded into
      // starsDonated by the caller; here we only need the score bump.
      pipeline.zincrby(key, input.starsDonated, input.donorId);
      const ttl = BUCKET_TTL_SECONDS[scope];
      if (ttl !== null) pipeline.expire(key, ttl);
    }
    await pipeline.exec().catch((error) => {
      logger.warn({ err: error }, 'leaderboard redis update failed');
      return null;
    });

    await Promise.all(
      scopes.map((scope) => {
        const bucket = bucketFor(scope, now);
        return prisma.leaderboardEntry.upsert({
          where: { scope_bucket_userId: { scope, bucket, userId: input.donorId } },
          create: {
            scope,
            bucket,
            userId: input.donorId,
            starsDonated: input.starsDonated,
            giftsDonated: input.giftsDonated,
          },
          update: {
            starsDonated: { increment: input.starsDonated },
            giftsDonated: { increment: input.giftsDonated },
          },
        });
      }),
    ).catch((error) => {
      logger.error({ err: error }, 'leaderboard persistence failed');
      return [];
    });
  },

  async get(
    scope: LeaderboardScope,
    options: { limit?: number; viewerId?: string | null; now?: Date } = {},
  ): Promise<Leaderboard> {
    const now = options.now ?? new Date();
    const bucket = bucketFor(scope, now);
    const limit = Math.min(options.limit ?? 50, LEADERBOARD_SIZE);
    const key = RedisKeys.leaderboard(scope, bucket);

    let ranked = await redis
      .zrevrange(key, 0, limit - 1, 'WITHSCORES')
      .catch(() => [] as string[]);

    // Cold cache (deploy, eviction, flush): rebuild from Postgres so the board
    // is never blank, then warm Redis back up for the next reader.
    if (ranked.length === 0) {
      ranked = await this.rebuildFromDatabase(scope, bucket, limit);
    }

    const userIds: string[] = [];
    const scores = new Map<string, number>();
    for (let index = 0; index < ranked.length; index += 2) {
      const userId = ranked[index];
      const score = Number(ranked[index + 1] ?? 0);
      if (!userId) continue;
      userIds.push(userId);
      scores.set(userId, score);
    }

    const rows = await this.hydrate(userIds, scores, scope, bucket);
    const viewer = options.viewerId
      ? await this.viewerRow(options.viewerId, scope, bucket, rows)
      : null;

    return { scope, bucket, rows, viewer, updatedAt: new Date().toISOString() };
  },

  async hydrate(
    userIds: string[],
    scores: Map<string, number>,
    scope: LeaderboardScope,
    bucket: string,
  ): Promise<LeaderboardRow[]> {
    if (userIds.length === 0) return [];

    const [users, entries] = await Promise.all([
      prisma.user.findMany({ where: { id: { in: userIds } }, select: publicUserSelect }),
      prisma.leaderboardEntry.findMany({
        where: { scope, bucket, userId: { in: userIds } },
        select: { userId: true, giftsDonated: true },
      }),
    ]);

    const usersById = new Map(users.map((user) => [user.id, user]));
    const giftsById = new Map(entries.map((entry) => [entry.userId, entry.giftsDonated]));

    const rows: LeaderboardRow[] = [];
    for (const userId of userIds) {
      const user = usersById.get(userId);
      if (!user) continue; // Deleted account; skip rather than render a ghost row.
      rows.push({
        rank: rows.length + 1,
        user: toPublicUser(user),
        starsDonated: Math.round(scores.get(userId) ?? 0),
        giftsDonated: giftsById.get(userId) ?? 0,
      });
    }
    return rows;
  },

  async viewerRow(
    viewerId: string,
    scope: LeaderboardScope,
    bucket: string,
    topRows: LeaderboardRow[],
  ): Promise<LeaderboardRow | null> {
    const inTop = topRows.find((row) => row.user.id === viewerId);
    if (inTop) return inTop;

    const key = RedisKeys.leaderboard(scope, bucket);
    const [rank, score] = await Promise.all([
      redis.zrevrank(key, viewerId).catch(() => null),
      redis.zscore(key, viewerId).catch(() => null),
    ]);
    if (rank === null || score === null) return null;

    const user = await prisma.user.findUnique({
      where: { id: viewerId },
      select: publicUserSelect,
    });
    if (!user) return null;

    const entry = await prisma.leaderboardEntry.findUnique({
      where: { scope_bucket_userId: { scope, bucket, userId: viewerId } },
      select: { giftsDonated: true },
    });

    return {
      rank: rank + 1,
      user: toPublicUser(user),
      starsDonated: Math.round(Number(score)),
      giftsDonated: entry?.giftsDonated ?? 0,
    };
  },

  /** Warm Redis from the durable mirror. Returns the same shape as ZREVRANGE. */
  async rebuildFromDatabase(
    scope: LeaderboardScope,
    bucket: string,
    limit: number,
  ): Promise<string[]> {
    const entries = await prisma.leaderboardEntry.findMany({
      where: { scope, bucket },
      orderBy: { starsDonated: 'desc' },
      take: LEADERBOARD_SIZE,
      select: { userId: true, starsDonated: true },
    });
    if (entries.length === 0) return [];

    const key = RedisKeys.leaderboard(scope, bucket);
    const pipeline = redis.pipeline();
    for (const entry of entries) {
      pipeline.zadd(key, entry.starsDonated, entry.userId);
    }
    const ttl = BUCKET_TTL_SECONDS[scope];
    if (ttl !== null) pipeline.expire(key, ttl);
    await pipeline.exec().catch(() => null);

    const flattened: string[] = [];
    for (const entry of entries.slice(0, limit)) {
      flattened.push(entry.userId, entry.starsDonated.toString());
    }
    return flattened;
  },

  /**
   * Refresh the in-process badge index. Called on a timer and after every
   * whale-tier settlement so the crown moves in near real time.
   */
  async refreshBadges(now: Date = new Date()): Promise<void> {
    const scopes: LeaderboardScope[] = ['ALL_TIME', 'WEEKLY', 'DAILY'];
    for (const scope of scopes) {
      const bucket = bucketFor(scope, now);
      const ranked = await redis
        .zrevrange(RedisKeys.leaderboard(scope, bucket), 0, BADGE_DEPTH - 1, 'WITHSCORES')
        .catch(() => [] as string[]);

      const badges: Array<{ userId: string; badge: WhaleBadge }> = [];
      for (let index = 0; index < ranked.length; index += 2) {
        const userId = ranked[index];
        if (!userId) continue;
        badges.push({
          userId,
          badge: {
            scope,
            rank: index / 2 + 1,
            starsDonated: Math.round(Number(ranked[index + 1] ?? 0)),
          },
        });
      }
      userService.setBadges(badges, scope);
    }
  },
};
