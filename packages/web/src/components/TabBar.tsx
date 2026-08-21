import { cn } from '../lib/cn.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore, type Screen } from '../store/app.store.js';

const TABS: Array<{ id: Screen; label: string; icon: string; accent: string }> = [
  { id: 'rooms', label: 'Plazas', icon: '🏛', accent: '#49df64' },
  { id: 'leaderboard', label: 'Ranks', icon: '🐋', accent: '#68fbdd' },
  { id: 'editor', label: 'My Stand', icon: '🎪', accent: '#f1aa05' },
  { id: 'profile', label: 'Profile', icon: '👤', accent: '#1689ff' },
];

/**
 * Fixed bottom navigation, 62px tall on a blurred glass pane.
 *
 * The reference build separates active from inactive with opacity and hue
 * rather than a moving highlight: inactive sits at 0.4 and inherits the
 * foreground colour, active goes to full opacity, takes the tab's accent, and
 * its icon scales up slightly. Cheaper than a layout animation and it reads
 * more clearly at this size.
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
      className="app-shell fixed inset-x-0 bottom-0 z-40"
      style={{ paddingBottom: 'var(--tg-safe-bottom)' }}
    >
      <div className="glass-shadow glass mx-3 mb-2 flex h-[var(--tab-bar-height)] items-stretch rounded-full bg-surface-3/85 px-1.5">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                if (active) return;
                haptics.select();
                setScreen(tab.id);
              }}
              className={cn(
                'flex flex-1 flex-col items-center justify-center gap-1 rounded-full',
                'transition-[opacity,color] duration-150',
                active ? 'opacity-100' : 'opacity-40',
              )}
              style={active ? { color: tab.accent } : undefined}
            >
              <span
                className="text-[19px] leading-none transition-transform duration-150"
                style={{ transform: active ? 'scale(1.1)' : 'scale(1)' }}
              >
                {tab.icon}
              </span>
              <span className="text-[10px] leading-[1.2] font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
