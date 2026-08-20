import type { Prisma, User } from '@prisma/client';
import type { LeaderboardScope, PublicUser, WhaleBadge } from '@tgdonate/shared';
import { prisma, toNumberId } from '../lib/prisma.js';
import type { TelegramUser } from '../telegram/init-data.js';

export type AuthenticatedUser = User;

/** Badge cache, refreshed by the leaderboard service on each recompute. */
const badgeCache = new Map<string, WhaleBadge>();

export const userService = {
  /**
   * Idempotent upsert keyed on the Telegram id. Profile fields are refreshed on
   * every launch because usernames and avatars change often; local state
   * (counters, wallet, ban flag) is never touched here.
   */
  async upsertFromTelegram(telegramUser: TelegramUser): Promise<User> {
    const displayName = buildDisplayName(telegramUser);
    return prisma.user.upsert({
      where: { telegramId: BigInt(telegramUser.id) },
      create: {
        telegramId: BigInt(telegramUser.id),
        username: telegramUser.username ?? null,
        displayName,
        photoUrl: telegramUser.photo_url ?? null,
        languageCode: telegramUser.language_code?.slice(0, 8) ?? null,
        isPremium: telegramUser.is_premium ?? false,
      },
      update: {
        username: telegramUser.username ?? null,
        displayName,
        photoUrl: telegramUser.photo_url ?? null,
        languageCode: telegramUser.language_code?.slice(0, 8) ?? null,
        isPremium: telegramUser.is_premium ?? false,
        lastSeenAt: new Date(),
      },
    });
  },

  async findByTelegramId(telegramId: number | bigint): Promise<User | null> {
    return prisma.user.findUnique({ where: { telegramId: BigInt(telegramId) } });
  },

  async findById(id: string): Promise<User | null> {
    return prisma.user.findUnique({ where: { id } });
  },

  /**
   * Bind a TON wallet after a verified TON Connect proof. The raw address is
   * unique across users: two accounts cannot claim the same wallet, which would
   * otherwise let someone hijack incoming escrow settlements.
   */
  async linkTonWallet(userId: string, rawAddress: string): Promise<User> {
    const existing = await prisma.user.findUnique({ where: { tonWalletRaw: rawAddress } });
    if (existing && existing.id !== userId) {
      throw new WalletAlreadyLinkedError(rawAddress);
    }
    return prisma.user.update({
      where: { id: userId },
      data: { tonWalletRaw: rawAddress, tonProofAt: new Date() },
    });
  },

  async unlinkTonWallet(userId: string): Promise<User> {
    return prisma.user.update({
      where: { id: userId },
      data: { tonWalletRaw: null, tonProofAt: null },
    });
  },

  async touchLastSeen(userId: string): Promise<void> {
    await prisma.user
      .update({ where: { id: userId }, data: { lastSeenAt: new Date() } })
      .catch(() => undefined);
  },

  /** Replace the in-memory badge index after a leaderboard recompute. */
  setBadges(entries: Array<{ userId: string; badge: WhaleBadge }>, scope: LeaderboardScope): void {
    for (const [userId, badge] of badgeCache) {
      if (badge.scope === scope) badgeCache.delete(userId);
    }
    for (const entry of entries) {
      const current = badgeCache.get(entry.userId);
      // Keep the most prestigious badge when a user ranks in several scopes.
      if (!current || badgeRank(entry.badge) < badgeRank(current)) {
        badgeCache.set(entry.userId, entry.badge);
      }
    }
  },

  getBadge(userId: string): WhaleBadge | null {
    return badgeCache.get(userId) ?? null;
  },
};

export class WalletAlreadyLinkedError extends Error {
  constructor(address: string) {
    super(`Wallet ${address} is already linked to another account`);
    this.name = 'WalletAlreadyLinkedError';
  }
}

function buildDisplayName(telegramUser: TelegramUser): string {
  const parts = [telegramUser.first_name, telegramUser.last_name].filter(Boolean);
  const joined = parts.join(' ').trim();
  const fallback = telegramUser.username ?? `User ${telegramUser.id}`;
  return (joined || fallback).slice(0, 64);
}

/** Lower is better: all-time #1 outranks a daily #1. */
function badgeRank(badge: WhaleBadge): number {
  const scopeWeight: Record<LeaderboardScope, number> = {
    ALL_TIME: 0,
    WEEKLY: 1_000,
    DAILY: 2_000,
  };
  return scopeWeight[badge.scope] + badge.rank;
}

/** Transport-safe projection. Never leaks wallet, ban state or counters. */
export function toPublicUser(user: Pick<
  User,
  'id' | 'telegramId' | 'username' | 'displayName' | 'photoUrl' | 'isPremium'
>): PublicUser {
  return {
    id: user.id,
    telegramId: toNumberId(user.telegramId),
    username: user.username,
    displayName: user.displayName,
    photoUrl: user.photoUrl,
    isPremium: user.isPremium,
    badge: userService.getBadge(user.id),
  };
}

export const publicUserSelect = {
  id: true,
  telegramId: true,
  username: true,
  displayName: true,
  photoUrl: true,
  isPremium: true,
} satisfies Prisma.UserSelect;
