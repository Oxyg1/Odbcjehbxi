import type { FastifyReply } from 'fastify';
import { ZodError } from 'zod';
import { logger } from '../lib/logger.js';
import { LockAcquisitionError } from '../lib/redis.js';
import { DonationError } from '../services/donation.service.js';
import { GiftError } from '../services/gift.service.js';
import {
  GiftUnavailableError,
  ListingValidationError,
} from '../services/listing.service.js';
import {
  ForbiddenError,
  ListingLimitError,
  RoomFullError,
  StandNotFoundError,
} from '../services/stand.service.js';
import { WalletAlreadyLinkedError } from '../services/user.service.js';
import { StarsInvoiceError } from '../telegram/payments.js';

/**
 * Single place that maps a domain error to an HTTP status. Keeping this out of
 * the handlers means a new service error cannot accidentally become a 500 with
 * a stack trace in the response body.
 */
export async function sendError(reply: FastifyReply, error: unknown): Promise<void> {
  if (error instanceof ZodError) {
    await reply.code(400).send({
      error: 'VALIDATION_FAILED',
      message: 'Request body failed validation',
      issues: error.issues.map((issue) => ({
        path: issue.path.join('.'),
        message: issue.message,
      })),
    });
    return;
  }

  if (error instanceof StandNotFoundError) {
    await reply.code(404).send({ error: 'NOT_FOUND', message: error.message });
    return;
  }

  if (error instanceof ForbiddenError) {
    await reply.code(403).send({ error: 'FORBIDDEN', message: error.message });
    return;
  }

  if (error instanceof RoomFullError) {
    await reply.code(409).send({ error: 'ROOM_FULL', message: error.message });
    return;
  }

  if (error instanceof ListingLimitError || error instanceof GiftUnavailableError) {
    await reply.code(409).send({ error: 'CONFLICT', message: error.message });
    return;
  }

  if (error instanceof ListingValidationError) {
    await reply.code(400).send({ error: 'INVALID_LISTING', message: error.message });
    return;
  }

  if (error instanceof WalletAlreadyLinkedError) {
    await reply.code(409).send({ error: 'WALLET_TAKEN', message: error.message });
    return;
  }

  if (error instanceof DonationError) {
    const status = error.code === 'STAND_NOT_FOUND' || error.code === 'TX_NOT_FOUND' ? 404 : 409;
    await reply.code(status).send({ error: error.code, message: error.message });
    return;
  }

  if (error instanceof StarsInvoiceError) {
    const status =
      error.code === 'THEME_NOT_FOUND' ? 404 : error.code === 'INVALID_AMOUNT' ? 400 : 409;
    await reply.code(status).send({ error: error.code, message: error.message });
    return;
  }

  if (error instanceof GiftError) {
    const status = error.code === 'NOT_FOUND' || error.code === 'USER_NOT_FOUND' ? 404 : 409;
    await reply.code(status).send({ error: error.code, message: error.message });
    return;
  }

  if (error instanceof LockAcquisitionError) {
    await reply.code(503).send({
      error: 'BUSY',
      message: 'That item is busy right now — try again in a moment',
    });
    return;
  }

  logger.error({ err: error }, 'unhandled route error');
  await reply.code(500).send({ error: 'INTERNAL', message: 'Something went wrong' });
}
