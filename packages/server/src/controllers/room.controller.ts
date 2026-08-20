import type { FastifyInstance } from 'fastify';
import { requireTelegramAuth } from '../middleware/auth.js';
import { donationService } from '../services/donation.service.js';
import { roomService } from '../services/room.service.js';
import { standService } from '../services/stand.service.js';
import { sendError } from './errors.js';
import { PaginationQuery } from './schemas.js';

export async function roomRoutes(app: FastifyInstance): Promise<void> {
  app.get('/api/rooms', async (_request, reply) => {
    try {
      const rooms = await roomService.listPublic();
      return await reply.send({ rooms });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get<{ Params: { id: string } }>('/api/rooms/:id', async (request, reply) => {
    try {
      const room = await roomService.getPublicRoom(request.params.id);
      if (!room) {
        return await reply.code(404).send({ error: 'NOT_FOUND', message: 'Room not found' });
      }
      const stands = await standService.listForRoom(room.id);
      return await reply.send({ room, stands });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  /** Auto-placement for users who publish without picking a room. */
  app.post('/api/rooms/suggest', { preHandler: requireTelegramAuth }, async (_request, reply) => {
    try {
      const room = await roomService.suggestRoom();
      if (!room) {
        return await reply.code(404).send({ error: 'NOT_FOUND', message: 'No rooms available' });
      }
      return await reply.send({ roomId: room.id, slug: room.slug });
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get('/api/activity', async (request, reply) => {
    try {
      const { limit } = PaginationQuery.parse(request.query);
      const donations = await donationService.recentGlobal(limit);
      return await reply.send({ donations });
    } catch (error) {
      return sendError(reply, error);
    }
  });
}
