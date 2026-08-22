import { create } from 'zustand';
import {
  GLOBAL_BROADCAST_DURATION_MS,
  ROOM_BROADCAST_DURATION_MS,
  type DonationEventPayload,
  type PublicUser,
  type Room,
  type Stand,
} from '@tgdonate/shared';
import type { SocketStatus } from '../lib/socket.js';

/**
 * `floor` replaces the old rooms-list + room pair: rooms are chips on the floor
 * itself, so there is no separate chooser screen to navigate through.
 */
export type Screen = 'floor' | 'stand' | 'editor' | 'leaderboard' | 'market' | 'profile';

/** A donation currently playing its VFX on a specific stand card. */
export interface ActiveEffect {
  id: string;
  standId: string;
  tier: 'MICRO' | 'MAJOR' | 'WHALE';
  amountStars: number;
  donorName: string;
  expiresAt: number;
}

export interface RoomBanner {
  id: string;
  donation: DonationEventPayload;
  expiresAt: number;
}

export interface GlobalBroadcast {
  id: string;
  donation: DonationEventPayload;
  jump: { roomId: string | null; standId: string };
  expiresAt: number;
}

interface AppState {
  screen: Screen;
  socketStatus: SocketStatus;
  onlineCount: number;

  me: PublicUser | null;
  unlockedThemeIds: string[];

  rooms: Room[];
  currentRoom: Room | null;
  stands: Stand[];
  occupants: PublicUser[];

  /** Stand opened from a card tap or a deep link. */
  focusedStandId: string | null;
  myStand: Stand | null;

  activeEffects: ActiveEffect[];
  roomBanner: RoomBanner | null;
  globalBroadcast: GlobalBroadcast | null;
  reactions: Array<{ id: string; standId: string; emoji: string }>;

  setScreen: (screen: Screen) => void;
  setSocketStatus: (status: SocketStatus) => void;
  setOnlineCount: (count: number) => void;
  setMe: (user: PublicUser | null, unlockedThemeIds?: string[]) => void;
  setRooms: (rooms: Room[]) => void;
  setRoomState: (room: Room, stands: Stand[], occupants: PublicUser[]) => void;
  upsertStand: (stand: Stand) => void;
  removeStand: (standId: string) => void;
  setMyStand: (stand: Stand | null) => void;
  focusStand: (standId: string | null) => void;
  applyDonation: (
    donation: DonationEventPayload,
    totals: {
      standId: string;
      totalStarsReceived: number;
      totalGiftsReceived: number;
      supporterCount: number;
    },
  ) => void;
  pushGlobalBroadcast: (broadcast: Omit<GlobalBroadcast, 'id' | 'expiresAt'> & { expiresAt?: number }) => void;
  dismissGlobalBroadcast: () => void;
  dismissRoomBanner: () => void;
  expireEffects: () => void;
  pushReaction: (standId: string, emoji: string) => void;
  updatePresence: (occupancy: number, joined: PublicUser[], left: string[]) => void;
}

let effectCounter = 0;
function nextId(prefix: string): string {
  effectCounter += 1;
  return `${prefix}-${Date.now()}-${effectCounter}`;
}

