import type { Prisma, TransactionStatus } from '@prisma/client';
import {
  GLOBAL_BROADCAST_DURATION_MS,
  resolveTier,
  splitStars,
  type DonationEventPayload,
  type DonationTier,
  type GiftRarity,
  type PaymentMethod,
} from '@tgdonate/shared';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { withLock } from '../lib/redis.js';
import { broadcaster } from '../realtime/broadcaster.js';
import { getGateway } from '../realtime/gateway.js';
import { leaderboardService } from './leaderboard.service.js';
import { projectGift } from './stand.service.js';
import { publicUserSelect, toPublicUser } from './user.service.js';

export interface CreateIntentInput {
  donorId: string | null;
  standId: string;
  listingId?: string | null;
  method: PaymentMethod;
  amountStars: number;
  amountNanoton?: string | null;
  isAnonymous?: boolean;
  message?: string | null;
  giftId?: string | null;
  giftRarity?: GiftRarity | null;
  invoicePayload?: string | null;
}

export class DonationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'DonationError';
    this.code = code;
  }
}

export const donationService = {
  /**
   * Create the transaction row before any money moves. The row is the unit of
   * idempotency: `invoicePayload` is unique, so a duplicated invoice request
   * cannot produce two charges.
   */
  async createIntent(input: CreateIntentInput) {
    const stand = await prisma.stand.findUnique({
      where: { id: input.standId },
      select: { id: true, ownerId: true, roomId: true, isPublished: true },
    });
    if (!stand) throw new DonationError('STAND_NOT_FOUND', 'Stand not found');
    if (!stand.isPublished) throw new DonationError('STAND_HIDDEN', 'This stand is not accepting support');
    if (input.donorId && input.donorId === stand.ownerId) {
      throw new DonationError('SELF_DONATION', 'You cannot donate to your own stand');
    }

    const { tier, valuationStars } = resolveTier({
      amountStars: input.amountStars,
      giftRarity: input.giftRarity ?? null,
    });
    const split = splitStars(input.amountStars, env.PLATFORM_FEE_BPS);

    return prisma.donationTransaction.create({
      data: {
        donorId: input.donorId,
        receiverId: stand.ownerId,
        standId: stand.id,
        roomId: stand.roomId,
        listingId: input.listingId ?? null,
        giftId: input.giftId ?? null,
        method: input.method,
        status: 'AWAITING_PAYMENT',
        tier,
        amountStars: split.gross,
        feeStars: split.fee,
        netStars: split.net,
        feeBps: split.feeBps,
        amountNanoton: input.amountNanoton ?? null,
        valuationStars,
        isAnonymous: input.isAnonymous ?? false,
        message: input.message?.slice(0, 280) ?? null,
        invoicePayload: input.invoicePayload ?? null,
      },
    });
  },

  /**
   * Settle a paid transaction: credit the receiver, bump every aggregate, hand
   * over any escrowed gift, then fire the tiered VFX broadcast.
   *
   * All the money-touching writes happen inside one SQL transaction so a crash
   * midway cannot leave a stand credited without its donor counter moving. The
   * whole thing is wrapped in a per-transaction Redis lock so a webhook replay
   * arriving on another node cannot settle the same row twice.
   */
  async settle(
    transactionId: string,
    settlement: { telegramChargeId?: string | null; tonTxHash?: string | null } = {},
  ): Promise<DonationEventPayload | null> {
    return withLock(`tx:${transactionId}`, async () => {
      const existing = await prisma.donationTransaction.findUnique({
        where: { id: transactionId },
        select: { status: true },
      });
      if (!existing) throw new DonationError('TX_NOT_FOUND', 'Transaction not found');

      // Idempotent by construction: a replayed webhook finds SETTLED and exits.
      if (existing.status === 'SETTLED') {
        logger.debug({ transactionId }, 'settle called on an already settled transaction');
        return null;
      }
      if (existing.status === 'REFUNDED' || existing.status === 'FAILED') {
        throw new DonationError('TX_TERMINAL', `Cannot settle a ${existing.status} transaction`);
      }

      const settled = await prisma.$transaction(async (tx) => {
        const transaction = await tx.donationTransaction.update({
          where: { id: transactionId },
          data: {
            status: 'SETTLED',
            settledAt: new Date(),
            ...(settlement.telegramChargeId
              ? { telegramChargeId: settlement.telegramChargeId }
              : {}),
            ...(settlement.tonTxHash ? { tonTxHash: settlement.tonTxHash } : {}),
          },
          include: {
            donor: { select: publicUserSelect },
            receiver: { select: publicUserSelect },
            stand: { select: { id: true, title: true, roomId: true } },
            gift: true,
          },
        });

        // Two different gift flows move the asset in opposite directions:
        //  * NFT_GIFT   — the donor gives their gift to the stand owner.
        //  * gift sale  — the stand owner sells a gift; the buyer receives it.
        // Only the first counts as a "gift received" for the stand.
        const isGiftDonation = transaction.method === 'NFT_GIFT';
        const isGiftSale = transaction.giftId !== null && !isGiftDonation;

        // Receiver aggregates.
        await tx.user.update({
          where: { id: transaction.receiverId },
          data: {
            starsReceived: { increment: transaction.netStars },
            ...(isGiftDonation ? { giftsReceived: { increment: 1 } } : {}),
          },
        });

        // Donor aggregates.
        if (transaction.donorId) {
          await tx.user.update({
            where: { id: transaction.donorId },
            data: {
              starsDonated: { increment: transaction.amountStars },
              ...(isGiftDonation ? { giftsDonated: { increment: 1 } } : {}),
            },
          });
        }

        // Distinct-supporter count: only increment when this donor has no other
        // settled donation to this stand, otherwise a repeat donor inflates it.
        let isNewSupporter = false;
        if (transaction.donorId) {
          const priorCount = await tx.donationTransaction.count({
            where: {
              standId: transaction.standId,
              donorId: transaction.donorId,
              status: 'SETTLED',
              id: { not: transaction.id },
            },
          });
          isNewSupporter = priorCount === 0;
        }

        await tx.stand.update({
          where: { id: transaction.standId },
          data: {
            totalStarsReceived: { increment: transaction.netStars },
            ...(isGiftDonation ? { totalGiftsReceived: { increment: 1 } } : {}),
            ...(isNewSupporter ? { supporterCount: { increment: 1 } } : {}),
            version: { increment: 1 },
          },
        });

        // Hand over the escrowed gift to whichever side is acquiring it.
        if (transaction.giftId) {
          const newOwnerId = isGiftSale ? transaction.donorId : transaction.receiverId;
          if (newOwnerId) {
            await tx.gift.update({
              where: { id: transaction.giftId },
              data: {
                ownerId: newOwnerId,
                state: 'TRANSFERRED',
                escrowedForTxId: null,
                escrowedAt: null,
              },
            });
          } else {
            // A gift sale with no registered buyer cannot be handed over; the
            // asset returns to its owner rather than vanishing into escrow.
            await tx.gift.update({
              where: { id: transaction.giftId },
              data: { state: 'RECLAIMED', escrowedForTxId: null, escrowedAt: null },
            });
          }
        }

        if (transaction.listingId) {
          const listing = await tx.listing.findUnique({
            where: { id: transaction.listingId },
            select: { supply: true, soldCount: true, kind: true },
          });
          if (listing) {
            const soldOut =
              listing.supply !== null && listing.soldCount + 1 >= listing.supply;
            await tx.listing.update({
              where: { id: transaction.listingId },
              data: {
                // tryReserve already incremented soldCount for capped listings.
                ...(listing.supply === null ? { soldCount: { increment: 1 } } : {}),
                ...(soldOut || listing.kind === 'NFT_GIFT_SALE'
                  ? { status: 'SOLD' as const }
                  : {}),
              },
            });
          }
        }

        return transaction;
      });

      const payload = projectDonation(settled);

      // Post-commit side effects. A failure here must not roll back a payment
      // that already cleared, so each is isolated and logged.
      if (settled.donorId) {
        await leaderboardService
          .recordDonation({
            donorId: settled.donorId,
            starsDonated: settled.amountStars,
            giftsDonated: settled.giftId ? 1 : 0,
            at: settled.settledAt ?? new Date(),
          })
          .catch((error) => logger.error({ err: error }, 'leaderboard credit failed'));
      }

      await this.broadcast(payload, settled.standId).catch((error) =>
        logger.error({ err: error }, 'donation broadcast failed'),
      );

      if (payload.tier === 'WHALE') {
        await leaderboardService
          .refreshBadges()
          .catch((error) => logger.warn({ err: error }, 'badge refresh failed'));
      }

      return payload;
    });
  },

  /**
   * Fan the donation out at the right blast radius.
   *
   *   MICRO → the stand's room only (local confetti)
   *   MAJOR → the stand's room (banner + shake + haptics)
   *   WHALE → every connected client, everywhere
   */
  async broadcast(payload: DonationEventPayload, standId: string): Promise<void> {
    const stand = await prisma.stand.findUnique({
      where: { id: standId },
      select: {
        id: true,
        totalStarsReceived: true,
        totalGiftsReceived: true,
        supporterCount: true,
        roomId: true,
      },
    });
    if (!stand) return;

    const donationFrame = {
      t: 'DONATION_EVENT' as const,
      donation: payload,
      standTotals: {
        standId: stand.id,
        totalStarsReceived: stand.totalStarsReceived,
        totalGiftsReceived: stand.totalGiftsReceived,
        supporterCount: stand.supporterCount,
      },
    };

    if (stand.roomId) {
      await broadcaster.toRoom(stand.roomId, donationFrame);
    } else {
      getGateway()?.deliverToUserLocally(payload.receiver.id, donationFrame);
    }

    if (payload.tier === 'WHALE') {
      await broadcaster.toEveryone({
        t: 'GLOBAL_BROADCAST',
        donation: payload,
        jump: { roomId: stand.roomId, standId: stand.id },
        expiresAt: new Date(Date.now() + GLOBAL_BROADCAST_DURATION_MS).toISOString(),
      });
    }

    await broadcaster.toUser(payload.receiver.id, {
      t: 'USER_NOTICE',
      targetUserId: payload.receiver.id,
      kind: payload.gift ? 'GIFT_RECEIVED' : 'PAYMENT_SETTLED',
      title: payload.gift ? 'Gift received' : `+${payload.amountStars} Stars`,
      body: payload.isAnonymous
        ? 'Someone supported your stand'
        : `${payload.donor?.displayName ?? 'Someone'} supported your stand`,
      meta: {
        transactionId: payload.id,
        standId: stand.id,
        amountStars: payload.amountStars,
      },
    });
  },

  async markStatus(transactionId: string, status: TransactionStatus): Promise<void> {
    await prisma.donationTransaction.update({
      where: { id: transactionId },
      data: {
        status,
        ...(status === 'REFUNDED' ? { refundedAt: new Date() } : {}),
      },
    });
  },

  async findByInvoicePayload(payload: string) {
    return prisma.donationTransaction.findUnique({ where: { invoicePayload: payload } });
  },

  /** Recent settled donations for a stand — the "supporters" list. */
  async recentForStand(standId: string, limit = 20): Promise<DonationEventPayload[]> {
    const rows = await prisma.donationTransaction.findMany({
      where: { standId, status: 'SETTLED' },
      orderBy: { settledAt: 'desc' },
      take: Math.min(limit, 50),
      include: {
        donor: { select: publicUserSelect },
        receiver: { select: publicUserSelect },
        stand: { select: { id: true, title: true, roomId: true } },
        gift: true,
      },
    });
    return rows.map(projectDonation);
  },

  /** The global "recent activity" ticker on the home screen. */
  async recentGlobal(limit = 30): Promise<DonationEventPayload[]> {
    const rows = await prisma.donationTransaction.findMany({
      where: { status: 'SETTLED' },
      orderBy: { settledAt: 'desc' },
      take: Math.min(limit, 50),
      include: {
        donor: { select: publicUserSelect },
        receiver: { select: publicUserSelect },
        stand: { select: { id: true, title: true, roomId: true } },
        gift: true,
      },
    });
    return rows.map(projectDonation);
  },

  /** Expire stale invoices and release the units they were holding. */
  async expireStaleIntents(olderThanMs = 15 * 60_000): Promise<number> {
    const cutoff = new Date(Date.now() - olderThanMs);
    const stale = await prisma.donationTransaction.findMany({
      where: { status: 'AWAITING_PAYMENT', createdAt: { lt: cutoff } },
      select: { id: true, listingId: true },
      take: 200,
    });
    if (stale.length === 0) return 0;

    await prisma.$transaction(async (tx) => {
      await tx.donationTransaction.updateMany({
        where: { id: { in: stale.map((row) => row.id) } },
        data: { status: 'EXPIRED' },
      });
      for (const row of stale) {
        if (!row.listingId) continue;
        await tx.listing.updateMany({
          where: { id: row.listingId, soldCount: { gt: 0 }, supply: { not: null } },
          data: { soldCount: { decrement: 1 } },
        });
      }
    });
    return stale.length;
  },
};

type SettledTransaction = Prisma.DonationTransactionGetPayload<{
  include: {
    donor: { select: typeof publicUserSelect };
    receiver: { select: typeof publicUserSelect };
    stand: { select: { id: true; title: true; roomId: true } };
    gift: true;
  };
}>;

export function projectDonation(record: SettledTransaction): DonationEventPayload {
  return {
    id: record.id,
    tier: record.tier as DonationTier,
    method: record.method,
    roomId: record.roomId,
    standId: record.standId,
    standTitle: record.stand.title,
    donor: record.isAnonymous || !record.donor ? null : toPublicUser(record.donor),
    isAnonymous: record.isAnonymous,
    receiver: toPublicUser(record.receiver),
    amountStars: record.amountStars,
    valuationStars: record.valuationStars,
    gift: record.gift ? projectGift(record.gift) : null,
    message: record.message,
    createdAt: (record.settledAt ?? record.createdAt).toISOString(),
  };
}
