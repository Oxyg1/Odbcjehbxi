import { PRESENCE_HEARTBEAT_MS, type ClientFrame, type ServerFrame } from '@tgdonate/shared';
import { getInitData } from './telegram.js';

type FrameListener = (frame: ServerFrame) => void;
type StatusListener = (status: SocketStatus) => void;

export type SocketStatus = 'connecting' | 'open' | 'closed' | 'reconnecting';

const WS_BASE = (import.meta.env.VITE_WS_URL ?? 'ws://localhost:3000').replace(/\/$/, '');

/** Exponential backoff with a ceiling, so a long outage does not hot-loop. */
const RECONNECT_DELAYS_MS = [500, 1_000, 2_000, 4_000, 8_000, 15_000];

/**
 * Realtime client.
 *
 * Owns exactly one socket for the app's lifetime. Reconnects transparently and
 * replays the room the user was in, so a backgrounded Mini App returning to the
 * foreground lands back in the same room with fresh state.
 */
class SocketClient {
  private socket: WebSocket | null = null;
  private status: SocketStatus = 'closed';
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private currentRoomId: string | null = null;
  private watchedStands = new Set<string>();
  private readonly frameListeners = new Set<FrameListener>();
  private readonly statusListeners = new Set<StatusListener>();
  private intentionallyClosed = false;

  connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.intentionallyClosed = false;
    this.setStatus(this.reconnectAttempt === 0 ? 'connecting' : 'reconnecting');

    const initData = getInitData();
    // Browsers cannot set headers on a handshake, so the credential rides in
    // the query string; the connection is wss:// in production.
    const url = `${WS_BASE}/ws?initData=${encodeURIComponent(initData)}`;

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus('open');
      this.startHeartbeat();
      // Subscriptions are replayed on HELLO, not here: the socket is open
      // before the server has finished authenticating it, and a frame sent in
      // that window can be dropped.
    };

    socket.onmessage = (event) => {
      let frame: ServerFrame;
      try {
        frame = JSON.parse(event.data as string) as ServerFrame;
      } catch {
        return;
      }

      // HELLO is the server's readiness signal — it is only sent once the
      // connection is authenticated and its message handler is attached. That
      // is the earliest point at which a frame is guaranteed to be received.
      if (frame.t === 'HELLO') this.replaySubscriptions();

      for (const listener of this.frameListeners) listener(frame);
    };

    socket.onclose = () => {
      this.stopHeartbeat();
      this.socket = null;
      if (this.intentionallyClosed) {
        this.setStatus('closed');
        return;
      }
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      // `onclose` always follows, so reconnection is handled there.
      socket.close();
    };
  }

  disconnect(): void {
    this.intentionallyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setStatus('closed');
  }

  /** Restore the room and stand subscriptions this session had before. */
  private replaySubscriptions(): void {
    if (this.currentRoomId) {
      this.send({ t: 'JOIN_ROOM', roomId: this.currentRoomId });
    }
    for (const standId of this.watchedStands) {
      this.send({ t: 'SUBSCRIBE_STAND', standId });
    }
  }

  send(frame: ClientFrame): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify(frame));
  }

  joinRoom(roomId: string): void {
    this.currentRoomId = roomId;
    this.send({ t: 'JOIN_ROOM', roomId });
  }

  leaveRoom(): void {
    this.currentRoomId = null;
    this.send({ t: 'LEAVE_ROOM' });
  }

  watchStand(standId: string): void {
    this.watchedStands.add(standId);
    this.send({ t: 'SUBSCRIBE_STAND', standId });
  }

  unwatchStand(standId: string): void {
    this.watchedStands.delete(standId);
  }

  /** Ask the server to re-broadcast our stand after a local edit. */
  publishStandUpdate(standId: string): void {
    this.send({ t: 'STAND_UPDATE', standId });
  }

  react(standId: string, emoji: '🔥' | '💎' | '⭐' | '👑' | '🫡'): void {
    this.send({ t: 'REACTION', standId, emoji });
  }

  onFrame(listener: FrameListener): () => void {
    this.frameListeners.add(listener);
    return () => this.frameListeners.delete(listener);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  getStatus(): SocketStatus {
    return this.status;
  }

  private setStatus(status: SocketStatus): void {
    if (this.status === status) return;
    this.status = status;
    for (const listener of this.statusListeners) listener(status);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    const delay =
      RECONNECT_DELAYS_MS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)] ?? 15_000;
    this.reconnectAttempt += 1;
    this.setStatus('reconnecting');

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ t: 'HEARTBEAT' });
    }, PRESENCE_HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }
}

export const socket = new SocketClient();
