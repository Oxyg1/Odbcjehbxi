import { randomUUID } from 'node:crypto';
import type { Bot } from 'grammy';
import {
  MAX_STARS_AMOUNT,
  MIN_STARS_AMOUNT,
  type PaymentMethod,
} from '@tgdonate/shared';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { claimOnce } from '../lib/redis.js';
import { donationService } from '../services/donation.service.js';
import { listingService } from '../services/listing.service.js';
import { bot, type TgDonateContext } from './bot.js';

/**
 * Telegram Stars payments.
 *
 * Flow:
 *  1. The Mini App asks the API for an invoice link.
 *  2. We create an AWAITING_PAYMENT transaction whose id is the invoice payload.
 *  3. `createInvoiceLink` returns a link; the client opens it with
 *     `openInvoice` from the Telegram WebApp API.
 *  4. Telegram calls `pre_checkout_query` — we re-validate and answer within
 *     10 seconds, otherwise the payment is cancelled by Telegram.
 *  5. `successful_payment` arrives; we settle exactly once.
 *
 * Everything Stars-denominated uses the "XTR" currency with a single price
 * component, which is the only shape Telegram accepts for Stars.
 */

export type StarsPurposeKind = 'DONATION' | 'LISTING' | 'THEME';

export interface InvoicePayloadData {
  kind: StarsPurposeKind;
  transactionId?: string;
  themeId?: string;
  userId: string;
  nonce: string;
}

/**
 * The payload is echoed back to us by Telegram, so it must be compact
 * (Telegram caps it at 128 bytes) and must not be trusted blindly — every field
 * is re-validated against the database on arrival.
 */
export function encodeInvoicePayload(data: InvoicePayloadData): string {
  const parts = [
    data.kind,
    data.transactionId ?? '',
    data.themeId ?? '',
    data.userId,
    data.nonce,
  ];
  const encoded = parts.join('|');
  if (Buffer.byteLength(encoded, 'utf8') > 128) {
    throw new Error('Invoice payload exceeds the 128-byte Telegram limit');
  }
  return encoded;
}

export function decodeInvoicePayload(raw: string): InvoicePayloadData | null {
  const parts = raw.split('|');
  if (parts.length !== 5) return null;
  const [kind, transactionId, themeId, userId, nonce] = parts;
  if (kind !== 'DONATION' && kind !== 'LISTING' && kind !== 'THEME') return null;
  if (!userId || !nonce) return null;
  return {
    kind,
    transactionId: transactionId || undefined,
    themeId: themeId || undefined,
    userId,
    nonce,
  };
}

export class StarsInvoiceError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'StarsInvoiceError';
    this.code = code;
  }
}

export interface CreateDonationInvoiceInput {
  donorId: string;
  standId: string;
  listingId?: string | null;
  amountStars: number;
  isAnonymous?: boolean;
  message?: string | null;
  title: string;
  description: string;
}

