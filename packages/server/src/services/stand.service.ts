import type { Prisma } from '@prisma/client';
import {
  MAX_LISTINGS_PER_STAND,
  ROOM_CAPACITY,
  type BannerStyle,
  type GiftAttribute,
  type GiftRef,
  type Listing,
  type Stand,
  type StandTheme,
  type ThemePalette,
} from '@tgdonate/shared';
import { prisma } from '../lib/prisma.js';
import { withLock } from '../lib/redis.js';
import { publicUserSelect, toPublicUser } from './user.service.js';

/** Everything the stand projection needs, in one query shape. */
const standInclude = {
  owner: { select: publicUserSelect },
  theme: true,
  listings: {
    where: { status: { in: ['ACTIVE', 'RESERVED'] } },
    orderBy: { position: 'asc' },
    include: { gift: true },
  },
} satisfies Prisma.StandInclude;

type StandRecord = Prisma.StandGetPayload<{ include: typeof standInclude }>;

export class StandNotFoundError extends Error {
  constructor(id: string) {
    super(`Stand ${id} not found`);
    this.name = 'StandNotFoundError';
  }
}

export class ListingLimitError extends Error {
  constructor() {
    super(`A stand may hold at most ${MAX_LISTINGS_PER_STAND} active listings`);
    this.name = 'ListingLimitError';
  }
}

export class RoomFullError extends Error {
  constructor(roomId: string) {
    super(`Room ${roomId} is at capacity`);
    this.name = 'RoomFullError';
  }
}

export class ForbiddenError extends Error {
  constructor(message = 'You do not own this resource') {
    super(message);
    this.name = 'ForbiddenError';
  }
}

export interface UpdateStandInput {
  title?: string;
  goal?: string | null;
  goalTargetStars?: number | null;
  themeId?: string;
  bannerStyle?: BannerStyle;
  roomId?: string | null;
  isPublished?: boolean;
}

export const standService = {
  /**
   * Every user has exactly one stand. It is created lazily on first open so
   * onboarding costs no extra taps.
   */
  async getOrCreateForUser(userId: string): Promise<Stand> {
    const existing = await prisma.stand.findUnique({
      where: { ownerId: userId },
      include: standInclude,
    });
    if (existing) return projectStand(existing);

    const defaultTheme = await prisma.standTheme.findFirst({
      where: { rarity: 'FREE', isActive: true },
      orderBy: { createdAt: 'asc' },
    });
    if (!defaultTheme) {
      throw new Error('No free stand theme is seeded; run `npm run db:seed`');
    }

    const created = await prisma.stand.create({
      data: {
        ownerId: userId,
        themeId: defaultTheme.id,
        title: 'My Stand',
        goal: null,
      },
      include: standInclude,
    });
    return projectStand(created);
  },

  async getById(standId: string): Promise<Stand> {
    const record = await prisma.stand.findUnique({
      where: { id: standId },
      include: standInclude,
    });
    if (!record) throw new StandNotFoundError(standId);
    return projectStand(record);
  },

  async getByIdOrNull(standId: string): Promise<Stand | null> {
    const record = await prisma.stand.findUnique({
      where: { id: standId },
      include: standInclude,
    });
    return record ? projectStand(record) : null;
  },

  async listForRoom(roomId: string, limit = ROOM_CAPACITY): Promise<Stand[]> {
    const records = await prisma.stand.findMany({
      where: { roomId, isPublished: true },
      include: standInclude,
      orderBy: [{ totalStarsReceived: 'desc' }, { updatedAt: 'desc' }],
      take: limit,
    });
    return records.map((record) => projectStand(record));
  },

  /**
   * Update a stand the caller owns. Room moves take the room lock so occupancy
   * cannot exceed capacity under concurrent joins.
   */
  async update(userId: string, input: UpdateStandInput): Promise<Stand> {
    const current = await prisma.stand.findUnique({ where: { ownerId: userId } });
    if (!current) throw new StandNotFoundError(userId);

    const data: Prisma.StandUpdateInput = { version: { increment: 1 } };

    if (input.title !== undefined) data.title = input.title.trim().slice(0, 64);
    if (input.goal !== undefined) data.goal = input.goal?.trim().slice(0, 140) || null;
    if (input.goalTargetStars !== undefined) {
      data.goalTargetStars =
        input.goalTargetStars === null ? null : Math.max(1, Math.floor(input.goalTargetStars));
    }
    if (input.bannerStyle !== undefined) data.bannerStyle = input.bannerStyle;
    if (input.isPublished !== undefined) data.isPublished = input.isPublished;

    if (input.themeId !== undefined) {
      await assertThemeUnlocked(userId, input.themeId);
      data.theme = { connect: { id: input.themeId } };
    }

    if (input.roomId === undefined) {
      const updated = await prisma.stand.update({
        where: { ownerId: userId },
        data,
        include: standInclude,
      });
      return projectStand(updated);
    }

    if (input.roomId === null) {
      const updated = await prisma.stand.update({
        where: { ownerId: userId },
        data: { ...data, room: { disconnect: true } },
        include: standInclude,
      });
      return projectStand(updated);
    }

    const targetRoomId = input.roomId;
    return withLock(`room:${targetRoomId}:occupancy`, async () => {
      const room = await prisma.room.findUnique({ where: { id: targetRoomId } });
      if (!room) throw new StandNotFoundError(targetRoomId);

      // Re-count inside the lock: a check outside it would be a TOCTOU race.
      const occupancy = await prisma.stand.count({
        where: { roomId: targetRoomId, isPublished: true, ownerId: { not: userId } },
      });
      if (occupancy >= room.capacity) throw new RoomFullError(targetRoomId);

      const updated = await prisma.stand.update({
        where: { ownerId: userId },
        data: { ...data, room: { connect: { id: targetRoomId } } },
        include: standInclude,
      });
      return projectStand(updated);
    });
  },

  /** Reorder listings in one transaction so the UI never sees a half-applied order. */
  async reorderListings(userId: string, orderedIds: string[]): Promise<Stand> {
    const stand = await prisma.stand.findUnique({
      where: { ownerId: userId },
      select: { id: true },
    });
    if (!stand) throw new StandNotFoundError(userId);

    const owned = await prisma.listing.findMany({
      where: { standId: stand.id, id: { in: orderedIds } },
      select: { id: true },
    });
    if (owned.length !== orderedIds.length) {
      throw new ForbiddenError('Listing order references unknown listings');
    }

    await prisma.$transaction(
      orderedIds.map((id, index) =>
        prisma.listing.update({ where: { id }, data: { position: index } }),
      ),
    );
    return this.getById(stand.id);
  },

  async assertOwnership(userId: string, standId: string): Promise<void> {
    const stand = await prisma.stand.findUnique({
      where: { id: standId },
      select: { ownerId: true },
    });
    if (!stand) throw new StandNotFoundError(standId);
    if (stand.ownerId !== userId) throw new ForbiddenError();
  },

  /** Top stands by lifetime Stars, used for the discovery rail. */
  async trending(limit = 12): Promise<Stand[]> {
    const records = await prisma.stand.findMany({
      where: { isPublished: true },
      include: standInclude,
      orderBy: { totalStarsReceived: 'desc' },
      take: limit,
    });
    return records.map((record) => projectStand(record));
  },
};

