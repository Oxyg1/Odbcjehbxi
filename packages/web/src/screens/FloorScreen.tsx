import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatCompact, type DonationEventPayload, type Room } from '@tgdonate/shared';
import { api } from '../lib/api.js';
import { cn } from '../lib/cn.js';
import { socket } from '../lib/socket.js';
import { haptics } from '../lib/telegram.js';
import { useRoomSubscription } from '../hooks/useRealtime.js';
import { useQuickDonate } from '../hooks/useQuickDonate.js';
import { useAppStore } from '../store/app.store.js';
import { StandCard } from '../components/StandCard.js';
import { DonationTicker } from '../components/DonationTicker.js';
import { Button, EmptyState, Skeleton } from '../components/ui/primitives.js';

const REACTIONS = ['🔥', '💎', '⭐', '👑', '🫡'] as const;

/**
 * The floor — the app's home.
 *
 * Rooms used to be a screen of their own, which meant every visit began on a
 * list of links rather than on the product. They are chips here instead: the
 * stands of the selected room are always on screen, and switching rooms is one
 * tap that never leaves the floor.
 */
export function FloorScreen() {
  const rooms = useAppStore((state) => state.rooms);
  const setRooms = useAppStore((state) => state.setRooms);
  const currentRoom = useAppStore((state) => state.currentRoom);
  const setRoomState = useAppStore((state) => state.setRoomState);
  const stands = useAppStore((state) => state.stands);
  const occupants = useAppStore((state) => state.occupants);
  const onlineCount = useAppStore((state) => state.onlineCount);
  const socketStatus = useAppStore((state) => state.socketStatus);
  const setScreen = useAppStore((state) => state.setScreen);
  const focusStand = useAppStore((state) => state.focusStand);

  const [activity, setActivity] = useState<DonationEventPayload[]>([]);
  const [loading, setLoading] = useState(true);

  const { donate, error, clearError } = useQuickDonate();

  useRoomSubscription(currentRoom?.id ?? null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [roomsResponse, activityResponse] = await Promise.all([
          api.rooms(),
          api.activity(20),
        ]);
        if (cancelled) return;
        setRooms(roomsResponse.rooms);
        setActivity(activityResponse.donations);

        // Land the user *in* a room rather than on a chooser.
        if (!useAppStore.getState().currentRoom && roomsResponse.rooms[0]) {
          setRoomState(roomsResponse.rooms[0], [], []);
        }
      } catch {
        // The socket fills the floor in once it connects.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setRooms, setRoomState]);

  const sorted = useMemo(
    () => [...stands].sort((a, b) => b.totalStarsReceived - a.totalStarsReceived),
    [stands],
  );

  const pickRoom = (room: Room) => {
    if (room.id === currentRoom?.id) return;
    haptics.impact('medium');
    setRoomState(room, [], []);
  };

  const openStand = (standId: string) => {
    haptics.impact('light');
    focusStand(standId);
    setScreen('stand');
  };

  return (
    <div className="safe-top safe-bottom flex flex-col gap-2.5">
      <header className="flex items-center justify-between px-4">
        <h1 className="text-[24px] leading-[28px] font-black tracking-[-0.6px]">
          The Floor
        </h1>
        <span
          className={cn(
            'glass-shadow flex items-center gap-1.5 rounded-full px-2.5 py-1',
            'text-[11px] font-bold',
            socketStatus === 'open' ? 'bg-accent/15 text-accent' : 'bg-destructive/15 text-destructive',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              socketStatus === 'open' ? 'animate-pulse-ring bg-accent' : 'bg-destructive',
            )}
          />
          {socketStatus === 'open' ? `${formatCompact(onlineCount)} live` : 'reconnecting'}
        </span>
      </header>

      <DonationTicker donations={activity} />

      {/* Room chips */}
      <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 pb-1">
        {loading && rooms.length === 0
          ? Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-[38px] w-[120px] shrink-0 rounded-full" />
            ))
          : rooms.map((room) => {
              const active = room.id === currentRoom?.id;
              return (
                <button
                  key={room.id}
                  type="button"
                  onClick={() => pickRoom(room)}
                  className={cn(
                    'pressable flex shrink-0 items-center gap-1.5 rounded-full px-3 py-2',
                    'text-[13px] font-bold whitespace-nowrap',
                    active ? 'neon-ring' : 'glass-shadow bg-surface-3/70 text-alpha-2',
                  )}
                  style={
                    active
                      ? {
                          ['--neon' as string]: room.accent,
                          backgroundColor: `color-mix(in srgb, ${room.accent} 16%, transparent)`,
                          color: room.accent,
                        }
                      : undefined
                  }
                >
                  <span className="text-[15px]">{room.emoji}</span>
                  {room.name}
                  {room.volume24hStars > 1000 ? <span className="text-[11px]">🔥</span> : null}
                </button>
              );
            })}
      </div>

      {/* Who is on the floor */}
      {occupants.length > 0 ? (
        <div className="no-scrollbar flex items-center gap-1 px-4">
          {occupants.slice(0, 14).map((occupant, index) => (
            <motion.img
              key={occupant.id}
              src={occupant.photoUrl ?? ''}
              alt=""
              className="animate-drift h-6 w-6 shrink-0 rounded-full bg-surface-5 object-cover ring-1 ring-white/15"
              style={{ animationDelay: `${index * 0.25}s` }}
              onError={(event) => {
                event.currentTarget.style.visibility = 'hidden';
              }}
            />
          ))}
          <span className="ml-1 text-[11px] font-semibold text-alpha-3">
            {occupants.length} here
          </span>
        </div>
      ) : null}

      {error ? (
        <button
          type="button"
          onClick={clearError}
          className="mx-4 squircle bg-destructive/15 px-3 py-2 text-left text-[12px] text-destructive"
        >
          {error} — tap to dismiss
        </button>
      ) : null}

      {/* Stand grid */}
      <div className="px-3">
        {loading && sorted.length === 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-[190px] w-full squircle-3xl" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <EmptyState
            icon="🏗"
            title="This plaza is empty"
            body="Be the first booth on the floor — it takes about a minute."
            action={{ label: 'Build my stand', onClick: () => setScreen('editor') }}
          />
        ) : (
          <motion.div layout className="grid grid-cols-2 gap-2">
            <AnimatePresence mode="popLayout">
              {sorted.map((stand) => (
                <StandCard
                  key={stand.id}
                  stand={stand}
                  onOpen={openStand}
                  onQuickDonate={(standId, amount) => void donate(standId, amount)}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>

      {/* Cheer rail */}
      {sorted.length > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 flex justify-center pb-[calc(var(--tg-safe-bottom)+var(--tab-bar-clearance)+6px)]">
          <div className="glass-shadow glass flex items-center gap-1 rounded-full bg-surface-3/85 p-1.5">
            {REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-full text-[16px] transition-transform active:scale-90"
                onClick={() => {
                  haptics.select();
                  const target = sorted[0];
                  if (target) socket.react(target.id, emoji);
                }}
              >
                {emoji}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {currentRoom ? (
        <p className="px-4 text-center text-[11px] text-alpha-3">
          {formatCompact(currentRoom.volume24hStars)} ⭐ moved here in 24h
        </p>
      ) : null}

      {sorted.length > 0 ? (
        <div className="px-4">
          <Button
            variant="ghost"
            shape="soft"
            fullWidth
            onClick={() => setScreen('editor')}
          >
            🎪 Open my stand
          </Button>
        </div>
      ) : null}
    </div>
  );
}
