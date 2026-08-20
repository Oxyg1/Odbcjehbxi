import { RedisChannels, type BroadcastEnvelope, type ServerFrame } from '@tgdonate/shared';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { redisPublisher, redisSubscriber } from '../lib/redis.js';

type Handler = (envelope: BroadcastEnvelope) => void;

/**
 * Cross-node fan-out.
 *
 * The gateway is horizontally scaled, so a donation settled on node A must
 * reach sockets held by node B. Every frame therefore goes through Redis
 * Pub/Sub; each node writes to its own local sockets when the message comes
 * back around. `originNodeId` is carried so a node can tell its own echo from a
 * peer's message — useful for metrics and for suppressing double delivery when
 * a caller has already written locally.
 */
class Broadcaster {
  private readonly handlers = new Set<Handler>();
  private readonly subscribed = new Set<string>();
  private started = false;

  async start(): Promise<void> {
    if (this.started) return;
    this.started = true;

    redisSubscriber.on('message', (channel: string, payload: string) => {
      let envelope: BroadcastEnvelope;
      try {
        envelope = JSON.parse(payload) as BroadcastEnvelope;
      } catch (error) {
        logger.warn({ err: error, channel }, 'dropping malformed broadcast envelope');
        return;
      }
      for (const handler of this.handlers) {
        try {
          handler(envelope);
        } catch (error) {
          logger.error({ err: error, channel }, 'broadcast handler threw');
        }
      }
    });

    await this.subscribe(RedisChannels.global);
  }

  onMessage(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  async subscribe(channel: string): Promise<void> {
    if (this.subscribed.has(channel)) return;
    this.subscribed.add(channel);
    await redisSubscriber.subscribe(channel);
  }

  async unsubscribe(channel: string): Promise<void> {
    if (!this.subscribed.has(channel)) return;
    this.subscribed.delete(channel);
    await redisSubscriber.unsubscribe(channel);
  }

  private async publish(channel: string, frame: ServerFrame, excludeSocketId?: string): Promise<void> {
    const envelope: BroadcastEnvelope = {
      originNodeId: env.NODE_ID,
      frame,
      ...(excludeSocketId ? { excludeSocketId } : {}),
    };
    await redisPublisher.publish(channel, JSON.stringify(envelope));
  }

  /** Deliver to everyone currently inside one room. */
  async toRoom(roomId: string, frame: ServerFrame, excludeSocketId?: string): Promise<void> {
    await this.publish(RedisChannels.room(roomId), frame, excludeSocketId);
  }

  /** Deliver to every connected client on every node — whale broadcasts only. */
  async toEveryone(frame: ServerFrame): Promise<void> {
    await this.publish(RedisChannels.global, frame);
  }

  /** Deliver to all sockets belonging to a single user. */
  async toUser(userId: string, frame: ServerFrame): Promise<void> {
    await this.publish(RedisChannels.user(userId), frame);
  }
}

export const broadcaster = new Broadcaster();
