import { randomUUID } from 'node:crypto';
import type { IncomingMessage, Server as HttpServer } from 'node:http';
import { WebSocket, WebSocketServer, type RawData } from 'ws';
import {
  PRESENCE_HEARTBEAT_MS,
  PRESENCE_TTL_SECONDS,
  RedisChannels,
  RedisKeys,
  WS_RATE_LIMITS,
  parseClientFrame,
  type ClientFrame,
  type ErrorFrame,
  type PublicUser,
  type ServerFrame,
} from '@tgdonate/shared';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { consumeRateLimit, redis } from '../lib/redis.js';
import { InitDataError, verifyInitData } from '../telegram/init-data.js';
import { roomService } from '../services/room.service.js';
import { standService } from '../services/stand.service.js';
import { toPublicUser, userService } from '../services/user.service.js';
import { broadcaster } from './broadcaster.js';

interface Connection {
  id: string;
  socket: WebSocket;
  userId: string;
  user: PublicUser;
  roomId: string | null;
  /** Stands this socket watches outside its current room (e.g. a deep link). */
  watchedStands: Set<string>;
  isAlive: boolean;
  connectedAt: number;
}

/**
 * The realtime gateway.
 *
 * Responsibilities:
 *  - authenticate the upgrade with the same initData HMAC used by the REST API;
 *  - keep per-room membership in memory (fast) and in Redis (shared);
 *  - fan frames out through Redis so every node sees every event;
 *  - rate-limit inbound frames per connection so one client cannot flood a room.
 */
export class RealtimeGateway {
  private readonly wss: WebSocketServer;
  private readonly connections = new Map<string, Connection>();
  private readonly rooms = new Map<string, Set<string>>();
  private readonly userSockets = new Map<string, Set<string>>();
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private presenceTimer: NodeJS.Timeout | null = null;

  constructor(server: HttpServer) {
    this.wss = new WebSocketServer({ server, path: '/ws', maxPayload: 16 * 1024 });
  }

  async start(): Promise<void> {
    await broadcaster.start();

    broadcaster.onMessage((envelope) => {
      this.deliverLocally(envelope.frame, envelope.excludeSocketId);
    });

    this.wss.on('connection', (socket, request) => {
      void this.handleConnection(socket, request);
    });

    // ws does not implement a keepalive for us; without one, half-open TCP
    // connections linger and inflate room occupancy indefinitely.
    this.heartbeatTimer = setInterval(() => this.sweepDeadSockets(), PRESENCE_HEARTBEAT_MS);
    this.presenceTimer = setInterval(() => {
      void this.refreshPresenceTtl();
    }, PRESENCE_HEARTBEAT_MS);

    logger.info('realtime gateway listening on /ws');
  }

  async stop(): Promise<void> {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    if (this.presenceTimer) clearInterval(this.presenceTimer);

    for (const connection of this.connections.values()) {
      connection.socket.close(1001, 'Server shutting down');
    }
    await new Promise<void>((resolve) => this.wss.close(() => resolve()));
  }

  get onlineCount(): number {
    return this.connections.size;
  }

  /* ------------------------------ lifecycle ----------------------------- */

