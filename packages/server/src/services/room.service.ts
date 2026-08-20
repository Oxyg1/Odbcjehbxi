import type { Room as RoomRecord } from '@prisma/client';
import { RedisKeys, ROOM_CAPACITY, type Room } from '@tgdonate/shared';
import { prisma } from '../lib/prisma.js';
import { redis } from '../lib/redis.js';

/** Room rows change rarely; a short in-process cache saves a query per join. */
const roomCache = new Map<string, { record: RoomRecord; expiresAt: number }>();
const ROOM_CACHE_TTL_MS = 30_000;

export const roomService = {
  async getById(roomId: string): Promise<RoomRecord | null> {
    const cached = roomCache.get(roomId);
    if (cached && cached.expiresAt > Date.now()) return cached.record;

    const record = await prisma.room.findUnique({ where: { id: roomId } });
    if (record) {
      roomCache.set(roomId, { record, expiresAt: Date.now() + ROOM_CACHE_TTL_MS });
    }
    return record;
  },

  async getBySlug(slug: string): Promise<RoomRecord | null> {
    return prisma.room.findUnique({ where: { slug } });
  },

  /** Live occupancy from the shared presence hash, so it spans gateway nodes. */
  async occupancy(roomId: string): Promise<number> {
    const count = await redis.hlen(RedisKeys.roomPresence(roomId)).catch(() => 0);
    return count;
  },

  async getPublicRoom(roomId: string): Promise<Room | null> {
    const record = await this.getById(roomId);
    if (!record) return null;
    const [occupancy, volume24hStars] = await Promise.all([
      this.occupancy(roomId),
      volumeLast24h(roomId),
    ]);
    return projectRoom(record, occupancy, volume24hStars);
  },

  /** Room switcher payload: every visible room with live occupancy + volume. */
  async listPublic(): Promise<Room[]> {
    const records = await prisma.room.findMany({
      where: { isHidden: false },
      orderBy: [{ sortOrder: 'asc' }, { createdAt: 'asc' }],
    });

    const [occupancies, volumes] = await Promise.all([
      Promise.all(records.map((record) => this.occupancy(record.id))),
      volumesLast24h(records.map((record) => record.id)),
    ]);

    return records.map((record, index) =>
      projectRoom(record, occupancies[index] ?? 0, volumes.get(record.id) ?? 0),
    );
  },

  /**
   * Pick the emptiest room with free space — used when a user publishes a stand
   * without choosing one explicitly.
   */
  async suggestRoom(): Promise<RoomRecord | null> {
    const rooms = await prisma.room.findMany({
      where: { isHidden: false },
      orderBy: { sortOrder: 'asc' },
    });
    if (rooms.length === 0) return null;

    let best: RoomRecord | null = null;
    let bestOccupancy = Number.POSITIVE_INFINITY;

    for (const room of rooms) {
      const occupancy = await prisma.stand.count({
        where: { roomId: room.id, isPublished: true },
      });
      if (occupancy < room.capacity && occupancy < bestOccupancy) {
        best = room;
        bestOccupancy = occupancy;
      }
    }
    return best ?? rooms[0] ?? null;
  },

  invalidate(roomId: string): void {
    roomCache.delete(roomId);
  },
};

function projectRoom(record: RoomRecord, occupancy: number, volume24hStars: number): Room {
  return {
    id: record.id,
    slug: record.slug,
    name: record.name,
    description: record.description,
    emoji: record.emoji,
    accent: record.accent,
    occupancy,
    capacity: record.capacity || ROOM_CAPACITY,
    volume24hStars,
  };
}

async function volumeLast24h(roomId: string): Promise<number> {
  const since = new Date(Date.now() - 86_400_000);
  const result = await prisma.donationTransaction.aggregate({
    where: { roomId, status: 'SETTLED', settledAt: { gte: since } },
    _sum: { amountStars: true },
  });
  return result._sum.amountStars ?? 0;
}

async function volumesLast24h(roomIds: string[]): Promise<Map<string, number>> {
  if (roomIds.length === 0) return new Map();
  const since = new Date(Date.now() - 86_400_000);
  const rows = await prisma.donationTransaction.groupBy({
    by: ['roomId'],
    where: { roomId: { in: roomIds }, status: 'SETTLED', settledAt: { gte: since } },
    _sum: { amountStars: true },
  });
  const map = new Map<string, number>();
  for (const row of rows) {
    if (row.roomId) map.set(row.roomId, row._sum.amountStars ?? 0);
  }
  return map;
}