export const starsPayments = {
  /**
   * Build a Stars invoice for a donation or a listing purchase and return the
   * link the Mini App should open.
   */
  async createDonationInvoice(input: CreateDonationInvoiceInput): Promise<{
    invoiceLink: string;
    transactionId: string;
  }> {
    assertStarsAmount(input.amountStars);

    // Reserve a unit of limited-supply stock *before* the invoice exists, so a
    // sold-out listing never produces a payable link.
    let reserved = false;
    if (input.listingId) {
      reserved = await listingService.tryReserve(input.listingId);
      if (!reserved) {
        throw new StarsInvoiceError('SOLD_OUT', 'This listing is no longer available');
      }
    }

    try {
      const method: PaymentMethod = 'TELEGRAM_STARS';
      const nonce = randomUUID().slice(0, 8);

      const transaction = await donationService.createIntent({
        donorId: input.donorId,
        standId: input.standId,
        listingId: input.listingId ?? null,
        method,
        amountStars: input.amountStars,
        isAnonymous: input.isAnonymous ?? false,
        message: input.message ?? null,
      });

      const payload = encodeInvoicePayload({
        kind: input.listingId ? 'LISTING' : 'DONATION',
        transactionId: transaction.id,
        userId: input.donorId,
        nonce,
      });

      await prisma.donationTransaction.update({
        where: { id: transaction.id },
        data: { invoicePayload: payload },
      });

      const invoiceLink = await bot.api.createInvoiceLink(
        truncate(input.title, 32),
        truncate(input.description, 255),
        payload,
        // Stars invoices take an empty provider token by protocol.
        '',
        'XTR',
        [{ label: truncate(input.title, 32), amount: input.amountStars }],
      );

      return { invoiceLink, transactionId: transaction.id };
    } catch (error) {
      // Give the reserved unit back; otherwise a failed invoice permanently
      // shrinks the listing's supply.
      if (reserved && input.listingId) {
        await listingService.releaseReservation(input.listingId).catch(() => undefined);
      }
      throw error;
    }
  },

  /** Build a Stars invoice that unlocks a premium stand theme. */
  async createThemeInvoice(input: { userId: string; themeId: string }): Promise<{
    invoiceLink: string;
  }> {
    const theme = await prisma.standTheme.findUnique({ where: { id: input.themeId } });
    if (!theme || !theme.isActive) {
      throw new StarsInvoiceError('THEME_NOT_FOUND', 'Theme not found');
    }
    if (theme.priceStars <= 0) {
      throw new StarsInvoiceError('THEME_FREE', 'This theme is already free');
    }

    const owned = await prisma.userTheme.findUnique({
      where: { userId_themeId: { userId: input.userId, themeId: input.themeId } },
    });
    if (owned) throw new StarsInvoiceError('ALREADY_OWNED', 'You already own this theme');

    const payload = encodeInvoicePayload({
      kind: 'THEME',
      themeId: theme.id,
      userId: input.userId,
      nonce: randomUUID().slice(0, 8),
    });

    const invoiceLink = await bot.api.createInvoiceLink(
      truncate(theme.name, 32),
      truncate(theme.description || `Unlock the ${theme.name} stand theme`, 255),
      payload,
      '',
      'XTR',
      [{ label: truncate(theme.name, 32), amount: theme.priceStars }],
    );
    return { invoiceLink };
  },

  /**
   * Refund a Stars charge. Telegram exposes this as `refundStarPayment`, keyed
   * on the payer's user id and the original charge id.
   */
  async refund(transactionId: string): Promise<void> {
    const transaction = await prisma.donationTransaction.findUnique({
      where: { id: transactionId },
      include: { donor: { select: { telegramId: true } } },
    });
    if (!transaction) throw new StarsInvoiceError('TX_NOT_FOUND', 'Transaction not found');
    if (!transaction.telegramChargeId || !transaction.donor) {
      throw new StarsInvoiceError('NOT_REFUNDABLE', 'Transaction has no Stars charge to refund');
    }
    if (transaction.status === 'REFUNDED') return;

    await bot.api.refundStarPayment(
      Number(transaction.donor.telegramId),
      transaction.telegramChargeId,
    );
    await donationService.markStatus(transactionId, 'REFUNDED');
  },
};

/* --------------------------- update handlers ---------------------------- */

