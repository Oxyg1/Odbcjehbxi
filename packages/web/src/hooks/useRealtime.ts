import { useEffect } from 'react';
import type { ServerFrame } from '@tgdonate/shared';
import { socket } from '../lib/socket.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore } from '../store/app.store.js';

/**
 * Bridges the socket to the store. Mounted once, at the app root.
 *
 * Haptics fire here rather than in a component so a donation feels the same
 * whether the user is looking at the room, the stand, or the leaderboard.
 */
export function useRealtime(): void {
  useEffect(() => {
    socket.connect();

    const offStatus = socket.onStatus((status) => {
      useAppStore.getState().setSocketStatus(status);
    });

    const offFrame = socket.onFrame((frame: ServerFrame) => {
      const store = useAppStore.getState();

      switch (frame.t) {
        case 'HELLO': {
          store.setMe(frame.user);
          store.setOnlineCount(frame.onlineCount);
          break;
        }
        case 'ROOM_STATE': {
          store.setRoomState(frame.room, frame.stands, frame.occupants);
          break;
        }
        case 'STAND_UPDATE': {
          store.upsertStand(frame.stand);
          break;
        }
        case 'STAND_REMOVED': {
          store.removeStand(frame.standId);
          break;
        }
        case 'DONATION_EVENT': {
          store.applyDonation(frame.donation, frame.standTotals);
          // Tiered feedback: a 5-Star tip should not feel like a 900-Star drop.
          if (frame.donation.tier === 'MICRO') haptics.impact('light');
          else if (frame.donation.tier === 'MAJOR') haptics.impact('medium');
          break;
        }
        case 'GLOBAL_BROADCAST': {
          store.pushGlobalBroadcast({
            donation: frame.donation,
            jump: frame.jump,
            expiresAt: new Date(frame.expiresAt).getTime(),
          });
          haptics.notify('success');
          haptics.impact('heavy');
          break;
        }
        case 'PRESENCE': {
          store.updatePresence(frame.occupancy, frame.joined, frame.left);
          store.setOnlineCount(frame.onlineCount);
          break;
        }
        case 'REACTION': {
          store.pushReaction(frame.standId, frame.emoji);
          break;
        }
        case 'USER_NOTICE': {
          haptics.notify('success');
          break;
        }
        case 'LEADERBOARD_TICK':
        case 'ERROR':
          break;
      }
    });

    // One shared timer retires expired VFX; per-effect timers would mean dozens
    // of pending timeouts during a busy room.
    const sweeper = window.setInterval(() => {
      useAppStore.getState().expireEffects();
    }, 400);

    return () => {
      offStatus();
      offFrame();
      window.clearInterval(sweeper);
      socket.disconnect();
    };
  }, []);
}

/** Join a room for as long as the calling component is mounted. */
export function useRoomSubscription(roomId: string | null): void {
  useEffect(() => {
    if (!roomId) return;
    socket.joinRoom(roomId);
    return () => socket.leaveRoom();
  }, [roomId]);
}

/** Watch a single stand (deep links, the editor preview). */
export function useStandSubscription(standId: string | null): void {
  useEffect(() => {
    if (!standId) return;
    socket.watchStand(standId);
    return () => socket.unwatchStand(standId);
  }, [standId]);
}
