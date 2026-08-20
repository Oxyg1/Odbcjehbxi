import pino from 'pino';
import { env, isProduction } from '../config/env.js';

export const logger = pino({
  level: env.LOG_LEVEL,
  base: { nodeId: env.NODE_ID },
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers["x-telegram-init-data"]',
      'initData',
      'hash',
      '*.telegramChargeId',
    ],
    censor: '[redacted]',
  },
  transport: isProduction
    ? undefined
    : { target: 'pino/file', options: { destination: 1 } },
});

export type Logger = typeof logger;
