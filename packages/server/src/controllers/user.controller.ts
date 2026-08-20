import type { FastifyInstance } from 'fastify';
import { toNumberId } from '../lib/prisma.js';
import { prisma } from '../lib/prisma.js';
import { getAuth, requireTelegramAuth } from '../middleware/auth.js';
import { giftService } from '../services/gift.service.js';
import { leaderboardService } from '../services/leaderboard.service.js';
import { toPublicUser, userService } from '../services/user.service.js';
import { projectTheme } from '../services/stand.service.js';
import { sendError } from './errors.js';
import { LeaderboardQuery } from './schemas.js';

export async function userRoutes(app: FastifyInstance): Promise<void> {
  /** Session bootstrap: identity, wallet, counters, unlocked themes. */
  app.get('/api/me', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user, initData } = getAuth(request);
      const unlockedThemes = await prisma.userTheme.findMany({
        where: { userId: user.id },
        select: { themeId: true },
      });

      return await reply.send({
        user: {
          ...toPublicUser(user),
          telegramId: toNumberId(user.telegramId),
          tonWallet: user.tonWalletRaw,
          starsDonated: user.starsDonated,
          starsReceived: user.starsReceived,
          giftsDonated: user.giftsDonated,
          giftsReceived: user.giftsReceived,
        },
        unlockedThemeIds: unlockedThemes.map((row) => row.themeId),
        // Deep-link target from `?startapp=`, e.g. `stand_<id>` or `room_<slug>`.
        startParam: initData.startParam,
      });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/leaderboard', async (request, reply) => {
    try {
      const { scope, limit } = LeaderboardQuery.parse(request.query);
      // The board is public, but a signed request also gets its own row back.
      const initDataUser = request.auth?.user ?? null;
      const board = await leaderboardService.get(scope, {
        limit,
        viewerId: initDataUser?.id ?? null,
      });
      return await reply.send({ leaderboard: board });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/themes', async (_request, reply) => {
    try {
      const themes = await prisma.standTheme.findMany({
        where: { isActive: true },
        orderBy: [{ priceStars: 'asc' }, { createdAt: 'asc' }],
      });
      return await reply.send({ themes: themes.map(projectTheme) });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/me/gifts', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const gifts = await giftService.listForUser(user.id);
      return await reply.send({
        gifts: gifts.map((gift) => ({
          id: gift.id,
          telegramGiftId: gift.telegramGiftId,
          slug: gift.slug,
          title: gift.title,
          rarity: gift.rarity,
          previewUrl: gift.previewUrl,
          attributes: gift.attributes,
          state: gift.state,
          listingId: gift.listing?.id ?? null,
        })),
      });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.post('/api/me/gifts/sync', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const synced = await giftService.syncInventory(user.id);
      return await reply.send({ synced });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/users/:id', async (request, reply) => {
    try {
      const { id } = request.params as { id: string };
      const user = await userService.findById(id);
      if (!user) {
        return await reply.code(404).send({ error: 'NOT_FOUND', message: 'User not found' });
      }
      return await reply.send({ user: toPublicUser(user) });
    } catch (error) {
      return sendError(reply, error);
    }
  });
}