export const useAppStore = create<AppState>((set, get) => ({
  screen: 'floor',
  socketStatus: 'closed',
  onlineCount: 0,

  me: null,
  unlockedThemeIds: [],

  rooms: [],
  currentRoom: null,
  stands: [],
  occupants: [],

  focusedStandId: null,
  myStand: null,

  activeEffects: [],
  roomBanner: null,
  globalBroadcast: null,
  reactions: [],

  setScreen: (screen) => set({ screen }),
  setSocketStatus: (socketStatus) => set({ socketStatus }),
  setOnlineCount: (onlineCount) => set({ onlineCount }),

  setMe: (me, unlockedThemeIds) =>
    set((state) => ({
      me,
      unlockedThemeIds: unlockedThemeIds ?? state.unlockedThemeIds,
    })),

  setRooms: (rooms) => set({ rooms }),

  setRoomState: (currentRoom, stands, occupants) =>
    set({ currentRoom, stands, occupants }),

  upsertStand: (stand) =>
    set((state) => {
      const index = state.stands.findIndex((candidate) => candidate.id === stand.id);
      const stands =
        index === -1
          ? [...state.stands, stand]
          : state.stands.map((candidate) => (candidate.id === stand.id ? stand : candidate));

      return {
        stands,
        myStand: state.myStand?.id === stand.id ? stand : state.myStand,
      };
    }),

  removeStand: (standId) =>
    set((state) => ({ stands: state.stands.filter((stand) => stand.id !== standId) })),

  setMyStand: (myStand) => set({ myStand }),
  focusStand: (focusedStandId) => set({ focusedStandId }),

  /**
   * Fold a donation into local state: patch the stand's counters so the number
   * moves immediately, then queue the tier-appropriate effect.
   */
  applyDonation: (donation, totals) =>
    set((state) => {
      const stands = state.stands.map((stand) =>
        stand.id === totals.standId
          ? {
              ...stand,
              totalStarsReceived: totals.totalStarsReceived,
              totalGiftsReceived: totals.totalGiftsReceived,
              supporterCount: totals.supporterCount,
            }
          : stand,
      );

      const myStand =
        state.myStand && state.myStand.id === totals.standId
          ? {
              ...state.myStand,
              totalStarsReceived: totals.totalStarsReceived,
              totalGiftsReceived: totals.totalGiftsReceived,
              supporterCount: totals.supporterCount,
            }
          : state.myStand;

      const effect: ActiveEffect = {
        id: nextId('fx'),
        standId: donation.standId,
        tier: donation.tier,
        amountStars: donation.amountStars,
        donorName: donation.isAnonymous
          ? 'Anonymous'
          : donation.donor?.displayName ?? 'Someone',
        expiresAt: Date.now() + (donation.tier === 'MICRO' ? 2_200 : ROOM_BROADCAST_DURATION_MS),
      };

      // MAJOR and WHALE also take over the room with a banner. WHALE gets the
      // full-screen overlay instead, pushed separately by the socket handler.
      const roomBanner =
        donation.tier === 'MAJOR'
          ? {
              id: nextId('banner'),
              donation,
              expiresAt: Date.now() + ROOM_BROADCAST_DURATION_MS,
            }
          : state.roomBanner;

      return {
        stands,
        myStand,
        activeEffects: [...state.activeEffects.slice(-11), effect],
        roomBanner,
      };
    }),

  pushGlobalBroadcast: (broadcast) =>
    set({
      globalBroadcast: {
        id: nextId('global'),
        donation: broadcast.donation,
        jump: broadcast.jump,
        expiresAt: broadcast.expiresAt ?? Date.now() + GLOBAL_BROADCAST_DURATION_MS,
      },
    }),

  dismissGlobalBroadcast: () => set({ globalBroadcast: null }),
  dismissRoomBanner: () => set({ roomBanner: null }),

  expireEffects: () => {
    const now = Date.now();
    const state = get();
    const activeEffects = state.activeEffects.filter((effect) => effect.expiresAt > now);
    const roomBanner = state.roomBanner && state.roomBanner.expiresAt > now ? state.roomBanner : null;
    const globalBroadcast =
      state.globalBroadcast && state.globalBroadcast.expiresAt > now ? state.globalBroadcast : null;

    // Only write when something actually changed, so the timer does not force a
    // re-render of every subscriber every tick.
    if (
      activeEffects.length !== state.activeEffects.length ||
      roomBanner !== state.roomBanner ||
      globalBroadcast !== state.globalBroadcast
    ) {
      set({ activeEffects, roomBanner, globalBroadcast });
    }
  },

  pushReaction: (standId, emoji) =>
    set((state) => ({
      reactions: [...state.reactions.slice(-19), { id: nextId('react'), standId, emoji }],
    })),

  updatePresence: (occupancy, joined, left) =>
    set((state) => {
      const byId = new Map(state.occupants.map((occupant) => [occupant.id, occupant]));
      for (const user of joined) byId.set(user.id, user);
      for (const userId of left) byId.delete(userId);

      return {
        occupants: [...byId.values()],
        currentRoom: state.currentRoom ? { ...state.currentRoom, occupancy } : null,
      };
    }),
}));
