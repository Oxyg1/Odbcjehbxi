import { motion } from 'framer-motion';
import { cn } from '../lib/cn.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore, type Screen } from '../store/app.store.js';

const TABS: Array<{ id: Screen; label: string; icon: string }> = [
  { id: 'rooms', label: 'Plazas', icon: '🏛' },
  { id: 'leaderboard', label: 'Ranks', icon: '🐋' },
  { id: 'editor', label: 'My Stand', icon: '🎪' },
  { id: 'profile', label: 'Profile', icon: '👤' },
];

/**
 * Fixed bottom navigation, 62px tall to match the reference app's switcher,
 * floating on a blurred glass pane above the safe-area inset.
 */
export function TabBar() {
  const screen = useAppStore((state) => state.screen);
  const setScreen = useAppStore((state) => state.setScreen);

  // `room` and `stand` are pushed on top of the Plazas tab, so that tab stays
  // highlighted while the user is deeper in the stack.
  const activeTab: Screen =
    screen === 'room' || screen === 'stand' ? 'rooms' : screen === 'market' ? 'editor' : screen;

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40"
      style={{ paddingBottom: 'var(--tg-viewport-safe-area-inset-bottom)' }}
    >
      <div className="glass-shadow glass mx-3 mb-2 flex h-[62px] items-stretch rounded-full bg-surface-3/85 px-1.5">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                haptics.select();
                setScreen(tab.id);
              }}
              className="relative flex flex-1 flex-col items-center justify-center gap-0.5"
            >
              {active ? (
                <motion.span
                  layoutId="tab-pill"
                  className="absolute inset-x-1.5 inset-y-2 rounded-full bg-white/10"
                  transition={{ type: 'spring', damping: 26, stiffness: 340 }}
                />
              ) : null}
              <span className={cn('relative text-[19px] leading-none', !active && 'opacity-55')}>
                {tab.icon}
              </span>
              <span
                className={cn(
                  'relative text-[10px] leading-none font-bold',
                  active ? 'text-white' : 'text-alpha-2',
                )}
              >
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
