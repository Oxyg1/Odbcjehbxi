import {
  MAX_LISTINGS_PER_STAND,
  MAX_STARS_AMOUNT,
  MIN_STARS_AMOUNT,
  type Listing,
  type ListingKind,
} from '@tgdonate/shared';
import { prisma } from '../lib/prisma.js';
import { withLock } from '../lib/redis.js';
import {
  ForbiddenError,
  ListingLimitError,
  StandNotFoundError,
  projectListing,
} from './stand.service.js';

export interface CreateListingInput {
  kind: ListingKind;
  title: string;
  description?: string | null;
  priceStars?: number | null;
  priceNanoton?: string | null;
  supply?: number | null;
  /** Required for NFT_GIFT_SALE: the gift the caller is putting up. */
  giftId?: string | null;
}

export class ListingValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ListingValidationError';
  }
}

export class GiftUnavailableError extends Error {
  constructor(giftId: string) {
    super(`Gift ${giftId} is not available for listing`);
    this.name = 'GiftUnavailableError';
  }
}

export const listingService = {
  async create(userId: string, input: CreateListingInput): Promise<Listing> {
    const stand = await prisma.stand.findUnique({
      where: { ownerId: userId },
      select: { id: true },
    });
    if (!stand) throw new StandNotFoundError(userId);

    validateListingInput(input);

    // The whole create is serialised per stand: two rapid taps must not push
    // the stand past its listing cap, and a gift must not land on two stands.
    return withLock(`stand:${stand.id}:listings`, async () => {
      const activeCount = await prisma.listing.count({
        where: { standId: stand.id, status: { in: ['ACTIVE', 'RESERVED'] } },
      });
      if (activeCount >= MAX_LISTINGS_PER_STAND) throw new ListingLimitError();

      if (input.kind === 'NFT_GIFT_SALE') {
        if (!input.giftId) {
          throw new ListingValidationError('An NFT gift listing requires a giftId');
        }
        const gift = await prisma.gift.findUnique({
          where: { id: input.giftId },
          include: { listing: { select: { id: true, status: true } } },
        });
        if (!gift || gift.ownerId !== userId) throw new ForbiddenError('You do not own this gift');
        if (gift.state !== 'HELD_BY_OWNER') throw new GiftUnavailableError(input.giftId);
        if (gift.listing && gift.listing.status !== 'SOLD') {
          throw new GiftUnavailableError(input.giftId);
        }
      }

      const created = await prisma.listing.create({
        data: {
          standId: stand.id,
          kind: input.kind,
          title: input.title.trim().slice(0, 80),
          description: input.description?.trim().slice(0, 280) || null,
          priceStars: input.priceStars ?? null,
          priceNanoton: input.priceNanoton ?? null,
          supply: input.supply ?? null,
          giftId: input.kind === 'NFT_GIFT_SALE' ? input.giftId ?? null : null,
          position: activeCount,
        },
        include: { gift: true },
      });
      return projectListing(created);
    });
  },

  async update(
    userId: string,
    listingId: string,
    patch: Partial<Omit<CreateListingInput, 'kind' | 'giftId'>> & { status?: 'ACTIVE' | 'HIDDEN' },
  ): Promise<Listing> {
    const listing = await loadOwnedListing(userId, listingId);

    if (patch.priceStars !== undefined && patch.priceStars !== null) {
      assertStarsRange(patch.priceStars);
    }
    if (patch.priceNanoton !== undefined && patch.priceNanoton !== null) {
      assertNanotonString(patch.priceNanoton);
    }

    const updated = await prisma.listing.update({
      where: { id: listing.id },
      data: {
        ...(patch.title !== undefined ? { title: patch.title.trim().slice(0, 80) } : {}),
        ...(patch.description !== undefined
          ? { description: patch.description?.trim().slice(0, 280) || null }
          : {}),
        ...(patch.priceStars !== undefined ? { priceStars: patch.priceStars } : {}),
        ...(patch.priceNanoton !== undefined ? { priceNanoton: patch.priceNanoton } : {}),
        ...(patch.supply !== undefined ? { supply: patch.supply } : {}),
        ...(patch.status !== undefined ? { status: patch.status } : {}),
      },
      include: { gift: true },
    });
    return projectListing(updated);
  },

  async remove(userId: string, listingId: string): Promise<void> {
    const listing = await loadOwnedListing(userId, listingId);

    // Never hard-delete a listing that has settled transactions pointing at it:
    // the donation history must stay readable. Hide it instead.
    const transactionCount = await prisma.donationTransaction.count({
      where: { listingId: listing.id },
    });
    if (transactionCount > 0) {
      await prisma.listing.update({ where: { id: listing.id }, data: { status: 'HIDDEN' } });
      return;
    }
    await prisma.listing.delete({ where: { id: listing.id } });
  },

  async getById(listingId: string): Promise<Listing | null> {
    const record = await prisma.listing.findUnique({
      where: { id: listingId },
      include: { gift: true },
    });
    return record ? projectListing(record) : null;
  },

  /**
   * Atomically reserve one unit of a limited-supply listing. Returns false when
   * the listing just sold out — the caller must not create an invoice then.
   */
  async tryReserve(listingId: string): Promise<boolean> {
    const listing = await prisma.listing.findUnique({
      where: { id: listingId },
      select: { supply: true, soldCount: true, status: true, kind: true },
    });
    if (!listing || listing.status !== 'ACTIVE') return false;
    if (listing.supply === null) return true;

    // Conditional update: the WHERE clause is the guard, so two concurrent
    // reservations cannot both observe the last unit as free.
    const result = await prisma.listing.updateMany({
      where: { id: listingId, status: 'ACTIVE', soldCount: { lt: listing.supply } },
      data: { soldCount: { increment: 1 } },
    });
    return result.count === 1;
  },

  /** Compensating action when an invoice expires or payment fails. */
  async releaseReservation(listingId: string): Promise<void> {
    await prisma.listing.updateMany({
      where: { id: listingId, soldCount: { gt: 0 } },
      data: { soldCount: { decrement: 1 } },
    });
  },
};