async function assertThemeUnlocked(userId: string, themeId: string): Promise<void> {
  const theme = await prisma.standTheme.findUnique({ where: { id: themeId } });
  if (!theme || !theme.isActive) throw new StandNotFoundError(themeId);
  if (theme.priceStars === 0) return;

  const owned = await prisma.userTheme.findUnique({
    where: { userId_themeId: { userId, themeId } },
  });
  if (!owned) throw new ForbiddenError('Theme is not unlocked for this account');
}

/* --------------------------- projections ------------------------------- */

export function projectStand(record: StandRecord, isOwnerOnline = false): Stand {
  return {
    id: record.id,
    ownerId: record.ownerId,
    owner: toPublicUser(record.owner),
    roomId: record.roomId,
    title: record.title,
    goal: record.goal,
    goalTargetStars: record.goalTargetStars,
    theme: projectTheme(record.theme),
    bannerStyle: record.bannerStyle as BannerStyle,
    listings: record.listings.map(projectListing),
    totalStarsReceived: record.totalStarsReceived,
    totalGiftsReceived: record.totalGiftsReceived,
    supporterCount: record.supporterCount,
    isOwnerOnline,
    isPublished: record.isPublished,
    updatedAt: record.updatedAt.toISOString(),
  };
}

export function projectTheme(
  record: Prisma.StandThemeGetPayload<Record<string, never>>,
): StandTheme {
  return {
    id: record.id,
    slug: record.slug,
    name: record.name,
    description: record.description,
    rarity: record.rarity,
    priceStars: record.priceStars,
    palette: record.palette as unknown as ThemePalette,
    effect: record.effect,
  };
}

type ListingRecord = StandRecord['listings'][number];

export function projectListing(record: ListingRecord): Listing {
  return {
    id: record.id,
    standId: record.standId,
    kind: record.kind,
    status: record.status,
    title: record.title,
    description: record.description,
    priceStars: record.priceStars,
    priceNanoton: record.priceNanoton ? record.priceNanoton.toFixed(0) : null,
    position: record.position,
    gift: record.gift ? projectGift(record.gift) : null,
    soldCount: record.soldCount,
    supply: record.supply,
    createdAt: record.createdAt.toISOString(),
  };
}

export function projectGift(record: NonNullable<ListingRecord['gift']>): GiftRef {
  return {
    telegramGiftId: record.telegramGiftId,
    slug: record.slug,
    title: record.title,
    rarity: record.rarity,
    previewUrl: record.previewUrl,
    attributes: (record.attributes as unknown as GiftAttribute[]) ?? [],
  };
}

export { standInclude };
export type { StandRecord };
