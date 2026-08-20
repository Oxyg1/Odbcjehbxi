import { randomUUID } from 'node:crypto';
import type { FastifyInstance } from 'fastify';
import { PLATFORM_FEE_BPS, splitStars } from '@tgdonate/shared';
import { env } from '../config/env.js';
import { prisma } from '../lib/prisma.js';
import { redis } from '../lib/redis.js';
import { getAuth, requireTelegramAuth } from '../middleware/auth.js';
import { donationService } from '../services/donation.service.js';
import { giftService } from '../services/gift.service.js';
import { listingService } from '../services/listing.service.js';
import { standService } from '../services/stand.service.js';
import { userService } from '../services/user.service.js';
import { starsPayments } from '../telegram/payments.js';
import { toRawAddress, verifyTonProof } from '../ton/client.js';
import { sendError } from './errors.js';
import {
  CreateDonationInvoiceBody,
  CreateThemeInvoiceBody,
  CreateTonIntentBody,
  LinkWalletBody,
} from './schemas.js';

const TON_PROOF_NONCE_TTL_SECONDS = 15 * 60;

export async function paymentRoutes(app: FastifyInstance): Promise<void> {
  /** Stars invoice for a donation or a listing purchase. */
  app.post(
    '/api/payments/stars/invoice',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const body = CreateDonationInvoiceBody.parse(request.body);

        const stand = await standService.getById(body.standId);

        // A listing's price is authoritative — never trust a client-sent amount
        // for a priced item, or the buyer sets their own price.
        let amountStars = body.amountStars;
        let title = `Support ${stand.title}`;
        let description = stand.goal ?? `Send Stars to ${stand.owner.displayName}`;

        if (body.listingId) {
          const listing = await listingService.getById(body.listingId);
          if (!listing || listing.standId !== stand.id) {
            return await reply
              .code(404)
              .send({ error: 'NOT_FOUND', message: 'Listing not found on this stand' });
          }
          if (listing.status !== 'ACTIVE') {
            return await reply
              .code(409)
              .send({ error: 'UNAVAILABLE', message: 'This listing is not available' });
          }
          if (listing.priceStars === null) {
            return await reply
              .code(409)
              .send({ error: 'NOT_STARS_PRICED', message: 'This listing is not priced in Stars' });
          }
          amountStars = listing.priceStars;
          title = listing.title;
          description = listing.description ?? `From ${stand.title}`;

          if (listing.kind === 'NFT_GIFT_SALE' && listing.gift) {
            const giftRecord = await prisma.gift.findUnique({
              where: { telegramGiftId: listing.gift.telegramGiftId },
              select: { id: true },
            });
            if (!giftRecord) {
              return await reply
                .code(409)
                .send({ error: 'GIFT_UNAVAILABLE', message: 'This gift is no longer available' });
            }
          }
        }

        const { invoiceLink, transactionId } = await starsPayments.createDonationInvoice({
          donorId: user.id,
          standId: stand.id,
          listingId: body.listingId ?? null,
          amountStars,
          isAnonymous: body.isAnonymous ?? false,
          message: body.message ?? null,
          title,
          description,
        });

        // Escrow the gift only once the invoice exists, so a failed invoice
        // never leaves an asset locked.
        if (body.listingId) {
          const listing = await listingService.getById(body.listingId);
          if (listing?.kind === 'NFT_GIFT_SALE' && listing.gift) {
            const giftRecord = await prisma.gift.findUnique({
              where: { telegramGiftId: listing.gift.telegramGiftId },
              select: { id: true },
            });
            if (giftRecord) {
              await giftService.lockForTransaction(giftRecord.id, transactionId);
              await prisma.donationTransaction.update({
                where: { id: transactionId },
                data: { giftId: giftRecord.id },
              });
            }
          }
        }

        const split = splitStars(amountStars, env.PLATFORM_FEE_BPS);
        return await reply.send({
          invoiceLink,
          transactionId,
          breakdown: split,
        });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  /** Stars invoice that unlocks a premium stand theme. */
  app.post(
    '/api/payments/stars/theme-invoice',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const body = CreateThemeInvoiceBody.parse(request.body);
        const result = await starsPayments.createThemeInvoice({
          userId: user.id,
          themeId: body.themeId,
        });
        return await reply.send(result);
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  /**
   * TON payment intent. Returns the escrow address and the comment the wallet
   * must attach; the watcher matches the on-chain comment back to this row.
   */
  app.post(
    '/api/payments/ton/intent',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const body = CreateTonIntentBody.parse(request.body);

        if (!env.TON_ESCROW_ADDRESS) {
          return await reply
            .code(503)
            .send({ error: 'TON_DISABLED', message: 'TON payments are not configured' });
        }

        const stand = await standService.getById(body.standId);

        let amountNanoton = body.amountNanoton;
        if (body.listingId) {
          const listing = await listingService.getById(body.listingId);
          if (!listing || listing.standId !== stand.id) {
            return await reply
              .code(404)
              .send({ error: 'NOT_FOUND', message: 'Listing not found on this stand' });
          }
          if (listing.priceNanoton === null) {
            return await reply
              .code(409)
              .send({ error: 'NOT_TON_PRICED', message: 'This listing is not priced in TON' });
          }
          amountNanoton = listing.priceNanoton;
        }

        const transaction = await donationService.createIntent({
          donorId: user.id,
          standId: stand.id,
          listingId: body.listingId ?? null,
          method: 'TON',
          amountStars: 0,
          amountNanoton,
          isAnonymous: body.isAnonymous ?? false,
          message: body.message ?? null,
        });

        return await reply.send({
          transactionId: transaction.id,
          escrowAddress: env.TON_ESCROW_ADDRESS,
          amountNanoton,
          // The wallet must send this verbatim or the payment cannot be matched.
          comment: `tgdonate:${transaction.id}`,
          validUntil: Math.floor(Date.now() / 1000) + 15 * 60,
        });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  /** Nonce for TON Connect's `ton_proof`. Single-use, short-lived. */
  app.post(
    '/api/wallet/ton-proof-payload',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const nonce = randomUUID().replace(/-/g, '');
        await redis.set(
          `tonproof:${user.id}`,
          nonce,
          'EX',
          TON_PROOF_NONCE_TTL_SECONDS,
        );
        return await reply.send({ payload: nonce });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  /** Bind a wallet after verifying its signature over our nonce. */
  app.post('/api/wallet/link', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const body = LinkWalletBody.parse(request.body);

      const expectedPayload = await redis.get(`tonproof:${user.id}`);
      if (!expectedPayload) {
        return await reply
          .code(400)
          .send({ error: 'PROOF_EXPIRED', message: 'Request a fresh proof payload' });
      }

      const rawAddress = toRawAddress(body.address);
      const allowedDomains = [
        ...env.corsOrigins.map(hostOf).filter((host): host is string => host !== null),
        hostOf(env.PUBLIC_WEBAPP_URL),
      ].filter((host): host is string => host !== null);

      const isValid = await verifyTonProof({
        rawAddress,
        proof: body.proof,
        expectedPayload,
        allowedDomains,
        publicKeyHex: body.publicKey,
      });
      if (!isValid) {
        return await reply
          .code(401)
          .send({ error: 'INVALID_PROOF', message: 'Wallet proof could not be verified' });
      }

      // Burn the nonce so the same proof cannot be replayed.
      await redis.del(`tonproof:${user.id}`);
      const updated = await userService.linkTonWallet(user.id, rawAddress);

      return await reply.send({ walletRaw: updated.tonWalletRaw });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.delete('/api/wallet/link', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      await userService.unlinkTonWallet(user.id);
      return await reply.code(204).send();
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/payments/fee', async (_request, reply) => {
    return reply.send({
      feeBps: env.PLATFORM_FEE_BPS,
      feePercent: env.PLATFORM_FEE_BPS / 100,
      defaultFeeBps: PLATFORM_FEE_BPS,
    });
  });
}

function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}
