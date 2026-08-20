import { z } from 'zod';
import { MAX_STARS_AMOUNT, MIN_STARS_AMOUNT } from '@tgdonate/shared';

/** Request schemas. Every mutating endpoint parses its body through one. */

export const StarsAmount = z
  .number()
  .int()
  .min(MIN_STARS_AMOUNT)
  .max(MAX_STARS_AMOUNT);

export const NanotonString = z
  .string()
  .regex(/^\d{1,38}$/, 'Must be an integer nanoton amount')
  .refine((value) => BigInt(value) > 0n, 'Must be greater than zero');

export const UpdateStandBody = z.object({
  title: z.string().min(1).max(64).optional(),
  goal: z.string().max(140).nullable().optional(),
  goalTargetStars: z.number().int().min(1).max(10_000_000).nullable().optional(),
  themeId: z.string().min(1).max(64).optional(),
  bannerStyle: z.enum(['SOLID', 'GRADIENT', 'HOLOGRAM', 'MARQUEE', 'PIXEL']).optional(),
  roomId: z.string().min(1).max(64).nullable().optional(),
  isPublished: z.boolean().optional(),
});

export const CreateListingBody = z
  .object({
    kind: z.enum(['DONATION_TIER', 'SERVICE_OFFER', 'NFT_GIFT_SALE']),
    title: z.string().min(1).max(80),
    description: z.string().max(280).nullable().optional(),
    priceStars: StarsAmount.nullable().optional(),
    priceNanoton: NanotonString.nullable().optional(),
    supply: z.number().int().min(1).max(10_000).nullable().optional(),
    giftId: z.string().min(1).max(64).nullable().optional(),
  })
  .refine(
    (value) => value.kind !== 'NFT_GIFT_SALE' || Boolean(value.giftId),
    { message: 'An NFT gift listing requires giftId', path: ['giftId'] },
  );

export const UpdateListingBody = z.object({
  title: z.string().min(1).max(80).optional(),
  description: z.string().max(280).nullable().optional(),
  priceStars: StarsAmount.nullable().optional(),
  priceNanoton: NanotonString.nullable().optional(),
  supply: z.number().int().min(1).max(10_000).nullable().optional(),
  status: z.enum(['ACTIVE', 'HIDDEN']).optional(),
});

export const ReorderListingsBody = z.object({
  order: z.array(z.string().min(1).max(64)).min(1).max(16),
});

export const CreateDonationInvoiceBody = z.object({
  standId: z.string().min(1).max(64),
  listingId: z.string().min(1).max(64).nullable().optional(),
  amountStars: StarsAmount,
  isAnonymous: z.boolean().optional(),
  message: z.string().max(280).nullable().optional(),
});

export const CreateThemeInvoiceBody = z.object({
  themeId: z.string().min(1).max(64),
});

export const CreateTonIntentBody = z.object({
  standId: z.string().min(1).max(64),
  listingId: z.string().min(1).max(64).nullable().optional(),
  amountNanoton: NanotonString,
  isAnonymous: z.boolean().optional(),
  message: z.string().max(280).nullable().optional(),
});

export const LinkWalletBody = z.object({
  address: z.string().min(10).max(96),
  publicKey: z.string().regex(/^[0-9a-fA-F]{64}$/, 'Must be a 32-byte hex public key'),
  proof: z.object({
    timestamp: z.number().int().positive(),
    domain: z.object({
      lengthBytes: z.number().int().positive(),
      value: z.string().min(1).max(255),
    }),
    signature: z.string().min(1).max(512),
    payload: z.string().min(1).max(255),
    stateInit: z.string().optional(),
  }),
});

export const LeaderboardQuery = z.object({
  scope: z.enum(['DAILY', 'WEEKLY', 'ALL_TIME']).default('DAILY'),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

export const PaginationQuery = z.object({
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

export const ReactionBody = z.object({
  standId: z.string().min(1).max(64),
  emoji: z.enum(['🔥', '💎', '⭐', '👑', '🫡']),
});
