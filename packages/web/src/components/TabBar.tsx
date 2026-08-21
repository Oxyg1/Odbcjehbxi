import { haptics } from '../lib/telegram.js';
import { useAppStore, type Screen } from '../store/app.store.js';

const TABS: Array<{ id: Screen; label: string; icon: string; accent: string }> = [
  { id: 'rooms', label: 'Plazas', icon: '🏛', accent: '#49df64' },
  { id: 'leaderboard', label: 'Ranks', icon: '🐋', accent: '#68fbdd' },
  { id: 'editor', label: 'My Stand', icon: '🎪', accent: '#f1aa05' },
  { id: 'profile', label: 'Profile', icon: '👤', accent: '#1689ff' },
];

/**
 * Bottom navigation, transcribed from the reference switcher.
 *
 * The selection pill is a single `::after` on the grid container (see
 * `tab-switcher` in the stylesheet), positioned by `data-active` holding the
 * active column index. Driving it from one data attribute keeps the travel a
 * pure compositor transform and means the DOM carries no extra element per tab.
 */
export function TabBar() {
  const screen = useAppStore((state) => state.screen);
  const setScreen = useAppStore((state) => state.setScreen);

  // `room` and `stand` are pushed on top of the Plazas tab, so that tab stays
  // highlighted while the user is deeper in the stack.
  const activeTab: Screen =
    screen === 'room' || screen === 'stand' ? 'rooms' : screen === 'market' ? 'editor' : screen;

  const activeIndex = TABS.findIndex((tab) => tab.id === activeTab);
  const accent = TABS[activeIndex]?.accent ?? '#1689ff';

  return (
    <nav
      className="app-shell fixed inset-x-0 bottom-0 z-40 px-3"
      style={{ paddingBottom: `calc(var(--tg-safe-bottom) + 8px)` }}
    >
      <div
        className="tab-switcher"
        data-active={activeIndex}
        style={{
          ['--tab-count' as string]: TABS.length,
          ['--tab-accent' as string]: accent,
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              data-active={active}
              aria-current={active ? 'page' : undefined}
              onClick={() => {
                if (active) return;
                haptics.select();
                setScreen(tab.id);
              }}
              className="tab-option"
              // Each tab tints the pill and its own label with its own hue, so
              // the bar reads as four destinations rather than one control.
              style={active ? { ['--tab-accent' as string]: tab.accent } : undefined}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-title">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