export function registerPaymentHandlers(instance: Bot<TgDonateContext>): void {
  /**
   * Telegram gives us ~10 seconds to answer. Anything slower and the user sees
   * a failed payment, so the checks here are deliberately cheap: existence,
   * amount match, and terminal-state guard.
   */
  instance.on('pre_checkout_query', async (ctx) => {
    const query = ctx.preCheckoutQuery;
    const decoded = decodeInvoicePayload(query.invoice_payload);

    if (!decoded) {
      await ctx.answerPreCheckoutQuery(false, 'This invoice is no longer valid.');
      return;
    }

    try {
      if (decoded.kind === 'THEME') {
        const theme = decoded.themeId
          ? await prisma.standTheme.findUnique({ where: { id: decoded.themeId } })
          : null;
        if (!theme || !theme.isActive || theme.priceStars !== query.total_amount) {
          await ctx.answerPreCheckoutQuery(false, 'This theme is no longer available.');
          return;
        }
        await ctx.answerPreCheckoutQuery(true);
        return;
      }

      const transaction = decoded.transactionId
        ? await prisma.donationTransaction.findUnique({
            where: { id: decoded.transactionId },
            include: { listing: { select: { status: true } } },
          })
        : null;

      if (!transaction) {
        await ctx.answerPreCheckoutQuery(false, 'This invoice has expired.');
        return;
      }
      if (transaction.status === 'SETTLED') {
        await ctx.answerPreCheckoutQuery(false, 'This invoice was already paid.');
        return;
      }
      if (transaction.status === 'EXPIRED' || transaction.status === 'REFUNDED') {
        await ctx.answerPreCheckoutQuery(false, 'This invoice is no longer valid.');
        return;
      }
      // The amount Telegram is about to charge must match what we recorded.
      if (transaction.amountStars !== query.total_amount) {
        logger.warn(
          { transactionId: transaction.id, expected: transaction.amountStars, got: query.total_amount },
          'pre_checkout amount mismatch',
        );
        await ctx.answerPreCheckoutQuery(false, 'Price changed, please try again.');
        return;
      }
      if (transaction.listing && transaction.listing.status === 'SOLD') {
        await ctx.answerPreCheckoutQuery(false, 'This item just sold out.');
        return;
      }

      await ctx.answerPreCheckoutQuery(true);
    } catch (error) {
      logger.error({ err: error }, 'pre_checkout_query handler failed');
      // Failing closed is correct here: better a retryable error than a charge
      // we cannot account for.
      await ctx
        .answerPreCheckoutQuery(false, 'Something went wrong, please try again.')
        .catch(() => undefined);
    }
  });

  instance.on('message:successful_payment', async (ctx) => {
    const payment = ctx.message.successful_payment;
    const decoded = decodeInvoicePayload(payment.invoice_payload);
    if (!decoded) {
      logger.error({ payload: payment.invoice_payload }, 'successful_payment with unknown payload');
      return;
    }

    // Telegram retries webhook deliveries. The charge id is globally unique, so
    // it is the natural idempotency key.
    const chargeId = payment.telegram_payment_charge_id;
    const isFirstDelivery = await claimOnce(`stars:${chargeId}`, 7 * 86_400);
    if (!isFirstDelivery) {
      logger.debug({ chargeId }, 'duplicate successful_payment delivery ignored');
      return;
    }

    await prisma.processedEvent
      .create({ data: { source: 'telegram_stars', externalId: chargeId } })
      .catch(() => undefined);

    try {
      if (decoded.kind === 'THEME') {
        await settleThemePurchase(decoded, chargeId, payment.total_amount);
        await ctx.reply('🎨 Theme unlocked! Open your stand editor to apply it.');
        return;
      }

      if (!decoded.transactionId) {
        logger.error({ decoded }, 'donation payment without a transaction id');
        return;
      }

      const donation = await donationService.settle(decoded.transactionId, {
        telegramChargeId: chargeId,
      });

      if (donation) {
        const suffix =
          donation.tier === 'WHALE'
            ? '\n\n🐋 Your donation was broadcast to every room.'
            : '';
        await ctx.reply(
          `✅ Sent ${donation.amountStars} ⭐ to ${donation.receiver.displayName}.${suffix}`,
        );
      }
    } catch (error) {
      logger.error({ err: error, chargeId }, 'failed to settle a successful payment');
      // The money has already moved; surface it rather than failing silently.
      await ctx
        .reply('We received your payment but hit an error crediting it. Support has been notified.')
        .catch(() => undefined);
    }
  });
}

async function settleThemePurchase(
  decoded: InvoicePayloadData,
  chargeId: string,
  amountPaid: number,
): Promise<void> {
  if (!decoded.themeId) throw new Error('Theme payment without a theme id');

  const theme = await prisma.standTheme.findUnique({ where: { id: decoded.themeId } });
  if (!theme) throw new Error(`Theme ${decoded.themeId} vanished before settlement`);
  if (theme.priceStars !== amountPaid) {
    logger.warn({ themeId: theme.id, amountPaid }, 'theme price mismatch at settlement');
  }

  // Unique on (userId, themeId): a replayed delivery that slipped past the
  // idempotency claim still cannot grant the theme twice.
  await prisma.userTheme
    .create({
      data: { userId: decoded.userId, themeId: decoded.themeId, transactionId: chargeId },
    })
    .catch((error: unknown) => {
      if (isUniqueViolation(error)) return;
      throw error;
    });
}

function isUniqueViolation(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { code?: string }).code === 'P2002'
  );
}

function assertStarsAmount(amount: number): void {
  if (!Number.isInteger(amount) || amount < MIN_STARS_AMOUNT || amount > MAX_STARS_AMOUNT) {
    throw new StarsInvoiceError(
      'INVALID_AMOUNT',
      `Amount must be an integer between ${MIN_STARS_AMOUNT} and ${MAX_STARS_AMOUNT} Stars`,
    );
  }
}

function truncate(value: string, max: number): string {
  const trimmed = value.trim();
  return trimmed.length <= max ? trimmed : `${trimmed.slice(0, max - 1)}…`;
}
