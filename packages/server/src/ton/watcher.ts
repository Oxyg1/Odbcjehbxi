import { Address, type Transaction } from '@ton/core';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { claimOnce } from '../lib/redis.js';
import { donationService } from '../services/donation.service.js';
import { getTonClient, parseCommentPayload } from './client.js';

/**
 * Escrow watcher.
 *
 * TON has no webhooks, so incoming payments are discovered by polling the
 * escrow wallet's transaction list. Each inbound message carries our
 * transaction id in its text comment; we match on that, verify the amount, and
 * settle exactly once.
 *
 * De-duplication is layered:
 *  1. a Redis one-shot claim on the tx hash (fast, cross-node);
 *  2. a unique index on DonationTransaction.tonTxHash (durable);
 *  3. the SETTLED guard inside donationService.settle.
 */
export class TonWatcher {
  private timer: NodeJS.Timeout | null = null;
  private running = false;
  private lastLogicalTime: string | null = null;

  async start(): Promise<void> {
    if (!env.ENABLE_TON_WATCHER) {
      logger.info('TON watcher disabled on this node');
      return;
    }
    if (!env.TON_ESCROW_ADDRESS) {
      logger.warn('TON watcher enabled but TON_ESCROW_ADDRESS is unset; not starting');
      return;
    }

    logger.info({ address: env.TON_ESCROW_ADDRESS }, 'TON watcher starting');
    this.timer = setInterval(() => {
      void this.poll();
    }, env.TON_POLL_INTERVAL_MS);
    await this.poll();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  /** One polling pass. Overlapping runs are skipped rather than queued. */
  private async poll(): Promise<void> {
    if (this.running) return;
    this.running = true;

    try {
      const client = getTonClient();
      const address = Address.parse(env.TON_ESCROW_ADDRESS as string);
      const transactions = await client.getTransactions(address, { limit: 32 });

      for (const transaction of transactions) {
        const logicalTime = transaction.lt.toString();
        // Transactions come newest-first; stop as soon as we reach known ground.
        if (this.lastLogicalTime !== null && BigInt(logicalTime) <= BigInt(this.lastLogicalTime)) {
          break;
        }
        await this.processTransaction(transaction).catch((error) =>
          logger.error({ err: error, lt: logicalTime }, 'failed to process TON transaction'),
        );
      }

      const newest = transactions[0];
      if (newest) this.lastLogicalTime = newest.lt.toString();
    } catch (error) {
      logger.error({ err: error }, 'TON polling pass failed');
    } finally {
      this.running = false;
    }
  }

  private async processTransaction(transaction: Transaction): Promise<void> {
    const inMessage = transaction.inMessage;
    if (!inMessage || inMessage.info.type !== 'internal') return;

    const amountNanoton = inMessage.info.value.coins;
    if (amountNanoton <= 0n) return;

    const comment = inMessage.body ? parseCommentPayload(inMessage.body) : null;
    if (!comment) return;

    // We only care about comments we minted: `tgdonate:<transactionId>`.
    const match = /^tgdonate:([A-Za-z0-9_-]{10,40})$/.exec(comment.trim());
    if (!match || !match[1]) return;

    const transactionId = match[1];
    const txHash = transaction.hash().toString('base64');

    const isFirstSighting = await claimOnce(`ton:${txHash}`, 7 * 86_400);
    if (!isFirstSighting) return;

    const record = await prisma.donationTransaction.findUnique({
      where: { id: transactionId },
      select: { id: true, status: true, amountNanoton: true, method: true },
    });
    if (!record) {
      logger.warn({ transactionId, txHash }, 'TON payment references an unknown transaction');
      return;
    }
    if (record.status === 'SETTLED') return;

    // Underpayment must not settle: the sender can top up, or we refund.
    const expected = record.amountNanoton ? BigInt(record.amountNanoton.toFixed(0)) : 0n;
    if (expected > 0n && amountNanoton < expected) {
      logger.warn(
        { transactionId, expected: expected.toString(), received: amountNanoton.toString() },
        'TON underpayment ignored',
      );
      await prisma.donationTransaction.update({
        where: { id: transactionId },
        data: { status: 'FAILED' },
      });
      return;
    }

    await prisma.processedEvent
      .create({ data: { source: 'ton', externalId: txHash } })
      .catch(() => undefined);

    await donationService.settle(transactionId, { tonTxHash: txHash });
    logger.info({ transactionId, txHash }, 'settled a TON payment');
  }
}

export const tonWatcher = new TonWatcher();