  private async handleConnection(socket: WebSocket, request: IncomingMessage): Promise<void> {
    const initData = extractInitDataFromUpgrade(request);
    if (!initData) {
      closeWithError(socket, 'UNAUTHORIZED', 'Missing initData in the upgrade request');
      return;
    }

    /*
     * The handshake completes — and the client's `open` fires — before the
     * authentication below finishes, because resolving the user hits the
     * database. `ws` drops any frame that arrives while no 'message' listener
     * is attached, so a client that sends immediately on open (which is exactly
     * what our own reconnect path does when it replays JOIN_ROOM) loses that
     * frame silently and never gets its room back.
     *
     * Buffer from the first tick, then replay once the real handler is wired.
     */
    const pending: RawData[] = [];
    const bufferEarlyFrames = (data: RawData): void => {
      // Bound the buffer: an unauthenticated peer must not be able to make us
      // hold arbitrary memory before we know who they are.
      if (pending.length < 16) pending.push(data);
    };
    socket.on('message', bufferEarlyFrames);

    let telegramUserId: number;
    try {
      const verified = verifyInitData(initData, {
        botToken: env.TELEGRAM_BOT_TOKEN,
        maxAgeSeconds: env.INITDATA_MAX_AGE_SECONDS,
      });
      telegramUserId = verified.user.id;
      const user = await userService.upsertFromTelegram(verified.user);
      if (user.isBanned) {
        socket.off('message', bufferEarlyFrames);
        closeWithError(socket, 'UNAUTHORIZED', 'Account suspended');
        return;
      }

      const connection: Connection = {
        id: randomUUID(),
        socket,
        userId: user.id,
        user: toPublicUser(user),
        roomId: null,
        watchedStands: new Set(),
        isAlive: true,
        connectedAt: Date.now(),
      };
      socket.off('message', bufferEarlyFrames);
      this.registerConnection(connection);
      await this.onConnectionReady(connection);

      // HELLO has been sent; anything the client fired before we were ready is
      // now safe to process in arrival order.
      for (const data of pending) {
        void this.handleMessage(connection, data);
      }
      pending.length = 0;
    } catch (error) {
      socket.off('message', bufferEarlyFrames);
      const reason = error instanceof InitDataError ? error.reason : 'INTERNAL';
      logger.warn({ reason }, 'websocket auth failed');
      closeWithError(socket, 'UNAUTHORIZED', 'Invalid initData');
      return;
    }

    logger.debug({ telegramUserId }, 'websocket connected');
  }

  private registerConnection(connection: Connection): void {
    this.connections.set(connection.id, connection);

    let sockets = this.userSockets.get(connection.userId);
    if (!sockets) {
      sockets = new Set();
      this.userSockets.set(connection.userId, sockets);
    }
    sockets.add(connection.id);

    connection.socket.on('pong', () => {
      connection.isAlive = true;
    });
    connection.socket.on('message', (data) => {
      void this.handleMessage(connection, data);
    });
    connection.socket.on('close', () => {
      void this.handleClose(connection);
    });
    connection.socket.on('error', (error) => {
      logger.debug({ err: error, socketId: connection.id }, 'websocket error');
    });
  }

  private async onConnectionReady(connection: Connection): Promise<void> {
    // Per-user channel so payment confirmations reach every device the user has
    // open, regardless of which room each one is in.
    await broadcaster.subscribe(RedisChannels.user(connection.userId));
    await redis.sadd(RedisKeys.userSockets(connection.userId), connection.id);

    this.send(connection, {
      t: 'HELLO',
      socketId: connection.id,
      user: connection.user,
      onlineCount: this.connections.size,
      serverTime: new Date().toISOString(),
    });
  }

  private async handleClose(connection: Connection): Promise<void> {
    this.connections.delete(connection.id);

    const sockets = this.userSockets.get(connection.userId);
    if (sockets) {
      sockets.delete(connection.id);
      if (sockets.size === 0) {
        this.userSockets.delete(connection.userId);
        await broadcaster.unsubscribe(RedisChannels.user(connection.userId));
      }
    }
    await redis.srem(RedisKeys.userSockets(connection.userId), connection.id).catch(() => 0);

    if (connection.roomId) {
      await this.leaveRoom(connection);
    }
    await userService.touchLastSeen(connection.userId);
  }

  /* ------------------------------- inbound ------------------------------ */

  private async handleMessage(connection: Connection, data: RawData): Promise<void> {
    const budget = await consumeRateLimit('ws:in', connection.id, WS_RATE_LIMITS.inbound);
    if (!budget.allowed) {
      this.send(connection, {
        t: 'ERROR',
        code: 'RATE_LIMITED',
        message: 'Slow down',
        retryAfterMs: budget.retryAfterMs,
      });
      return;
    }

    const parsed = parseClientFrame(data.toString());
    if (!parsed.ok) {
      this.send(connection, { t: 'ERROR', code: 'BAD_FRAME', message: parsed.error });
      return;
    }

    try {
      await this.dispatch(connection, parsed.frame);
    } catch (error) {
      logger.error({ err: error, frame: parsed.frame.t }, 'frame handler failed');
      this.send(connection, {
        t: 'ERROR',
        code: 'INTERNAL',
        message: 'Could not process that action',
      });
    }
  }

