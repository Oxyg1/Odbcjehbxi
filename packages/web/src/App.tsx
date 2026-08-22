import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { TonConnectUIProvider } from '@tonconnect/ui-react';
import { api } from './lib/api.js';
import { initTelegram, isInsideTelegram } from './lib/telegram.js';
import { useRealtime } from './hooks/useRealtime.js';
import { useAppStore } from './store/app.store.js';
import { MegaphoneOverlay, RoomBanner } from './components/MegaphoneOverlay.js';
import { TabBar } from './components/TabBar.js';
import { EditorScreen } from './screens/EditorScreen.js';
import { LeaderboardScreen } from './screens/LeaderboardScreen.js';
import { ProfileScreen } from './screens/ProfileScreen.js';
import { FloorScreen } from './screens/FloorScreen.js';
import { StandScreen } from './screens/StandScreen.js';

const MANIFEST_URL =
  import.meta.env.VITE_TONCONNECT_MANIFEST ??
  `${window.location.origin}/tonconnect-manifest.json`;

export function App() {
  return (
    <TonConnectUIProvider manifestUrl={MANIFEST_URL}>
      <Shell />
    </TonConnectUIProvider>
  );
}

function Shell() {
  const screen = useAppStore((state) => state.screen);
  const setScreen = useAppStore((state) => state.setScreen);
  const setMe = useAppStore((state) => state.setMe);
  const setRooms = useAppStore((state) => state.setRooms);
  const setRoomState = useAppStore((state) => state.setRoomState);
  const focusStand = useAppStore((state) => state.focusStand);

  useRealtime();

  useEffect(() => {
    initTelegram();

    void (async () => {
      try {
        const [me, roomsResponse] = await Promise.all([api.me(), api.rooms()]);
        setMe(me.user, me.unlockedThemeIds);
        setRooms(roomsResponse.rooms);

        // Deep link handling: `?startapp=stand_<id>` or `room_<slug>` decides
        // where the session actually begins.
        const startParam = me.startParam;
        if (!startParam) return;

        if (startParam.startsWith('stand_')) {
          const standId = startParam.slice('stand_'.length);
          const { stand } = await api.stand(standId);
          focusStand(stand.id);

          // Land the viewer inside the stand's room so the live layer works.
          if (stand.roomId) {
            const room = roomsResponse.rooms.find((candidate) => candidate.id === stand.roomId);
            if (room) setRoomState(room, [stand], []);
          }
          setScreen('stand');
        } else if (startParam.startsWith('room_')) {
          const slug = startParam.slice('room_'.length);
          const room = roomsResponse.rooms.find((candidate) => candidate.slug === slug);
          if (room) {
            setRoomState(room, [], []);
            setScreen('floor');
          }
        } else if (startParam === 'leaderboard') {
          setScreen('leaderboard');
        }
      } catch {
        // Bootstrap failures leave the user on the Plazas shell rather than a
        // blank screen; the socket will fill it in once it connects.
      }
    })();
  }, [setMe, setRooms, setRoomState, setScreen, focusStand]);

  return (
    <div className="app-shell relative min-h-dvh">
      {!isInsideTelegram() ? (
        <div className="bg-gold/15 px-4 py-2 text-center text-[12px] font-semibold text-gold">
          Running outside Telegram — payments and haptics are unavailable.
        </div>
      ) : null}

      <AnimatePresence mode="wait">
        <motion.main
          key={screen}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.18 }}
        >
          {screen === 'floor' ? <FloorScreen /> : null}
          {screen === 'stand' ? <StandScreen /> : null}
          {screen === 'editor' ? <EditorScreen /> : null}
          {screen === 'leaderboard' ? <LeaderboardScreen /> : null}
          {screen === 'profile' ? <ProfileScreen /> : null}
        </motion.main>
      </AnimatePresence>

      <RoomBanner />
      <MegaphoneOverlay />
      <TabBar />
    </div>
  );
}