async function loadOwnedListing(userId: string, listingId: string) {
  const listing = await prisma.listing.findUnique({
    where: { id: listingId },
    include: { stand: { select: { ownerId: true } } },
  });
  if (!listing) throw new StandNotFoundError(listingId);
  if (listing.stand.ownerId !== userId) throw new ForbiddenError();
  return listing;
}

function validateListingInput(input: CreateListingInput): void {
  if (!input.title.trim()) {
    throw new ListingValidationError('Listing title is required');
  }

  switch (input.kind) {
    case 'DONATION_TIER': {
      if (input.priceStars === null || input.priceStars === undefined) {
        throw new ListingValidationError('A donation tier requires a Stars price');
      }
      assertStarsRange(input.priceStars);
      break;
    }
    case 'SERVICE_OFFER': {
      const hasStars = input.priceStars !== null && input.priceStars !== undefined;
      const hasTon = input.priceNanoton !== null && input.priceNanoton !== undefined;
      if (!hasStars && !hasTon) {
        throw new ListingValidationError('A service offer needs a Stars or TON price');
      }
      if (hasStars) assertStarsRange(input.priceStars as number);
      if (hasTon) assertNanotonString(input.priceNanoton as string);
      break;
    }
    case 'NFT_GIFT_SALE': {
      const hasStars = input.priceStars !== null && input.priceStars !== undefined;
      const hasTon = input.priceNanoton !== null && input.priceNanoton !== undefined;
      if (!hasStars && !hasTon) {
        throw new ListingValidationError('A gift sale needs a Stars or TON price');
      }
      if (hasStars) assertStarsRange(input.priceStars as number);
      if (hasTon) assertNanotonString(input.priceNanoton as string);
      break;
    }
  }
}

function assertStarsRange(value: number): void {
  if (!Number.isInteger(value) || value < MIN_STARS_AMOUNT || value > MAX_STARS_AMOUNT) {
    throw new ListingValidationError(
      `Stars price must be an integer between ${MIN_STARS_AMOUNT} and ${MAX_STARS_AMOUNT}`,
    );
  }
}

function assertNanotonString(value: string): void {
  if (!/^\d{1,38}$/.test(value)) {
    throw new ListingValidationError('TON price must be an integer nanoton string');
  }
  if (BigInt(value) <= 0n) {
    throw new ListingValidationError('TON price must be greater than zero');
  }
}