  private async dispatch(connection: Connection, frame: ClientFrame): Promise<void> {
    switch (frame.t) {
      case 'HEARTBEAT': {
        connection.isAlive = true;
        if (connection.roomId) {
          await redis.hset(
            RedisKeys.roomPresence(connection.roomId),
            connection.id,
            Date.now().toString(),
          );
        }
        return;
      }
      case 'JOIN_ROOM': {
        const budget = await consumeRateLimit(
          'ws:join',
          connection.id,
          WS_RATE_LIMITS.joinRoom,
        );
        if (!budget.allowed) {
          this.send(connection, {
            t: 'ERROR',
            code: 'RATE_LIMITED',
            message: 'Too many room switches',
            retryAfterMs: budget.retryAfterMs,
          });
          return;
        }
        await this.joinRoom(connection, frame.roomId);
        return;
      }
      case 'LEAVE_ROOM': {
        await this.leaveRoom(connection);
        return;
      }
      case 'SUBSCRIBE_STAND': {
        connection.watchedStands.add(frame.standId);
        const stand = await standService.getByIdOrNull(frame.standId);
        if (!stand) {
          this.send(connection, { t: 'ERROR', code: 'NOT_FOUND', message: 'Stand not found' });
          return;
        }
        this.send(connection, { t: 'STAND_UPDATE', stand });
        return;
      }
      case 'STAND_UPDATE': {
        const budget = await consumeRateLimit(
          'ws:stand',
          connection.userId,
          WS_RATE_LIMITS.standUpdate,
        );
        if (!budget.allowed) {
          this.send(connection, {
            t: 'ERROR',
            code: 'RATE_LIMITED',
            message: 'Editing too fast',
            retryAfterMs: budget.retryAfterMs,
          });
          return;
        }
        // Never trust the client's copy of the stand: re-read and broadcast the
        // authoritative row so a hostile client cannot inject fake totals.
        const stand = await standService.getByIdOrNull(frame.standId);
        if (!stand) {
          this.send(connection, { t: 'ERROR', code: 'NOT_FOUND', message: 'Stand not found' });
          return;
        }
        if (stand.ownerId !== connection.userId) {
          this.send(connection, {
            t: 'ERROR',
            code: 'UNAUTHORIZED',
            message: 'You do not own this stand',
          });
          return;
        }
        await this.publishStandUpdate(stand.id);
        return;
      }
      case 'REACTION': {
        const budget = await consumeRateLimit(
          'ws:react',
          connection.userId,
          WS_RATE_LIMITS.reaction,
        );
        if (!budget.allowed) return; // Reactions are cosmetic; drop silently.
        if (!connection.roomId) return;
        await broadcaster.toRoom(connection.roomId, {
          t: 'REACTION',
          roomId: connection.roomId,
          standId: frame.standId,
          emoji: frame.emoji,
          fromUserId: connection.userId,
        });
        return;
      }
    }
  }

  /* -------------------------------- rooms ------------------------------- */

  private async joinRoom(connection: Connection, roomId: string): Promise<void> {
    const room = await roomService.getById(roomId);
    if (!room) {
      this.send(connection, { t: 'ERROR', code: 'NOT_FOUND', message: 'Room not found' });
      return;
    }

    if (connection.roomId === roomId) {
      await this.sendRoomState(connection, roomId);
      return;
    }
    if (connection.roomId) {
      await this.leaveRoom(connection);
    }

    connection.roomId = roomId;
    let members = this.rooms.get(roomId);
    if (!members) {
      members = new Set();
      this.rooms.set(roomId, members);
      await broadcaster.subscribe(RedisChannels.room(roomId));
    }
    members.add(connection.id);

    await redis.hset(RedisKeys.roomPresence(roomId), connection.id, Date.now().toString());
    await redis.expire(RedisKeys.roomPresence(roomId), PRESENCE_TTL_SECONDS * 4);

    await prisma.roomSession
      .upsert({
        where: { socketId: connection.id },
        create: {
          socketId: connection.id,
          nodeId: env.NODE_ID,
          userId: connection.userId,
          roomId,
        },
        update: { roomId, leftAt: null, lastHeartbeat: new Date() },
      })
      .catch((error) => logger.warn({ err: error }, 'could not persist room session'));

    await this.sendRoomState(connection, roomId);

    await broadcaster.toRoom(
      roomId,
      {
        t: 'PRESENCE',
        roomId,
        occupancy: await roomService.occupancy(roomId),
        onlineCount: this.connections.size,
        joined: [connection.user],
        left: [],
      },
      connection.id,
    );
  }

