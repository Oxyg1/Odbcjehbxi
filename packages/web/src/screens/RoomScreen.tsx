import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { formatCompact } from '@tgdonate/shared';
import { socket } from '../lib/socket.js';
import { haptics } from '../lib/telegram.js';
import { useRoomSubscription } from '../hooks/useRealtime.js';
import { useBackButton } from '../hooks/useTelegramUI.js';
import { useAppStore } from '../store/app.store.js';
import { StandCard } from '../components/StandCard.js';
import { Avatar, Card, Pill, Skeleton } from '../components/ui/primitives.js';

const REACTIONS = ['🔥', '💎', '⭐', '👑', '🫡'] as const;

/**
 * The live plaza: a grid of stand cards that mutate in place as donations land.
 * Nothing here polls — every number moves because a WS frame moved it.
 */
export function RoomScreen() {
  const room = useAppStore((state) => state.currentRoom);
  const stands = useAppStore((state) => state.stands);
  const occupants = useAppStore((state) => state.occupants);
  const setScreen = useAppStore((state) => state.setScreen);
  const focusStand = useAppStore((state) => state.focusStand);
  const socketStatus = useAppStore((state) => state.socketStatus);

  useRoomSubscription(room?.id ?? null);
  useBackButton(true, () => setScreen('rooms'));

  // Busiest stands first so the room always leads with its best content.
  const sorted = useMemo(
    () => [...stands].sort((a, b) => b.totalStarsReceived - a.totalStarsReceived),
    [stands],
  );

  const openStand = (standId: string) => {
    haptics.impact('light');
    focusStand(standId);
    setScreen('stand');
  };

  if (!room) {
    return (
      <div className="safe-top px-4">
        <Skeleton className="h-8 w-40" />
      </div>
    );
  }

  return (
    <div className="safe-top safe-bottom flex flex-col gap-3 px-4">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[22px]">{room.emoji}</span>
            <h1 className="truncate text-[22px] leading-[26px] font-black tracking-[-0.5px]">
              {room.name}
            </h1>
          </div>
          <p className="truncate text-[12px] text-alpha-2">{room.description}</p>
        </div>
        <Pill tone={socketStatus === 'open' ? 'accent' : 'danger'}>
          <span
            className={socketStatus === 'open' ? 'h-1.5 w-1.5 rounded-full bg-accent' : 'h-1.5 w-1.5 rounded-full bg-destructive'}
          />
          {socketStatus === 'open' ? `${room.occupancy} here` : 'reconnecting'}
        </Pill>
      </header>

      {/* Who is in the room right now */}
      {occupants.length > 0 ? (
        <div className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4">
          {occupants.slice(0, 24).map((occupant) => (
            <Avatar
              key={occupant.id}
              src={occupant.photoUrl}
              name={occupant.displayName}
              size={28}
              ring={occupant.badge ? '#f1aa05' : null}
            />
          ))}
          {occupants.length > 24 ? (
            <span className="flex h-7 shrink-0 items-center px-2 text-[12px] font-bold text-alpha-2">
              +{occupants.length - 24}
            </span>
          ) : null}
        </div>
      ) : null}

      {sorted.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-6 text-center">
          <span className="text-[28px]">🏗</span>
          <p className="text-[15px] font-bold">This room is empty</p>
          <p className="text-[13px] text-alpha-2">
            Publish your stand here and be the first booth on the floor.
          </p>
        </Card>
      ) : (
        <motion.div layout className="grid grid-cols-2 gap-2.5">
          {sorted.map((stand) => (
            <StandCard key={stand.id} stand={stand} onOpen={openStand} />
          ))}
        </motion.div>
      )}

      {/* Room-wide reaction bar */}
      {sorted.length > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 flex justify-center pb-[calc(var(--tg-viewport-safe-area-inset-bottom)+var(--tab-bar-height)+10px)]">
          <div className="glass-shadow glass flex items-center gap-1 rounded-full bg-surface-3/85 p-1.5">
            {REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-full text-[16px] transition-transform active:scale-90"
                onClick={() => {
                  haptics.select();
                  // Reactions land on the room's top stand — the crowd cheering
                  // for whoever is currently winning.
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

      <p className="pb-2 text-center text-[11px] text-alpha-3">
        {formatCompact(room.volume24hStars)} ⭐ moved here in the last 24 hours
      </p>
    </div>
  );
}
