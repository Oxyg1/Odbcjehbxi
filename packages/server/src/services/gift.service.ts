import type { GiftRarity } from '@tgdonate/shared';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { withLock } from '../lib/redis.js';
import { bot } from '../telegram/bot.js';
import { ForbiddenError } from './stand.service.js';

/**
 * Telegram NFT Gift ownership and escrow.
 *
 * Telegram is the custodian of record: we mirror ownership locally so the UI is
 * fast, and re-verify against the Bot API before any transfer so a stale mirror
 * cannot be used to sell a gift the user no longer holds.
 */

export class GiftError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'GiftError';
    this.code = code;
  }
}

interface TelegramOwnedGift {
  owned_gift_id?: string;
  type?: string;
  gift?: {
    id?: string;
    base_name?: string;
    name?: string;
    model?: { name?: string; rarity_per_mille?: number };
    backdrop?: { name?: string; rarity_per_mille?: number };
    symbol?: { name?: string; rarity_per_mille?: number };
  };
}

export const giftService = {
  /**
   * Pull the caller's gift inventory from Telegram and reconcile it with our
   * mirror. Gifts that disappeared upstream are marked RECLAIMED rather than
   * deleted, so historical listings still resolve.
   */
  async syncInventory(userId: string): Promise<number> {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { telegramId: true },
    });
    if (!user) throw new GiftError('USER_NOT_FOUND', 'User not found');

    let owned: TelegramOwnedGift[];
    try {
      // `getBusinessAccountGifts`/`getUserGifts` availability varies by bot
      // permissions; a failure here is non-fatal — the mirror simply goes stale.
      const response = (await bot.api.raw.getUserGifts?.({
        user_id: Number(user.telegramId),
      } as never)) as { gifts?: TelegramOwnedGift[] } | undefined;
      owned = response?.gifts ?? [];
    } catch (error) {
      logger.warn({ err: error, userId }, 'could not fetch gifts from Telegram');
      return 0;
    }

    const seenIds: string[] = [];
    for (const entry of owned) {
      const telegramGiftId = entry.owned_gift_id ?? entry.gift?.id;
      if (!telegramGiftId) continue;
      seenIds.push(telegramGiftId);

      const attributes = buildAttributes(entry);
      const rarity = inferRarity(attributes);

      await prisma.gift.upsert({
        where: { telegramGiftId },
        create: {
          telegramGiftId,
          slug: entry.gift?.base_name ?? entry.gift?.name ?? 'gift',
          title: entry.gift?.name ?? entry.gift?.base_name ?? 'Telegram Gift',
          rarity,
          attributes: attributes as never,
          ownerId: userId,
          state: 'HELD_BY_OWNER',
        },
        update: {
          ownerId: userId,
          title: entry.gift?.name ?? entry.gift?.base_name ?? 'Telegram Gift',
          rarity,
          attributes: attributes as never,
        },
      });
    }

    // Anything we believed this user held but Telegram no longer reports.
    if (seenIds.length > 0) {
      await prisma.gift.updateMany({
        where: {
          ownerId: userId,
          state: 'HELD_BY_OWNER',
          telegramGiftId: { notIn: seenIds },
        },
        data: { state: 'RECLAIMED' },
      });
    }

    return seenIds.length;
  },

  async listForUser(userId: string) {
    return prisma.gift.findMany({
      where: { ownerId: userId, state: { in: ['HELD_BY_OWNER', 'IN_ESCROW'] } },
      orderBy: [{ rarity: 'desc' }, { createdAt: 'desc' }],
      include: { listing: { select: { id: true, status: true } } },
    });
  },

  /**
   * Move a gift into escrow for a pending transaction. Serialised per gift: two
   * buyers hitting "Buy" on the same gift in the same instant must not both get
   * an invoice.
   */
  async lockForTransaction(giftId: string, transactionId: string): Promise<void> {
    await withLock(`gift:${giftId}`, async () => {
      const gift = await prisma.gift.findUnique({
        where: { id: giftId },
        select: { state: true, escrowedForTxId: true },
      });
      if (!gift) throw new GiftError('NOT_FOUND', 'Gift not found');

      if (gift.state === 'IN_ESCROW' && gift.escrowedForTxId !== transactionId) {
        throw new GiftError('ALREADY_ESCROWED', 'This gift is already reserved');
      }
      if (gift.state === 'TRANSFERRED') {
        throw new GiftError('ALREADY_SOLD', 'This gift has already been transferred');
      }

      await prisma.gift.update({
        where: { id: giftId },
        data: {
          state: 'IN_ESCROW',
          escrowedForTxId: transactionId,
          escrowedAt: new Date(),
        },
      });
    });
  },

  /** Release escrow when a purchase falls through. */
  async releaseEscrow(giftId: string): Promise<void> {
    await prisma.gift.updateMany({
      where: { id: giftId, state: 'IN_ESCROW' },
      data: { state: 'HELD_BY_OWNER', escrowedForTxId: null, escrowedAt: null },
    });
  },

  /**
   * Register a gift the platform observed arriving as a donation. Called by the
   * gift-transfer webhook listener.
   */
  async recordIncomingGift(input: {
    telegramGiftId: string;
    receiverTelegramId: number;
    slug: string;
    title: string;
    rarity: GiftRarity;
    previewUrl?: string | null;
  }) {
    const receiver = await prisma.user.findUnique({
      where: { telegramId: BigInt(input.receiverTelegramId) },
      select: { id: true },
    });
    if (!receiver) throw new GiftError('USER_NOT_FOUND', 'Receiver is not a TgDonate user');

    return prisma.gift.upsert({
      where: { telegramGiftId: input.telegramGiftId },
      create: {
        telegramGiftId: input.telegramGiftId,
        slug: input.slug,
        title: input.title,
        rarity: input.rarity,
        previewUrl: input.previewUrl ?? null,
        ownerId: receiver.id,
        state: 'HELD_BY_OWNER',
      },
      update: { ownerId: receiver.id, state: 'HELD_BY_OWNER' },
    });
  },

  async assertOwnership(userId: string, giftId: string): Promise<void> {
    const gift = await prisma.gift.findUnique({
      where: { id: giftId },
      select: { ownerId: true },
    });
    if (!gift) throw new GiftError('NOT_FOUND', 'Gift not found');
    if (gift.ownerId !== userId) throw new ForbiddenError('You do not own this gift');
  },

  /** Escrow that nobody completed: return the asset after a grace period. */
  async reclaimStaleEscrow(olderThanMs = 30 * 60_000): Promise<number> {
    const cutoff = new Date(Date.now() - olderThanMs);
    const result = await prisma.gift.updateMany({
      where: { state: 'IN_ESCROW', escrowedAt: { lt: cutoff } },
      data: { state: 'HELD_BY_OWNER', escrowedForTxId: null, escrowedAt: null },
    });
    return result.count;
  },
};