  private async leaveRoom(connection: Connection): Promise<void> {
    const roomId = connection.roomId;
    if (!roomId) return;

    connection.roomId = null;
    const members = this.rooms.get(roomId);
    if (members) {
      members.delete(connection.id);
      if (members.size === 0) {
        this.rooms.delete(roomId);
        await broadcaster.unsubscribe(RedisChannels.room(roomId));
      }
    }

    await redis.hdel(RedisKeys.roomPresence(roomId), connection.id).catch(() => 0);
    await prisma.roomSession
      .updateMany({ where: { socketId: connection.id }, data: { leftAt: new Date() } })
      .catch(() => undefined);

    await broadcaster.toRoom(roomId, {
      t: 'PRESENCE',
      roomId,
      occupancy: await roomService.occupancy(roomId),
      onlineCount: this.connections.size,
      joined: [],
      left: [connection.userId],
    });
  }

  private async sendRoomState(connection: Connection, roomId: string): Promise<void> {
    const [room, stands] = await Promise.all([
      roomService.getPublicRoom(roomId),
      standService.listForRoom(roomId),
    ]);
    if (!room) return;

    const occupants = this.occupantsOf(roomId);
    const onlineOwners = new Set(occupants.map((occupant) => occupant.id));

    this.send(connection, {
      t: 'ROOM_STATE',
      room,
      stands: stands.map((stand) => ({
        ...stand,
        isOwnerOnline: onlineOwners.has(stand.ownerId),
      })),
      occupants,
    });
  }

  private occupantsOf(roomId: string): PublicUser[] {
    const members = this.rooms.get(roomId);
    if (!members) return [];
    const seen = new Set<string>();
    const occupants: PublicUser[] = [];
    for (const socketId of members) {
      const connection = this.connections.get(socketId);
      if (!connection || seen.has(connection.userId)) continue;
      seen.add(connection.userId);
      occupants.push(connection.user);
    }
    return occupants;
  }

  /** Re-read a stand and push the authoritative projection to its room. */
  async publishStandUpdate(standId: string): Promise<void> {
    const stand = await standService.getByIdOrNull(standId);
    if (!stand) return;
    const frame: ServerFrame = { t: 'STAND_UPDATE', stand };

    if (stand.roomId) {
      await broadcaster.toRoom(stand.roomId, frame);
    } else {
      // An unplaced stand still has watchers (its owner's editor, deep links).
      this.deliverLocally(frame);
    }
  }

  /* ------------------------------- outbound ----------------------------- */

  private send(connection: Connection, frame: ServerFrame): void {
    if (connection.socket.readyState !== WebSocket.OPEN) return;
    connection.socket.send(JSON.stringify(frame));
  }

  /**
   * Write a frame to the sockets this node owns. Routing mirrors the channel
   * the frame arrived on, derived from the frame's own shape.
   */
  private deliverLocally(frame: ServerFrame, excludeSocketId?: string): void {
    const targets = this.resolveTargets(frame);
    const payload = JSON.stringify(frame);

    for (const connection of targets) {
      if (excludeSocketId && connection.id === excludeSocketId) continue;
      if (connection.socket.readyState !== WebSocket.OPEN) continue;
      connection.socket.send(payload);
    }
  }

  private resolveTargets(frame: ServerFrame): Connection[] {
    switch (frame.t) {
      case 'GLOBAL_BROADCAST':
      case 'LEADERBOARD_TICK':
        return [...this.connections.values()];

      case 'USER_NOTICE':
        return this.socketsOf(frame.targetUserId);

      case 'DONATION_EVENT': {
        const roomId = frame.donation.roomId;
        const inRoom = roomId ? this.membersOf(roomId) : [];
        const watchers = this.watchersOf(frame.donation.standId);
        return dedupe([...inRoom, ...watchers]);
      }
      case 'STAND_UPDATE': {
        const inRoom = frame.stand.roomId ? this.membersOf(frame.stand.roomId) : [];
        const watchers = this.watchersOf(frame.stand.id);
        return dedupe([...inRoom, ...watchers]);
      }
      case 'STAND_REMOVED':
        return this.membersOf(frame.roomId);
      case 'ROOM_STATE':
        return this.membersOf(frame.room.id);
      case 'PRESENCE':
        return this.membersOf(frame.roomId);
      case 'REACTION':
        return dedupe([...this.membersOf(frame.roomId), ...this.watchersOf(frame.standId)]);
      case 'HELLO':
      case 'ERROR':
        return [];
      default:
        return [];
    }
  }

