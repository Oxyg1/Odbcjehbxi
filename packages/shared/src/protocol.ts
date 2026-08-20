import { z } from 'zod';
import type {
  DonationEventPayload,
  LeaderboardRow,
  PublicUser,
  Room,
  Stand,
} from './types.js';

/**
 * Realtime protocol.
 *
 * Every envelope is a discriminated union on `t` (type). Client→server frames
 * are validated with Zod at the gateway boundary; server→client frames are
 * constructed exclusively by the server and typed structurally.
 */

/* -------------------------------------------------------------------------- */
/*                              Client -> Server                              */
/* -------------------------------------------------------------------------- */

export const JoinRoomFrame = z.object({
  t: z.literal('JOIN_ROOM'),
  roomId: z.string().min(1).max(64),
});

export const LeaveRoomFrame = z.object({
  t: z.literal('LEAVE_ROOM'),
});

export const HeartbeatFrame = z.object({
  t: z.literal('HEARTBEAT'),
});

/**
 * Optimistic stand edit. The gateway never trusts the payload as-is: it
 * re-reads the persisted stand and broadcasts the authoritative projection.
 */
export const StandUpdateFrame = z.object({
  t: z.literal('STAND_UPDATE'),
  standId: z.string().min(1).max(64),
});

export const ReactionFrame = z.object({
  t: z.literal('REACTION'),
  standId: z.string().min(1).max(64),
  emoji: z.enum(['🔥', '💎', '⭐', '👑', '🫡']),
});

export const SubscribeStandFrame = z.object({
  t: z.literal('SUBSCRIBE_STAND'),
  standId: z.string().min(1).max(64),
});

export const ClientFrame = z.discriminatedUnion('t', [
  JoinRoomFrame,
  LeaveRoomFrame,
  HeartbeatFrame,
  StandUpdateFrame,
  ReactionFrame,
  SubscribeStandFrame,
]);

export type ClientFrame = z.infer<typeof ClientFrame>;
export type ClientFrameType = ClientFrame['t'];

/* -------------------------------------------------------------------------- */
/*                              Server -> Client                              */
/* -------------------------------------------------------------------------- */

export interface ServerHelloFrame {
  t: 'HELLO';
  socketId: string;
  user: PublicUser;
  onlineCount: number;
  serverTime: string;
}

export interface RoomStateFrame {
  t: 'ROOM_STATE';
  room: Room;
  stands: Stand[];
  occupants: PublicUser[];
}

export interface StandUpsertFrame {
  t: 'STAND_UPDATE';
  stand: Stand;
}

export interface StandRemovedFrame {
  t: 'STAND_REMOVED';
  standId: string;
  roomId: string;
}

/** Micro/major donations, scoped to a single room. */
export interface DonationEventFrame {
  t: 'DONATION_EVENT';
  donation: DonationEventPayload;
  /** Post-donation totals so clients can reconcile without refetching. */
  standTotals: {
    standId: string;
    totalStarsReceived: number;
    totalGiftsReceived: number;
    supporterCount: number;
  };
}

/** Whale-tier donations, fanned out to every connected client. */
export interface GlobalBroadcastFrame {
  t: 'GLOBAL_BROADCAST';
  donation: DonationEventPayload;
  /** Deep-link target so the overlay's CTA can teleport the viewer. */
  jump: {
    roomId: string | null;
    standId: string;
  };
  expiresAt: string;
}

export interface PresenceFrame {
  t: 'PRESENCE';
  roomId: string;
  occupancy: number;
  onlineCount: number;
  joined: PublicUser[];
  left: string[];
}

export interface ReactionBroadcastFrame {
  t: 'REACTION';
  roomId: string;
  standId: string;
  emoji: string;
  fromUserId: string;
}

export interface LeaderboardTickFrame {
  t: 'LEADERBOARD_TICK';
  scope: 'DAILY' | 'WEEKLY' | 'ALL_TIME';
  rows: LeaderboardRow[];
}

/** Private, user-scoped notice (payment settled, gift received, refund). */
export interface UserNoticeFrame {
  t: 'USER_NOTICE';
  /** Routing key: the gateway delivers this only to that user's sockets. */
  targetUserId: string;
  kind: 'PAYMENT_SETTLED' | 'GIFT_RECEIVED' | 'REFUNDED' | 'THEME_UNLOCKED' | 'LISTING_SOLD';
  title: string;
  body: string;
  meta: Record<string, string | number | null>;
}

export interface ErrorFrame {
  t: 'ERROR';
  code:
    | 'UNAUTHORIZED'
    | 'RATE_LIMITED'
    | 'BAD_FRAME'
    | 'ROOM_FULL'
    | 'NOT_FOUND'
    | 'INTERNAL';
  message: string;
  /** Present on RATE_LIMITED: milliseconds until the budget refills. */
  retryAfterMs?: number;
}

export type ServerFrame =
  | ServerHelloFrame
  | RoomStateFrame
  | StandUpsertFrame
  | StandRemovedFrame
  | DonationEventFrame
  | GlobalBroadcastFrame
  | PresenceFrame
  | ReactionBroadcastFrame
  | LeaderboardTickFrame
  | UserNoticeFrame
  | ErrorFrame;

export type ServerFrameType = ServerFrame['t'];

/**
 * Envelope published on Redis Pub/Sub. `originNodeId` lets a gateway node skip
 * re-delivering a frame it has already written to its own local sockets.
 */
export interface BroadcastEnvelope {
  originNodeId: string;
  frame: ServerFrame;
  /** Optional socket id to exclude (the actor's own connection). */
  excludeSocketId?: string;
}

export function parseClientFrame(
  raw: string,
): { ok: true; frame: ClientFrame } | { ok: false; error: string } {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { ok: false, error: 'Malformed JSON envelope' };
  }
  const parsed = ClientFrame.safeParse(json);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? 'Invalid frame' };
  }
  return { ok: true, frame: parsed.data };
}
