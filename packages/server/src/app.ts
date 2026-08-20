import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import rateLimit from '@fastify/rate-limit';
import Fastify, { type FastifyBaseLogger, type FastifyInstance } from 'fastify';
import { env, isProduction } from './config/env.js';
import { logger } from './lib/logger.js';
import { extractInitData } from './middleware/auth.js';
import { paymentRoutes } from './controllers/payment.controller.js';
import { roomRoutes } from './controllers/room.controller.js';
import { standRoutes } from './controllers/stand.controller.js';
import { userRoutes } from './controllers/user.controller.js';
import { webhookRoutes } from './controllers/webhook.controller.js';
import { getGateway } from './realtime/gateway.js';

export async function buildApp(): Promise<FastifyInstance> {
  const app = Fastify({
    // pino's concrete Logger type is structurally narrower than Fastify's
    // FastifyBaseLogger; the instance satisfies the interface Fastify uses.
    loggerInstance: logger as FastifyBaseLogger,
    trustProxy: true,
    bodyLimit: 256 * 1024,
    disableRequestLogging: !isProduction,
  });

  await app.register(helmet, {
    // The Mini App is served separately; this API returns JSON only, so the
    // restrictive default CSP would only get in the way of the docs route.
    contentSecurityPolicy: false,
    crossOriginEmbedderPolicy: false,
  });

  await app.register(cors, {
    origin: (origin, callback) => {
      // Telegram's in-app browser omits Origin on some platforms; allow those
      // through since initData is what actually authenticates the caller.
      if (!origin) return callback(null, true);
      if (env.corsOrigins.length === 0) return callback(null, true);
      if (env.corsOrigins.includes(origin)) return callback(null, true);
      return callback(new Error('Origin not allowed'), false);
    },
    credentials: true,
    allowedHeaders: ['content-type', 'authorization', 'x-telegram-init-data', 'x-webhook-secret'],
    methods: ['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
  });

  /**
   * Coarse IP-level limiter in front of the per-user limiter in the auth
   * middleware. This one exists to blunt unauthenticated floods; the per-user
   * one enforces fair use among real accounts.
   */
  await app.register(rateLimit, {
    global: true,
    max: 300,
    timeWindow: '1 minute',
    allowList: (request) => request.url.startsWith('/telegram/webhook/'),
    keyGenerator: (request) => {
      const initData = extractInitData(request);
      return initData ? `tma:${initData.slice(0, 64)}` : request.ip;
    },
  });

  app.get('/health', async () => ({
    status: 'ok',
    nodeId: env.NODE_ID,
    online: getGateway()?.onlineCount ?? 0,
    uptimeSeconds: Math.floor(process.uptime()),
  }));

  await app.register(userRoutes);
  await app.register(standRoutes);
  await app.register(roomRoutes);
  await app.register(paymentRoutes);
  await app.register(webhookRoutes);

  app.setNotFoundHandler(async (request, reply) => {
    await reply.code(404).send({ error: 'NOT_FOUND', message: `No route for ${request.url}` });
  });

  return app;
}
