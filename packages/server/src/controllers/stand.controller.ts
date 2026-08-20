import type { FastifyInstance } from 'fastify';
import { getAuth, requireTelegramAuth } from '../middleware/auth.js';
import { getGateway } from '../realtime/gateway.js';
import { donationService } from '../services/donation.service.js';
import { listingService } from '../services/listing.service.js';
import { standService } from '../services/stand.service.js';
import { sendError } from './errors.js';
import {
  CreateListingBody,
  PaginationQuery,
  ReorderListingsBody,
  UpdateListingBody,
  UpdateStandBody,
} from './schemas.js';

export async function standRoutes(app: FastifyInstance): Promise<void> {
  /** The caller's own stand, created on first access. */
  app.get('/api/stands/me', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const stand = await standService.getOrCreateForUser(user.id);
      return await reply.send({ stand });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get<{ Params: { id: string } }>('/api/stands/:id', async (request, reply) => {
    try {
      const stand = await standService.getById(request.params.id);
      return await reply.send({ stand });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get<{ Params: { id: string }; Querystring: unknown }>(
    '/api/stands/:id/supporters',
    async (request, reply) => {
      try {
        const { limit } = PaginationQuery.parse(request.query);
        const donations = await donationService.recentForStand(request.params.id, limit);
        return await reply.send({ donations });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  app.get('/api/stands/trending', async (_request, reply) => {
    try {
      const stands = await standService.trending();
      return await reply.send({ stands });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  /** Edit the caller's stand, then push the new state to its room live. */
  app.patch('/api/stands/me', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const body = UpdateStandBody.parse(request.body);
      const stand = await standService.update(user.id, body);
      await getGateway()?.publishStandUpdate(stand.id);
      return await reply.send({ stand });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.post('/api/stands/me/listings', { preHandler: requireTelegramAuth }, async (request, reply) => {
    try {
      const { user } = getAuth(request);
      const body = CreateListingBody.parse(request.body);
      const listing = await listingService.create(user.id, body);
      await getGateway()?.publishStandUpdate(listing.standId);
      return await reply.code(201).send({ listing });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.patch<{ Params: { listingId: string } }>(
    '/api/stands/me/listings/:listingId',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const body = UpdateListingBody.parse(request.body);
        const listing = await listingService.update(user.id, request.params.listingId, body);
        await getGateway()?.publishStandUpdate(listing.standId);
        return await reply.send({ listing });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  app.delete<{ Params: { listingId: string } }>(
    '/api/stands/me/listings/:listingId',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const stand = await standService.getOrCreateForUser(user.id);
        await listingService.remove(user.id, request.params.listingId);
        await getGateway()?.publishStandUpdate(stand.id);
        return await reply.code(204).send();
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );

  app.post(
    '/api/stands/me/listings/reorder',
    { preHandler: requireTelegramAuth },
    async (request, reply) => {
      try {
        const { user } = getAuth(request);
        const { order } = ReorderListingsBody.parse(request.body);
        const stand = await standService.reorderListings(user.id, order);
        await getGateway()?.publishStandUpdate(stand.id);
        return await reply.send({ stand });
      } catch (error) {
        return sendError(reply, error);
      }
    },
  );
}
