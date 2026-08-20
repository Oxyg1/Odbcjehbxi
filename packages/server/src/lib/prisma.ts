import { PrismaClient } from '@prisma/client';
import { env, isProduction } from '../config/env.js';
import { logger } from './logger.js';

export const prisma = new PrismaClient({
  datasources: { db: { url: env.DATABASE_URL } },
  log: isProduction
    ? [{ emit: 'event', level: 'error' }]
    : [
        { emit: 'event', level: 'error' },
        { emit: 'event', level: 'warn' },
      ],
});

prisma.$on('error' as never, (event: unknown) => {
  logger.error({ event }, 'prisma error');
});

export async function disconnectPrisma(): Promise<void> {
  await prisma.$disconnect();
}

/**
 * `JSON.stringify` cannot serialise BigInt, and Prisma returns Telegram ids as
 * BigInt. Rather than patching the prototype globally (which leaks into every
 * dependency), callers convert explicitly through this helper.
 */
export function toNumberId(value: bigint): number {
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new RangeError(`Telegram id ${value} exceeds Number.MAX_SAFE_INTEGER`);
  }
  return Number(value);
}