  private membersOf(roomId: string): Connection[] {
    const members = this.rooms.get(roomId);
    if (!members) return [];
    const connections: Connection[] = [];
    for (const socketId of members) {
      const connection = this.connections.get(socketId);
      if (connection) connections.push(connection);
    }
    return connections;
  }

  private watchersOf(standId: string): Connection[] {
    const connections: Connection[] = [];
    for (const connection of this.connections.values()) {
      if (connection.watchedStands.has(standId)) connections.push(connection);
    }
    return connections;
  }

  private socketsOf(userId: string): Connection[] {
    const sockets = this.userSockets.get(userId);
    if (!sockets) return [];
    const connections: Connection[] = [];
    for (const socketId of sockets) {
      const connection = this.connections.get(socketId);
      if (connection) connections.push(connection);
    }
    return connections;
  }

  /** Deliver a user-scoped frame to every socket this node holds for the user. */
  deliverToUserLocally(userId: string, frame: ServerFrame): void {
    const sockets = this.userSockets.get(userId);
    if (!sockets) return;
    const payload = JSON.stringify(frame);
    for (const socketId of sockets) {
      const connection = this.connections.get(socketId);
      if (connection && connection.socket.readyState === WebSocket.OPEN) {
        connection.socket.send(payload);
      }
    }
  }

  /* ------------------------------ keepalive ----------------------------- */

  private sweepDeadSockets(): void {
    for (const connection of this.connections.values()) {
      if (!connection.isAlive) {
        connection.socket.terminate();
        continue;
      }
      connection.isAlive = false;
      connection.socket.ping();
    }
  }

  private async refreshPresenceTtl(): Promise<void> {
    const now = Date.now().toString();
    for (const [roomId, members] of this.rooms) {
      if (members.size === 0) continue;
      const entries: string[] = [];
      for (const socketId of members) entries.push(socketId, now);
      await redis
        .hset(RedisKeys.roomPresence(roomId), ...entries)
        .catch((error) => logger.debug({ err: error }, 'presence refresh failed'));
      await redis.expire(RedisKeys.roomPresence(roomId), PRESENCE_TTL_SECONDS * 4).catch(() => 0);
    }
  }
}

/* ------------------------------- helpers -------------------------------- */

let gatewayInstance: RealtimeGateway | null = null;

export function setGateway(gateway: RealtimeGateway): void {
  gatewayInstance = gateway;
}

export function getGateway(): RealtimeGateway | null {
  return gatewayInstance;
}

function extractInitDataFromUpgrade(request: IncomingMessage): string | null {
  // Browsers cannot set headers on a WebSocket handshake, so the Mini App
  // passes initData as a query parameter. `Sec-WebSocket-Protocol` is accepted
  // as a fallback for native clients.
  try {
    const url = new URL(request.url ?? '/', 'http://localhost');
    const fromQuery = url.searchParams.get('initData');
    if (fromQuery) return fromQuery;
  } catch {
    // fall through to the header check
  }
  const protocolHeader = request.headers['sec-websocket-protocol'];
  if (typeof protocolHeader === 'string' && protocolHeader.startsWith('tma.')) {
    return decodeURIComponent(protocolHeader.slice(4));
  }
  return null;
}

function closeWithError(socket: WebSocket, code: ErrorFrame['code'], message: string): void {
  const frame: ErrorFrame = { t: 'ERROR', code, message };
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(frame));
  }
  socket.close(4001, message);
}

function dedupe(connections: Connection[]): Connection[] {
  const seen = new Set<string>();
  const result: Connection[] = [];
  for (const connection of connections) {
    if (seen.has(connection.id)) continue;
    seen.add(connection.id);
    result.push(connection);
  }
  return result;
}