function buildAttributes(entry: TelegramOwnedGift) {
  const attributes: Array<{ type: string; name: string; rarityPermille: number }> = [];
  const gift = entry.gift;
  if (gift?.model?.name) {
    attributes.push({
      type: 'MODEL',
      name: gift.model.name,
      rarityPermille: gift.model.rarity_per_mille ?? 0,
    });
  }
  if (gift?.backdrop?.name) {
    attributes.push({
      type: 'BACKDROP',
      name: gift.backdrop.name,
      rarityPermille: gift.backdrop.rarity_per_mille ?? 0,
    });
  }
  if (gift?.symbol?.name) {
    attributes.push({
      type: 'SYMBOL',
      name: gift.symbol.name,
      rarityPermille: gift.symbol.rarity_per_mille ?? 0,
    });
  }
  return attributes;
}

/**
 * Telegram reports per-attribute rarity in permille. The scarcest attribute
 * drives the gift's overall band, which is what the VFX tiering keys on.
 */
function inferRarity(
  attributes: Array<{ rarityPermille: number }>,
): GiftRarity {
  if (attributes.length === 0) return 'COMMON';
  const scarcest = Math.min(...attributes.map((attribute) => attribute.rarityPermille || 1000));
  if (scarcest <= 5) return 'LEGENDARY';
  if (scarcest <= 20) return 'EPIC';
  if (scarcest <= 100) return 'RARE';
  return 'COMMON';
}
