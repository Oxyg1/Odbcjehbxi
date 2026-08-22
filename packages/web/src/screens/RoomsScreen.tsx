import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { formatCompact, type DonationEventPayload, type Room } from '@tgdonate/shared';
import { api, ApiError, apiOrigin } from '../lib/api.js';
import { cn } from '../lib/cn.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore } from '../store/app.store.js';
import { Avatar, Card, LoadFailed, Pill, Skeleton } from '../components/ui/primitives.js';

/** Room picker + live global activity ticker. The app's landing surface. */
export function RoomsScreen() {
  const rooms = useAppStore((state) => state.rooms);
  const setRooms = useAppStore((state) => state.setRooms);
  const setScreen = useAppStore((state) => state.setScreen);
  const setRoomState = useAppStore((state) => state.setRoomState);
  const onlineCount = useAppStore((state) => state.onlineCount);

  const [activity, setActivity] = useState<DonationEventPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

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
      } catch (caught) {
        // Report it rather than rendering an empty list that looks like a room
        // list with nothing in it.
        if (cancelled) return;
        setLoadError(
          caught instanceof ApiError
            ? `${caught.message} (${[caught.code, caught.reason].filter(Boolean).join(' / ')}, HTTP ${caught.status})`
            : 'Could not reach the server',
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setRooms, reloadKey]);

  const enterRoom = (room: Room) => {
    haptics.impact('medium');
    // Clear the previous room's stands so the grid does not flash stale cards
    // while the new ROOM_STATE frame is in flight.
    setRoomState(room, [], []);
    setScreen('room');
  };

  if (loadError && rooms.length === 0) {
    return (
      <LoadFailed
        title="Could not load the plazas"
        message={loadError}
        endpoint={apiOrigin}
        onRetry={() => {
          setLoadError(null);
          setLoading(true);
          setReloadKey((key) => key + 1);
        }}
      />
    );
  }

  return (
    <div className="safe-top safe-bottom flex flex-col gap-4 px-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[26px] leading-[30px] font-black tracking-[-0.6px]">Plazas</h1>
          <p className="text-[13px] text-alpha-2">Pick a room, pick a stand, send Stars.</p>
        </div>
        <Pill tone="accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          {formatCompact(onlineCount)} online
        </Pill>
      </header>

      <section className="flex flex-col gap-2">
        {loading
          ? Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-[86px] w-full squircle-3xl" />
            ))
          : rooms.map((room, index) => (
              <motion.button
                key={room.id}
                type="button"
                onClick={() => enterRoom(room)}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }}
                whileTap={{ scale: 0.985 }}
                className="text-left"
              >
                <Card className="flex items-center gap-3 p-3">
                  <div
                    className="pointer-events-none absolute inset-y-0 left-0 w-[120px] opacity-30"
                    style={{
                      background: `radial-gradient(circle at 0% 50%, ${room.accent} 0%, transparent 70%)`,
                    }}
                  />
                  <div
                    className="squircle-lg relative flex h-12 w-12 shrink-0 items-center justify-center text-[24px]"
                    style={{ backgroundColor: `color-mix(in srgb, ${room.accent} 18%, transparent)` }}
                  >
                    {room.emoji}
                  </div>
                  <div className="relative min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="truncate text-[15px] font-bold">{room.name}</p>
                      {room.volume24hStars > 1000 ? <Pill tone="gold">🔥 Hot</Pill> : null}
                    </div>
                    <p className="truncate text-[12px] text-alpha-2">{room.description}</p>
                    <div className="mt-1 flex items-center gap-2 text-[11px] font-semibold text-alpha-2">
                      <span
                        className={cn(
                          room.occupancy >= room.capacity ? 'text-destructive' : 'text-accent',
                        )}
                      >
                        {room.occupancy}/{room.capacity}
                      </span>
                      <span>·</span>
                      <span>⭐ {formatCompact(room.volume24hStars)} / 24h</span>
                    </div>
                  </div>
                </Card>
              </motion.button>
            ))}
      </section>

      {activity.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">
            Live activity
          </h2>
          <Card className="flex flex-col divide-y divide-white/6 p-0" glass={false} variant="flat">
            {activity.slice(0, 8).map((donation) => (
              <div key={donation.id} className="flex items-center gap-2.5 px-3 py-2.5">
                <Avatar
                  src={donation.donor?.photoUrl ?? null}
                  name={donation.isAnonymous ? 'Anonymous' : donation.donor?.displayName ?? '?'}
                  size={28}
                />
                <p className="min-w-0 flex-1 truncate text-[13px]">
                  <span className="font-bold">
                    {donation.isAnonymous ? 'Anonymous' : donation.donor?.displayName ?? 'Someone'}
                  </span>
                  <span className="text-alpha-2"> → </span>
                  <span className="text-alpha-1">{donation.standTitle}</span>
                </p>
                <span
                  className={cn(
                    'shrink-0 text-[13px] font-black',
                    donation.tier === 'WHALE'
                      ? 'text-tifany'
                      : donation.tier === 'MAJOR'
                        ? 'text-gold'
                        : 'text-accent',
                  )}
                >
                  {donation.gift ? '🎁' : `${formatCompact(donation.amountStars)} ⭐`}
                </span>
              </div>
            ))}
          </Card>
        </section>
      ) : null}
    </div>
  );
}
