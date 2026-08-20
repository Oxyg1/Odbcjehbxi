/**
 * Domain types shared between the realtime gateway, the REST API and the TMA.
 * These mirror the Prisma models but are transport-safe: no Decimal, no Date,
 * every timestamp is an ISO-8601 string and every bigint is a number.
 */

export type ListingKind = 'DONATION_TIER' | 'SERVICE_OFFER' | 'NFT_GIFT_SALE';

export type ListingStatus = 'ACTIVE' | 'RESERVED' | 'SOLD' | 'HIDDEN' | 'EXPIRED';

export type PaymentMethod = 'TELEGRAM_STARS' | 'TON' | 'NFT_GIFT';

export type TransactionStatus =
  | 'PENDING'
  | 'AWAITING_PAYMENT'
  | 'PAID'
  | 'SETTLED'
  | 'REFUNDED'
  | 'FAILED'
  | 'EXPIRED';

export type DonationTier = 'MICRO' | 'MAJOR' | 'WHALE';

export type GiftRarity = 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY';

export type ThemeRarity = 'FREE' | 'PREMIUM' | 'LEGENDARY';

export type LeaderboardScope = 'DAILY' | 'WEEKLY' | 'ALL_TIME';

/** Public, non-sensitive projection of a user. Safe to broadcast. */
export interface PublicUser {
  id: string;
  telegramId: number;
  username: string | null;
  displayName: string;
  photoUrl: string | null;
  /** Whale rank badge, or null when the user is not currently ranked. */
  badge: WhaleBadge | null;
  isPremium: boolean;
}

export interface WhaleBadge {
  scope: LeaderboardScope;
  rank: number;
  /** Total Stars donated within the badge's scope. */
  starsDonated: number;
}

export interface StandTheme {
  id: string;
  slug: string;
  name: string;
  description: string;
  rarity: ThemeRarity;
  /** Price in Telegram Stars. 0 for the default free themes. */
  priceStars: number;
  /** CSS gradient / color stops consumed by the stand card renderer. */
  palette: ThemePalette;
  /** Optional decorative preset (particles, scanlines, low-poly plinth...). */
  effect: ThemeEffect | null;
}

export interface ThemePalette {
  /** Card surface base color. */
  surface: string;
  /** Accent used for counters, ring glow and CTA. */
  accent: string;
  /** Secondary accent used for gradients. */
  accentSoft: string;
  /** Banner gradient, as a full CSS `background-image` value. */
  banner: string;
  /** Foreground text color on top of `surface`. */
  foreground: string;
}

export type ThemeEffect =
  | 'NONE'
  | 'LOW_POLY'
  | 'CYBERPUNK_GRID'
  | 'GOLD_ROYALTY'
  | 'CRT_SCANLINES'
  | 'AURORA';

export interface Listing {
  id: string;
  standId: string;
  kind: ListingKind;
  status: ListingStatus;
  title: string;
  description: string | null;
  /** Price in Telegram Stars. Null for TON-only or gift-only listings. */
  priceStars: number | null;
  /** Price in nanotons, serialized as a decimal string. Null when Stars-only. */
  priceNanoton: string | null;
  /** Ordering index inside the stand. */
  position: number;
  /** Populated for NFT_GIFT_SALE listings. */
  gift: GiftRef | null;
  /** How many times this listing has been purchased. */
  soldCount: number;
  /** Optional supply cap; null means unlimited. */
  supply: number | null;
  createdAt: string;
}

export interface GiftRef {
  /** Telegram's unique gift identifier. */
  telegramGiftId: string;
  slug: string;
  title: string;
  rarity: GiftRarity;
  /** Preview asset (TGS/webp/png) served by the CDN. */
  previewUrl: string | null;
  /** Model / backdrop / symbol attributes shown on the card. */
  attributes: GiftAttribute[];
}

export interface GiftAttribute {
  type: 'MODEL' | 'BACKDROP' | 'SYMBOL';
  name: string;
  /** Rarity permille, as returned by Telegram (e.g. 15 = 1.5%). */
  rarityPermille: number;
}

export interface Stand {
  id: string;
  ownerId: string;
  owner: PublicUser;
  roomId: string | null;
  title: string;
  /** The public goal, e.g. "Saving for a Rare Pepe gift". */
  goal: string | null;
  /** Target in Stars for the progress ring; null disables the ring. */
  goalTargetStars: number | null;
  theme: StandTheme;
  bannerStyle: BannerStyle;
  listings: Listing[];
  /** Lifetime Stars received. */
  totalStarsReceived: number;
  /** Lifetime gift count received. */
  totalGiftsReceived: number;
  /** Donor count, distinct. */
  supporterCount: number;
  /** Whether the owner is currently connected to the room. */
  isOwnerOnline: boolean;
  /** An unpublished stand is hidden from rooms and refuses new donations. */
  isPublished: boolean;
  updatedAt: string;
}

export type BannerStyle = 'SOLID' | 'GRADIENT' | 'HOLOGRAM' | 'MARQUEE' | 'PIXEL';

export interface Room {
  id: string;
  slug: string;
  name: string;
  description: string;
  /** Emoji shown in the room switcher. */
  emoji: string;
  accent: string;
  occupancy: number;
  capacity: number;
  /** Stars donated inside this room in the last 24h. Drives the "hot" flag. */
  volume24hStars: number;
}

export interface DonationEventPayload {
  id: string;
  tier: DonationTier;
  method: PaymentMethod;
  roomId: string | null;
  standId: string;
  standTitle: string;
  donor: PublicUser | null;
  /** Null when the donor chose to stay anonymous. */
  isAnonymous: boolean;
  receiver: PublicUser;
  /** Stars amount; 0 for pure gift donations. */
  amountStars: number;
  /** Star-equivalent used for tiering, always > 0. */
  valuationStars: number;
  gift: GiftRef | null;
  message: string | null;
  createdAt: string;
}

export interface LeaderboardRow {
  rank: number;
  user: PublicUser;
  starsDonated: number;
  giftsDonated: number;
}

export interface Leaderboard {
  scope: LeaderboardScope;
  /** Bucket key: `2026-08-20` for daily, `2026-W34` for weekly, `all` otherwise. */
  bucket: string;
  rows: LeaderboardRow[];
  /** The requesting user's own row, even when outside the top N. */
  viewer: LeaderboardRow | null;
  updatedAt: string;
}
