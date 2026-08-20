import {
  BPS_DENOMINATOR,
  GIFT_RARITY_STAR_EQUIVALENT,
  PLATFORM_FEE_BPS,
  VFX_TIER_THRESHOLDS,
} from './constants.js';
import type { DonationTier, GiftRarity } from './types.js';

/**
 * Fee split for a Stars payment. All arithmetic is integer-only — Telegram
 * Stars are indivisible, so rounding must never mint or burn a fraction.
 */
export interface FeeSplit {
  /** What the payer was charged. */
  gross: number;
  /** What the platform keeps. */
  fee: number;
  /** What the receiver is credited. */
  net: number;
  feeBps: number;
}

export function splitStars(gross: number, feeBps: number = PLATFORM_FEE_BPS): FeeSplit {
  if (!Number.isInteger(gross) || gross < 0) {
    throw new RangeError(`gross must be a non-negative integer, received ${gross}`);
  }
  if (!Number.isInteger(feeBps) || feeBps < 0 || feeBps > BPS_DENOMINATOR) {
    throw new RangeError(`feeBps must be within [0, ${BPS_DENOMINATOR}], received ${feeBps}`);
  }
  // Floor the fee so the receiver never loses a Star to rounding.
  const fee = Math.floor((gross * feeBps) / BPS_DENOMINATOR);
  return { gross, fee, net: gross - fee, feeBps };
}

/** Star-equivalent valuation of a gift, used purely for VFX tiering. */
export function valueOfGift(rarity: GiftRarity): number {
  return GIFT_RARITY_STAR_EQUIVALENT[rarity];
}

/**
 * Resolve the VFX tier for a donation.
 *
 * A legendary gift is always a whale event: its floor price is volatile but its
 * social signal is not.
 */
export function resolveTier(input: {
  amountStars: number;
  giftRarity?: GiftRarity | null;
}): { tier: DonationTier; valuationStars: number } {
  const giftValue = input.giftRarity ? valueOfGift(input.giftRarity) : 0;
  const valuationStars = Math.max(input.amountStars, giftValue, 1);

  if (input.giftRarity === 'LEGENDARY') {
    return { tier: 'WHALE', valuationStars };
  }
  if (valuationStars >= VFX_TIER_THRESHOLDS.whale.min) {
    return { tier: 'WHALE', valuationStars };
  }
  if (valuationStars >= VFX_TIER_THRESHOLDS.major.min) {
    return { tier: 'MAJOR', valuationStars };
  }
  return { tier: 'MICRO', valuationStars };
}

/** Nanoton <-> TON helpers. Nanotons are handled as bigint to stay exact. */
export const NANOTON_PER_TON = 1_000_000_000n;

export function tonToNano(ton: string | number): bigint {
  const asString = typeof ton === 'number' ? ton.toString() : ton.trim();
  if (!/^\d+(\.\d{1,9})?$/.test(asString)) {
    throw new RangeError(`Invalid TON amount: ${asString}`);
  }
  const [whole = '0', fraction = ''] = asString.split('.');
  const padded = fraction.padEnd(9, '0');
  return BigInt(whole) * NANOTON_PER_TON + BigInt(padded || '0');
}

export function nanoToTon(nano: bigint | string, decimals = 2): string {
  const value = typeof nano === 'bigint' ? nano : BigInt(nano);
  const whole = value / NANOTON_PER_TON;
  const fraction = (value % NANOTON_PER_TON).toString().padStart(9, '0');
  const trimmed = fraction.slice(0, decimals);
  return decimals > 0 ? `${whole}.${trimmed}` : whole.toString();
}

/** Compact display formatting: 1240 -> "1.2K", 2_400_000 -> "2.4M". */
export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return '0';
  const abs = Math.abs(value);
  if (abs < 1_000) return value.toString();
  if (abs < 1_000_000) return `${trimZero(value / 1_000)}K`;
  if (abs < 1_000_000_000) return `${trimZero(value / 1_000_000)}M`;
  return `${trimZero(value / 1_000_000_000)}B`;
}

function trimZero(value: number): string {
  const fixed = value.toFixed(1);
  return fixed.endsWith('.0') ? fixed.slice(0, -2) : fixed;
}

/** Leaderboard bucket keys. Daily/weekly buckets are computed in UTC. */
export function dailyBucket(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function weeklyBucket(now: Date = new Date()): string {
  // ISO-8601 week number, Monday-based.
  const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dayNumber = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNumber);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
  return `${date.getUTCFullYear()}-W${week.toString().padStart(2, '0')}`;
}
