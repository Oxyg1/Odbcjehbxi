import { webhookCallback } from 'grammy';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { claimOnce } from '../lib/redis.js';
import { donationService } from '../services/donation.service.js';
import { giftService } from '../services/gift.service.js';
import { bot } from '../telegram/bot.js';
import { sendError } from './errors.js';

/**
 * Inbound webhooks.
 *
 * Two surfaces:
 *  - Telegram Bot API updates (payments, commands, inline queries);
 *  - a gift-transfer listener, for the NFT Gift flow that a partner service or
 *    a userbot relays to us.
 *
 * Both are authenticated by a shared secret and both de-duplicate before doing
 * any work, because both providers retry on non-2xx.
 */

const GiftTransferEvent = z.object({
  eventId: z.string().min(1).max(128),
  telegramGiftId: z.string().min(1).max(128),
  fromTelegramId: z.number().int().positive(),
  toTelegramId: z.number().int().positive(),
  slug: z.string().min(1).max(64),
  title: z.string().min(1).max(128),
  rarity: z.enum(['COMMON', 'RARE', 'EPIC', 'LEGENDARY']),
  previewUrl: z.string().url().nullable().optional(),
  /** Set when the transfer settles a listing purchase we already know about. */
  transactionId: z.string().min(1).max(64).nullable().optional(),
});

export async function webhookRoutes(app: FastifyInstance): Promise<void> {
  if (env.ENABLE_BOT && env.BOT_MODE === 'webhook') {
    const handler = webhookCallback(bot, 'fastify', {
      secretToken: env.TELEGRAM_WEBHOOK_SECRET,
    });

    app.post(`/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`, handler);
    logger.info('telegram webhook route mounted');
  }

  /**
   * NFT Gift transfer listener.
   *
   * Telegram does not push gift transfers to bots directly, so this endpoint
   * accepts a relayed event. It is idempotent on `eventId` and re-validates
   * every id against our own tables before crediting anything.
   */
  app.post('/webhooks/gifts', async (request, reply) => {
    const providedSecret = request.headers['x-webhook-secret'];
    if (providedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return reply.code(401).send({ error: 'UNAUTHORIZED', message: 'Bad webhook secret' });
    }

    try {
      const event = GiftTransferEvent.parse(request.body);

      const isFirstDelivery = await claimOnce(`gift-event:${event.eventId}`, 7 * 86_400);
      if (!isFirstDelivery) {
        return await reply.send({ status: 'duplicate' });
      }

      await prisma.processedEvent
        .create({ data: { source: 'gift_transfer', externalId: event.eventId } })
        .catch(() => undefined);

      const gift = await giftService.recordIncomingGift({
        telegramGiftId: event.telegramGiftId,
        receiverTelegramId: event.toTelegramId,
        slug: event.slug,
        title: event.title,
        rarity: event.rarity,
        previewUrl: event.previewUrl ?? null,
      });

      // A gift arriving against a known intent settles it, which is what fires
      // the donation VFX for gift-only donations.
      if (event.transactionId) {
        const transaction = await prisma.donationTransaction.findUnique({
          where: { id: event.transactionId },
          select: { id: true, status: true },
        });
        if (transaction && transaction.status !== 'SETTLED') {
          await prisma.donationTransaction.update({
            where: { id: transaction.id },
            data: { giftId: gift.id },
          });
          await donationService.settle(transaction.id);
        }
      }

      return await reply.send({ status: 'ok', giftId: gift.id });
    } catch (error) {
      return sendError(reply, error);
    }
  });
}
